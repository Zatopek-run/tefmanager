"""Impianti avanzati (PIANOLAVORO E.2): funzioni pure, senza Qt. Le cifre stanno in `entities.py`.

Senza l'impianto ogni funzione restituisce il valore di prima di E.2 e **non estrae numeri casuali**: la sequenza
dell'RNG della partita cambia solo per chi compra il centro medico (una estrazione per infortunio).
"""
from __future__ import annotations

import json
import random
from typing import Dict, Mapping, Optional

from models.entities import (
    ALTITUDE_CAMP_STAMINA_BONUS,
    FACILITY_ALTITUDE,
    FACILITY_COSTS,
    FACILITY_LABELS,
    FACILITY_MEDICAL,
    FACILITY_ORDER,
    FACILITY_UPKEEP,
    FACILITY_VIDEO,
    FACILITY_WEIGHTS,
    INJURY_MIN_WEEKS,
    MEDICAL_CENTER_INJURY_CUT,
    VIDEO_CENTER_TECHNIQUE_BONUS,
    WEIGHTS_ROOM_STRENGTH_BONUS,
    Specialty,
)

Facilities = Mapping[str, int]

# Descrizione dell'effetto mostrata nella scheda dell'impianto (cifre dalle costanti, mai scritte a mano).
FACILITY_EFFECTS: Dict[str, str] = {
    FACILITY_MEDICAL: f"−{round(MEDICAL_CENTER_INJURY_CUT * 100)}% sul tempo di infortunio (minimo {INJURY_MIN_WEEKS} sett.)",
    FACILITY_VIDEO: f"+{round(VIDEO_CENTER_TECHNIQUE_BONUS * 100)}% probabilità di migliorare la Tecnica",
    FACILITY_WEIGHTS: f"+{round(WEIGHTS_ROOM_STRENGTH_BONUS * 100)}% probabilità di migliorare la Forza",
    FACILITY_ALTITUDE: f"+{round(ALTITUDE_CAMP_STAMINA_BONUS * 100)}% probabilità di migliorare la Resistenza (solo Mezzofondo)",
}


def owns(facilities: Optional[Facilities], key: str) -> bool:
    return bool(facilities) and int(facilities.get(key, 0)) > 0


def growth_multiplier(facilities: Optional[Facilities], stat_name: str, specialty: Specialty) -> float:
    """Moltiplicatore della probabilità settimanale di migliorare `stat_name` dovuto agli impianti avanzati (1,0 = nessuno)."""
    mult = 1.0
    if stat_name == "technique" and owns(facilities, FACILITY_VIDEO):
        mult *= 1.0 + VIDEO_CENTER_TECHNIQUE_BONUS
    if stat_name == "strength" and owns(facilities, FACILITY_WEIGHTS):
        mult *= 1.0 + WEIGHTS_ROOM_STRENGTH_BONUS
    if stat_name == "stamina" and specialty == Specialty.MIDDLE_DISTANCE and owns(facilities, FACILITY_ALTITUDE):
        mult *= 1.0 + ALTITUDE_CAMP_STAMINA_BONUS
    return mult


def injury_weeks_with_medical_center(weeks: int, facilities: Optional[Facilities], rng: random.Random) -> int:
    """Settimane di stop dopo il centro medico: −15% con arrotondamento a caso, mai sotto `INJURY_MIN_WEEKS`.

    Senza il centro restituisce `weeks` **senza toccare l'RNG**. Con il centro fa una sola estrazione, anche quando il
    risultato non può cambiare, così il numero di estrazioni dipende solo dal possesso e non dal valore.
    """
    if not owns(facilities, FACILITY_MEDICAL):
        return weeks
    target = weeks * (1.0 - MEDICAL_CENTER_INJURY_CUT)
    whole = int(target)
    weeks_out = whole + (1 if rng.random() < target - whole else 0)
    return max(INJURY_MIN_WEEKS, min(weeks, weeks_out))


def facilities_to_json(facilities: Facilities) -> str:
    return json.dumps({k: int(facilities[k]) for k in FACILITY_ORDER if owns(facilities, k)})


def facilities_from_json(raw: Optional[str]) -> Dict[str, int]:
    """Impianti posseduti da una colonna JSON: chiavi sconosciute scartate, JSON rotto = nessun impianto."""
    try:
        data = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    out: Dict[str, int] = {}
    for key in FACILITY_ORDER:
        try:
            level = int(data.get(key, 0))
        except (TypeError, ValueError):
            continue
        if level > 0:
            out[key] = 1  # per ora un solo livello: «posseduto»
    return out


def facility_cost(key: str) -> int:
    return FACILITY_COSTS[key]


def facility_upkeep(key: str) -> int:
    """Manutenzione settimanale (€) di un impianto avanzato posseduto (Q34a)."""
    return FACILITY_UPKEEP[key]


def total_upkeep(facilities: Optional[Facilities]) -> int:
    """Manutenzione settimanale di tutti gli impianti avanzati posseduti; 0 senza impianti."""
    return sum(FACILITY_UPKEEP[k] for k in FACILITY_ORDER if owns(facilities, k))


def facility_label(key: str) -> str:
    return FACILITY_LABELS[key]
