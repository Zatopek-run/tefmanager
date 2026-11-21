"""Dashboard potenziata (PIANOLAVORO G.1), Qt offscreen: widget grafici, semaforo, tabella dei migliori, timeline.

Non si prova il mouse reale e non si giudica l'aspetto (per quello: screenshot a occhio): si controlla che le viste si
disegnino davvero, che la geometria sia quella giusta e che lo stato si rifletta nei widget.
"""

from __future__ import annotations

import os
import random
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("TEF_NO_GODOT", "1")

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication, QPushButton

from controllers.game_controller import GameController
from models.dashboard import heat_map, season_timeline
from models.database import DatabaseManager
from models.entities import EthicalDilemma, HISTORY_WEEKS
from models.simulation import advance_week
from tests.support import start_game
from views import theme
from views.main_window import MainWindow
from views.widgets import (
    BADGE_LEVEL_ROLE,
    HeatMapWidget,
    SeasonTimelineWidget,
    StatusPill,
    TrendChart,
    check_icon,
    heat_color,
    line_points,
    nearest_index,
    readable_on,
    short_event_name,
)

_app = QApplication.instance() or QApplication([])


def _career(path: Path, seed: int = 3) -> GameController:
    ctrl = GameController(db_manager=DatabaseManager(db_path=path), rng=random.Random(seed), auto_create=False)
    start_game(ctrl, team_name="CUS Test", game_mode="career")
    return ctrl


class TestGeometry(unittest.TestCase):
    def test_line_points_span_the_plot_and_invert_y(self) -> None:
        pts = line_points([0, 50, 100], left=10, top=20, width=200, height=100)
        self.assertEqual(pts[0], (10, 120))  # 0 in basso a sinistra
        self.assertEqual(pts[1], (110, 70))
        self.assertEqual(pts[2], (210, 20))  # 100 in alto a destra

    def test_line_points_clamp_and_single_point(self) -> None:
        self.assertEqual(line_points([150], 0, 0, 100, 100), [(50.0, 0.0)])  # un punto sta al centro, valore tagliato a 100
        self.assertEqual(line_points([], 0, 0, 100, 100), [])

    def test_nearest_index(self) -> None:
        self.assertEqual(nearest_index(0, 10, 200, 5), 0)
        self.assertEqual(nearest_index(10 + 200, 10, 200, 5), 4)
        self.assertEqual(nearest_index(10 + 100, 10, 200, 5), 2)
        self.assertEqual(nearest_index(-999, 10, 200, 5), 0)
        self.assertEqual(nearest_index(999, 10, 200, 5), 4)
        self.assertEqual(nearest_index(5, 10, 200, 1), 0)

    def test_short_event_names(self) -> None:
        self.assertEqual(short_event_name("100m"), "100m")
        self.assertEqual(short_event_name("Salto in Lungo"), "Lungo")
        self.assertEqual(short_event_name("Getto del Peso"), "Peso")

    def test_heat_colors_are_distinct_and_text_is_readable(self) -> None:
        cold, mid, hot = heat_color(0.0), heat_color(0.5), heat_color(1.0)
        self.assertEqual(len({cold.name(), mid.name(), hot.name()}), 3)
        self.assertEqual(readable_on(QColor("#fbbf24")).name(), QColor("#0a0f1f").name())  # scuro su chiaro
        self.assertEqual(readable_on(QColor("#262c63")).name(), QColor(theme.TEXT).name())  # chiaro su scuro

    def test_check_icon_has_two_states(self) -> None:
        done, todo = check_icon(True).pixmap(18, 18).toImage(), check_icon(False).pixmap(18, 18).toImage()
        self.assertNotEqual(done, todo)
        self.assertFalse(done.isNull())


class TestWidgets(unittest.TestCase):
    def test_status_pill_levels(self) -> None:
        pill = StatusPill()
        for level in ("ok", "warn", "danger"):
            pill.set_level(level, "x")
            self.assertEqual(pill.level, level)
            self.assertEqual(pill.property("level"), level)

    def test_trend_chart_paints_empty_one_point_and_many(self) -> None:
        chart = TrendChart()
        chart.resize(600, 220)
        for form, fat in (([], []), ([50], [20]), ([40 + i for i in range(HISTORY_WEEKS)], [20 + i for i in range(HISTORY_WEEKS)])):
            chart.set_series(form, fat)
            img = chart.grab().toImage()
            self.assertFalse(img.isNull())
        colors = {img.pixel(x, y) for x in range(0, 600, 5) for y in range(0, 220, 5)}
        self.assertGreater(len(colors), 3)  # non è un rettangolo uniforme: griglia e linee ci sono

    def test_heat_map_cells_map_to_hits(self) -> None:
        from tests.test_assignments import make_state

        state = make_state(3)
        hm = heat_map(state)
        widget = HeatMapWidget()
        widget.resize(700, 400)
        widget.set_heat_map(hm)
        for r in (0, len(hm.athletes) - 1):
            for c in (0, len(hm.events) - 1):
                centre = widget.cell_rect(r, c).center()
                self.assertEqual(widget.cell_at(centre.x(), centre.y()), (r, c))
        self.assertIsNone(widget.cell_at(1, 1))  # sulla colonna dei nomi
        self.assertFalse(widget.grab().toImage().isNull())
        widget.set_heat_map(None)
        self.assertIsNone(widget.cell_at(300, 100))
        self.assertFalse(widget.grab().toImage().isNull())

    def test_timeline_cells_do_not_overlap_and_paint(self) -> None:
        from tests.test_assignments import make_state

        state = make_state(3)
        widget = SeasonTimelineWidget()
        widget.resize(900, 90)
        tl = season_timeline(state)
        widget.set_timeline(tl, ["Outdoor", "Cross", "Indoor"])
        xs = [widget.cell_x(i) for i in range(len(tl.weeks))]
        for (x1, w1), (x2, _w2) in zip(xs, xs[1:]):
            self.assertLessEqual(x1 + w1, x2)
        self.assertLessEqual(xs[-1][0] + xs[-1][1], 900)
        self.assertFalse(widget.grab().toImage().isNull())
        widget.set_timeline(None)
        self.assertFalse(widget.grab().toImage().isNull())


class TestDashboard(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.ctrl = _career(Path(tmp.name) / "s.db")
        self.win = MainWindow(controller=self.ctrl)
        self.addCleanup(self.win.close)
        self.dash = self.win.dashboard_tab

    def refresh(self) -> None:
        self.dash.refresh(self.ctrl.state)

    def test_a_fresh_game_shows_the_empty_trend_and_a_full_heat_map(self) -> None:
        self.refresh()
        self.assertEqual(self.dash.trend_chart._form, [])  # nessuno storico prima del primo tick
        self.assertIsNotNone(self.dash.heat_map_widget._hm)
        self.assertEqual(self.dash.timeline._tl.current, 1)
        self.dash.grab()

    def test_the_trend_fills_up_while_playing(self) -> None:
        for _ in range(3):
            advance_week(self.ctrl.state, rng=self.ctrl.rng)
            self.ctrl.dismiss_dilemma()
        self.refresh()
        self.assertEqual(len(self.dash.trend_chart._form), 3)
        self.assertEqual(len(self.dash.trend_chart._fatigue), 3)
        self.dash.grab()

    def test_the_traffic_light(self) -> None:
        state = self.ctrl.state
        state.pending_dilemma = None
        self.refresh()
        items = [b for b in self.dash.findChildren(QPushButton, "ActionItemButton")]
        severities = {b.property("severity") for b in items}
        expected = "danger" if "danger" in severities else ("warn" if "warn" in severities else "ok")
        self.assertEqual(self.dash.status_pill.level, expected)
        # un dilemma pendente rende il semaforo rosso, anche senza altre urgenze
        state.pending_dilemma = EthicalDilemma(id="d1", title="t", description="d", accept_label="Sì", reject_label="No")
        self.refresh()
        self.assertEqual(self.dash.status_pill.level, "danger")
        self.assertIn("Dilemma", self.dash.status_pill.text())
        state.pending_dilemma = None

    def test_refreshing_twice_leaves_one_button_per_priority(self) -> None:
        self.refresh()
        self.refresh()
        self.assertEqual(
            len(self.dash.findChildren(QPushButton, "ActionItemButton")), self.dash.actions_box.count()
        )

    def test_the_top_table_is_complete_and_uses_badges(self) -> None:
        self.refresh()
        table = self.dash.top_table
        headers = [table.horizontalHeaderItem(i).text() for i in range(table.columnCount())]
        self.assertEqual(headers, ["Atleta", "Disciplina", "OVR", "Forma", "Fatica", "Stato"])
        self.assertLessEqual(table.rowCount(), self.dash.TOP_ATHLETES)
        for row in range(table.rowCount()):
            self.assertIn(table.item(row, 5).data(BADGE_LEVEL_ROLE), ("ok", "warn", "danger"))
            self.assertNotIn("...", table.item(row, 5).text())  # lo stato non è mai abbreviato
        self.assertGreaterEqual(table.height(), table.rowCount() * self.dash.TOP_ROW_H)

    def test_objectives_have_real_check_icons(self) -> None:
        self.refresh()
        lst = self.dash.objectives_list
        self.assertGreater(lst.count(), 0)
        for i in range(lst.count()):
            self.assertFalse(lst.item(i).icon().isNull())
            self.assertNotIn("[", lst.item(i).text())  # niente più «[ ]» né «[COMPLETATO]»

    def test_the_contracts_label_lists_the_expiring_ones(self) -> None:
        state = self.ctrl.state
        for a in state.main_squad:
            a.contract_end_season = state.season_number + 3
        state.main_squad[0].contract_end_season = state.season_number
        self.refresh()
        self.assertIn(state.main_squad[0].name, self.dash.contracts_label.text())
        state.main_squad[0].contract_end_season = state.season_number + 3
        self.refresh()
        self.assertEqual(self.dash.contracts_label.text(), "")

    def test_the_prototype_has_no_season_timeline(self) -> None:
        self.refresh()
        self.assertFalse(self.dash.timeline.isHidden())
        self.ctrl.state.game_mode = "vertical_slice"
        self.refresh()
        self.assertTrue(self.dash.timeline.isHidden())  # il Prototipo dura 8 settimane: la timeline di 36 sarebbe fuorviante
        self.assertEqual(self.dash.contracts_label.text(), "")

    def test_the_empty_trend_says_why(self) -> None:
        self.refresh()
        self.assertIn("avanza la prima settimana", self.dash.trend_chart._empty_text)
        self.ctrl.state.athletes = []
        self.refresh()
        self.assertIn("Nessun atleta", self.dash.trend_chart._empty_text)
        self.dash.grab()

    def test_the_whole_window_paints_every_page(self) -> None:
        for i in range(self.win.tabs.count()):
            self.win._navigate_to(i)
            self.assertFalse(self.win.tabs.widget(i).grab().toImage().isNull())


if __name__ == "__main__":
    unittest.main()
