"""Lotto D.1 (parte con Qt offscreen): agenti nel controller, nel mercato e nella scheda atleta.

Non si prova il mouse reale: si leggono tabelle ed etichette e si chiamano i metodi che i pulsanti collegano.
"""

from __future__ import annotations

import os
import random
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("TEF_NO_GODOT", "1")

from PyQt6.QtWidgets import QApplication, QLabel

from controllers.game_controller import GameController
from tests.support import start_game
from models.agents import agent_by_id, agent_of, clients_of
from models.database import DatabaseManager
from models.entities import (
    AGENT_RELATION_RELEASED,
    AGENT_RELATION_START,
    Agent,
    AgentPersonality,
)
from models.generator import get_recruitment_fee
from views.athlete_dialog import AthleteDetailDialog
from views.dialogs import RecruitAthleteDialog

_app = QApplication.instance() or QApplication([])


class _Base(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "s.db"
        self.ctrl = GameController(db_manager=DatabaseManager(db_path=self.path), rng=random.Random(3), auto_create=False)
        start_game(self.ctrl, team_name="CUS Test", game_mode="career")
        self.state = self.ctrl.state


class TestControllerAgents(_Base):
    def test_a_new_game_gives_every_athlete_an_agent(self) -> None:
        self.assertTrue(all(agent_of(self.state, a) is not None for a in self.state.athletes))
        self.assertTrue(all(ag.relation == AGENT_RELATION_START for ag in self.state.agents))

    def test_market_candidates_come_with_their_agent(self) -> None:
        pool = self.ctrl.get_free_agent_market(count=5)
        self.assertTrue(all(agent_by_id(self.state, c.agent_id) is not None for c in pool))

    def test_recruiting_pays_the_fee_asked_by_the_agent(self) -> None:
        for personality, factor in ((AgentPersonality.AGGRESSIVE, 1.20), (AgentPersonality.LOYAL, 0.90)):
            with self.subTest(personality=personality.value):
                self.ctrl.state.budget = 50000
                prospect = self.ctrl.generate_free_agents(count=1)[0]
                prospect.agent_id = None
                agent = Agent(id=900 + len(self.state.agents), name="Gigi", personality=personality)
                self.state.agents.append(agent)
                prospect.agent_id = agent.id
                base = get_recruitment_fee(prospect)
                before = self.state.budget
                self.assertTrue(self.ctrl.recruit_athlete(prospect))
                self.assertEqual(before - self.state.budget, round(base * factor))
                self.assertEqual(self.state.transactions[0].amount, -round(base * factor))

    def test_refuses_when_the_agent_ask_exceeds_the_budget_even_if_the_standard_fee_fits(self) -> None:
        prospect = self.ctrl.generate_free_agents(count=1)[0]
        agent = Agent(id=950, name="Gigi", personality=AgentPersonality.AGGRESSIVE)
        self.state.agents.append(agent)
        prospect.agent_id = agent.id
        base = get_recruitment_fee(prospect)
        self.state.budget = base  # basta per l'ingaggio standard, non per +20%
        self.assertFalse(self.ctrl.recruit_athlete(prospect))
        self.assertEqual(self.state.budget, base)

    def test_a_prospect_signed_without_an_agent_gets_one(self) -> None:
        self.state.budget = 50000
        prospect = self.ctrl.generate_free_agents(count=1)[0]
        prospect.agent_id = None
        self.assertTrue(self.ctrl.recruit_athlete(prospect))
        self.assertIsNotNone(agent_of(self.state, prospect))

    def test_releasing_an_athlete_lowers_the_relation_with_the_whole_agent(self) -> None:
        shared = next(ag for ag in self.state.agents if len([a for a in clients_of(self.state, ag) if not a.in_youth_squad]) >= 2)
        target = next(a for a in clients_of(self.state, shared) if not a.in_youth_squad)
        self.assertTrue(self.ctrl.release_athlete(target.id))
        self.assertEqual(agent_by_id(self.state, shared.id).relation, AGENT_RELATION_START + AGENT_RELATION_RELEASED)

    def test_agents_without_clients_and_neutral_relation_are_pruned_at_the_next_week(self) -> None:
        self.ctrl.get_free_agent_market(count=5)
        idle = Agent(id=700, name="Mai Visto", relation=AGENT_RELATION_START)
        self.state.agents.append(idle)
        self.ctrl.advance_week()
        self.assertNotIn(700, [ag.id for ag in self.state.agents])
        self.assertTrue(all(agent_by_id(self.state, a.agent_id) is not None for a in self.state.athletes))

    def test_agents_survive_a_reload(self) -> None:
        self.state.agents[0].relation = 71
        self.ctrl.save_game()
        other = GameController(db_manager=DatabaseManager(db_path=self.path), rng=random.Random(1), auto_create=False)
        self.assertTrue(other.load_game())
        self.assertEqual(other.state.agents, self.state.agents)


class TestRecruitDialogAgents(_Base):
    def test_the_agent_column_and_the_asked_fee(self) -> None:
        self.state.budget = 50000
        pool = self.ctrl.get_free_agent_market(count=5)
        dlg = RecruitAthleteDialog(pool, self.state.budget, roster=self.state.main_squad, agents=self.state.agents)
        self.addCleanup(dlg.close)
        header = [dlg.table.horizontalHeaderItem(c).text() for c in range(dlg.table.columnCount())]
        self.assertEqual(header[9:11], ["Agente", "Costo"])
        for row, prospect in enumerate(pool):
            agent = agent_by_id(self.state, prospect.agent_id)
            self.assertIn(agent.name, dlg.table.item(row, 9).text())
            self.assertIn(agent.personality.value, dlg.table.item(row, 9).text())
            ask = round(get_recruitment_fee(prospect) * (1 + agent.fee_modifier))
            self.assertEqual(dlg.table.item(row, 10).text(), f"€{ask:,}")
            self.assertIn("ingaggio standard", dlg.table.item(row, 9).toolTip())

    def test_without_agents_the_dialog_shows_the_standard_fee(self) -> None:
        pool = self.ctrl.generate_free_agents(count=2)
        dlg = RecruitAthleteDialog(pool, 50000)
        self.addCleanup(dlg.close)
        self.assertEqual(dlg.table.item(0, 9).text(), "—")
        self.assertEqual(dlg.table.item(0, 10).text(), f"€{get_recruitment_fee(pool[0]):,}")

    def test_signing_is_refused_when_the_asked_fee_exceeds_the_budget(self) -> None:
        pool = self.ctrl.get_free_agent_market(count=3)
        agent = Agent(id=960, name="Gigi", personality=AgentPersonality.AGGRESSIVE)
        self.state.agents.append(agent)
        pool[0].agent_id = agent.id
        base = get_recruitment_fee(pool[0])
        dlg = RecruitAthleteDialog(pool, base, roster=self.state.main_squad, agents=self.state.agents)  # budget = ingaggio standard
        self.addCleanup(dlg.close)
        dlg.table.selectRow(0)
        self.assertIn("Fondi insufficienti", dlg.compare_label.text())  # il «dopo tesseramento» usa la richiesta dell'agente


class TestAthleteDialogAgent(_Base):
    def test_the_card_shows_the_agent(self) -> None:
        athlete = self.state.main_squad[0]
        agent = agent_of(self.state, athlete)
        agent.relation = 64
        dlg = AthleteDetailDialog(self.ctrl, athlete.id)
        self.addCleanup(dlg.close)
        text = " ".join(label.text() for label in dlg.overview_page.findChildren(QLabel))
        self.assertIn("Agente", text)
        self.assertIn(agent.name, text)
        self.assertIn("Rapporto", text)
        self.assertIn(f"{agent.personality.value} · 64", text)

    def test_an_athlete_without_agent_shows_a_dash(self) -> None:
        athlete = self.state.main_squad[0]
        athlete.agent_id = None
        dlg = AthleteDetailDialog(self.ctrl, athlete.id)
        self.addCleanup(dlg.close)
        self.assertEqual((dlg._agent_text(athlete), dlg._relation_text(athlete)), ("—", "—"))


if __name__ == "__main__":
    unittest.main()
