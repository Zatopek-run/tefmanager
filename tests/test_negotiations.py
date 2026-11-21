"""Lotto D.2: trattativa con l'agente (richiesta, offerta, controfferta), bonus per record, clausola rescissoria (schema v19).

Solo modello e database: gira senza PyQt6 (`PYTHONPATH=. python3 -m unittest tests.test_negotiations`).
"""

from __future__ import annotations

import itertools
import math
import random
import tempfile
import unittest
from pathlib import Path

from models.agents import ensure_agents, negotiated_fee
from models.database import DatabaseManager
from models.entities import (
    AGENT_BREAK_FRACTION,
    AGENT_FLEXIBILITY,
    AGENT_FLEXIBILITY_MAX,
    AGENT_RELATION_BROKEN,
    MIN_NEGOTIATED_FEE,
    RECORD_BONUS_OPTIONS,
    RELEASE_CLAUSE_WEEKS,
    Agent,
    AgentPersonality,
)
from models.generator import generate_initial_roster, get_recruitment_fee
from models.market import (
    Negotiation,
    NegotiationState,
    Terms,
    agent_flexibility,
    bonus_options,
    break_fee,
    floor_fee,
    is_valid_terms,
    opening_terms,
)
from models.simulation import advance_week, renew_expiring_contracts
from tests.test_assignments import make_state

AGG, REA, LOY = AgentPersonality.AGGRESSIVE, AgentPersonality.REASONABLE, AgentPersonality.LOYAL


def agent(personality: AgentPersonality = REA, relation: int = 50) -> Agent:
    return Agent(id=1, name="Gigi Agente", personality=personality, relation=relation)


def candidate():
    """Un atleta adulto con un ingaggio standard alto (qualche migliaio di euro: lascia spazio a sconti e bonus)."""
    return max(generate_initial_roster(rng=random.Random(1)), key=lambda a: a.overall)


class TestFlexibilityAndFloor(unittest.TestCase):
    def setUp(self) -> None:
        self.athlete = candidate()

    def test_loyal_agents_give_way_more_than_aggressive_ones(self) -> None:
        self.assertEqual((AGENT_FLEXIBILITY[AGG], AGENT_FLEXIBILITY[REA], AGENT_FLEXIBILITY[LOY]), (0.05, 0.15, 0.25))
        self.assertLess(agent_flexibility(agent(AGG)), agent_flexibility(agent(REA)))
        self.assertLess(agent_flexibility(agent(REA)), agent_flexibility(agent(LOY)))

    def test_a_better_relation_makes_the_agent_more_flexible(self) -> None:
        self.assertAlmostEqual(agent_flexibility(agent(REA, 100)), 0.25)
        self.assertAlmostEqual(agent_flexibility(agent(REA, 0)), 0.05)
        self.assertAlmostEqual(agent_flexibility(agent(AGG, 0)), 0.0)  # non scende sotto zero
        self.assertLessEqual(agent_flexibility(agent(LOY, 100)), AGENT_FLEXIBILITY_MAX)

    def test_opening_terms_are_the_d1_ask(self) -> None:
        for personality, relation in itertools.product((AGG, REA, LOY), (0, 50, 100)):
            ag = agent(personality, relation)
            self.assertEqual(opening_terms(self.athlete, ag), Terms(fee=max(MIN_NEGOTIATED_FEE, negotiated_fee(self.athlete, ag))))

    def test_the_floor_is_the_ask_minus_the_flexibility(self) -> None:
        ag = agent(REA, 50)
        ask = opening_terms(self.athlete, ag).fee
        self.assertEqual(ask, get_recruitment_fee(self.athlete))  # ragionevole a relazione neutra: ingaggio standard
        self.assertEqual(floor_fee(self.athlete, ag), round(ask * 0.85))

    def test_an_aggressive_agent_asks_and_demands_more_than_a_loyal_one(self) -> None:
        agg, loy = agent(AGG), agent(LOY)
        self.assertGreater(opening_terms(self.athlete, agg).fee, opening_terms(self.athlete, loy).fee)
        self.assertGreater(floor_fee(self.athlete, agg), floor_fee(self.athlete, loy))

    def test_the_floor_is_never_above_the_ask_nor_below_the_minimum(self) -> None:
        for a in generate_initial_roster(rng=random.Random(2)):
            for personality, relation in itertools.product((AGG, REA, LOY), (0, 50, 100)):
                ag = agent(personality, relation)
                for bonus in bonus_options(a, ag):
                    floor, ask = floor_fee(a, ag, bonus), opening_terms(a, ag, bonus).fee
                    self.assertGreaterEqual(floor, MIN_NEGOTIATED_FEE)
                    self.assertLessEqual(floor, ask)


class TestBonus(unittest.TestCase):
    def setUp(self) -> None:
        self.athlete = candidate()
        self.agent = agent(REA)

    def test_the_discount_equals_the_bonus(self) -> None:
        base = opening_terms(self.athlete, self.agent).fee
        for bonus in bonus_options(self.athlete, self.agent):
            self.assertEqual(opening_terms(self.athlete, self.agent, bonus), Terms(fee=base - bonus, bonus=bonus))

    def test_only_bonuses_that_leave_a_minimum_fee_are_offered(self) -> None:
        self.assertEqual(bonus_options(self.athlete, self.agent), [0, *RECORD_BONUS_OPTIONS])
        loyal = agent(LOY, 100)  # la richiesta più bassa possibile
        for a in generate_initial_roster(rng=random.Random(1)):
            options = bonus_options(a, loyal)
            ask = opening_terms(a, loyal).fee
            self.assertEqual(options[0], 0)
            self.assertTrue(all(ask - b >= MIN_NEGOTIATED_FEE for b in options), a.name)
            self.assertTrue(set(options) <= {0, *RECORD_BONUS_OPTIONS})

    def test_the_floor_follows_the_discounted_ask(self) -> None:
        plain = floor_fee(self.athlete, self.agent)
        with_bonus = floor_fee(self.athlete, self.agent, RECORD_BONUS_OPTIONS[0])
        self.assertLess(with_bonus, plain)


class TestNegotiationFlow(unittest.TestCase):
    def setUp(self) -> None:
        self.athlete = candidate()
        self.agent = agent(REA)
        self.neg = Negotiation(self.athlete, self.agent)

    def test_accepting_the_ask_closes_at_the_ask(self) -> None:
        terms = self.neg.accept_ask()
        self.assertEqual(terms, self.neg.ask)
        self.assertEqual((self.neg.state, self.neg.terms), (NegotiationState.ACCEPTED, terms))

    def test_an_offer_at_or_above_the_floor_is_accepted_without_a_counter(self) -> None:
        offer = self.neg.floor
        self.assertEqual(self.neg.offer(offer), NegotiationState.ACCEPTED)
        self.assertEqual(self.neg.terms, Terms(fee=offer))
        self.assertIsNone(self.neg.counter)

    def test_an_offer_above_the_ask_still_pays_only_the_ask(self) -> None:
        self.neg.offer(self.neg.ask.fee * 3)
        self.assertEqual(self.neg.terms, self.neg.ask)

    def test_a_lowball_offer_gets_one_counter_halfway_but_not_below_the_floor(self) -> None:
        ask, floor = self.neg.ask.fee, self.neg.floor
        offer = self.neg.break_below  # la più bassa che non rompe la trattativa (Q30b)
        self.assertEqual(self.neg.offer(offer), NegotiationState.COUNTERED)
        assert self.neg.counter is not None
        self.assertEqual(self.neg.counter.fee, max(floor, math.ceil((offer + ask) / 2)))
        self.assertGreaterEqual(self.neg.counter.fee, floor)
        self.assertLessEqual(self.neg.counter.fee, ask)
        self.assertGreater(self.neg.counter.fee, offer)

    def test_an_offer_just_under_the_floor_is_countered_at_the_floor(self) -> None:
        self.neg.offer(self.neg.floor - 1)
        assert self.neg.counter is not None
        self.assertEqual(self.neg.state, NegotiationState.COUNTERED)
        self.assertGreaterEqual(self.neg.counter.fee, self.neg.floor)

    def test_accepting_the_counter_closes_the_deal(self) -> None:
        self.neg.offer(self.neg.break_below)
        counter = self.neg.counter
        self.assertEqual(self.neg.accept_counter(), counter)
        self.assertEqual(self.neg.state, NegotiationState.ACCEPTED)

    def test_there_is_only_one_round_of_counteroffers(self) -> None:
        self.neg.offer(self.neg.break_below)
        with self.assertRaises(ValueError):
            self.neg.offer(self.neg.floor)
        with self.assertRaises(ValueError):
            self.neg.accept_ask()

    def test_refusing_closes_without_terms_from_the_ask_or_the_counter(self) -> None:
        self.neg.refuse()
        self.assertEqual((self.neg.state, self.neg.terms), (NegotiationState.REFUSED, None))
        other = Negotiation(self.athlete, self.agent)
        other.offer(other.break_below)
        other.refuse()
        self.assertEqual((other.state, other.terms), (NegotiationState.REFUSED, None))

    def test_a_closed_negotiation_accepts_no_more_moves(self) -> None:
        self.neg.accept_ask()
        for move in (self.neg.accept_ask, self.neg.refuse, self.neg.accept_counter, lambda: self.neg.offer(500)):
            with self.assertRaises(ValueError):
                move()

    def test_the_bonus_is_chosen_before_answering_and_must_be_one_of_the_options(self) -> None:
        self.neg.set_bonus(RECORD_BONUS_OPTIONS[1])
        self.assertEqual(self.neg.ask.bonus, RECORD_BONUS_OPTIONS[1])
        with self.assertRaises(ValueError):
            self.neg.set_bonus(123)
        self.neg.offer(MIN_NEGOTIATED_FEE)
        with self.assertRaises(ValueError):
            self.neg.set_bonus(0)

    def test_the_bonus_travels_with_the_agreed_terms(self) -> None:
        self.neg.set_bonus(RECORD_BONUS_OPTIONS[0])
        terms = self.neg.accept_ask()
        self.assertEqual(terms.bonus, RECORD_BONUS_OPTIONS[0])

    def test_offers_below_the_minimum_are_refused_as_invalid(self) -> None:
        with self.assertRaises(ValueError):
            self.neg.offer(MIN_NEGOTIATED_FEE - 1)

    def test_an_aggressive_agent_counters_higher_than_a_loyal_one_to_the_same_lowball(self) -> None:
        results = {}
        lowball = Negotiation(self.athlete, agent(AGG)).break_below  # la più bassa che non rompe con nessuno dei due
        for personality in (AGG, LOY):
            n = Negotiation(self.athlete, agent(personality))
            n.offer(lowball)
            results[personality] = n.counter.fee if n.counter else n.terms.fee
        self.assertGreater(results[AGG], results[LOY])

    def test_a_generous_offer_beats_a_stingy_one_for_the_same_agent(self) -> None:
        for personality in (AGG, REA, LOY):
            cheap, fair = Negotiation(self.athlete, agent(personality)), Negotiation(self.athlete, agent(personality))
            cheap.offer(cheap.break_below)
            fair.offer(fair.floor)
            self.assertEqual(fair.state, NegotiationState.ACCEPTED)
            self.assertNotEqual(cheap.state, NegotiationState.ACCEPTED, personality.value)  # un'offerta da 100 € non passa


class TestBrokenNegotiation(unittest.TestCase):
    """Q30b: un'offerta troppo bassa rompe la trattativa e costa relazione."""

    def setUp(self) -> None:
        self.athlete = candidate()
        self.agent = agent(REA)
        self.neg = Negotiation(self.athlete, self.agent)

    def test_the_break_threshold_is_a_fraction_of_the_floor(self) -> None:
        self.assertEqual(self.neg.break_below, round(self.neg.floor * AGENT_BREAK_FRACTION))
        self.assertLess(self.neg.break_below, self.neg.floor)

    def test_an_offer_below_it_breaks_the_negotiation_without_a_counter(self) -> None:
        relation = self.agent.relation
        self.assertEqual(self.neg.offer(self.neg.break_below - 1), NegotiationState.BROKEN)
        self.assertIsNone(self.neg.counter)
        self.assertIsNone(self.neg.terms)
        self.assertTrue(self.neg.is_closed)
        self.assertEqual(self.agent.relation, relation + AGENT_RELATION_BROKEN)

    def test_an_offer_exactly_at_it_is_only_countered_and_costs_nothing(self) -> None:
        relation = self.agent.relation
        self.assertEqual(self.neg.offer(self.neg.break_below), NegotiationState.COUNTERED)
        self.assertEqual(self.agent.relation, relation)

    def test_no_more_moves_after_the_break(self) -> None:
        self.neg.offer(self.neg.break_below - 1)
        for move in (self.neg.accept_ask, self.neg.accept_counter, lambda: self.neg.offer(self.neg.ask.fee)):
            with self.assertRaises(ValueError):
                move()
        with self.assertRaises(ValueError):
            self.neg.refuse()

    def test_the_relation_never_goes_below_zero(self) -> None:
        ag = agent(REA, 1)
        n = Negotiation(self.athlete, ag)
        n.offer(n.break_below - 1)
        self.assertEqual(ag.relation, 0)

    def test_the_cheapest_offer_that_survives_still_pays_the_floor(self) -> None:
        """Limite noto (R27): chi indovina la soglia di rottura (il giocatore non la vede) paga comunque la soglia."""
        n = Negotiation(self.athlete, self.agent)
        n.offer(n.break_below)
        self.assertEqual(n.counter.fee, n.floor)

    def test_a_better_relation_moves_the_threshold_down(self) -> None:
        low, high = Negotiation(self.athlete, agent(REA, 10)), Negotiation(self.athlete, agent(REA, 90))
        self.assertGreater(low.break_below, high.break_below)

    def test_an_aggressive_agent_breaks_earlier_than_a_loyal_one(self) -> None:
        self.assertGreater(Negotiation(self.athlete, agent(AGG)).break_below, Negotiation(self.athlete, agent(LOY)).break_below)


class TestEveryOutcomeIsValid(unittest.TestCase):
    def test_every_terms_the_flow_can_produce_are_valid_for_the_controller(self) -> None:
        for a in generate_initial_roster(rng=random.Random(3))[:6]:
            for personality, relation in itertools.product((AGG, REA, LOY), (0, 50, 100)):
                ag = agent(personality, relation)
                for bonus in bonus_options(a, ag):
                    ask = opening_terms(a, ag, bonus).fee
                    for offer in (MIN_NEGOTIATED_FEE, ask // 2, break_fee(a, ag, bonus), floor_fee(a, ag, bonus), ask, ask * 2):
                        n = Negotiation(a, ag)
                        n.set_bonus(bonus)
                        n.offer(max(MIN_NEGOTIATED_FEE, offer))
                        if n.state is NegotiationState.BROKEN:  # Q30b: nessuna condizione, da qui non si tessera
                            self.assertIsNone(n.terms)
                            continue
                        terms = n.terms if n.state is NegotiationState.ACCEPTED else n.accept_counter()
                        self.assertTrue(is_valid_terms(a, ag, terms), (a.name, personality, relation, bonus, offer))

    def test_forged_terms_are_not_valid(self) -> None:
        a, ag = candidate(), agent(REA)
        floor, ask = floor_fee(a, ag), opening_terms(a, ag).fee
        self.assertTrue(is_valid_terms(a, ag, Terms(fee=floor)))
        self.assertTrue(is_valid_terms(a, ag, Terms(fee=ask)))
        self.assertFalse(is_valid_terms(a, ag, Terms(fee=floor - 1)))  # sotto la soglia
        self.assertFalse(is_valid_terms(a, ag, Terms(fee=ask + 1)))  # più della richiesta
        self.assertFalse(is_valid_terms(a, ag, Terms(fee=ask, bonus=999)))  # bonus che non esiste
        self.assertFalse(is_valid_terms(a, ag, Terms(fee=ask, bonus=RECORD_BONUS_OPTIONS[0])))  # sconto non applicato


class TestReleaseClauseAmount(unittest.TestCase):
    def test_twenty_weeks_of_wage_for_the_main_squad_and_none_for_the_academy(self) -> None:
        a = candidate()
        self.assertEqual(RELEASE_CLAUSE_WEEKS, 20)
        self.assertEqual(a.release_clause_cost, 20 * a.weekly_wage)
        a.in_youth_squad = True
        self.assertEqual(a.release_clause_cost, 0)

    def test_the_clause_range_fits_the_economy(self) -> None:
        clauses = [a.release_clause_cost for a in generate_initial_roster(rng=random.Random(4))]
        self.assertTrue(all(1000 <= c <= 10400 for c in clauses), (min(clauses), max(clauses)))


class TestRecordBonus(unittest.TestCase):
    def meeting_state(self):
        state = make_state(3)
        ensure_agents(state)
        state.week = 4
        return state

    def lineup_athlete(self, state, event: str = "100m"):
        return next(a for a in state.athletes if a.id == state.event_lineup[event])

    def test_a_club_record_pays_the_agreed_bonus_once_per_record(self) -> None:
        state = self.meeting_state()
        star = self.lineup_athlete(state)
        star.record_bonus = 500
        report = advance_week(state, rng=random.Random(5))
        records = [
            er for er in report.competition_summary.event_results
            if er.player_athlete_name == star.name and er.is_club_record and er.event_name == "100m"
        ]
        self.assertTrue(records, "senza record precedenti il primo risultato è record sociale")
        paid = [t for t in state.transactions if t.category == "Bonus Atleti"]
        star_records = [
            er for er in report.competition_summary.event_results
            if er.player_athlete_name == star.name and er.is_club_record and er.event_name not in ("4x100m", "4x400m")
        ]
        self.assertEqual([t.amount for t in paid], [-500] * len(star_records))  # un bonus per ogni record individuale
        self.assertTrue(any("bonus record" in line for line in state.news_log))
        self.assertTrue(all(star.name in t.description for t in paid))

    def test_the_bonus_comes_out_of_the_budget(self) -> None:
        with_bonus, without = self.meeting_state(), self.meeting_state()
        star = self.lineup_athlete(with_bonus)
        star.record_bonus = 700
        advance_week(with_bonus, rng=random.Random(5))
        advance_week(without, rng=random.Random(5))
        paid = -sum(t.amount for t in with_bonus.transactions if t.category == "Bonus Atleti")
        self.assertGreater(paid, 0)
        self.assertEqual(without.budget - with_bonus.budget, paid)  # stessa partita, l'unica differenza è il bonus

    def test_no_bonus_without_a_new_record_and_none_for_athletes_without_the_clause(self) -> None:
        state = self.meeting_state()
        for ev in list(state.event_lineup):
            state.club_records[ev] = (0.001 if ev not in ("Salto in Lungo", "Getto del Peso") else 10 ** 6, "x", "Altro")
        for ev in list(state.event_lineup_f):
            state.club_records_f[ev] = (0.001 if ev not in ("Salto in Lungo", "Getto del Peso") else 10 ** 6, "x", "Altro")
        star = self.lineup_athlete(state)
        star.record_bonus = 500
        advance_week(state, rng=random.Random(5))
        self.assertEqual([t for t in state.transactions if t.category == "Bonus Atleti"], [])

    def test_athletes_without_a_bonus_cost_nothing_extra(self) -> None:
        state = self.meeting_state()
        advance_week(state, rng=random.Random(5))
        self.assertEqual([t for t in state.transactions if t.category == "Bonus Atleti"], [])

    def test_the_bonus_ends_with_the_contract_at_renewal(self) -> None:
        state = make_state(3)
        state.season_number = 2
        athlete = state.main_squad[0]
        athlete.contract_end_season, athlete.record_bonus = 1, 600
        keeper = state.main_squad[1]
        keeper.contract_end_season, keeper.record_bonus = 5, 400  # contratto ancora in corso: il bonus resta
        renew_expiring_contracts(state)
        self.assertEqual((athlete.record_bonus, keeper.record_bonus), (0, 400))


class TestPersistence(unittest.TestCase):
    def test_the_record_bonus_survives_a_reload(self) -> None:
        state = make_state(3)
        state.athletes[0].record_bonus = 600
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "n.db"
            DatabaseManager(db_path=path).save_game(state)
            loaded = DatabaseManager(db_path=path).load_game()
        self.assertEqual([a.record_bonus for a in loaded.athletes], [600] + [0] * (len(state.athletes) - 1))


if __name__ == "__main__":
    unittest.main()
