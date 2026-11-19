"""Convocazioni: tetto di 2 gare individuali + 1 staffetta (FIDAL 3.3 e 5.7) e under 20 fuori da «Internazionale» (Q17).

Solo modello: questi test girano senza PyQt6 (`PYTHONPATH=. python3 -m unittest tests.test_assignments`).
"""

from __future__ import annotations

import random
import unittest
from typing import List

from models.entities import (
    EVENTS,
    INTERNATIONAL_MIN_AGE,
    MAX_INDIVIDUAL_EVENTS,
    Athlete,
    CompetitionTier,
    GameState,
)
from models.generator import build_default_lineup, create_rival_clubs, generate_initial_roster
from models.simulation import auto_build_all_relays, normalize_assignments, simulate_competition

ALL_EVENTS: List[str] = list(EVENTS)


def make_state(seed: int = 3, tier: CompetitionTier = CompetitionTier.PROVINCIALE) -> GameState:
    roster = generate_initial_roster(rng=random.Random(seed))
    for i, a in enumerate(roster, start=1):
        a.id = i
        a.in_youth_squad = False
    state = GameState(athletes=roster, game_mode="career", tier=tier, week=4)
    state.event_lineup = build_default_lineup(roster, ALL_EVENTS, gender="M")
    state.event_lineup_f = build_default_lineup(roster, ALL_EVENTS, gender="F")
    state.rival_clubs = create_rival_clubs(rng=random.Random(seed))
    auto_build_all_relays(state)
    return state


def entries(state: GameState, gender: str) -> dict:
    count: dict = {}
    for event in state.active_events:
        aid = state.lineup_for(gender).get(event)
        if aid is not None:
            count[aid] = count.get(aid, 0) + 1
    return count


class TestAgeEligibility(unittest.TestCase):
    def test_under_20_cannot_race_in_international(self) -> None:
        a: Athlete = generate_initial_roster(rng=random.Random(1))[0]
        a.age = INTERNATIONAL_MIN_AGE - 1
        self.assertFalse(a.can_race_in(CompetitionTier.INTERNAZIONALE))
        for tier in (CompetitionTier.PROVINCIALE, CompetitionTier.REGIONALE, CompetitionTier.NAZIONALE):
            self.assertTrue(a.can_race_in(tier), tier)
        a.age = INTERNATIONAL_MIN_AGE
        self.assertTrue(a.can_race_in(CompetitionTier.INTERNAZIONALE))


class TestEventCap(unittest.TestCase):
    def test_default_lineup_never_exceeds_the_cap(self) -> None:
        for seed in range(12):
            state = make_state(seed)
            for gender in ("M", "F"):
                self.assertLessEqual(max(entries(state, gender).values()), MAX_INDIVIDUAL_EVENTS, (seed, gender))
        # un solo atleta per divisione: due gare, le altre restano scoperte (non si viola il tetto)
        roster = [a for a in generate_initial_roster(rng=random.Random(1)) if a.gender == "M"][:1]
        roster[0].id, roster[0].in_youth_squad = 1, False
        lineup = build_default_lineup(roster, ALL_EVENTS, gender="M")
        self.assertEqual(sum(1 for v in lineup.values() if v == 1), MAX_INDIVIDUAL_EVENTS)
        self.assertEqual(sum(1 for v in lineup.values() if v is None), len(ALL_EVENTS) - MAX_INDIVIDUAL_EVENTS)

    def test_default_lineup_keeps_fixed_entries_and_counts_them(self) -> None:
        state = make_state(5)
        men = [a for a in state.athletes if a.gender == "M"]
        star = men[0]
        fixed = {ALL_EVENTS[0]: star.id, ALL_EVENTS[1]: star.id}
        lineup = build_default_lineup(state.athletes, ALL_EVENTS, gender="M", fixed=fixed)
        self.assertEqual(lineup[ALL_EVENTS[0]], star.id)
        self.assertEqual(lineup[ALL_EVENTS[1]], star.id)
        self.assertEqual(sum(1 for v in lineup.values() if v == star.id), 2)  # nessuna terza gara per lui

    def test_lineup_problem_refuses_the_third_individual_event(self) -> None:
        state = make_state(7)
        star = next(a for a in state.athletes if a.gender == "M")
        lineup = state.lineup_for("M")
        for event in ALL_EVENTS:
            lineup[event] = None
        lineup[ALL_EVENTS[0]] = star.id
        lineup[ALL_EVENTS[1]] = star.id
        self.assertIsNone(state.lineup_problem(star, ALL_EVENTS[0], "M"))  # confermare una gara già sua
        self.assertIsNone(state.lineup_problem(star, ALL_EVENTS[1], "M"))
        problem = state.lineup_problem(star, ALL_EVENTS[2], "M")
        self.assertIsNotNone(problem)
        self.assertIn("2", problem)
        # la divisione sbagliata e il vivaio sono rifiutati con un motivo
        woman = next(a for a in state.athletes if a.gender == "F")
        self.assertIsNotNone(state.lineup_problem(woman, ALL_EVENTS[2], "M"))
        star.in_youth_squad = True
        self.assertIsNotNone(state.lineup_problem(star, ALL_EVENTS[2], "M"))

    def test_only_active_events_count_for_the_cap(self) -> None:
        """Le gare che non si disputano in questa fase (es. Cross) non contano per il tetto."""
        state = make_state(7)
        star = next(a for a in state.athletes if a.gender == "M")
        lineup = state.lineup_for("M")
        for event in ALL_EVENTS:
            lineup[event] = None
        inactive = [e for e in ALL_EVENTS if e not in state.active_events]
        active = state.active_events
        for e in inactive[:3]:
            lineup[e] = star.id
        self.assertIsNone(state.lineup_problem(star, active[0], "M"))


class TestNormalizeAssignments(unittest.TestCase):
    def test_old_save_with_three_events_is_brought_within_the_cap(self) -> None:
        state = make_state(9)
        star = next(a for a in state.athletes if a.gender == "M")
        lineup = state.lineup_for("M")
        for event in ALL_EVENTS[:3]:
            lineup[event] = star.id
        notes = normalize_assignments(state)
        self.assertEqual(entries(state, "M")[star.id], MAX_INDIVIDUAL_EVENTS)
        self.assertEqual(len(notes), 1)
        self.assertLessEqual(max(entries(state, "M").values()), MAX_INDIVIDUAL_EVENTS)
        self.assertEqual(normalize_assignments(state), [])  # idempotente

    def test_under_20_replaced_after_promotion_to_international(self) -> None:
        state = make_state(11)
        young = next(a for a in state.athletes if a.gender == "M")
        young.age = 19
        state.event_lineup[ALL_EVENTS[0]] = young.id
        relay_name = state.active_relays[0]
        state.relays["4x100m" if "4x100m" in state.relays else relay_name].member_ids[0] = young.id
        state.tier = CompetitionTier.INTERNAZIONALE
        notes = normalize_assignments(state)
        self.assertNotEqual(state.event_lineup[ALL_EVENTS[0]], young.id)
        for event in state.active_events:
            aid = state.event_lineup.get(event)
            if aid is not None:
                athlete = next(a for a in state.athletes if a.id == aid)
                self.assertTrue(athlete.can_race_in(state.tier), (event, athlete.name, athlete.age))
        for relay in list(state.relays.values()) + list(state.relays_f.values()):
            for aid in relay.all_ids():
                athlete = next(a for a in state.athletes if a.id == aid)
                self.assertTrue(athlete.can_race_in(state.tier), athlete.name)
        self.assertTrue(notes)

    def test_no_rng_is_used(self) -> None:
        """L'ordine delle chiamate all'RNG del tick non cambia: la funzione non ne riceve né ne crea."""
        import inspect

        self.assertEqual(list(inspect.signature(normalize_assignments).parameters), ["state"])


class TestCompetitionSafetyNet(unittest.TestCase):
    def _club_results(self, age: int) -> list:
        state = make_state(13, CompetitionTier.INTERNAZIONALE)
        runner = next(a for a in state.athletes if a.gender == "M")
        runner.age = age
        for event in ALL_EVENTS:
            state.event_lineup[event] = None
        event = state.active_events[0]
        state.event_lineup[event] = runner.id
        summary = simulate_competition(state, rng=random.Random(1))
        return [r for r in summary.event_results if r.event_name == event and r.gender == "M"]

    def test_under_20_in_lineup_does_not_race_in_international(self) -> None:
        self.assertEqual(len(self._club_results(INTERNATIONAL_MIN_AGE)), 1)  # controllo: a 20 anni gareggia
        self.assertEqual(self._club_results(INTERNATIONAL_MIN_AGE - 1), [])  # a 19 resta fuori anche se convocato


if __name__ == "__main__":
    unittest.main()
