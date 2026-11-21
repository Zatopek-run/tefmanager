"""Inviti alla Diamond League (PIANOLAVORO C.1b): funzioni pure, senza Qt e **senza RNG**.

Una volta a stagione di Carriera, nel secondo meeting della fase Outdoor, una società del livello Internazionale che sta
nei primi posti della classifica di società (`models/ranking.py`) è **invitata** al meeting Diamond League, che prende il
posto di quello di lega: premi e prestigio moltiplicati, nessun punto di lega. L'invito non è salvato: è una funzione pura
dello stato (livello, classifica di società, settimana), quindi non serve alcuna colonna nel salvataggio. I punti ranking non
cambiano tra la notizia della settimana prima e il meeting, a parte i cambi di rosa fatti nel frattempo.
"""
from __future__ import annotations

from models.entities import (
    DIAMOND_INVITE_MAX_RANK,
    DIAMOND_INVITE_MIN_POINTS,
    DIAMOND_MEET_LABEL,
    DIAMOND_MEET_PHASE_OFFSET,
    CompetitionTier,
    GameState,
)
from models.ranking import club_points, club_ranking


def is_diamond_week(state: GameState, week: int) -> bool:
    """La settimana `week` è quella del meeting Diamond League della stagione (solo Carriera, solo settimane di gara)."""
    if state.game_mode != "career" or not state.is_race_week(week):
        return False
    return (week - 1) % state.season_length - state.prep_weeks == DIAMOND_MEET_PHASE_OFFSET


def club_rank(state: GameState) -> int:
    """Posto (da 1) del club nella classifica di società del livello attuale."""
    for place, (_name, _points, is_club) in enumerate(club_ranking(state), start=1):
        if is_club:
            return place
    return 0


def is_club_invited(state: GameState) -> bool:
    """Il club ha i requisiti per l'invito: livello Internazionale, almeno un atleta in Prima Squadra, abbastanza punti e un posto nei primi."""
    if state.tier != CompetitionTier.INTERNAZIONALE or not state.main_squad:
        return False
    if club_points(state) < DIAMOND_INVITE_MIN_POINTS:
        return False
    return club_rank(state) <= DIAMOND_INVITE_MAX_RANK


def is_diamond_meet(state: GameState, week: int | None = None) -> bool:
    """Il meeting della settimana `week` (di default quella attuale) è la Diamond League e il club è invitato."""
    return is_diamond_week(state, state.week if week is None else week) and is_club_invited(state)


def diamond_meet_name(base_name: str) -> str:
    """Nome del meeting a invito: il nome del meeting di lega al quale si sostituisce, preceduto da «Diamond League»."""
    return f"{DIAMOND_MEET_LABEL} — {base_name}"
