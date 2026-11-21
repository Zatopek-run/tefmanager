"""Lotto C.1 (parte con Qt offscreen): scheda «Ranking», riga di ranking nella scheda atleta e ricarica della partita.

Non si prova il mouse reale: si agisce sui menu a tendina da codice (`setCurrentIndex`), che emette gli stessi segnali.
"""

from __future__ import annotations

import os
import random
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("TEF_NO_GODOT", "1")

from PyQt6.QtWidgets import QApplication, QLabel

from controllers.game_controller import GameController
from tests.support import start_game
from models.database import DatabaseManager
from models.entities import RANKING_NATIONAL_SIZE, RANKING_WORLD_SIZE
from models.simulation import advance_week
from views.athlete_dialog import AthleteDetailDialog
from views.main_window import MainWindow

_app = QApplication.instance() or QApplication([])


def _controller(path: Path, seed: int = 3) -> GameController:
    ctrl = GameController(db_manager=DatabaseManager(db_path=path), rng=random.Random(seed), auto_create=False)
    start_game(ctrl, team_name="CUS Test", game_mode="vertical_slice")
    return ctrl


def _play_first_meeting(ctrl: GameController) -> None:
    while not ctrl.state.is_competition_week:
        ctrl.dismiss_dilemma()
        advance_week(ctrl.state, rng=ctrl.rng)
    ctrl.dismiss_dilemma()
    advance_week(ctrl.state, rng=ctrl.rng)  # la gara si simula all'avanzamento della settimana di gara


class TestRankingTab(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "s.db"
        self.ctrl = _controller(self.path)
        self.win = MainWindow(controller=self.ctrl)
        self.addCleanup(self.win.close)
        self.tab = self.win.ranking_tab

    def test_the_tab_lists_the_world_and_national_tops_and_the_league_clubs(self) -> None:
        self.tab.refresh(self.ctrl.state)
        self.assertEqual(self.tab.world_table.rowCount(), RANKING_WORLD_SIZE)  # prima di giocare: solo i sintetici
        self.assertGreater(self.tab.national_table.rowCount(), 5)
        self.assertLessEqual(self.tab.national_table.rowCount(), RANKING_NATIONAL_SIZE)
        self.assertEqual(self.tab.club_table.rowCount(), len(self.ctrl.state.rivals_in()) + 1)
        self.assertEqual(self.tab.world_table.item(0, 0).text(), "1°")
        self.assertIn("Punti del club", self.tab.summary_label.text())

    def test_the_selectors_follow_the_active_events_and_both_genders(self) -> None:
        self.tab.refresh(self.ctrl.state)
        items = [self.tab.event_combo.itemText(i) for i in range(self.tab.event_combo.count())]
        self.assertEqual(items, list(self.ctrl.state.active_events))
        first = self.tab.world_table.item(0, 1).text()
        self.tab.gender_combo.setCurrentIndex(1)
        self.assertNotEqual(self.tab.world_table.item(0, 1).text(), first)
        self.tab.event_combo.setCurrentIndex(1)
        self.assertEqual(self.tab.world_table.rowCount(), RANKING_WORLD_SIZE)

    def test_after_a_meeting_my_athletes_appear_even_outside_the_top_100(self) -> None:
        _play_first_meeting(self.ctrl)
        self.win.ranking_tab.refresh(self.ctrl.state)
        state = self.ctrl.state
        scored = [(a, e) for a in state.athletes for e in a.ranking_points]
        self.assertTrue(scored, "nessun atleta ha preso punti dalla prima gara")
        athlete, event = scored[0]
        self.tab.event_combo.setCurrentIndex(self.tab.event_combo.findText(event))
        self.tab.gender_combo.setCurrentIndex(0 if athlete.gender == "M" else 1)
        names = [self.tab.world_table.item(r, 1).text() for r in range(self.tab.world_table.rowCount())]
        self.assertIn(athlete.name, names)  # Provinciale: fuori dalla Top 100 ma in fondo con il posto vero
        row = names.index(athlete.name)
        self.assertGreater(int(self.tab.world_table.item(row, 0).text().rstrip("°")), RANKING_WORLD_SIZE - 5)
        self.assertEqual(self.tab.world_table.item(row, 3).text(), state.team_name)

    def test_club_points_are_in_the_summary_after_a_meeting(self) -> None:
        _play_first_meeting(self.ctrl)
        self.tab.refresh(self.ctrl.state)
        self.assertNotIn("Punti del club in stagione: 0 ", self.tab.summary_label.text())


class TestAthleteDialogRanking(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.ctrl = _controller(Path(tmp.name) / "s.db")

    def _ranking_text(self, athlete_id: int) -> str:
        dlg = AthleteDetailDialog(self.ctrl, athlete_id)
        self.addCleanup(dlg.close)
        return " ".join(label.text() for label in dlg.results_page.findChildren(QLabel))

    def test_no_ranking_line_before_any_points(self) -> None:
        athlete = self.ctrl.state.main_squad[0]
        self.assertNotIn("RANKING", self._ranking_text(athlete.id))

    def test_the_ranking_line_shows_points_and_positions_after_a_meeting(self) -> None:
        _play_first_meeting(self.ctrl)
        athlete = next(a for a in self.ctrl.state.athletes if a.ranking_points)
        text = self._ranking_text(athlete.id)
        self.assertIn("RANKING", text)
        event = next(iter(athlete.ranking_points))
        self.assertIn(event, text)
        self.assertIn("punti", text)


class TestReloadKeepsRanking(unittest.TestCase):
    def test_reloading_gives_the_same_world_and_the_same_next_meeting(self) -> None:
        """Ricaricare non ritira i dadi dei sintetici: stesso campo e stessi punti dopo il meeting successivo."""
        with tempfile.TemporaryDirectory() as tmp:
            ctrl = _controller(Path(tmp) / "s.db")
            _play_first_meeting(ctrl)
            ctrl._persist()
            before = [(s.name, s.skill, s.points) for s in ctrl.state.ranking_pool]
            self.assertTrue(before)
            other = GameController(
                db_manager=DatabaseManager(db_path=Path(tmp) / "s.db"), rng=random.Random(999), auto_create=False
            )
            self.assertTrue(other.load_game())
            self.assertEqual([(s.name, s.skill, s.points) for s in other.state.ranking_pool], before)
            for c in (ctrl, other):
                for _ in range(4):
                    c.dismiss_dilemma()
                    advance_week(c.state, rng=c.rng)
            self.assertEqual(
                [(s.name, s.skill, s.points) for s in ctrl.state.ranking_pool],
                [(s.name, s.skill, s.points) for s in other.state.ranking_pool],
            )
            self.assertEqual(
                {a.name: a.ranking_points for a in ctrl.state.athletes},
                {a.name: a.ranking_points for a in other.state.athletes},
            )


if __name__ == "__main__":
    unittest.main()
