"""Obiettivi del Board ed esonero (PIANOLAVORO C.2). Nessuna dipendenza da Qt e nessuna chiamata all'RNG.

A inizio stagione (solo Carriera: il Prototipo non ha stagioni) il Board assegna tre obiettivi:

- **Piazzamento:** chiudere tra i primi `BOARD_LEAGUE_TARGET[livello]` della lega (più largo nei livelli alti);
- **Bilancio:** non chiudere la stagione in perdita, cioè con un budget almeno pari a quello di inizio stagione
  (il bonus promozione si somma dopo il verdetto e non aiuta);
- **Record:** stabilire almeno `BOARD_MIN_RECORDS` record sociali, individuali o di staffetta (i primi record di una
  partita nuova sono facili: in una società senza record, ogni primato lo è).

A fine stagione (`settle_season`, chiamata da `close_season`) la stagione è **fallita** se si centrano meno di
`BOARD_OBJECTIVES_TO_PASS` obiettivi su tre **oppure** se non si centra il posto in lega (`BOARD_LEAGUE_REQUIRED`: il piazzamento è
obbligatorio, scelta dell'utente del 2026-11-21, Q27). `BOARD_MAX_FAILED_STREAK` stagioni fallite **di fila** portano all'esonero
(`GameState.fired`, game over come il fallimento): una stagione non fallita azzera il conto. Un salvataggio iniziato
prima di C.2 ha ancora gli obiettivi vecchi fino a fine stagione: quella stagione non viene giudicata.

**Fondazione (Q32).** Una Carriera nuova parte senza atleti: nella stagione 1 il Board non chiede risultati ma di costruire la
società (`create_foundation_objectives`: atleti in società, ragazzi nel vivaio, meeting a cui si partecipa). Il verdetto è solo
informativo: non conta come stagione fallita, non tocca `board_failed_streak` e non può esonerare. La stagione 2 ha le tre chiavi
standard con il solo posto in lega ammorbidito in base alla forza della rosa (`league_target`); dalla 3 è tutto standard.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Tuple

from models.entities import (
    BOARD_KEY_BUDGET,
    BOARD_KEY_LEAGUE,
    BOARD_KEY_RECORDS,
    BOARD_KEYS,
    BOARD_LEAGUE_REQUIRED,
    BOARD_LEAGUE_TARGET,
    BOARD_MAX_FAILED_STREAK,
    BOARD_MIN_RECORDS,
    BOARD_OBJECTIVES_TO_PASS,
    BOARD_RAMP_GAP_PER_PLACE,
    BOARD_RAMP_MAX_SLACK,
    BOARD_RAMP_SQUAD_SIZE,
    FOUND_KEY_ATHLETES,
    FOUND_KEY_MEETS,
    FOUND_KEY_YOUTH,
    FOUNDATION_KEYS,
    FOUNDATION_MIN_ATHLETES,
    FOUNDATION_MIN_MEETS,
    FOUNDATION_MIN_YOUTH,
    CompetitionTier,
    GameState,
    SeasonObjective,
)


def create_board_objectives(tier: CompetitionTier, budget: int, top: Optional[int] = None) -> List[SeasonObjective]:
    """I tre obiettivi di una stagione che inizia nel livello `tier` con `budget` in cassa (`top` = posto massimo in lega)."""
    top = BOARD_LEAGUE_TARGET[tier] if top is None else top
    return [
        SeasonObjective(BOARD_KEY_LEAGUE, f"Chiudi la stagione tra i primi {top} della lega {tier.display_name} (obbligatorio)", target=top),
        SeasonObjective(
            BOARD_KEY_BUDGET, f"Non chiudere la stagione in perdita: bilancio almeno €{budget:,}", target=budget
        ),
        SeasonObjective(
            BOARD_KEY_RECORDS, f"Stabilisci almeno {BOARD_MIN_RECORDS} record sociali", target=BOARD_MIN_RECORDS
        ),
    ]


def create_foundation_objectives() -> List[SeasonObjective]:
    """Gli obiettivi della stagione di fondazione (Carriera nuova, senza atleti): costruire la società, non vincere."""
    return [
        SeasonObjective(
            FOUND_KEY_ATHLETES,
            f"Fonda la rosa: almeno {FOUNDATION_MIN_ATHLETES} atleti in società (Prima Squadra e vivaio)",
            target=FOUNDATION_MIN_ATHLETES,
        ),
        SeasonObjective(
            FOUND_KEY_YOUTH,
            f"Avvia il settore giovanile: almeno {FOUNDATION_MIN_YOUTH} ragazzi nel vivaio",
            target=FOUNDATION_MIN_YOUTH,
        ),
        SeasonObjective(
            FOUND_KEY_MEETS,
            f"Schiera la società in almeno {FOUNDATION_MIN_MEETS} meeting",
            target=FOUNDATION_MIN_MEETS,
        ),
    ]


def foundation_value(state: GameState, key: str) -> int:
    """Avanzamento di un obiettivo di fondazione, letto dallo stato (nessun contatore da tenere aggiornato)."""
    if key == FOUND_KEY_ATHLETES:
        return len(state.athletes)
    if key == FOUND_KEY_YOUTH:
        return len(state.youth_squad)
    if key == FOUND_KEY_MEETS:
        first = (state.season_number - 1) * state.season_length + 1
        last = state.season_number * state.season_length
        return sum(1 for m in state.competition_history if m.event_results and first <= m.week <= last)
    return 0


def league_target(state: GameState) -> int:
    """Posto massimo in lega richiesto nella stagione che comincia. Standard tranne nella stagione 2 di una Carriera nuova:
    si allarga di un posto ogni `BOARD_RAMP_GAP_PER_PLACE` punti di forza che la rosa ha sotto i rivali (al massimo
    `BOARD_RAMP_MAX_SLACK`), perché la società è appena nata e non va giudicata come una già avviata."""
    base = BOARD_LEAGUE_TARGET[state.tier]
    if state.prep_weeks <= 0 or state.season_number != 2:
        return base
    rivals = state.rivals_in()
    best = sorted((a.overall for a in state.main_squad), reverse=True)[:BOARD_RAMP_SQUAD_SIZE]
    strength = sum(best) / len(best) if best else 0.0
    rival_level = sum(c.level() for c in rivals) / len(rivals) if rivals else strength
    slack = min(BOARD_RAMP_MAX_SLACK, math.ceil(max(0.0, rival_level - strength) / BOARD_RAMP_GAP_PER_PLACE))
    return min(len(rivals) + 1, base + slack)


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
        elif obj.key in FOUNDATION_KEYS:
            obj.value = foundation_value(state, obj.key)
            obj.completed = obj.value >= obj.target


def progress_text(state: GameState, obj: SeasonObjective) -> str:
    """Quanto manca, per la Dashboard."""
    if obj.key == BOARD_KEY_LEAGUE:
        return f"ora {state.league_position}° (obiettivo: entro il {obj.target}°)"
    if obj.key == BOARD_KEY_BUDGET:
        return f"ora €{state.budget:,}"
    if obj.key == BOARD_KEY_RECORDS:
        return f"{obj.value}/{obj.target}"
    if obj.key in FOUNDATION_KEYS:  # letto dallo stato: resta giusto anche tra un tick e l'altro (tesseramenti)
        return f"{foundation_value(state, obj.key)}/{obj.target}"
    return ""


@dataclass
class BoardVerdict:
    results: List[Tuple[str, bool]]
    passed: int
    failed: bool
    streak: int
    fired: bool
    foundation: bool = False  # stagione di fondazione: verdetto solo informativo (`failed` è sempre False)


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
        elif obj.key in FOUNDATION_KEYS:
            obj.value = foundation_value(state, obj.key)
            obj.completed = obj.value >= obj.target
    passed = sum(1 for o in objectives if o.completed)
    if any(o.key in FOUNDATION_KEYS for o in objectives):
        # Fondazione (Q32): nessuna stagione fallita, il conto delle stagioni fallite di fila non si muove, nessun esonero.
        return BoardVerdict(
            results=[(o.title, o.completed) for o in objectives],
            passed=passed,
            failed=False,
            streak=state.board_failed_streak,
            fired=False,
            foundation=True,
        )
    league_met = all(o.completed for o in objectives if o.key == BOARD_KEY_LEAGUE)
    failed = passed < BOARD_OBJECTIVES_TO_PASS or (BOARD_LEAGUE_REQUIRED and not league_met)  # Q27: il posto in lega è obbligatorio
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
    top = league_target(state)
    state.objectives = create_board_objectives(state.tier, state.budget, top)
    return [
        f"Sett. {state.week}: il Board assegna gli obiettivi della stagione {state.season_number}: "
        f"primi {top} in lega, bilancio non in perdita, {BOARD_MIN_RECORDS} record sociali."
    ]
