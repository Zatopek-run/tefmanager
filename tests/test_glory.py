"""Momenti di gloria (PIANOLAVORO F.4): quali eventi meritano un popup. Senza Qt.

Garanzie: (1) il record del mondo si riconosce solo con una misura valida e individuale che raggiunge il tetto del gioco; (2) i
tetti di `WORLD_RECORDS` coincidono con quelli che usa davvero la simulazione; (3) l'atleta dell'anno è chi ha più vittorie e
podi nella stagione; (4) nessun RNG.
"""

from __future__ import annotations

import random
import unittest

from models.entities import (
    EVENTS,
    WORLD_RECORDS,
    CompetitionSummary,
    CompetitionTier,
    EventResult,
    EventStanding,
    SeasonEndResult,
    SeasonOutcome,
    SeasonPhase,
    WeatherCondition,
)
from models.glory import (
    ATHLETE_OF_THE_YEAR,
    CHAMPION,
    HISTORIC,
    PROMOTION,
    WORLD_RECORD,
    is_world_record,
    meeting_moments,
    season_awards,
    season_moments,
)
from models.simulation import _score_to_mark
from tests.test_assignments import make_state


def result(name: str, placement: int, event: str = "100m", gender: str = "M", mark: float = 12.0, **kw) -> EventResult:
    return EventResult(
        event_name=event, player_athlete_name=name, placement=placement, total_competitors=8, player_mark=f"{mark:.2f}",
        prize_money=0, prestige_gained=0, gender=gender,
        standings=[EventStanding(athlete_name=name, team_name="Noi", is_player=True, mark_value=mark, mark_display=f"{mark:.2f}")],
        **kw,
    )


def meet(results, week: int = 4, absent: bool = False) -> CompetitionSummary:
    return CompetitionSummary(
        week=week, tier=CompetitionTier.PROVINCIALE, season_phase=SeasonPhase.OUTDOOR, meet_name="Meeting di Prova",
        weather=WeatherCondition.SERENO, track_surface="tartan", event_results=results, total_prize_money=0,
        total_prestige_gained=0, club_absent=absent,
    )


def season_end(outcome=SeasonOutcome.STAYED, placement=4, season=1, new_tier=None) -> SeasonEndResult:
    return SeasonEndResult(season=season, tier=CompetitionTier.PROVINCIALE, placement=placement, outcome=outcome, new_tier=new_tier)


class TestWorldRecordTable(unittest.TestCase):
    def test_every_game_event_has_a_record_for_both_sexes(self) -> None:
        for event in EVENTS:
            for gender in ("M", "F"):
                self.assertIn((event, gender), WORLD_RECORDS, (event, gender))

    def test_the_records_are_the_caps_the_simulation_really_applies(self) -> None:
        """Con un punteggio altissimo `_score_to_mark` si ferma al tetto: deve essere lo stesso numero di `WORLD_RECORDS`."""
        for (event, gender), record in WORLD_RECORDS.items():
            mark, _ = _score_to_mark(EVENTS[event], 500.0, wind_ms=0.0, gender=gender)
            self.assertAlmostEqual(mark, record, places=6, msg=(event, gender))
            self.assertTrue(is_world_record(event, gender, mark), (event, gender))

    def test_direction_of_the_comparison(self) -> None:
        self.assertTrue(is_world_record("100m", "M", 9.58))
        self.assertTrue(is_world_record("100m", "M", 9.50))  # meglio del tetto
        self.assertFalse(is_world_record("100m", "M", 9.59))
        self.assertTrue(is_world_record("Salto in Lungo", "M", 8.95))
        self.assertFalse(is_world_record("Salto in Lungo", "M", 8.94))
        self.assertFalse(is_world_record("Getto del Peso", "F", 10.0))

    def test_unknown_event_is_never_a_record(self) -> None:
        self.assertFalse(is_world_record("Salto in Alto", "M", 100.0))


class TestMeetingMoments(unittest.TestCase):
    def test_a_world_record_makes_a_moment_with_a_log_line(self) -> None:
        state = make_state(3)
        moments = meeting_moments(state, meet([result("Mario Rossi", 1, mark=9.58)]))
        self.assertEqual([m.kind for m in moments], [WORLD_RECORD])
        self.assertIn("Mario Rossi", moments[0].text)
        self.assertTrue(moments[0].log_line.startswith("Sett. 4: RECORD DEL MONDO!"))

    def test_an_ordinary_mark_makes_nothing(self) -> None:
        self.assertEqual(meeting_moments(make_state(3), meet([result("A", 1, mark=10.5)])), [])

    def test_invalid_results_do_not_count(self) -> None:
        state = make_state(3)
        for kw in ({"withdrew_injured": True}, {"disqualified": True}, {"wind_illegal": True}):
            self.assertEqual(meeting_moments(state, meet([result("A", 1, mark=9.58, **kw)])), [], kw)

    def test_relays_do_not_count(self) -> None:
        state = make_state(3)
        self.assertEqual(meeting_moments(state, meet([result("A / B", 1, event="4x100m", mark=0.0)])), [])

    def test_an_absent_club_has_no_moments(self) -> None:
        self.assertEqual(meeting_moments(make_state(3), meet([result("A", 1, mark=9.58)], absent=True)), [])

    def test_a_female_record_uses_the_female_table(self) -> None:
        state = make_state(3)
        self.assertEqual(meeting_moments(state, meet([result("Anna", 1, gender="F", mark=10.49)]))[0].kind, WORLD_RECORD)
        self.assertEqual(meeting_moments(state, meet([result("Anna", 1, gender="F", mark=10.60)])), [])

    def test_new_historic_milestones_become_moments_without_a_new_log_line(self) -> None:
        state = make_state(3)
        line = "Sett. 4: MOMENTO STORICO! Mario Rossi abbatte il muro sub-11.00s nei 100m (M) (10.98s)!"
        moments = meeting_moments(state, meet([]), [line, "Sett. 4: FALLIMENTO! altro"])
        self.assertEqual([m.kind for m in moments], [HISTORIC])
        self.assertIn("Mario Rossi abbatte il muro", moments[0].text)
        self.assertNotIn("Sett. 4", moments[0].text)
        self.assertIsNone(moments[0].log_line)  # la notizia e il traguardo ci sono già


class TestSeasonAwards(unittest.TestCase):
    def state(self):
        state = make_state(3)
        state.prep_weeks = 0  # stagione di 36 settimane: la 1 va dalla sett. 1 alla 36
        state.competition_history = []
        return state

    def add(self, state, week, *results):
        state.competition_history.insert(0, meet(list(results), week=week))

    def test_most_wins_then_most_podiums_then_name(self) -> None:
        state = self.state()
        self.add(state, 4, result("Bruno", 1), result("Carlo", 2, event="400m"), result("Dario", 3, event="800m"))
        self.add(state, 8, result("Bruno", 3), result("Carlo", 1, event="400m"), result("Dario", 3, event="800m"))
        self.add(state, 12, result("Carlo", 3, event="400m"), result("Anna", 1), result("Bruno", 3))
        rows = season_awards(state, 1)
        # Bruno: 1 vittoria e 3 podi; Carlo: 1 vittoria e 3 podi; Anna: 1 vittoria e 1 podio; Dario: 0 vittorie
        self.assertEqual([r[0] for r in rows], ["Bruno", "Carlo", "Anna", "Dario"])
        self.assertEqual(rows[0], ("Bruno", 1, 3))

    def test_only_the_requested_season_counts(self) -> None:
        state = self.state()
        self.add(state, 4, result("Bruno", 1))
        self.add(state, 40, result("Carlo", 1))  # stagione 2
        self.assertEqual([r[0] for r in season_awards(state, 1)], ["Bruno"])
        self.assertEqual([r[0] for r in season_awards(state, 2)], ["Carlo"])

    def test_without_a_podium_nobody_wins_the_award(self) -> None:
        state = self.state()
        self.add(state, 4, result("Bruno", 4), result("Carlo", 5, event="400m"))
        self.assertEqual(season_awards(state, 1), [])
        self.assertEqual(season_moments(state, season_end()), [])

    def test_withdrawn_disqualified_and_relays_do_not_count(self) -> None:
        state = self.state()
        self.add(state, 4, result("Bruno", 1, withdrew_injured=True), result("Carlo", 1, disqualified=True),
                 result("A / B", 1, event="4x100m"))
        self.assertEqual(season_awards(state, 1), [])

    def test_the_preparation_weeks_shift_the_season_window(self) -> None:
        state = self.state()
        state.prep_weeks = 8  # stagione di 44 settimane
        self.add(state, 40, result("Bruno", 1))
        self.assertEqual([r[0] for r in season_awards(state, 1)], ["Bruno"])


class TestSeasonMoments(unittest.TestCase):
    def state(self):
        state = make_state(3)
        state.prep_weeks = 0
        state.competition_history = [meet([result("Bruno", 1)], week=8)]
        return state

    def test_champions_promotion_and_athlete_of_the_year(self) -> None:
        state = self.state()
        champ = season_moments(state, season_end(SeasonOutcome.CHAMPION, 1))
        self.assertEqual([m.kind for m in champ], [CHAMPION, ATHLETE_OF_THE_YEAR])
        promo = season_moments(state, season_end(SeasonOutcome.PROMOTED, 2, new_tier=CompetitionTier.REGIONALE))
        self.assertEqual([m.kind for m in promo], [PROMOTION, ATHLETE_OF_THE_YEAR])
        stayed = season_moments(state, season_end(SeasonOutcome.STAYED))
        self.assertEqual([m.kind for m in stayed], [ATHLETE_OF_THE_YEAR])
        self.assertEqual(season_moments(state, season_end(SeasonOutcome.RELEGATED, 8))[0].kind, ATHLETE_OF_THE_YEAR)

    def test_only_the_athlete_of_the_year_has_a_log_line(self) -> None:
        moments = season_moments(self.state(), season_end(SeasonOutcome.CHAMPION, 1))
        self.assertIsNone(moments[0].log_line)  # il titolo è già nelle notizie (close_season)
        self.assertIn("ATLETA DELL'ANNO", moments[1].log_line)
        self.assertEqual(moments[1].athlete_name, "Bruno")

    def test_it_never_touches_the_random_generators(self) -> None:
        state = self.state()
        random.seed(8)
        before = random.getstate()
        season_moments(state, season_end(SeasonOutcome.CHAMPION, 1))
        meeting_moments(state, meet([result("A", 1, mark=9.58)]))
        self.assertEqual(random.getstate(), before)


if __name__ == "__main__":
    unittest.main()
