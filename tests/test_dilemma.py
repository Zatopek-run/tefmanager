"""Lotto A.4: un dilemma chiuso senza scelta non resta pendente e non blocca più i successivi.

Il controller è un QObject, quindi serve PyQt6 (offscreen). I dialoghi non si aprono con `exec()` (bloccherebbe per
sempre): si istanziano e si chiamano i metodi, oppure si sostituiscono con finti.
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
from models.database import DatabaseManager

_app = QApplication.instance() or QApplication([])


def _controller(tmpdir: str, seed: int = 7) -> GameController:
    return GameController(db_manager=DatabaseManager(db_path=Path(tmpdir) / "d.db"), rng=random.Random(seed))


def _advance_until_dilemma(ctrl: GameController, limit: int = 12) -> None:
    for _ in range(limit):
        if ctrl.state.pending_dilemma is not None:
            return
        ctrl.advance_week()
    raise AssertionError("nessun dilemma generato")


class TestDismissDilemma(unittest.TestCase):
    def test_dismiss_has_no_effect_on_money_reputation_or_prestige(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ctrl = _controller(tmpdir)
            _advance_until_dilemma(ctrl)
            s = ctrl.state
            before = (s.budget, s.reputation, s.prestige, [(a.fatigue, a.form, a.resilience) for a in s.athletes])
            news_before = len(s.news_log)

            self.assertTrue(ctrl.dismiss_dilemma())

            self.assertIsNone(s.pending_dilemma)
            after = (s.budget, s.reputation, s.prestige, [(a.fatigue, a.form, a.resilience) for a in s.athletes])
            self.assertEqual(before, after)
            self.assertEqual(len(s.news_log), news_before + 1)
            self.assertIn("ignorato", s.news_log[0])

    def test_dismiss_without_pending_dilemma_does_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ctrl = _controller(tmpdir)
            news = list(ctrl.state.news_log)
            self.assertFalse(ctrl.dismiss_dilemma())
            self.assertEqual(ctrl.state.news_log, news)

    def test_dismiss_differs_from_reject(self) -> None:
        """Rifiutare dà un premio (reputazione/prestigio o forma): ignorare non deve darlo."""
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            ignored, rejected = _controller(d1), _controller(d2)
            _advance_until_dilemma(ignored)
            _advance_until_dilemma(rejected)
            ignored.dismiss_dilemma()
            rejected.resolve_dilemma(accepted=False)
            i, r = ignored.state, rejected.state
            self.assertNotEqual(
                (i.reputation, i.prestige, [a.form for a in i.athletes], [a.resilience for a in i.athletes]),
                (r.reputation, r.prestige, [a.form for a in r.athletes], [a.resilience for a in r.athletes]),
            )


class TestPendingDilemmaNoLongerBlocks(unittest.TestCase):
    def test_pending_dilemma_is_dismissed_by_the_next_tick_and_new_ones_appear(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ctrl = _controller(tmpdir)
            _advance_until_dilemma(ctrl)
            first = ctrl.state.pending_dilemma
            self.assertIsNotNone(first)
            first_week = ctrl.state.week

            # Il giocatore non sceglie mai: prima della correzione il dilemma restava pendente per sempre.
            seen = {id(first)}
            for _ in range(20):
                ctrl.advance_week()
                d = ctrl.state.pending_dilemma
                if d is not None and id(d) not in seen:
                    self.assertGreater(ctrl.state.week, first_week)
                    return
            self.fail("nessun nuovo dilemma dopo 20 settimane: il dilemma pendente blocca ancora i successivi")

    def test_tick_with_pending_dilemma_leaves_a_news_note(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ctrl = _controller(tmpdir)
            _advance_until_dilemma(ctrl)
            title = ctrl.state.pending_dilemma.title
            ctrl.advance_week()
            self.assertTrue(any("ignorato" in n and title in n for n in ctrl.state.news_log))


class TestDilemmaDialog(unittest.TestCase):
    def _dialog(self):
        from views.dialogs import EthicalDilemmaDialog

        with tempfile.TemporaryDirectory() as tmpdir:
            ctrl = _controller(tmpdir)
            _advance_until_dilemma(ctrl)
            return EthicalDilemmaDialog(ctrl.state.pending_dilemma)

    def test_closing_the_window_is_not_a_choice(self) -> None:
        dlg = self._dialog()
        dlg.reject()  # X o Esc
        self.assertFalse(dlg.chose)

    def test_ignore_button_is_not_a_choice(self) -> None:
        dlg = self._dialog()
        dlg.ignore_btn.click()
        self.assertFalse(dlg.chose)

    def test_accept_and_reject_are_choices(self) -> None:
        for method, expected in (("_choose_accept", True), ("_choose_reject", False)):
            dlg = self._dialog()
            getattr(dlg, method)()
            self.assertTrue(dlg.chose)
            self.assertEqual(dlg.accepted_shortcut, expected)


class TestMainWindowDilemmaFlow(unittest.TestCase):
    def test_closed_dialog_dismisses_instead_of_leaving_it_pending(self) -> None:
        from views.main_window import MainWindow

        class ClosedDialog:
            chose = False
            accepted_shortcut = False

            def __init__(self, *_a, **_k) -> None:
                pass

            def exec(self) -> int:
                return 0

        with tempfile.TemporaryDirectory() as tmpdir:
            ctrl = _controller(tmpdir)
            # Prima si avanza senza finestra: una settimana di gara aprirebbe dialoghi modali con exec() (bloccherebbe).
            _advance_until_dilemma(ctrl)
            win = MainWindow(controller=ctrl)
            dilemma = ctrl.state.pending_dilemma
            with mock.patch("views.main_window.EthicalDilemmaDialog", ClosedDialog):
                win._show_dilemma(dilemma)
            self.assertIsNone(ctrl.state.pending_dilemma)
            win.close()


if __name__ == "__main__":
    unittest.main()
