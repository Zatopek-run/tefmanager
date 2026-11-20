"""Lotto D.1: agenti con personalità e relazione, ingaggio chiesto all'agente (schema v18).

Solo modello e database: gira senza PyQt6 (`PYTHONPATH=. python3 -m unittest tests.test_agents`).
"""

from __future__ import annotations

import random
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from models.agents import (
    adjust_relation,
    agent_of,
    assign_agent,
    clients_of,
    drift_relations,
    ensure_agents,
    make_agent,
    negotiated_fee,
    penalize_idle_athletes,
    prune_idle_agents,
    raced_names,
)
from models.database import DatabaseManager
from models.entities import (
    AGENT_FEE_MARKUP,
    AGENT_MAX_IDLE,
    AGENT_PERSONALITY_WEIGHTS,
    AGENT_RELATION_FEE_SPAN,
    AGENT_RELATION_IDLE,
    AGENT_RELATION_NOT_RENEWED,
    AGENT_RELATION_PODIUM,
    AGENT_RELATION_RENEWED,
    AGENT_RELATION_START,
    RELAYS,
    SEASON_WEEKS,
    Agent,
    AgentPersonality,
    CompetitionSummary,
    CompetitionTier,
    EventResult,
    GameState,
    Relay,
    SeasonPhase,
    WeatherCondition,
)
from models.generator import generate_initial_roster, get_recruitment_fee
from models.simulation import advance_week, renew_expiring_contracts
from tests.test_assignments import make_state

AGG, REA, LOY = AgentPersonality.AGGRESSIVE, AgentPersonality.REASONABLE, AgentPersonality.LOYAL


def agent(personality: AgentPersonality, relation: int = AGENT_RELATION_START, agent_id: int = 1) -> Agent:
    return Agent(id=agent_id, name="Gigi Agente", personality=personality, relation=relation)


class TestFeeModifier(unittest.TestCase):
    def test_personality_sets_the_ask_at_neutral_relation(self) -> None:
        self.assertEqual((AGENT_FEE_MARKUP[AGG], AGENT_FEE_MARKUP[REA], AGENT_FEE_MARKUP[LOY]), (0.20, 0.0, -0.10))
        self.assertAlmostEqual(agent(AGG).fee_modifier, 0.20)
        self.assertAlmostEqual(agent(REA).fee_modifier, 0.0)
        self.assertAlmostEqual(agent(LOY).fee_modifier, -0.10)

    def test_relation_moves_the_ask_by_up_to_fifteen_points(self) -> None:
        self.assertEqual(AGENT_RELATION_FEE_SPAN, 0.15)
        self.assertAlmostEqual(agent(REA, 100).fee_modifier, -0.15)
        self.assertAlmostEqual(agent(REA, 0).fee_modifier, 0.15)
        self.assertAlmostEqual(agent(REA, 75).fee_modifier, -0.075)
        self.assertAlmostEqual(agent(AGG, 100).fee_modifier, 0.05)  # l'aggressivo con ottimi rapporti chiede ancora un po' più
        self.assertAlmostEqual(agent(LOY, 100).fee_modifier, -0.25)
        self.assertAlmostEqual(agent(LOY, 0).fee_modifier, 0.05)

    def test_labels_follow_the_relation(self) -> None:
        self.assertEqual(
            [agent(REA, r).relation_label for r in (10, 30, 50, 60, 90)], ["Pessima", "Tesa", "Neutra", "Buona", "Ottima"]
        )


class TestNegotiatedFee(unittest.TestCase):
    def setUp(self) -> None:
        self.athlete = generate_initial_roster(rng=random.Random(1))[0]
        self.base = get_recruitment_fee(self.athlete)

    def test_an_aggressive_agent_asks_more_than_a_reasonable_one_and_a_loyal_one_less(self) -> None:
        asks = {p: negotiated_fee(self.athlete, agent(p)) for p in (AGG, REA, LOY)}
        self.assertGreater(asks[AGG], asks[REA])
        self.assertGreater(asks[REA], asks[LOY])
        self.assertEqual(asks[REA], self.base)
        self.assertEqual(asks[AGG], round(self.base * 1.20))
        self.assertEqual(asks[LOY], round(self.base * 0.90))

    def test_better_relation_lowers_the_ask_for_the_same_personality(self) -> None:
        asks = [negotiated_fee(self.athlete, agent(AGG, r)) for r in (0, 50, 100)]
        self.assertEqual(asks, sorted(asks, reverse=True))
        self.assertLess(asks[2], asks[1])

    def test_no_agent_means_the_standard_fee(self) -> None:
        self.assertEqual(negotiated_fee(self.athlete, None), self.base)


class TestAgentGeneration(unittest.TestCase):
    def test_same_inputs_same_agent(self) -> None:
        self.assertEqual(make_agent(4, "Mario Rossi"), make_agent(4, "Mario Rossi"))
        self.assertNotEqual(make_agent(4, "Mario Rossi").name, make_agent(5, "Mario Rossi").name)

    def test_new_agents_start_neutral(self) -> None:
        self.assertEqual(make_agent(1, "X").relation, AGENT_RELATION_START)

    def test_personality_follows_the_weights(self) -> None:
        count = Counter(make_agent(i, f"Atleta {i}").personality for i in range(1, 2001))
        total = sum(AGENT_PERSONALITY_WEIGHTS.values())
        for p, weight in AGENT_PERSONALITY_WEIGHTS.items():
            share = count[p] / 2000
            self.assertAlmostEqual(share, weight / total, delta=0.04, msg=p.value)

    def test_assignment_never_touches_the_global_or_game_rng(self) -> None:
        random.seed(11)
        before = random.getstate()
        state = make_state(3)
        ensure_agents(state)
        self.assertEqual(random.getstate(), before)


class TestAssignment(unittest.TestCase):
    def test_every_athlete_gets_an_agent_and_agents_serve_several_athletes(self) -> None:
        state = make_state(3)
        self.assertGreater(ensure_agents(state), 0)
        self.assertTrue(all(agent_of(state, a) is not None for a in state.athletes))
        self.assertLess(len(state.agents), len(state.athletes))
        self.assertTrue(any(len(clients_of(state, ag)) >= 2 for ag in state.agents))
        self.assertTrue(all(clients_of(state, ag) for ag in state.agents))  # nessun agente creato a vuoto

    def test_ensure_is_idempotent_and_deterministic(self) -> None:
        first, second = make_state(3), make_state(3)
        ensure_agents(first)
        ensure_agents(second)
        self.assertEqual(first.agents, second.agents)
        self.assertEqual([a.agent_id for a in first.athletes], [a.agent_id for a in second.athletes])
        self.assertEqual(ensure_agents(first), 0)

    def test_an_athlete_with_a_valid_agent_keeps_it_and_a_dangling_id_is_reassigned(self) -> None:
        state = make_state(3)
        ensure_agents(state)
        a = state.athletes[0]
        keep = a.agent_id
        assign_agent(state, a)
        self.assertEqual(a.agent_id, keep)
        a.agent_id = 9999
        assign_agent(state, a)
        self.assertIn(a.agent_id, {ag.id for ag in state.agents})

    def test_agent_ids_are_unique(self) -> None:
        state = make_state(3)
        ensure_agents(state)
        ids = [ag.id for ag in state.agents]
        self.assertEqual(len(ids), len(set(ids)))


class TestRelation(unittest.TestCase):
    def test_adjust_clamps_between_0_and_100_and_ignores_unknown_agents(self) -> None:
        state = GameState(agents=[agent(REA, 98)])
        adjust_relation(state, 1, +10)
        self.assertEqual(state.agents[0].relation, 100)
        adjust_relation(state, 1, -250)
        self.assertEqual(state.agents[0].relation, 0)
        self.assertIsNone(adjust_relation(state, 77, +5))
        self.assertIsNone(adjust_relation(state, None, +5))

    def test_automatic_renewal_raises_the_relation_of_each_athlete_agent(self) -> None:
        state = make_state(3)
        ensure_agents(state)
        state.season_number = 2
        target = state.main_squad[0]
        target.contract_end_season = 1  # scaduto con la stagione 1
        ag = agent_of(state, target)
        before = ag.relation
        renew_expiring_contracts(state)
        self.assertEqual(ag.relation, before + AGENT_RELATION_RENEWED)

    def test_not_renewing_lowers_the_relation_and_the_athlete_leaves(self) -> None:
        state = make_state(3)
        ensure_agents(state)
        state.season_number = 2
        target = state.main_squad[0]
        target.contract_end_season, target.contract_no_renew = 1, True
        ag = agent_of(state, target)
        before = ag.relation
        renew_expiring_contracts(state)
        self.assertNotIn(target.id, [a.id for a in state.athletes])
        self.assertEqual(ag.relation, before + AGENT_RELATION_NOT_RENEWED)

    def test_podium_places_raise_the_relation_by_one_each(self) -> None:
        state = make_state(3)
        ensure_agents(state)
        for i, a in enumerate(state.athletes):  # metà fortissimi (podio), metà scarsi (fuori dal podio)
            level = 99 if i % 2 == 0 else 5
            a.speed = a.stamina = a.strength = a.technique = a.resilience = level
            a.form, a.fatigue = (100, 0) if level == 99 else (40, 60)
        before = {ag.id: ag.relation for ag in state.agents}
        report = advance_week(state, rng=random.Random(5))  # settimana 4: gara
        self.assertIsNotNone(report.competition_summary)
        by_name = {a.name: a for a in state.athletes}
        expected: Counter = Counter()
        off_podium = 0
        for er in report.competition_summary.event_results:
            if er.event_name in RELAYS or er.withdrew_injured:
                continue
            if er.placement > 3:
                off_podium += 1
                continue
            expected[by_name[er.player_athlete_name].agent_id] += AGENT_RELATION_PODIUM
        self.assertGreater(sum(expected.values()), 0, "con atleti al massimo almeno un podio c'è")
        self.assertGreater(off_podium, 0, "il test deve distinguere un podio da un piazzamento qualunque")
        for ag in state.agents:
            self.assertEqual(ag.relation, min(100, before[ag.id] + expected[ag.id]), ag.name)

    def test_relays_do_not_move_the_relation(self) -> None:
        state = make_state(3)
        ensure_agents(state)
        for ag in state.agents:
            ag.relation = 40
        for a in state.athletes:
            a.injured_weeks = 0
        # nessuna gara individuale: tolgo le convocazioni individuali e lascio solo le staffette
        state.event_lineup = {e: None for e in state.event_lineup}
        state.event_lineup_f = {e: None for e in state.event_lineup_f}
        advance_week(state, rng=random.Random(5))
        self.assertTrue(all(ag.relation == 40 for ag in state.agents))


class TestDrift(unittest.TestCase):
    def test_each_season_the_relation_closes_a_quarter_of_the_distance_to_neutral(self) -> None:
        state = GameState(agents=[agent(REA, 90, 1), agent(REA, 20, 2), agent(REA, 50, 3), agent(REA, 100, 4)])
        drift_relations(state)
        self.assertEqual([a.relation for a in state.agents], [80, 28, 50, 87])  # 7,5 → 8 e 12,5 → 13: per eccesso

    def test_the_step_is_at_least_one_point_so_values_near_neutral_reach_it(self) -> None:
        state = GameState(agents=[agent(REA, 52, 1), agent(REA, 48, 2), agent(REA, 51, 3), agent(REA, 49, 4)])
        drift_relations(state)
        self.assertEqual([a.relation for a in state.agents], [51, 49, 50, 50])
        drift_relations(state)
        self.assertEqual([a.relation for a in state.agents], [50, 50, 50, 50])

    def _quiet_state(self, week: int, phase: SeasonPhase) -> GameState:
        """Stato senza podi né rinnovi possibili e senza staffette: muovono la relazione solo l'attenuazione e i «fermi»."""
        state = make_state(3)
        ensure_agents(state)
        state.week, state.season_phase = week, phase
        for a in state.athletes:
            a.age = 25
            a.contract_end_season = 9
        for ag in state.agents:
            ag.relation = 90
        state.event_lineup = {e: None for e in state.event_lineup}
        state.event_lineup_f = {e: None for e in state.event_lineup_f}
        state.relays, state.relays_f = {}, {}
        return state

    def test_it_runs_at_the_season_change(self) -> None:
        state = self._quiet_state(36, SeasonPhase.INDOOR)
        advance_week(state, rng=random.Random(4))
        self.assertEqual(state.season_number, 2)
        for ag in state.agents:  # 90 → 80 per l'attenuazione, poi −2 per ogni suo atleta della Prima Squadra rimasto fermo
            fermi = len([a for a in state.main_squad if a.agent_id == ag.id])
            self.assertEqual(ag.relation, 80 + AGENT_RELATION_IDLE * fermi, ag.name)

    def test_it_does_not_run_in_the_middle_of_the_season(self) -> None:
        state = self._quiet_state(8, SeasonPhase.OUTDOOR)
        advance_week(state, rng=random.Random(4))
        self.assertEqual(state.season_number, 1)
        self.assertTrue(all(ag.relation == 90 for ag in state.agents))


def _result(name: str, event: str = "100m") -> EventResult:
    return EventResult(event, name, 5, 8, "11.20", 0, 0)


def _meet(week: int, *results: EventResult) -> CompetitionSummary:
    return CompetitionSummary(
        week, CompetitionTier.PROVINCIALE, SeasonPhase.OUTDOOR, "Meeting", next(iter(WeatherCondition)), "Tartan",
        list(results), 0, 0,
    )


class TestIdleAthletes(unittest.TestCase):
    """«Resta fermo»: scende la relazione con l'agente di chi non è mai stato convocato in una stagione."""

    def setUp(self) -> None:
        roster = generate_initial_roster(rng=random.Random(1))[:4]
        for i, a in enumerate(roster, start=1):
            a.id, a.in_youth_squad, a.agent_id = i, False, i
        self.state = GameState(athletes=roster, agents=[agent(REA, 60, i) for i in range(1, 5)], season_number=2)
        self.names = [a.name for a in roster]
        self.rel = lambda: [ag.relation for ag in self.state.agents]

    def test_only_athletes_never_called_up_lose_relation(self) -> None:
        self.state.competition_history = [_meet(5, _result(self.names[0]), _result(self.names[1], "Salto in Lungo"))]
        self.assertEqual(penalize_idle_athletes(self.state, 1), 2)
        self.assertEqual(self.rel(), [60, 60, 60 + AGENT_RELATION_IDLE, 60 + AGENT_RELATION_IDLE])

    def test_a_meeting_of_another_season_does_not_count(self) -> None:
        self.state.competition_history = [_meet(SEASON_WEEKS + 3, _result(self.names[0]))]  # stagione 2
        penalize_idle_athletes(self.state, 1)
        self.assertEqual(self.rel(), [60 + AGENT_RELATION_IDLE] * 4)
        self.assertEqual(sorted(raced_names(self.state, 2)), [self.names[0]])

    def test_the_first_and_the_last_week_of_the_season_count(self) -> None:
        self.state.competition_history = [_meet(1, _result(self.names[0])), _meet(SEASON_WEEKS, _result(self.names[1]))]
        self.assertEqual(penalize_idle_athletes(self.state, 1), 2)

    def test_a_relay_slot_counts_as_racing_and_so_does_being_withdrawn_before_the_start(self) -> None:
        withdrawn = _result(self.names[1])
        withdrawn.withdrew_injured = True
        self.state.competition_history = [_meet(5, withdrawn)]
        self.state.relays = {"4x100m": Relay("4x100m", member_ids=[3, None, None, None], reserve_id=4)}
        self.assertEqual(penalize_idle_athletes(self.state, 1), 1)  # solo il primo è rimasto fermo
        self.assertEqual(self.rel(), [60 + AGENT_RELATION_IDLE, 60, 60, 60])

    def test_relay_results_in_the_history_are_not_athlete_names(self) -> None:
        self.state.competition_history = [_meet(5, _result("A. Rossi / B. Bianchi / C. Verdi / D. Neri", "4x100m"))]
        self.assertEqual(raced_names(self.state, 1), set())  # le staffette si riconoscono dalla formazione, non dal nome

    def test_the_academy_is_not_penalized(self) -> None:
        self.state.athletes[3].in_youth_squad = True
        self.assertEqual(penalize_idle_athletes(self.state, 1), 3)
        self.assertEqual(self.rel()[3], 60)

    def test_clients_of_the_same_agent_stack(self) -> None:
        for a in self.state.athletes:
            a.agent_id = 1
        penalize_idle_athletes(self.state, 1)
        self.assertEqual(self.state.agents[0].relation, 60 + 4 * AGENT_RELATION_IDLE)

    def test_an_athlete_without_agent_is_ignored(self) -> None:
        self.state.athletes[0].agent_id = None
        self.assertEqual(penalize_idle_athletes(self.state, 1), 4)  # lo conta, ma non c'è relazione da muovere
        self.assertEqual(self.rel(), [60, 60 + AGENT_RELATION_IDLE, 60 + AGENT_RELATION_IDLE, 60 + AGENT_RELATION_IDLE])


class TestPrune(unittest.TestCase):
    def test_idle_neutral_agents_go_and_the_others_stay(self) -> None:
        state = make_state(3)
        ensure_agents(state)
        used = {a.agent_id for a in state.athletes}
        idle_neutral = Agent(id=500, name="Senza Clienti", relation=AGENT_RELATION_START)
        idle_angry = Agent(id=501, name="Arrabbiato", relation=20)
        state.agents += [idle_neutral, idle_angry]
        removed = prune_idle_agents(state)
        ids = {ag.id for ag in state.agents}
        self.assertEqual(removed, 1)
        self.assertNotIn(500, ids)
        self.assertIn(501, ids)
        self.assertTrue(used <= ids)

    def test_the_idle_ones_remembered_are_capped_keeping_the_farthest_from_neutral(self) -> None:
        state = GameState()
        for i in range(AGENT_MAX_IDLE + 5):
            state.agents.append(Agent(id=i + 1, name=f"A{i}", relation=51 + i))  # più alto l'indice, più lontano
        prune_idle_agents(state)
        self.assertEqual(len(state.agents), AGENT_MAX_IDLE)
        self.assertEqual(min(ag.relation for ag in state.agents), 56)  # i 5 più vicini al 50 sono usciti


class TestPersistence(unittest.TestCase):
    def test_agents_and_assignments_survive_a_reload(self) -> None:
        state = make_state(3)
        ensure_agents(state)
        state.agents[0].relation = 83
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.db"
            DatabaseManager(db_path=path).save_game(state)
            loaded = DatabaseManager(db_path=path).load_game()
        self.assertEqual(loaded.agents, state.agents)
        self.assertEqual({a.id: a.agent_id for a in loaded.athletes}, {a.id: a.agent_id for a in state.athletes})

    def test_an_athlete_without_agent_loads_as_none(self) -> None:
        state = make_state(3)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.db"
            DatabaseManager(db_path=path).save_game(state)
            loaded = DatabaseManager(db_path=path).load_game()
        self.assertTrue(all(a.agent_id is None for a in loaded.athletes))
        self.assertEqual(loaded.agents, [])


if __name__ == "__main__":
    unittest.main()
