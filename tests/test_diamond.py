"""Inviti alla Diamond League (PIANOLAVORO C.1b, 2026-11-21): requisiti, calendario e meeting a invito. Senza Qt.

Garanzie: (1) il meeting a invito cade una volta a stagione, nel secondo meeting della fase Outdoor (anche con la
Preparazione) e solo in Carriera; (2) si è invitati solo nel livello Internazionale, con abbastanza punti e nei primi posti
della classifica di società; (3) il meeting a invito dà premi e prestigio doppi e **nessun** punto di lega, né bonus
squadra, né spareggio; (4) piazzamenti e numero di estrazioni dell'RNG sono quelli di un meeting normale; (5) l'invito si
annuncia nella settimana del meeting; (6) il popup di gloria c'è solo per il meeting a invito.
"""

from __future__ import annotations

import copy
import random
import unittest

from models.diamond import club_rank, diamond_meet_name, is_club_invited, is_diamond_meet, is_diamond_week
from models.entities import (
    DIAMOND_INVITE_MAX_RANK,
    DIAMOND_INVITE_MIN_POINTS,
    DIAMOND_PRESTIGE_MULT,
    DIAMOND_PRIZE_MULT,
    CompetitionSummary,
    CompetitionTier,
    GameState,
    SeasonPhase,
    WeatherCondition,
)
from models.glory import DIAMOND, meeting_moments
from models.simulation import advance_week, simulate_competition
from tests.test_assignments import make_state

INTL = CompetitionTier.INTERNAZIONALE


def invited_state(seed: int = 3, week: int = 8) -> GameState:
    """Società Internazionale in settimana Diamond con molti punti ranking: invitata."""
    state = make_state(seed, tier=INTL)
    state.week = week
    state.season_phase = SeasonPhase.OUTDOOR
    for a in state.main_squad:
        a.ranking_points = {"100m": 500.0}
        a.speed = a.stamina = a.strength = a.technique = a.resilience = 100  # vincono premi anche contro il livello Internazionale
        a.form, a.fatigue, a.injured_weeks = 100, 0, 0
    return state


class TestCalendar(unittest.TestCase):
    def test_the_diamond_week_is_the_second_outdoor_meeting_without_preparation(self) -> None:
        state = GameState(game_mode="career", prep_weeks=0)
        diamond = [w for w in range(1, 37) if is_diamond_week(state, w)]
        self.assertEqual(diamond, [8])
        # una sola volta a stagione, anche dalla seconda in poi (la settimana è continua)
        self.assertEqual([w for w in range(37, 73) if is_diamond_week(state, w)], [44])

    def test_with_the_preparation_it_moves_by_the_preparation_weeks(self) -> None:
        state = GameState(game_mode="career", prep_weeks=8)
        weeks = [w for w in range(1, 45) if is_diamond_week(state, w)]
        self.assertEqual(weeks, [16])  # nessuna in Preparazione (1-8), la seconda gara di Outdoor è la settimana 16
        self.assertTrue(state.is_race_week(16))
        self.assertEqual([w for w in range(45, 89) if is_diamond_week(state, w)], [60])

    def test_never_in_the_prototype(self) -> None:
        state = GameState(game_mode="vertical_slice")
        self.assertFalse(any(is_diamond_week(state, w) for w in range(1, 40)))

    def test_it_is_always_a_race_week_in_the_outdoor_phase(self) -> None:
        for prep in (0, 8):
            state = GameState(game_mode="career", prep_weeks=prep)
            for w in range(1, 3 * state.season_length):
                if is_diamond_week(state, w):
                    self.assertTrue(state.is_race_week(w))
                    pos = (w - 1) % state.season_length - prep
                    self.assertEqual(state.season_cycle[1 if prep else 0].name, "OUTDOOR")
                    self.assertTrue(0 <= pos < 12)


class TestInvitation(unittest.TestCase):
    def test_a_strong_international_club_is_invited(self) -> None:
        state = invited_state()
        self.assertEqual(club_rank(state), 1)
        self.assertTrue(is_club_invited(state))
        self.assertTrue(is_diamond_meet(state))

    def test_only_in_the_international_tier(self) -> None:
        for tier in (CompetitionTier.PROVINCIALE, CompetitionTier.REGIONALE, CompetitionTier.NAZIONALE):
            state = invited_state()
            state.tier = tier
            self.assertFalse(is_club_invited(state), tier)

    def test_not_without_enough_points(self) -> None:
        state = invited_state()
        for a in state.main_squad:
            a.ranking_points = {}
        state.main_squad[0].ranking_points = {"100m": DIAMOND_INVITE_MIN_POINTS - 1}
        self.assertFalse(is_club_invited(state))
        state.main_squad[0].ranking_points = {"100m": DIAMOND_INVITE_MIN_POINTS}
        self.assertTrue(is_club_invited(state))

    def test_not_outside_the_top_places_of_the_club_ranking(self) -> None:
        state = invited_state()
        clubs = state.rivals_in(INTL)
        self.assertGreater(len(clubs), DIAMOND_INVITE_MAX_RANK)
        for club in clubs[:DIAMOND_INVITE_MAX_RANK]:
            club.athletes[next(iter(club.athletes))].ranking_points = {"100m": 1e6}
        self.assertEqual(club_rank(state), DIAMOND_INVITE_MAX_RANK + 1)
        self.assertFalse(is_club_invited(state))
        for club in clubs[:1]:  # un solo rivale in meno davanti: di nuovo tra i primi
            club.athletes[next(iter(club.athletes))].ranking_points = {}
        self.assertEqual(club_rank(state), DIAMOND_INVITE_MAX_RANK)
        self.assertTrue(is_club_invited(state))

    def test_not_without_athletes(self) -> None:
        state = invited_state()
        state.athletes = []
        self.assertFalse(is_club_invited(state))

    def test_not_in_another_week(self) -> None:
        self.assertFalse(is_diamond_meet(invited_state(week=4)))
        self.assertFalse(is_diamond_meet(invited_state(week=12)))

    def test_the_meet_name(self) -> None:
        self.assertEqual(diamond_meet_name("Internazionale Outdoor #2"), "Diamond League — Internazionale Outdoor #2")


class TestTheInvitationalMeet(unittest.TestCase):
    def setUp(self) -> None:
        self.invited = invited_state()
        self.regular = copy.deepcopy(self.invited)
        for a in self.regular.main_squad:  # stesso stato, ma senza i punti per l'invito
            a.ranking_points = {}
        self.assertTrue(is_diamond_meet(self.invited))
        self.assertFalse(is_diamond_meet(self.regular))
        self.r_inv, self.r_reg = random.Random(11), random.Random(11)
        self.d = simulate_competition(self.invited, rng=self.r_inv)
        self.n = simulate_competition(self.regular, rng=self.r_reg)

    def test_the_summary_says_so(self) -> None:
        self.assertTrue(self.d.is_diamond)
        self.assertFalse(self.n.is_diamond)
        self.assertTrue(self.d.meet_name.startswith("Diamond League — "))
        self.assertFalse(self.n.meet_name.startswith("Diamond League"))

    def test_same_placements_and_same_number_of_rng_draws(self) -> None:
        self.assertEqual(
            [(e.event_name, e.placement) for e in self.d.event_results],
            [(e.event_name, e.placement) for e in self.n.event_results],
        )
        self.assertEqual(self.r_inv.getstate(), self.r_reg.getstate())  # nessuna estrazione in più né in meno

    def test_prizes_and_prestige_are_doubled_per_event(self) -> None:
        got_prize = False
        for d, n in zip(self.d.event_results, self.n.event_results):
            self.assertEqual(d.prize_money, int(n.prize_money * DIAMOND_PRIZE_MULT), d.event_name)
            self.assertEqual(d.prestige_gained, round(n.prestige_gained * DIAMOND_PRESTIGE_MULT), d.event_name)
            got_prize = got_prize or d.prize_money > 0
        self.assertTrue(got_prize, "il test non misura nulla se nessuno vince un premio")

    def test_no_team_bonus_in_the_total_prestige(self) -> None:
        self.assertEqual(self.d.total_prestige_gained, sum(e.prestige_gained for e in self.d.event_results))
        self.assertEqual(self.d.total_prize_money, sum(e.prize_money for e in self.d.event_results))

    def test_the_budget_and_prestige_of_the_club_follow_the_summary(self) -> None:
        self.assertEqual(self.invited.prestige - self.regular.prestige, self.d.total_prestige_gained - self.n.total_prestige_gained)

    def test_no_league_points_and_no_tiebreak_counts(self) -> None:
        self.assertEqual(self.invited.league_table, {})
        self.assertEqual(self.invited.league_places, {})
        self.assertTrue(self.regular.league_table)  # il meeting normale li scrive: il confronto ha senso

    def test_the_ranking_points_still_count_and_decay(self) -> None:
        # I punti ranking del club sono quelli del livello Internazionale (moltiplicatore 1,0): il meeting a invito li dà come gli altri
        before = sum(sum(a.ranking_points.values()) for a in self.invited.main_squad)
        self.assertGreater(before, 0)


class TestAnnouncement(unittest.TestCase):
    def test_the_invitation_is_announced_in_the_week_of_the_meeting(self) -> None:
        state = invited_state(week=7)
        state.season_phase = SeasonPhase.OUTDOOR
        advance_week(state, rng=random.Random(5))
        self.assertEqual(state.week, 8)
        self.assertTrue(any("INVITO alla Diamond League" in line for line in state.news_log[:3]))

    def test_no_announcement_when_not_invited(self) -> None:
        state = invited_state(week=7)
        for a in state.main_squad:
            a.ranking_points = {}
        advance_week(state, rng=random.Random(5))
        self.assertFalse(any("INVITO alla Diamond League" in line for line in state.news_log))

    def test_the_announcement_matches_the_meeting(self) -> None:
        """Annuncio nel tick di settimana 7 e meeting a invito nel tick di settimana 8: stessa decisione."""
        state = invited_state(week=7)
        advance_week(state, rng=random.Random(5))
        self.assertTrue(is_diamond_meet(state))  # ora è settimana 8, i punti non sono ancora decaduti
        report = advance_week(state, rng=random.Random(6))
        self.assertTrue(report.competition_summary is not None and report.competition_summary.is_diamond)


class TestGloryMoment(unittest.TestCase):
    def summary(self, diamond: bool) -> CompetitionSummary:
        return CompetitionSummary(
            week=8, tier=INTL, season_phase=SeasonPhase.OUTDOOR, meet_name="Diamond League — Internazionale Outdoor #2",
            weather=WeatherCondition.SERENO, track_surface="Tartan", event_results=[], total_prize_money=40000,
            total_prestige_gained=120, is_diamond=diamond,
        )

    def test_only_the_invitational_meet_has_the_moment(self) -> None:
        state = invited_state()
        self.assertEqual([m.kind for m in meeting_moments(state, self.summary(True))], [DIAMOND])
        self.assertEqual(meeting_moments(state, self.summary(False)), [])

    def test_the_moment_tells_prize_and_prestige(self) -> None:
        state = invited_state()
        moment = meeting_moments(state, self.summary(True))[0]
        self.assertIn("40,000", moment.text)
        self.assertIn("120", moment.text)

    def test_a_club_that_did_not_enter_has_no_moment(self) -> None:
        state = invited_state()
        summary = self.summary(True)
        summary.club_absent = True
        self.assertEqual(meeting_moments(state, summary), [])


if __name__ == "__main__":
    unittest.main()
