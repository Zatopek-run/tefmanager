"""Conferenza stampa (PIANOLAVORO F.2): domande ed effetti di `models/press.py`. Senza Qt.

Garanzie: (1) l'effetto sulla reputazione dipende dal risultato del meeting; (2) la risposta sul futuro sposta solo la
relazione con l'agente dell'atleta citato; (3) senza risposta niente cambia; (4) nessun RNG.
"""

from __future__ import annotations

import random
import unittest

from models.agents import agent_of, ensure_agents
from models.entities import (
    AGENT_RELATION_MAX,
    PRESS_RELATION,
    PRESS_REPUTATION,
    CompetitionSummary,
    CompetitionTier,
    EventResult,
    SeasonPhase,
    WeatherCondition,
)
from models.press import (
    FUTURE,
    FUTURE_OPTIONS,
    PERFORMANCE,
    PERFORMANCE_OPTIONS,
    apply_answers,
    best_athlete_of,
    build_conference,
    performance_tier,
)
from tests.test_assignments import make_state


def result(name: str, placement: int, event: str = "100m", **kw) -> EventResult:
    return EventResult(
        event_name=event, player_athlete_name=name, placement=placement, total_competitors=8, player_mark="10.50",
        prize_money=0, prestige_gained=0, **kw,
    )


def summary(placement: int, teams: int = 6, results=None, week: int = 4, absent: bool = False) -> CompetitionSummary:
    standings = [(f"Club{i}", 100 - 10 * i) for i in range(1, teams + 1)]
    standings[placement - 1] = ("Noi", standings[placement - 1][1])
    return CompetitionSummary(
        week=week, tier=CompetitionTier.PROVINCIALE, season_phase=SeasonPhase.OUTDOOR, meet_name="Meeting di Prova",
        weather=WeatherCondition.SERENO, track_surface="tartan", event_results=results or [], total_prize_money=0,
        total_prestige_gained=0, team_standings=standings, player_team="Noi", club_absent=absent,
    )


def prepared():
    state = make_state(3)
    state.team_name = "Noi"
    state.reputation = 50
    ensure_agents(state)
    return state


class TestTier(unittest.TestCase):
    def test_good_average_and_bad(self) -> None:
        self.assertEqual(performance_tier(summary(1)), "good")
        self.assertEqual(performance_tier(summary(2)), "good")
        self.assertEqual(performance_tier(summary(3)), "average")
        self.assertEqual(performance_tier(summary(4)), "average")
        self.assertEqual(performance_tier(summary(5)), "bad")
        self.assertEqual(performance_tier(summary(6)), "bad")

    def test_a_tiny_field_is_never_good_or_bad(self) -> None:
        self.assertEqual(performance_tier(summary(1, teams=3)), "average")
        self.assertEqual(performance_tier(summary(3, teams=3)), "average")

    def test_every_tier_defines_every_answer(self) -> None:
        for tier, effects in PRESS_REPUTATION.items():
            self.assertEqual(set(effects), set(PERFORMANCE_OPTIONS), tier)
        self.assertEqual(set(PRESS_RELATION), set(FUTURE_OPTIONS))

    def test_answers_are_coherent_with_the_result(self) -> None:
        self.assertGreater(PRESS_REPUTATION["good"]["soddisfatto"], PRESS_REPUTATION["good"]["critico"])
        self.assertLess(PRESS_REPUTATION["bad"]["soddisfatto"], PRESS_REPUTATION["bad"]["critico"])
        for tier in PRESS_REPUTATION:
            self.assertGreaterEqual(PRESS_REPUTATION[tier]["cauto"], 0)  # la risposta prudente non fa mai male


class TestBestAthlete(unittest.TestCase):
    def test_best_placement_wins_and_ties_go_to_the_first_name(self) -> None:
        state = prepared()
        a, b, c = (x.name for x in state.main_squad[:3])
        res = summary(1, results=[result(a, 3), result(b, 1), result(c, 1, event="Salto in Lungo")]).event_results
        s = summary(1, results=res)
        self.assertEqual(best_athlete_of(state, s).name, min(b, c))

    def test_withdrawn_disqualified_unknown_and_youth_do_not_count(self) -> None:
        state = prepared()
        a, b = state.main_squad[0], state.main_squad[1]
        res = [
            result(a.name, 1, withdrew_injured=True),
            result(b.name, 2, disqualified=True),
            result("Staffetta 4x100", 1, event="4x100m"),
            result("Nome Sconosciuto", 1),
        ]
        self.assertIsNone(best_athlete_of(state, summary(1, results=res)))
        b.in_youth_squad = True
        self.assertIsNone(best_athlete_of(state, summary(1, results=[result(b.name, 1)])))


class TestBuild(unittest.TestCase):
    def test_two_questions_when_somebody_raced_one_otherwise(self) -> None:
        state = prepared()
        star = state.main_squad[0].name
        conf = build_conference(state, summary(1, results=[result(star, 1)]))
        self.assertEqual([q.key for q in conf.questions], [PERFORMANCE, FUTURE])
        self.assertEqual(conf.questions[1].athlete_name, star)
        self.assertIn(star, conf.questions[1].text)
        self.assertEqual(conf.tier, "good")
        only = build_conference(state, summary(3))
        self.assertEqual([q.key for q in only.questions], [PERFORMANCE])

    def test_no_conference_for_an_absent_club_or_an_empty_squad(self) -> None:
        state = prepared()
        self.assertIsNone(build_conference(state, summary(1, absent=True)))
        state.athletes = []
        self.assertIsNone(build_conference(state, summary(1)))

    def test_it_is_deterministic_and_does_not_use_the_random_generators(self) -> None:
        state = prepared()
        s = summary(2, results=[result(state.main_squad[0].name, 2)])
        random.seed(3)
        before = random.getstate()
        first = build_conference(state, s)
        self.assertEqual(random.getstate(), before)
        self.assertEqual(first, build_conference(state, s))


class TestApply(unittest.TestCase):
    def conf(self, state, placement: int = 1):
        star = state.main_squad[0]
        return build_conference(state, summary(placement, results=[result(star.name, 1)])), star

    def test_reputation_follows_the_table_for_every_tier_and_answer(self) -> None:
        for placement, tier in ((1, "good"), (3, "average"), (6, "bad")):
            for answer, delta in PRESS_REPUTATION[tier].items():
                state = prepared()
                conf, _ = self.conf(state, placement)
                lines = apply_answers(state, conf, {PERFORMANCE: answer})
                self.assertEqual(state.reputation, 50 + delta, (tier, answer))
                self.assertEqual(len(lines), 1)

    def test_being_satisfied_after_a_last_place_costs_reputation(self) -> None:
        state = prepared()
        conf, _ = self.conf(state, 6)
        apply_answers(state, conf, {PERFORMANCE: "soddisfatto"})
        self.assertLess(state.reputation, 50)

    def test_reputation_stays_between_0_and_100(self) -> None:
        state = prepared()
        state.reputation = 99
        conf, _ = self.conf(state, 1)
        apply_answers(state, conf, {PERFORMANCE: "soddisfatto"})
        self.assertEqual(state.reputation, 100)
        state.reputation = 1
        conf, _ = self.conf(state, 6)
        apply_answers(state, conf, {PERFORMANCE: "soddisfatto"})
        self.assertEqual(state.reputation, 0)

    def test_the_future_answer_moves_only_the_agent_of_the_named_athlete(self) -> None:
        for answer, delta in PRESS_RELATION.items():
            state = prepared()
            conf, star = self.conf(state)
            others = {a.id: a.relation for a in state.agents if a.id != star.agent_id}
            before = agent_of(state, star).relation
            apply_answers(state, conf, {FUTURE: answer})
            self.assertEqual(agent_of(state, star).relation, max(0, min(AGENT_RELATION_MAX, before + delta)), answer)
            self.assertEqual({a.id: a.relation for a in state.agents if a.id != star.agent_id}, others)
            self.assertEqual(state.reputation, 50)  # la domanda sul futuro non tocca la reputazione

    def test_no_answer_no_effect_and_unknown_answers_are_ignored(self) -> None:
        state = prepared()
        conf, star = self.conf(state)
        before = (state.reputation, [a.relation for a in state.agents])
        self.assertEqual(apply_answers(state, conf, {}), [])
        self.assertEqual(apply_answers(state, conf, {PERFORMANCE: "urla", FUTURE: "boh", "altra": "x"}), [])
        self.assertEqual((state.reputation, [a.relation for a in state.agents]), before)

    def test_a_single_answer_is_enough(self) -> None:
        state = prepared()
        conf, star = self.conf(state)
        before = agent_of(state, star).relation
        apply_answers(state, conf, {FUTURE: "punto"})
        self.assertEqual(agent_of(state, star).relation, before + PRESS_RELATION["punto"])
        self.assertEqual(state.reputation, 50)

    def test_the_log_lines_name_the_athlete_and_the_deltas(self) -> None:
        state = prepared()
        conf, star = self.conf(state)
        lines = apply_answers(state, conf, {PERFORMANCE: "critico", FUTURE: "dubbio"})
        self.assertEqual(len(lines), 2)
        self.assertIn("reputazione -2", lines[0])
        self.assertIn(star.name, lines[1])
        self.assertIn("-3", lines[1])


if __name__ == "__main__":
    unittest.main()
