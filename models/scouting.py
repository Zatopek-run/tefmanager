"""Giovanili avanzate (PIANOLAVORO E.3): Academy a stelle, osservatore con attributi, rete regionale. Senza Qt.

Principio di neutralità: **senza Academy, senza scout e senza regione** ogni funzione restituisce ciò che il gioco faceva
prima di E.3 (crescita del vivaio ×1,5, fascia del potenziale ±8, nessuna estrazione in più dell'RNG). L'unica estrazione
nuova è la regione: una `rng.random()` per ragazzo segnalato (più una `randint` se è un talento), solo se si sceglie una regione.
"""
from __future__ import annotations

import json
import random
import zlib
from typing import Dict, List, Optional, Tuple

from models.entities import (
    ACADEMY_GROWTH_BONUS_PER_LEVEL,
    ACADEMY_MAX_LEVEL,
    ACADEMY_UPGRADE_COST_STEP,
    SCOUT_ATTRIBUTES,
    SCOUT_BAND_OFFSET,
    SCOUT_CURRENT_BAND,
    SCOUT_CURRENT_BAND_MIN,
    SCOUT_POTENTIAL_BAND,
    SCOUT_POTENTIAL_BAND_MIN,
    SCOUT_REGION_EXTRA_POINTS,
    SCOUT_REGION_FEE,
    SCOUT_REGION_STAR_CHANCE,
    SCOUT_REGION_STAR_STAT_MAX,
    SCOUT_REGION_STAR_STAT_MIN,
    SCOUT_REGIONS,
    STAFF_ATTR_MAX,
    STAFF_ATTR_MIN,
    STAFF_SEVERANCE_WEEKS,
    Athlete,
    Scout,
    Specialty,
)

# Candidati osservatore: dati fissi (nessun RNG), cifre PROVVISORIE (Q35). (id, nome, compenso/sett, potenziale, attuale)
SCOUT_CATALOGUE: Tuple[Tuple[int, str, int, int, int], ...] = (
    (1, "Bruno Fabbri (junior)", 120, 8, 8),
    (2, "Irene Costa (esperta)", 260, 13, 13),
    (3, "Gianni Sartori (senior)", 440, 19, 16),
)


def scout_candidates() -> List[Scout]:
    return [Scout(sid, name, cost, pot, cur) for sid, name, cost, pot, cur in SCOUT_CATALOGUE]


def _clamp_attr(value: int) -> int:
    return max(STAFF_ATTR_MIN, min(STAFF_ATTR_MAX, int(value)))


def band_half_width(attribute: Optional[int], widest: int, narrowest: int) -> int:
    """Mezza larghezza della fascia: `widest` senza scout o con attributo 1, `narrowest` con attributo 20 (lineare)."""
    if attribute is None:
        return widest
    steps = _clamp_attr(attribute) - STAFF_ATTR_MIN
    span = STAFF_ATTR_MAX - STAFF_ATTR_MIN
    return int(round(widest - (widest - narrowest) * steps / span))


def potential_half_width(scout: Optional[Scout]) -> int:
    return band_half_width(None if scout is None else scout.potenziale, SCOUT_POTENTIAL_BAND, SCOUT_POTENTIAL_BAND_MIN)


def current_half_width(scout: Optional[Scout]) -> int:
    return band_half_width(None if scout is None else scout.attuale, SCOUT_CURRENT_BAND, SCOUT_CURRENT_BAND_MIN)


def estimate_band(value: int, key: str, half_width: int) -> Tuple[int, int]:
    """Fascia (basso, alto) che contiene sempre `value`, con il centro spostato di uno scarto deterministico per `key`.

    crc32 e non `hash()` (salato per processo). Lo scarto è limitato a `half_width` così la fascia contiene sempre il valore
    vero, anche con una fascia stretta (con mezza larghezza 0 la fascia è il valore esatto).
    """
    limit = min(SCOUT_BAND_OFFSET, half_width)
    offset = random.Random(zlib.crc32(key.encode())).randint(-limit, limit) if limit > 0 else 0
    return max(1, value - half_width + offset), min(99, value + half_width + offset)


def _key(prospect: Athlete, kind: str) -> str:
    return f"{prospect.name}|{prospect.age}|{prospect.specialty.value}|{prospect.gender}" + ("" if kind == "pot" else f"|{kind}")


def potential_band_text(prospect: Athlete, scout: Optional[Scout]) -> str:
    lo, hi = estimate_band(prospect.potential, _key(prospect, "pot"), potential_half_width(scout))
    return f"{lo}-{hi}"


def current_band_text(prospect: Athlete, scout: Optional[Scout]) -> str:
    """Qualità attuale (OVR) del ragazzo segnalato: fascia, o il valore esatto se lo scout è perfetto (attributo 20)."""
    width = current_half_width(scout)
    if width <= 0:
        return str(prospect.overall)
    lo, hi = estimate_band(prospect.overall, _key(prospect, "ovr"), width)
    return f"{lo}-{hi}"


# ------------------------------------------------------------------ academy
def academy_growth_multiplier(level: int) -> float:
    """Moltiplicatore della crescita del vivaio dovuto alle stelle dell'Academy (1,0 a 0 stelle, 1,5 a 5)."""
    return 1.0 + ACADEMY_GROWTH_BONUS_PER_LEVEL * max(0, min(ACADEMY_MAX_LEVEL, int(level)))


def academy_upgrade_cost(level: int) -> int:
    """Costo per salire dalla stella `level` alla successiva."""
    return (level + 1) * ACADEMY_UPGRADE_COST_STEP


# ------------------------------------------------------------------ scout
def scout_severance(scout: Scout) -> int:
    """Liquidazione di un osservatore licenziato: come per lo staff clinico (`STAFF_SEVERANCE_WEEKS` settimane)."""
    return scout.weekly_cost * STAFF_SEVERANCE_WEEKS


def scout_to_json(scout: Optional[Scout]) -> str:
    if scout is None:
        return "{}"
    return json.dumps(
        {"id": scout.scout_id, "name": scout.name, "cost": scout.weekly_cost,
         "potenziale": scout.potenziale, "attuale": scout.attuale}
    )


def scout_from_json(raw: Optional[str]) -> Optional[Scout]:
    """Osservatore da una colonna JSON: vuoto o rotto = nessuno scout (il comportamento di prima di E.3)."""
    try:
        data = json.loads(raw or "{}")
        if not isinstance(data, dict) or not data:
            return None
        return Scout(
            scout_id=int(data["id"]),
            name=str(data["name"]),
            weekly_cost=max(0, int(data["cost"])),
            potenziale=_clamp_attr(data["potenziale"]),
            attuale=_clamp_attr(data["attuale"]),
        )
    except (TypeError, ValueError, KeyError):
        return None


# ------------------------------------------------------------------ rete regionale
def region_specialty(region: str) -> Specialty:
    return SCOUT_REGIONS[region][1]


def region_label(region: str) -> str:
    return SCOUT_REGIONS[region][0]


def region_search_extras(region: Optional[str]) -> Tuple[int, int]:
    """(punti scouting in più, quota in euro) di una ricerca con regione; (0, 0) senza regione."""
    if region is None:
        return 0, 0
    return SCOUT_REGION_EXTRA_POINTS, SCOUT_REGION_FEE


def apply_region_talent(kid: Athlete, region: str, rng: random.Random) -> bool:
    """Marca il ragazzo con la nazionalità della regione e, con probabilità `SCOUT_REGION_STAR_CHANCE`, ne alza la qualità
    tipica oltre 80. Una `rng.random()` per ragazzo (+ una `randint` se è un talento). Ritorna True se è un talento."""
    _name, _spec, stat, nationality = SCOUT_REGIONS[region]
    kid.nationality = nationality
    if rng.random() >= SCOUT_REGION_STAR_CHANCE:
        return False
    value = rng.randint(SCOUT_REGION_STAR_STAT_MIN, SCOUT_REGION_STAR_STAT_MAX)
    setattr(kid, stat, value)
    kid.potential = max(kid.potential, value)  # il tetto di crescita non può stare sotto la qualità
    return True
