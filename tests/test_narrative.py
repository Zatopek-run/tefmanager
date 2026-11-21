"""Notizie dinamiche (PIANOLAVORO F.1): il generatore di `models/narrative.py` e il suo aggancio al tick. Senza Qt.

Garanzie: (1) le notizie nascono solo dalle condizioni giuste e solo alla chiusura del mese; (2) al più una riga per tipo;
(3) nessun RNG (le frasi si scelgono con crc32) e quindi nessuno spostamento dell'RNG della partita.
"""

from __future__ import annotations

import random
import unittest

from models.agents import ensure_agents
from models.entities import (
    MONTH_WEEKS,
    NARRATIVE_COACH_REPUTATION,
    NARRATIVE_TENSION_RELATION,
    RETIREMENT_INJURIES_PER_SEASON,
    CompetitionSummary,
    CompetitionTier,
    SeasonPhase,
    WeatherCondition,
)
from models.narrative import (
    coach_award,
    coach_of_the_month_news,
    injuries_news,
    locker_room_news,
    monthly_news,
    press_news,
)
from models.simulation import advance_week
from tests.test_assignments import make_state


def meet(week: int, placement: int, teams: int = 5, name: str = "Meeting di Prova", absent: bool = False) -> CompetitionSummary:
    standings = [(f"Club{i}", 100 - 10 * i) for i in range(1, teams + 1)]  # già in ordine di punti, dal primo all'ultimo
    standings[placement - 1] = ("Noi", standings[placement - 1][1])  # il club occupa esattamente quel posto
    return CompetitionSummary(
        week=week, tier=CompetitionTier.PROVINCIALE, season_phase=SeasonPhase.OUTDOOR, meet_name=name,
        weather=WeatherCondition.SERENO, track_surface="tartan", event_results=[], total_prize_money=0,
        total_prestige_gained=0, team_standings=standings, player_team="Noi", club_absent=absent,
    )


def state_with_agents(seed: int = 3):
    state = make_state(seed)
    state.team_name = "Noi"
    ensure_agents(state)
    for agent in state.agents:
        agent.relation = 60
    return state


class TestLockerRoom(unittest.TestCase):
    def test_nothing_when_everybody_is_calm(self) -> None:
        self.assertIsNone(locker_room_news(state_with_agents()))

    def test_an_unhappy_athlete_makes_the_news(self) -> None:
        state = state_with_agents()
        athlete = state.main_squad[0]
        next(a for a in state.agents if a.id == athlete.agent_id).relation = NARRATIVE_TENSION_RELATION
        text = locker_room_news(state)
        self.assertIsNotNone(text)
        # la relazione è con l'agente: tra i suoi clienti si cita il primo per nome
        clients = sorted(a.name for a in state.main_squad if a.agent_id == athlete.agent_id)
        self.assertIn(clients[0], text)

    def test_just_above_the_threshold_is_calm(self) -> None:
        state = state_with_agents()
        athlete = state.main_squad[0]
        next(a for a in state.agents if a.id == athlete.agent_id).relation = NARRATIVE_TENSION_RELATION + 1
        self.assertIsNone(locker_room_news(state))

    def test_only_the_unhappiest_is_named(self) -> None:
        state = state_with_agents()
        by_agent = {}
        for a in state.main_squad:
            by_agent.setdefault(a.agent_id, []).append(a)
        (id1, _c1), (id2, c2) = list(by_agent.items())[:2]  # due agenti diversi
        agents = {a.id: a for a in state.agents}
        agents[id1].relation = 25
        agents[id2].relation = 10
        self.assertIn(sorted(a.name for a in c2)[0], locker_room_news(state))

    def test_the_youth_squad_is_not_in_the_locker_room(self) -> None:
        state = state_with_agents()
        for a in state.athletes:
            a.in_youth_squad = True
        for agent in state.agents:
            agent.relation = 0
        self.assertIsNone(locker_room_news(state))


class TestPress(unittest.TestCase):
    def test_nothing_when_all_is_fine(self) -> None:
        state = state_with_agents()
        state.budget = 5000
        self.assertIsNone(press_news(state, meet(4, 1)))

    def test_red_figures_make_the_press_critical(self) -> None:
        state = state_with_agents()
        state.budget = -1
        self.assertIn("conti in rosso", press_news(state, None))

    def test_a_failed_board_season_makes_the_press_critical(self) -> None:
        state = state_with_agents()
        state.budget = 5000
        state.board_failed_streak = 1
        self.assertIn("Board", press_news(state, None))

    def test_last_place_in_the_last_meet_makes_the_press_critical(self) -> None:
        state = state_with_agents()
        state.budget = 5000
        self.assertIn("ultimo posto", press_news(state, meet(4, 5)))
        self.assertIsNone(press_news(state, meet(4, 4)))

    def test_budget_beats_the_other_reasons(self) -> None:
        state = state_with_agents()
        state.budget, state.board_failed_streak = -50, 2
        self.assertIn("conti in rosso", press_news(state, meet(4, 5)))


class TestCoachOfTheMonth(unittest.TestCase):
    def test_a_win_earns_the_award(self) -> None:
        state = state_with_agents()
        text = coach_of_the_month_news(state, meet(4, 1, name="Meeting dei Colli"))
        self.assertIn("Allenatore del Mese", text)
        self.assertIn("Meeting dei Colli", text)

    def test_no_award_without_a_win_or_without_a_meet(self) -> None:
        state = state_with_agents()
        self.assertIsNone(coach_of_the_month_news(state, meet(4, 2)))
        self.assertIsNone(coach_of_the_month_news(state, None))


class TestInjuriesNews(unittest.TestCase):
    """Q36b: gli infortuni gravi (3+ in stagione, la soglia del ritiro anticipato) fanno notizia."""

    def test_nothing_below_the_threshold(self) -> None:
        state = state_with_agents()
        for a in state.athletes:
            a.season_injuries = RETIREMENT_INJURIES_PER_SEASON - 1
        self.assertIsNone(injuries_news(state))

    def test_the_most_injured_athlete_is_named_with_the_count(self) -> None:
        state = state_with_agents()
        a, b = state.main_squad[0], state.main_squad[1]
        a.season_injuries, b.season_injuries = RETIREMENT_INJURIES_PER_SEASON, RETIREMENT_INJURIES_PER_SEASON + 2
        text = injuries_news(state)
        self.assertIn(b.name, text)
        self.assertNotIn(a.name, text)
        self.assertIn(str(RETIREMENT_INJURIES_PER_SEASON + 2), text)

    def test_a_veteran_is_said_to_risk_retirement_a_young_one_is_not(self) -> None:
        state = state_with_agents()
        a = state.main_squad[0]
        a.season_injuries = RETIREMENT_INJURIES_PER_SEASON
        a.age = 24
        self.assertNotIn("dire basta", injuries_news(state))
        a.age = 33
        self.assertIn("rischia di dover dire basta", injuries_news(state))

    def test_the_youth_squad_is_not_in_the_news(self) -> None:
        state = state_with_agents()
        for a in state.athletes:
            a.season_injuries = 0
        kid = state.athletes[0]
        kid.in_youth_squad, kid.season_injuries = True, 5
        self.assertIsNone(injuries_news(state))

    def test_it_comes_between_the_press_and_the_locker_room(self) -> None:
        state = state_with_agents()
        state.budget = -100
        state.week = 5
        state.competition_history.insert(0, meet(4, 1))
        a = state.main_squad[0]
        a.season_injuries = RETIREMENT_INJURIES_PER_SEASON
        next(g for g in state.agents if g.id == a.agent_id).relation = 10
        lines = monthly_news(state, 1, 4)
        self.assertEqual(len(lines), 4)
        self.assertIn("Allenatore del Mese", lines[0])
        self.assertIn("conti in rosso", lines[1])
        self.assertIn(a.name, lines[2])
        self.assertIn(str(RETIREMENT_INJURIES_PER_SEASON), lines[2])  # è la riga degli infortuni, non quella dello spogliatoio
        self.assertNotIn("agente", lines[2])


class TestCoachAward(unittest.TestCase):
    """Q36c: «Allenatore del Mese» vale reputazione."""

    def test_award_follows_the_win_of_the_month(self) -> None:
        state = state_with_agents()
        state.competition_history.insert(0, meet(4, 1))
        self.assertTrue(coach_award(state, 1, 4))
        self.assertFalse(coach_award(state, 5, 8))  # un meeting di un altro mese non conta
        state.competition_history[0] = meet(4, 2)
        self.assertFalse(coach_award(state, 1, 4))

    def test_no_award_without_a_squad_or_in_the_foundation_season(self) -> None:
        state = state_with_agents()
        state.competition_history.insert(0, meet(4, 1))
        state.athletes = []
        self.assertFalse(coach_award(state, 1, 4))

    def test_the_line_states_the_bonus(self) -> None:
        text = coach_of_the_month_news(state_with_agents(), meet(4, 1))
        self.assertIn(f"+{NARRATIVE_COACH_REPUTATION} reputazione", text)

    def test_in_the_tick_a_won_month_raises_the_reputation_by_exactly_the_bonus(self) -> None:
        from unittest import mock

        def one_month(award: bool, reputation: int):
            state = state_with_agents()
            state.week, state.reputation, state.transactions = 1, reputation, []
            with mock.patch("models.simulation.coach_award", return_value=award) as patched:
                for _ in range(MONTH_WEEKS):
                    state.pending_dilemma = None
                    advance_week(state, rng=random.Random(state.week))
            return state.reputation, patched.call_count

        (won, calls), (lost, _) = one_month(True, 50), one_month(False, 50)
        self.assertEqual(calls, 1)  # una volta sola, alla chiusura del mese
        self.assertEqual(won - lost, NARRATIVE_COACH_REPUTATION)

    def test_the_reputation_bonus_is_capped_at_100(self) -> None:
        from unittest import mock

        state = state_with_agents()
        state.week, state.reputation, state.transactions = 1, 100, []
        with mock.patch("models.simulation.coach_award", return_value=True):
            for _ in range(MONTH_WEEKS):
                state.pending_dilemma = None
                advance_week(state, rng=random.Random(state.week))
        self.assertLessEqual(state.reputation, 100)


class TestMonthlyNews(unittest.TestCase):
    def prepared(self):
        state = state_with_agents()
        state.budget = -100
        state.week = 5
        state.competition_history.insert(0, meet(4, 1))
        athlete = state.main_squad[0]
        next(a for a in state.agents if a.id == athlete.agent_id).relation = 10
        return state

    def test_one_line_per_kind_in_order_award_press_locker_room(self) -> None:
        lines = monthly_news(self.prepared(), 1, 4)
        self.assertEqual(len(lines), 3)
        self.assertIn("Allenatore del Mese", lines[0])
        self.assertIn("conti in rosso", lines[1])
        self.assertTrue(lines[2].split(": ", 1)[1])
        for line in lines:
            self.assertTrue(line.startswith("Sett. 4: "), line)

    def test_only_the_meet_of_that_month_counts(self) -> None:
        state = self.prepared()
        self.assertFalse(any("Allenatore del Mese" in l for l in monthly_news(state, 5, 8)))  # il meeting è alla sett. 4

    def test_an_absent_club_has_no_meet_of_the_month(self) -> None:
        state = self.prepared()
        state.competition_history[0] = meet(4, 1, absent=True)
        self.assertFalse(any("Allenatore del Mese" in l for l in monthly_news(state, 1, 4)))

    def test_no_news_without_a_main_squad_or_in_the_foundation_season(self) -> None:
        state = self.prepared()
        state.prep_weeks, state.season_number = 8, 1
        self.assertEqual(monthly_news(state, 1, 4), [])
        state.prep_weeks = 0
        state.athletes = []
        self.assertEqual(monthly_news(state, 1, 4), [])

    def test_it_never_touches_the_random_generators(self) -> None:
        state = self.prepared()
        random.seed(5)
        before = random.getstate()
        monthly_news(state, 1, 4)
        self.assertEqual(random.getstate(), before)

    def test_same_state_same_text_and_the_wording_varies_over_weeks(self) -> None:
        state = self.prepared()
        self.assertEqual(monthly_news(state, 1, 4), monthly_news(state, 1, 4))
        seen = set()
        for week in range(5, 5 + 4 * 12, 4):
            state.week = week
            seen.add(coach_of_the_month_news(state, meet(4, 1)))
        self.assertGreater(len(seen), 1)


class TestTickIntegration(unittest.TestCase):
    def run_weeks(self, weeks: int, budget: int = 5000):
        state = state_with_agents()
        state.week, state.transactions, state.budget = 1, [], budget
        state.news_log = []
        seen = []
        for _ in range(weeks):
            state.pending_dilemma = None
            before = len(state.news_log)
            advance_week(state, rng=random.Random(state.week))
            seen.append((state.week, state.news_log[: max(0, len(state.news_log) - before)]))
        return state, seen

    def test_press_news_appears_only_when_a_month_closes(self) -> None:
        state = state_with_agents()
        state.week, state.budget = 1, 5000
        # un conto in rosso permanente: ogni mese chiuso deve produrre la critica, nelle altre settimane no
        press_weeks = []
        for _ in range(MONTH_WEEKS * 3):
            state.pending_dilemma = None
            state.budget = -500
            advance_week(state, rng=random.Random(state.week))
            if any("La stampa critica" in n or "Giornali severi" in n or "Editoriale duro" in n for n in state.news_log[:6]):
                press_weeks.append(state.week)
        self.assertTrue(press_weeks)
        for week in press_weeks:
            self.assertEqual((week - 1) % MONTH_WEEKS, 0, week)

    def test_the_game_rng_is_not_moved_by_the_narrative(self) -> None:
        """Stessa partita con la narrativa spenta e accesa: stesso stato dell'RNG alla fine."""
        from unittest import mock

        def final_rng_state(enabled: bool):
            state = state_with_agents(5)
            state.week = 1
            rng = random.Random(21)
            patch = mock.patch("models.simulation.monthly_news", lambda *_a, **_k: []) if not enabled else mock.patch(
                "models.simulation.monthly_news", wraps=monthly_news
            )
            with patch:
                for _ in range(MONTH_WEEKS * 5):
                    state.pending_dilemma = None
                    advance_week(state, rng=rng)
            return rng.getstate(), [a.speed + a.stamina + a.strength + a.technique for a in state.athletes], state.budget

        self.assertEqual(final_rng_state(True), final_rng_state(False))


if __name__ == "__main__":
    unittest.main()
