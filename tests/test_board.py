"""Lotto C.2: obiettivi del Board, verdetto di fine stagione ed esonero (schema v16).

Solo modello e database: gira senza PyQt6 (`PYTHONPATH=. python3 -m unittest tests.test_board`).
"""

from __future__ import annotations

import random
import tempfile
import unittest
from pathlib import Path

from models.board import (
    board_objectives,
    create_board_objectives,
    note_club_record,
    progress_text,
    refresh_board_objectives,
    settle_season,
    start_new_season,
)
from models.database import DatabaseManager
from models.entities import (
    BOARD_KEY_BUDGET,
    BOARD_KEY_LEAGUE,
    BOARD_KEY_RECORDS,
    BOARD_KEYS,
    BOARD_LEAGUE_TARGET,
    BOARD_MAX_FAILED_STREAK,
    BOARD_MIN_RECORDS,
    BOARD_OBJECTIVES_TO_PASS,
    PROMOTION_BONUS,
    CompetitionTier,
    SeasonObjective,
    SeasonOutcome,
)
from models.generator import create_season_objectives
from models.simulation import close_season, simulate_competition
from tests.test_assignments import make_state

BUDGET = 20000


def board_state(budget: int = BUDGET, tier: CompetitionTier = CompetitionTier.PROVINCIALE):
    state = make_state(3, tier)
    state.budget = budget
    state.objectives = create_board_objectives(tier, budget)
    return state


def force_position(state, position: int) -> None:
    names = [c.name for c in state.rivals_in()]
    table, points = {}, 1000
    for pos in range(1, len(names) + 2):
        team = state.team_name if pos == position else names.pop(0)
        table[team] = points
        points -= 100
    state.league_table = table


def close(state, position: int, records: int, budget_ok: bool):
    """Chiude la stagione con un piazzamento, un numero di record e un bilancio dati."""
    force_position(state, position)
    for obj in state.objectives:
        if obj.key == BOARD_KEY_RECORDS:
            obj.value = records
    state.budget = BUDGET if budget_ok else BUDGET - 1
    state.week = 37
    return close_season(state)


class TestCreation(unittest.TestCase):
    def test_three_objectives_with_targets_by_tier(self) -> None:
        for tier in CompetitionTier:
            objs = create_board_objectives(tier, BUDGET)
            self.assertEqual([o.key for o in objs], [BOARD_KEY_LEAGUE, BOARD_KEY_BUDGET, BOARD_KEY_RECORDS])
            by_key = {o.key: o for o in objs}
            self.assertEqual(by_key[BOARD_KEY_LEAGUE].target, BOARD_LEAGUE_TARGET[tier])
            self.assertEqual(by_key[BOARD_KEY_BUDGET].target, BUDGET)
            self.assertEqual(by_key[BOARD_KEY_RECORDS].target, BOARD_MIN_RECORDS)
            self.assertIn(f"{BUDGET:,}", by_key[BOARD_KEY_BUDGET].title)
            self.assertIn(str(BOARD_LEAGUE_TARGET[tier]), by_key[BOARD_KEY_LEAGUE].title)
            self.assertTrue(all(not o.completed and o.value == 0 for o in objs))

    def test_the_target_is_wider_in_higher_tiers(self) -> None:
        targets = [BOARD_LEAGUE_TARGET[t] for t in CompetitionTier]
        self.assertEqual(targets, sorted(targets))
        self.assertEqual(BOARD_LEAGUE_TARGET[CompetitionTier.PROVINCIALE], 3)  # «Top 3 in lega» del piano

    def test_career_gets_the_board_objectives_and_the_prototype_keeps_its_own(self) -> None:
        career = create_season_objectives("career", CompetitionTier.PROVINCIALE, BUDGET)
        self.assertEqual({o.key for o in career}, set(BOARD_KEYS))
        prototype = create_season_objectives("vertical_slice", CompetitionTier.PROVINCIALE)
        self.assertEqual([o.key for o in prototype], ["positive_budget", "win_event", "club_record"])

    def test_board_objectives_ignores_the_old_style_ones(self) -> None:
        state = make_state(3)
        state.objectives = [SeasonObjective("positive_budget", "vecchio")]
        self.assertEqual(board_objectives(state), [])


class TestProgress(unittest.TestCase):
    def test_records_count_and_complete_at_the_target(self) -> None:
        state = board_state()
        records = next(o for o in state.objectives if o.key == BOARD_KEY_RECORDS)
        note_club_record(state)
        self.assertEqual((records.value, records.completed), (1, False))
        note_club_record(state)
        self.assertEqual((records.value, records.completed), (BOARD_MIN_RECORDS, True))

    def test_a_first_meeting_sets_club_records_and_they_are_counted(self) -> None:
        state = board_state()
        summary = simulate_competition(state, rng=random.Random(5))
        made = sum(1 for er in summary.event_results if er.is_club_record)
        self.assertGreater(made, 0)
        records = next(o for o in state.objectives if o.key == BOARD_KEY_RECORDS)
        self.assertEqual(records.value, made)

    def test_budget_is_provisional_and_can_flip_back(self) -> None:
        state = board_state()
        budget = next(o for o in state.objectives if o.key == BOARD_KEY_BUDGET)
        state.budget = BUDGET + 1
        refresh_board_objectives(state)
        self.assertTrue(budget.completed)
        state.budget = BUDGET - 1
        refresh_board_objectives(state)
        self.assertFalse(budget.completed)

    def test_the_league_objective_is_not_decided_before_the_season_ends(self) -> None:
        state = board_state()
        league = next(o for o in state.objectives if o.key == BOARD_KEY_LEAGUE)
        force_position(state, 1)
        refresh_board_objectives(state)
        self.assertFalse(league.completed)
        self.assertIn("1°", progress_text(state, league))

    def test_progress_text_for_each_objective(self) -> None:
        state = board_state()
        texts = {o.key: progress_text(state, o) for o in state.objectives}
        self.assertIn("obiettivo", texts[BOARD_KEY_LEAGUE])
        self.assertIn(f"{state.budget:,}", texts[BOARD_KEY_BUDGET])
        self.assertEqual(texts[BOARD_KEY_RECORDS], f"0/{BOARD_MIN_RECORDS}")


class TestVerdict(unittest.TestCase):
    def test_two_of_three_is_enough_and_one_is_not(self) -> None:
        self.assertEqual(BOARD_OBJECTIVES_TO_PASS, 2)
        for position, records, budget_ok, passed, failed in (
            (1, 5, True, 3, False),
            (1, 5, False, 2, False),  # bilancio mancato
            (8, 5, True, 2, False),  # piazzamento mancato
            (1, 0, True, 2, False),  # record mancati
            (1, 0, False, 1, True),
            (8, 0, True, 1, True),
            (8, 0, False, 0, True),
        ):
            result = close(board_state(), position, records, budget_ok)
            self.assertEqual(sum(1 for _t, ok in result.board_results if ok), passed, (position, records, budget_ok))
            self.assertEqual(result.board_failed, failed, (position, records, budget_ok))
            self.assertEqual(len(result.board_results), 3)

    def test_the_league_target_is_inclusive(self) -> None:
        top = BOARD_LEAGUE_TARGET[CompetitionTier.PROVINCIALE]
        self.assertTrue(dict(close(board_state(), top, 0, False).board_results)[create_board_objectives(CompetitionTier.PROVINCIALE, BUDGET)[0].title])
        result = close(board_state(), top + 1, 0, False)
        self.assertFalse(dict(result.board_results)[create_board_objectives(CompetitionTier.PROVINCIALE, BUDGET)[0].title])

    def test_the_promotion_bonus_does_not_pay_for_the_budget_objective(self) -> None:
        state = board_state()
        result = close(state, 2, 0, False)  # 2° = promozione; budget 1 € sotto la soglia, il bonus lo porterebbe sopra
        self.assertEqual(result.outcome, SeasonOutcome.PROMOTED)
        self.assertGreater(state.budget, BUDGET)
        self.assertFalse(dict(result.board_results)[next(o.title for o in create_board_objectives(CompetitionTier.PROVINCIALE, BUDGET) if o.key == BOARD_KEY_BUDGET)])
        self.assertEqual(state.budget, BUDGET - 1 + PROMOTION_BONUS)

    def test_a_season_without_board_objectives_is_not_judged(self) -> None:
        """Salvataggio precedente a C.2: obiettivi vecchi, nessun verdetto e nessun cambio del conto."""
        state = make_state(3)
        state.objectives = [SeasonObjective("positive_budget", "vecchio"), SeasonObjective("promote", "vecchio")]
        state.board_failed_streak = 1
        force_position(state, 8)
        state.week = 37
        result = close_season(state)
        self.assertIsNone(result.board_failed)
        self.assertEqual(result.board_results, [])
        self.assertEqual(state.board_failed_streak, 1)
        self.assertFalse(state.fired)
        self.assertIsNone(settle_season(state, 8))

    def test_the_verdict_is_written_in_the_news_and_the_history(self) -> None:
        state = board_state()
        result = close(state, 1, 5, True)
        self.assertIn("Board è soddisfatto", state.news_log[1])
        self.assertIs(state.season_history[0], result)
        failed = close(board_state(), 8, 0, False)
        self.assertTrue(failed.board_failed)


class TestFiring(unittest.TestCase):
    def play(self, outcomes: list) -> tuple:
        """`outcomes`: per stagione True = centrata (3 obiettivi), False = fallita (0 obiettivi)."""
        state = board_state()
        results = []
        for ok in outcomes:
            if state.fired:
                break
            state.objectives = create_board_objectives(state.tier, BUDGET)
            results.append(close(state, 1 if ok else 8, 5 if ok else 0, ok))
            state.tier = CompetitionTier.PROVINCIALE  # la promozione non c'entra: si guarda solo il conto
        return state, results

    def test_two_failed_seasons_in_a_row_fire_the_manager(self) -> None:
        self.assertEqual(BOARD_MAX_FAILED_STREAK, 2)
        state, results = self.play([False])
        self.assertEqual((state.board_failed_streak, state.fired), (1, False))
        self.assertFalse(results[0].fired)
        state, results = self.play([False, False])
        self.assertTrue(state.fired)
        self.assertTrue(results[-1].fired)
        self.assertEqual(results[-1].board_streak, 2)
        self.assertIn("ESONERATO", state.milestones[0])

    def test_a_good_season_resets_the_count(self) -> None:
        state, _ = self.play([False, True, False])
        self.assertEqual((state.board_failed_streak, state.fired), (1, False))

    def test_two_failures_that_are_not_in_a_row_do_not_fire(self) -> None:
        state, _ = self.play([False, True, False, True, False])
        self.assertFalse(state.fired)

    def test_a_fired_manager_gets_no_new_objectives(self) -> None:
        state, _ = self.play([False, False])
        before = list(state.objectives)
        self.assertEqual(start_new_season(state), [])
        self.assertEqual(state.objectives, before)

    def test_a_new_season_replaces_the_objectives_with_the_new_level_and_budget(self) -> None:
        state = board_state()
        for obj in state.objectives:
            obj.completed, obj.value = True, 9
        state.tier, state.budget, state.season_number = CompetitionTier.REGIONALE, 31000, 2
        news = start_new_season(state)
        self.assertEqual(len(news), 1)
        by_key = {o.key: o for o in state.objectives}
        self.assertEqual(by_key[BOARD_KEY_LEAGUE].target, BOARD_LEAGUE_TARGET[CompetitionTier.REGIONALE])
        self.assertEqual(by_key[BOARD_KEY_BUDGET].target, 31000)
        self.assertTrue(all(not o.completed and o.value == 0 for o in state.objectives))


class TestPersistence(unittest.TestCase):
    def test_objectives_streak_fired_and_history_survive_a_save(self) -> None:
        state = board_state()
        close(state, 8, 1, False)  # fallita: streak 1
        state.objectives = create_board_objectives(state.tier, state.budget)
        state.objectives[2].value = 1
        state.fired = True
        with tempfile.TemporaryDirectory() as tmp:
            db = DatabaseManager(db_path=Path(tmp) / "slot.db")
            db.save_game(state)
            loaded = db.load_game()
        self.assertEqual(loaded.board_failed_streak, 1)
        self.assertTrue(loaded.fired)
        self.assertEqual([(o.key, o.target, o.value) for o in loaded.objectives], [(o.key, o.target, o.value) for o in state.objectives])
        old, new = state.season_history[0], loaded.season_history[0]
        self.assertEqual((new.board_results, new.board_failed, new.board_streak, new.fired), (old.board_results, old.board_failed, old.board_streak, old.fired))
        self.assertTrue(new.board_failed)

    def test_a_history_entry_without_board_fields_loads_as_not_judged(self) -> None:
        state = make_state(3)
        state.objectives = []
        force_position(state, 4)
        state.week = 37
        close_season(state)  # senza obiettivi del Board: board_failed None
        with tempfile.TemporaryDirectory() as tmp:
            db = DatabaseManager(db_path=Path(tmp) / "slot.db")
            db.save_game(state)
            loaded = db.load_game()
        self.assertIsNone(loaded.season_history[0].board_failed)
        self.assertEqual(loaded.season_history[0].board_results, [])
        self.assertFalse(loaded.fired)


if __name__ == "__main__":
    unittest.main()
