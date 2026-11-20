"""Stato dell'RNG di una partita: serializzazione nel salvataggio e seed dei vecchi salvataggi (A.3).

Un solo `random.Random` per partita, condiviso da tick e azioni dell'interfaccia (scouting, mercato, vivaio).
Il suo stato completo (`getstate()`: una tupla di interi, JSON-serializzabile) viaggia in `GameState.rng_state`
e viene scritto a ogni salvataggio: ricaricare e rigiocare dà gli stessi esiti, quindi non si può «ritirare i dadi».
Niente `hash()` su stringhe (è salato per processo): i seed si ricavano con `hashlib`.
"""

from __future__ import annotations

import hashlib
import random
from typing import Any, List

from models.entities import RNG_SEED_TAG, GameState


def dump_rng_state(rng: random.Random) -> List[Any]:
    """Stato dell'RNG come lista JSON-serializzabile: [versione, [625 interi], gauss_next]."""
    version, internal, gauss_next = rng.getstate()
    return [version, list(internal), gauss_next]


def restore_rng_state(rng: random.Random, data: Any) -> bool:
    """Ripristina lo stato salvato; False (RNG intatto) se è vuoto o non valido."""
    if not data:
        return False
    try:
        version, internal, gauss_next = data
        rng.setstate((int(version), tuple(int(n) for n in internal), gauss_next))
    except (TypeError, ValueError):
        return False
    return True


def legacy_seed(state: GameState) -> int:
    """Seed deterministico per un salvataggio senza stato dell'RNG (v12 o precedente).

    Dipende da società, stagione e settimana (non c'è un id di partita: lo slot ha una sola riga).
    """
    key = f"{RNG_SEED_TAG}|{state.team_name}|{state.season_number}|{state.week}"
    return int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big")


def restore_or_seed(rng: random.Random, state: GameState) -> bool:
    """Riporta `rng` allo stato salvato in `state`; senza stato valido lo semina con `legacy_seed`.

    Ritorna True se ha ripristinato lo stato salvato, False se ha usato il seed di ripiego.
    """
    if restore_rng_state(rng, state.rng_state):
        return True
    rng.seed(legacy_seed(state))
    return False
