"""Dashboard in QML (PIANOLAVORO G, scelta C), Qt offscreen: caricamento, errori, clic, ripiego, token del design system.

Il punto debole di QML è che gli errori sono **silenziosi** (un binding rotto stampa un avviso e `grab()` riesce lo stesso): qui ogni
avviso del motore e ogni messaggio Qt proveniente da un file `.qml` fa fallire il test. Non si prova la GPU (offscreen = backend
software) né il mouse reale.
"""

from __future__ import annotations

import os
import random
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("TEF_NO_GODOT", "1")

from PyQt6.QtCore import QPoint, QPointF, Qt, qInstallMessageHandler
from PyQt6.QtQuick import QQuickItem
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from controllers.game_controller import GameController
from models.database import DatabaseManager
from models.simulation import advance_week
from tests.support import start_game
from views import theme
from views.dashboard_qml import DashboardTab
from views.main_window import MainWindow
from views.qml_host import qml_dir, theme_tokens

_app = QApplication.instance() or QApplication([])


def _career(path: Path, seed: int = 3) -> GameController:
    ctrl = GameController(db_manager=DatabaseManager(db_path=path), rng=random.Random(seed), auto_create=False)
    start_game(ctrl, team_name="CUS Test", game_mode="career")
    return ctrl


def settle(ms: int = 300) -> None:
    """`Canvas` carica la sua texture in modo asincrono: serve un po' di ciclo eventi prima di `grab()`."""
    QTest.qWait(ms)


def walk(item: QQuickItem):
    yield item
    for child in item.childItems():
        yield from walk(child)


def find_items(root: QQuickItem, type_prefix: str):
    """Gli elementi QML di un tipo (il nome della classe C++ è «KpiCard_QMLTYPE_n»)."""
    return [i for i in walk(root) if i.metaObject().className().startswith(type_prefix + "_QMLTYPE")]


def center_in_widget(host, item: QQuickItem) -> QPoint:
    p = item.mapToScene(QPointF(item.width() / 2, item.height() / 2))
    return QPoint(int(p.x()), int(p.y()))


class QmlCase(unittest.TestCase):
    def setUp(self) -> None:
        self.messages: list[str] = []
        previous = qInstallMessageHandler(lambda _mode, ctx, msg: self.messages.append(msg) if (ctx.file or "").endswith(".qml") or "qml" in msg.lower() else None)
        self.addCleanup(qInstallMessageHandler, previous)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.ctrl = _career(Path(tmp.name) / "s.db")
        self.win = MainWindow(controller=self.ctrl)
        self.win.resize(1340, 900)
        self.win.show()
        self.addCleanup(self.win.close)
        self.dash = self.win.dashboard_tab

    def assertQmlClean(self) -> None:
        self.assertEqual(self.dash.qml.warnings, [])
        self.assertEqual(self.messages, [])


class TestLoading(QmlCase):
    def test_qml_is_used_and_loads_without_warnings(self) -> None:
        self.assertTrue(self.dash.uses_qml)
        self.assertFalse(self.dash.qml.failed)
        self.dash.refresh(self.ctrl.state)
        settle()
        self.assertQmlClean()

    def test_a_played_game_stays_clean_week_after_week(self) -> None:
        for _ in range(6):
            advance_week(self.ctrl.state, rng=self.ctrl.rng)
            self.ctrl.dismiss_dilemma()
            self.dash.refresh(self.ctrl.state)
            QTest.qWait(30)
        settle()
        self.assertQmlClean()
        self.assertEqual(len(self.dash.snapshot["trend"]["form"]), 6)

    def test_every_state_of_the_game_is_clean(self) -> None:
        state = self.ctrl.state
        for mutate in (
            lambda: setattr(state, "pending_dilemma", None),
            lambda: setattr(state, "budget", -3000),
            lambda: setattr(state, "board_failed_streak", 1),
            lambda: setattr(state, "fired", True),
            lambda: setattr(state, "athletes", []),
            lambda: setattr(state, "game_mode", "vertical_slice"),
        ):
            mutate()
            self.dash.refresh(state)
            QTest.qWait(30)
        settle()
        self.assertQmlClean()

    def test_it_really_paints(self) -> None:
        self.dash.refresh(self.ctrl.state)
        settle()
        img = self.dash.qml.grab().toImage()
        self.assertFalse(img.isNull())
        colors = {img.pixel(x, y) for x in range(0, img.width(), 11) for y in range(0, img.height(), 11)}
        self.assertGreater(len(colors), 8)
        accent = theme.qcolor(theme.ACCENT).rgb()
        self.assertTrue(any(img.pixel(x, y) == accent for x in range(0, img.width(), 2) for y in range(0, img.height(), 4)), "il turchese del design system non compare")

    def test_the_whole_window_still_paints_every_page(self) -> None:
        for i in range(self.win.tabs.count()):
            self.win._navigate_to(i)
            self.assertFalse(self.win.tabs.widget(i).grab().toImage().isNull())
        self.assertQmlClean()


class TestInteraction(QmlCase):
    def test_clicking_a_kpi_card_navigates(self) -> None:
        self.dash.refresh(self.ctrl.state)
        settle()
        got: list[int] = []
        self.dash.navigate_requested.connect(got.append)
        cards = find_items(self.dash.qml.rootObject(), "KpiCard")
        self.assertEqual(len(cards), 4)
        for card in cards:
            QTest.mouseClick(self.dash.qml, Qt.MouseButton.LeftButton, pos=center_in_widget(self.dash.qml, card))
        self.assertEqual(got, [7, 5, 1, 3])

    def test_clicking_a_priority_navigates_to_its_page(self) -> None:
        self.dash.refresh(self.ctrl.state)
        settle()
        got: list[int] = []
        self.dash.navigate_requested.connect(got.append)
        rows = find_items(self.dash.qml.rootObject(), "ActionRow")
        self.assertEqual(len(rows), len(self.dash.snapshot["actions"]))
        QTest.mouseClick(self.dash.qml, Qt.MouseButton.LeftButton, pos=center_in_widget(self.dash.qml, rows[0]))
        self.assertEqual(got, [self.dash.snapshot["actions"][0]["target"]])

    def test_double_click_on_an_athlete_row_opens_the_sheet(self) -> None:
        self.win.resize(1340, 2300)  # tutta la pagina visibile: il Flickable non deve scorrere per raggiungere la tabella
        self.dash.refresh(self.ctrl.state)
        settle()
        table = find_items(self.dash.qml.rootObject(), "TopTable")[0]
        first_row = table.mapToScene(QPointF(table.width() / 2, 30 + 1 + 20))  # intestazione 30 + filo 1 + metà riga
        pos = QPoint(int(first_row.x()), int(first_row.y()))
        opened: list[int] = []
        with mock.patch("views.dashboard_qml.AthleteDetailDialog") as dialog:
            dialog.side_effect = lambda ctrl, athlete_id, parent=None: opened.append(athlete_id) or mock.Mock(exec=lambda: 0)
            QTest.mouseDClick(self.dash.qml, Qt.MouseButton.LeftButton, pos=pos)
            QTest.qWait(80)
        self.assertEqual(opened, [self.dash.snapshot["top"]["rows"][0]["id"]])

    def test_the_trend_chart_reacts_to_hover_without_errors(self) -> None:
        for _ in range(4):
            advance_week(self.ctrl.state, rng=self.ctrl.rng)
            self.ctrl.dismiss_dilemma()
        self.dash.refresh(self.ctrl.state)
        settle()
        chart = find_items(self.dash.qml.rootObject(), "TrendChart")[0]
        pos = center_in_widget(self.dash.qml, chart)
        QTest.mouseMove(self.dash.qml, pos)
        QTest.mouseMove(self.dash.qml, QPoint(pos.x() + 40, pos.y()))
        settle(100)
        self.assertQmlClean()


class TestFallback(QmlCase):
    def test_a_scene_graph_failure_switches_to_the_widget_dashboard(self) -> None:
        self.dash.refresh(self.ctrl.state)
        got: list[int] = []
        self.dash.navigate_requested.connect(got.append)
        self.dash.qml.failed_signal.emit("grafo di scena non avviato: prova")
        self.assertFalse(self.dash.uses_qml)
        self.assertIsNotNone(self.dash._fallback)
        self.dash.refresh(self.ctrl.state)  # ora disegna la versione QWidget
        self.assertGreater(self.dash._fallback.top_table.rowCount(), 0)
        self.dash._fallback.navigate_requested.emit(3)
        self.assertEqual(got, [3])

    def test_the_fallback_is_refreshed_with_the_last_state_when_it_takes_over(self) -> None:
        self.dash.refresh(self.ctrl.state)
        self.dash.qml.failed_signal.emit("x")
        self.assertNotEqual(self.dash._fallback.squad_val.text(), "-")  # «-» è il valore di una scheda mai aggiornata

    def test_tef_no_qml_forces_the_widget_dashboard(self) -> None:
        with mock.patch.dict(os.environ, {"TEF_NO_QML": "1"}):
            tab = DashboardTab(self.ctrl)
        self.addCleanup(tab.close)
        self.assertFalse(tab.uses_qml)
        tab.refresh(self.ctrl.state)
        self.assertGreater(tab._fallback.top_table.rowCount(), 0)

    def test_a_broken_qml_file_falls_back_instead_of_raising(self) -> None:
        with mock.patch("views.dashboard_qml.QmlHost", side_effect=RuntimeError("boom")):
            tab = DashboardTab(self.ctrl)
        self.addCleanup(tab.close)
        self.assertFalse(tab.uses_qml)


class TestDesignSystem(unittest.TestCase):
    def test_tokens_are_the_ones_of_theme_py(self) -> None:
        t = theme_tokens(animations=False)
        for key, const in (("accent", theme.ACCENT), ("surface", theme.SURFACE), ("bad", theme.BAD), ("good", theme.GOOD), ("warn", theme.WARN), ("text", theme.TEXT)):
            self.assertEqual(t[key], const)
        self.assertEqual((t["sp4"], t["radiusLg"], t["fsXxl"]), (theme.SP_4, theme.RADIUS_LG, theme.FS_XXL))
        self.assertEqual(t["animScale"], 0.0)
        self.assertEqual(theme_tokens(animations=True)["animScale"], 1.0)

    def test_animations_are_off_on_the_offscreen_platform(self) -> None:
        self.assertEqual(theme_tokens()["animScale"], 0.0)  # test e screenshot non prendono fotogrammi a metà

    def test_qml_uses_only_what_the_software_backend_can_draw(self) -> None:
        """Gli effetti a shader non si vedono col backend software: senza questo controllo mancherebbero senza che nessuno se ne accorga."""
        banned = re.compile(r"\b(MultiEffect|ShaderEffect|DropShadow|Glow|GaussianBlur|FastBlur|OpacityMask|layer\.effect)\b")
        files = sorted(qml_dir().glob("*.qml"))
        self.assertGreaterEqual(len(files), 10)
        for f in files:
            code = re.sub(r"//.*", "", f.read_text(encoding="utf-8"))
            self.assertIsNone(banned.search(code), f"{f.name}: effetto a shader")

    def test_every_canvas_renders_to_an_image(self) -> None:
        """`Canvas` di default usa un FBO che il backend software non ha: serve `renderTarget: Canvas.Image`."""
        for f in sorted(qml_dir().glob("*.qml")):
            code = f.read_text(encoding="utf-8")
            if "Canvas {" in code:
                self.assertIn("renderTarget: Canvas.Image", code, f.name)

    def test_the_font_family_reaches_qml(self) -> None:
        self.assertTrue(theme_tokens()["fontFamily"])


if __name__ == "__main__":
    unittest.main()
