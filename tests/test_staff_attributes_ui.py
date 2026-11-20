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
        self.assertEqual(table.rowCount(), 9)
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
        self.assertEqual({table.cellWidget(r, last).text() for r in range(table.rowCount())}, {"Assumi"})
        staff_id = self.ctrl.state.staff[0].id
        self.ctrl.toggle_staff(staff_id)
        self.assertTrue(self.ctrl.state.staff[0].hired)
        labels = [table.cellWidget(r, last).text() for r in range(table.rowCount())]
        self.assertEqual(labels.count("Licenzia"), 1)

    def test_rows_are_grouped_by_role_from_cheapest_to_dearest(self) -> None:
        table = self.win.staff_tab.table
        roles = [table.item(r, 1).text() for r in range(table.rowCount())]
        self.assertEqual(
            roles, [StaffRole.PHYSIO.value] * 3 + [StaffRole.DOCTOR.value] * 3 + [StaffRole.MENTAL_COACH.value] * 3
        )
        for start in (0, 3, 6):
            costs = [int(table.item(r, 3).text().lstrip("€")) for r in range(start, start + 3)]
            self.assertEqual(costs, sorted(costs))

    def test_hiring_a_second_specialist_of_the_same_role_replaces_the_first(self) -> None:
        state = self.ctrl.state
        physios = [m for m in state.staff if m.role == StaffRole.PHYSIO]
        first, second = physios[0], physios[1]
        self.ctrl.toggle_staff(first.id)
        self.assertEqual([m.id for m in state.staff if m.role == StaffRole.PHYSIO and m.hired], [first.id])
        self.ctrl.toggle_staff(second.id)
        self.assertEqual([m.id for m in state.staff if m.role == StaffRole.PHYSIO and m.hired], [second.id])
        self.assertTrue(any("lascia il posto" in line for line in state.news_log[:3]))

    def test_roles_do_not_exclude_each_other_and_firing_works(self) -> None:
        state = self.ctrl.state
        ids = {role: next(m.id for m in state.staff if m.role == role) for role in (StaffRole.PHYSIO, StaffRole.DOCTOR)}
        for sid in ids.values():
            self.ctrl.toggle_staff(sid)
        self.assertEqual(sum(1 for m in state.staff if m.hired), 2)
        self.ctrl.toggle_staff(ids[StaffRole.PHYSIO])  # licenzia
        self.assertEqual([m.role for m in state.staff if m.hired], [StaffRole.DOCTOR])

    def test_hired_cost_follows_the_chosen_candidate(self) -> None:
        from models.simulation import weekly_finances

        member = next(m for m in self.ctrl.state.staff if m.role == StaffRole.DOCTOR and m.weekly_cost != 340)
        self.ctrl.toggle_staff(member.id)
        self.assertEqual(weekly_finances(self.ctrl.state)["staff_cost"], member.weekly_cost)

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
