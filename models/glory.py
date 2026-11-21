"""Momenti di gloria (PIANOLAVORO F.4): funzioni pure, senza Qt e **senza RNG**.

Dopo ogni settimana il controller chiede qui quali eventi meritano un popup celebrativo: un **record del mondo**, un **momento
storico** (muro abbattuto), la **promozione** o il **titolo** a fine stagione e l'**atleta dell'anno**. Sono messe in scena, non
cambiano nulla del gioco: i momenti non sono salvati (come i risultati di una gara); i due che non lasciavano già traccia
(record del mondo, atleta dell'anno) ne lasciano una riga nel registro notizie e nei traguardi. Convocazione in nazionale e
invito alla Diamond League non esistono ancora (C.1b) e restano fuori.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

from models.entities import (
    EVENTS,
    RELAYS,
    WORLD_RECORD_EPSILON,
    WORLD_RECORDS,
    CompetitionSummary,
    EventResult,
    GameState,
    SeasonEndResult,
    SeasonOutcome,
)

WORLD_RECORD = "world_record"
HISTORIC = "historic"
PROMOTION = "promotion"
CHAMPION = "champion"
ATHLETE_OF_THE_YEAR = "athlete_of_the_year"
HISTORIC_MARK = "MOMENTO STORICO!"


@dataclass
class GloryMoment:
    kind: str
    title: str
    text: str
    athlete_name: Optional[str] = None
    # Riga da scrivere nel registro notizie e nei traguardi se il momento non ne ha già una (None = già registrato altrove).
    log_line: Optional[str] = None


def is_world_record(event: str, gender: str, mark_value: float) -> bool:
    """Vero se `mark_value` raggiunge (o supera) il record del mondo del gioco per quell'evento e sesso."""
    record = WORLD_RECORDS.get((event, gender))
    if record is None:
        return False
    event_def = EVENTS.get(event)
    if event_def is None:
        return False
    if event_def.lower_is_better:
        return mark_value <= record + WORLD_RECORD_EPSILON
    return mark_value >= record - WORLD_RECORD_EPSILON


def _player_standing(result: EventResult):
    return next((s for s in result.standings if s.is_player), None)


def meeting_moments(state: GameState, summary: CompetitionSummary, new_milestones: Iterable[str] = ()) -> List[GloryMoment]:
    """Momenti di un meeting appena giocato: record del mondo (misura valida, mai staffette né ritiri) e muri abbattuti."""
    moments: List[GloryMoment] = []
    if summary.club_absent:
        return moments
    for result in summary.event_results:
        if result.event_name in RELAYS or result.withdrew_injured or result.disqualified or result.wind_illegal:
            continue
        standing = _player_standing(result)
        if standing is None or not is_world_record(result.event_name, result.gender, standing.mark_value):
            continue
        name = result.player_athlete_name
        label = f"{result.event_name} ({result.gender})"
        moments.append(
            GloryMoment(
                WORLD_RECORD,
                "RECORD DEL MONDO!",
                f"{name} segna {result.player_mark} nei {label} a {summary.meet_name}: nessuno ha mai fatto meglio.",
                name,
                log_line=f"Sett. {summary.week}: RECORD DEL MONDO! {name} segna {result.player_mark} nei {label}.",
            )
        )
    for line in new_milestones:
        if HISTORIC_MARK in line:
            text = line.split(": ", 1)[-1]
            moments.append(GloryMoment(HISTORIC, "MOMENTO STORICO", text))
    return moments


def season_awards(state: GameState, season: int) -> List[Tuple[str, int, int]]:
    """Podi individuali di ogni atleta del club nella stagione `season`: (nome, vittorie, podi), dal migliore al peggiore.
    Vale chi ha almeno un podio in una gara individuale; a parità di vittorie e podi il nome alfabeticamente primo."""
    first, last = (season - 1) * state.season_length + 1, season * state.season_length
    tally: Dict[str, List[int]] = {}
    for summary in state.competition_history:
        if not (first <= summary.week <= last) or summary.club_absent:
            continue
        for result in summary.event_results:
            if result.event_name in RELAYS or result.withdrew_injured or result.disqualified:
                continue
            if 1 <= result.placement <= 3:
                wins_podiums = tally.setdefault(result.player_athlete_name, [0, 0])
                wins_podiums[0] += 1 if result.placement == 1 else 0
                wins_podiums[1] += 1
    rows = [(name, wp[0], wp[1]) for name, wp in tally.items()]
    return sorted(rows, key=lambda row: (-row[1], -row[2], row[0]))


def season_moments(state: GameState, result: SeasonEndResult) -> List[GloryMoment]:
    """Momenti di fine stagione: titolo o promozione del club e atleta dell'anno."""
    moments: List[GloryMoment] = []
    if result.outcome == SeasonOutcome.CHAMPION:
        moments.append(
            GloryMoment(
                CHAMPION, "CAMPIONI!",
                f"{state.team_name} chiude {result.placement}ª e vince la lega {result.tier.display_name}.",
            )
        )
    elif result.outcome == SeasonOutcome.PROMOTED and result.new_tier is not None:
        moments.append(
            GloryMoment(
                PROMOTION, "PROMOZIONE!",
                f"{state.team_name} chiude {result.placement}ª in {result.tier.display_name} e sale in "
                f"{result.new_tier.display_name}.",
            )
        )
    awards = season_awards(state, result.season)
    if awards:
        name, wins, podiums = awards[0]
        moments.append(
            GloryMoment(
                ATHLETE_OF_THE_YEAR, "ATLETA DELL'ANNO",
                f"{name} è l'atleta dell'anno: {wins} vittorie e {podiums} podi nella stagione {result.season}.",
                name,
                log_line=f"Stagione {result.season}: ATLETA DELL'ANNO! {name} ({wins} vittorie, {podiums} podi).",
            )
        )
    return moments
