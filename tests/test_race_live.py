"""Tabellone live della gara in diretta (PIANOLAVORO G.3), Qt offscreen.

Garanzie: (1) è **sola lettura**: usa le stesse `position_fraction` e gli stessi dati del renderer, quindi a tempo pieno la classifica coincide
con quella ufficiale e ogni atleta risulta arrivato esattamente a `mark_value`; (2) durante la gara i metri non tornano mai indietro e i posti
sono una permutazione; (3) ritirati ultimi, mai arrivati; (4) il pannello QML non produce avvisi e compare solo per le corse in pista.
"""

from __future__ import annotations

import json
import os
import random
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("TEF_NO_GODOT", "1")

from PyQt6.QtCore import qInstallMessageHandler
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from controllers.game_controller import GameController
from models.bibs import assign_bibs
from models.database import DatabaseManager
from tests.support import start_game
from views.race_live import DNF_PROGRESS, empty_board, live_board
from views.race_viewer import TrackRaceWidget, RaceViewerDialog, is_field_event, position_fraction

_app = QApplication.instance() or QApplication([])


def played_meeting(seed: int = 4):  # seed scelto perché il meeting abbia corse e staffette (con il 5 il test delle staffette saltava)
    tmp = tempfile.TemporaryDirectory()
    ctrl = GameController(db_manager=DatabaseManager(db_path=Path(tmp.name) / "s.db"), rng=random.Random(seed), auto_create=False)
    start_game(ctrl)
    for _ in range(8):
        ctrl.dismiss_dilemma()
        ctrl.advance_week()
    return tmp, ctrl.state.competition_history[0]


def track_results(summary):
    return [r for r in summary.event_results if not is_field_event(r.event_name)]


def widget_for(summary, result) -> TrackRaceWidget:
    w = TrackRaceWidget()
    w.set_race(result.event_name, result, f"{summary.week}-{summary.meet_name}")
    return w


class TestLiveBoard(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp, cls.summary = played_meeting()
        cls.results = track_results(cls.summary)
        assert cls.results, "il meeting di prova non ha corse in pista"

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def board(self, w: TrackRaceWidget, t: float, **kw) -> dict:
        return live_board(w.runners, w.event_name, w.distance, t, w.winner_time, **kw)

    def test_the_final_board_is_the_official_result_for_every_track_race(self) -> None:
        for res in self.results:
            w = widget_for(self.summary, res)
            last = max(r["s"].mark_value for r in w.runners if not r["dnf"])
            b = self.board(w, last + 5)
            self.assertTrue(b["done"], res.event_name)
            by_rank = sorted(b["rows"], key=lambda r: r["rank"])
            self.assertEqual([r["name"] for r in by_rank if not r["dnf"]], [s.athlete_name for s in sorted(res.standings, key=lambda s: s.placement) if not (s.is_player and res.withdrew_injured)], res.event_name)
            for r in b["rows"]:
                if not r["dnf"]:
                    self.assertTrue(r["finished"])
                    self.assertEqual(r["pct"], 1.0)

    def test_everyone_arrives_exactly_at_their_official_time(self) -> None:
        """Lo stesso invariante del renderer: si arriva a `mark_value`, non un istante prima."""
        for res in self.results:
            w = widget_for(self.summary, res)
            for i, r in enumerate(w.runners):
                if r["dnf"]:
                    continue
                mark = r["s"].mark_value
                before = self.board(w, mark - 1e-3)["rows"][i]
                at = self.board(w, mark)["rows"][i]
                self.assertFalse(before["finished"], f"{res.event_name} {r['s'].athlete_name}")
                self.assertTrue(at["finished"])
                self.assertEqual(at["markText"], r["s"].mark_display)

    def test_it_reads_the_same_positions_as_the_renderer(self) -> None:
        res = self.results[0]
        w = widget_for(self.summary, res)
        for frac in (0.1, 0.4, 0.8):
            t = w.winner_time * frac
            w._t = 2.4 + t / w._scale  # il renderer legge `race_time` dal proprio orologio
            b = self.board(w, w.race_time)
            for i, r in enumerate(w.runners):
                self.assertAlmostEqual(b["rows"][i]["meters"], min(w.distance, w.fraction(r) * w.distance), places=6)

    def test_start_nobody_has_moved_or_finished(self) -> None:
        w = widget_for(self.summary, self.results[0])
        b = self.board(w, 0.0)
        self.assertFalse(b["started"])
        self.assertTrue(all(r["meters"] == 0 and not r["finished"] and r["speedKmh"] == 0 for r in b["rows"]))

    def test_meters_never_go_back_and_ranks_are_a_permutation(self) -> None:
        for res in self.results[:3]:
            w = widget_for(self.summary, res)
            prev = [0.0] * len(w.runners)
            steps = 40
            for k in range(steps + 1):
                b = self.board(w, w.winner_time * 1.2 * k / steps)
                self.assertEqual(sorted(r["rank"] for r in b["rows"]), list(range(1, len(b["rows"]) + 1)))
                for i, r in enumerate(b["rows"]):
                    self.assertGreaterEqual(r["meters"] + 1e-9, prev[i], f"{res.event_name} t-step {k}")
                    self.assertLessEqual(r["meters"], w.distance + 1e-9)
                    self.assertGreaterEqual(r["speedKmh"], 0.0)
                    prev[i] = r["meters"]

    def test_the_leader_has_the_most_meters_among_those_still_running(self) -> None:
        w = widget_for(self.summary, self.results[0])
        b = self.board(w, w.winner_time * 0.5)
        running = [r for r in b["rows"] if not r["finished"] and not r["dnf"]]
        leader = min(running, key=lambda r: r["rank"])
        self.assertEqual(leader["rank"], 1)
        self.assertEqual(leader["meters"], max(r["meters"] for r in running))
        self.assertEqual(leader["gap"], "")  # il primo non ha distacco
        self.assertTrue(all(r["gap"].startswith("+") for r in running if r is not leader))

    def test_finished_gaps_are_time_differences_to_the_winner(self) -> None:
        res = self.results[0]
        w = widget_for(self.summary, res)
        b = self.board(w, w.winner_time * 3)
        rows = sorted((r for r in b["rows"] if not r["dnf"]), key=lambda r: r["rank"])
        for r in rows[1:]:
            self.assertEqual(r["gap"], f"+{r['mark'] - rows[0]['mark']:.2f} s")
        self.assertEqual(rows[0]["gap"], rows[0]["markText"])

    def test_a_withdrawn_athlete_is_last_and_never_arrives(self) -> None:
        res = self.results[0]
        res = mock.Mock(wraps=res)  # stesso risultato, ma con il giocatore ritirato
        res.standings = self.results[0].standings
        res.withdrew_injured = True
        res.event_name = self.results[0].event_name
        w = TrackRaceWidget()
        w.set_race(res.event_name, res, "x")
        dnfs = [i for i, r in enumerate(w.runners) if r["dnf"]]
        if not dnfs:
            self.skipTest("nessun atleta del club in questa gara")
        for t in (0.0, w.winner_time * 0.5, w.winner_time * 5):
            b = self.board(w, t)
            for i in dnfs:
                row = b["rows"][i]
                self.assertFalse(row["finished"])
                self.assertLessEqual(row["pct"], DNF_PROGRESS + 1e-9)
                self.assertEqual(row["rank"], len(b["rows"]))
        self.assertEqual(b["rows"][dnfs[0]]["gap"], "ritirato")

    def test_pure_data_and_the_same_keys_as_the_empty_board(self) -> None:
        w = widget_for(self.summary, self.results[0])
        b = self.board(w, w.winner_time * 0.5, bibs=assign_bibs(self.summary), phase="", replay=False, race_id="r")
        json.dumps(b)
        self.assertEqual(set(b), set(empty_board()))
        self.assertTrue(all(r["bib"] > 0 for r in b["rows"]))
        self.assertTrue(all(r["kit"].startswith("#") for r in b["rows"]))

    def test_relays_are_covered_too(self) -> None:
        relays = [r for r in self.results if "x" in r.event_name.lower()]
        if not relays:
            self.skipTest("nessuna staffetta in questo meeting")
        w = widget_for(self.summary, relays[0])
        b = self.board(w, w.winner_time * 5)
        self.assertTrue(b["done"] or any(r["dnf"] for r in b["rows"]))


class TestPanelInTheDialog(unittest.TestCase):
    def setUp(self) -> None:
        self.messages: list[str] = []
        previous = qInstallMessageHandler(lambda _m, ctx, msg: self.messages.append(msg) if (ctx.file or "").endswith(".qml") or "qml" in msg.lower() else None)
        self.addCleanup(qInstallMessageHandler, previous)
        tmp, self.summary = played_meeting()
        self.addCleanup(tmp.cleanup)

    def dialog(self) -> RaceViewerDialog:
        d = RaceViewerDialog(self.summary)
        self.addCleanup(d.close)
        d.show()
        QTest.qWait(150)
        return d

    def test_the_panel_shows_for_a_track_race_and_loads_clean(self) -> None:
        d = self.dialog()
        self.assertFalse(is_field_event(self.summary.event_results[0].event_name))
        self.assertTrue(d.board_panel.isVisible())
        self.assertFalse(d.board_panel.failed)
        self.assertEqual(d.board_panel.qml.warnings, [])
        self.assertEqual(self.messages, [])
        self.assertTrue(d.board_panel.board["rows"])

    def test_skipping_to_the_end_shows_the_official_final_board(self) -> None:
        d = self.dialog()
        d._skip_race()
        QTest.qWait(150)
        board = d.board_panel.board
        self.assertTrue(board["done"])
        res = self.summary.event_results[0]
        by_rank = [r["name"] for r in sorted(board["rows"], key=lambda r: r["rank"]) if not r["dnf"]]
        self.assertEqual(by_rank, [s.athlete_name for s in sorted(res.standings, key=lambda s: s.placement) if not (s.is_player and res.withdrew_injured)])
        self.assertEqual(d.board_panel.qml.warnings, [])
        self.assertEqual(self.messages, [])

    def test_the_button_hides_and_shows_the_panel(self) -> None:
        d = self.dialog()
        d.btn_board.setChecked(False)
        d._update_board(force=True)
        self.assertFalse(d.board_panel.isVisible())
        d.btn_board.setChecked(True)
        d._update_board(force=True)
        self.assertTrue(d.board_panel.isVisible())

    def test_updates_are_throttled_to_about_ten_per_second(self) -> None:
        d = self.dialog()
        d._update_board(force=True)
        first = d.board_panel.board
        d._update_board()  # subito dopo: nessun nuovo calcolo
        self.assertIs(d.board_panel.board, first)
        QTest.qWait(130)
        d._update_board()
        self.assertIsNot(d.board_panel.board, first)

    def test_no_panel_for_field_events(self) -> None:
        field = [i for i, r in enumerate(self.summary.event_results) if is_field_event(r.event_name)]
        if not field:
            self.skipTest("nessun concorso in questo meeting")
        d = self.dialog()
        d._index = field[0] - 1
        d._race_done = True
        d._next()
        self.assertFalse(d.board_panel.isVisible())

    def test_with_qml_disabled_the_dialog_works_without_the_panel(self) -> None:
        with mock.patch.dict(os.environ, {"TEF_NO_QML": "1"}):
            d = RaceViewerDialog(self.summary)
        self.addCleanup(d.close)
        d.show()
        self.assertTrue(d.board_panel.failed)
        self.assertFalse(d.board_panel.isVisible())
        d._skip_race()  # la gara si guarda e si salta come prima
        self.assertTrue(d._race_done)

    def test_the_race_itself_is_unchanged_by_the_panel(self) -> None:
        """Il renderer non legge nulla dal pannello: stessi risultati con e senza (e il finale è sempre `mark_value`)."""
        d = self.dialog()
        res = self.summary.event_results[0]
        before = [(s.athlete_name, s.mark_value, s.placement) for s in res.standings]
        d._skip_race()
        QTest.qWait(100)
        self.assertEqual(before, [(s.athlete_name, s.mark_value, s.placement) for s in res.standings])
        for r in d.track.runners:
            if not r["dnf"]:
                self.assertAlmostEqual(position_fraction(d.track.event_name, r["s"].mark_value, r["s"].mark_value, r["react"], r["phase"]), 1.0, places=6)

    def test_the_finish_replay_works_in_2d_and_3d_and_changes_nothing(self) -> None:
        """Replay dell'arrivo (G.3): disponibile in entrambe le viste, riavvolge, scorre al rallentatore e torna al finale identico."""
        d = self.dialog()
        res = self.summary.event_results[0]
        before = [(s.athlete_name, s.mark_value, s.placement) for s in res.standings]
        self.assertFalse(d.btn_replay.isEnabled())  # non prima della fine della gara
        d._skip_race()
        QTest.qWait(100)
        for view in ("2d", "3d"):
            if (d.track is d.track2d) != (view == "2d"):
                d._toggle_view()
            w = d.track
            final_t = w._t
            self.assertTrue(d.btn_replay.isEnabled(), view)
            d._start_replay()
            self.assertTrue(d._replay_active and w._replay_active, view)
            self.assertLess(w._t, final_t, view)  # riavvolto
            self.assertFalse(d.btn_replay.isEnabled(), view)
            self.assertFalse(d.btn_view.isEnabled(), view)
            w.grab()  # disegno in replay senza eccezioni
            d._clock.restart()
            for _ in range(2000):  # scorre fino al traguardo del vincitore
                if not d._replay_active:
                    break
                w.advance(0.1 * d.REPLAY_SPEED)
                d._tick()
            self.assertFalse(d._replay_active, view)
            self.assertFalse(w._replay_active, view)
            self.assertTrue(w._done and d.btn_replay.isEnabled() and d.btn_view.isEnabled(), view)
            self.assertAlmostEqual(w._t, final_t, places=6, msg=view)
        self.assertEqual(before, [(s.athlete_name, s.mark_value, s.placement) for s in res.standings])


if __name__ == "__main__":
    unittest.main()
