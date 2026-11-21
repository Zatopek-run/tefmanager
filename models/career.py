"""Ritiro e post-carriera degli atleti del club (PIANOLAVORO C.3). Nessuna dipendenza da Qt e nessuna chiamata all'RNG:
le estrazioni le fa `simulation.retire_veterans`, qui ci sono solo le regole pure (probabilità, ricordo, abilità).

- **Ritiro per età:** al cambio stagione, dopo l'incremento dell'età, ogni atleta della Prima Squadra da
  `RETIREMENT_MIN_AGE` anni in su si ritira con probabilità crescente (`RETIREMENT_CHANCE_BY_AGE`); da
  `RETIREMENT_CERTAIN_AGE` il ritiro è certo.
- **Ritiro anticipato per infortuni:** chi ha almeno `RETIREMENT_INJURY_MIN_AGE` anni e `RETIREMENT_INJURIES_PER_SEASON`
  infortuni nella stagione appena chiusa si ritira con probabilità `RETIREMENT_INJURY_CHANCE` (se l'età non ne dà una più alta).
- **Post-carriera:** un ex atleta su dieci (`RETIRED_COACH_CHANCE`) si offre come allenatore. Le sue abilità vengono
  dagli attributi che aveva da atleta (principale e secondaria della sua specialità, come per gli altri allenatori),
  limitate a [`RETIRED_COACH_SKILL_MIN`, `RETIRED_COACH_SKILL_MAX`]; il giocatore lo assume (o no) a `RETIRED_COACH_HIRE_COST`.
"""

from __future__ import annotations

from typing import Dict, Tuple

from models.entities import (
    COACH_BASE_SKILL,
    COACH_STATS,
    RETIRED_COACH_SECONDARY_GAP,
    RETIRED_COACH_SKILL_MAX,
    RETIRED_COACH_SKILL_MIN,
    RETIREMENT_CERTAIN_AGE,
    RETIREMENT_CHANCE_BY_AGE,
    RETIREMENT_INJURIES_PER_SEASON,
    RETIREMENT_INJURY_CHANCE,
    RETIREMENT_INJURY_MIN_AGE,
    RETIREMENT_MIN_AGE,
    Athlete,
    RetiredAthlete,
)
from models.personal_bests import summary_text
from models.generator import SPECIALTY_COACH_FOCUS

REASON_AGE = "Età"
REASON_INJURIES = "Infortuni"


def age_retirement_chance(age: int) -> float:
    """Probabilità di ritiro per la sola età: 0 sotto la soglia, tabella nelle età intermedie, 1 da quella certa."""
    if age >= RETIREMENT_CERTAIN_AGE:
        return 1.0
    if age < RETIREMENT_MIN_AGE:
        return 0.0
    return RETIREMENT_CHANCE_BY_AGE.get(age, 0.0)


def retirement_chance(athlete: Athlete) -> Tuple[float, str]:
    """(probabilità, motivo) di ritiro al cambio stagione. Probabilità 0 = non eleggibile: non si estrae nulla."""
    by_age = age_retirement_chance(athlete.age)
    by_injuries = 0.0
    if athlete.age >= RETIREMENT_INJURY_MIN_AGE and athlete.season_injuries >= RETIREMENT_INJURIES_PER_SEASON:
        by_injuries = RETIREMENT_INJURY_CHANCE
    if by_injuries > by_age:
        return by_injuries, REASON_INJURIES
    return by_age, REASON_AGE


def coach_skills_from_athlete(athlete: Athlete) -> Dict[str, int]:
    """Abilità da allenatore di un ex atleta: la sua principale e secondaria, il resto al livello base."""
    primary, secondary = SPECIALTY_COACH_FOCUS[athlete.specialty]
    skills = {stat: COACH_BASE_SKILL for stat in COACH_STATS}

    def clamp(value: int) -> int:
        return max(RETIRED_COACH_SKILL_MIN, min(RETIRED_COACH_SKILL_MAX, value))

    skills[primary] = clamp(getattr(athlete, primary))
    if secondary != primary:
        skills[secondary] = max(COACH_BASE_SKILL, clamp(getattr(athlete, secondary)) - RETIRED_COACH_SECONDARY_GAP)
    return skills


def make_retired(athlete: Athlete, season: int, reason: str, coach_offer: bool) -> RetiredAthlete:
    """Il ricordo di un atleta che lascia l'attività; con `coach_offer` si offre come allenatore."""
    return RetiredAthlete(
        name=athlete.name,
        gender=athlete.gender,
        specialty=athlete.specialty,
        age=athlete.age,
        season=season,
        reason=reason,
        nationality=athlete.nationality,
        overall=athlete.overall,
        personal_best_display=summary_text(athlete, ()),  # Q43: i primati più recenti (al più due gare)
        coach_skills=coach_skills_from_athlete(athlete) if coach_offer else {},
        coach_offer=coach_offer,
    )
