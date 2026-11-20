"""Avvio della Carriera senza atleti (Q32), parte di modello: SENZA PyQt6.

Calendario con Preparazione (e compatibilità con `prep_weeks` = 0), meeting con la società assente (nessuna sanzione),
obiettivi di fondazione e stagione di raccordo del Board, assenza di sanzioni dopo la stagione 1.
"""

from __future__ import annotations

import random
import unittest

from models.board import (
    create_foundation_objectives,
    foundation_value,
    league_target,
    progress_text,
    settle_season,
    start_new_season,
)
from models.entities import (
    BOARD_LEAGUE_TARGET,
    BOARD_RAMP_MAX_SLACK,
    FOUNDATION_KEYS,
    FOUNDATION_MIN_ATHLETES,
    SEASON_PREP_WEEKS,
    STANDARD_BOARD_KEYS,
    GameState,
    SeasonEndResult,
    SeasonOutcome,
    SeasonPhase,
)
from models.finances import sponsor_cut_active
from models.agents import penalize_idle_athletes
from models.generator import create_rival_clubs, create_season_objectives, generate_initial_roster
from models.simulation import advance_week, simulate_competition
from tests.test_assignments import make_state


def empty_career(seed: int = 3, prep_weeks: int = SEASON_PREP_WEEKS) -> GameState:
    """Una Carriera nuova, come la crea il controller: nessun atleta, Preparazione, obiettivi di fondazione."""
    state = GameState(
        game_mode="career",
        week=1,
        prep_weeks=prep_weeks,
        season_phase=SeasonPhase.PREPARAZIONE if prep_weeks else SeasonPhase.OUTDOOR,
        budget=18000,
        rival_clubs=create_rival_clubs(rng=random.Random(seed)),
    )
    state.objectives = create_season_objectives("career", state.tier, state.budget, foundation=bool(prep_weeks))
    return state


def play(state: GameState, weeks: int, rng: random.Random):
    """Avanza `weeks` settimane senza dilemmi; ritorna i rapporti."""
    reports = []
    for _ in range(weeks):
        state.pending_dilemma = None
        reports.append(advance_week(state, rng=rng))
    return reports


class TestCalendarWithPreparation(unittest.TestCase):
    def test_no_race_in_the_preparation_and_the_first_meet_is_after_it(self) -> None:
        s = empty_career()
        racing = [w for w in range(1, 45) if s.is_race_week(w)]
        self.assertEqual(racing, [12, 16, 20, 24, 28, 32, 36, 40, 44])  # 9 gare come prima, tutte dopo la Preparazione
        self.assertEqual(s.season_length, 44)
        self.assertEqual(s.weeks_until_competition, 11)  # a settimana 1 la prossima gara è la 12
        self.assertFalse(s.is_competition_week)

    def test_weeks_until_competition_skips_the_preparation_in_every_season(self) -> None:
        s = empty_career()
        s.week = 45 + 6  # settimana 7 della Preparazione della stagione 2
        self.assertTrue(s.is_prep_week(s.week))
        self.assertEqual(s.week + s.weeks_until_competition, 45 + 11)

    def test_phases_follow_the_cycle_and_the_season_closes_when_it_wraps(self) -> None:
        s = empty_career()
        rng = random.Random(1)
        seen = {}
        for _ in range(88):
            s.pending_dilemma = None
            advance_week(s, rng=rng)
            seen.setdefault((s.season_number, s.season_phase), s.week)
        self.assertEqual(seen[(1, SeasonPhase.OUTDOOR)], 9)
        self.assertEqual(seen[(1, SeasonPhase.CROSS)], 21)
        self.assertEqual(seen[(1, SeasonPhase.INDOOR)], 33)
        self.assertEqual(seen[(2, SeasonPhase.PREPARAZIONE)], 45)  # la stagione 1 si chiude qui, non a settimana 9
        self.assertEqual(seen[(2, SeasonPhase.OUTDOOR)], 53)
        self.assertEqual([h.season for h in s.season_history], [2, 1])  # la 2 si chiude alla settimana 89

    def test_weeks_to_season_end_counts_the_preparation(self) -> None:
        s = empty_career()
        self.assertEqual(s.weeks_to_season_end, 44)
        s.week = 44
        self.assertEqual(s.weeks_to_season_end, 1)

    def test_a_save_without_preparation_keeps_the_old_calendar(self) -> None:
        s = make_state(3)  # prep_weeks = 0
        self.assertEqual((s.season_length, s.prep_weeks), (36, 0))
        self.assertEqual([w for w in range(1, 13) if s.is_race_week(w)], [4, 8, 12])
        self.assertEqual([w for w in range(1, 38) if s.is_phase_start(w)], [1, 13, 25, 37])
        s.week = 1
        self.assertEqual(s.weeks_until_competition, 3)
        self.assertEqual(s.weeks_to_season_end, 36)
        self.assertEqual(s.season_cycle, [SeasonPhase.OUTDOOR, SeasonPhase.CROSS, SeasonPhase.INDOOR])

    def test_the_preparation_has_no_peak_form_bonus_week(self) -> None:
        """`pre_meet` = «la settimana dopo è di gara»: in Preparazione la settimana 3 NON precede la gara della 4."""
        s = empty_career()
        s.week = 3
        self.assertNotEqual(s.weeks_until_competition, 1)


class TestMeetWithoutAthletes(unittest.TestCase):
    def test_the_club_does_not_enter_and_nothing_is_charged_or_given(self) -> None:
        for week, label in ((12, "in casa"), (16, "in trasferta")):
            with self.subTest(week=week):
                s = empty_career()
                s.week, s.season_phase, s.prep_weeks = week, SeasonPhase.OUTDOOR, SEASON_PREP_WEEKS
                before = (s.budget, s.prestige, s.reputation, s.track_condition)
                summary = simulate_competition(s, rng=random.Random(2))
                self.assertTrue(summary.club_absent)
                self.assertEqual(summary.event_results, [])
                self.assertEqual((summary.travel_cost, summary.ticket_income, summary.spectators), (0, 0, 0))
                self.assertEqual((s.budget, s.prestige, s.reputation, s.track_condition), before)
                self.assertFalse([t for t in s.transactions if t.category in ("Trasferte", "Biglietti", "Premi Gara")])
                self.assertIn("non si iscrive", s.news_log[0])
                self.assertIn("nessuna sanzione", s.news_log[0])

    def test_rivals_still_score_and_the_league_table_is_filled(self) -> None:
        s = empty_career()
        s.week, s.season_phase = 12, SeasonPhase.OUTDOOR
        simulate_competition(s, rng=random.Random(2))
        self.assertEqual(s.league_table.get(s.team_name, 0), 0)
        self.assertTrue(sum(v for k, v in s.league_table.items() if k != s.team_name) > 0)

    def test_a_club_with_athletes_still_pays_the_trip_as_before(self) -> None:
        s = make_state(3)
        s.week = 8  # in trasferta
        self.assertFalse(s.next_meet_is_home)
        summary = simulate_competition(s, rng=random.Random(2))
        self.assertFalse(summary.club_absent)
        self.assertGreater(summary.travel_cost, 0)

    def test_many_weeks_with_no_athletes_run_clean(self) -> None:
        s = empty_career()
        start = (s.prestige, s.reputation)
        reports = play(s, 100, random.Random(7))
        meets = [r.competition_summary for r in reports if r.competition_summary is not None]
        self.assertEqual(len(meets), 19)  # 9 + 9 + 1 nelle prime 100 settimane
        self.assertTrue(all(m.club_absent for m in meets))
        self.assertEqual((s.prestige, s.reputation), start)
        cats = {t.category for t in s.transactions}
        self.assertFalse(cats & {"Trasferte", "Biglietti", "Premi Gara", "Rimborsi Atleti", "Interessi"})
        self.assertFalse(s.bankrupt)


class TestFoundationBoard(unittest.TestCase):
    def test_season_one_has_the_foundation_set_and_season_two_the_standard_one(self) -> None:
        s = empty_career()
        self.assertEqual([o.key for o in s.objectives], list(FOUNDATION_KEYS))
        play(s, 44, random.Random(4))
        self.assertEqual(s.season_number, 2)
        self.assertEqual([o.key for o in s.objectives], list(STANDARD_BOARD_KEYS))

    def test_progress_is_read_from_the_state(self) -> None:
        s = empty_career()
        roster = generate_initial_roster(rng=random.Random(1))
        for i, a in enumerate(roster[:4], start=1):
            a.id, a.in_youth_squad = i, i > 2
            s.athletes.append(a)
        values = {o.key: foundation_value(s, o.key) for o in s.objectives}
        self.assertEqual(values, {"found_athletes": 4, "found_youth": 2, "found_meets": 0})
        self.assertEqual(progress_text(s, s.objectives[0]), f"4/{FOUNDATION_MIN_ATHLETES}")

    def test_the_foundation_verdict_is_informative_only(self) -> None:
        s = empty_career()
        s.board_failed_streak = 1  # anche con una stagione fallita alle spalle (partita importata): il conto non si muove
        verdict = settle_season(s, placement=8)
        self.assertTrue(verdict.foundation)
        self.assertFalse(verdict.failed)
        self.assertFalse(verdict.fired)
        self.assertEqual((s.board_failed_streak, s.fired), (1, False))
        self.assertEqual(verdict.passed, 0)

    def test_even_two_foundation_seasons_of_nothing_never_fire_the_manager(self) -> None:
        s = empty_career()
        play(s, 44, random.Random(5))
        self.assertEqual((s.board_failed_streak, s.fired), (0, False))
        record = s.season_history[0]
        self.assertTrue(record.board_foundation)
        self.assertFalse(record.board_failed)

    def test_no_sponsor_cut_and_no_idle_penalty_after_the_foundation_season(self) -> None:
        s = empty_career()
        play(s, 44, random.Random(5))
        self.assertGreater(s.season_history[0].placement, 5)  # ultimi: in una stagione normale taglierebbe lo sponsor
        self.assertFalse(sponsor_cut_active(s))
        self.assertEqual(penalize_idle_athletes(s, 1), 0)

    def test_the_sponsor_cut_still_applies_after_a_normal_season(self) -> None:
        s = empty_career()
        s.season_history.insert(0, SeasonEndResult(season=2, tier=s.tier, placement=7, outcome=SeasonOutcome.STAYED))
        self.assertTrue(sponsor_cut_active(s))

    def test_season_two_target_is_relaxed_by_how_weak_the_squad_is_and_season_three_is_standard(self) -> None:
        s = empty_career()
        base = BOARD_LEAGUE_TARGET[s.tier]
        s.season_number = 2
        self.assertEqual(league_target(s), min(len(s.rivals_in()) + 1, base + BOARD_RAMP_MAX_SLACK))  # rosa vuota: massimo
        roster = generate_initial_roster(rng=random.Random(1))
        for i, a in enumerate(roster, start=1):
            a.id, a.in_youth_squad = i, False
            for stat in ("speed", "stamina", "strength", "technique", "resilience"):
                setattr(a, stat, 95)
        s.athletes = roster
        self.assertEqual(league_target(s), base)  # rosa più forte dei rivali: nessun margine
        s.season_number = 3
        s.athletes = []
        self.assertEqual(league_target(s), base)
        s.season_number, s.prep_weeks = 2, 0
        self.assertEqual(league_target(s), base)  # salvataggi vecchi: mai ammorbidito

    def test_start_new_season_writes_the_relaxed_target_into_the_objective(self) -> None:
        s = empty_career()
        s.season_number = 2
        news = start_new_season(s)
        league = next(o for o in s.objectives if o.key == "board_league")
        self.assertEqual(league.target, league_target(s))
        self.assertIn(str(league.target), news[0])

    def test_foundation_objectives_have_the_expected_targets(self) -> None:
        objs = create_foundation_objectives()
        self.assertEqual([o.key for o in objs], list(FOUNDATION_KEYS))
        self.assertTrue(all(o.target > 0 and not o.completed for o in objs))


if __name__ == "__main__":
    unittest.main()
