"""Notizie dinamiche (PIANOLAVORO F.1): il giornale racconta ciò che è successo. Funzioni pure, senza Qt e **senza RNG**.

Il generatore gira a ogni chiusura di mese (stesso istante del bilancio mensile, `close_month_if_due`) e scrive **al più una
riga per tipo**: spogliatoio, stampa, premio del mese. La scelta tra le varianti di una frase è deterministica
(`zlib.crc32` di stagione, settimana, tipo e soggetto, mai `hash()`), quindi non sposta l'RNG della partita e lo stesso
salvataggio racconta sempre le stesse notizie. Le righe sono solo cronaca: nessun effetto su morale o reputazione (arrivano
con le conferenze stampa, F.2).
"""
from __future__ import annotations

import zlib
from typing import List, Optional

from models.agents import agent_of
from models.entities import NARRATIVE_TENSION_RELATION, CompetitionSummary, GameState


def _pick(variants: List[str], state: GameState, kind: str, subject: str = "") -> str:
    key = f"{state.season_number}|{state.week}|{kind}|{subject}"
    return variants[zlib.crc32(key.encode()) % len(variants)]


def _meet_of_month(state: GameState, first_week: int, last_week: int) -> Optional[CompetitionSummary]:
    """L'ultimo meeting del club giocato tra `first_week` e `last_week` (nessuno se il club era assente)."""
    meets = [
        s for s in state.competition_history
        if first_week <= s.week <= last_week and not s.club_absent and s.player_team
    ]
    return meets[0] if meets else None  # `competition_history` ha il più recente in testa


def locker_room_news(state: GameState) -> Optional[str]:
    """«Tensione nello spogliatoio»: l'atleta di Prima Squadra con la relazione più bassa con il suo agente, se è sotto soglia."""
    worst = None
    for athlete in state.main_squad:
        agent = agent_of(state, athlete)
        if agent is None or agent.relation > NARRATIVE_TENSION_RELATION:
            continue
        if worst is None or (agent.relation, athlete.name) < (worst[0], worst[1].name):
            worst = (agent.relation, athlete)
    if worst is None:
        return None
    name = worst[1].name
    return _pick(
        [
            f"Tensione nello spogliatoio: {name} è insoddisfatto e il suo agente lo fa sapere.",
            f"Aria pesante negli spogliatoi: {name} non nasconde il malumore per come viene impiegato.",
            f"Voci di malcontento: {name} pensa a un futuro altrove se le cose non cambiano.",
        ],
        state, "spogliatoio", name,
    )


def press_news(state: GameState, meet: Optional[CompetitionSummary]) -> Optional[str]:
    """«La stampa critica la tua gestione»: conti in rosso, obiettivi del Board mancati o fondo classifica nell'ultimo meeting."""
    if state.budget < 0:
        reason = "i conti in rosso"
    elif state.board_failed_streak >= 1:
        reason = "gli obiettivi del Board mancati"
    elif meet is not None and len(meet.team_standings) >= 3 and meet.team_placement == len(meet.team_standings):
        reason = "l'ultimo posto nell'ultimo meeting"
    else:
        return None
    return _pick(
        [
            f"La stampa critica la tua gestione: pesano {reason}.",
            f"Giornali severi con {state.team_name}: «{reason[0].upper() + reason[1:]}» è il tema della settimana.",
            f"Editoriale duro sulla società: {reason} mettono in dubbio la guida tecnica.",
        ],
        state, "stampa", reason,
    )


def coach_of_the_month_news(state: GameState, meet: Optional[CompetitionSummary]) -> Optional[str]:
    """«Allenatore del Mese»: il club ha vinto il meeting del mese appena chiuso."""
    if meet is None or meet.team_placement != 1:
        return None
    return _pick(
        [
            f"Sei stato nominato «Allenatore del Mese» dopo la vittoria a {meet.meet_name}!",
            f"Premio «Allenatore del Mese»: la giuria sceglie te per il successo a {meet.meet_name}.",
            f"{state.team_name} domina {meet.meet_name} e la tua guida vale il titolo di «Allenatore del Mese».",
        ],
        state, "premio", meet.meet_name,
    )


def monthly_news(state: GameState, first_week: int, last_week: int) -> List[str]:
    """Le notizie di un mese appena chiuso (`first_week`-`last_week`), nell'ordine premio, stampa, spogliatoio.

    Senza atleti in Prima Squadra (avvio da zero, Q32) e nella stagione di fondazione non si scrive nulla: non c'è ancora
    una squadra di cui parlare.
    """
    if not state.main_squad or state.is_foundation(state.season_number):
        return []
    meet = _meet_of_month(state, first_week, last_week)
    lines = [
        coach_of_the_month_news(state, meet),
        press_news(state, meet),
        locker_room_news(state),
    ]
    prefix = f"Sett. {last_week}: "
    return [prefix + line for line in lines if line]
