"""Lotto D.3: bilancio mensile, merchandising, sponsor con obiettivo, diritti TV (schema v20).

Solo modello e database: gira senza PyQt6 (`PYTHONPATH=. python3 -m unittest tests.test_finances`).
"""

from __future__ import annotations

import random
import tempfile
import unittest
from pathlib import Path

from models.database import DatabaseManager
from models.entities import (
    MAX_MONTHLY_REPORTS,
    MERCH_FANS_DIVISOR,
    MERCH_PRESTIGE_DIVISOR,
    MONTH_WEEKS,
    SEASON_WEEKS,
    SPONSOR_MISS_PENALTY,
    SPONSOR_TOP_N,
    TV_RIGHTS_PER_HOME_MEET,
    CompetitionTier,
    MonthlyReport,
    SeasonEndResult,
    SeasonOutcome,
    SeasonPhase,
    Transaction,
)
from models.finances import (
    build_monthly_report,
    close_month_if_due,
    merchandising_income,
    month_bounds,
    recent_reports,
    sponsor_after_cut,
    sponsor_cut_active,
    tv_rights_income,
)
from models.simulation import advance_week, weekly_finances
from tests.test_assignments import make_state


def tx(week: int, category: str, amount: int) -> Transaction:
    return Transaction(id=None, week=week, description=f"{category} sett. {week}", category=category, amount=amount)


def season_result(placement: int) -> SeasonEndResult:
    return SeasonEndResult(season=1, tier=CompetitionTier.PROVINCIALE, placement=placement, outcome=SeasonOutcome.STAYED)


def fresh():
    state = make_state(3)
    state.week = 1
    state.transactions = []
    return state


class TestMonthBounds(unittest.TestCase):
    def test_months_are_four_weeks_long_and_continuous(self) -> None:
        self.assertEqual(MONTH_WEEKS, 4)
        self.assertEqual([month_bounds(w) for w in (1, 4, 5, 8, 36, 37)], [(1, 4), (1, 4), (5, 8), (5, 8), (33, 36), (37, 40)])

    def test_a_season_has_nine_months(self) -> None:
        self.assertEqual(SEASON_WEEKS // MONTH_WEEKS, 9)


class TestBuildReport(unittest.TestCase):
    def test_sums_by_category_split_into_income_and_expenses(self) -> None:
        state = fresh()
        state.transactions = [
            tx(4, "Sponsor", 1000), tx(3, "Sponsor", 900), tx(2, "Premi Gara", 500),
            tx(4, "Rimborsi Atleti", -300), tx(1, "Rimborsi Atleti", -200), tx(3, "Trasferte", -150),
        ]
        state.budget = 777
        rep = build_monthly_report(state, 1, 4)
        self.assertEqual(rep.income, {"Sponsor": 1900, "Premi Gara": 500})
        self.assertEqual(rep.expenses, {"Rimborsi Atleti": 500, "Trasferte": 150})
        self.assertEqual((rep.total_income, rep.total_expenses, rep.net, rep.budget_end), (2400, 650, 1750, 777))

    def test_only_the_weeks_of_that_month_count(self) -> None:
        state = fresh()
        state.transactions = [tx(4, "Sponsor", 10), tx(5, "Sponsor", 99), tx(0, "Sponsor", 77)]
        self.assertEqual(build_monthly_report(state, 1, 4).income, {"Sponsor": 10})

    def test_the_starting_capital_is_not_an_operating_income(self) -> None:
        state = fresh()
        state.transactions = [tx(1, "Capitale", 18000), tx(1, "Sponsor", 100)]
        self.assertEqual(build_monthly_report(state, 1, 4).income, {"Sponsor": 100})

    def test_season_and_month_numbers(self) -> None:
        state = fresh()
        for first, season, month in ((1, 1, 1), (5, 1, 2), (33, 1, 9), (37, 2, 1), (73, 3, 1)):
            rep = build_monthly_report(state, first, first + 3)
            self.assertEqual((rep.season, rep.month), (season, month), first)
        self.assertIn("Stagione 2 · mese 1 (sett. 37-40)", build_monthly_report(state, 37, 40).label)


class TestCloseMonth(unittest.TestCase):
    def test_nothing_is_closed_in_the_middle_of_a_month_or_before_the_first_ends(self) -> None:
        state = fresh()
        for week in (1, 2, 3, 4, 6, 7, 8):
            state.week = week
            self.assertFalse(close_month_if_due(state), week)
        self.assertEqual(state.monthly_reports, [])

    def test_the_month_just_ended_is_closed_once(self) -> None:
        state = fresh()
        state.transactions = [tx(3, "Sponsor", 50)]
        state.week = 5
        self.assertTrue(close_month_if_due(state))
        self.assertFalse(close_month_if_due(state))  # idempotente
        self.assertEqual([(r.first_week, r.last_week) for r in state.monthly_reports], [(1, 4)])

    def test_reports_are_kept_newest_first_and_capped(self) -> None:
        state = fresh()
        for week in range(5, 5 + MONTH_WEEKS * (MAX_MONTHLY_REPORTS + 5), MONTH_WEEKS):
            state.week = week
            close_month_if_due(state)
        self.assertEqual(len(state.monthly_reports), MAX_MONTHLY_REPORTS)
        firsts = [r.first_week for r in state.monthly_reports]
        self.assertEqual(firsts, sorted(firsts, reverse=True))
        self.assertEqual([r.first_week for r in recent_reports(state, 3)], sorted(firsts[:3]))  # il più vecchio per primo

    def test_the_tick_closes_a_month_every_four_weeks_and_its_net_equals_the_budget_change(self) -> None:
        """L'invariante che tiene insieme tutto: il saldo del mese è esattamente la variazione del budget del mese."""
        state = make_state(3)
        state.week, state.transactions = 1, []
        previous = state.budget
        for _ in range(MONTH_WEEKS * 6):
            state.pending_dilemma = None
            advance_week(state, rng=random.Random(state.week))
        self.assertEqual(len(state.monthly_reports), 6)
        for rep in reversed(state.monthly_reports):
            self.assertEqual(rep.net, rep.budget_end - previous, rep.label)
            previous = rep.budget_end
        self.assertEqual(state.monthly_reports[0].budget_end, state.budget)


class TestMerchandising(unittest.TestCase):
    def test_zero_at_the_start_and_grows_with_fans_and_prestige(self) -> None:
        state = fresh()
        for a in state.athletes:
            a.fans = 0
        state.prestige = 0
        self.assertEqual(merchandising_income(state), 0)
        state.athletes[0].fans = 400
        state.prestige = 100
        base = 400 // MERCH_FANS_DIVISOR + 100 // MERCH_PRESTIGE_DIVISOR
        self.assertEqual(merchandising_income(state), base)
        state.athletes[1].fans = 400
        self.assertGreater(merchandising_income(state), base)

    def test_only_the_main_squad_counts(self) -> None:
        state = fresh()
        for a in state.athletes:
            a.fans, a.in_youth_squad = 0, False
        state.prestige = 0
        state.athletes[0].fans, state.athletes[0].in_youth_squad = 4000, True
        self.assertEqual(merchandising_income(state), 0)

    def test_it_is_part_of_the_weekly_income_and_the_ledger(self) -> None:
        state = make_state(3)
        state.athletes[0].fans, state.prestige = 800, 200
        expected = 800 // MERCH_FANS_DIVISOR + 200 // MERCH_PRESTIGE_DIVISOR
        fin = weekly_finances(state)
        self.assertEqual(fin["merchandising"], expected)
        self.assertEqual(fin["income"], fin["sponsor"] + fin["individual_sponsors"] + expected + fin["member_fees"])
        state.pending_dilemma = None
        advance_week(state, rng=random.Random(1))
        entries = [t for t in state.transactions if t.category == "Merchandising"]
        self.assertTrue(entries and entries[0].amount > 0)


class TestSponsorObjective(unittest.TestCase):
    def test_no_history_no_cut(self) -> None:
        state = fresh()
        self.assertFalse(sponsor_cut_active(state))
        self.assertEqual(weekly_finances(state)["sponsor_cut"], 0)

    def test_top_five_keeps_the_full_sponsor_and_sixth_loses_twenty_percent(self) -> None:
        self.assertEqual((SPONSOR_TOP_N, SPONSOR_MISS_PENALTY), (5, 0.20))
        state = fresh()
        state.season_history = [season_result(SPONSOR_TOP_N)]
        full = weekly_finances(state)
        self.assertEqual(full["sponsor_cut"], 0)
        state.season_history = [season_result(SPONSOR_TOP_N + 1)]
        cut = weekly_finances(state)
        self.assertEqual(cut["sponsor"] + cut["sponsor_cut"], full["sponsor"])
        self.assertEqual(cut["sponsor_cut"], round(full["sponsor"] * 0.20))
        self.assertEqual(cut["net"], full["net"] - cut["sponsor_cut"])

    def test_a_good_season_restores_the_sponsor(self) -> None:
        state = fresh()
        state.season_history = [season_result(3), season_result(8)]  # la più recente in testa: 3° dopo un 8°
        self.assertFalse(sponsor_cut_active(state))
        state.season_history = [season_result(8), season_result(3)]
        self.assertTrue(sponsor_cut_active(state))

    def test_only_the_club_sponsor_is_cut(self) -> None:
        state = fresh()
        state.season_history = [season_result(8)]
        for a in state.athletes:
            a.fans = 400
        state.prestige = 100
        cut = weekly_finances(state)
        self.assertGreater(cut["individual_sponsors"], 0)
        self.assertEqual(cut["individual_sponsors"] + cut["merchandising"] + cut["member_fees"], cut["income"] - cut["sponsor"])

    def test_helper_returns_the_amounts(self) -> None:
        state = fresh()
        self.assertEqual(sponsor_after_cut(state, 1000), (1000, 0))
        state.season_history = [season_result(6)]
        self.assertEqual(sponsor_after_cut(state, 1000), (800, 200))

    def test_the_ledger_line_says_why_the_sponsor_is_lower(self) -> None:
        state = make_state(3)
        state.season_history = [season_result(7)]
        state.pending_dilemma = None
        advance_week(state, rng=random.Random(1))
        line = next(t for t in state.transactions if t.category == "Sponsor" and "Società" in t.description)
        self.assertIn("fuori dai primi 5", line.description)

    def test_the_verdict_of_a_real_season_drives_the_cut(self) -> None:
        """Chiudere davvero una stagione fuori dai primi 5 taglia lo sponsor di quella dopo."""
        state = make_state(3)
        state.week, state.season_phase = SEASON_WEEKS, SeasonPhase.INDOOR
        state.league_table = {state.team_name: 0, **{c.name: 100 + i for i, c in enumerate(state.rivals_in())}}
        state.pending_dilemma = None
        advance_week(state, rng=random.Random(4))
        self.assertEqual(state.season_number, 2)
        self.assertGreater(state.season_history[0].placement, SPONSOR_TOP_N)
        self.assertTrue(sponsor_cut_active(state))


class TestTvRights(unittest.TestCase):
    def test_only_international_home_meetings_pay(self) -> None:
        state = fresh()
        for tier in CompetitionTier:
            state.tier = tier
            expected = TV_RIGHTS_PER_HOME_MEET if tier == CompetitionTier.INTERNAZIONALE else 0
            self.assertEqual(tv_rights_income(state, True), expected, tier)
            self.assertEqual(tv_rights_income(state, False), 0, tier)

    def _international(self, week: int):
        state = make_state(3, tier=CompetitionTier.INTERNAZIONALE)
        for a in state.athletes:
            a.age = max(a.age, 20)
        state.week = week
        state.pending_dilemma = None
        return state

    def test_a_home_international_meeting_books_the_tv_rights(self) -> None:
        week = next(w for w in range(4, 80, 4) if (w // 4) % 2 == 1)
        state = self._international(week)
        self.assertTrue(state.is_competition_week and state.next_meet_is_home)
        advance_week(state, rng=random.Random(2))
        tv = [t for t in state.transactions if t.category == "Diritti TV"]
        self.assertEqual([t.amount for t in tv], [TV_RIGHTS_PER_HOME_MEET])

    def test_no_tv_rights_for_an_away_or_lower_tier_meeting(self) -> None:
        away = next(w for w in range(4, 80, 4) if (w // 4) % 2 == 0)
        state = self._international(away)
        self.assertTrue(state.is_competition_week and not state.next_meet_is_home)
        advance_week(state, rng=random.Random(2))
        self.assertEqual([t for t in state.transactions if t.category == "Diritti TV"], [])
        home = next(w for w in range(4, 80, 4) if (w // 4) % 2 == 1)
        lower = make_state(3, tier=CompetitionTier.NAZIONALE)
        lower.week = home
        lower.pending_dilemma = None
        advance_week(lower, rng=random.Random(2))
        self.assertEqual([t for t in lower.transactions if t.category == "Diritti TV"], [])


class TestPersistence(unittest.TestCase):
    def test_monthly_reports_survive_a_reload(self) -> None:
        state = make_state(3)
        state.monthly_reports = [
            MonthlyReport(1, 2, 5, 8, {"Sponsor": 100}, {"Rimborsi Atleti": 40}, 1234),
            MonthlyReport(1, 1, 1, 4, {"Sponsor": 90, "Premi Gara": 10}, {}, 1000),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "f.db"
            DatabaseManager(db_path=path).save_game(state)
            loaded = DatabaseManager(db_path=path).load_game()
        self.assertEqual(loaded.monthly_reports, state.monthly_reports)

    def test_a_state_without_reports_loads_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "f.db"
            DatabaseManager(db_path=path).save_game(make_state(3))
            self.assertEqual(DatabaseManager(db_path=path).load_game().monthly_reports, [])


if __name__ == "__main__":
    unittest.main()
