"""Lotto A.3 (parte con il controller): ricaricare e rigiocare dà gli stessi esiti; niente `hash()` salato.

Serve PyQt6 (offscreen) solo perché il controller è un QObject; la logica sta in `models/`.
"""

from __future__ import annotations

import os
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("TEF_NO_GODOT", "1")

from PyQt6.QtWidgets import QApplication

from controllers.game_controller import GameController
from tests.support import start_game
from models.database import DatabaseManager
from models.rng_state import dump_rng_state

_app = QApplication.instance() or QApplication([])
ROOT = Path(__file__).resolve().parent.parent


def _controller(db_path: Path, seed: int) -> GameController:
    return GameController(db_manager=DatabaseManager(db_path=db_path), rng=random.Random(seed), auto_create=False)


def _fingerprint(ctrl: GameController) -> tuple:
    s = ctrl.state
    return (s.budget, s.prestige, s.week, sorted(s.league_table.items()), s.news_log[:6], dump_rng_state(ctrl.rng))


class TestReloadReplays(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        first = _controller(self.dir / "a.db", seed=4)
        start_game(first, team_name="CUS Test", game_mode="career")
        first.advance_week()
        first.advance_week()

    def reload(self, name: str, seed: int) -> GameController:
        """Copia il file e lo carica con un RNG di partenza DIVERSO: conta solo quello salvato."""
        shutil.copy(self.dir / "a.db", self.dir / f"{name}.db")
        ctrl = _controller(self.dir / f"{name}.db", seed=seed)
        self.assertTrue(ctrl.load_game())
        return ctrl

    def test_same_save_loaded_twice_gives_identical_weeks(self) -> None:
        one, two = self.reload("b", seed=1), self.reload("c", seed=99)
        self.assertEqual(one.state.rng_state, two.state.rng_state)
        self.assertTrue(one.state.rng_state)
        for _ in range(8):
            one.advance_week()
            two.advance_week()
        self.assertEqual(_fingerprint(one), _fingerprint(two))

    def test_saved_state_is_the_one_after_the_last_action(self) -> None:
        ctrl = self.reload("b", seed=1)
        ctrl.advance_week()
        # il tick ha consumato RNG e `_persist` l'ha salvato: ricaricare ora riparte da lì, non da prima
        again = self.reload_from(ctrl)
        self.assertEqual(dump_rng_state(again.rng), dump_rng_state(ctrl.rng))

    def reload_from(self, ctrl: GameController) -> GameController:
        shutil.copy(ctrl.db.db_path, self.dir / "d.db")
        other = _controller(self.dir / "d.db", seed=123)
        self.assertTrue(other.load_game())
        return other

    def test_reloading_after_scouting_cannot_reroll_the_dice(self) -> None:
        """Ricerca vivaio → ricarica → seconda ricerca: identica a una seconda ricerca senza ricarica."""
        straight = self.reload("b", seed=1)
        straight.state.budget = 50000
        straight.run_youth_scouting()
        second_straight = [(k.name, k.potential) for k in straight.run_youth_scouting()]

        reloaded = self.reload("c", seed=2)
        reloaded.state.budget = 50000
        reloaded.run_youth_scouting()
        reloaded = self.reload_from(reloaded)
        second_reloaded = [(k.name, k.potential) for k in reloaded.run_youth_scouting()]
        self.assertTrue(second_straight)
        self.assertEqual(second_straight, second_reloaded)

    def test_old_save_without_rng_state_is_seeded_deterministically(self) -> None:
        shutil.copy(self.dir / "a.db", self.dir / "old.db")
        db = DatabaseManager(db_path=self.dir / "old.db")
        state = db.load_game()
        state.rng_state = []  # come un salvataggio v12: colonna al valore di default
        db.save_game(state)
        one, two = _controller(self.dir / "old.db", seed=1), _controller(self.dir / "old.db", seed=77)
        self.assertTrue(one.load_game())
        self.assertTrue(two.load_game())
        for _ in range(4):
            one.advance_week()
            two.advance_week()
        self.assertEqual(_fingerprint(one), _fingerprint(two))

    def test_failed_load_does_not_touch_the_running_rng(self) -> None:
        ctrl = self.reload("b", seed=1)
        before = ctrl.rng.getstate()
        self.assertFalse(ctrl.load_save_slot(self.dir / "non_esiste.db"))
        self.assertEqual(ctrl.rng.getstate(), before)


class TestPotentialBandIsStable(unittest.TestCase):
    """PLAN 2.2: la fascia del potenziale non dipende più da `hash()` (salato per processo)."""

    SCRIPT = (
        "import random\n"
        "from models.generator import generate_academy_prospects\n"
        "from views.dialogs import potential_band_display\n"
        "kids = generate_academy_prospects(count=4, rng=random.Random(5))\n"
        "print([potential_band_display(k) for k in kids])\n"
    )

    def run_with_hashseed(self, hashseed: str) -> str:
        env = dict(os.environ, PYTHONHASHSEED=hashseed, PYTHONPATH=str(ROOT), QT_QPA_PLATFORM="offscreen")
        done = subprocess.run(
            [sys.executable, "-c", self.SCRIPT], env=env, cwd=ROOT, capture_output=True, text=True, timeout=120
        )
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout.strip()

    def test_same_output_in_three_processes(self) -> None:
        outputs = {self.run_with_hashseed(seed) for seed in ("1", "2", "random")}
        self.assertEqual(len(outputs), 1, outputs)


if __name__ == "__main__":
    unittest.main()
