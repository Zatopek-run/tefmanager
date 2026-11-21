"""Lotto F.2 (parte con Qt offscreen): finestra della conferenza stampa, controller e aggancio ai risultati della gara.

Non si prova il mouse reale e non si chiama mai `exec()` di un dialogo vero (in offscreen non torna): si istanziano i
dialoghi e si chiamano i metodi, oppure si sostituiscono con finti.
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
from models.agents import agent_of
from models.database import DatabaseManager
from models.entities import PRESS_RELATION, PRESS_REPUTATION
from models.press import FUTURE, PERFORMANCE, build_conference
from tests.support import start_game
from tests.test_press_conference import result, summary
from views.dialogs import PressConferenceDialog
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
        self.state.reputation = 50
        self.star = self.state.main_squad[0]
        self.summary = summary(1, results=[result(self.star.name, 1)], week=4)
        self.summary.player_team = self.state.team_name
        self.summary.team_standings[0] = (self.state.team_name, self.summary.team_standings[0][1])


class TestController(_Base):
    def test_a_conference_is_offered_once_per_meeting_after_it_is_answered(self) -> None:
        conf = self.ctrl.press_conference_for(self.summary)
        self.assertIsNotNone(conf)
        self.assertTrue(self.ctrl.answer_press_conference(conf, {PERFORMANCE: "soddisfatto"}))
        self.assertIsNone(self.ctrl.press_conference_for(self.summary))
        self.assertFalse(self.ctrl.answer_press_conference(conf, {PERFORMANCE: "soddisfatto"}))
        self.assertEqual(self.state.reputation, 50 + PRESS_REPUTATION["good"]["soddisfatto"])  # una volta sola

    def test_an_unanswered_conference_can_be_offered_again_and_changes_nothing(self) -> None:
        conf = self.ctrl.press_conference_for(self.summary)
        self.assertFalse(self.ctrl.answer_press_conference(conf, {}))
        self.assertEqual(self.state.reputation, 50)
        self.assertIsNotNone(self.ctrl.press_conference_for(self.summary))

    def test_answers_move_reputation_and_the_agent_and_are_logged_and_saved(self) -> None:
        conf = self.ctrl.press_conference_for(self.summary)
        agent = agent_of(self.state, self.star)
        before = agent.relation
        self.ctrl.answer_press_conference(conf, {PERFORMANCE: "cauto", FUTURE: "punto"})
        self.assertEqual(self.state.reputation, 50 + PRESS_REPUTATION["good"]["cauto"])
        self.assertEqual(agent_of(self.state, self.star).relation, before + PRESS_RELATION["punto"])
        self.assertTrue(any("Conferenza stampa" in n for n in self.state.news_log[:3]))
        other = GameController(db_manager=DatabaseManager(db_path=self.path), rng=random.Random(9), auto_create=False)
        self.assertTrue(other.load_game())
        self.assertEqual(other.state.reputation, self.state.reputation)
        self.assertEqual(agent_of(other.state, other.state.main_squad[0]).relation, agent_of(self.state, self.star).relation)

    def test_the_game_rng_is_untouched(self) -> None:
        before = self.ctrl.rng.getstate()
        conf = self.ctrl.press_conference_for(self.summary)
        self.ctrl.answer_press_conference(conf, {PERFORMANCE: "critico", FUTURE: "dubbio"})
        self.assertEqual(self.ctrl.rng.getstate(), before)

    def test_no_conference_for_an_absent_club(self) -> None:
        self.summary.club_absent = True
        self.assertIsNone(self.ctrl.press_conference_for(self.summary))


class TestDialog(_Base):
    def make(self):
        conf = build_conference(self.state, self.summary)
        dlg = PressConferenceDialog(conf)
        self.addCleanup(dlg.close)
        return dlg

    def test_it_lists_every_answer_of_every_question(self) -> None:
        dlg = self.make()
        self.assertEqual(set(dlg._groups), {PERFORMANCE, FUTURE})
        for group in dlg._groups.values():
            self.assertEqual(len(group), 3)

    def test_the_two_questions_are_answered_independently(self) -> None:
        dlg = self.make()
        dlg._groups[PERFORMANCE]["critico"].setChecked(True)
        dlg._groups[FUTURE]["punto"].setChecked(True)
        self.assertTrue(dlg._groups[PERFORMANCE]["critico"].isChecked())  # scegliere sull'altra domanda non la deseleziona
        dlg._answer()
        self.assertTrue(dlg.answered)
        self.assertEqual(dlg.answers, {PERFORMANCE: "critico", FUTURE: "punto"})

    def test_picking_again_in_the_same_question_replaces_the_answer(self) -> None:
        dlg = self.make()
        dlg._groups[PERFORMANCE]["critico"].setChecked(True)
        dlg._groups[PERFORMANCE]["cauto"].setChecked(True)
        dlg._answer()
        self.assertEqual(dlg.answers, {PERFORMANCE: "cauto"})

    def test_answering_with_nothing_chosen_is_the_same_as_no_comment(self) -> None:
        dlg = self.make()
        dlg._answer()
        self.assertFalse(dlg.answered)
        self.assertEqual(dlg.answers, {})

    def test_no_comment_leaves_it_unanswered(self) -> None:
        dlg = self.make()
        dlg._groups[PERFORMANCE]["critico"].setChecked(True)
        dlg.skip_btn.click()
        self.assertFalse(dlg.answered)


class TestMainWindowFlow(_Base):
    def setUp(self) -> None:
        super().setUp()
        self.win = MainWindow(self.ctrl)
        self.addCleanup(self.win.close)

    def run_flow(self, answered: bool, answers=None):
        fake = mock.MagicMock()
        fake.return_value.answered = answered
        fake.return_value.answers = answers or {}
        with mock.patch("views.main_window.RaceViewerDialog"), mock.patch("views.main_window.CompetitionResultsDialog"), \
                mock.patch("views.main_window.PressConferenceDialog", fake):
            self.win._show_competition_results(self.summary)
        return fake

    def test_after_the_results_the_conference_opens_and_its_answers_are_applied(self) -> None:
        fake = self.run_flow(True, {PERFORMANCE: "soddisfatto"})
        fake.return_value.exec.assert_called_once()
        self.assertEqual(self.state.reputation, 50 + PRESS_REPUTATION["good"]["soddisfatto"])

    def test_closing_the_conference_changes_nothing(self) -> None:
        self.run_flow(False)
        self.assertEqual(self.state.reputation, 50)

    def test_an_absent_club_opens_no_conference(self) -> None:
        self.summary.club_absent = True
        fake = self.run_flow(True, {PERFORMANCE: "soddisfatto"})
        fake.assert_not_called()


if __name__ == "__main__":
    unittest.main()
