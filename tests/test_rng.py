"""Lotto A.3 (parte senza Qt): stato dell'RNG nel salvataggio, seed di ripiego per i vecchi salvataggi, schema v13.

Gira senza PyQt6 (`PYTHONPATH=. python3 -m unittest tests.test_rng`). La parte con il controller sta in
`tests/test_rng_controller.py`.
"""

from __future__ import annotations

import json
import random
import tempfile
import unittest
from pathlib import Path

from models.database import DatabaseManager
from models.rng_state import dump_rng_state, legacy_seed, restore_or_seed, restore_rng_state
from tests.test_assignments import make_state


class TestRngState(unittest.TestCase):
    def test_dump_survives_json_and_restores_the_sequence(self) -> None:
        source = random.Random(42)
        for _ in range(17):
            source.random()
        source.gauss(0, 1)  # lascia un `gauss_next` pendente: fa parte dello stato
        data = json.loads(json.dumps(dump_rng_state(source)))
        other = random.Random(7)
        self.assertTrue(restore_rng_state(other, data))
        self.assertEqual([source.random() for _ in range(5)], [other.random() for _ in range(5)])
        self.assertEqual(source.gauss(0, 1), other.gauss(0, 1))

    def test_invalid_state_leaves_the_rng_untouched(self) -> None:
        rng = random.Random(5)
        before = rng.getstate()
        for bad in ([], None, [3, [1, 2], None], "xx", [3, "non una lista", None]):
            self.assertFalse(restore_rng_state(rng, bad), bad)
            self.assertEqual(rng.getstate(), before)

    def test_legacy_seed_is_deterministic_and_depends_on_the_game(self) -> None:
        a, b = make_state(3), make_state(3)
        self.assertEqual(legacy_seed(a), legacy_seed(b))
        b.week += 1
        self.assertNotEqual(legacy_seed(a), legacy_seed(b))
        c = make_state(3)
        c.team_name = "Altra Società"
        self.assertNotEqual(legacy_seed(a), legacy_seed(c))

    def test_restore_or_seed_uses_the_saved_state_else_the_legacy_seed(self) -> None:
        state = make_state(3)
        source = random.Random(11)
        source.random()
        state.rng_state = dump_rng_state(source)
        rng = random.Random(1)
        self.assertTrue(restore_or_seed(rng, state))
        self.assertEqual(rng.random(), source.random())
        state.rng_state = []
        first, second = random.Random(1), random.Random(2)
        self.assertFalse(restore_or_seed(first, state))
        self.assertFalse(restore_or_seed(second, state))
        self.assertEqual(first.random(), second.random())  # stesso salvataggio vecchio → stessa sequenza


class TestRngPersistence(unittest.TestCase):
    def test_state_roundtrips_through_the_database(self) -> None:
        state = make_state(3)
        rng = random.Random(9)
        rng.random()
        state.rng_state = dump_rng_state(rng)
        with tempfile.TemporaryDirectory() as tmp:
            db = DatabaseManager(db_path=Path(tmp) / "r.db")
            db.save_game(state)
            loaded = db.load_game()
        self.assertEqual(loaded.rng_state, state.rng_state)
        restored = random.Random(0)
        self.assertTrue(restore_rng_state(restored, loaded.rng_state))
        self.assertEqual(restored.random(), rng.random())

    def test_a_state_without_rng_loads_as_empty(self) -> None:
        state = make_state(3)
        with tempfile.TemporaryDirectory() as tmp:
            db = DatabaseManager(db_path=Path(tmp) / "r.db")
            db.save_game(state)
            self.assertEqual(db.load_game().rng_state, [])


if __name__ == "__main__":
    unittest.main()
