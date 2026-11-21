"""Storico di forma, fatica e risultati per atleta (PIANOLAVORO G.1/G.2). Senza Qt.

Garanzie: (1) a fine di ogni tick ogni atleta ha una riga (forma, fatica, infortunato), al più le ultime HISTORY_WEEKS; (2) ogni
gara individuale lascia una voce, al più le ultime HISTORY_RESULTS; (3) **lo storico non cambia il gioco**: stesso seme, stessi
esiti con e senza storico; (4) serializzazione robusta a JSON rotto e voci non valide; (5) il percentile è confrontabile.
"""

from __future__ import annotations

import random
import unittest

from models.entities import HISTORY_RESULTS, HISTORY_WEEKS, EventResult
from models.history import (
    history_from_json,
    history_to_json,
    record_result,
    record_weekly,
    result_percentile,
    results_series,
    weekly_series,
)
from models.simulation import advance_week
from tests.test_assignments import make_state


def play(weeks: int, seed: int = 7):
    state = make_state(3)
    rng = random.Random(seed)
    for _ in range(weeks):
        advance_week(state, rng)
    return state, rng


class TestWeekly(unittest.TestCase):
    def test_every_tick_adds_one_row_per_athlete(self) -> None:
        state, _ = play(3)
        for a in state.athletes:
            series = weekly_series(a)
            self.assertEqual(len(series), 3)
            self.assertEqual(series[-1], (a.form, a.fatigue, a.injured_weeks > 0))

    def test_only_the_last_weeks_are_kept(self) -> None:
        state, _ = play(HISTORY_WEEKS + 5)
        for a in state.athletes:
            self.assertEqual(len(weekly_series(a)), HISTORY_WEEKS)

    def test_history_does_not_change_the_game(self) -> None:
        """Stesso seme: forma, fatica, bilancio e stato dell'RNG identici con lo storico acceso e con lo storico azzerato a ogni tick."""
        a_state, a_rng = play(10)
        b_state = make_state(3)
        b_rng = random.Random(7)
        for _ in range(10):
            advance_week(b_state, b_rng)
            for ath in b_state.athletes:
                ath.history = {}
        self.assertEqual([(x.form, x.fatigue, x.injured_weeks) for x in a_state.athletes], [(x.form, x.fatigue, x.injured_weeks) for x in b_state.athletes])
        self.assertEqual(a_state.budget, b_state.budget)
        self.assertEqual(a_rng.getstate(), b_rng.getstate())


class TestResults(unittest.TestCase):
    def test_a_meet_records_individual_results(self) -> None:
        state, _ = play(8)  # almeno una settimana di gara (sett. % 4 == 0)
        recorded = [r for a in state.athletes for r in results_series(a)]
        meets = [c for c in state.competition_history]
        self.assertTrue(meets and recorded)
        individual = sum(1 for c in meets for e in c.event_results if "x" not in e.event_name.lower())
        self.assertEqual(len(recorded), individual)  # una voce per ogni gara individuale, niente per le staffette
        for r in recorded:
            self.assertTrue(1 <= r["place"] <= r["of"])

    def test_only_the_last_results_are_kept(self) -> None:
        state = make_state(1)
        a = state.athletes[0]
        for i in range(HISTORY_RESULTS + 4):
            record_result(state, a, EventResult("100m", a.name, 1 + i % 8, 8, "11.00", 0, 0, gender="M"))
        self.assertEqual(len(results_series(a)), HISTORY_RESULTS)
        self.assertEqual(results_series(a)[-1]["place"], 1 + (HISTORY_RESULTS + 3) % 8)

    def test_percentile(self) -> None:
        self.assertEqual(result_percentile({"place": 1, "of": 8}), 100.0)
        self.assertEqual(result_percentile({"place": 8, "of": 8}), 0.0)
        self.assertAlmostEqual(result_percentile({"place": 4, "of": 7}), 50.0)
        self.assertEqual(result_percentile({"place": 1, "of": 8, "out": True}), 0.0)  # ritirato
        self.assertEqual(result_percentile({"place": 1, "of": 1}), 100.0)  # gara in solitaria


class TestJson(unittest.TestCase):
    def test_roundtrip(self) -> None:
        h = {"weekly": [[60, 20, 0], [61, 30, 1]], "results": [{"place": 2, "of": 8, "event": "100m"}]}
        self.assertEqual(history_from_json(history_to_json(h)), h)

    def test_broken_json_is_empty_and_bad_entries_are_dropped(self) -> None:
        for raw in (None, "", "non json", "[]", "5", '{"weekly": 3, "results": "x"}'):
            self.assertEqual(history_from_json(raw), {})
        got = history_from_json('{"weekly": [[1, 2, 0], [1], "x", [3, "b", 0], [5, 6, 1]], "results": [{"place": 1}, {"place": 2, "of": 8}, 4]}')
        self.assertEqual(got, {"weekly": [[1, 2, 0], [5, 6, 1]], "results": [{"place": 2, "of": 8}]})

    def test_loading_trims_to_the_limits(self) -> None:
        raw = history_to_json({"weekly": [[i, i, 0] for i in range(50)], "results": [{"place": 1, "of": 8, "n": i} for i in range(50)]})
        got = history_from_json(raw)
        self.assertEqual(len(got["weekly"]), HISTORY_WEEKS)
        self.assertEqual(len(got["results"]), HISTORY_RESULTS)
        self.assertEqual(got["weekly"][-1], [49, 49, 0])


if __name__ == "__main__":
    unittest.main()
