"""Conferenza stampa dopo la gara (PIANOLAVORO F.2): funzioni pure, senza Qt e **senza RNG**.

Dopo ogni meeting del club il giornalista fa due domande: una sulla **prestazione** (le risposte spostano la reputazione, in
modo coerente con il risultato: dirsi soddisfatti dopo un ultimo posto costa) e una sul **futuro del miglior atleta del
meeting** (le risposte spostano la relazione con il suo agente, D.1). La formulazione si sceglie con `crc32`, mai con l'RNG
della partita. Non esiste un morale per atleta nel gioco: la relazione con l'agente è il solo canale tra la tua risposta e
l'atleta. Chiudere senza rispondere non ha effetti; la conferenza non è salvata (come i risultati della gara).
"""
from __future__ import annotations

import zlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from models.agents import adjust_relation, agent_of
from models.entities import (
    PRESS_BAD_FROM_BOTTOM,
    PRESS_GOOD_MAX_PLACEMENT,
    PRESS_MIN_TEAMS,
    PRESS_RELATION,
    PRESS_REPUTATION,
    Athlete,
    CompetitionSummary,
    GameState,
)
from models.generator import clamp_stat

PERFORMANCE = "prestazione"
FUTURE = "futuro"

# Etichette delle risposte (le chiavi sono quelle di `PRESS_REPUTATION` e `PRESS_RELATION`).
PERFORMANCE_OPTIONS: Dict[str, str] = {
    "soddisfatto": "Siamo molto soddisfatti, la squadra ha fatto bene",
    "cauto": "C'è del buono, ma si può migliorare",
    "critico": "No, ci aspettavamo di più: dobbiamo fare meglio",
}
FUTURE_OPTIONS: Dict[str, str] = {
    "punto": "È un punto fermo del nostro progetto",
    "valuto": "Valuteremo settimana per settimana",
    "dubbio": "Il suo posto non è garantito",
}


@dataclass
class PressQuestion:
    key: str  # PERFORMANCE o FUTURE
    text: str
    options: Dict[str, str]  # chiave della risposta -> testo
    athlete_name: Optional[str] = None  # solo per FUTURE


@dataclass
class PressConference:
    week: int
    meet_name: str
    tier: str  # good / average / bad
    questions: List[PressQuestion] = field(default_factory=list)


def _pick(variants: List[str], state: GameState, kind: str, subject: str = "") -> str:
    return variants[zlib.crc32(f"{state.season_number}|{state.week}|{kind}|{subject}".encode()) % len(variants)]


def performance_tier(summary: CompetitionSummary) -> str:
    """good / average / bad in base alla posizione del club nella classifica a squadre del meeting."""
    teams = len(summary.team_standings)
    placement = summary.team_placement
    if placement <= 0 or teams < PRESS_MIN_TEAMS:
        return "average"
    if placement <= PRESS_GOOD_MAX_PLACEMENT:
        return "good"
    if placement > teams - PRESS_BAD_FROM_BOTTOM:
        return "bad"
    return "average"


def best_athlete_of(state: GameState, summary: CompetitionSummary) -> Optional[Athlete]:
    """L'atleta di Prima Squadra col miglior piazzamento individuale nel meeting (a parità, il nome alfabeticamente primo).
    Chi si è ritirato o è stato squalificato non conta; le staffette non hanno un nome di atleta e si saltano da sole."""
    by_name = {a.name: a for a in state.main_squad}
    best = None
    for result in summary.event_results:
        athlete = by_name.get(result.player_athlete_name)
        if athlete is None or result.withdrew_injured or result.disqualified or result.placement <= 0:
            continue
        rank = (result.placement, athlete.name)
        if best is None or rank < best[0]:
            best = (rank, athlete)
    return best[1] if best else None


def build_conference(state: GameState, summary: CompetitionSummary) -> Optional[PressConference]:
    """La conferenza dopo `summary`; None se il club non ha gareggiato (società senza atleti, Q32)."""
    if summary.club_absent or not summary.player_team or not state.main_squad:
        return None
    tier = performance_tier(summary)
    conference = PressConference(week=summary.week, meet_name=summary.meet_name, tier=tier)
    conference.questions.append(
        PressQuestion(
            PERFORMANCE,
            _pick(
                [
                    f"Come giudica la prestazione della squadra a {summary.meet_name}?",
                    f"Siete soddisfatti di come è andata a {summary.meet_name}?",
                    f"Un commento a caldo su {summary.meet_name}?",
                ],
                state, PERFORMANCE, summary.meet_name,
            ),
            dict(PERFORMANCE_OPTIONS),
        )
    )
    star = best_athlete_of(state, summary)
    if star is not None:
        conference.questions.append(
            PressQuestion(
                FUTURE,
                _pick(
                    [
                        f"Punta sul futuro di {star.name}?",
                        f"{star.name} è stato il migliore del vostro meeting: sarà al centro del progetto?",
                        f"Che ruolo avrà {star.name} nei prossimi mesi?",
                    ],
                    state, FUTURE, star.name,
                ),
                dict(FUTURE_OPTIONS),
                athlete_name=star.name,
            )
        )
    return conference


def apply_answers(state: GameState, conference: PressConference, answers: Dict[str, str]) -> List[str]:
    """Applica le risposte (domanda → chiave della risposta); ignora domande senza risposta o risposte sconosciute.
    Sposta reputazione e relazione con l'agente; ritorna le righe di cronaca (in testa al registro notizie)."""
    lines: List[str] = []
    prefix = f"Sett. {state.week}: Conferenza stampa a {conference.meet_name}"
    answer = answers.get(PERFORMANCE)
    if answer in PRESS_REPUTATION[conference.tier]:
        delta = PRESS_REPUTATION[conference.tier][answer]
        state.reputation = clamp_stat(state.reputation + delta, 0, 100)
        verdict = {"soddisfatto": "esprimi soddisfazione", "cauto": "resti cauto", "critico": "ti mostri critico"}[answer]
        lines.append(f"{prefix}: {verdict} (reputazione {delta:+d}).")
    answer = answers.get(FUTURE)
    question = next((q for q in conference.questions if q.key == FUTURE), None)
    if question is not None and answer in PRESS_RELATION:
        athlete = next((a for a in state.main_squad if a.name == question.athlete_name), None)
        delta = PRESS_RELATION[answer]
        if athlete is not None:
            agent = agent_of(state, athlete)
            adjust_relation(state, athlete.agent_id, delta)
            who = f" (relazione con l'agente {agent.name} {delta:+d})" if agent is not None and delta else ""
            what = {"punto": "puntare su", "valuto": "valutare", "dubbio": "non garantire il posto a"}[answer]
            lines.append(f"{prefix}: dici di {what} {athlete.name}{who}.")
    return lines
