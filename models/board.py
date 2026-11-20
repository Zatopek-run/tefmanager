"""Obiettivi del Board ed esonero (PIANOLAVORO C.2). Nessuna dipendenza da Qt e nessuna chiamata all'RNG.

A inizio stagione (solo Carriera: il Prototipo non ha stagioni) il Board assegna tre obiettivi:

- **Piazzamento:** chiudere tra i primi `BOARD_LEAGUE_TARGET[livello]` della lega (più largo nei livelli alti);
- **Bilancio:** non chiudere la stagione in perdita, cioè con un budget almeno pari a quello di inizio stagione
  (il bonus promozione si somma dopo il verdetto e non aiuta);
- **Record:** stabilire almeno `BOARD_MIN_RECORDS` record sociali, individuali o di staffetta (i primi record di una
  partita nuova sono facili: in una società senza record, ogni primato lo è).

A fine stagione (`settle_season`, chiamata da `close_season`) la stagione è **fallita** se si centrano meno di
`BOARD_OBJECTIVES_TO_PASS` obiettivi su tre. `BOARD_MAX_FAILED_STREAK` stagioni fallite **di fila** portano all'esonero
(`GameState.fired`, game over come il fallimento): una stagione non fallita azzera il conto. Un salvataggio iniziato
prima di C.2 ha ancora gli obiettivi vecchi fino a fine stagione: quella stagione non viene giudicata.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from models.entities import (
    BOARD_KEY_BUDGET,
    BOARD_KEY_LEAGUE,
    BOARD_KEY_RECORDS,
    BOARD_KEYS,
    BOARD_LEAGUE_TARGET,
    BOARD_MAX_FAILED_STREAK,
    BOARD_MIN_RECORDS,
    BOARD_OBJECTIVES_TO_PASS,
    CompetitionTier,
    GameState,
    SeasonObjective,
)


def create_board_objectives(tier: CompetitionTier, budget: int) -> List[SeasonObjective]:
    """I tre obiettivi di una stagione che inizia nel livello `tier` con `budget` in cassa."""
    top = BOARD_LEAGUE_TARGET[tier]
    return [
        SeasonObjective(BOARD_KEY_LEAGUE, f"Chiudi la stagione tra i primi {top} della lega {tier.display_name}", target=top),
        SeasonObjective(
            BOARD_KEY_BUDGET, f"Non chiudere la stagione in perdita: bilancio almeno €{budget:,}", target=budget
        ),
        SeasonObjective(
            BOARD_KEY_RECORDS, f"Stabilisci almeno {BOARD_MIN_RECORDS} record sociali", target=BOARD_MIN_RECORDS
        ),
    ]


def board_objectives(state: GameState) -> List[SeasonObjective]:
    """Gli obiettivi del Board in corso (vuota per il Prototipo e per i salvataggi precedenti a C.2)."""
    return [o for o in state.objectives if o.key in BOARD_KEYS]


def note_club_record(state: GameState) -> None:
    """Un record sociale stabilito: conta per l'obiettivo del Board."""
    for obj in state.objectives:
        if obj.key == BOARD_KEY_RECORDS:
            obj.value += 1
            obj.completed = obj.value >= obj.target


def refresh_board_objectives(state: GameState) -> None:
    """Avanzamento provvisorio durante la stagione. Il piazzamento si decide solo a fine stagione (il posto cambia a
    ogni gara e a metà stagione la classifica è ancora vuota), il bilancio può tornare falso."""
    for obj in state.objectives:
        if obj.key == BOARD_KEY_BUDGET:
            obj.completed = state.budget >= obj.target


def progress_text(state: GameState, obj: SeasonObjective) -> str:
    """Quanto manca, per la Dashboard."""
    if obj.key == BOARD_KEY_LEAGUE:
        return f"ora {state.league_position}° (obiettivo: entro il {obj.target}°)"
    if obj.key == BOARD_KEY_BUDGET:
        return f"ora €{state.budget:,}"
    if obj.key == BOARD_KEY_RECORDS:
        return f"{obj.value}/{obj.target}"
    return ""


@dataclass
class BoardVerdict:
    results: List[Tuple[str, bool]]
    passed: int
    failed: bool
    streak: int
    fired: bool


def settle_season(state: GameState, placement: int) -> Optional[BoardVerdict]:
    """Verdetto di fine stagione, da chiamare prima del cambio di livello e del bonus promozione. Aggiorna
    `board_failed_streak` e `fired`; ritorna None se la stagione non aveva obiettivi del Board."""
    objectives = board_objectives(state)
    if not objectives:
        return None
    for obj in objectives:
        if obj.key == BOARD_KEY_LEAGUE:
            obj.completed = 0 < placement <= obj.target
        elif obj.key == BOARD_KEY_BUDGET:
            obj.completed = state.budget >= obj.target
        elif obj.key == BOARD_KEY_RECORDS:
            obj.completed = obj.value >= obj.target
    passed = sum(1 for o in objectives if o.completed)
    failed = passed < BOARD_OBJECTIVES_TO_PASS
    state.board_failed_streak = state.board_failed_streak + 1 if failed else 0
    if state.board_failed_streak >= BOARD_MAX_FAILED_STREAK:
        state.fired = True
    return BoardVerdict(
        results=[(o.title, o.completed) for o in objectives],
        passed=passed,
        failed=failed,
        streak=state.board_failed_streak,
        fired=state.fired,
    )


def start_new_season(state: GameState) -> List[str]:
    """Nuovi obiettivi per la stagione che comincia (chiamata dopo il cambio di livello). Esonerato: nessuno.
    Ritorna le righe di notizia."""
    if state.fired:
        return []
    state.objectives = create_board_objectives(state.tier, state.budget)
    top = BOARD_LEAGUE_TARGET[state.tier]
    return [
        f"Sett. {state.week}: il Board assegna gli obiettivi della stagione {state.season_number}: "
        f"primi {top} in lega, bilancio non in perdita, {BOARD_MIN_RECORDS} record sociali."
    ]
