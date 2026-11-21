"""Avvio della Carriera senza atleti (Q32), parte con il controller e le viste (Qt offscreen).

Non si prova il mouse reale: le finestre si istanziano, si aggiornano e si leggono; `exec()` non si chiama mai.
"""

from __future__ import annotations

import os
import random
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("TEF_NO_GODOT", "1")

from PyQt6.QtWidgets import QApplication

from controllers.game_controller import GameController
from models.board import progress_text
from models.database import DatabaseManager
from models.entities import FOUNDATION_KEYS, SEASON_PREP_WEEKS, SeasonPhase
from models.generator import SPECIALTY_COACH_FOCUS
from views.main_window import MainWindow

_app = QApplication.instance() or QApplication([])


def _new(path: Path, mode: str = "career", seed: int = 3) -> GameController:
    ctrl = GameController(db_manager=DatabaseManager(db_path=path), rng=random.Random(seed), auto_create=False)
    ctrl.start_new_game(team_name="CUS Test", game_mode=mode)  # niente scorciatoie di test: l'avvio vero
    return ctrl


class _Case(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "s.db"
        self.ctrl = _new(self.path)
        self.state = self.ctrl.state


class TestNewGame(_Case):
    def test_squad_and_academy_are_empty_and_the_budget_is_unchanged(self) -> None:
        s = self.state
        self.assertEqual((s.athletes, s.main_squad, s.youth_squad), ([], [], []))
        self.assertEqual(s.budget, 18000)
        self.assertEqual([(t.category, t.amount) for t in s.transactions], [("Capitale", 18000)])
        self.assertEqual((s.week, s.season_number, s.tier.value), (1, 1, "Provinciale"))
        self.assertEqual(len(s.staff), 9)  # mercato dello staff clinico (E.1), nessuno assunto
        self.assertEqual(s.coaches, [])  # Q32d: nessun allenatore iniziale, si assumono quando servono
        self.assertEqual(s.member_fees_weekly, 450)

    def test_it_starts_in_the_preparation_with_the_foundation_objectives(self) -> None:
        s = self.state
        self.assertEqual((s.season_phase, s.prep_weeks), (SeasonPhase.PREPARAZIONE, SEASON_PREP_WEEKS))
        self.assertEqual([o.key for o in s.objectives], list(FOUNDATION_KEYS))
        self.assertEqual(s.current_date.isoformat(), "2026-02-09")
        self.assertEqual(s.week + s.weeks_until_competition, 12)

    def test_the_onboarding_message_explains_the_situation(self) -> None:
        intro = self.state.news_log[0]
        for needle in ("non ha ancora atleti", "€18,000", "8 settimane di Preparazione", "settimana 12", "Vivaio", "Rosa"):
            self.assertIn(needle, intro)

    def test_the_prototype_is_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            proto = _new(Path(tmp) / "p.db", mode="vertical_slice").state
            self.assertEqual((len(proto.main_squad), proto.budget, proto.prep_weeks), (10, 10000, 0))
            self.assertEqual(proto.season_phase, SeasonPhase.OUTDOOR)

    def test_an_empty_state_saves_and_loads(self) -> None:
        self.ctrl.save_game()
        other = GameController(db_manager=DatabaseManager(db_path=self.path), rng=random.Random(9), auto_create=False)
        self.assertTrue(other.load_game())
        loaded = other.state
        self.assertEqual((loaded.athletes, loaded.prep_weeks, loaded.season_phase), ([], 8, SeasonPhase.PREPARAZIONE))
        self.assertEqual([o.key for o in loaded.objectives], list(FOUNDATION_KEYS))
        self.assertEqual(loaded.budget, 18000)


class TestFirstSigning(_Case):
    def test_market_and_scouting_are_available_in_week_one(self) -> None:
        self.assertTrue(self.ctrl.get_free_agent_market())
        kids = self.ctrl.run_youth_scouting()
        self.assertTrue(kids)

    def test_the_first_signing_is_registered_and_paid(self) -> None:
        s = self.state
        candidate = self.ctrl.get_free_agent_market()[0]
        before = s.budget
        self.assertTrue(self.ctrl.recruit_athlete(candidate))
        self.assertEqual(len(s.main_squad), 1)
        athlete = s.main_squad[0]
        self.assertGreater(athlete.id, 0)
        self.assertGreater(before - s.budget, 0)
        self.assertEqual(s.transactions[0].category, "Scouting")
        self.assertEqual(s.transactions[0].amount, s.budget - before)
        self.assertGreater(athlete.contract_end_season, 0)
        self.assertIsNone(self.ctrl.state.coach_of(athlete))  # Q32d: nessun allenatore iniziale, serve assumerne uno
        self.assertTrue(self.ctrl.hire_coach(athlete.specialty, *SPECIALTY_COACH_FOCUS[athlete.specialty], 1))
        self.assertIsNotNone(self.ctrl.state.coach_of(athlete))  # l'allenatore assunto prende l'atleta della sua disciplina
        self.assertEqual(progress_text(s, s.objectives[0]), "1/6")

    def test_the_first_youth_signing_starts_the_academy(self) -> None:
        kid = self.ctrl.run_youth_scouting()[0]
        self.assertTrue(self.ctrl.sign_youth(kid))
        self.assertEqual(len(self.state.youth_squad), 1)
        self.assertEqual(progress_text(self.state, self.state.objectives[1]), "1/2")

    def test_the_week_advances_and_the_new_athlete_costs_wages_only_from_then_on(self) -> None:
        self.ctrl.recruit_athlete(self.ctrl.get_free_agent_market()[0])
        self.ctrl.advance_week()
        self.assertTrue([t for t in self.state.transactions if t.category == "Rimborsi Atleti"])

    def test_the_first_meet_with_one_athlete_counts_for_the_foundation(self) -> None:
        s = self.state
        self.ctrl.recruit_athlete(self.ctrl.get_free_agent_market()[0])
        self.ctrl.auto_fill_lineup()
        for _ in range(11):  # settimane 1-11: Preparazione, poi Outdoor fino alla vigilia della gara
            self.ctrl.dismiss_dilemma()
            report = self.ctrl.advance_week()
            self.assertIsNone(report.competition_summary)
        s.main_squad[0].injured_weeks = 0  # un infortunio casuale delle settimane prima non deve decidere il test
        self.ctrl.dismiss_dilemma()
        report = self.ctrl.advance_week()  # settimana 12
        self.assertFalse(report.competition_summary.club_absent)
        self.assertEqual(progress_text(s, s.objectives[2]), "1/3")


class TestViews(_Case):
    def setUp(self) -> None:
        super().setUp()
        self.win = MainWindow(controller=self.ctrl)
        self.addCleanup(self.win.close)

    def _refresh(self) -> None:
        self.ctrl.state_changed.emit(self.ctrl.state)

    def test_every_tab_refreshes_on_an_empty_club(self) -> None:
        self._refresh()
        for i in range(self.win.tabs.count()):
            self.win._navigate_to(i)
            self.win.tabs.widget(i).grab()  # disegna davvero la scheda

    def test_the_dashboard_tells_what_to_do(self) -> None:
        # Dal G.1 in QML la Dashboard disegna `dashboard_tab.snapshot`: le asserzioni di prima (che leggevano i widget) leggono lo snapshot.
        self._refresh()
        snap = self.win.dashboard_tab.snapshot
        kpi = {k["key"]: k for k in snap["kpis"]}
        self.assertIn("Nessun atleta", kpi["squad"]["value"])
        self.assertIn("Vivaio", kpi["squad"]["sub"])
        self.assertEqual(snap["top"]["rows"], [])
        self.assertIn("Nessun atleta in rosa", snap["top"]["emptyText"])
        buttons = [a["text"] for a in snap["actions"]]
        self.assertTrue(any("Nessun atleta in rosa" in b for b in buttons))
        self.assertFalse(any("gare scoperte" in b for b in buttons))  # non 12 gare scoperte per una rosa che non c'è
        objectives = [o["text"] for o in snap["objectives"]]
        self.assertTrue(any("0/6" in o for o in objectives))

    def test_the_dashboard_shows_the_preparation_and_the_season_length(self) -> None:
        self._refresh()
        snap = self.win.dashboard_tab.snapshot
        self.assertEqual(snap["season"]["progress"]["max"], 44)
        self.assertIn("44", snap["season"]["progress"]["text"].replace("mancano 44", "44"))
        self.assertIn("Tra 11 sett.", {k["key"]: k for k in snap["kpis"]}["race"]["value"])
        self.assertIn("Preparazione", self.win.date_label.text())

    def test_the_empty_tabs_explain_how_to_start(self) -> None:
        self._refresh()
        self.assertFalse(self.win.roster_tab.empty_hint.isHidden())
        self.assertFalse(self.win.youth_tab.empty_hint.isHidden())
        self.assertFalse(self.win.calendar_tab.empty_hint.isHidden())
        self.assertFalse(self.win.relay_tab.empty_hint.isHidden())
        self.ctrl.recruit_athlete(self.ctrl.get_free_agent_market()[0])
        self.assertTrue(self.win.roster_tab.empty_hint.isHidden())
        self.assertTrue(self.win.calendar_tab.empty_hint.isHidden())

    def test_the_navigation_badges_do_not_warn_about_an_empty_lineup(self) -> None:
        self._refresh()
        calendar_index = 3
        self.assertNotIn("(!)", self.win._nav_buttons[calendar_index].text())

    def test_playing_to_week_12_with_no_athletes_opens_no_dialog(self) -> None:
        with mock.patch("views.main_window.CompetitionResultsDialog") as results, mock.patch(
            "views.main_window.RaceViewerDialog"
        ) as viewer:
            for _ in range(12):
                self.ctrl.dismiss_dilemma()
                self.win._on_advance_clicked()
            results.assert_not_called()
            viewer.assert_not_called()
        self.assertEqual(self.state.week, 13)
        self.assertIn("non si iscrive", " ".join(self.state.news_log))
        self.assertEqual(self.state.budget > 18000, True)


class TestSeasonEndDialog(_Case):
    def test_the_foundation_season_end_says_no_consequences(self) -> None:
        from views.dialogs import SeasonEndDialog

        for _ in range(44):
            self.ctrl.dismiss_dilemma()
            self.ctrl.advance_week()
        result = self.state.season_history[-1]
        self.assertTrue(result.board_foundation)
        dlg = SeasonEndDialog(result, self.state.team_name)
        self.assertIn("fondazione", dlg.board_label.text())
        self.assertNotIn("FALLITA", dlg.board_label.text())


if __name__ == "__main__":
    unittest.main()
