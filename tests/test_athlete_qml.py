"""Scheda atleta, parte grafica in QML (PIANOLAVORO G.2, scelta C), Qt offscreen: caricamento senza avvisi, dati, ripiego, parità dei livelli.

Come per la Dashboard: ogni avviso del motore QML e ogni messaggio Qt proveniente da un file `.qml` fa fallire il test.
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

from PyQt6.QtCore import qInstallMessageHandler
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from controllers.game_controller import GameController
from models.athlete_view import athlete_snapshot, stat_level
from models.database import DatabaseManager
from models.simulation import advance_week
from tests.support import start_game
from views.athlete_dialog import AthleteDetailDialog, stat_colors

_app = QApplication.instance() or QApplication([])


def _career(path: Path, seed: int = 3) -> GameController:
    ctrl = GameController(db_manager=DatabaseManager(db_path=path), rng=random.Random(seed), auto_create=False)
    start_game(ctrl, team_name="CUS Test", game_mode="career")
    return ctrl


class AthleteQmlCase(unittest.TestCase):
    def setUp(self) -> None:
        self.messages: list[str] = []
        previous = qInstallMessageHandler(lambda _m, ctx, msg: self.messages.append(msg) if (ctx.file or "").endswith(".qml") or "qml" in msg.lower() else None)
        self.addCleanup(qInstallMessageHandler, previous)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.ctrl = _career(Path(tmp.name) / "s.db")
        self.athlete = max(self.ctrl.state.main_squad, key=lambda a: a.overall)

    def open_dialog(self) -> AthleteDetailDialog:
        dlg = AthleteDetailDialog(self.ctrl, self.athlete.id)
        dlg.resize(980, 860)
        dlg.show()
        self.addCleanup(dlg.close)
        QTest.qWait(300)
        return dlg


class TestDialogWithQml(AthleteQmlCase):
    def test_qml_loads_clean_and_shows_the_athlete_snapshot(self) -> None:
        dlg = self.open_dialog()
        view = dlg._stats_view
        self.assertFalse(view.failed)
        self.assertEqual(view.qml.warnings, [])
        self.assertEqual(self.messages, [])
        self.assertEqual(view.snapshot, athlete_snapshot(self.ctrl.state, self.athlete))

    def test_it_really_paints(self) -> None:
        dlg = self.open_dialog()
        img = dlg._stats_view.qml.grab().toImage()
        self.assertFalse(img.isNull())
        colors = {img.pixel(x, y) for x in range(0, img.width(), 9) for y in range(0, img.height(), 9)}
        self.assertGreater(len(colors), 8)

    def test_refresh_updates_the_view_and_keeps_the_same_qml_instance(self) -> None:
        dlg = self.open_dialog()
        view = dlg._stats_view
        before = view.snapshot["condition"]
        for _ in range(4):
            advance_week(self.ctrl.state, rng=self.ctrl.rng)
            self.ctrl.dismiss_dilemma()
        dlg.refresh()
        QTest.qWait(150)
        self.assertIs(dlg._stats_view, view)  # una sola vista QML per dialogo: non si ricrea a ogni refresh
        self.assertNotEqual(view.snapshot["condition"], before)
        self.assertEqual(view.snapshot, athlete_snapshot(self.ctrl.state, self.athlete))
        self.assertEqual(view.qml.warnings, [])
        self.assertEqual(self.messages, [])

    def test_the_results_chart_gets_the_played_races(self) -> None:
        for _ in range(8):
            advance_week(self.ctrl.state, rng=self.ctrl.rng)
            self.ctrl.dismiss_dilemma()
        raced = next((a for a in self.ctrl.state.main_squad if a.history.get("results")), None)
        self.assertIsNotNone(raced)
        self.athlete = raced
        dlg = self.open_dialog()
        perf = dlg._stats_view.snapshot["performance"]
        self.assertEqual(len(perf["points"]), len(raced.history["results"]))
        QTest.qWait(150)
        self.assertEqual(dlg._stats_view.qml.warnings, [])

    def test_the_records_card_shows_the_progression_without_warnings(self) -> None:
        from models.personal_bests import record_best

        for i, v in enumerate((11.6, 11.4, 11.0)):
            record_best(self.athlete, "100m", v, f"{v:.2f}s", 1, 4 * (i + 1), f"Meeting {i}")
        record_best(self.athlete, "Salto in Lungo", 6.2, "6.20m", 1, 8, "Meeting 1")
        dlg = self.open_dialog()
        items = dlg._stats_view.snapshot["records"]["items"]
        self.assertEqual([i["event"] for i in items], ["100m", "Salto in Lungo"])
        QTest.qWait(300)  # il Canvas carica la texture in modo asincrono
        img = dlg._stats_view.qml.grab().toImage()
        self.assertFalse(img.isNull())
        self.assertEqual(dlg._stats_view.qml.warnings, [])
        self.assertEqual(self.messages, [])

    def test_every_athlete_opens_clean(self) -> None:
        for a in self.ctrl.state.athletes[:6]:
            self.athlete = a
            dlg = self.open_dialog()
            self.assertEqual(dlg._stats_view.qml.warnings, [], a.name)
            dlg.close()
        self.assertEqual(self.messages, [])


class TestFallback(AthleteQmlCase):
    def test_tef_no_qml_keeps_the_old_three_columns(self) -> None:
        with mock.patch.dict(os.environ, {"TEF_NO_QML": "1"}):
            dlg = AthleteDetailDialog(self.ctrl, self.athlete.id)
        self.addCleanup(dlg.close)
        self.assertTrue(dlg._stats_view.failed)
        from views.athlete_dialog import _StatColumn

        self.assertEqual(len(dlg.overview_page.findChildren(_StatColumn)), 3)

    def test_a_qml_failure_after_creation_uses_the_columns_at_the_next_refresh(self) -> None:
        dlg = self.open_dialog()
        dlg._stats_view.qml.failed_signal.emit("grafo di scena non avviato: prova")
        self.assertTrue(dlg._stats_view.failed)
        dlg.refresh()
        from views.athlete_dialog import _StatColumn

        self.assertEqual(len(dlg.overview_page.findChildren(_StatColumn)), 3)

    def test_the_dialog_with_qml_has_no_old_columns(self) -> None:
        dlg = self.open_dialog()
        from views.athlete_dialog import _StatColumn

        self.assertEqual(dlg.overview_page.findChildren(_StatColumn), [])


class TestLevelsParity(unittest.TestCase):
    def test_the_new_levels_follow_the_old_badge_colors(self) -> None:
        """Stessa scala del badge a colori di prima (80 / 65 / 45): il livello decide il colore, qui e nel vecchio widget."""
        by_color = {}
        for v in range(0, 101):
            by_color.setdefault(stat_colors(v)[0], set()).add(stat_level(v))
            by_color.setdefault(stat_colors(v, invert=True)[0], set())
        for colour, levels in by_color.items():
            self.assertLessEqual(len(levels), 1, f"{colour}: {levels}")
        for v in range(0, 101):
            for inv in (False, True):
                self.assertEqual(stat_colors(v, inv)[0] == stat_colors(100 if not inv else 0, inv)[0], stat_level(v, inv) == "great")


if __name__ == "__main__":
    unittest.main()
