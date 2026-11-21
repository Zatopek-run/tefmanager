"""Lotto F.3 (parte con Qt offscreen): tab «Relazioni» della scheda atleta e salvataggio dal controller.

Non si prova il mouse reale: si istanzia la scheda (mai `exec()`) e si legge la tabella.
"""

from __future__ import annotations

import os
import random
import tempfile
import unittest
from itertools import combinations
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("TEF_NO_GODOT", "1")

from PyQt6.QtWidgets import QApplication

from controllers.game_controller import GameController
from models.database import DatabaseManager
from models.relationships import ensure_relationships, relation_between, set_relation
from tests.support import start_game
from views.athlete_dialog import AthleteDetailDialog

_app = QApplication.instance() or QApplication([])


class TestRelationsTab(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "s.db"
        self.ctrl = GameController(db_manager=DatabaseManager(db_path=self.path), rng=random.Random(3), auto_create=False)
        start_game(self.ctrl, team_name="CUS Test", game_mode="career")
        self.state = self.ctrl.state
        ensure_relationships(self.state)
        for a, b in combinations(self.state.main_squad, 2):
            set_relation(a, b, 0)
        self.me, self.friend, self.rival = self.state.main_squad[:3]
        set_relation(self.me, self.friend, 70)
        set_relation(self.me, self.rival, -55)

    def dialog(self, athlete):
        dlg = AthleteDetailDialog(self.ctrl, athlete.id)
        self.addCleanup(dlg.close)
        return dlg

    def test_the_tab_exists_and_lists_friends_before_rivals(self) -> None:
        dlg = self.dialog(self.me)
        self.assertEqual([dlg.tabs.tabText(i) for i in range(dlg.tabs.count())][-1], "RELAZIONI")
        table = dlg.relations_table
        self.assertEqual(table.rowCount(), 2)
        self.assertEqual(table.item(0, 0).text(), self.friend.name)
        self.assertEqual((table.item(0, 2).text(), table.item(0, 3).text()), ("Amicizia", "+70"))
        self.assertEqual(table.item(1, 0).text(), self.rival.name)
        self.assertEqual((table.item(1, 2).text(), table.item(1, 3).text()), ("Rivalità", "-55"))

    def test_an_athlete_without_relationships_shows_the_empty_hint(self) -> None:
        loner = self.state.main_squad[5]
        dlg = self.dialog(loner)
        self.assertEqual(dlg.relations_table.rowCount(), 0)

    def test_the_friend_sees_the_same_relationship(self) -> None:
        table = self.dialog(self.friend).relations_table
        self.assertEqual((table.item(0, 0).text(), table.item(0, 3).text()), (self.me.name, "+70"))

    def test_relationships_survive_a_save_and_reload(self) -> None:
        self.ctrl._persist()
        other = GameController(db_manager=DatabaseManager(db_path=self.path), rng=random.Random(9), auto_create=False)
        self.assertTrue(other.load_game())
        me = next(a for a in other.state.athletes if a.id == self.me.id)
        friend = next(a for a in other.state.athletes if a.id == self.friend.id)
        self.assertEqual(relation_between(me, friend), 70)
        self.assertEqual(relation_between(friend, me), 70)

    def test_the_week_advances_with_relationships_in_the_squad(self) -> None:
        for _ in range(4):
            self.ctrl.dismiss_dilemma()
            self.ctrl.advance_week()
        self.assertTrue(any(a.relationships for a in self.ctrl.state.main_squad))


if __name__ == "__main__":
    unittest.main()
