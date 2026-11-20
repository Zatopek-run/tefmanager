"""Staff con attributi (PIANOLAVORO E.1): effetti dei clinici in funzione degli attributi 1-20. Senza Qt.

Due garanzie: (1) al valore di riferimento ogni effetto è IDENTICO a quello di prima degli attributi (nessuno spostamento
del bilanciamento né dell'RNG); (2) sopra/sotto il riferimento l'effetto cresce/cala nella direzione giusta.
"""

from __future__ import annotations

import os
import random
import subprocess
import sys
import unittest
from copy import deepcopy
from pathlib import Path

from models.entities import (
    CALM_SIGMA,
    DOCTOR_RISK_FLOOR,
    IMPULSIVE_SIGMA,
    MENTAL_SIGMA_FLOOR,
    STAFF_ATTR_MAX,
    STAFF_ATTR_MIN,
    STAFF_ATTR_REF,
    STAFF_ATTRIBUTES,
    GameState,
    PeriodizationPhase,
    Personality,
    StaffMember,
    StaffRole,
    TrainingFocus,
)
from models.generator import STAFF_CATALOGUE, create_initial_staff, ensure_staff_market, generate_initial_roster
from models.simulation import _recalculate_form, apply_weekly_training
from models.staff import (
    describe_attributes,
    doctor_risk_multiplier,
    hired_staff_attributes,
    impulsive_sigma,
    mental_form_bonus,
    normalize_attributes,
    physio_cuts_injury_week,
    physio_fatigue_relief,
    physio_heal_step_chance,
    physio_injury_recovery_bonus,
)

REF = STAFF_ATTR_REF


def attrs_for(role: StaffRole, value: int) -> dict:
    """Staff assunto di un ruolo con tutti gli attributi a `value` (forma di `hired_staff_attributes`)."""
    return {role: {key: value for key, _label in STAFF_ATTRIBUTES[role]}}


def tired_athlete(seed: int = 1, fatigue: int = 88):
    athlete = generate_initial_roster(rng=random.Random(seed))[0]
    athlete.personality = Personality.LEADER  # nessun modificatore di personalità sul rischio
    athlete.training_focus = TrainingFocus.EXPLOSIVE_POWER
    athlete.periodization = PeriodizationPhase.PREP_SPECIFICA
    athlete.fatigue = fatigue
    athlete.resilience = 40
    athlete.age = 25
    athlete.doping_boost_weeks = 0
    athlete.injured_weeks = 0
    return athlete


def count_training_injuries(roles: set, attrs, seeds: int = 400) -> int:
    base = tired_athlete()
    n = 0
    for seed in range(seeds):
        a = deepcopy(base)
        _g, injury, _r, _s = apply_weekly_training(
            a, hired_roles=roles, rng=random.Random(seed), staff_attrs=attrs
        )
        n += 1 if injury else 0
    return n


class TestNeutralAtReference(unittest.TestCase):
    """Al riferimento le cifre sono quelle di prima di E.1."""

    def test_pure_functions_give_the_old_numbers(self) -> None:
        self.assertEqual(physio_fatigue_relief(REF), 7)
        self.assertEqual(physio_injury_recovery_bonus(REF), 8)
        self.assertEqual(physio_heal_step_chance(REF), 0.55)
        self.assertTrue(physio_cuts_injury_week(REF))
        self.assertEqual(doctor_risk_multiplier(REF), 0.55)
        self.assertEqual(mental_form_bonus(REF), 4)
        self.assertEqual(impulsive_sigma(False), 5.6)
        self.assertEqual(impulsive_sigma(True, REF), 3.8)

    def test_constants_match_what_the_simulation_used_to_hardcode(self) -> None:
        self.assertEqual((IMPULSIVE_SIGMA, CALM_SIGMA), (5.6, 3.8))

    def test_training_without_attributes_equals_training_at_reference(self) -> None:
        # Stesso seme: chiamare senza `staff_attrs` (come i test di prima) o con tutto al riferimento è la stessa cosa.
        roles = {StaffRole.PHYSIO, StaffRole.DOCTOR, StaffRole.MENTAL_COACH}
        full = {}
        for role in roles:
            full.update(attrs_for(role, REF))
        for seed in range(60):
            a, b = tired_athlete(fatigue=75), tired_athlete(fatigue=75)
            out_a = apply_weekly_training(a, hired_roles=roles, rng=random.Random(seed))
            out_b = apply_weekly_training(b, hired_roles=roles, rng=random.Random(seed), staff_attrs=full)
            self.assertEqual(out_a, out_b)
            self.assertEqual(a, b)

    def test_form_with_mental_coach_at_reference_is_the_old_bonus(self) -> None:
        a = tired_athlete(fatigue=40)
        with_coach = _recalculate_form(a, False, False, True, False)
        without = _recalculate_form(a, False, False, False, False)
        self.assertGreaterEqual(with_coach - without, 3)  # +4 al bersaglio, arrotondato dopo il 65%
        self.assertEqual(with_coach, _recalculate_form(a, False, False, True, False, mental_bonus=mental_form_bonus(REF)))


class TestEffectDirection(unittest.TestCase):
    def test_functions_are_monotonic_in_the_attribute(self) -> None:
        for lo, hi in ((STAFF_ATTR_MIN, REF), (REF, STAFF_ATTR_MAX)):
            self.assertLessEqual(physio_fatigue_relief(lo), physio_fatigue_relief(hi))
            self.assertLessEqual(physio_injury_recovery_bonus(lo), physio_injury_recovery_bonus(hi))
            self.assertLess(physio_heal_step_chance(lo), physio_heal_step_chance(hi))
            self.assertGreater(doctor_risk_multiplier(lo), doctor_risk_multiplier(hi))
            self.assertLessEqual(mental_form_bonus(lo), mental_form_bonus(hi))
            self.assertGreater(impulsive_sigma(True, lo), impulsive_sigma(True, hi))

    def test_limits_hold_at_the_extremes(self) -> None:
        self.assertGreaterEqual(doctor_risk_multiplier(STAFF_ATTR_MAX), DOCTOR_RISK_FLOOR)
        self.assertLessEqual(doctor_risk_multiplier(STAFF_ATTR_MIN), 1.0)
        self.assertLessEqual(physio_heal_step_chance(STAFF_ATTR_MAX), 0.95)
        self.assertGreaterEqual(impulsive_sigma(True, STAFF_ATTR_MAX), MENTAL_SIGMA_FLOOR)
        self.assertLessEqual(impulsive_sigma(True, STAFF_ATTR_MIN), IMPULSIVE_SIGMA)  # mai peggio che senza preparatore
        self.assertFalse(physio_cuts_injury_week(1))

    def test_prevention_reduces_training_injuries(self) -> None:
        roles = {StaffRole.DOCTOR}
        low = count_training_injuries(roles, attrs_for(StaffRole.DOCTOR, 3))
        high = count_training_injuries(roles, attrs_for(StaffRole.DOCTOR, 19))
        none = count_training_injuries(set(), None)
        self.assertGreater(low, high, (low, high))
        self.assertGreater(none, low)  # anche un medico scarso aiuta un po', non peggiora
        self.assertGreater(high, 0)  # il campione è abbastanza grande da vedere infortuni

    def test_a_skilled_physio_cuts_injury_length_and_heals_faster(self) -> None:
        # Competenza alta: più doppi passi di guarigione. Competenza sotto soglia: nessuna settimana tolta.
        def weeks_left(value: int) -> int:
            total = 0
            for seed in range(300):
                a = tired_athlete()
                a.injured_weeks = 6
                apply_weekly_training(
                    a, hired_roles={StaffRole.PHYSIO},
                    rng=random.Random(seed), staff_attrs=attrs_for(StaffRole.PHYSIO, value),
                )
                total += a.injured_weeks
            return total

        self.assertLess(weeks_left(19), weeks_left(3))

    def test_physio_recovery_sets_fatigue_relief(self) -> None:
        def fatigue_after(value: int) -> int:
            a = tired_athlete(fatigue=50)
            a.training_focus = TrainingFocus.REST
            apply_weekly_training(
                a, hired_roles={StaffRole.PHYSIO}, rng=random.Random(5),
                staff_attrs=attrs_for(StaffRole.PHYSIO, value),
            )
            return a.fatigue

        self.assertLess(fatigue_after(20), fatigue_after(2))

    def test_mental_coach_motivation_and_pressure(self) -> None:
        self.assertGreater(mental_form_bonus(19), mental_form_bonus(3))
        self.assertLess(impulsive_sigma(True, 19), impulsive_sigma(False))
        a = tired_athlete(fatigue=30)
        hi = _recalculate_form(a, False, False, True, False, mental_bonus=mental_form_bonus(20))
        lo = _recalculate_form(a, False, False, True, False, mental_bonus=mental_form_bonus(2))
        self.assertGreaterEqual(hi, lo)


class TestStaffMarket(unittest.TestCase):
    """Mercato dello staff (E.1, Q33): 3 candidati per ruolo, profili e costi diversi, dati fissi."""

    def test_three_candidates_per_clinical_role_with_unique_ids_and_names(self) -> None:
        staff = create_initial_staff()
        self.assertEqual(len(staff), 9)
        self.assertEqual(len({m.id for m in staff}), 9)
        self.assertEqual(len({m.name for m in staff}), 9)
        for role in STAFF_ATTRIBUTES:
            self.assertEqual(sum(1 for m in staff if m.role == role), 3, role)
        self.assertFalse(any(m.hired for m in staff))

    def test_original_candidates_keep_their_ids_costs_and_reference_attributes(self) -> None:
        by_id = {m.id: m for m in create_initial_staff()}
        for sid, role, cost in ((4, StaffRole.PHYSIO, 300), (5, StaffRole.DOCTOR, 340), (6, StaffRole.MENTAL_COACH, 220)):
            self.assertEqual((by_id[sid].role, by_id[sid].weekly_cost), (role, cost))
            self.assertEqual(by_id[sid].attributes, {key: REF for key, _label in STAFF_ATTRIBUTES[role]})

    def test_candidates_differ_and_better_attributes_cost_more(self) -> None:
        staff = create_initial_staff()
        for role in STAFF_ATTRIBUTES:
            group = sorted((m for m in staff if m.role == role), key=lambda m: m.weekly_cost)
            totals = [sum(normalize_attributes(role, m.attributes).values()) for m in group]
            self.assertEqual(totals, sorted(totals), role)  # chi costa di più è almeno altrettanto bravo
            self.assertLess(totals[0], totals[-1], role)
            for m in group:
                for value in m.attributes.values():
                    self.assertTrue(STAFF_ATTR_MIN <= value <= STAFF_ATTR_MAX)

    def test_market_is_deterministic_and_instances_are_independent(self) -> None:
        self.assertEqual(create_initial_staff(), create_initial_staff())
        self.assertEqual(len(STAFF_CATALOGUE), 9)
        a, b = create_initial_staff(), create_initial_staff()
        a[0].hired = True
        self.assertFalse(b[0].hired)

    def test_ensure_market_adds_missing_candidates_and_keeps_hirings(self) -> None:
        old = [m for m in create_initial_staff() if m.id in (4, 5, 6)]  # salvataggio precedente al mercato
        old[1].hired = True
        old[1].weekly_cost = 999  # il dato salvato non si riscrive
        self.assertEqual(ensure_staff_market(old), 6)
        self.assertEqual([m.id for m in old], sorted(m.id for m in old))
        self.assertEqual(len(old), 9)
        conti = next(m for m in old if m.id == 5)
        self.assertTrue(conti.hired)
        self.assertEqual(conti.weekly_cost, 999)
        self.assertEqual(ensure_staff_market(old), 0)  # idempotente

    def test_the_senior_candidates_beat_the_junior_ones_where_it_counts(self) -> None:
        by_id = {m.id: m for m in create_initial_staff()}
        self.assertLess(
            physio_heal_step_chance(by_id[7].attributes["competenza"]),
            physio_heal_step_chance(by_id[8].attributes["competenza"]),
        )
        self.assertGreater(
            doctor_risk_multiplier(by_id[9].attributes["prevenzione"]),
            doctor_risk_multiplier(by_id[10].attributes["prevenzione"]),
        )
        self.assertGreater(impulsive_sigma(True, by_id[11].attributes["pressione"]),
                           impulsive_sigma(True, by_id[12].attributes["pressione"]))


class TestAttributeData(unittest.TestCase):

    def test_normalize_fills_missing_and_clamps(self) -> None:
        self.assertEqual(normalize_attributes(StaffRole.PHYSIO), {"competenza": REF, "recupero": REF})
        out = normalize_attributes(StaffRole.DOCTOR, {"diagnosi": 99, "prevenzione": -5, "estranea": 7})
        self.assertEqual(out, {"diagnosi": STAFF_ATTR_MAX, "prevenzione": STAFF_ATTR_MIN})
        self.assertEqual(normalize_attributes(StaffRole.MENTAL_COACH, {"pressione": "x"})["pressione"], REF)
        self.assertEqual(normalize_attributes(StaffRole.COACH_SPRINTS), {})  # i coach non hanno attributi clinici

    def test_hired_attributes_only_include_hired_clinical_staff(self) -> None:
        state = GameState(staff=create_initial_staff())
        self.assertEqual(hired_staff_attributes(state), {})
        state.staff[0].hired = True
        state.staff[0].attributes = {"competenza": 18, "recupero": 9}
        self.assertEqual(hired_staff_attributes(state), {StaffRole.PHYSIO: {"competenza": 18, "recupero": 9}})

    def test_better_duplicate_role_wins(self) -> None:
        state = GameState(
            staff=[
                StaffMember(1, "A", StaffRole.DOCTOR, 3, 100, True, attributes={"diagnosi": 8, "prevenzione": 8}),
                StaffMember(2, "B", StaffRole.DOCTOR, 3, 100, True, attributes={"diagnosi": 16, "prevenzione": 15}),
            ]
        )
        self.assertEqual(hired_staff_attributes(state)[StaffRole.DOCTOR]["prevenzione"], 15)

    def test_describe_attributes_uses_the_italian_labels(self) -> None:
        member = StaffMember(1, "X", StaffRole.PHYSIO, 4, 300, attributes={"competenza": 17, "recupero": 11})
        self.assertEqual(describe_attributes(member), "Competenza infortuni 17 · Velocità recupero 11")

    def test_models_import_without_qt(self) -> None:
        # Convenzione 6: la logica sta in `models/`, che non importa PyQt6 (processo pulito: qui Qt può essere già caricato).
        root = Path(__file__).resolve().parent.parent
        code = "import sys, models.staff, models.simulation; sys.exit(1 if any(m.startswith('PyQt6') for m in sys.modules) else 0)"
        result = subprocess.run(
            [sys.executable, "-c", code], cwd=root, env={**os.environ, "PYTHONPATH": str(root)}, capture_output=True
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))


if __name__ == "__main__":
    unittest.main()
