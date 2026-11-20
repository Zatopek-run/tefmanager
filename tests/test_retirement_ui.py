"""Lotto C.3 (parte con Qt offscreen): lista «Ex atleti» nella scheda Albo e assunzione dell'ex atleta come allenatore.

Non si prova il mouse reale: si leggono le tabelle e si chiamano i metodi che i pulsanti collegano.
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
from models.career import REASON_AGE
from models.database import DatabaseManager
from models.entities import (
    COACH_STATS,
    MAX_SPECIALIZED_COACHES,
    RETIRED_COACH_HIRE_COST,
    RetiredAthlete,
    Specialty,
)
from views.tabs import RecordsTab

_app = QApplication.instance() or QApplication([])


def _ex(name: str, offer: bool, spec: Specialty = Specialty.SPRINTS) -> RetiredAthlete:
    skills = {s: 30 for s in COACH_STATS}
    skills.update(speed=78, technique=68)
    return RetiredAthlete(name, "M", spec, 36, 1, REASON_AGE, coach_offer=offer, coach_skills=skills if offer else {})


class TestHireRetiredCoach(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "s.db"
        self.ctrl = GameController(db_manager=DatabaseManager(db_path=self.path), rng=random.Random(3), auto_create=False)
        self.ctrl.start_new_game(team_name="CUS Test", game_mode="career")
        self.state = self.ctrl.state
        self.state.budget = 10000
        self.state.coach_hired_week = 0

    def test_hiring_pays_the_reduced_fee_and_creates_the_coach_with_the_ex_athlete_skills(self) -> None:
        ex = _ex("Mario Veloci", True)
        self.state.retired = [ex]
        coaches, budget = len(self.state.coaches), self.state.budget
        self.assertTrue(self.ctrl.hire_retired_coach(0))
        self.assertEqual(self.state.budget, budget - RETIRED_COACH_HIRE_COST)
        coach = self.state.coaches[-1]
        self.assertEqual(len(self.state.coaches), coaches + 1)
        self.assertEqual((coach.name, coach.specialty, coach.skills), ("Mario Veloci", Specialty.SPRINTS, ex.coach_skills))
        self.assertTrue(ex.became_coach and not ex.coach_offer)
        self.assertEqual(self.state.coach_hired_week, self.state.week)
        self.assertEqual(self.state.transactions[0].amount, -RETIRED_COACH_HIRE_COST)

    def test_the_hired_coach_survives_a_reload(self) -> None:
        self.state.retired = [_ex("Mario Veloci", True)]
        self.ctrl.hire_retired_coach(0)
        loaded = DatabaseManager(db_path=self.path).load_game()
        self.assertIn("Mario Veloci", [c.name for c in loaded.coaches])
        self.assertTrue(loaded.retired[0].became_coach)

    def test_refuses_without_an_offer_or_with_a_bad_index(self) -> None:
        self.state.retired = [_ex("Senza Offerta", False)]
        budget = self.state.budget
        self.assertFalse(self.ctrl.hire_retired_coach(0))
        self.assertFalse(self.ctrl.hire_retired_coach(5))
        self.assertFalse(self.ctrl.hire_retired_coach(-1))
        self.assertEqual(self.state.budget, budget)

    def test_one_coach_a_week(self) -> None:
        self.state.retired = [_ex("Primo", True), _ex("Secondo", True)]
        self.assertTrue(self.ctrl.hire_retired_coach(0))
        self.assertFalse(self.ctrl.hire_retired_coach(1))
        self.assertTrue(self.state.retired[1].coach_offer)  # l'offerta resta, finché non scade

    def test_refuses_at_the_specialized_coach_limit(self) -> None:
        extra = MAX_SPECIALIZED_COACHES - sum(1 for c in self.state.coaches if not c.is_youth_coach)
        for i in range(extra):
            self.state.coaches.append(_coach(100 + i))
        self.state.retired = [_ex("Fuori Limite", True)]
        budget = self.state.budget
        self.assertFalse(self.ctrl.hire_retired_coach(0))
        self.assertEqual(self.state.budget, budget)

    def test_refuses_without_money(self) -> None:
        self.state.retired = [_ex("Povero", True)]
        self.state.budget = RETIRED_COACH_HIRE_COST - 1
        self.assertFalse(self.ctrl.hire_retired_coach(0))
        self.assertTrue(self.state.retired[0].coach_offer)


def _coach(coach_id: int):
    from models.entities import Coach

    return Coach(id=coach_id, name=f"Coach {coach_id}", specialty=Specialty.THROWS, skills={s: 40 for s in COACH_STATS})


class TestRecordsTabRetiredList(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.ctrl = GameController(
            db_manager=DatabaseManager(db_path=Path(tmp.name) / "s.db"), rng=random.Random(3), auto_create=False
        )
        self.ctrl.start_new_game(team_name="CUS Test", game_mode="career")
        self.tab = RecordsTab(self.ctrl)
        self.ctrl.state.retired = [_ex("Con Offerta", True), _ex("In Pensione", False)]
        self.tab.refresh(self.ctrl.state)

    def test_lists_the_retired_with_their_status(self) -> None:
        table = self.tab.retired_table
        self.assertEqual(table.rowCount(), 2)
        self.assertEqual(table.item(0, 0).text(), "Con Offerta")
        self.assertEqual(table.item(0, 4).text(), "Disponibile come allenatore")
        self.assertEqual(table.item(1, 4).text(), "In pensione")

    def test_the_hire_button_is_enabled_only_for_an_open_offer(self) -> None:
        self.assertFalse(self.tab.hire_retired_button.isEnabled())  # nessuna riga scelta
        self.tab.retired_table.selectRow(1)
        self.assertFalse(self.tab.hire_retired_button.isEnabled())
        self.tab.retired_table.selectRow(0)
        self.assertTrue(self.tab.hire_retired_button.isEnabled())
        self.assertIn("Con Offerta", self.tab.hire_retired_button.toolTip())

    def test_the_button_hires_the_selected_row(self) -> None:
        self.ctrl.state.budget = 10000
        self.tab.retired_table.selectRow(0)
        self.tab.hire_retired_button.click()
        self.assertTrue(self.ctrl.state.retired[0].became_coach)
        self.tab.refresh(self.ctrl.state)
        self.assertEqual(self.tab.retired_table.item(0, 4).text(), "Allenatore della società")
        self.assertFalse(self.tab.hire_retired_button.isEnabled())

    def test_an_empty_list_paints(self) -> None:
        self.ctrl.state.retired = []
        self.tab.refresh(self.ctrl.state)
        self.assertEqual(self.tab.retired_table.rowCount(), 0)
        self.assertFalse(self.tab.hire_retired_button.isEnabled())


if __name__ == "__main__":
    unittest.main()
