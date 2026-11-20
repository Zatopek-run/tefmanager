"""Lotto A.2: spareggio in classifica (non più alfabetico) e salvataggio dei piazzamenti (schema v12).

A pari punti: più 1° posti, poi più 2°, ...; se è ancora parità, un sorteggio deterministico che dipende da
stagione e posizione del club, **non dal nome**. Stessa regola per la classifica di lega e per quella del meeting.

Solo modello e database: gira senza PyQt6 (`PYTHONPATH=. python3 -m unittest tests.test_tiebreaker`).
"""

from __future__ import annotations

import random
import tempfile
import unittest
from pathlib import Path

from models.database import DatabaseManager
from models.entities import LEAGUE_PLACE_SLOTS, TEAM_POINTS, GameState
from models.simulation import _rival_only_points, _score_place, simulate_competition
from tests.test_assignments import make_state


def places(**by_place: int) -> list:
    """`places(p1=2, p3=1)` → [2, 0, 1, 0, 0, 0, 0, 0]."""
    counts = [0] * LEAGUE_PLACE_SLOTS
    for key, n in by_place.items():
        counts[int(key[1:]) - 1] = n
    return counts


def tied_state(table_points: int = 5) -> GameState:
    """Società del giocatore e due rivali a pari punti; il resto a zero."""
    state = make_state(3)
    state.team_name = "Atletica Zeta"
    state.league_table = {state.team_name: table_points}
    for club in state.rivals_in()[:2]:
        state.league_table[club.name] = table_points
    return state


class TestTiebreakOrder(unittest.TestCase):
    def test_more_wins_beats_more_points_in_lower_places(self) -> None:
        """Stessi punti (8 = 8): chi ha un 1° posto passa davanti a chi ha otto 8° posti."""
        state = tied_state(8)
        a, b = state.rivals_in()[:2]
        state.league_places = {a.name: places(p8=8), b.name: places(p1=1), state.team_name: places(p4=1, p5=0)}
        order = [t for t, _p in state.league_standings()]
        self.assertLess(order.index(b.name), order.index(a.name))

    def test_lexicographic_first_places_then_second(self) -> None:
        state = tied_state(14)
        a, b = state.rivals_in()[:2]
        state.league_places = {a.name: places(p1=1, p2=1), b.name: places(p1=1, p3=1)}
        order = [t for t, _p in state.league_standings()]
        self.assertLess(order.index(a.name), order.index(b.name))

    def test_points_still_come_first(self) -> None:
        state = tied_state(5)
        a, b = state.rivals_in()[:2]
        state.league_table[b.name] = 6
        state.league_places = {a.name: places(p1=9)}
        self.assertEqual(state.league_standings()[0], (b.name, 6))

    def test_draw_is_deterministic_and_does_not_depend_on_the_name(self) -> None:
        """Tabella tutta in pareggio: stesso ordine a ogni esecuzione, e cambiare i nomi non cambia le posizioni."""
        state = make_state(3)
        positions = [state.tiebreak_draw(n) for n in [state.team_name] + [c.name for c in state.rivals_in()]]
        again = make_state(3)
        self.assertEqual(positions, [again.tiebreak_draw(n) for n in [again.team_name] + [c.name for c in again.rivals_in()]])
        before = [t for t, _p in state.league_standings()]
        order_by_slot = [([state.team_name] + [c.name for c in state.rivals_in()]).index(t) for t in before]
        state.team_name = "AAA Primi in alfabeto"
        for i, club in enumerate(state.rivals_in(), start=1):
            club.name = f"Società {chr(ord('Z') - i)}"
        renamed = [t for t, _p in state.league_standings()]
        renamed_slots = [([state.team_name] + [c.name for c in state.rivals_in()]).index(t) for t in renamed]
        self.assertEqual(order_by_slot, renamed_slots)

    def test_draw_changes_with_the_season_and_is_not_alphabetical(self) -> None:
        state = make_state(3)
        orders = set()
        for season in range(1, 9):
            state.season_number = season
            orders.add(tuple(t for t, _p in state.league_standings()))
        self.assertGreater(len(orders), 1)  # il sorteggio varia da una stagione all'altra
        alphabetical = tuple(sorted(t for t, _p in state.league_standings()))
        self.assertTrue(any(o != alphabetical for o in orders))

    def test_draw_is_stable_during_the_season(self) -> None:
        state = tied_state(0)
        first = state.league_standings()
        state.week += 7
        self.assertEqual(state.league_standings(), first)

    def test_old_save_without_places_falls_back_to_the_draw(self) -> None:
        state = tied_state(5)
        state.league_places = {}
        self.assertEqual(len(state.league_standings()), 8)


class TestScoring(unittest.TestCase):
    def test_score_place_gives_points_and_counts_the_place(self) -> None:
        points: dict = {}
        counted: dict = {}
        _score_place(points, counted, "A", 1)
        _score_place(points, counted, "A", 1)
        _score_place(points, counted, "A", 3)
        _score_place(points, counted, "B", 9)  # fuori dalla zona punti: nessun punto, nessun contatore
        self.assertEqual(points, {"A": 2 * TEAM_POINTS[1] + TEAM_POINTS[3], "B": 0})
        self.assertEqual(counted, {"A": places(p1=2, p3=1)})

    def test_rival_only_event_counts_places(self) -> None:
        state = make_state(3)
        points: dict = {}
        counted: dict = {}
        _rival_only_points(state.rivals_in(), "100m", points, counted, random.Random(1))
        self.assertEqual(sum(sum(c) for c in counted.values()), len(state.rivals_in()))
        self.assertEqual(sum(points.values()), sum(TEAM_POINTS.get(i, 0) for i in range(1, len(state.rivals_in()) + 1)))

    def test_meeting_accumulates_places_matching_the_points(self) -> None:
        """Dopo un meeting i punti di lega sono la somma dei punti dei piazzamenti contati."""
        state = make_state(3)
        simulate_competition(state, rng=random.Random(1))
        self.assertTrue(state.league_places)
        for team, counts in state.league_places.items():
            self.assertEqual(len(counts), LEAGUE_PLACE_SLOTS)
            self.assertEqual(
                state.league_table.get(team, 0), sum(n * TEAM_POINTS[i] for i, n in enumerate(counts, start=1)), team
            )

    def test_meeting_table_is_reproducible_with_the_same_rng(self) -> None:
        tables = []
        for _ in range(2):
            state = make_state(3)
            summary = simulate_competition(state, rng=random.Random(5))
            tables.append(summary.team_standings)
        self.assertEqual(tables[0], tables[1])


class TestPersistence(unittest.TestCase):
    def test_places_survive_save_and_load(self) -> None:
        state = make_state(3)
        simulate_competition(state, rng=random.Random(1))
        with tempfile.TemporaryDirectory() as tmp:
            db = DatabaseManager(db_path=Path(tmp) / "p.db")
            db.save_game(state)
            loaded = db.load_game()
        self.assertEqual(loaded.league_places, state.league_places)
        self.assertEqual(loaded.league_standings(), state.league_standings())


if __name__ == "__main__":
    unittest.main()
