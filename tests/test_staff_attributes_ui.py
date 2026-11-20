"""Lotto E.1 (parte con Qt offscreen): scheda «Staff & Impianto» con gli attributi e salvataggio dal controller.

Non si prova il mouse reale: si legge la tabella e si chiama `toggle_staff` come farebbe il pulsante.
"""

from __future__ import annotations

import os
import random
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("TEF_NO_GODOT", "1")

from PyQt6.QtWidgets import QApplication

from controllers.game_controller import GameController
from models.database import DatabaseManager
from models.entities import STAFF_ATTR_REF, StaffRole
from tests.support import start_game
from views.main_window import MainWindow

_app = QApplication.instance() or QApplication([])


class TestStaffAttributesUi(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "s.db"
        self.ctrl = GameController(db_manager=DatabaseManager(db_path=self.path), rng=random.Random(3), auto_create=False)
        start_game(self.ctrl, team_name="CUS Test", game_mode="career")
        self.win = MainWindow(self.ctrl)
        self.addCleanup(self.win.close)

    def test_the_staff_table_shows_the_attributes_of_every_member(self) -> None:
        table = self.win.staff_tab.table
        self.assertEqual(table.rowCount(), 3)
        headers = [table.horizontalHeaderItem(c).text() for c in range(table.columnCount())]
        self.assertIn("Attributi (1-20)", headers)
        col = headers.index("Attributi (1-20)")
        texts = [table.item(row, col).text() for row in range(table.rowCount())]
        self.assertIn(f"Competenza infortuni {STAFF_ATTR_REF} · Velocità recupero {STAFF_ATTR_REF}", texts)
        self.assertIn(f"Diagnosi {STAFF_ATTR_REF} · Prevenzione {STAFF_ATTR_REF}", texts)
        self.assertIn(f"Motivazione {STAFF_ATTR_REF} · Gestione pressione {STAFF_ATTR_REF}", texts)

    def test_the_hire_button_is_still_in_the_last_column_and_works(self) -> None:
        table = self.win.staff_tab.table
        last = table.columnCount() - 1
        self.assertEqual(table.horizontalHeaderItem(last).text(), "Azione")
        button = table.cellWidget(0, last)
        self.assertEqual(button.text(), "Assumi")
        staff_id = self.ctrl.state.staff[0].id
        self.ctrl.toggle_staff(staff_id)
        self.assertTrue(self.ctrl.state.staff[0].hired)
        self.assertEqual(table.cellWidget(0, last).text(), "Licenzia")

    def test_edited_attributes_survive_a_reload(self) -> None:
        member = next(s for s in self.ctrl.state.staff if s.role == StaffRole.PHYSIO)
        member.attributes = {"competenza": 17, "recupero": 12}
        self.ctrl.toggle_staff(member.id)  # salva
        other = GameController(db_manager=DatabaseManager(db_path=self.path), rng=random.Random(9), auto_create=False)
        self.assertTrue(other.load_game())
        loaded = next(s for s in other.state.staff if s.role == StaffRole.PHYSIO)
        self.assertEqual(loaded.attributes, {"competenza": 17, "recupero": 12})
        self.assertTrue(loaded.hired)


if __name__ == "__main__":
    unittest.main()
