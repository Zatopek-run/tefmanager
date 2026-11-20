"""Aiuti condivisi dai test che hanno bisogno della Carriera «di una volta».

Dal 2026-11-20 (Q32) una Carriera nuova parte senza atleti e con 8 settimane di Preparazione. Molti test misurano però regole
che presuppongono una società già avviata (16 atleti, calendario di 36 settimane, obiettivi del Board standard): `start_game`
avvia la partita e, per la Carriera, la porta a quello stato **solo nei test** (nel gioco non c'è alcuna scorciatoia).
I test dell'avvio vuoto usano `GameController.start_new_game` direttamente.

Nessuna dipendenza da PyQt6 oltre al controller passato.
"""

from __future__ import annotations

from models.entities import FIRST_OUTDOOR_DATE, SeasonPhase
from models.generator import (
    build_default_lineup,
    create_season_objectives,
    generate_initial_roster,
)
from models.agents import ensure_agents
from models.simulation import auto_assign_coach, auto_build_all_relays, ensure_contracts


def make_established_career(ctrl) -> None:
    """Porta una Carriera appena creata allo stato di prima: 16 atleti, calendario senza Preparazione, obiettivi standard."""
    state = ctrl.state
    state.prep_weeks = 0
    state.season_phase = SeasonPhase.OUTDOOR
    state.start_date = FIRST_OUTDOOR_DATE
    state.objectives = create_season_objectives("career", state.tier, state.budget)
    state.athletes = generate_initial_roster(rng=ctrl.rng)
    for athlete in state.athletes:
        auto_assign_coach(state, athlete)
    state.event_lineup = build_default_lineup(state.athletes, gender="M")
    state.event_lineup_f = build_default_lineup(state.athletes, gender="F")
    auto_build_all_relays(state)
    ensure_contracts(state)
    ensure_agents(state)
    state.news_log = [f"Sett. 1: Carriera Completa avviata per {state.team_name}! (test: rosa iniziale di 16 atleti)"]
    ctrl._persist()


def start_game(ctrl, team_name: str = "CUS Test", game_mode: str = "career", **kwargs):
    """`ctrl.start_new_game(...)` e, per la Carriera, rosa e calendario «di una volta» (vedi `make_established_career`)."""
    ctrl.start_new_game(team_name=team_name, game_mode=game_mode, **kwargs)
    if game_mode == "career":
        make_established_career(ctrl)
    return ctrl


__all__ = ["make_established_career", "start_game"]
