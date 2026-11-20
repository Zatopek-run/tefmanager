"""Lotto D.3 (parte con Qt offscreen): tab «Finanze» con il bilancio mensile e il grafico a barre (QPainter).

Non si prova il mouse reale: si leggono tabelle ed etichette, si seleziona una riga da codice e si disegna il widget su un'immagine.
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
from tests.support import start_game
from models.database import DatabaseManager
from models.entities import MONTH_WEEKS, SPONSOR_TOP_N, MonthlyReport, SeasonEndResult, SeasonOutcome, CompetitionTier
from views.finance_chart import MonthlyBarsWidget
from views.tabs import FinancesTab

_app = QApplication.instance() or QApplication([])


def _controller(tmp: str) -> GameController:
    ctrl = GameController(db_manager=DatabaseManager(db_path=Path(tmp) / "s.db"), rng=random.Random(3), auto_create=False)
    start_game(ctrl, team_name="CUS Test", game_mode="career")
    return ctrl


def _play(ctrl: GameController, weeks: int) -> None:
    for _ in range(weeks):
        ctrl.dismiss_dilemma()
        ctrl.advance_week()


def _report(month: int, income: int, expenses: int) -> MonthlyReport:
    return MonthlyReport(1, month, (month - 1) * 4 + 1, month * 4, {"Sponsor": income}, {"Rimborsi Atleti": expenses}, 1000)


class TestFinancesTab(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.ctrl = _controller(tmp.name)
        self.tab = FinancesTab(self.ctrl)
        self.addCleanup(self.tab.close)

    def test_it_starts_with_no_month_and_an_explanation_in_the_chart(self) -> None:
        self.tab.refresh(self.ctrl.state)
        self.assertEqual(self.tab.months_table.rowCount(), 0)
        self.assertEqual(self.tab.breakdown_table.rowCount(), 0)
        self.assertEqual(self.tab.sections.tabText(0), "Bilancio mensile")
        self.assertEqual(self.tab.sections.tabText(1), "Libro mastro")

    def test_each_closed_month_is_a_row_newest_first_with_a_matching_breakdown(self) -> None:
        _play(self.ctrl, MONTH_WEEKS * 3)
        self.tab.refresh(self.ctrl.state)
        reports = self.ctrl.state.monthly_reports
        self.assertEqual(self.tab.months_table.rowCount(), 3)
        self.assertIn("mese 3", self.tab.months_table.item(0, 0).text())  # il più recente in alto
        self.assertEqual(self.tab.months_table.currentRow(), 0)  # selezionato di default
        rows = {self.tab.breakdown_table.item(r, 0).text(): r for r in range(self.tab.breakdown_table.rowCount())}
        self.assertIn("TOTALE", rows)
        total = rows["TOTALE"]
        self.assertEqual(self.tab.breakdown_table.item(total, 1).text(), f"€{reports[0].total_income:,}")
        self.assertEqual(self.tab.breakdown_table.item(total, 2).text(), f"-€{reports[0].total_expenses:,}")
        for category in reports[0].income:
            self.assertIn(category, rows)

    def test_selecting_another_month_changes_the_breakdown(self) -> None:
        _play(self.ctrl, MONTH_WEEKS * 3)
        self.tab.refresh(self.ctrl.state)
        self.tab.months_table.selectRow(2)
        total = self.tab.breakdown_table.rowCount() - 1
        oldest = self.ctrl.state.monthly_reports[2]
        self.assertEqual(self.tab.breakdown_table.item(total, 1).text(), f"€{oldest.total_income:,}")

    def test_the_selected_month_is_kept_when_the_tab_refreshes(self) -> None:
        _play(self.ctrl, MONTH_WEEKS * 3)
        self.tab.refresh(self.ctrl.state)
        self.tab.months_table.selectRow(1)
        self.tab.refresh(self.ctrl.state)
        self.assertEqual(self.tab.months_table.currentRow(), 1)

    def test_the_cards_show_merchandising_and_the_sponsor_cut(self) -> None:
        state = self.ctrl.state
        state.prestige = 400
        state.season_history = [SeasonEndResult(1, CompetitionTier.PROVINCIALE, SPONSOR_TOP_N + 2, SeasonOutcome.STAYED)]
        self.tab.refresh(state)
        text = self.tab.sponsor_sub.text()
        self.assertIn("Merch €", text)
        self.assertIn(f"fuori dai primi {SPONSOR_TOP_N}", text)

    def test_no_cut_note_when_the_season_was_good(self) -> None:
        state = self.ctrl.state
        state.season_history = [SeasonEndResult(1, CompetitionTier.PROVINCIALE, 2, SeasonOutcome.STAYED)]
        self.tab.refresh(state)
        self.assertNotIn("fuori dai primi", self.tab.sponsor_sub.text())

    def test_the_ledger_is_still_there(self) -> None:
        _play(self.ctrl, 2)
        self.tab.refresh(self.ctrl.state)
        self.assertGreater(self.tab.table.rowCount(), 0)


class TestMonthlyBars(unittest.TestCase):
    def test_bar_heights_share_one_scale(self) -> None:
        reports = [_report(1, 1000, 500), _report(2, 250, 2000)]
        heights = MonthlyBarsWidget.bar_heights(reports, 100.0)
        self.assertEqual(heights, [(50.0, 25.0), (12.5, 100.0)])

    def test_empty_or_flat_data_gives_flat_bars(self) -> None:
        self.assertEqual(MonthlyBarsWidget.bar_heights([], 100.0), [])
        self.assertEqual(MonthlyBarsWidget.bar_heights([_report(1, 0, 0)], 100.0), [(0.0, 0.0)])

    def test_it_paints_with_and_without_data_and_keeps_the_last_twelve_months(self) -> None:
        widget = MonthlyBarsWidget()
        widget.resize(600, 200)
        self.addCleanup(widget.close)
        self.assertFalse(widget.grab().isNull())  # vuoto: scrive il messaggio
        widget.set_reports([_report(m, 1000 * m, 500 * m) for m in range(1, 16)])
        self.assertEqual(len(widget._reports), 12)
        self.assertEqual(widget._reports[0].month, 4)
        image = widget.grab().toImage()
        colours = {image.pixelColor(x, y).name() for x in range(0, image.width(), 3) for y in range(0, image.height(), 3)}
        self.assertIn("#34d399", colours)  # barre delle entrate
        self.assertIn("#f87171", colours)  # barre delle uscite


class TestEveryMovementGoesThroughTheLedger(unittest.TestCase):
    """Il saldo di un mese è la variazione del budget solo se ogni azione che muove denaro scrive una voce nel libro mastro."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.ctrl = _controller(tmp.name)
        self.state = self.ctrl.state
        self.state.budget = 60000

    def _dilemma(self, kind: str):
        from models.entities import EthicalDilemma

        self.state.pending_dilemma = EthicalDilemma(kind, "t", "d", "si", "no", athlete_id=self.state.main_squad[0].id)

    def test_every_spending_action_matches_a_ledger_entry(self) -> None:
        a = self.state.main_squad[0]
        actions = [
            lambda: self.ctrl.apply_recovery_session(a.id),
            lambda: self.ctrl.maintain_track(),
            lambda: self.ctrl.upgrade_gym(),
            lambda: self.ctrl.expand_stands(),
            lambda: self.ctrl.release_athlete(self.state.main_squad[1].id),
            lambda: (self._dilemma("doping_w3"), self.ctrl.resolve_dilemma(True)),
            lambda: (self._dilemma("doping_w5"), self.ctrl.resolve_dilemma(False)),
            lambda: (self._dilemma("youth_w4"), self.ctrl.resolve_dilemma(True)),
            lambda: (self._dilemma("youth_w6"), self.ctrl.resolve_dilemma(False)),
            lambda: self.ctrl.run_youth_scouting(),
        ]
        for i, action in enumerate(actions):
            before_budget, before_ledger = self.state.budget, sum(t.amount for t in self.state.transactions)
            action()
            self.assertEqual(
                self.state.budget - before_budget,
                sum(t.amount for t in self.state.transactions) - before_ledger,
                f"azione {i}: il budget è cambiato senza una voce corrispondente nel libro mastro",
            )

    def test_a_rejected_dilemma_costs_at_most_what_the_club_has(self) -> None:
        self.state.budget = 200
        self._dilemma("doping_w3")
        self.ctrl.resolve_dilemma(False)
        self.assertEqual(self.state.budget, 0)
        self.assertEqual(self.state.transactions[0].amount, -200)
        self.assertEqual(self.state.transactions[0].category, "Dilemmi")

    def test_a_club_in_debt_is_not_wiped_clean_by_rejecting_a_dilemma(self) -> None:
        self.state.budget = -5000
        self._dilemma("youth_w4")
        self.ctrl.resolve_dilemma(False)
        self.assertEqual(self.state.budget, -5000)

    def test_the_monthly_net_matches_the_budget_with_player_actions_in_between(self) -> None:
        a = self.state.main_squad[0]
        self.state.transactions = []
        start = self.state.budget
        self.ctrl.apply_recovery_session(a.id)
        self._dilemma("doping_w3")
        self.ctrl.resolve_dilemma(False)
        _play(self.ctrl, MONTH_WEEKS)
        report = self.state.monthly_reports[0]
        self.assertEqual(report.net, report.budget_end - start)


if __name__ == "__main__":
    unittest.main()
