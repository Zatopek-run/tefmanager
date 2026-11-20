"""Staff clinico con attributi (PIANOLAVORO E.1): funzioni pure, senza Qt e senza RNG.

Gli attributi (1-20, `STAFF_ATTRIBUTES`) scalano gli effetti che prima erano fissi per ruolo. Al valore di riferimento
(`STAFF_ATTR_REF`) ogni funzione restituisce esattamente la cifra di prima di E.1; le cifre stanno in `entities.py`.
Nessuna funzione estrae numeri casuali: la simulazione usa le stesse estrazioni di prima (ordine del tick invariato).
"""
from __future__ import annotations

from typing import Dict, Optional

from models.entities import (
    CALM_SIGMA,
    DOCTOR_RISK_CUT,
    DOCTOR_RISK_FLOOR,
    IMPULSIVE_SIGMA,
    MENTAL_FORM_BONUS,
    MENTAL_SIGMA_FLOOR,
    PHYSIO_FATIGUE_RELIEF,
    PHYSIO_HEAL_STEP_CHANCE,
    PHYSIO_HEAL_STEP_CHANCE_CAP,
    PHYSIO_INJURY_RECOVERY_BONUS,
    PHYSIO_WEEK_CUT_MIN,
    STAFF_ATTR_MAX,
    STAFF_ATTR_MIN,
    STAFF_ATTR_REF,
    STAFF_ATTRIBUTES,
    GameState,
    StaffMember,
    StaffRole,
)

# Attributi dei ruoli assunti: ruolo → {chiave: valore}. Un ruolo assente = non assunto.
StaffAttrs = Dict[StaffRole, Dict[str, int]]


def normalize_attributes(role: StaffRole, raw: Optional[Dict[str, int]] = None) -> Dict[str, int]:
    """Attributi completi del ruolo: le chiavi mancanti valgono il riferimento, i valori restano tra 1 e 20."""
    raw = raw or {}
    out: Dict[str, int] = {}
    for key, _label in STAFF_ATTRIBUTES.get(role, ()):
        try:
            value = int(raw.get(key, STAFF_ATTR_REF))
        except (TypeError, ValueError):
            value = STAFF_ATTR_REF
        out[key] = max(STAFF_ATTR_MIN, min(STAFF_ATTR_MAX, value))
    return out


def hired_staff_attributes(state: GameState) -> StaffAttrs:
    """Attributi (normalizzati) dei soli specialisti assunti. Più assunti con lo stesso ruolo: vale il migliore."""
    out: StaffAttrs = {}
    for member in state.staff:
        if not member.hired or member.role not in STAFF_ATTRIBUTES:
            continue
        attrs = normalize_attributes(member.role, member.attributes)
        current = out.get(member.role)
        if current is None or sum(attrs.values()) > sum(current.values()):
            out[member.role] = attrs
    return out


def attribute_of(staff: Optional[StaffAttrs], role: StaffRole, key: str) -> int:
    """Valore di un attributo; senza dati (chiamata senza `staff`) vale il riferimento, cioè l'effetto di sempre."""
    if staff is None or role not in staff:
        return STAFF_ATTR_REF
    return staff[role].get(key, STAFF_ATTR_REF)


def _factor(value: int) -> float:
    return value / STAFF_ATTR_REF


def physio_fatigue_relief(recupero: int) -> int:
    """Fatica tolta in più a settimana dal fisioterapista (7 al riferimento)."""
    return round(PHYSIO_FATIGUE_RELIEF * _factor(recupero))


def physio_injury_recovery_bonus(recupero: int) -> int:
    """Recupero di fatica extra di un atleta infortunato (8 al riferimento)."""
    return round(PHYSIO_INJURY_RECOVERY_BONUS * _factor(recupero))


def physio_heal_step_chance(competenza: int) -> float:
    """Probabilità che un infortunato guarisca di due settimane invece di una (0,55 al riferimento)."""
    return min(PHYSIO_HEAL_STEP_CHANCE_CAP, PHYSIO_HEAL_STEP_CHANCE * _factor(competenza))


def physio_cuts_injury_week(competenza: int) -> bool:
    """Se il fisioterapista toglie una settimana a un nuovo infortunio di più di una settimana."""
    return competenza >= PHYSIO_WEEK_CUT_MIN


def doctor_risk_multiplier(value: int) -> float:
    """Moltiplicatore del rischio d'infortunio con il medico (0,55 al riferimento), tra DOCTOR_RISK_FLOOR e 1."""
    return max(DOCTOR_RISK_FLOOR, 1.0 - DOCTOR_RISK_CUT * _factor(value))


def mental_form_bonus(motivazione: int) -> int:
    """Bonus al bersaglio di forma dato dal preparatore mentale (4 al riferimento)."""
    return round(MENTAL_FORM_BONUS * _factor(motivazione))


def impulsive_sigma(has_mental_coach: bool, pressione: int = STAFF_ATTR_REF) -> float:
    """Deviazione in gara di un Impulsivo: 5,6 senza preparatore, 3,8 col preparatore al riferimento, fino a 3,0."""
    if not has_mental_coach:
        return IMPULSIVE_SIGMA
    return max(MENTAL_SIGMA_FLOOR, IMPULSIVE_SIGMA - (IMPULSIVE_SIGMA - CALM_SIGMA) * _factor(pressione))


def describe_attributes(member: StaffMember) -> str:
    """Testo per la scheda staff, p. es. «Competenza infortuni 14 · Velocità recupero 14»."""
    attrs = normalize_attributes(member.role, member.attributes)
    return " · ".join(f"{label} {attrs[key]}" for key, label in STAFF_ATTRIBUTES.get(member.role, ()))
