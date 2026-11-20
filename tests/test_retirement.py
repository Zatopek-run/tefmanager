"""Lotto C.3: ritiro degli atleti a 33-35 anni (o per infortuni) e post-carriera da allenatore (schema v17).

Solo modello e database: gira senza PyQt6 (`PYTHONPATH=. python3 -m unittest tests.test_retirement`).
"""

from __future__ import annotations

import dataclasses
import random
import tempfile
import unittest
from pathlib import Path
from typing import List

from models.career import (
    REASON_AGE,
    REASON_INJURIES,
    age_retirement_chance,
    coach_skills_from_athlete,
    retirement_chance,
)
from models.database import DatabaseManager
from models.entities import (
    COACH_BASE_SKILL,
    COACH_STATS,
    MAX_RETIRED_LIST,
    RETIRED_COACH_CHANCE,
    RETIRED_COACH_SKILL_MAX,
    RETIRED_COACH_SKILL_MIN,
    RETIREMENT_CERTAIN_AGE,
    RETIREMENT_INJURIES_PER_SEASON,
    RETIREMENT_INJURY_CHANCE,
    RETIREMENT_INJURY_MIN_AGE,
    RETIREMENT_MIN_AGE,
    Athlete,
    RetiredAthlete,
    SeasonPhase,
    Specialty,
)
from models.generator import SPECIALTY_COACH_FOCUS, generate_initial_roster
from models.simulation import advance_week, apply_weekly_training, retire_veterans
from tests.test_assignments import make_state


class FakeRng:
    """RNG a sequenza fissa: `random()` restituisce i valori dati, in ordine, e li conta."""

    def __init__(self, *values: float) -> None:
        self.values = list(values)
        self.calls = 0

    def random(self) -> float:
        self.calls += 1
        return self.values.pop(0)


def veteran(state, age: int, injuries: int = 0) -> Athlete:
    """Il primo atleta della Prima Squadra, portato all'età e agli infortuni dati."""
    a = state.main_squad[0]
    a.age, a.season_injuries = age, injuries
    return a


def clones(state, n: int, age: int) -> None:
    """Sostituisce la squadra con `n` copie di un atleta (id nuovi) tutte della stessa età."""
    base = state.main_squad[0]
    state.athletes = [
        dataclasses.replace(base, id=i, age=age, in_youth_squad=False, season_injuries=0, coach_id=None)
        for i in range(1, n + 1)
    ]
    state.event_lineup, state.event_lineup_f, state.relays, state.relays_f = {}, {}, {}, {}


class TestChance(unittest.TestCase):
    def test_table_is_zero_below_33_growing_then_certain_at_35(self) -> None:
        self.assertEqual((RETIREMENT_MIN_AGE, RETIREMENT_CERTAIN_AGE), (33, 35))
        for age in (18, 25, 32):
            self.assertEqual(age_retirement_chance(age), 0.0, age)
        self.assertEqual(age_retirement_chance(33), 0.25)
        self.assertEqual(age_retirement_chance(34), 0.50)
        for age in (35, 36, 45):
            self.assertEqual(age_retirement_chance(age), 1.0, age)
        self.assertLess(age_retirement_chance(33), age_retirement_chance(34))

    def test_injuries_need_age_and_a_tormented_season(self) -> None:
        state = make_state(3)
        a = veteran(state, RETIREMENT_INJURY_MIN_AGE - 1, injuries=9)
        self.assertEqual(retirement_chance(a)[0], 0.0)  # troppo giovane, anche con molti infortuni
        a.age = RETIREMENT_INJURY_MIN_AGE
        a.season_injuries = RETIREMENT_INJURIES_PER_SEASON - 1
        self.assertEqual(retirement_chance(a)[0], 0.0)
        a.season_injuries = RETIREMENT_INJURIES_PER_SEASON
        self.assertEqual(retirement_chance(a), (RETIREMENT_INJURY_CHANCE, REASON_INJURIES))

    def test_injuries_never_lower_the_chance_given_by_age(self) -> None:
        state = make_state(3)
        a = veteran(state, 33, injuries=RETIREMENT_INJURIES_PER_SEASON)
        self.assertEqual(retirement_chance(a), (RETIREMENT_INJURY_CHANCE, REASON_INJURIES))  # 0,35 > 0,25
        a.age = 34
        self.assertEqual(retirement_chance(a), (0.5, REASON_AGE))  # l'età pesa di più
        a.age = 36
        self.assertEqual(retirement_chance(a), (1.0, REASON_AGE))


class TestRetireVeterans(unittest.TestCase):
    def test_nobody_eligible_consumes_no_random_numbers(self) -> None:
        state = make_state(3)
        for a in state.athletes:
            a.age, a.season_injuries = 25, 5
        rng = random.Random(7)
        before = rng.getstate()
        self.assertEqual(retire_veterans(state, rng), [])
        self.assertEqual(rng.getstate(), before)
        self.assertEqual(state.retired, [])
        self.assertTrue(all(a.season_injuries == 0 for a in state.athletes))  # il conto riparte

    def test_one_draw_to_retire_and_another_only_for_who_retires(self) -> None:
        state = make_state(3)
        for a in state.athletes:
            a.age = 25
        a = veteran(state, 33)
        n = len(state.athletes)
        stays = FakeRng(0.25)  # 0,25 non è < 0,25: resta, e non estrae altro
        self.assertEqual(retire_veterans(state, stays), [])
        self.assertEqual((stays.calls, len(state.athletes)), (1, n))
        goes = FakeRng(0.24, 0.5)  # si ritira, ma 0,5 >= 0,10: nessuna offerta
        notes = retire_veterans(state, goes)
        self.assertEqual((goes.calls, len(state.athletes)), (2, n - 1))
        self.assertFalse(state.retired[0].coach_offer)
        self.assertIn(a.name, notes[0])
        self.assertNotIn("allenatore", notes[0])

    def test_the_second_number_decides_the_coach_offer(self) -> None:
        state = make_state(3)
        for a in state.athletes:
            a.age = 25
        a = veteran(state, 36)
        notes = retire_veterans(state, FakeRng(0.99, RETIRED_COACH_CHANCE - 0.001))
        ex = state.retired[0]
        self.assertTrue(ex.coach_offer and not ex.became_coach)
        self.assertEqual(ex.coach_skills, coach_skills_from_athlete(a))
        self.assertIn("allenatore", notes[0])

    def test_the_memory_keeps_who_they_were(self) -> None:
        state = make_state(3)
        for x in state.athletes:
            x.age = 25
        a = veteran(state, 35, injuries=1)
        a.personal_best_display = "10.42"
        state.season_number = 4  # già incrementato: la stagione chiusa è la 3
        retire_veterans(state, FakeRng(0.0, 0.5))
        ex = state.retired[0]
        self.assertEqual(
            (ex.name, ex.gender, ex.specialty, ex.age, ex.season, ex.reason, ex.personal_best_display),
            (a.name, a.gender, a.specialty, 35, 3, REASON_AGE, "10.42"),
        )
        self.assertNotIn(a, state.athletes)

    def test_probability_of_retiring_at_33_over_many_athletes(self) -> None:
        state = make_state(3)
        clones(state, 1200, 33)
        retire_veterans(state, random.Random(11))
        gone = 1200 - len(state.athletes)  # non `len(state.retired)`: la lista ricorda al massimo MAX_RETIRED_LIST
        self.assertGreater(gone, MAX_RETIRED_LIST)  # il test deve poter vedere oltre il tetto della lista
        self.assertTrue(0.21 <= gone / 1200 <= 0.29, gone / 1200)  # attesi 25%

    def test_everyone_retires_at_35_and_a_tenth_offers_to_coach(self) -> None:
        state = make_state(3)
        clones(state, 601, 35)
        retire_veterans(state, random.Random(5))
        self.assertEqual(len(state.retired), MAX_RETIRED_LIST)  # ricordati solo i più recenti
        self.assertEqual(len(state.main_squad), 1)  # l'ultimo resta
        state = make_state(3)
        clones(state, 301, 35)
        notes = retire_veterans(state, random.Random(5))
        self.assertEqual(len(notes), 300)  # tutti tranne l'ultimo, anche oltre i 100 ricordati
        offers = sum(1 for n in notes if "Si offre come allenatore" in n)
        self.assertTrue(15 <= offers <= 45, offers)  # attese ~30 su 300 (10%), sigma ~5

    def test_the_last_main_squad_athlete_cannot_retire(self) -> None:
        state = make_state(3)
        state.athletes = [veteran(state, 40)]
        rng = FakeRng(0.0)
        self.assertEqual(retire_veterans(state, rng), [])
        self.assertEqual(len(state.athletes), 1)
        self.assertEqual(rng.calls, 1)  # la prima estrazione c'è, il secondo numero no
        state = make_state(3)
        clones(state, 2, 40)
        retire_veterans(state, FakeRng(0.0, 0.9, 0.0))
        self.assertEqual([a.id for a in state.athletes], [2])  # parte il primo, resta il secondo

    def test_youth_academy_kids_never_retire(self) -> None:
        state = make_state(3)
        for a in state.athletes:
            a.age = 25
        kid = state.athletes[-1]
        kid.in_youth_squad, kid.age = True, 40
        retire_veterans(state, FakeRng())  # se estraesse, FakeRng solleverebbe IndexError
        self.assertIn(kid, state.athletes)

    def test_lineup_and_relays_are_rebuilt_without_the_retired(self) -> None:
        state = make_state(3)
        for a in state.athletes:
            a.age = 25
        in_lineup = {aid for aid in state.event_lineup.values() if aid is not None}
        a = next(x for x in state.main_squad if x.id in in_lineup)
        a.age = 36
        retire_veterans(state, FakeRng(0.0, 0.9))
        remaining = {x.id for x in state.athletes}
        self.assertNotIn(a.id, remaining)
        for gender in ("M", "F"):
            for aid in state.lineup_for(gender).values():
                self.assertTrue(aid is None or aid in remaining, (gender, aid))
            for relay in state.relays_for(gender).values():
                self.assertTrue(set(relay.all_ids()) <= remaining | {None})
                self.assertIn(relay.reserve_id, remaining | {None})

    def test_coach_offers_expire_at_the_next_season_change(self) -> None:
        state = make_state(3)
        old = RetiredAthlete("Ex Offerta", "M", Specialty.SPRINTS, 36, 1, REASON_AGE, coach_offer=True,
                             coach_skills={s: 60 for s in COACH_STATS})
        hired = RetiredAthlete("Ex Assunto", "M", Specialty.JUMPS, 36, 1, REASON_AGE, became_coach=True)
        state.retired = [old, hired]
        for a in state.athletes:
            a.age = 25
        retire_veterans(state, FakeRng())
        self.assertFalse(old.coach_offer)
        self.assertEqual(old.status_label, "In pensione")
        self.assertTrue(hired.became_coach)
        self.assertEqual(hired.status_label, "Allenatore della società")


class TestCoachSkills(unittest.TestCase):
    def athlete(self, spec: Specialty, **stats: int) -> Athlete:
        a = next(x for x in generate_initial_roster(rng=random.Random(1)) if x.specialty == spec)
        for k, v in stats.items():
            setattr(a, k, v)
        return a

    def test_primary_and_secondary_come_from_the_athlete_and_are_clamped(self) -> None:
        for spec in Specialty:
            primary, secondary = SPECIALTY_COACH_FOCUS[spec]
            skills = coach_skills_from_athlete(self.athlete(spec, **{primary: 95, secondary: 72}))
            self.assertEqual(skills[primary], RETIRED_COACH_SKILL_MAX, spec)
            self.assertEqual(skills[secondary], 72 - 10, spec)
            others = [s for s in COACH_STATS if s not in (primary, secondary)]
            self.assertTrue(all(skills[s] == COACH_BASE_SKILL for s in others), spec)
            weak = coach_skills_from_athlete(self.athlete(spec, **{primary: 30, secondary: 30}))
            self.assertEqual(weak[primary], RETIRED_COACH_SKILL_MIN, spec)
            self.assertGreaterEqual(weak[secondary], COACH_BASE_SKILL, spec)


class TestSeasonInjuries(unittest.TestCase):
    def test_a_training_injury_is_counted(self) -> None:
        a = next(iter(generate_initial_roster(rng=random.Random(2))))
        rng = random.Random(9)
        counted = notes = 0
        for _ in range(300):
            a.injured_weeks, a.fatigue, a.doping_boost_weeks = 0, 95, 0
            before = a.season_injuries
            _g, injury_note, _r, _s = apply_weekly_training(a, hired_roles=set(), rng=rng)
            if injury_note:
                notes += 1
                counted += a.season_injuries - before
        self.assertGreater(notes, 0)
        self.assertEqual(counted, notes)  # un infortunio = +1, mai di più né di meno


class TestSeasonChangeTick(unittest.TestCase):
    """Il passo di ritiro dentro `advance_week`, al cambio stagione (TICK.md 16b')."""

    def season_end_state(self):
        state = make_state(3)
        state.week, state.season_phase = 36, SeasonPhase.INDOOR
        for a in state.athletes:
            a.age = 24
        return state

    def test_a_36_year_old_retires_at_the_season_change_and_is_not_renewed(self) -> None:
        state = self.season_end_state()
        a = veteran(state, 35)  # +1 al cambio = 36: ritiro certo
        a.contract_end_season = 1  # il contratto scade proprio ora
        report = advance_week(state, rng=random.Random(4))
        self.assertIsNotNone(report.season_end)
        self.assertEqual(state.season_number, 2)
        self.assertNotIn(a.id, [x.id for x in state.athletes])
        self.assertEqual(state.retired[0].name, a.name)
        self.assertEqual(state.retired[0].season, 1)
        news = "\n".join(state.news_log)
        self.assertIn(f"{a.name} (36 anni", news)
        renewed = [line for line in state.news_log if "contratti rinnovati" in line]
        self.assertFalse(any(a.name in line for line in renewed))
        self.assertTrue(all(x.season_injuries == 0 for x in state.athletes))

    def test_nobody_retires_in_the_middle_of_the_season(self) -> None:
        state = make_state(3)
        state.week = 8
        for a in state.athletes:
            a.age = 40
        advance_week(state, rng=random.Random(4))
        self.assertEqual(state.retired, [])

    def test_same_seed_same_retirements(self) -> None:
        def run() -> List[str]:
            s = self.season_end_state()
            for a in s.main_squad[:6]:
                a.age = 33
            advance_week(s, rng=random.Random(21))
            return [r.name for r in s.retired]

        self.assertEqual(run(), run())


class TestPersistence(unittest.TestCase):
    def test_retired_list_and_season_injuries_survive_a_save(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "s.db"
            state = make_state(3)
            state.athletes[0].season_injuries = 2
            state.retired = [
                RetiredAthlete("Anna Bianchi", "F", Specialty.JUMPS, 35, 2, REASON_AGE, "Francia", 71, "6.12",
                               {s: 40 + i for i, s in enumerate(COACH_STATS)}, True, False),
                RetiredAthlete("Luca Rossi", "M", Specialty.SPRINTS, 31, 1, REASON_INJURIES, became_coach=True),
            ]
            DatabaseManager(db_path=path).save_game(state)
            loaded = DatabaseManager(db_path=path).load_game()
            self.assertEqual(loaded.retired, state.retired)
            self.assertEqual(loaded.athletes[0].season_injuries, 2)


if __name__ == "__main__":
    unittest.main()
