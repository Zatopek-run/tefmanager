"""Lotto A.5: «Avanza settimana» non è rientrante (nessuna doppia settimana da un secondo clic).

Il controller è un QObject, quindi serve PyQt6 (in modalità offscreen). Il doppio clic con il mouse vero non è
provato: qui si simula il rientro dall'interno di un segnale del tick, che è il punto in cui un dialogo modale
farebbe girare un ciclo di eventi annidato.
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


class TestAdvanceWeekGuard(unittest.TestCase):
    def _controller(self, tmpdir: str) -> GameController:
        return GameController(db_manager=DatabaseManager(db_path=Path(tmpdir) / "g.db"), rng=random.Random(7))

    def test_reentrant_call_during_tick_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ctrl = self._controller(tmpdir)
            start = ctrl.state.week
            inner_results = []
            seen_flag = []

            def reenter(_report) -> None:
                seen_flag.append(ctrl.is_advancing)
                inner_results.append(ctrl.advance_week())

            ctrl.week_advanced.connect(reenter)
            report = ctrl.advance_week()

            self.assertIsNotNone(report)
            self.assertEqual(inner_results, [None])
            self.assertEqual(seen_flag, [True])
            self.assertEqual(ctrl.state.week, start + 1)
            self.assertFalse(ctrl.is_advancing)

    def test_flag_is_released_when_the_tick_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ctrl = self._controller(tmpdir)
            with mock.patch("controllers.game_controller.advance_week", side_effect=RuntimeError("boom")):
                with self.assertRaises(RuntimeError):
                    ctrl.advance_week()
            self.assertFalse(ctrl.is_advancing)
            self.assertIsNotNone(ctrl.advance_week())  # la partita non resta bloccata

    def test_sequential_calls_still_advance_one_week_each(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ctrl = self._controller(tmpdir)
            start = ctrl.state.week
            ctrl.advance_week()
            ctrl.advance_week()
            self.assertEqual(ctrl.state.week, start + 2)


class TestAdvanceButton(unittest.TestCase):
    def test_button_is_disabled_during_the_tick_and_clicks_are_ignored(self) -> None:
        from views.main_window import MainWindow

        # Un dilemma a metà prova aprirebbe un dialogo modale (blocca per sempre offscreen): qui non c'entra.
        no_dilemma = mock.patch("models.simulation.maybe_generate_dilemma", return_value=None)
        no_dilemma.start()
        self.addCleanup(no_dilemma.stop)

        with tempfile.TemporaryDirectory() as tmpdir:
            ctrl = GameController(
                db_manager=DatabaseManager(db_path=Path(tmpdir) / "ui.db"), rng=random.Random(7)
            )
            win = MainWindow(controller=ctrl)
            start = ctrl.state.week
            during = []

            def on_tick(_report) -> None:
                during.append(win.advance_btn.isEnabled())
                win.advance_btn.click()  # un secondo clic a metà tick: il pulsante è spento, non fa nulla
                during.append(ctrl.state.week)

            ctrl.week_advanced.connect(on_tick)
            win.advance_btn.click()

            self.assertEqual(during[0], False)
            self.assertEqual(ctrl.state.week, start + 1)
            self.assertTrue(win.advance_btn.isEnabled())  # riabilitato a tick finito
            win.close()


if __name__ == "__main__":
    unittest.main()
