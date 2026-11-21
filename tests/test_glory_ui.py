"""Lotto F.4 (parte con Qt offscreen): popup dei momenti di gloria e aggancio al controller.

«Test manuale» del piano (record del mondo → popup) **non eseguito con il mouse**: qui si istanzia il popup (mai `exec()`) e si
prova il percorso controller → segnale → finestra con dialoghi finti.
"""

from __future__ import annotations

import os
import random
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("TEF_NO_GODOT", "1")

from PyQt6.QtWidgets import QApplication, QLabel

from controllers.game_controller import GameController
from models.database import DatabaseManager
from models.entities import SeasonOutcome
from models.glory import ATHLETE_OF_THE_YEAR, CHAMPION, WORLD_RECORD, GloryMoment
from tests.support import start_game
from tests.test_glory import meet, result, season_end
from views.dialogs import GloryMomentDialog
from views.main_window import MainWindow

_app = QApplication.instance() or QApplication([])


class _Base(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "s.db"
        self.ctrl = GameController(db_manager=DatabaseManager(db_path=self.path), rng=random.Random(3), auto_create=False)
        start_game(self.ctrl, team_name="CUS Test", game_mode="career")
        self.state = self.ctrl.state


class TestDialog(_Base):
    def test_it_shows_title_and_text_and_prepares_a_fade_in(self) -> None:
        moment = GloryMoment(WORLD_RECORD, "RECORD DEL MONDO!", "Mario Rossi segna 9.58.", "Mario Rossi")
        dlg = GloryMomentDialog(moment)
        self.addCleanup(dlg.close)
        labels = [w.text() for w in dlg.findChildren(QLabel)]
        self.assertIn("RECORD DEL MONDO!", labels)
        self.assertIn("Mario Rossi segna 9.58.", labels)
        self.assertEqual(dlg.windowTitle(), "RECORD DEL MONDO!")
        self.assertEqual(dlg.fade.duration(), GloryMomentDialog.FADE_MS)
        self.assertEqual(dlg.windowOpacity(), 0.0)  # parte trasparente e sale con la dissolvenza

    def test_the_button_closes_it(self) -> None:
        dlg = GloryMomentDialog(GloryMoment(CHAMPION, "CAMPIONI!", "x"))
        self.addCleanup(dlg.close)
        dlg.close_btn.click()
        self.assertEqual(dlg.result(), dlg.DialogCode.Accepted)


class TestController(_Base):
    def report(self, summary=None, season=None):
        return SimpleNamespace(competition_summary=summary, season_end=season)

    def test_a_world_record_is_logged_as_news_and_milestone(self) -> None:
        summary = meet([result("Mario Rossi", 1, mark=9.58)], week=self.state.week)
        moments = self.ctrl._glory_of(self.report(summary), set(self.state.milestones))
        self.assertEqual([m.kind for m in moments], [WORLD_RECORD])
        self.assertIn("RECORD DEL MONDO", self.state.news_log[0])
        self.assertIn("RECORD DEL MONDO", self.state.milestones[0])

    def test_historic_milestones_are_picked_from_the_new_ones_only(self) -> None:
        old = "Sett. 4: MOMENTO STORICO! Vecchio abbatte il muro (M) (10.9s)!"
        self.state.milestones.insert(0, old)
        before = set(self.state.milestones)
        new = "Sett. 8: MOMENTO STORICO! Nuovo abbatte il muro (M) (10.8s)!"
        self.state.milestones.insert(0, new)
        moments = self.ctrl._glory_of(self.report(meet([], week=8)), before)
        self.assertEqual(len(moments), 1)
        self.assertIn("Nuovo abbatte", moments[0].text)
        self.assertEqual(self.state.milestones.count(new), 1)  # nessuna riga doppia

    def test_the_season_end_adds_the_athlete_of_the_year(self) -> None:
        self.state.prep_weeks = 0
        self.state.competition_history = [meet([result("Bruno", 1)], week=8)]
        moments = self.ctrl._glory_of(self.report(None, season_end(SeasonOutcome.CHAMPION, 1)), set())
        self.assertEqual([m.kind for m in moments], [CHAMPION, ATHLETE_OF_THE_YEAR])
        self.assertTrue(any("ATLETA DELL'ANNO" in n for n in self.state.news_log[:2]))

    def test_nothing_happens_without_a_meeting_or_a_season_end(self) -> None:
        before = list(self.state.news_log)
        self.assertEqual(self.ctrl._glory_of(self.report(), set()), [])
        self.assertEqual(self.state.news_log, before)

    def test_advance_week_emits_the_moments_after_logging_and_saving_them(self) -> None:
        summary = meet([result("Mario Rossi", 1, mark=9.58)], week=self.state.week)
        stub = SimpleNamespace(
            completed_week=self.state.week, new_week=self.state.week + 1, competition_summary=summary, season_end=None,
            triggered_dilemma=None,
        )
        got = []
        self.ctrl.glory_moments.connect(got.append)
        with mock.patch("controllers.game_controller.advance_week", return_value=stub):
            self.ctrl.advance_week()
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0][0].kind, WORLD_RECORD)
        other = GameController(db_manager=DatabaseManager(db_path=self.path), rng=random.Random(9), auto_create=False)
        self.assertTrue(other.load_game())
        self.assertTrue(any("RECORD DEL MONDO" in m for m in other.state.milestones))  # già nel salvataggio

    def test_no_signal_when_nothing_deserves_a_popup(self) -> None:
        got = []
        self.ctrl.glory_moments.connect(got.append)
        stub = SimpleNamespace(
            completed_week=1, new_week=2, competition_summary=None, season_end=None, triggered_dilemma=None
        )
        with mock.patch("controllers.game_controller.advance_week", return_value=stub):
            self.ctrl.advance_week()
        self.assertEqual(got, [])

    def test_the_game_rng_is_untouched_by_the_glory_logic(self) -> None:
        before = self.ctrl.rng.getstate()
        self.ctrl._glory_of(self.report(meet([result("A", 1, mark=9.58)], week=1)), set())
        self.assertEqual(self.ctrl.rng.getstate(), before)


class TestMainWindow(_Base):
    def test_every_moment_gets_its_own_popup_in_order(self) -> None:
        win = MainWindow(self.ctrl)
        self.addCleanup(win.close)
        moments = [GloryMoment(CHAMPION, "A", "a"), GloryMoment(ATHLETE_OF_THE_YEAR, "B", "b")]
        with mock.patch("views.main_window.GloryMomentDialog") as dialog:
            win._show_glory_moments(moments)
        self.assertEqual([c.args[0] for c in dialog.call_args_list], moments)
        self.assertEqual(dialog.return_value.exec.call_count, 2)

    def test_the_window_listens_to_the_controller_signal(self) -> None:
        win = MainWindow(self.ctrl)
        self.addCleanup(win.close)
        with mock.patch("views.main_window.GloryMomentDialog") as dialog:
            self.ctrl.glory_moments.emit([GloryMoment(CHAMPION, "A", "a")])
        dialog.return_value.exec.assert_called_once()


if __name__ == "__main__":
    unittest.main()
