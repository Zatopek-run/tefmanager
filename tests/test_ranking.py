"""Lotto C.1: ranking individuale e di società (punti per piazzamento, decadimento, campo sintetico, schema v15).

Solo modello e database: gira senza PyQt6 (`PYTHONPATH=. python3 -m unittest tests.test_ranking`).
"""

from __future__ import annotations

import copy
import random
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from models.database import DatabaseManager
from models.entities import (
    RANKING_DECAY,
    RANKING_HOME_NATION,
    RANKING_NATIONAL_SIZE,
    RANKING_PLACE_POINTS,
    RANKING_SYNTH_ITALIAN_SHARE,
    RANKING_TIER_MULT,
    RANKING_WORLD_SIZE,
    CompetitionTier,
    EventStanding,
    GameState,
    SyntheticAthlete,
)
from models.ranking import (
    athlete_rankings,
    award_event_points,
    club_points,
    club_ranking,
    decay_ranking,
    ensure_ranking_pool,
    generate_synthetic_field,
    national_ranking,
    place_points,
    update_synthetic_field,
    world_ranking,
)
from models.simulation import simulate_competition
from tests.test_assignments import make_state


def standing(name: str, team: str, placement: int, is_player: bool = False) -> EventStanding:
    return EventStanding(name, team, is_player, 10.0, "10.00", placement=placement)


class TestPlacePoints(unittest.TestCase):
    def test_first_place_is_the_top_of_the_table_scaled_by_tier(self) -> None:
        self.assertEqual(RANKING_PLACE_POINTS[0], 100)
        self.assertEqual(RANKING_PLACE_POINTS[1], 80)  # piano: 1° = 100, 2° = 80
        for tier, mult in RANKING_TIER_MULT.items():
            self.assertAlmostEqual(place_points(tier, 1), 100 * mult)
            self.assertAlmostEqual(place_points(tier, 2), 80 * mult)

    def test_points_fall_with_the_place_and_stop_after_the_last(self) -> None:
        values = [place_points(CompetitionTier.INTERNAZIONALE, p) for p in range(1, len(RANKING_PLACE_POINTS) + 1)]
        self.assertEqual(values, sorted(values, reverse=True))
        self.assertGreater(values[-1], 0)
        self.assertEqual(place_points(CompetitionTier.INTERNAZIONALE, len(RANKING_PLACE_POINTS) + 1), 0.0)
        self.assertEqual(place_points(CompetitionTier.INTERNAZIONALE, 0), 0.0)

    def test_the_same_place_is_worth_more_in_a_higher_tier(self) -> None:
        tiers = [CompetitionTier.PROVINCIALE, CompetitionTier.REGIONALE, CompetitionTier.NAZIONALE, CompetitionTier.INTERNAZIONALE]
        values = [place_points(t, 3) for t in tiers]
        self.assertEqual(values, sorted(values))
        self.assertEqual(len(set(values)), 4)


class TestAwarding(unittest.TestCase):
    def test_only_known_holders_get_points(self) -> None:
        state = make_state(3)
        athlete = state.main_squad[0]
        rival = state.rivals_in()[0].athlete_for("100m", "M")
        holders = {(state.team_name, athlete.name): athlete, (state.rivals_in()[0].name, rival.name): rival}
        standings = [
            standing(athlete.name, state.team_name, 1, True),
            standing(rival.name, state.rivals_in()[0].name, 2),
            standing("Sconosciuto", "Altra Squadra", 3),
        ]
        award_event_points(CompetitionTier.REGIONALE, "100m", standings, holders)
        self.assertAlmostEqual(athlete.ranking_points["100m"], 25.0)
        self.assertAlmostEqual(rival.ranking_points["100m"], 20.0)

    def test_a_meeting_gives_every_placed_athlete_the_points_of_their_place(self) -> None:
        state = make_state(3)
        club_by_name = {c.name: c for c in state.rival_clubs}
        summary = simulate_competition(state, rng=random.Random(5))
        checked_player = checked_rival = 0
        for er in summary.event_results:
            if er.withdrew_injured or er.disqualified or er.event_name not in state.active_events:
                continue
            for st in er.standings:
                expected = place_points(state.tier, st.placement)
                if st.is_player:
                    athlete = next(a for a in state.athletes if a.name == st.athlete_name)
                    self.assertAlmostEqual(athlete.ranking_points.get(er.event_name, 0.0), expected, places=1)
                    checked_player += 1
                else:
                    rival = club_by_name[st.team_name].athlete_for(er.event_name, er.gender)
                    self.assertAlmostEqual(rival.ranking_points.get(er.event_name, 0.0), expected, places=1)
                    checked_rival += 1
        self.assertGreater(checked_player, 0)
        self.assertGreater(checked_rival, 0)

    def test_relays_give_no_ranking_points(self) -> None:
        state = make_state(3)
        simulate_competition(state, rng=random.Random(5))
        events = set(state.active_events)
        for athlete in state.athletes:
            self.assertTrue(set(athlete.ranking_points) <= events, athlete.ranking_points)

    def test_injured_athletes_do_not_start_and_score_nothing(self) -> None:
        state = make_state(3)
        # tutti infortunati: nessuno parte, nessun punto al club, solo ai rivali
        for athlete in state.athletes:
            athlete.injured_weeks = 3
        simulate_competition(state, rng=random.Random(5))
        self.assertTrue(all(not a.ranking_points for a in state.athletes))
        self.assertTrue(any(c.athlete_for("100m", "M").ranking_points for c in state.rivals_in()))


class _AlwaysUnlucky(random.Random):
    """`random()` vale sempre 0: ogni controllo «succede se r.random() < p» scatta (ritiro in gara compreso)."""

    def random(self) -> float:
        return 0.0


class TestWithdrawalMidRace(unittest.TestCase):
    def test_an_athlete_who_withdraws_during_the_race_is_not_classified_and_scores_nothing(self) -> None:
        state = make_state(3)
        summary = simulate_competition(state, rng=_AlwaysUnlucky(5))
        withdrawn = [er for er in summary.event_results if er.withdrew_injured and er.event_name in state.active_events]
        self.assertTrue(withdrawn, "nessun ritiro a metà gara simulato")
        self.assertTrue(all(not a.ranking_points for a in state.athletes), [a.ranking_points for a in state.athletes])
        self.assertTrue(any(c.athlete_for("100m", "M").ranking_points for c in state.rivals_in()))


class TestDecay(unittest.TestCase):
    def test_everyone_decays_by_the_same_factor_in_the_same_call(self) -> None:
        state = make_state(3)
        state.ranking_pool = [SyntheticAthlete("Sint Etico", "Kenya", "100m", "M", 80.0, 200.0)]
        state.athletes[0].ranking_points = {"100m": 100.0}
        rival = state.rival_clubs[0].athlete_for("100m", "M")
        rival.ranking_points = {"100m": 50.0}
        decay_ranking(state)
        self.assertAlmostEqual(state.athletes[0].ranking_points["100m"], 100 * RANKING_DECAY, places=2)
        self.assertAlmostEqual(rival.ranking_points["100m"], 50 * RANKING_DECAY, places=2)
        self.assertAlmostEqual(state.ranking_pool[0].points, 200 * RANKING_DECAY, places=2)

    def test_points_that_have_vanished_are_dropped(self) -> None:
        state = make_state(3)
        state.ranking_pool = [SyntheticAthlete("Sint Etico", "Kenya", "100m", "M", 80.0, 1.0)]
        state.athletes[0].ranking_points = {"100m": 0.04, "400m": 10.0}
        decay_ranking(state)
        self.assertNotIn("100m", state.athletes[0].ranking_points)
        self.assertIn("400m", state.athletes[0].ranking_points)

    def test_a_result_loses_half_its_weight_in_about_six_meetings(self) -> None:
        self.assertAlmostEqual(RANKING_DECAY**6, 0.53, places=2)


class TestSyntheticField(unittest.TestCase):
    def test_size_per_event_and_gender(self) -> None:
        state = make_state(3)
        pool = generate_synthetic_field(state, random.Random(1))
        self.assertEqual(len(pool), RANKING_WORLD_SIZE * 2 * len(state.active_events))
        for gender in ("M", "F"):
            for event in state.active_events:
                self.assertEqual(sum(1 for s in pool if s.event == event and s.gender == gender), RANKING_WORLD_SIZE)

    def test_vertical_slice_only_has_its_events(self) -> None:
        state = GameState(game_mode="vertical_slice")
        pool = generate_synthetic_field(state, random.Random(1))
        self.assertEqual({s.event for s in pool}, set(state.active_events))
        self.assertLess(len(state.active_events), 6)

    def test_nationalities_mix_with_a_minority_of_italians(self) -> None:
        pool = generate_synthetic_field(make_state(3), random.Random(1))
        share = sum(1 for s in pool if s.nationality == RANKING_HOME_NATION) / len(pool)
        self.assertAlmostEqual(share, RANKING_SYNTH_ITALIAN_SHARE, delta=0.06)
        self.assertGreater(len({s.nationality for s in pool}), 3)

    def test_same_rng_same_field_and_levels_decrease_with_rank(self) -> None:
        state = make_state(3)
        a = generate_synthetic_field(state, random.Random(7))
        b = generate_synthetic_field(state, random.Random(7))
        self.assertEqual(a, b)
        self.assertNotEqual(a, generate_synthetic_field(state, random.Random(8)))
        sprint = [s for s in a if s.event == "100m" and s.gender == "M"]
        self.assertGreater(sum(s.skill for s in sprint[:10]), sum(s.skill for s in sprint[-10:]) + 100)

    def test_points_start_close_to_steady_state_not_from_zero(self) -> None:
        pool = generate_synthetic_field(make_state(3), random.Random(1))
        self.assertTrue(all(s.points > 0 for s in pool))

    def test_ensure_ranking_pool_creates_the_field_once_with_the_given_rng(self) -> None:
        state = make_state(3)
        self.assertEqual(state.ranking_pool, [])
        rng = random.Random(4)
        self.assertTrue(ensure_ranking_pool(state, rng))
        first = list(state.ranking_pool)
        after_creation = rng.getstate()
        self.assertFalse(ensure_ranking_pool(state, rng))  # c'è già: nessuna estrazione
        self.assertEqual(rng.getstate(), after_creation)
        self.assertEqual(state.ranking_pool, first)
        again = make_state(3)
        ensure_ranking_pool(again, random.Random(4))
        self.assertEqual(again.ranking_pool, first)  # stesso RNG → stesso campo


class TestSyntheticMeeting(unittest.TestCase):
    def setUp(self) -> None:
        self.state = make_state(3)
        ensure_ranking_pool(self.state, random.Random(1))

    def test_without_a_pool_nothing_happens_and_the_rng_is_untouched(self) -> None:
        state = make_state(3)
        rng = random.Random(1)
        before = rng.getstate()
        update_synthetic_field(state, rng)
        self.assertEqual(state.ranking_pool, [])
        self.assertEqual(rng.getstate(), before)

    def test_the_meeting_is_a_function_of_the_pool_and_the_rng(self) -> None:
        """Stesso campo e stesso stato dell'RNG → stessi esiti (l'RNG è salvato: ricaricare non ritira i dadi)."""
        other = copy.deepcopy(self.state)
        update_synthetic_field(self.state, random.Random(9))
        update_synthetic_field(other, random.Random(9))
        self.assertEqual(self.state.ranking_pool, other.ranking_pool)

    def test_another_rng_state_draws_differently(self) -> None:
        other = copy.deepcopy(self.state)
        update_synthetic_field(self.state, random.Random(9))
        update_synthetic_field(other, random.Random(10))
        self.assertNotEqual(self.state.ranking_pool, other.ranking_pool)

    def test_levels_move_a_little_and_points_grow(self) -> None:
        before = copy.deepcopy(self.state.ranking_pool)
        update_synthetic_field(self.state, random.Random(9))
        moved = [abs(a.skill - b.skill) for a, b in zip(before, self.state.ranking_pool)]
        self.assertLess(max(moved), 2.5)
        self.assertGreater(max(moved), 0)
        self.assertTrue(all(a.points >= b.points for a, b in zip(self.state.ranking_pool, before)))

    def test_the_meeting_draws_from_the_game_rng_after_the_league_and_before_the_gate(self) -> None:
        """Passo C-13b del tick: i sintetici consumano `r`; senza campo la sequenza è quella di prima."""
        with_pool = make_state(3)
        ensure_ranking_pool(with_pool, random.Random(2))
        r_with = random.Random(5)
        simulate_competition(with_pool, rng=r_with)
        without = make_state(3)
        r_without = random.Random(5)
        simulate_competition(without, rng=r_without)
        self.assertNotEqual(r_with.getstate(), r_without.getstate())
        self.assertEqual(without.ranking_pool, [])  # senza campo il meeting non lo crea né consuma l'RNG


class TestRankings(unittest.TestCase):
    def setUp(self) -> None:
        self.state = make_state(3)
        ensure_ranking_pool(self.state, random.Random(1))

    def test_world_ranking_is_sorted_by_points_and_numbered_from_one(self) -> None:
        ranking = world_ranking(self.state, "100m", "M")
        self.assertEqual([e.rank for e in ranking], list(range(1, len(ranking) + 1)))
        self.assertEqual([e.points for e in ranking], sorted((e.points for e in ranking), reverse=True))
        self.assertEqual(len(ranking), RANKING_WORLD_SIZE)  # nessuno ha ancora punti nel club né tra i rivali

    def test_ties_are_broken_by_kind_then_name_deterministically(self) -> None:
        state = make_state(3)
        state.ranking_pool = [
            SyntheticAthlete("Zeta", "Italia", "100m", "M", 80.0, 100.0),
            SyntheticAthlete("Alfa", "Italia", "100m", "M", 80.0, 100.0),
        ]
        me = next(a for a in state.athletes if a.gender == "M")
        me.ranking_points = {"100m": 100.0}
        order = [e.name for e in world_ranking(state, "100m", "M")]
        self.assertEqual(order, [me.name, "Alfa", "Zeta"])

    def test_national_ranking_has_only_the_home_nation_and_is_renumbered(self) -> None:
        national = national_ranking(self.state, "100m", "M")
        self.assertTrue(national)
        self.assertTrue(all(e.nationality == RANKING_HOME_NATION for e in national))
        self.assertEqual([e.rank for e in national], list(range(1, len(national) + 1)))
        self.assertLessEqual(len(national[:RANKING_NATIONAL_SIZE]), RANKING_NATIONAL_SIZE)

    def test_genders_are_separate(self) -> None:
        men = {e.name for e in world_ranking(self.state, "100m", "M")}
        women = {e.name for e in world_ranking(self.state, "100m", "F")}
        self.assertFalse(men & women)

    def test_athlete_rankings_for_the_club(self) -> None:
        athlete = next(a for a in self.state.athletes if a.gender == "M")
        self.assertEqual(athlete_rankings(self.state, athlete, "100m"), (None, None, 0.0))
        athlete.ranking_points = {"100m": 100000.0}
        world, national, points = athlete_rankings(self.state, athlete, "100m")
        self.assertEqual((world, national, points), (1, 1, 100000.0))
        athlete.ranking_points = {"100m": 0.5}
        world, national, _ = athlete_rankings(self.state, athlete, "100m")
        self.assertEqual(world, RANKING_WORLD_SIZE + 1)  # sotto tutti i sintetici: fuori dalla Top 100
        self.assertGreater(national, 1)

    def test_club_ranking_is_the_points_earned_in_the_season(self) -> None:
        state = self.state
        club = state.rivals_in()[0]
        state.club_season_points = {state.team_name: 30.0, club.name: 7.0}
        rows = {name: pts for name, pts, _me in club_ranking(state)}
        self.assertEqual(rows[state.team_name], 30.0)
        self.assertEqual(rows[club.name], 7.0)
        self.assertTrue(all(pts == 0.0 for name, pts, _me in club_ranking(state) if name not in (state.team_name, club.name)))
        self.assertEqual([me for _n, _p, me in club_ranking(state)].count(True), 1)
        self.assertEqual({n for n, _p, _m in club_ranking(state)}, {state.team_name, *(c.name for c in state.rivals_in())})

    def test_calibration_a_provincial_winner_stays_out_of_the_top_100_and_an_international_one_leads(self) -> None:
        """Cifre provvisorie (Q26): chi vince sempre in Fase regionale non entra nella Top 100 mondiale, chi vince
        sempre in Finale Oro è tra i primi. Punti a regime = 1° × moltiplicatore ÷ (1 − decadimento)."""
        steady = lambda tier: place_points(tier, 1) / (1 - RANKING_DECAY)
        pool = [s.points for s in self.state.ranking_pool if s.event == "100m" and s.gender == "M"]
        rank = lambda pts: 1 + sum(1 for p in pool if p > pts)
        self.assertGreater(rank(steady(CompetitionTier.PROVINCIALE)), RANKING_WORLD_SIZE)
        self.assertLessEqual(rank(steady(CompetitionTier.REGIONALE)), RANKING_WORLD_SIZE)
        self.assertLessEqual(rank(steady(CompetitionTier.INTERNAZIONALE)), 5)


class TestSeasonClubRanking(unittest.TestCase):
    """Classifica delle società stagionale (Q26, 2026-11-21): conta i punti guadagnati nella stagione in corso e riparte da zero per tutti."""

    def setUp(self) -> None:
        self.state = make_state(3)
        self.state.week = 4

    def test_a_meeting_adds_the_points_earned_to_each_club(self) -> None:
        state = self.state
        simulate_competition(state, rng=random.Random(5))
        self.assertGreater(club_points(state), 0.0)
        # dopo un solo meeting (punti di partenza zero) il contatore di ogni società è la somma dei punti guadagnati dai suoi atleti
        self.assertAlmostEqual(club_points(state), sum(sum(a.ranking_points.values()) for a in state.main_squad), places=1)
        for club in state.rivals_in():
            earned = sum(sum(r.ranking_points.values()) for r in [*club.athletes.values(), *club.female_athletes.values()])
            self.assertAlmostEqual(state.club_season_points.get(club.name, 0.0), earned, places=1, msg=club.name)

    def test_the_season_counter_does_not_decay(self) -> None:
        """I punti degli atleti decadono a ogni meeting (×0,9), la classifica stagionale no: dopo due meeting somma entrambi."""
        state = self.state
        simulate_competition(state, rng=random.Random(5))
        first = club_points(state)
        state.week = 8
        simulate_competition(state, rng=random.Random(6))
        self.assertGreater(club_points(state), first)
        self.assertGreater(club_points(state), sum(sum(a.ranking_points.values()) for a in state.main_squad))

    def test_it_restarts_from_zero_for_everyone_at_the_season_change(self) -> None:
        state = self.state
        rng = random.Random(7)
        simulate_competition(state, rng=rng)
        self.assertTrue(state.club_season_points)
        from models.simulation import advance_week

        start = state.season_number
        for _ in range(60):
            advance_week(state, rng=rng)
            if state.season_number > start:
                break
        self.assertEqual(state.season_number, start + 1)
        self.assertEqual(state.club_season_points, {})
        self.assertTrue(all(points == 0.0 for _name, points, _me in club_ranking(state)))

    def test_nobody_has_a_head_start_after_a_promotion(self) -> None:
        """Il difetto di prima: il club saliva di livello tenendo i suoi punti e risultava 1° contro rivali a zero.
        Ora si azzera la classifica delle società, ma non il ranking individuale degli atleti (Top 100, Top 50)."""
        from models.simulation import advance_week

        state = self.state
        rng = random.Random(7)
        start_tier, start_season = state.tier, state.season_number
        for _ in range(60):
            if state.week == 30:  # il club chiude primo la lega: sarà promosso
                state.league_table = {state.team_name: 9999, **{c.name: 0 for c in state.rivals_in()}}
            advance_week(state, rng=rng)
            if state.season_number > start_season:
                break
        self.assertEqual(state.season_number, start_season + 1)
        self.assertNotEqual(state.tier, start_tier)  # promosso: nuovo livello, nuovi rivali
        self.assertTrue(all(points == 0.0 for _n, points, _m in club_ranking(state)))
        self.assertTrue(any(a.ranking_points for a in state.athletes))  # il ranking individuale resta


class TestPersistence(unittest.TestCase):
    def test_save_and_load_keep_the_season_club_points(self) -> None:
        state = make_state(3)
        state.club_season_points = {state.team_name: 123.5, state.rival_clubs[0].name: 7.25}
        with tempfile.TemporaryDirectory() as tmp:
            db = DatabaseManager(db_path=Path(tmp) / "slot.db")
            db.save_game(state)
            loaded = db.load_game()
        self.assertEqual(loaded.club_season_points, state.club_season_points)

    def test_save_and_load_keep_points_and_the_synthetic_field(self) -> None:
        state = make_state(3)
        ensure_ranking_pool(state, random.Random(1))
        state.athletes[0].ranking_points = {"100m": 12.5, "400m": 3.0}
        state.rival_clubs[0].athletes["100m"].ranking_points = {"100m": 7.0}
        state.rival_clubs[0].female_athletes["100m"].ranking_points = {"100m": 9.0}
        with tempfile.TemporaryDirectory() as tmp:
            db = DatabaseManager(db_path=Path(tmp) / "slot.db")
            db.save_game(state)
            loaded = db.load_game()
        self.assertEqual(loaded.athletes[0].ranking_points, {"100m": 12.5, "400m": 3.0})
        self.assertEqual(loaded.athletes[1].ranking_points, state.athletes[1].ranking_points)
        self.assertEqual(loaded.rival_clubs[0].athletes["100m"].ranking_points, {"100m": 7.0})
        self.assertEqual(loaded.rival_clubs[0].female_athletes["100m"].ranking_points, {"100m": 9.0})
        self.assertEqual(loaded.ranking_pool, state.ranking_pool)

    def test_a_save_without_a_pool_gets_one_when_it_is_upgraded(self) -> None:
        state = make_state(3)
        with tempfile.TemporaryDirectory() as tmp:
            db = DatabaseManager(db_path=Path(tmp) / "slot.db")
            db.save_game(state)
            loaded = db.load_game()
        self.assertEqual(loaded.ranking_pool, [])
        from models.simulation import upgrade_legacy_state

        upgrade_legacy_state(loaded, rng=random.Random(1))
        self.assertTrue(loaded.ranking_pool)
        again = make_state(3)
        upgrade_legacy_state(again, rng=random.Random(1))
        self.assertEqual(again.ranking_pool, loaded.ranking_pool)  # stesso stato e stesso RNG → stesso campo


if __name__ == "__main__":
    unittest.main()
