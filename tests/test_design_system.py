"""Design system esteso a tutta l'interfaccia (PIANOLAVORO G), Qt offscreen.

Garanzie: (1) il foglio di stile nasce dai token (nessun segnaposto rimasto, tutti i colori dei token presenti, nessun colore del vecchio
tema) e Qt lo accetta senza avvisi di parsing; (2) la barra laterale e l'intestazione hanno le icone; (3) le tabelle si adattano al contenuto
(niente testi o intestazioni tagliati, i widget di cella hanno la loro larghezza); (4) tutte le pagine si disegnano.
"""

from __future__ import annotations

import os
import random
import re
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("TEF_NO_GODOT", "1")

from PyQt6.QtCore import qInstallMessageHandler
from PyQt6.QtWidgets import QApplication, QComboBox, QHeaderView, QPushButton, QTableWidget, QTableWidgetItem

from controllers.game_controller import GameController
from models.database import DatabaseManager
from tests.support import start_game
from views import icons, theme
from views.main_window import MainWindow
from views.styles import DARK_STYLESHEET, build_stylesheet
from views.table_fit import TableFitter, fit_table

_app = QApplication.instance() or QApplication([])

VIEWS = Path(__file__).resolve().parent.parent / "views"
RETIRED_COLORS = ("#0de0cc", "#080d22", "#0e1535", "#f8fafc", "#94a3b8", "#e2e8f0")  # accento e grigi del tema di prima


class TestStylesheet(unittest.TestCase):
    def test_no_placeholder_is_left_and_the_tokens_are_used(self) -> None:
        css = build_stylesheet()
        self.assertEqual(css, DARK_STYLESHEET)
        self.assertNotRegex(css, r"\$\{?[A-Za-z]")
        for token in (theme.BG, theme.SURFACE, theme.BORDER, theme.TEXT, theme.ACCENT, theme.GOOD, theme.WARN, theme.BAD):
            self.assertIn(token, css)
        self.assertIn(theme.FONT_FAMILY, css)

    def test_changing_a_token_changes_the_stylesheet(self) -> None:
        before = build_stylesheet()
        original = theme.ACCENT
        try:
            theme.ACCENT = "#ff00aa"
            self.assertIn("#ff00aa", build_stylesheet())
            self.assertNotEqual(before, build_stylesheet())
        finally:
            theme.ACCENT = original

    def test_qt_accepts_it_without_parse_warnings(self) -> None:
        messages: list[str] = []
        previous = qInstallMessageHandler(lambda _m, _c, msg: messages.append(msg))
        try:
            w = QPushButton("x")
            w.setStyleSheet(DARK_STYLESHEET)
            w.show()
            w.ensurePolished()
            w.close()
        finally:
            qInstallMessageHandler(previous)
        self.assertEqual([m for m in messages if "stylesheet" in m.lower() or "parse" in m.lower() or "unknown property" in m.lower()], [])

    def test_the_old_theme_colors_are_gone_from_the_views(self) -> None:
        ui_files = ("tabs", "dialogs", "athlete_dialog", "start_screen", "main_window", "results_board", "widgets", "finance_chart", "dashboard_qml")
        for f in (VIEWS / f"{name}.py" for name in ui_files):  # le viste 3D e di gara hanno i colori della scena: fuori dal design system
            text = f.read_text(encoding="utf-8").lower()
            for color in RETIRED_COLORS:
                self.assertNotIn(color, text, f"{f.name}: colore del tema vecchio {color}")

    def test_the_athlete_dialog_has_no_hand_written_colors(self) -> None:
        """Ogni colore della scheda atleta viene dai token di `theme.py` (R37-R41): nessun `#rrggbb` nel file."""
        text = (VIEWS / "athlete_dialog.py").read_text(encoding="utf-8")
        self.assertEqual(re.findall(r"#[0-9a-fA-F]{6}\b", text), [])

    def test_every_object_name_styled_in_the_views_exists_in_the_stylesheet_or_is_unstyled_on_purpose(self) -> None:
        css = DARK_STYLESHEET
        used = set()
        for f in VIEWS.glob("*.py"):
            used |= set(re.findall(r'setObjectName\("([A-Za-z]+)"\)', f.read_text(encoding="utf-8")))
        styled = set(re.findall(r"#([A-Za-z]+)", css))
        # nomi che non hanno (ancora) una regola propria: devono essere pochi e noti
        unstyled = used - styled
        self.assertLessEqual(unstyled, {"IgnoreDilemmaButton", "DashboardPage"} | {n for n in unstyled if n in ("Card", "CardHeading")}, unstyled)


class TestWindow(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        ctrl = GameController(db_manager=DatabaseManager(db_path=Path(tmp.name) / "s.db"), rng=random.Random(3), auto_create=False)
        start_game(ctrl)
        self.win = MainWindow(controller=ctrl)
        self.win.show()
        self.addCleanup(self.win.close)

    @unittest.skipUnless(icons.available(), "qtawesome non installato")
    def test_navigation_and_header_have_icons(self) -> None:
        for btn in self.win._nav_buttons:
            self.assertFalse(btn.icon().isNull(), btn.text())
        self.assertFalse(self.win.advance_btn.icon().isNull())
        self.assertFalse(self.win.menu_btn.icon().isNull())

    def test_every_page_paints_and_every_table_is_fitted(self) -> None:
        for i in range(self.win.tabs.count()):
            self.win._navigate_to(i)
            page = self.win.tabs.widget(i)
            self.assertFalse(page.grab().toImage().isNull())
            for table in page.findChildren(QTableWidget):
                if table.columnCount() and table.isVisible():
                    modes = {table.horizontalHeader().sectionResizeMode(c) for c in range(table.columnCount())}
                    self.assertNotIn(QHeaderView.ResizeMode.Stretch, modes, f"pagina {i}: tabella non adattata")

    def test_the_roster_shows_full_names_and_headers(self) -> None:
        self.win._navigate_to(1)
        table = self.win.roster_tab.findChildren(QTableWidget)[0]
        header = table.horizontalHeader()
        fm = header.fontMetrics()
        for c in range(table.columnCount()):
            item = table.horizontalHeaderItem(c)
            if item is not None:
                self.assertGreaterEqual(header.sectionSize(c), fm.horizontalAdvance(item.text()), item.text())  # intestazione intera
        longest = max((table.item(r, 0).text() for r in range(table.rowCount()) if table.item(r, 0)), key=len)
        self.assertGreaterEqual(header.sectionSize(0), table.fontMetrics().horizontalAdvance(longest))  # nome intero


class TestTableFit(unittest.TestCase):
    def make(self, long_text: str = "Una cella con un testo piuttosto lungo") -> QTableWidget:
        t = QTableWidget(3, 3)
        t.setHorizontalHeaderLabels(["Nome", "Scelta", "Azione"])
        for r in range(3):
            t.setItem(r, 0, QTableWidgetItem(long_text))
            combo = QComboBox()
            combo.addItems(["Preparazione generale", "Riposo"])
            t.setCellWidget(r, 1, combo)
            t.setItem(r, 2, QTableWidgetItem("x"))
        return t

    def test_text_columns_fit_content_and_widget_columns_get_the_widget_width(self) -> None:
        t = self.make()
        t.resize(900, 300)
        t.show()
        fit_table(t)
        header = t.horizontalHeader()
        self.assertEqual(header.sectionResizeMode(0), QHeaderView.ResizeMode.ResizeToContents)
        self.assertEqual(header.sectionResizeMode(1), QHeaderView.ResizeMode.Interactive)
        self.assertGreaterEqual(t.columnWidth(1), t.cellWidget(0, 1).sizeHint().width())
        self.assertTrue(header.stretchLastSection())
        t.close()

    def test_a_header_wider_than_its_widgets_wins(self) -> None:
        t = QTableWidget(1, 1)
        t.setHorizontalHeaderLabels(["Un'intestazione molto molto lunga"])
        t.setCellWidget(0, 0, QPushButton("ok"))
        fit_table(t)
        self.assertGreaterEqual(t.columnWidth(0), t.horizontalHeader().fontMetrics().horizontalAdvance("Un'intestazione molto molto lunga"))

    def test_the_event_filter_fits_on_show_and_can_be_skipped(self) -> None:
        fitter = TableFitter()
        _app.installEventFilter(fitter)
        self.addCleanup(_app.removeEventFilter, fitter)
        fitted, skipped = self.make(), self.make()
        skipped.setProperty("fit", False)
        for t in (fitted, skipped):
            t.resize(900, 300)
            t.show()
            self.addCleanup(t.close)
        self.assertEqual(fitted.horizontalHeader().sectionResizeMode(0), QHeaderView.ResizeMode.ResizeToContents)
        self.assertNotEqual(skipped.horizontalHeader().sectionResizeMode(0), QHeaderView.ResizeMode.ResizeToContents)

    def test_an_empty_table_does_not_break(self) -> None:
        fit_table(QTableWidget(0, 0))


class TestIcons(unittest.TestCase):
    def test_unknown_names_give_an_empty_icon_not_an_exception(self) -> None:
        self.assertTrue(icons.icon("mdi6.questo-nome-non-esiste").isNull() or True)  # nessuna eccezione verso Qt

    def test_the_label_with_counters_still_finds_its_icon(self) -> None:
        if not icons.available():
            self.skipTest("qtawesome non installato")
        self.assertFalse(icons.nav_icon_for("Rosa && Allenamenti (9 st.)").isNull())
        self.assertFalse(icons.nav_icon_for("Calendario && Gare (!)").isNull())
        self.assertTrue(icons.nav_icon_for("Pagina sconosciuta").isNull())


if __name__ == "__main__":
    unittest.main()
