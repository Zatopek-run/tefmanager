"""Lotti B.1, B.2 e B.3 (parte con Qt offscreen): la colonna «Piano gara / Rischio» della scheda Calendario, il menu
«Cambio» della scheda Staffette e il controller.

Non si prova il mouse reale: si agisce sui menu a tendina da codice (`setCurrentIndex`), che emette gli stessi segnali.
"""

from __future__ import annotations

import os
import random
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("TEF_NO_GODOT", "1")

from PyQt6.QtWidgets import QApplication, QComboBox

from controllers.game_controller import GameController
from tests.support import start_game
from models.database import DatabaseManager
from models.entities import FieldRisk, RaceKick, RacePace, RelayChange
from views.main_window import MainWindow

_app = QApplication.instance() or QApplication([])


def _controller(path: Path) -> GameController:
    ctrl = GameController(db_manager=DatabaseManager(db_path=path), rng=random.Random(3), auto_create=False)
    start_game(ctrl, team_name="CUS Test", game_mode="vertical_slice")  # nel Prototipo c'è il 1500m
    return ctrl


class TestStrategyColumn(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "s.db"
        self.ctrl = _controller(self.path)
        self.win = MainWindow(controller=self.ctrl)
        self.addCleanup(self.win.close)
        self.table = self.win.calendar_tab.lineup_table

    def strategy_combos(self, event: str) -> list:
        for row in range(self.table.rowCount()):
            if self.table.item(row, 0).text().startswith(event):
                widget = self.table.cellWidget(row, 5)
                return [] if widget is None else widget.findChildren(QComboBox)
        self.fail(f"riga {event} non trovata")

    def test_only_middle_distance_rows_have_the_strategy_combos(self) -> None:
        self.assertEqual(len(self.strategy_combos("1500m")), 2)
        self.assertEqual(self.strategy_combos("100m"), [])
        self.assertEqual(len(self.strategy_combos("Salto in Lungo")), 1)  # B.2: un solo menu, il rischio

    def test_choosing_in_the_combos_updates_the_state_and_survives_a_save(self) -> None:
        pace_combo, kick_combo = self.strategy_combos("1500m")
        pace_combo.setCurrentIndex(pace_combo.findData(RacePace.VELOCE))
        kick_combo.setCurrentIndex(kick_combo.findData(RaceKick.ULTIMI_200))
        self.assertEqual(self.ctrl.state.strategy_for("1500m"), (RacePace.VELOCE, RaceKick.ULTIMI_200))
        self.ctrl.save_game()
        other = GameController(db_manager=DatabaseManager(db_path=self.path), rng=random.Random(1), auto_create=False)
        self.assertTrue(other.load_game())
        self.assertEqual(other.state.strategy_for("1500m"), (RacePace.VELOCE, RaceKick.ULTIMI_200))

    def test_combos_show_the_saved_plan_after_a_refresh(self) -> None:
        self.ctrl.set_race_strategy("1500m", RacePace.LENTO, RaceKick.ULTIMO_GIRO)
        self.win.calendar_tab.refresh(self.ctrl.state)
        pace_combo, kick_combo = self.strategy_combos("1500m")
        self.assertEqual(pace_combo.currentData(), RacePace.LENTO)
        self.assertEqual(kick_combo.currentData(), RaceKick.ULTIMO_GIRO)

    def test_controller_ignores_events_without_a_plan(self) -> None:
        self.ctrl.set_race_strategy("100m", RacePace.VELOCE, RaceKick.ULTIMO_GIRO)
        self.assertNotIn("100m", self.ctrl.state.race_strategy)

    # ---- B.2: rischio nei concorsi (lungo/peso)
    def test_field_rows_have_the_risk_combo_and_choice_survives_a_save(self) -> None:
        (combo,) = self.strategy_combos("Salto in Lungo")
        self.assertEqual(combo.currentData(), FieldRisk.SICURO)
        combo.setCurrentIndex(combo.findData(FieldRisk.AGGRESSIVO))
        self.assertEqual(self.ctrl.state.risk_for("Salto in Lungo"), FieldRisk.AGGRESSIVO)
        self.ctrl.save_game()
        other = GameController(db_manager=DatabaseManager(db_path=self.path), rng=random.Random(1), auto_create=False)
        self.assertTrue(other.load_game())
        self.assertEqual(other.state.risk_for("Salto in Lungo"), FieldRisk.AGGRESSIVO)

    def test_risk_combo_shows_the_saved_choice_after_a_refresh(self) -> None:
        self.ctrl.set_field_risk("Salto in Lungo", FieldRisk.BILANCIATO)
        self.win.calendar_tab.refresh(self.ctrl.state)
        (combo,) = self.strategy_combos("Salto in Lungo")
        self.assertEqual(combo.currentData(), FieldRisk.BILANCIATO)

    def test_controller_ignores_risk_for_other_events(self) -> None:
        self.ctrl.set_field_risk("100m", FieldRisk.AGGRESSIVO)
        self.ctrl.set_field_risk("1500m", FieldRisk.AGGRESSIVO)
        self.assertNotIn("100m", self.ctrl.state.race_strategy)
        self.assertNotIn("risk", self.ctrl.state.race_strategy.get("1500m", {}))


class TestRelayChangeCombo(unittest.TestCase):
    """B.3: il menu «Cambio» della scheda Staffette (una scelta per staffetta, M e F insieme)."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "r.db"
        self.ctrl = GameController(db_manager=DatabaseManager(db_path=self.path), rng=random.Random(3), auto_create=False)
        start_game(self.ctrl, team_name="CUS Test", game_mode="career")  # in Carriera ci sono entrambe le staffette
        self.win = MainWindow(controller=self.ctrl)
        self.addCleanup(self.win.close)
        self.tab = self.win.relay_tab

    def combo(self, relay: str) -> QComboBox:
        return self.tab._change_combos[relay]

    def test_each_relay_has_a_combo_starting_at_normal(self) -> None:
        self.assertEqual(set(self.tab._change_combos), {"4x100m", "4x400m"})
        for relay in ("4x100m", "4x400m"):
            self.assertEqual(self.combo(relay).currentData(), RelayChange.NORMALE)
            self.assertEqual(self.combo(relay).count(), len(RelayChange))

    def test_choosing_updates_the_state_for_that_relay_only_and_survives_a_save(self) -> None:
        combo = self.combo("4x100m")
        combo.setCurrentIndex(combo.findData(RelayChange.AGGRESSIVO))
        self.assertEqual(self.ctrl.state.change_for("4x100m"), RelayChange.AGGRESSIVO)
        self.assertEqual(self.ctrl.state.change_for("4x400m"), RelayChange.NORMALE)
        self.ctrl.save_game()
        other = GameController(db_manager=DatabaseManager(db_path=self.path), rng=random.Random(1), auto_create=False)
        self.assertTrue(other.load_game())
        self.assertEqual(other.state.change_for("4x100m"), RelayChange.AGGRESSIVO)

    def test_combos_show_the_saved_choice_after_a_refresh_and_a_division_switch(self) -> None:
        self.ctrl.set_relay_change("4x400m", RelayChange.CONSERVATIVO)
        self.tab.refresh(self.ctrl.state)
        self.assertEqual(self.combo("4x400m").currentData(), RelayChange.CONSERVATIVO)
        self.tab.division_combo.setCurrentIndex(self.tab.division_combo.findData("F"))  # vale per M e F insieme
        self.assertEqual(self.combo("4x400m").currentData(), RelayChange.CONSERVATIVO)

    def test_refresh_does_not_write_the_state(self) -> None:
        """Il refresh imposta i menu con i segnali bloccati: non deve creare scelte che l'utente non ha fatto."""
        self.tab.refresh(self.ctrl.state)
        self.assertNotIn("4x100m", self.ctrl.state.race_strategy)
        self.assertNotIn("4x400m", self.ctrl.state.race_strategy)

    def test_combo_is_disabled_for_a_relay_not_in_the_programme(self) -> None:
        proto = GameController(
            db_manager=DatabaseManager(db_path=self.path.with_name("p.db")), rng=random.Random(3), auto_create=False
        )
        start_game(proto, team_name="CUS Proto", game_mode="vertical_slice")
        win = MainWindow(controller=proto)
        self.addCleanup(win.close)
        self.assertTrue(win.relay_tab._change_combos["4x100m"].isEnabled())
        self.assertFalse(win.relay_tab._change_combos["4x400m"].isEnabled())

    def test_controller_ignores_unknown_relays(self) -> None:
        self.ctrl.set_relay_change("4x200m", RelayChange.AGGRESSIVO)
        self.ctrl.set_relay_change("100m", RelayChange.AGGRESSIVO)
        self.assertNotIn("4x200m", self.ctrl.state.race_strategy)
        self.assertNotIn("100m", self.ctrl.state.race_strategy)


if __name__ == "__main__":
    unittest.main()
