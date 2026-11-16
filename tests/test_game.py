"""Unit and integration tests for Track & Field Manager (v2 Vertical Slice & Career)."""

from __future__ import annotations

import os
import random
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from controllers.game_controller import GameController
from models.database import DatabaseManager
from models.entities import (
    CompetitionTier,
    PeriodizationPhase,
    SeasonPhase,
    TrainingFocus,
    WeatherCondition,
)
from models.generator import generate_vertical_slice_roster
from models.simulation import advance_week, apply_weekly_training


class TestVerticalSliceAndMechanics(unittest.TestCase):
    """Tests vertical slice, periodization, wind records, staff, dilemmas, and SQLite v2."""

    def test_vertical_slice_initial_setup(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db = DatabaseManager(db_path=Path(tmpdir) / "vs.db")
            ctrl = GameController(db_manager=db, rng=random.Random(42))
            self.assertEqual(ctrl.state.game_mode, "vertical_slice")
            self.assertEqual(ctrl.state.season_phase, SeasonPhase.OUTDOOR)
            self.assertEqual(len(ctrl.state.athletes), 10)
            self.assertEqual(ctrl.state.active_events, ["100m", "Salto in Lungo", "1500m"])
            self.assertEqual(len(ctrl.state.staff), 6)
            self.assertEqual(len(ctrl.state.objectives), 3)

    def test_periodization_tapering_and_recovery(self) -> None:
        roster = generate_vertical_slice_roster(rng=random.Random(10))
        sprinter = roster[0]
        sprinter.fatigue = 75
        sprinter.training_focus = TrainingFocus.REST
        sprinter.periodization = PeriodizationPhase.SCARICO
        apply_weekly_training(sprinter, rng=random.Random(10))
        self.assertLess(sprinter.fatigue, 55)

    def test_two_meets_and_sqlite_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db = DatabaseManager(db_path=Path(tmpdir) / "roundtrip.db")
            ctrl = GameController(db_manager=db, rng=random.Random(99))

            # Advance through Week 8 (completing Meet #1 on Week 4 and Meet #2 on Week 8)
            for _ in range(8):
                ctrl.advance_week()
                if ctrl.state.pending_dilemma is not None:
                    ctrl.resolve_dilemma(accepted=False)

            self.assertEqual(ctrl.state.week, 9)
            self.assertTrue(ctrl.state.is_vertical_slice_complete)
            self.assertEqual(len(ctrl.state.competition_history), 2)

            loaded = db.load_game()
            self.assertIsNotNone(loaded)
            assert loaded is not None
            self.assertEqual(loaded.week, 9)
            self.assertEqual(len(loaded.athletes), 10)
            self.assertEqual(len(loaded.competition_history), 2)
            self.assertEqual(loaded.reputation, ctrl.state.reputation)

    def test_wind_illegal_does_not_set_club_record(self) -> None:
        from models import simulation as sim

        with tempfile.TemporaryDirectory() as tmpdir:
            db = DatabaseManager(db_path=Path(tmpdir) / "wind.db")
            ctrl = GameController(db_manager=db, rng=random.Random(55))
            ctrl.state.week = 4

            orig_roll = sim._roll_meet_wind
            sim._roll_meet_wind = lambda _w, _s, _r: 2.8  # Force illegal tailwind > 2.0 m/s
            try:
                summary = sim.simulate_competition(ctrl.state, rng=random.Random(55))
            finally:
                sim._roll_meet_wind = orig_roll

            sprint_res = next(er for er in summary.event_results if er.event_name == "100m")
            self.assertTrue(sprint_res.wind_illegal)
            self.assertFalse(sprint_res.is_club_record)
            self.assertNotIn("100m", ctrl.state.club_records)

    def test_staff_track_and_career_season_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db = DatabaseManager(db_path=Path(tmpdir) / "career.db")
            ctrl = GameController(db_manager=db, rng=random.Random(77))
            ctrl.start_new_game(team_name="CUS Test", game_mode="career")
            self.assertEqual(len(ctrl.state.athletes), 8)
            self.assertEqual(len(ctrl.state.active_events), 5)

            ctrl.toggle_staff(4)  # Hire Physio
            self.assertTrue(any(s.id == 4 and s.hired for s in ctrl.state.staff))

            old_cond = ctrl.state.track_condition
            self.assertTrue(ctrl.maintain_track())
            self.assertGreater(ctrl.state.track_condition, old_cond)

            # Advance 12 weeks -> transitions Outdoor -> Cross
            for _ in range(12):
                advance_week(ctrl.state, rng=random.Random(77))
            self.assertEqual(ctrl.state.season_phase, SeasonPhase.CROSS)


class TestPyQtViewsV2(unittest.TestCase):
    """Smoke tests for MainWindow (5 tabs) and updated Dialogs."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_mainwindow_and_dialogs(self) -> None:
        from views.dialogs import (
            CompetitionResultsDialog,
            EthicalDilemmaDialog,
            NewGameDialog,
            RecruitAthleteDialog,
        )
        from views.main_window import MainWindow

        with tempfile.TemporaryDirectory() as tmpdir:
            db = DatabaseManager(db_path=Path(tmpdir) / "ui_v2.db")
            ctrl = GameController(db_manager=db, rng=random.Random(15))
            win = MainWindow(controller=ctrl)

            self.assertEqual(win.windowTitle(), "Track & Field Manager")
            self.assertEqual(win.tabs.count(), 5)
            self.assertEqual(win.roster_tab.table.rowCount(), 10)
            self.assertEqual(win.calendar_tab.lineup_table.rowCount(), 3)
            self.assertEqual(win.staff_tab.table.rowCount(), 6)

            new_dlg = NewGameDialog()
            self.assertEqual(new_dlg.game_mode, "vertical_slice")
            new_dlg.close()

            prospects = ctrl.generate_free_agents(count=4)
            rec_dlg = RecruitAthleteDialog(prospects, ctrl.state.budget)
            self.assertEqual(rec_dlg.table.rowCount(), 4)
            rec_dlg.close()

            ctrl.state.week = 4
            rep = advance_week(ctrl.state, rng=random.Random(15))
            assert rep.competition_summary is not None
            comp_dlg = CompetitionResultsDialog(rep.competition_summary)
            self.assertEqual(comp_dlg.events_table.rowCount(), 3)
            comp_dlg.close()

            if ctrl.state.pending_dilemma is not None:
                dil_dlg = EthicalDilemmaDialog(ctrl.state.pending_dilemma)
                dil_dlg.close()

            win.close()


if __name__ == "__main__":
    unittest.main()
