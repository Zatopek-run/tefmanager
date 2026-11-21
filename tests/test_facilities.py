"""Impianti avanzati (PIANOLAVORO E.2): effetti di centro medico, analisi video, palestra pesi e campo altura. Senza Qt.

Garanzie: (1) senza impianti ogni cosa è identica a prima di E.2, RNG compreso; (2) ogni impianto agisce solo sulla sua
qualità e solo con l'impianto; (3) il centro medico non tocca la squalifica per doping.
"""

from __future__ import annotations

import random
import re
import unittest
from copy import deepcopy
from unittest import mock

from models.entities import (
    ATTITUDE_EFFECTS,
    FACILITY_ALTITUDE,
    FACILITY_COSTS,
    FACILITY_LABELS,
    FACILITY_MEDICAL,
    FACILITY_ORDER,
    FACILITY_UPKEEP,
    FACILITY_VIDEO,
    FACILITY_WEIGHTS,
    INJURY_MIN_WEEKS,
    MEDICAL_CENTER_INJURY_CUT,
    PeriodizationPhase,
    Personality,
    RaceAttitude,
    Specialty,
    TrainingFocus,
)
from models.facilities import (
    FACILITY_EFFECTS,
    facilities_from_json,
    facilities_to_json,
    growth_multiplier,
    injury_weeks_with_medical_center,
    owns,
    total_upkeep,
)
from models.generator import generate_initial_roster
from models.simulation import advance_week, apply_weekly_training, simulate_competition, weekly_finances
from tests.test_assignments import make_state

ALL = {key: 1 for key in FACILITY_ORDER}


def trainee(focus: TrainingFocus, specialty: Specialty = Specialty.SPRINTS, seed: int = 1):
    """Atleta con molto margine di crescita, nessun modificatore di personalità, allenato con `focus`."""
    athlete = generate_initial_roster(rng=random.Random(seed))[0]
    athlete.specialty = specialty
    athlete.personality = Personality.LEADER
    athlete.training_focus = focus
    athlete.periodization = PeriodizationPhase.PREP_SPECIFICA
    athlete.age = 22
    athlete.speed = athlete.stamina = athlete.strength = athlete.technique = 40
    athlete.potential = 95
    athlete.fatigue = 10
    athlete.injured_weeks = 0
    athlete.doping_boost_weeks = 0
    return athlete


def gains_of(focus: TrainingFocus, stat: str, facilities, specialty: Specialty = Specialty.SPRINTS, seeds: int = 500) -> int:
    base = trainee(focus, specialty)
    total = 0
    for seed in range(seeds):
        a = deepcopy(base)
        apply_weekly_training(a, rng=random.Random(seed), facilities=facilities)
        total += getattr(a, stat) - 40
    return total


class TestConstants(unittest.TestCase):
    def test_every_facility_has_a_label_a_cost_and_an_effect(self) -> None:
        self.assertEqual(len(FACILITY_ORDER), 4)
        for key in FACILITY_ORDER:
            self.assertTrue(FACILITY_LABELS[key])
            self.assertGreater(FACILITY_COSTS[key], 0)
            self.assertTrue(FACILITY_EFFECTS[key])

    def test_costs_are_the_ones_of_the_plan(self) -> None:
        self.assertEqual(
            FACILITY_COSTS,
            {FACILITY_MEDICAL: 15000, FACILITY_VIDEO: 10000, FACILITY_WEIGHTS: 12000, FACILITY_ALTITUDE: 20000},
        )


class TestGrowthMultiplier(unittest.TestCase):
    def test_without_facilities_it_is_exactly_one(self) -> None:
        for facilities in (None, {}):
            for stat in ("speed", "stamina", "strength", "technique", "resilience"):
                for specialty in Specialty:
                    self.assertEqual(growth_multiplier(facilities, stat, specialty), 1.0)

    def test_each_facility_acts_on_its_own_quality_only(self) -> None:
        self.assertAlmostEqual(growth_multiplier({FACILITY_VIDEO: 1}, "technique", Specialty.JUMPS), 1.05)
        self.assertAlmostEqual(growth_multiplier({FACILITY_WEIGHTS: 1}, "strength", Specialty.THROWS), 1.10)
        self.assertAlmostEqual(growth_multiplier({FACILITY_ALTITUDE: 1}, "stamina", Specialty.MIDDLE_DISTANCE), 1.10)
        for key, stat in ((FACILITY_VIDEO, "technique"), (FACILITY_WEIGHTS, "strength"), (FACILITY_ALTITUDE, "stamina")):
            for other in ("speed", "technique", "strength", "stamina", "resilience"):
                if other != stat:
                    self.assertEqual(growth_multiplier({key: 1}, other, Specialty.MIDDLE_DISTANCE), 1.0, (key, other))

    def test_the_altitude_camp_is_for_middle_distance_only(self) -> None:
        for specialty in (Specialty.SPRINTS, Specialty.JUMPS, Specialty.THROWS):
            self.assertEqual(growth_multiplier({FACILITY_ALTITUDE: 1}, "stamina", specialty), 1.0)

    def test_the_medical_center_does_not_touch_growth(self) -> None:
        self.assertEqual(growth_multiplier({FACILITY_MEDICAL: 1}, "strength", Specialty.THROWS), 1.0)


class TestTrainingGrowth(unittest.TestCase):
    def test_weights_room_makes_strength_grow_more(self) -> None:
        self.assertGreater(
            gains_of(TrainingFocus.EXPLOSIVE_POWER, "strength", {FACILITY_WEIGHTS: 1}),
            gains_of(TrainingFocus.EXPLOSIVE_POWER, "strength", {}),
        )

    def test_video_center_makes_technique_grow_more(self) -> None:
        self.assertGreater(
            gains_of(TrainingFocus.TECHNIQUE, "technique", {FACILITY_VIDEO: 1}),
            gains_of(TrainingFocus.TECHNIQUE, "technique", {}),
        )

    def test_altitude_camp_helps_middle_distance_stamina(self) -> None:
        self.assertGreater(
            gains_of(TrainingFocus.ENDURANCE, "stamina", {FACILITY_ALTITUDE: 1}, Specialty.MIDDLE_DISTANCE),
            gains_of(TrainingFocus.ENDURANCE, "stamina", {}, Specialty.MIDDLE_DISTANCE),
        )

    def test_altitude_camp_changes_nothing_for_a_sprinter_not_even_the_rng(self) -> None:
        for seed in range(30):
            with_camp, without = trainee(TrainingFocus.ENDURANCE), trainee(TrainingFocus.ENDURANCE)
            r1, r2 = random.Random(seed), random.Random(seed)
            apply_weekly_training(with_camp, rng=r1, facilities={FACILITY_ALTITUDE: 1})
            apply_weekly_training(without, rng=r2, facilities={})
            self.assertEqual(with_camp, without)
            self.assertEqual(r1.getstate(), r2.getstate())

    def test_none_and_empty_facilities_are_identical(self) -> None:
        for seed in range(30):
            a, b = trainee(TrainingFocus.EXPLOSIVE_POWER), trainee(TrainingFocus.EXPLOSIVE_POWER)
            a.fatigue = b.fatigue = 90  # così entra anche il rischio di infortunio
            r1, r2 = random.Random(seed), random.Random(seed)
            out_a = apply_weekly_training(a, rng=r1, facilities=None)
            out_b = apply_weekly_training(b, rng=r2, facilities={})
            self.assertEqual(out_a, out_b)
            self.assertEqual(a, b)
            self.assertEqual(r1.getstate(), r2.getstate())


class TestMedicalCenterRule(unittest.TestCase):
    def test_without_the_center_nothing_changes_and_no_draw_is_made(self) -> None:
        for facilities in (None, {}, {FACILITY_VIDEO: 1, FACILITY_WEIGHTS: 1, FACILITY_ALTITUDE: 1}):
            for weeks in (1, 2, 3, 4):
                rng = random.Random(5)
                before = rng.getstate()
                self.assertEqual(injury_weeks_with_medical_center(weeks, facilities, rng), weeks)
                self.assertEqual(rng.getstate(), before)

    def test_with_the_center_exactly_one_draw_is_made(self) -> None:
        for weeks in (1, 2, 3, 4):
            rng, ref = random.Random(5), random.Random(5)
            injury_weeks_with_medical_center(weeks, {FACILITY_MEDICAL: 1}, rng)
            ref.random()
            self.assertEqual(rng.getstate(), ref.getstate())

    def test_never_below_the_minimum_and_never_above_the_original(self) -> None:
        for weeks in (1, 2, 3, 4, 6):
            for seed in range(200):
                out = injury_weeks_with_medical_center(weeks, {FACILITY_MEDICAL: 1}, random.Random(seed))
                self.assertGreaterEqual(out, INJURY_MIN_WEEKS)
                self.assertLessEqual(out, weeks)

    def test_a_one_week_injury_stays_one_week(self) -> None:
        for seed in range(200):
            self.assertEqual(injury_weeks_with_medical_center(1, {FACILITY_MEDICAL: 1}, random.Random(seed)), 1)

    def test_the_average_cut_is_close_to_the_plan_but_lower_because_of_the_one_week_floor(self) -> None:
        """Su infortuni di 1-3 settimane (equiprobabili) il taglio vero è ≈12,5%, non 15%: il minimo di 1 sett. mangia il resto."""
        rng = random.Random(0)
        n = 30000
        sampled = [rng.randint(1, 3) for _ in range(n)]
        cut = sum(injury_weeks_with_medical_center(w, {FACILITY_MEDICAL: 1}, rng) for w in sampled)
        saving = 1 - cut / sum(sampled)
        self.assertGreater(saving, 0.11)
        self.assertLess(saving, MEDICAL_CENTER_INJURY_CUT)

    def test_a_long_injury_is_cut_by_the_nominal_percentage(self) -> None:
        rng = random.Random(1)
        n = 20000
        mean = sum(injury_weeks_with_medical_center(10, {FACILITY_MEDICAL: 1}, rng) for _ in range(n)) / n
        self.assertAlmostEqual(mean, 10 * (1 - MEDICAL_CENTER_INJURY_CUT), delta=0.05)


def _tired(seed: int = 1):
    a = trainee(TrainingFocus.EXPLOSIVE_POWER, seed=seed)
    a.fatigue = 92
    a.resilience = 30
    return a


class TestMedicalCenterInTraining(unittest.TestCase):
    def mean_weeks(self, facilities) -> float:
        weeks = []
        for seed in range(1500):
            a = _tired()
            _g, injury, _r, _s = apply_weekly_training(a, rng=random.Random(seed), facilities=facilities)
            if injury:
                weeks.append(a.injured_weeks)
        self.assertGreater(len(weeks), 100)
        return sum(weeks) / len(weeks)

    def test_the_center_shortens_training_injuries(self) -> None:
        self.assertLess(self.mean_weeks({FACILITY_MEDICAL: 1}), self.mean_weeks({}))

    def test_the_news_quotes_the_shortened_stop(self) -> None:
        for seed in range(400):
            a = _tired()
            _g, injury, _r, _s = apply_weekly_training(a, rng=random.Random(seed), facilities={FACILITY_MEDICAL: 1})
            if injury:
                self.assertIn(f"stop di {a.injured_weeks} sett.", injury)

    def test_the_doping_ban_is_not_shortened(self) -> None:
        found = 0
        for seed in range(300):
            a = trainee(TrainingFocus.EXPLOSIVE_POWER)
            a.doping_boost_weeks = 5
            _g, _i, _r, scandal = apply_weekly_training(a, rng=random.Random(seed), facilities={FACILITY_MEDICAL: 1})
            if scandal:
                found += 1
                self.assertEqual(a.injured_weeks, 4)
        self.assertGreater(found, 20)  # il campione contiene davvero degli scandali

    def test_without_an_injury_the_center_draws_nothing(self) -> None:
        for seed in range(40):
            a, b = trainee(TrainingFocus.REST), trainee(TrainingFocus.REST)
            r1, r2 = random.Random(seed), random.Random(seed)
            apply_weekly_training(a, rng=r1, facilities={FACILITY_MEDICAL: 1})
            apply_weekly_training(b, rng=r2, facilities={})
            self.assertEqual(a, b)
            self.assertEqual(r1.getstate(), r2.getstate())


class TestMedicalCenterInRaces(unittest.TestCase):
    """Ogni partecipante si ritira (probabilità forzata a 5): con il centro lo stop medio cala."""

    def total_weeks(self, facilities) -> tuple:
        always = {k: dict(v, injury=5.0) for k, v in ATTITUDE_EFFECTS.items()}
        total, news_ok = 0, True
        with mock.patch.dict("models.simulation.ATTITUDE_EFFECTS", always):
            for seed in range(25):
                state = make_state(3)
                state.facilities = dict(facilities)
                for a in state.athletes:
                    a.injured_weeks = 0
                summary = simulate_competition(state, rng=random.Random(seed))
                total += sum(a.injured_weeks for a in state.athletes)
                for line in state.news_log:
                    m = re.search(r"si ritira .* stop di (\d+) sett\.", line)
                    news_ok = news_ok and (m is None or 1 <= int(m.group(1)) <= 4)
                self.assertTrue(summary.event_results)
        return total, news_ok

    def test_the_center_shortens_race_injuries(self) -> None:
        without, _ = self.total_weeks({})
        with_center, news_ok = self.total_weeks({FACILITY_MEDICAL: 1})
        self.assertGreater(without, 0)
        self.assertLess(with_center, without)
        self.assertTrue(news_ok)

    def test_the_other_facilities_leave_race_injuries_alone(self) -> None:
        self.assertEqual(
            self.total_weeks({})[0],
            self.total_weeks({FACILITY_VIDEO: 1, FACILITY_WEIGHTS: 1, FACILITY_ALTITUDE: 1})[0],
        )


class TestUpkeep(unittest.TestCase):
    """Q34a: ogni impianto avanzato posseduto costa una manutenzione settimanale."""

    def test_every_facility_has_a_positive_upkeep_below_its_price(self) -> None:
        self.assertEqual(sorted(FACILITY_UPKEEP), sorted(FACILITY_ORDER))
        for key in FACILITY_ORDER:
            self.assertGreater(FACILITY_UPKEEP[key], 0)
            self.assertLess(FACILITY_UPKEEP[key] * 52, FACILITY_COSTS[key])  # in un anno costa meno dell'acquisto

    def test_total_is_the_sum_of_the_owned_ones_and_zero_without_any(self) -> None:
        self.assertEqual(total_upkeep({}), 0)
        self.assertEqual(total_upkeep(None), 0)
        self.assertEqual(total_upkeep({FACILITY_MEDICAL: 1}), FACILITY_UPKEEP[FACILITY_MEDICAL])
        self.assertEqual(total_upkeep(ALL), sum(FACILITY_UPKEEP.values()))
        self.assertEqual(total_upkeep({FACILITY_VIDEO: 0}), 0)

    def test_weekly_finances_charges_it_and_nothing_without_facilities(self) -> None:
        state = make_state(3)
        before = weekly_finances(state)
        self.assertEqual(before["facilities_upkeep"], 0)
        state.facilities = dict(ALL)
        after = weekly_finances(state)
        self.assertEqual(after["facilities_upkeep"], sum(FACILITY_UPKEEP.values()))
        self.assertEqual(after["expenses"], before["expenses"] + sum(FACILITY_UPKEEP.values()))
        self.assertEqual(after["net"], before["net"] - sum(FACILITY_UPKEEP.values()))

    def test_the_week_writes_a_ledger_line_and_pays_it(self) -> None:
        state = make_state(3)
        state.week, state.transactions = 1, []
        state.facilities = {FACILITY_MEDICAL: 1, FACILITY_ALTITUDE: 1}
        expected = FACILITY_UPKEEP[FACILITY_MEDICAL] + FACILITY_UPKEEP[FACILITY_ALTITUDE]
        advance_week(state, rng=random.Random(4))
        lines = [t for t in state.transactions if t.description == "Manutenzione impianti avanzati"]
        self.assertEqual([(t.category, t.amount) for t in lines], [("Impianto", -expected)])

    def test_no_ledger_line_without_facilities(self) -> None:
        state = make_state(3)
        state.week, state.transactions = 1, []
        advance_week(state, rng=random.Random(4))
        self.assertFalse(any("Manutenzione impianti" in t.description for t in state.transactions))


class TestPersistenceHelpers(unittest.TestCase):
    def test_roundtrip_keeps_only_owned_known_facilities(self) -> None:
        raw = facilities_to_json({FACILITY_VIDEO: 1, FACILITY_MEDICAL: 1, "inventato": 1, FACILITY_WEIGHTS: 0})
        self.assertEqual(facilities_from_json(raw), {FACILITY_MEDICAL: 1, FACILITY_VIDEO: 1})

    def test_corrupt_or_unexpected_json_means_no_facilities(self) -> None:
        for raw in (None, "", "non json", "[1, 2]", "42", '{"centro_medico": "x"}', "null"):
            self.assertEqual(facilities_from_json(raw), {}, raw)

    def test_owns(self) -> None:
        self.assertFalse(owns(None, FACILITY_MEDICAL))
        self.assertFalse(owns({}, FACILITY_MEDICAL))
        self.assertTrue(owns({FACILITY_MEDICAL: 1}, FACILITY_MEDICAL))


if __name__ == "__main__":
    unittest.main()
