"""Contratti con scadenza stagionale (Q22, parte 2) e colonna `contract_end_season` (schema v10).

Solo modello e database: gira senza PyQt6 (`PYTHONPATH=. python3 -m unittest tests.test_contracts`).
"""

from __future__ import annotations

import random
import tempfile
import unittest
from pathlib import Path

from models.database import DatabaseManager
from models.entities import CONTRACT_MAX_SEASONS
from models.simulation import (
    contract_length,
    ensure_contracts,
    promote_youth_athlete,
    renew_expiring_contracts,
)
from tests.test_assignments import make_state


class TestContractRules(unittest.TestCase):
    def test_length_is_one_to_three_seasons_and_deterministic(self) -> None:
        seen = set()
        for athlete_id in range(1, 40):
            for season in range(1, 8):
                n = contract_length(athlete_id, season)
                self.assertIn(n, range(1, CONTRACT_MAX_SEASONS + 1))
                self.assertEqual(n, contract_length(athlete_id, season))
                seen.add(n)
        self.assertEqual(seen, {1, 2, 3})  # tutte le durate possibili compaiono

    def test_backfill_gives_every_main_squad_athlete_a_contract(self) -> None:
        state = make_state(4)
        youth = state.athletes[0]
        youth.in_youth_squad = True
        for a in state.athletes:
            a.contract_end_season = 0
        self.assertEqual(ensure_contracts(state), len(state.main_squad))
        for a in state.main_squad:
            self.assertGreaterEqual(a.contract_end_season, state.season_number)
            self.assertLessEqual(a.contract_end_season, state.season_number + CONTRACT_MAX_SEASONS - 1)
        self.assertEqual(youth.contract_end_season, 0)  # il vivaio non ha contratto
        self.assertEqual(ensure_contracts(state), 0)  # idempotente

    def test_loading_an_old_save_assigns_contracts(self) -> None:
        """Un salvataggio v9 non ha la colonna: dopo la migrazione vale 0 e `upgrade_legacy_state` la riempie."""
        from models.simulation import upgrade_legacy_state

        state = make_state(8)
        for a in state.athletes:
            a.contract_end_season = 0
        upgrade_legacy_state(state, rng=random.Random(1))
        self.assertTrue(all(a.contract_end_season >= state.season_number for a in state.main_squad))

    def test_youth_promotion_signs_a_contract(self) -> None:
        state = make_state(4)
        kid = state.athletes[0]
        kid.in_youth_squad, kid.contract_end_season = True, 0
        promote_youth_athlete(state, kid)
        self.assertGreaterEqual(kid.contract_end_season, state.season_number)

    def test_expired_contracts_are_renewed_automatically(self) -> None:
        state = make_state(4)
        for a in state.athletes:
            a.contract_end_season = state.season_number + 1  # scade tra una stagione: nessun rinnovo
        self.assertEqual(renew_expiring_contracts(state), [])
        state.season_number += 1  # la stagione dopo, il contratto è ancora valido (fino alla fine di questa)
        self.assertEqual(renew_expiring_contracts(state), [])
        state.season_number += 1  # ora è scaduto: rinnovo automatico, un solo messaggio
        notes = renew_expiring_contracts(state)
        self.assertEqual(len(notes), 1)
        for a in state.main_squad:
            self.assertGreaterEqual(a.contract_end_season, state.season_number)
            self.assertIn(a.name, notes[0])
        self.assertEqual(renew_expiring_contracts(state), [])  # già rinnovati

    def test_release_is_the_way_to_not_renew(self) -> None:
        """Chi è stato svincolato prima della scadenza non compare più tra i rinnovi."""
        state = make_state(4)
        for a in state.athletes:
            a.contract_end_season = state.season_number
        gone = state.athletes.pop(0)
        state.season_number += 1
        notes = renew_expiring_contracts(state)
        self.assertNotIn(gone.name, notes[0])

    def test_roundtrip_through_sqlite_keeps_the_contract(self) -> None:
        state = make_state(4)
        for i, a in enumerate(state.athletes):
            a.contract_end_season = 1 + i % 3
        with tempfile.TemporaryDirectory() as tmp:
            db = DatabaseManager(db_path=Path(tmp) / "c.db")
            db.save_game(state)
            loaded = db.load_game()
        assert loaded is not None
        self.assertEqual(
            [(a.id, a.contract_end_season) for a in loaded.athletes],
            [(a.id, a.contract_end_season) for a in state.athletes],
        )


if __name__ == "__main__":
    unittest.main()
