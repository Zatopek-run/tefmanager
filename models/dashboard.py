"""Dati calcolati per la Dashboard (PIANOLAVORO G.1): andamento della rosa, heat map atleti × gare, timeline della stagione.

Funzioni pure, senza Qt e senza RNG: le viste (`views/widgets.py`) disegnano, qui si decide che cosa. Nessuna scrittura sullo stato.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from models.entities import (
    EVENTS,
    HEATMAP_ATHLETES,
    HEATMAP_SCORE_HIGH,
    HEATMAP_SCORE_LOW,
    Athlete,
    GameState,
)
from models.history import weekly_series
from models.simulation import expected_event_score


def squad_trend(state: GameState) -> List[Tuple[float, float]]:
    """(forma media, fatica media) della Prima Squadra per settimana, dalla più vecchia alla più recente.

    Gli storici sono allineati **dalla fine** (l'ultimo tick è l'ultimo punto di tutti): un atleta arrivato dopo ha meno punti e conta
    solo nelle settimane in cui c'era. Vuota se nessuno ha uno storico (partita appena iniziata o salvataggio vecchio)."""
    series = [weekly_series(a) for a in state.main_squad]
    depth = max((len(s) for s in series), default=0)
    out: List[Tuple[float, float]] = []
    for back in range(depth, 0, -1):  # `back` = quante settimane fa (1 = l'ultima)
        rows = [s[-back] for s in series if len(s) >= back]
        out.append((sum(r[0] for r in rows) / len(rows), sum(r[1] for r in rows) / len(rows)))
    return out


def heat_level(score: float) -> float:
    """Punteggio atteso → 0..1 (0 = freddo, 1 = caldo), lineare tra HEATMAP_SCORE_LOW e HEATMAP_SCORE_HIGH."""
    return max(0.0, min(1.0, (score - HEATMAP_SCORE_LOW) / (HEATMAP_SCORE_HIGH - HEATMAP_SCORE_LOW)))


@dataclass(frozen=True)
class HeatMap:
    events: List[str]
    athletes: List[Athlete]
    scores: List[List[float]]  # [riga atleta][colonna gara]
    best_columns: List[int]  # per riga: colonna della gara migliore dell'atleta (la sua forza)


def heat_map(state: GameState, limit: int = HEATMAP_ATHLETES) -> Optional[HeatMap]:
    """Punteggio atteso dei migliori atleti sulle gare della fase in corso. `None` senza atleti o senza gare."""
    athletes = sorted(state.main_squad, key=lambda a: a.overall, reverse=True)[:limit]
    events = [e for e in state.active_events if e in EVENTS]
    if not athletes or not events:
        return None
    scores = [[expected_event_score(a, EVENTS[e], state.track_condition) for e in events] for a in athletes]
    best = [max(range(len(events)), key=lambda c: row[c]) for row in scores]
    return HeatMap(events=events, athletes=athletes, scores=scores, best_columns=best)


@dataclass(frozen=True)
class TimelineWeek:
    number: int  # settimana nella stagione, da 1
    is_race: bool
    is_prep: bool
    is_phase_start: bool
    is_current: bool
    is_past: bool


@dataclass(frozen=True)
class SeasonTimeline:
    weeks: List[TimelineWeek]
    current: int  # settimana nella stagione, da 1
    next_race_in: Optional[int]  # settimane alla prossima gara (0 = questa settimana); None se non ce n'è
    expiring: List[str]  # atleti della Prima Squadra con il contratto in scadenza a fine stagione


def season_timeline(state: GameState) -> SeasonTimeline:
    """Le settimane della stagione in corso: gare, Preparazione, inizio fase, e i contratti che scadono a fine stagione."""
    length = state.season_length
    pos = (state.week - 1) % length  # 0-based
    base = state.week - pos  # settimana assoluta della prima della stagione
    weeks = [
        TimelineWeek(
            number=i + 1,
            is_race=state.is_race_week(base + i),
            is_prep=state.is_prep_week(base + i),
            is_phase_start=state.is_phase_start(base + i),
            is_current=i == pos,
            is_past=i < pos,
        )
        for i in range(length)
    ]
    expiring = [a.name for a in state.main_squad if a.contract_end_season == state.season_number]
    return SeasonTimeline(weeks=weeks, current=pos + 1, next_race_in=state.weeks_until_competition, expiring=expiring)
