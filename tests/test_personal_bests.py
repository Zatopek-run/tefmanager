"""Primati personali per gara e progressione nel tempo (richiesta dell'utente, 2026-11-21, Q43). Senza Qt.

Prima c'era **un solo** PB per atleta (`Athlete.personal_best`), confrontato con la misura di qualunque gara: un atleta iscritto a
100m e Salto in Lungo (si può, `MAX_INDIVIDUAL_EVENTS` = 2) non faceva mai un PB nel lungo dopo il primato nei 100m (una misura
in metri non è mai «meglio» di 10,9 secondi) e i PB, che danno fan e notizie, erano sbagliati.

Garanzie: (1) ogni gara ha il suo primato e le altre non lo toccano; (2) i primati si confrontano con il verso giusto (tempi più
bassi, misure più alte); (3) un risultato con vento illegale o un ritiro non conta; (4) la progressione cresce solo quando c'è un
miglioramento vero e non supera `PB_LOG_MAX` voci per gara; (5) salvataggio e ricarica la conservano; (6) nessun RNG.
"""

from __future__ import annotations

import copy
import random
import tempfile
import unittest
from pathlib import Path

from models.database import DatabaseManager
from models.entities import PB_LOG_MAX, Athlete
from models.personal_bests import (
    best_display,
    best_value,
    headline_events,
    is_improvement,
    pb_log_from_json,
    pb_log_to_json,
    progression,
    record_best,
    summary_text,
)
from models.simulation import simulate_competition
from tests.test_assignments import make_state


def sprinter_and_jumper_state(seed: int = 3):
    """Uno stesso atleta iscritto a una gara a tempo (100m) e a una a misura (Salto in Lungo)."""
    state = make_state(seed)
    athlete = next(a for a in state.main_squad if a.gender == "M")
    for event, athlete_id in list(state.event_lineup.items()):  # solo queste due gare (il limite è `MAX_INDIVIDUAL_EVENTS`)
        if athlete_id == athlete.id:
            state.event_lineup[event] = None
    state.event_lineup["100m"] = athlete.id
    state.event_lineup["Salto in Lungo"] = athlete.id
    return state, athlete


class TestEveryEventHasItsOwnBest(unittest.TestCase):
    def test_a_time_event_does_not_block_a_distance_event(self) -> None:
        """Il difetto di prima: dopo il primato nei 100m (10,9 s) il lungo (~6 m) non poteva più essere un PB."""
        state, a = sprinter_and_jumper_state()
        for week in (4, 8, 12):
            state.week = week
            simulate_competition(state, rng=random.Random(week))
        self.assertIsNotNone(best_value(a, "100m"))
        self.assertIsNotNone(best_value(a, "Salto in Lungo"))
        self.assertLess(best_value(a, "100m"), 20.0)  # secondi
        self.assertLess(best_value(a, "Salto in Lungo"), 12.0)  # metri
        self.assertGreater(best_value(a, "Salto in Lungo"), 2.0)

    def test_the_first_result_in_each_event_is_a_personal_best(self) -> None:
        for seed in range(1, 60):  # un seme in cui il vento è legale in entrambe le gare (altrimenti il risultato non conta)
            state, a = sprinter_and_jumper_state()
            state.week = 4
            summary = simulate_competition(state, rng=random.Random(seed))
            mine = {r.event_name: r for r in summary.event_results if r.player_athlete_name == a.name and r.gender == "M"}
            if not (mine["100m"].wind_illegal or mine["Salto in Lungo"].wind_illegal):
                break
        else:
            self.fail("nessun seme con vento legale")
        self.assertTrue(mine["100m"].is_pb and mine["Salto in Lungo"].is_pb)
        self.assertEqual(set(a.pb_log), {"100m", "Salto in Lungo"})

    def test_an_illegal_wind_does_not_count(self) -> None:
        for seed in range(1, 60):
            state, a = sprinter_and_jumper_state()
            state.week = 4
            summary = simulate_competition(state, rng=random.Random(seed))
            mine = {r.event_name: r for r in summary.event_results if r.player_athlete_name == a.name and r.gender == "M"}
            if mine["100m"].wind_illegal:
                self.assertFalse(mine["100m"].is_pb)
                self.assertNotIn("100m", a.pb_log)
                return
        self.fail("nessun seme con vento illegale")

    def test_the_best_of_each_event_is_never_worse_than_before(self) -> None:
        state, a = sprinter_and_jumper_state()
        prev = {}
        for week in range(4, 40, 4):
            state.week = week
            simulate_competition(state, rng=random.Random(week))
            for event, lower in (("100m", True), ("Salto in Lungo", False)):
                now = best_value(a, event)
                if event in prev:
                    self.assertTrue(now <= prev[event] if lower else now >= prev[event], (event, week))
                prev[event] = now

    def test_the_rng_is_not_touched_by_the_personal_bests(self) -> None:
        """Con o senza primati già registrati l'RNG finisce nello stesso stato: nessuna estrazione in più o in meno."""
        a_state, _ = sprinter_and_jumper_state()
        b_state = copy.deepcopy(a_state)
        for ath in b_state.main_squad:
            ath.pb_log = {}
        ra, rb = random.Random(9), random.Random(9)
        a_state.week = b_state.week = 4
        simulate_competition(a_state, rng=ra)
        simulate_competition(b_state, rng=rb)
        self.assertEqual(ra.getstate(), rb.getstate())


class TestRecording(unittest.TestCase):
    def athlete(self) -> Athlete:
        return make_state().main_squad[0]

    def test_directions(self) -> None:
        a = self.athlete()
        self.assertTrue(is_improvement("100m", 11.0, a))  # nessun primato: il primo vale sempre
        record_best(a, "100m", 11.0, "11.00s", 1, 4, "Meeting A")
        self.assertTrue(is_improvement("100m", 10.9, a))  # tempo più basso = meglio
        self.assertFalse(is_improvement("100m", 11.0, a))  # pari non è un miglioramento
        self.assertFalse(is_improvement("100m", 11.1, a))
        record_best(a, "Salto in Lungo", 6.0, "6.00m", 1, 4, "Meeting A")
        self.assertTrue(is_improvement("Salto in Lungo", 6.1, a))  # misura più alta = meglio
        self.assertFalse(is_improvement("Salto in Lungo", 5.9, a))

    def test_the_progression_is_chronological_and_improving(self) -> None:
        a = self.athlete()
        for i, value in enumerate((11.5, 11.3, 11.2, 11.0)):
            record_best(a, "100m", value, f"{value:.2f}s", 1, 4 * (i + 1), f"Meeting {i}")
        steps = progression(a, "100m")
        self.assertEqual([s["value"] for s in steps], [11.5, 11.3, 11.2, 11.0])
        self.assertEqual(best_value(a, "100m"), 11.0)
        self.assertEqual(best_display(a, "100m"), "11.00s")
        self.assertEqual(steps[-1]["meet"], "Meeting 3")
        self.assertEqual((steps[0]["season"], steps[0]["week"]), (1, 4))

    def test_the_progression_is_capped_and_keeps_the_best(self) -> None:
        a = self.athlete()
        for i in range(PB_LOG_MAX + 8):
            record_best(a, "100m", 13.0 - 0.01 * i, f"{13.0 - 0.01 * i:.2f}s", 1 + i // 9, 4 * (i % 9 + 1), "M")
        steps = progression(a, "100m")
        self.assertEqual(len(steps), PB_LOG_MAX)
        self.assertAlmostEqual(best_value(a, "100m"), 13.0 - 0.01 * (PB_LOG_MAX + 7))
        self.assertEqual(steps[-1]["value"], best_value(a, "100m"))

    def test_the_events_do_not_overwrite_each_other(self) -> None:
        a = self.athlete()
        record_best(a, "100m", 11.0, "11.00s", 1, 4, "M")
        record_best(a, "Getto del Peso", 12.0, "12.00m", 1, 4, "M")
        self.assertEqual(best_value(a, "100m"), 11.0)
        self.assertEqual(best_value(a, "Getto del Peso"), 12.0)
        self.assertIsNone(best_value(a, "400m"))
        self.assertEqual(progression(a, "400m"), [])


class TestHeadline(unittest.TestCase):
    def athlete(self) -> Athlete:
        a = make_state().main_squad[0]
        record_best(a, "100m", 11.0, "11.00s", 1, 4, "M")
        record_best(a, "Salto in Lungo", 6.0, "6.00m", 1, 8, "M")
        record_best(a, "400m", 50.0, "50.00s", 2, 4, "M")
        return a

    def test_entered_events_come_first_in_the_given_order(self) -> None:
        a = self.athlete()
        self.assertEqual(headline_events(a, ["Salto in Lungo", "100m"]), ["Salto in Lungo", "100m"])
        self.assertEqual(headline_events(a, ["800m"]), ["400m", "Salto in Lungo"])  # iscritto senza primato: i più recenti

    def test_without_entries_the_two_most_recent(self) -> None:
        a = self.athlete()
        self.assertEqual(headline_events(a, []), ["400m", "Salto in Lungo"])

    def test_the_text(self) -> None:
        a = self.athlete()
        self.assertEqual(summary_text(a, ["100m"]), "11.00s")
        self.assertEqual(summary_text(a, ["100m", "Salto in Lungo"]), "100m 11.00s · Salto in Lungo 6.00m")
        self.assertEqual(summary_text(make_state().main_squad[1], ["100m"]), "—")


class TestJson(unittest.TestCase):
    def test_round_trip(self) -> None:
        a = make_state().main_squad[0]
        record_best(a, "100m", 11.0, "11.00s", 1, 4, "Meeting A")
        record_best(a, "100m", 10.9, "10.90s", 1, 8, "Meeting B")
        self.assertEqual(pb_log_from_json(pb_log_to_json(a.pb_log)), a.pb_log)

    def test_broken_input_is_an_empty_log(self) -> None:
        for raw in (None, "", "{", "[]", "3", '{"100m": 5}', '{"100m": ["x"]}'):
            self.assertEqual(pb_log_from_json(raw), {}, raw)

    def test_bad_entries_are_dropped_and_the_log_is_cut(self) -> None:
        good = {"season": 1, "week": 4, "value": 11.0, "display": "11.00s", "meet": "M"}
        raw = pb_log_to_json({"100m": [{"season": "x"}, good], "Evento Falso": [good]})
        self.assertEqual(pb_log_from_json(raw), {"100m": [good]})
        many = pb_log_to_json({"100m": [{**good, "value": 20.0 - 0.01 * i} for i in range(PB_LOG_MAX + 5)]})
        self.assertEqual(len(pb_log_from_json(many)["100m"]), PB_LOG_MAX)


class TestSaveLoad(unittest.TestCase):
    def test_the_log_survives_a_save_and_load(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        state, a = sprinter_and_jumper_state()
        record_best(a, "100m", 10.8, "10.80s", 1, 4, "Meeting A")
        record_best(a, "Salto in Lungo", 7.1, "7.10m", 1, 4, "Meeting A")
        db = DatabaseManager(db_path=Path(tmp.name) / "s.db")
        db.save_game(state)
        loaded = db.load_game()
        b = next(x for x in loaded.athletes if x.id == a.id)
        self.assertEqual(b.pb_log, a.pb_log)
        self.assertEqual(best_value(b, "Salto in Lungo"), 7.1)


if __name__ == "__main__":
    unittest.main()
