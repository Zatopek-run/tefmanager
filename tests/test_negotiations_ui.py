"""Lotto D.2 (parte con Qt offscreen): trattativa nel controller e nelle finestre, clausola rescissoria allo svincolo.

Non si prova il mouse reale: si chiamano i metodi che i pulsanti collegano e si leggono tabelle ed etichette.
"""

from __future__ import annotations

import os
import random
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("TEF_NO_GODOT", "1")

from PyQt6.QtWidgets import QApplication, QDialog, QLabel

from controllers.game_controller import GameController
from tests.support import start_game
from models.agents import agent_by_id
from models.database import DatabaseManager
from models.entities import (
    AGENT_RELATION_RELEASED,
    AGENT_RELATION_START,
    MIN_NEGOTIATED_FEE,
    RECORD_BONUS_OPTIONS,
    Agent,
    AgentPersonality,
)
from models.market import NegotiationState, Terms, floor_fee, opening_terms
from views.athlete_dialog import AthleteDetailDialog
from views.dialogs import NegotiationDialog, RecruitAthleteDialog, release_question_text

_app = QApplication.instance() or QApplication([])


class _Base(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "s.db"
        self.ctrl = GameController(db_manager=DatabaseManager(db_path=self.path), rng=random.Random(3), auto_create=False)
        start_game(self.ctrl, team_name="CUS Test", game_mode="career")
        self.state = self.ctrl.state
        self.state.budget = 50000

    def prospect(self, personality: AgentPersonality = AgentPersonality.REASONABLE, relation: int = AGENT_RELATION_START):
        """Un candidato del mercato con un agente noto (nuovo, con la personalità e la relazione volute)."""
        athlete = max(self.ctrl.generate_free_agents(count=4), key=lambda a: get_fee(a))
        agent = Agent(id=max(ag.id for ag in self.state.agents) + 1, name="Gigi Agente", personality=personality, relation=relation)
        self.state.agents.append(agent)
        athlete.agent_id = agent.id
        return athlete, agent


def get_fee(athlete) -> int:
    from models.generator import get_recruitment_fee

    return get_recruitment_fee(athlete)


class TestRecruitWithTerms(_Base):
    def test_the_agreed_fee_is_paid_and_the_bonus_is_written_on_the_athlete(self) -> None:
        athlete, agent = self.prospect()
        terms = opening_terms(athlete, agent, RECORD_BONUS_OPTIONS[0])
        before = self.state.budget
        self.assertTrue(self.ctrl.recruit_athlete(athlete, terms=terms))
        self.assertEqual(before - self.state.budget, terms.fee)
        self.assertEqual(self.state.transactions[0].amount, -terms.fee)
        self.assertEqual(athlete.record_bonus, RECORD_BONUS_OPTIONS[0])
        self.assertIn(athlete, self.state.athletes)

    def test_a_discounted_offer_costs_less_than_the_ask(self) -> None:
        athlete, agent = self.prospect()
        terms = Terms(fee=floor_fee(athlete, agent))
        self.assertLess(terms.fee, opening_terms(athlete, agent).fee)
        before = self.state.budget
        self.assertTrue(self.ctrl.recruit_athlete(athlete, terms=terms))
        self.assertEqual(before - self.state.budget, terms.fee)

    def test_without_terms_the_agent_ask_is_paid_and_there_is_no_bonus(self) -> None:
        athlete, agent = self.prospect(AgentPersonality.AGGRESSIVE)
        before = self.state.budget
        self.assertTrue(self.ctrl.recruit_athlete(athlete))
        self.assertEqual(before - self.state.budget, opening_terms(athlete, agent).fee)
        self.assertEqual(athlete.record_bonus, 0)

    def test_forged_terms_are_refused_and_nothing_is_charged(self) -> None:
        athlete, agent = self.prospect()
        before, squad = self.state.budget, len(self.state.athletes)
        for bad in (Terms(fee=floor_fee(athlete, agent) - 1), Terms(fee=opening_terms(athlete, agent).fee + 1), Terms(fee=900, bonus=5)):
            self.assertFalse(self.ctrl.recruit_athlete(athlete, terms=bad), bad)
        self.assertEqual((self.state.budget, len(self.state.athletes)), (before, squad))

    def test_it_refuses_when_the_agreed_fee_exceeds_the_budget(self) -> None:
        athlete, agent = self.prospect()
        terms = opening_terms(athlete, agent)
        self.state.budget = terms.fee - 1
        self.assertFalse(self.ctrl.recruit_athlete(athlete, terms=terms))
        self.assertNotIn(athlete, self.state.athletes)

    def test_the_bonus_survives_a_reload(self) -> None:
        athlete, agent = self.prospect()
        self.ctrl.recruit_athlete(athlete, terms=opening_terms(athlete, agent, RECORD_BONUS_OPTIONS[1]))
        other = GameController(db_manager=DatabaseManager(db_path=self.path), rng=random.Random(1), auto_create=False)
        self.assertTrue(other.load_game())
        self.assertEqual(next(a for a in other.state.athletes if a.name == athlete.name).record_bonus, RECORD_BONUS_OPTIONS[1])


class TestReleaseClause(_Base):
    def test_releasing_a_main_squad_athlete_pays_the_clause(self) -> None:
        target = self.state.main_squad[0]
        clause = target.release_clause_cost
        self.assertGreater(clause, 0)
        before = self.state.budget
        self.assertTrue(self.ctrl.release_athlete(target.id))
        self.assertEqual(before - self.state.budget, clause)
        self.assertEqual(self.state.transactions[0].category, "Clausola")
        self.assertEqual(self.state.transactions[0].amount, -clause)
        self.assertNotIn(target.id, [a.id for a in self.state.athletes])

    def test_without_the_money_the_release_is_refused_and_nothing_changes(self) -> None:
        target = self.state.main_squad[0]
        self.state.budget = target.release_clause_cost - 1
        squad, fidelity = len(self.state.athletes), self.state.fidelity
        relation = agent_by_id(self.state, target.agent_id).relation
        self.assertFalse(self.ctrl.release_athlete(target.id))
        self.assertEqual(len(self.state.athletes), squad)
        self.assertEqual(self.state.budget, target.release_clause_cost - 1)
        self.assertEqual(self.state.fidelity, fidelity)
        self.assertEqual(agent_by_id(self.state, target.agent_id).relation, relation)  # l'agente non ne sa nulla

    def test_the_academy_has_no_clause(self) -> None:
        kid = self.ctrl.run_youth_scouting()[0]
        self.assertTrue(self.ctrl.sign_youth(kid))
        before = self.state.budget
        self.assertTrue(self.ctrl.release_athlete(kid.id))
        self.assertEqual(self.state.budget, before)

    def test_releasing_still_costs_fidelity_and_relation(self) -> None:
        shared = next(ag for ag in self.state.agents if len([a for a in self.state.main_squad if a.agent_id == ag.id]) >= 2)
        target = next(a for a in self.state.main_squad if a.agent_id == shared.id)
        self.assertTrue(self.ctrl.release_athlete(target.id))
        self.assertEqual(shared.relation, AGENT_RELATION_START + AGENT_RELATION_RELEASED)

    def test_the_confirmation_text_states_the_clause(self) -> None:
        target = self.state.main_squad[0]
        text = release_question_text(target, self.state.budget)
        self.assertIn(target.name, text)
        self.assertIn(f"€{target.release_clause_cost:,}", text)
        self.assertIn("Non rinnovare", text)
        target.in_youth_squad = True
        self.assertNotIn("Clausola", release_question_text(target, self.state.budget))


class TestNegotiationDialog(_Base):
    def dialog(self, personality=AgentPersonality.REASONABLE, relation=AGENT_RELATION_START, budget=50000):
        athlete, agent = self.prospect(personality, relation)
        dlg = NegotiationDialog(athlete, agent, budget)
        self.addCleanup(dlg.close)
        return dlg, athlete, agent

    def test_it_opens_on_the_agent_ask_with_the_bonus_choices(self) -> None:
        dlg, athlete, agent = self.dialog()
        self.assertEqual([dlg.bonus_combo.itemData(i) for i in range(dlg.bonus_combo.count())], [0, *RECORD_BONUS_OPTIONS])
        self.assertIn(f"€{opening_terms(athlete, agent).fee:,}", dlg.ask_label.text())
        self.assertEqual(dlg.offer_spin.value(), opening_terms(athlete, agent).fee)
        self.assertEqual(dlg.offer_spin.maximum(), opening_terms(athlete, agent).fee)
        self.assertTrue(dlg.btn_accept_ask.isEnabled() and not dlg.btn_accept_counter.isVisibleTo(dlg))

    def test_accepting_the_ask_closes_with_those_terms(self) -> None:
        dlg, athlete, agent = self.dialog()
        dlg._accept_ask()
        self.assertEqual(dlg.selected_terms, opening_terms(athlete, agent))
        self.assertEqual(dlg.result(), QDialog.DialogCode.Accepted)

    def test_choosing_a_bonus_lowers_the_ask(self) -> None:
        dlg, athlete, agent = self.dialog()
        dlg.bonus_combo.setCurrentIndex(2)  # 600 €
        self.assertEqual(dlg.negotiation.ask, opening_terms(athlete, agent, RECORD_BONUS_OPTIONS[1]))
        self.assertEqual(dlg.offer_spin.maximum(), dlg.negotiation.ask.fee)
        dlg._accept_ask()
        self.assertEqual(dlg.selected_terms.bonus, RECORD_BONUS_OPTIONS[1])

    def test_an_offer_at_the_floor_is_accepted_straight_away(self) -> None:
        dlg, athlete, agent = self.dialog()
        dlg.offer_spin.setValue(floor_fee(athlete, agent))
        dlg._propose()
        self.assertEqual(dlg.selected_terms, Terms(fee=floor_fee(athlete, agent)))
        self.assertEqual(dlg.result(), QDialog.DialogCode.Accepted)

    def test_a_low_offer_gets_a_counter_and_then_only_accept_or_refuse(self) -> None:
        dlg, athlete, agent = self.dialog()
        dlg.offer_spin.setValue(MIN_NEGOTIATED_FEE)
        dlg._propose()
        self.assertEqual(dlg.negotiation.state, NegotiationState.COUNTERED)
        self.assertIsNone(dlg.selected_terms)
        self.assertFalse(dlg.offer_spin.isEnabled() or dlg.bonus_combo.isEnabled())
        self.assertTrue(dlg.btn_accept_counter.isVisibleTo(dlg) and not dlg.btn_offer.isVisibleTo(dlg))
        self.assertIn(f"€{dlg.negotiation.counter.fee:,}", dlg.status_label.text())
        dlg._accept_counter()
        self.assertEqual(dlg.selected_terms, dlg.negotiation.counter)
        self.assertEqual(dlg.result(), QDialog.DialogCode.Accepted)

    def test_refusing_closes_without_terms(self) -> None:
        dlg, *_ = self.dialog()
        dlg._refuse()
        self.assertIsNone(dlg.selected_terms)
        self.assertEqual(dlg.result(), QDialog.DialogCode.Rejected)
        self.assertEqual(dlg.negotiation.state, NegotiationState.REFUSED)

    def test_refusing_the_counter_closes_without_terms(self) -> None:
        dlg, *_ = self.dialog()
        dlg.offer_spin.setValue(MIN_NEGOTIATED_FEE)
        dlg._propose()
        dlg._refuse()
        self.assertIsNone(dlg.selected_terms)
        self.assertEqual(dlg.result(), QDialog.DialogCode.Rejected)

    def test_with_little_money_the_ask_cannot_be_accepted_but_a_cheaper_offer_can(self) -> None:
        athlete, agent = self.prospect()
        floor, ask = floor_fee(athlete, agent), opening_terms(athlete, agent).fee
        budget = (floor + ask) // 2  # basta per la soglia, non per la richiesta
        dlg = NegotiationDialog(athlete, agent, budget)
        self.addCleanup(dlg.close)
        self.assertFalse(dlg.btn_accept_ask.isEnabled())
        dlg._accept_ask()
        self.assertIsNone(dlg.selected_terms)
        dlg.offer_spin.setValue(floor)
        dlg._propose()
        self.assertEqual(dlg.selected_terms, Terms(fee=floor))

    def test_an_offer_above_the_budget_is_not_sent(self) -> None:
        athlete, agent = self.prospect()
        dlg = NegotiationDialog(athlete, agent, MIN_NEGOTIATED_FEE + 5)
        self.addCleanup(dlg.close)
        dlg.offer_spin.setValue(MIN_NEGOTIATED_FEE + 50)
        dlg._propose()
        self.assertEqual(dlg.negotiation.state, NegotiationState.OPEN)
        self.assertIn("Fondi insufficienti", dlg.status_label.text())

    def test_the_counter_cannot_be_accepted_without_the_money(self) -> None:
        athlete, agent = self.prospect()
        dlg = NegotiationDialog(athlete, agent, opening_terms(athlete, agent).fee)
        self.addCleanup(dlg.close)
        dlg.offer_spin.setValue(MIN_NEGOTIATED_FEE)
        dlg._propose()
        dlg.budget = MIN_NEGOTIATED_FEE  # i soldi finiscono mentre si pensa
        dlg._refresh()
        self.assertFalse(dlg.btn_accept_counter.isEnabled())
        dlg._accept_counter()
        self.assertIsNone(dlg.selected_terms)


class TestRecruitDialogUsesTheNegotiation(_Base):
    def build(self):
        pool = self.ctrl.get_free_agent_market(count=4)
        dlg = RecruitAthleteDialog(pool, self.state.budget, roster=self.state.main_squad, agents=self.state.agents)
        self.addCleanup(dlg.close)
        return dlg, pool

    def test_signing_with_an_agent_goes_through_the_negotiation(self) -> None:
        dlg, pool = self.build()
        seen = []
        agreed = Terms(fee=700, bonus=0)
        dlg._negotiate = lambda prospect, agent: (seen.append((prospect, agent)), agreed)[1]
        dlg.table.selectRow(1)
        dlg._on_sign()
        self.assertEqual(seen[0][0], pool[1])
        self.assertEqual(seen[0][1], agent_by_id(self.state, pool[1].agent_id))
        self.assertEqual((dlg.selected_prospect, dlg.selected_terms), (pool[1], agreed))
        self.assertEqual(dlg.result(), QDialog.DialogCode.Accepted)

    def test_walking_away_from_the_negotiation_signs_nobody(self) -> None:
        dlg, _pool = self.build()
        dlg._negotiate = lambda prospect, agent: None
        dlg.table.selectRow(0)
        dlg._on_sign()
        self.assertIsNone(dlg.selected_prospect)
        self.assertIsNone(dlg.selected_terms)
        self.assertNotEqual(dlg.result(), QDialog.DialogCode.Accepted)

    def test_without_agents_the_old_flow_applies_and_there_are_no_terms(self) -> None:
        pool = self.ctrl.generate_free_agents(count=2)
        dlg = RecruitAthleteDialog(pool, 50000)
        self.addCleanup(dlg.close)
        dlg._negotiate = lambda prospect, agent: self.fail("senza agente non si tratta")
        dlg.table.selectRow(0)
        dlg._on_sign()
        self.assertEqual(dlg.selected_prospect, pool[0])
        self.assertIsNone(dlg.selected_terms)


class TestAthleteCard(_Base):
    def text(self, athlete) -> str:
        dlg = AthleteDetailDialog(self.ctrl, athlete.id)
        self.addCleanup(dlg.close)
        return " ".join(label.text() for label in dlg.overview_page.findChildren(QLabel))

    def test_the_card_shows_the_clause_and_the_bonus(self) -> None:
        athlete = self.state.main_squad[0]
        self.assertIn(f"€{athlete.release_clause_cost:,}", self.text(athlete))
        athlete.record_bonus = 600
        self.assertIn("+ €600/rec.", self.text(athlete))

    def test_the_academy_shows_a_dash(self) -> None:
        kid = self.ctrl.run_youth_scouting()[0]
        self.ctrl.sign_youth(kid)
        dlg = AthleteDetailDialog(self.ctrl, kid.id)
        self.addCleanup(dlg.close)
        self.assertEqual(dlg._clause_text(kid), "—")


if __name__ == "__main__":
    unittest.main()
