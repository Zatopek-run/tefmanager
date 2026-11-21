"""Lotto C.2 (parte con Qt offscreen): Dashboard, dialoghi del Board, pulsante «Avanza» e controller (esonero).

Non si prova il mouse reale: i dialoghi si istanziano e si leggono, `exec()` è sostituito da un finto.
"""

from __future__ import annotations

import os
import random
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("TEF_NO_GODOT", "1")

from PyQt6.QtWidgets import QApplication

from controllers.game_controller import GameController
from tests.support import start_game
from models.database import DatabaseManager
from models.entities import BOARD_KEYS, STANDARD_BOARD_KEYS, SeasonEndResult, SeasonOutcome
from models.simulation import advance_week
from views.dialogs import BoardObjectivesDialog, SeasonEndDialog
from views.main_window import MainWindow

_app = QApplication.instance() or QApplication([])


def _career(path: Path, seed: int = 3) -> GameController:
    ctrl = GameController(db_manager=DatabaseManager(db_path=path), rng=random.Random(seed), auto_create=False)
    start_game(ctrl, team_name="CUS Test", game_mode="career")
    return ctrl


def _play_season(ctrl: GameController) -> None:
    """Gioca 36 settimane in autopilota (nessun dilemma)."""
    season = ctrl.state.season_number
    while ctrl.state.season_number == season:
        ctrl.dismiss_dilemma()
        advance_week(ctrl.state, rng=ctrl.rng)


class TestSeasonCycle(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.ctrl = _career(Path(tmp.name) / "s.db")

    def test_a_new_career_starts_with_the_three_board_objectives(self) -> None:
        self.assertEqual([o.key for o in self.ctrl.state.objectives], list(STANDARD_BOARD_KEYS))
        budget = next(o for o in self.ctrl.state.objectives if o.key == "board_budget")
        self.assertEqual(budget.target, self.ctrl.state.budget)

    def test_the_season_end_judges_the_season_and_renews_the_objectives(self) -> None:
        state = self.ctrl.state
        _play_season(self.ctrl)
        self.assertEqual(state.season_number, 2)
        verdict = state.season_history[0]
        self.assertIsNotNone(verdict.board_failed)
        self.assertEqual(len(verdict.board_results), 3)
        self.assertEqual([o.key for o in state.objectives], list(STANDARD_BOARD_KEYS))
        self.assertTrue(all(o.value == 0 and not o.completed for o in state.objectives if o.key != "board_budget"))
        self.assertTrue(any("il Board assegna" in line for line in state.news_log))

    def test_the_verdict_survives_save_and_load(self) -> None:
        _play_season(self.ctrl)
        self.ctrl._persist()
        loaded = GameController(
            db_manager=self.ctrl.db, rng=random.Random(1), auto_create=False
        )
        self.assertTrue(loaded.load_game())
        self.assertEqual(loaded.state.season_history[0].board_results, self.ctrl.state.season_history[0].board_results)
        self.assertEqual(loaded.state.board_failed_streak, self.ctrl.state.board_failed_streak)

    def test_a_fired_manager_cannot_advance(self) -> None:
        state = self.ctrl.state
        state.fired = True
        week = state.week
        messages = []
        self.ctrl.status_message.connect(messages.append)
        self.assertIsNone(self.ctrl.advance_week())
        self.assertEqual(state.week, week)
        self.assertTrue(any("Esonerato" in m for m in messages))
        self.assertFalse(self.ctrl.is_advancing)


class TestViews(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.ctrl = _career(Path(tmp.name) / "s.db")
        self.win = MainWindow(controller=self.ctrl)
        self.addCleanup(self.win.close)

    def dashboard_lines(self) -> list:
        return [o["text"] for o in self.win.dashboard_tab.snapshot["objectives"]]  # G.1 in QML: la Dashboard disegna lo snapshot

    def test_the_dashboard_shows_the_objectives_with_their_progress(self) -> None:
        lines = self.dashboard_lines()
        self.assertEqual(len(lines), 3)
        self.assertIn("obiettivo", lines[0])
        self.assertIn("0/2", lines[2])

    def test_the_dashboard_warns_after_a_failed_season_and_after_the_sacking(self) -> None:
        self.ctrl.state.board_failed_streak = 1
        self.win.dashboard_tab.refresh(self.ctrl.state)
        self.assertIn("Attenzione", self.dashboard_lines()[-1])
        self.ctrl.state.fired = True
        self.win.dashboard_tab.refresh(self.ctrl.state)
        self.assertIn("ESONERATO", self.dashboard_lines()[-1])

    def test_the_advance_button_is_off_when_fired(self) -> None:
        self.assertTrue(self.win.advance_btn.isEnabled())
        self.ctrl.state.fired = True
        self.win._refresh_all(self.ctrl.state)
        self.assertFalse(self.win.advance_btn.isEnabled())
        self.assertIn("Esonerato", self.win.advance_btn.text())

    def test_the_prototype_dashboard_keeps_its_own_objectives(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            proto = GameController(
                db_manager=DatabaseManager(db_path=Path(tmp) / "p.db"), rng=random.Random(3), auto_create=False
            )
            start_game(proto, team_name="CUS Test", game_mode="vertical_slice")
            self.assertTrue(all(o.key not in BOARD_KEYS for o in proto.state.objectives))


def _result(**kw) -> SeasonEndResult:
    base = dict(
        season=1,
        tier=__import__("models.entities", fromlist=["CompetitionTier"]).CompetitionTier.PROVINCIALE,
        placement=5,
        outcome=SeasonOutcome.STAYED,
        final_table=[("CUS Test", 10), ("Altra", 8)],
        board_results=[("Obiettivo uno", True), ("Obiettivo due", False), ("Obiettivo tre", False)],
        board_failed=True,
        board_streak=1,
    )
    base.update(kw)
    return SeasonEndResult(**base)


class TestDialogs(unittest.TestCase):
    def text(self, **kw) -> str:
        dlg = SeasonEndDialog(_result(**kw), "CUS Test")
        self.addCleanup(dlg.close)
        return dlg.board_label.text() if dlg.board_label is not None else ""

    def test_season_end_dialog_lists_the_objectives_and_the_verdict(self) -> None:
        text = self.text()
        self.assertIn("✔ Obiettivo uno", text)
        self.assertIn("✘ Obiettivo due", text)
        self.assertIn("FALLITA", text)
        self.assertIn("soddisfatto", self.text(board_failed=False, board_streak=0))
        self.assertIn("ESONERATO", self.text(fired=True, board_streak=2))

    def test_a_season_without_a_board_verdict_shows_no_board_block(self) -> None:
        self.assertEqual(self.text(board_failed=None, board_results=[]), "")

    def test_objectives_dialog_shows_the_goals_and_the_warning(self) -> None:
        objs = _career_objectives()
        dlg = BoardObjectivesDialog(objs, 2, "CUS Test", failed_streak=1)
        self.addCleanup(dlg.close)
        for o in objs:
            self.assertIn(o.title, dlg.objectives_label.text())

    def test_the_main_window_opens_the_objectives_after_the_season_end_unless_fired(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ctrl = _career(Path(tmp) / "s.db")
            win = MainWindow(controller=ctrl)
            self.addCleanup(win.close)
            with mock.patch("views.main_window.SeasonEndDialog"), mock.patch(
                "views.main_window.BoardObjectivesDialog"
            ) as objectives_dialog:
                win._show_season_end(_result())
                self.assertEqual(objectives_dialog.call_count, 1)
                ctrl.state.fired = True
                win._show_season_end(_result(fired=True))
                self.assertEqual(objectives_dialog.call_count, 1)  # esonerato: nessun nuovo obiettivo


def _career_objectives():
    from models.board import create_board_objectives
    from models.entities import CompetitionTier

    return create_board_objectives(CompetitionTier.REGIONALE, 25000)


if __name__ == "__main__":
    unittest.main()
