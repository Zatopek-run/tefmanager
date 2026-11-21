"""Lotto E.2 (parte con Qt offscreen): schede degli impianti avanzati nella tab «Infrastrutture» e acquisto dal controller.

Non si prova il mouse reale: si legge lo stato dei pulsanti e si chiama `buy_facility` come farebbe il click.
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
from models.entities import FACILITY_COSTS, FACILITY_MEDICAL, FACILITY_ORDER, FACILITY_UPKEEP, FACILITY_VIDEO
from tests.support import start_game
from views.main_window import MainWindow

_app = QApplication.instance() or QApplication([])


class TestFacilitiesUi(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "s.db"
        self.ctrl = GameController(db_manager=DatabaseManager(db_path=self.path), rng=random.Random(3), auto_create=False)
        start_game(self.ctrl, team_name="CUS Test", game_mode="career")
        self.ctrl.state.budget = 100000
        self.win = MainWindow(self.ctrl)
        self.addCleanup(self.win.close)
        self.tab = self.win.infrastructure_tab  # Q34d: le schede stanno nella tab «Infrastrutture»

    def test_there_is_one_buy_button_per_facility_with_its_cost(self) -> None:
        self.tab.refresh(self.ctrl.state)
        self.assertEqual(list(self.tab.facility_btns), FACILITY_ORDER)
        for key, btn in self.tab.facility_btns.items():
            self.assertTrue(btn.isEnabled())
            self.assertIn(f"{FACILITY_COSTS[key]:,}", btn.text())

    def test_buying_charges_the_cost_records_it_and_disables_the_button(self) -> None:
        before = self.ctrl.state.budget
        self.assertTrue(self.ctrl.buy_facility(FACILITY_MEDICAL))
        self.assertEqual(self.ctrl.state.budget, before - FACILITY_COSTS[FACILITY_MEDICAL])
        self.assertEqual(self.ctrl.state.facilities, {FACILITY_MEDICAL: 1})
        tx = self.ctrl.state.transactions[0]
        self.assertEqual((tx.category, tx.amount), ("Impianto", -FACILITY_COSTS[FACILITY_MEDICAL]))
        self.tab.refresh(self.ctrl.state)
        self.assertFalse(self.tab.facility_btns[FACILITY_MEDICAL].isEnabled())
        self.assertEqual(self.tab.facility_btns[FACILITY_MEDICAL].text(), "Posseduto")
        self.assertTrue(self.tab.facility_btns[FACILITY_VIDEO].isEnabled())

    def test_the_cards_show_the_weekly_upkeep(self) -> None:
        self.tab.refresh(self.ctrl.state)
        for key in FACILITY_ORDER:
            self.assertIn(f"manutenzione €{FACILITY_UPKEEP[key]}/sett", self.tab.facility_subs[key].text())

    def test_the_infrastructure_tab_is_last_and_does_not_move_the_other_pages(self) -> None:
        labels = [b.text().split(" (")[0] for b in self.win._nav_buttons]
        self.assertEqual(labels[-1], "Infrastrutture")
        self.assertEqual(self.win.tabs.widget(len(labels) - 1), self.win.infrastructure_tab)
        # la tab nuova è in fondo: gli indici delle pagine che c'erano prima non si spostano
        self.assertEqual(labels[7:10], ["Staff && Impianto", "Finanze", "Albo && Record"])  # «&&» = «&» letterale nei pulsanti Qt

    def test_gym_stands_and_facilities_live_in_the_new_tab_not_in_the_staff_tab(self) -> None:
        for attr in ("gym_btn", "stand_btn", "facility_btns"):
            self.assertTrue(hasattr(self.win.infrastructure_tab, attr), attr)
            self.assertFalse(hasattr(self.win.staff_tab, attr), attr)

    def test_the_gym_and_stand_buttons_still_work_from_the_new_tab(self) -> None:
        tab, state = self.win.infrastructure_tab, self.ctrl.state
        gym, seats = state.gym_level, state.stand_seats
        tab.gym_btn.click()
        tab.stand_btn.click()
        self.assertEqual(state.gym_level, gym + 1)
        self.assertGreater(state.stand_seats, seats)

    def test_the_button_click_buys(self) -> None:
        self.tab.facility_btns[FACILITY_VIDEO].click()
        self.assertEqual(self.ctrl.state.facilities, {FACILITY_VIDEO: 1})

    def test_a_second_purchase_is_refused_and_costs_nothing(self) -> None:
        self.ctrl.buy_facility(FACILITY_MEDICAL)
        budget = self.ctrl.state.budget
        self.assertFalse(self.ctrl.buy_facility(FACILITY_MEDICAL))
        self.assertEqual(self.ctrl.state.budget, budget)

    def test_without_the_money_nothing_is_bought(self) -> None:
        self.ctrl.state.budget = FACILITY_COSTS[FACILITY_MEDICAL] - 1
        messages = []
        self.ctrl.status_message.connect(messages.append)
        self.assertFalse(self.ctrl.buy_facility(FACILITY_MEDICAL))
        self.assertEqual(self.ctrl.state.facilities, {})
        self.assertEqual(self.ctrl.state.budget, FACILITY_COSTS[FACILITY_MEDICAL] - 1)
        self.assertTrue(any("Budget insufficiente" in m for m in messages))

    def test_an_unknown_facility_is_ignored(self) -> None:
        self.assertFalse(self.ctrl.buy_facility("piscina"))
        self.assertEqual(self.ctrl.state.facilities, {})

    def test_the_purchase_survives_a_reload(self) -> None:
        self.ctrl.buy_facility(FACILITY_VIDEO)
        other = GameController(db_manager=DatabaseManager(db_path=self.path), rng=random.Random(9), auto_create=False)
        self.assertTrue(other.load_game())
        self.assertEqual(other.state.facilities, {FACILITY_VIDEO: 1})
        self.assertEqual(other.state.budget, self.ctrl.state.budget)

    def test_the_week_still_advances_with_every_facility_owned(self) -> None:
        # Controller senza finestra: con la MainWindow la gara aprirebbe dialoghi modali (che in offscreen non tornano).
        with tempfile.TemporaryDirectory() as tmp:
            ctrl = GameController(db_manager=DatabaseManager(db_path=Path(tmp) / "t.db"), rng=random.Random(3), auto_create=False)
            start_game(ctrl, team_name="CUS Test", game_mode="career")
            ctrl.state.budget = 100000
            for key in FACILITY_ORDER:
                ctrl.buy_facility(key)
            for _ in range(4):
                ctrl.dismiss_dilemma()
                ctrl.advance_week()
            self.assertEqual(len(ctrl.state.facilities), 4)


if __name__ == "__main__":
    unittest.main()
