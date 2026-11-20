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
from models.entities import STAFF_ATTR_REF, STAFF_SEVERANCE_WEEKS, StaffRole
from models.staff import severance_pay
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
        self.assertEqual(sum(1 for t in labels if t.startswith("Licenzia")), 1)
        self.assertEqual(sum(1 for t in labels if t.startswith("Sostituisci")), 2)  # gli altri due dello stesso ruolo
        self.assertEqual(labels.count("Assumi"), 6)  # i ruoli ancora scoperti

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
        budget_before = state.budget  # l'assunzione in un ruolo scoperto non costa nulla
        self.assertEqual([m.id for m in state.staff if m.role == StaffRole.PHYSIO and m.hired], [first.id])
        self.ctrl.toggle_staff(second.id)
        self.assertEqual([m.id for m in state.staff if m.role == StaffRole.PHYSIO and m.hired], [second.id])
        self.assertTrue(any("lascia il posto" in line for line in state.news_log[:3]))
        self.assertEqual(state.budget, budget_before - severance_pay(first))

    def test_roles_do_not_exclude_each_other_and_firing_works(self) -> None:
        state = self.ctrl.state
        ids = {role: next(m.id for m in state.staff if m.role == role) for role in (StaffRole.PHYSIO, StaffRole.DOCTOR)}
        for sid in ids.values():
            self.ctrl.toggle_staff(sid)
        self.assertEqual(sum(1 for m in state.staff if m.hired), 2)
        self.ctrl.toggle_staff(ids[StaffRole.PHYSIO])  # licenzia (con liquidazione)
        self.assertEqual([m.role for m in state.staff if m.hired], [StaffRole.DOCTOR])

    def test_hired_cost_follows_the_chosen_candidate(self) -> None:
        from models.simulation import weekly_finances

        member = next(m for m in self.ctrl.state.staff if m.role == StaffRole.DOCTOR and m.weekly_cost != 340)
        self.ctrl.toggle_staff(member.id)
        self.assertEqual(weekly_finances(self.ctrl.state)["staff_cost"], member.weekly_cost)

    def test_firing_and_replacing_both_cost_the_severance_of_the_one_who_leaves(self) -> None:
        state = self.ctrl.state
        physios = sorted((m for m in state.staff if m.role == StaffRole.PHYSIO), key=lambda m: m.weekly_cost)
        junior, senior = physios[0], physios[-1]
        self.assertTrue(self.ctrl.toggle_staff(junior.id))  # nessuno in carica: niente liquidazione
        self.assertEqual(state.budget, 18000)
        self.assertEqual(severance_pay(junior), junior.weekly_cost * STAFF_SEVERANCE_WEEKS)
        self.assertTrue(self.ctrl.toggle_staff(senior.id))  # sostituzione: paga la liquidazione del JUNIOR
        self.assertEqual(state.budget, 18000 - severance_pay(junior))
        self.assertTrue(self.ctrl.toggle_staff(senior.id))  # licenziamento semplice: paga quella del senior
        self.assertEqual(state.budget, 18000 - severance_pay(junior) - severance_pay(senior))
        self.assertFalse(any(m.hired for m in state.staff))
        rows = [t for t in state.transactions if t.category == "Staff" and t.description.startswith("Liquidazione")]
        self.assertEqual([t.amount for t in rows], [-severance_pay(senior), -severance_pay(junior)])

    def test_without_the_money_nothing_changes(self) -> None:
        state = self.ctrl.state
        physios = sorted((m for m in state.staff if m.role == StaffRole.PHYSIO), key=lambda m: m.weekly_cost)
        self.ctrl.toggle_staff(physios[0].id)
        state.budget = severance_pay(physios[0]) - 1
        news_before = list(state.news_log)
        self.assertFalse(self.ctrl.toggle_staff(physios[1].id))  # sostituzione
        self.assertFalse(self.ctrl.toggle_staff(physios[0].id))  # licenziamento
        self.assertEqual([m.id for m in state.staff if m.hired], [physios[0].id])
        self.assertEqual(state.budget, severance_pay(physios[0]) - 1)
        self.assertEqual(state.news_log, news_before)

    def test_the_severance_is_in_the_staff_category_of_the_monthly_report(self) -> None:
        # Stessa categoria delle voci settimanali: il bilancio mensile (D.3) la raggruppa con lo staff.
        state = self.ctrl.state
        member = next(m for m in state.staff if m.role == StaffRole.DOCTOR)
        self.ctrl.toggle_staff(member.id)
        self.ctrl.toggle_staff(member.id)
        self.assertEqual(state.transactions[0].category, "Staff")
        self.assertEqual(state.transactions[0].amount, -severance_pay(member))

    def test_buttons_show_the_severance(self) -> None:
        state = self.ctrl.state
        physios = sorted((m for m in state.staff if m.role == StaffRole.PHYSIO), key=lambda m: m.weekly_cost)
        self.ctrl.toggle_staff(physios[1].id)
        table = self.win.staff_tab.table
        last = table.columnCount() - 1
        labels = [table.cellWidget(r, last).text() for r in range(3)]  # i fisioterapisti sono le prime 3 righe
        self.assertEqual(labels[1], f"Licenzia (€{severance_pay(physios[1]):,})")
        self.assertEqual(labels[0], f"Sostituisci (€{severance_pay(physios[1]):,})")
        self.assertEqual(labels[2], f"Sostituisci (€{severance_pay(physios[1]):,})")

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
