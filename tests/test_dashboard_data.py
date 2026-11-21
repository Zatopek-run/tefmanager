"""Dati della Dashboard (PIANOLAVORO G.1): andamento della rosa, heat map, timeline della stagione. Senza Qt.

Garanzie: (1) l'andamento è la media degli storici allineati dalla fine; (2) la heat map ha una riga per atleta e una colonna per gara
della fase e la colonna «migliore» è davvero il massimo della riga; (3) la timeline ha una casella per settimana della stagione con le
gare ogni 4 settimane fuori dalla Preparazione; (4) niente RNG e nessuna scrittura sullo stato.
"""

from __future__ import annotations

import random
import unittest

from models.dashboard import heat_level, heat_map, season_timeline, squad_trend
from models.entities import HEATMAP_ATHLETES, HEATMAP_SCORE_HIGH, HEATMAP_SCORE_LOW
from models.simulation import advance_week
from tests.test_assignments import make_state


class TestSquadTrend(unittest.TestCase):
    def test_empty_without_history(self) -> None:
        state = make_state(3)
        for a in state.athletes:
            a.history = {}
        self.assertEqual(squad_trend(state), [])

    def test_average_of_the_squad_aligned_from_the_end(self) -> None:
        state = make_state(3)
        squad = state.main_squad
        squad[0].history = {"weekly": [[40, 10, 0], [50, 20, 0], [60, 30, 0]]}
        squad[1].history = {"weekly": [[70, 50, 0]]}  # arrivato solo nell'ultima settimana
        for a in squad[2:]:
            a.history = {}
        trend = squad_trend(state)
        self.assertEqual(len(trend), 3)
        self.assertEqual(trend[0], (40.0, 10.0))  # solo il primo atleta aveva uno storico
        self.assertEqual(trend[1], (50.0, 20.0))
        self.assertEqual(trend[2], (65.0, 40.0))  # media dei due

    def test_a_played_game_has_one_point_per_tick(self) -> None:
        state = make_state(3)
        rng = random.Random(3)
        for _ in range(5):
            advance_week(state, rng)
        self.assertEqual(len(squad_trend(state)), 5)


class TestHeatMap(unittest.TestCase):
    def test_shape_and_best_column(self) -> None:
        state = make_state(3)
        hm = heat_map(state)
        self.assertIsNotNone(hm)
        self.assertLessEqual(len(hm.athletes), HEATMAP_ATHLETES)
        self.assertEqual(hm.events, [e for e in state.active_events if e in hm.events])
        self.assertEqual(len(hm.scores), len(hm.athletes))
        for row, best in zip(hm.scores, hm.best_columns):
            self.assertEqual(len(row), len(hm.events))
            self.assertEqual(row[best], max(row))
        overalls = [a.overall for a in hm.athletes]
        self.assertEqual(overalls, sorted(overalls, reverse=True))

    def test_none_without_athletes(self) -> None:
        state = make_state(3)
        state.athletes = []
        self.assertIsNone(heat_map(state))

    def test_heat_level_is_clamped_and_linear(self) -> None:
        self.assertEqual(heat_level(HEATMAP_SCORE_LOW - 10), 0.0)
        self.assertEqual(heat_level(HEATMAP_SCORE_HIGH + 10), 1.0)
        self.assertAlmostEqual(heat_level((HEATMAP_SCORE_LOW + HEATMAP_SCORE_HIGH) / 2), 0.5)


class TestTimeline(unittest.TestCase):
    def test_one_cell_per_week_with_races_every_four(self) -> None:
        state = make_state(3)
        tl = season_timeline(state)
        self.assertEqual(len(tl.weeks), state.season_length)
        self.assertEqual(sum(w.is_current for w in tl.weeks), 1)
        self.assertEqual(tl.weeks[tl.current - 1].number, tl.current)
        races = [w.number for w in tl.weeks if w.is_race]
        self.assertTrue(all(b - a == 4 for a, b in zip(races, races[1:])))
        self.assertTrue(all(w.is_past for w in tl.weeks[: tl.current - 1]))

    def test_preparation_has_no_races_and_next_race_matches_the_state(self) -> None:
        state = make_state(3)
        state.prep_weeks = 8
        state.week = 3
        tl = season_timeline(state)
        prep = [w for w in tl.weeks if w.is_prep]
        self.assertEqual(len(prep), 8)
        self.assertFalse(any(w.is_race for w in prep))
        self.assertEqual(tl.next_race_in, state.weeks_until_competition)

    def test_expiring_contracts_are_the_ones_ending_this_season(self) -> None:
        state = make_state(3)
        squad = state.main_squad
        for a in squad:
            a.contract_end_season = state.season_number + 2
        squad[0].contract_end_season = state.season_number
        self.assertEqual(season_timeline(state).expiring, [squad[0].name])

    def test_does_not_touch_the_state(self) -> None:
        state = make_state(3)
        before = (state.week, state.budget, [(a.form, a.fatigue) for a in state.athletes])
        squad_trend(state), heat_map(state), season_timeline(state)
        self.assertEqual(before, (state.week, state.budget, [(a.form, a.fatigue) for a in state.athletes]))


if __name__ == "__main__":
    unittest.main()
