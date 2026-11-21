"""Lotto E.3 (parte con Qt offscreen): Academy, osservatore e rete regionale nel controller e nella tab «Vivaio & Osservatori».

Non si prova il mouse reale: si legge lo stato dei pulsanti e si chiamano i metodi del controller come farebbero i click.
Le gare con la MainWindow aprirebbero dialoghi modali (che in offscreen non tornano): per avanzare di settimana si usa un
controller senza finestra.
"""

from __future__ import annotations

import os
import random
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("TEF_NO_GODOT", "1")

from PyQt6.QtWidgets import QApplication

from controllers.game_controller import GameController, scouting_search_cost
from models.database import DatabaseManager
from models.entities import (
    ACADEMY_MAX_LEVEL,
    SCOUT_REGION_FEE,
    SCOUT_REGIONS,
    SCOUT_POTENTIAL_BAND,
    Specialty,
)
from models.generator import generate_academy_prospects
from models.scouting import academy_upgrade_cost, scout_candidates, scout_severance
from models.simulation import weekly_finances
from tests.support import start_game
from views.dialogs import potential_band_display
from views.main_window import MainWindow

_app = QApplication.instance() or QApplication([])


def _controller(tmp: str, seed: int = 3, window: bool = False):
    path = Path(tmp) / "s.db"
    ctrl = GameController(db_manager=DatabaseManager(db_path=path), rng=random.Random(seed), auto_create=False)
    start_game(ctrl, team_name="CUS Test", game_mode="career")
    ctrl.state.budget = 200000
    return (ctrl, MainWindow(ctrl), path) if window else (ctrl, None, path)


class TestAcademyController(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.ctrl, _win, self.path = _controller(tmp.name)

    def test_upgrading_charges_the_cost_and_raises_the_star(self) -> None:
        before = self.ctrl.state.budget
        self.assertTrue(self.ctrl.upgrade_academy())
        self.assertEqual(self.ctrl.state.academy_level, 1)
        self.assertEqual(self.ctrl.state.budget, before - academy_upgrade_cost(0))
        tx = self.ctrl.state.transactions[0]
        self.assertEqual((tx.category, tx.amount), ("Impianto", -academy_upgrade_cost(0)))

    def test_it_stops_at_five_stars(self) -> None:
        for _ in range(ACADEMY_MAX_LEVEL):
            self.assertTrue(self.ctrl.upgrade_academy())
        budget = self.ctrl.state.budget
        self.assertFalse(self.ctrl.upgrade_academy())
        self.assertEqual((self.ctrl.state.academy_level, self.ctrl.state.budget), (5, budget))

    def test_without_the_money_nothing_changes(self) -> None:
        self.ctrl.state.budget = academy_upgrade_cost(0) - 1
        self.assertFalse(self.ctrl.upgrade_academy())
        self.assertEqual(self.ctrl.state.academy_level, 0)

    def test_it_survives_a_reload(self) -> None:
        self.ctrl.upgrade_academy()
        other = GameController(db_manager=DatabaseManager(db_path=self.path), rng=random.Random(9), auto_create=False)
        self.assertTrue(other.load_game())
        self.assertEqual(other.state.academy_level, 1)


class TestScoutController(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.ctrl, _win, self.path = _controller(tmp.name)
        self.cands = scout_candidates()

    def test_hiring_is_free_up_front_and_costs_weekly(self) -> None:
        budget = self.ctrl.state.budget
        base = weekly_finances(self.ctrl.state)["staff_cost"]
        self.assertTrue(self.ctrl.hire_scout(self.cands[1].scout_id))
        self.assertEqual(self.ctrl.state.budget, budget)
        self.assertEqual(self.ctrl.state.scout, self.cands[1])
        self.assertEqual(weekly_finances(self.ctrl.state)["staff_cost"], base + self.cands[1].weekly_cost)

    def test_replacing_pays_the_severance_of_the_previous_one(self) -> None:
        self.ctrl.hire_scout(self.cands[0].scout_id)
        budget = self.ctrl.state.budget
        self.assertTrue(self.ctrl.hire_scout(self.cands[2].scout_id))
        self.assertEqual(self.ctrl.state.budget, budget - scout_severance(self.cands[0]))
        self.assertEqual(self.ctrl.state.scout, self.cands[2])

    def test_hiring_the_same_scout_twice_or_an_unknown_one_does_nothing(self) -> None:
        self.ctrl.hire_scout(self.cands[0].scout_id)
        budget = self.ctrl.state.budget
        self.assertFalse(self.ctrl.hire_scout(self.cands[0].scout_id))
        self.assertFalse(self.ctrl.hire_scout(999))
        self.assertEqual(self.ctrl.state.budget, budget)

    def test_firing_costs_the_severance_and_stops_the_weekly_pay(self) -> None:
        base = weekly_finances(self.ctrl.state)["staff_cost"]
        self.ctrl.hire_scout(self.cands[1].scout_id)
        budget = self.ctrl.state.budget
        self.assertTrue(self.ctrl.fire_scout())
        self.assertEqual(self.ctrl.state.budget, budget - scout_severance(self.cands[1]))
        self.assertIsNone(self.ctrl.state.scout)
        self.assertEqual(weekly_finances(self.ctrl.state)["staff_cost"], base)
        self.assertFalse(self.ctrl.fire_scout())  # nessuno da licenziare

    def test_without_the_money_for_the_severance_nobody_is_fired(self) -> None:
        self.ctrl.hire_scout(self.cands[2].scout_id)
        self.ctrl.state.budget = scout_severance(self.cands[2]) - 1
        self.assertFalse(self.ctrl.fire_scout())
        self.assertEqual(self.ctrl.state.scout, self.cands[2])

    def test_the_scout_survives_a_reload_and_is_paid_in_the_ledger(self) -> None:
        self.ctrl.hire_scout(self.cands[1].scout_id)
        self.ctrl.dismiss_dilemma()
        self.ctrl.advance_week()
        self.assertTrue(
            any(tx.category == "Staff" and "1 specialisti" in tx.description for tx in self.ctrl.state.transactions[:15])
        )
        other = GameController(db_manager=DatabaseManager(db_path=self.path), rng=random.Random(9), auto_create=False)
        self.assertTrue(other.load_game())
        self.assertEqual(other.state.scout, self.cands[1])


class TestRegionSearch(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.ctrl, _win, self.path = _controller(tmp.name, seed=5)

    def test_without_a_region_the_search_is_exactly_the_old_one(self) -> None:
        """Stessi ragazzi e stesso stato dell'RNG che avrebbe prodotto il codice di prima di E.3."""
        state_rng = random.Random(77)
        self.ctrl.rng = random.Random(77)
        kids = self.ctrl.run_youth_scouting(specialty=Specialty.JUMPS, high_potential=True)
        count = state_rng.randint(1, 4)
        expected = generate_academy_prospects(
            count=count, rng=state_rng, specialty=Specialty.JUMPS, high_potential=True,
            existing_names={a.name for a in self.ctrl.state.athletes},
        )
        self.assertEqual([k.name for k in kids], [k.name for k in expected])
        self.assertEqual([k.potential for k in kids], [k.potential for k in expected])
        self.assertEqual(self.ctrl.rng.getstate(), state_rng.getstate())
        self.assertEqual(self.ctrl.state.scouting_points_used, 4)  # 2 + disciplina + potenziale, come sempre

    def test_a_region_costs_one_point_and_the_fixed_fee_and_forces_the_discipline(self) -> None:
        budget = self.ctrl.state.budget
        points, fee = scouting_search_cost(0, 1)  # 2 punti di base + 1 della regione
        kids = self.ctrl.run_youth_scouting(region="giamaica")
        self.assertTrue(kids)
        self.assertEqual(self.ctrl.state.scouting_points_used, points)
        self.assertEqual(self.ctrl.state.budget, budget - fee - SCOUT_REGION_FEE)
        for kid in kids:
            self.assertEqual(kid.specialty, Specialty.SPRINTS)
            self.assertEqual(kid.nationality, "Giamaica")

    def test_a_region_overrides_the_discipline_filter_without_double_charging(self) -> None:
        kids = self.ctrl.run_youth_scouting(specialty=Specialty.THROWS, region="kenya")
        self.assertEqual(self.ctrl.state.scouting_points_used, 3)  # 2 + la regione (non anche la disciplina)
        self.assertTrue(all(k.specialty == Specialty.MIDDLE_DISTANCE for k in kids))

    def test_an_unknown_region_is_refused_without_cost(self) -> None:
        budget = self.ctrl.state.budget
        self.assertEqual(self.ctrl.run_youth_scouting(region="atlantide"), [])
        self.assertEqual((self.ctrl.state.budget, self.ctrl.state.scouting_points_used), (budget, 0))

    def test_the_prototype_has_no_throws_region(self) -> None:
        self.ctrl.state.game_mode = "vertical_slice"
        for key, (_label, spec, _stat, _nat) in SCOUT_REGIONS.items():
            if spec == Specialty.THROWS:
                self.assertEqual(self.ctrl.run_youth_scouting(region=key), [], key)
        self.assertEqual(self.ctrl.state.scouting_points_used, 0)

    def test_not_enough_money_for_the_fee_refuses_the_region_search(self) -> None:
        self.ctrl.state.budget = SCOUT_REGION_FEE - 1
        self.assertEqual(self.ctrl.run_youth_scouting(region="giamaica"), [])
        self.assertEqual(self.ctrl.state.scouting_points_used, 0)

    def test_about_a_fifth_of_region_kids_are_stars_over_many_searches(self) -> None:
        stars = total = 0
        for seed in range(60):
            self.ctrl.rng = random.Random(seed)
            self.ctrl.state.scouting_points_used = 0
            self.ctrl.state.budget = 200000
            for kid in self.ctrl.run_youth_scouting(region="giamaica"):
                total += 1
                stars += 1 if kid.speed > 80 else 0
        self.assertGreater(total, 100)
        self.assertAlmostEqual(stars / total, 0.20, delta=0.08)


class TestYouthTabUi(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.ctrl, self.win, self.path = _controller(tmp.name, seed=5, window=True)
        self.addCleanup(self.win.close)
        self.tab = self.win.youth_tab

    def test_academy_button_buys_a_star_and_shows_the_stars(self) -> None:
        self.tab.refresh(self.ctrl.state)
        self.assertIn("☆☆☆☆☆", self.tab.academy_label.text())
        self.tab.academy_btn.click()
        self.assertEqual(self.ctrl.state.academy_level, 1)
        self.tab.refresh(self.ctrl.state)
        self.assertIn("★☆☆☆☆", self.tab.academy_label.text())
        self.assertIn("+10%", self.tab.academy_sub.text())
        for _ in range(4):
            self.ctrl.upgrade_academy()
        self.tab.refresh(self.ctrl.state)
        self.assertFalse(self.tab.academy_btn.isEnabled())

    def test_the_scout_combo_hires_and_the_buttons_follow_the_state(self) -> None:
        self.tab.refresh(self.ctrl.state)
        self.assertFalse(self.tab.scout_fire_btn.isEnabled())
        self.assertEqual(self.tab.scout_hire_btn.text(), "Assumi")
        self.tab.scout_combo.setCurrentIndex(2)
        self.tab.scout_hire_btn.click()
        self.assertEqual(self.ctrl.state.scout, scout_candidates()[2])
        self.tab.refresh(self.ctrl.state)
        self.assertTrue(self.tab.scout_fire_btn.isEnabled())
        self.assertEqual(self.tab.scout_hire_btn.text(), "Sostituisci")
        self.assertIn("Giudizio potenziale 19/20", self.tab.scout_sub.text())

    def test_the_region_combo_lists_every_region_and_disables_the_discipline_filter(self) -> None:
        keys = [self.tab.region_combo.itemData(i) for i in range(self.tab.region_combo.count())]
        self.assertEqual(keys, [None, *SCOUT_REGIONS])
        self.tab.region_combo.setCurrentIndex(1)
        self.assertFalse(self.tab.spec_combo.isEnabled())
        self.assertIn(f"{SCOUT_REGION_FEE:,}", self.tab.cost_label.text() + self.tab.region_combo.itemText(1))
        self.tab.region_combo.setCurrentIndex(0)
        self.assertTrue(self.tab.spec_combo.isEnabled())

    def test_the_region_cost_label_adds_the_point_and_the_fee(self) -> None:
        self.tab.refresh(self.ctrl.state)
        self.tab.region_combo.setCurrentIndex(1)
        self.assertEqual(self.tab.cost_label.text(), f"Costo: 3 punti · €{scouting_search_cost(0, 1)[1] + SCOUT_REGION_FEE:,}")

    def test_the_search_button_runs_a_region_search(self) -> None:
        self.tab.region_combo.setCurrentIndex(1)
        self.tab.search_btn.click()
        self.assertTrue(self.ctrl.scouting_results)
        self.assertEqual({k.specialty for k in self.ctrl.scouting_results}, {Specialty.SPRINTS})

    def test_results_show_bands_and_without_a_scout_the_potential_band_is_the_old_one(self) -> None:
        self.ctrl.run_youth_scouting()
        self.tab.refresh(self.ctrl.state)
        table = self.tab.results_table
        for row, kid in enumerate(self.tab._results_list):
            self.assertEqual(table.item(row, 5).text(), potential_band_display(kid))  # identica alla fascia di prima di E.3
            self.assertIn("-", table.item(row, 4).text())  # senza scout anche la qualità attuale è una fascia
        self.assertEqual(SCOUT_POTENTIAL_BAND, 8)

    def test_a_perfect_scout_shows_the_exact_overall(self) -> None:
        self.ctrl.hire_scout(3)
        self.ctrl.state.scout.attuale = 20
        self.ctrl.run_youth_scouting()
        self.tab.refresh(self.ctrl.state)
        for row, kid in enumerate(self.tab._results_list):
            self.assertEqual(self.tab.results_table.item(row, 4).text(), str(kid.overall))

    def test_overall_and_potential_columns_do_not_sort_by_the_true_value(self) -> None:
        self.ctrl.run_youth_scouting()
        self.tab.refresh(self.ctrl.state)
        order = [k.name for k in self.tab._results_list]
        for col in (4, 5):
            self.tab._on_results_header_clicked(col)
            self.assertEqual([k.name for k in self.tab._results_list], order)


class TestWeekWithTheNewFeatures(unittest.TestCase):
    def test_the_week_advances_with_academy_scout_and_youth_in_the_squad(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ctrl, _win, _path = _controller(tmp)
            ctrl.hire_scout(3)
            for _ in range(5):
                ctrl.upgrade_academy()
            kids = ctrl.run_youth_scouting(region="kenya")
            self.assertTrue(ctrl.sign_youth(kids[0]))
            before = kids[0].stamina + kids[0].technique + kids[0].speed + kids[0].strength
            for _ in range(8):
                ctrl.dismiss_dilemma()
                ctrl.advance_week()
            self.assertEqual(ctrl.state.academy_level, 5)
            self.assertIsNotNone(ctrl.state.scout)
            after = sum(getattr(kids[0], s) for s in ("stamina", "technique", "speed", "strength"))
            self.assertGreaterEqual(after, before)


if __name__ == "__main__":
    unittest.main()
