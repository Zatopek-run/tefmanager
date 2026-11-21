"""Dati calcolati per la Dashboard (PIANOLAVORO G.1): andamento della rosa, heat map atleti × gare, timeline della stagione.

Funzioni pure, senza Qt e senza RNG: le viste (`views/widgets.py`) disegnano, qui si decide che cosa. Nessuna scrittura sullo stato.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from models.board import progress_text
from models.entities import (
    BANKRUPTCY_THRESHOLD,
    BOARD_KEYS,
    BOARD_MAX_FAILED_STREAK,
    COACH_COMFORT_LOAD,
    EVENTS,
    HEATMAP_ATHLETES,
    HEATMAP_SCORE_HIGH,
    HEATMAP_SCORE_LOW,
    HISTORY_WEEKS,
    PROMOTION_SPOTS,
    RELEGATION_SPOTS,
    YOUTH_SQUAD_MAX,
    Athlete,
    GameState,
)
from models.history import weekly_series
from models.simulation import expected_event_score, weekly_finances


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


EMPTY_SQUAD_TEXT = (
    "Nessun atleta in rosa. Vai a «Vivaio && Osservatori» per lo scouting dei giovani, oppure a «Rosa && Allenamenti» "
    "→ «Mercato Svincolati» per tesserare i primi atleti."
)


def weekly_action_items(state: GameState, free_agent_pool: Optional[list] = None) -> list[tuple[str, str, int]]:
    """Return actionable alerts `(text, severity, target_tab_index)` for the current week."""
    items: list[tuple[str, str, int]] = []
    by_id = {a.id: a for a in state.main_squad}

    if not state.main_squad:  # società senza atleti: il primo passo è tesserarli, non coprire 12 gare
        items.append(("Nessun atleta in rosa: apri lo scouting e tessera i primi atleti", "warn", 2))

    missing_lineups = 0
    injured_lineups = 0
    lineup_ids: set[int] = set()
    for gender in ("M", "F") if state.main_squad else ():
        lineup = state.lineup_for(gender)
        for ev in state.active_events:
            aid = lineup.get(ev)
            ath = by_id.get(aid) if aid is not None else None
            if ath is None:
                missing_lineups += 1
            else:
                lineup_ids.add(aid)
                if ath.is_injured:
                    injured_lineups += 1

    if missing_lineups or injured_lineups:
        parts = []
        if missing_lineups:
            parts.append(f"{missing_lineups} gare scoperte")
        if injured_lineups:
            parts.append(f"{injured_lineups} infortunati")
        sev = "danger" if state.is_competition_week else "warn"
        items.append((f"Convocazioni: {', '.join(parts)}", sev, 3))

    injured_bench = sum(
        1 for a in state.main_squad if a.is_injured and a.id not in lineup_ids
    )
    if injured_bench:
        items.append((f"{injured_bench} infortunati non convocati in formazione", "warn", 1))

    if not state.bankrupt and state.budget < 0:
        sev = "danger" if state.budget <= BANKRUPTCY_THRESHOLD // 2 else "warn"
        items.append((f"Bilancio in rosso: €{state.budget:,}", sev, 7))

    if free_agent_pool is not None and not free_agent_pool:
        items.append(("Mercato: nuovi svincolati da valutare questa settimana", "ok", 1))

    incomplete_relays = 0
    for gender in ("M", "F") if state.main_squad else ():
        relays = state.relays_for(gender)
        for name in state.active_relays:
            r = relays.get(name)
            if r is None or not r.is_complete:
                incomplete_relays += 1
    if incomplete_relays:
        items.append((f"Staffette: {incomplete_relays} formazioni incomplete", "warn", 4))

    tired = sum(1 for a in state.main_squad if not a.is_injured and a.fatigue >= 75)
    if tired:
        msg = (
            f"Gara vicina: {tired} atleti stanchi (valuta Scarico)"
            if state.is_competition_week
            else f"{tired} atleti con fatica ≥ 75%"
        )
        items.append((msg, "danger" if state.is_competition_week else "warn", 1))

    overloaded = sum(1 for c in state.coaches if state.coach_load(c) > COACH_COMFORT_LOAD)
    if overloaded:
        items.append((f"{overloaded} allenatori oltre {COACH_COMFORT_LOAD} atleti", "warn", 6))

    if state.track_condition < 60:
        items.append((f"Pista usurata al {state.track_condition}% (manutenzione)", "warn", 6))

    if state.scouting_points_left >= 2 and len(state.youth_squad) < YOUTH_SQUAD_MAX:
        items.append((f"Osservatori: {state.scouting_points_left} punti scouting", "ok", 2))

    if not items:
        items.append(("Tutto pronto per avanzare la settimana.", "ok", 0))
    return items


def short_event_name(name: str) -> str:
    """Nome breve di una gara per le intestazioni strette: «100m» resta, «Salto in Lungo» → «Lungo», «Getto del Peso» → «Peso»."""
    return name if any(ch.isdigit() for ch in name) else name.split()[-1]


# ---------------------------------------------------------------- istantanea per la Dashboard QML
TOP_ATHLETES = 8  # righe della tabella dei migliori atleti
NEWS_LINES = 8  # righe di cronaca
MILESTONE_LINES = 4  # traguardi in testa alla cronaca


def _kpis(state: GameState) -> List[dict]:
    net = weekly_finances(state)["net"]
    sign = "+" if net >= 0 else ""
    if state.bankrupt:
        budget_sub = "SOCIETÀ FALLITA — avvia una nuova partita"
    elif state.budget < 0:
        budget_sub = f"In rosso: 5% interessi/sett, fallimento sotto -€{-BANKRUPTCY_THRESHOLD:,}"
    else:
        budget_sub = f"Flusso netto {sign}€{net:,}/sett"
    squad = state.main_squad
    if squad:
        squad_value = f"{sum(1 for a in squad if not a.is_injured)}/{len(squad)} Sani"
        squad_sub = f"Vivaio {len(state.youth_squad)}/{YOUTH_SQUAD_MAX} · Pista {state.track_condition}%"
    else:
        squad_value, squad_sub = "Nessun atleta", "Vai a Vivaio & Osservatori o al Mercato per tesserare"
    if state.is_vertical_slice_complete:
        comp_value, comp_sub, comp_tone = "Prototipo OK", "2 gare completate — avvia Carriera!", "good"
    elif state.is_competition_week:
        comp_value, comp_sub, comp_tone = "QUESTA SETT!", "Prepara lo Scarico & gareggia", "warn"
    else:
        venue = "In casa" if state.next_meet_is_home else "In trasferta"
        comp_value, comp_sub, comp_tone = f"Tra {state.weeks_until_competition} sett.", f"{venue} · {state.season_phase.value}", ""
    return [
        {"key": "budget", "title": "BILANCIO SOCIETÀ", "value": f"€{state.budget:,}", "sub": budget_sub,
         "tone": "bad" if state.budget < 0 else "", "target": 7, "hint": "Clicca per aprire Finanze"},
        {"key": "prestige", "title": "PRESTIGIO & ETICA", "value": f"{state.prestige} pt", "sub": f"Reputazione Etica: {state.reputation}%",
         "tone": "", "target": 5, "hint": "Clicca per aprire Rivali & Classifica"},
        {"key": "squad", "title": "ROSA & PISTA TARTAN", "value": squad_value, "sub": squad_sub,
         "tone": "", "target": 1, "hint": "Clicca per aprire Rosa & Allenamenti"},
        {"key": "race", "title": "PROSSIMA GARA", "value": comp_value, "sub": comp_sub,
         "tone": comp_tone, "target": 3, "hint": "Clicca per aprire Calendario & Gare"},
    ]


def _season(state: GameState) -> dict:
    pos = state.league_position
    standings = state.league_standings()
    pts = dict(standings).get(state.team_name, 0)
    weeks_left = state.weeks_to_season_end
    if weeks_left is None:
        lead = f"Lega {state.tier.display_name}: {pos}° su {len(standings)} con {pts} pt (promozioni e retrocessioni solo in Carriera)"
        progress = {"value": min(8, state.week), "max": 8, "text": f"Prototipo: settimana {min(8, state.week)} di 8"}
    else:
        if pos <= PROMOTION_SPOTS and state.tier.next_tier is not None:
            zone = f"zona promozione → {state.tier.next_tier.display_name}"
        elif pos <= PROMOTION_SPOTS:
            zone = "in corsa per il titolo" if pos > 1 else "in testa: verso il titolo"
        elif pos > len(standings) - RELEGATION_SPOTS and state.tier.previous_tier is not None:
            zone = f"zona retrocessione → {state.tier.previous_tier.display_name}"
        else:
            zone = "metà classifica"
        lead = f"Lega {state.tier.display_name}: {pos}° su {len(standings)} con {pts} pt — {zone}"
        progress = {
            "value": state.season_length - weeks_left,
            "max": state.season_length,
            "text": f"Stagione {state.season_number}: mancano {weeks_left} settimane al verdetto (prime {PROMOTION_SPOTS} su, ultima giù)",
        }
    n_m, n_f = len(state.club_records), len(state.club_records_f)
    if n_m or n_f:
        archive = f" · {len(state.season_history)} stagioni in archivio" if state.season_history else ""
        records = f"Record Sociali omologati: {n_m} maschili · {n_f} femminili{archive}"
    else:
        records = "Record Sociali: nessun record ancora omologato."
    in_career = state.game_mode == "career"  # il Prototipo dura 8 settimane e non ha stagioni né contratti: niente timeline
    tl = season_timeline(state)
    contracts = ""
    if in_career and tl.expiring:
        shown = ", ".join(tl.expiring[:2]) + (f" e altri {len(tl.expiring) - 2}" if len(tl.expiring) > 2 else "")
        contracts = f"Contratti in scadenza a fine stagione: {shown}"
    weeks = []
    for w in tl.weeks:
        kind = "gara" if w.is_race else ("Preparazione" if w.is_prep else "allenamento")
        weeks.append(
            {"number": w.number, "race": w.is_race, "prep": w.is_prep, "phaseStart": w.is_phase_start, "current": w.is_current,
             "past": w.is_past, "tip": f"Settimana {w.number}: {kind}" + (" · oggi" if w.is_current else "")}
        )
    return {
        "lead": lead, "progress": progress, "records": records, "contracts": contracts,
        "showTimeline": in_career, "weeks": weeks, "phases": [p.value.split(" (")[0] for p in state.season_cycle],
    }


def _objectives(state: GameState) -> List[dict]:
    rows = []
    for obj in state.objectives:
        progress = progress_text(state, obj) if obj.key in BOARD_KEYS else ""
        rows.append({"text": obj.title + (f" — {progress}" if progress else ""), "done": bool(obj.completed), "kind": "objective"})
    if state.fired:
        rows.append({"text": "ESONERATO dal Board: la partita è finita.", "done": False, "kind": "fired"})
    elif state.board_failed_streak:
        rows.append({
            "text": f"Attenzione: {state.board_failed_streak} stagione/i fallita/e di fila. Alla {BOARD_MAX_FAILED_STREAK}ª arriva l'esonero.",
            "done": False, "kind": "warn",
        })
    return rows


def _heat(state: GameState) -> Optional[dict]:
    hm = heat_map(state)
    if hm is None:
        return None
    rows = []
    for a, scores, best in zip(hm.athletes, hm.scores, hm.best_columns):
        cells = [
            {"score": round(sc), "level": heat_level(sc), "best": c == best,
             "tip": f"{a.name} · {hm.events[c]}: punteggio atteso {sc:.0f} (forma {a.form}, fatica {a.fatigue})"}
            for c, sc in enumerate(scores)
        ]
        rows.append({"id": a.id or -1, "name": a.name, "injured": a.is_injured, "cells": cells})
    return {"events": [short_event_name(e) for e in hm.events], "rows": rows}


def _top(state: GameState) -> dict:
    squad = sorted(state.main_squad, key=lambda a: a.overall, reverse=True)[:TOP_ATHLETES]
    rows = []
    for a in squad:
        level = "danger" if (a.is_injured or a.doping_boost_weeks > 0) else ("warn" if a.fatigue >= 75 else "ok")
        rows.append({"id": a.id or -1, "name": f"{a.name} ({a.gender})", "specialty": a.specialty.value, "ovr": a.overall,
                     "form": a.form, "fatigue": a.fatigue, "status": a.status_label, "level": level})
    return {"rows": rows, "emptyText": "" if rows else EMPTY_SQUAD_TEXT.replace("&&", "&")}


def _pill(state: GameState, actions: List[dict]) -> dict:
    """Semaforo: rosso se c'è un dilemma da risolvere o un'urgenza, ambra se c'è qualcosa da guardare, verde se tutto ok."""
    danger = sum(1 for a in actions if a["severity"] == "danger")
    warn = sum(1 for a in actions if a["severity"] == "warn")
    if state.pending_dilemma is not None:
        return {"level": "danger", "text": "Dilemma da risolvere"}
    if danger:
        return {"level": "danger", "text": f"{danger} urgenz{'a' if danger == 1 else 'e'}"}
    if warn:
        return {"level": "warn", "text": f"{warn} da guardare"}
    return {"level": "ok", "text": "Tutto ok"}


def dashboard_snapshot(state: GameState, free_agent_pool: Optional[list] = None) -> dict:
    """Tutto ciò che la Dashboard mostra, già pronto (testi compresi): solo dict, liste, stringhe, numeri e booleani con chiavi stringa.

    La vista QML non ricalcola nulla (né regole né soglie): disegna questo. Nessuna scrittura sullo stato, nessun RNG."""
    trend = squad_trend(state)
    tips = []
    for i, (f, t) in enumerate(trend):
        ago = len(trend) - 1 - i
        tips.append(f"{'ultima settimana' if ago == 0 else f'{ago} sett. fa'}: forma {f:.0f} · fatica {t:.0f}")
    actions = [{"text": t, "severity": sev, "target": idx} for t, sev, idx in weekly_action_items(state, free_agent_pool)]
    return {
        "pill": _pill(state, actions),
        "kpis": _kpis(state),
        "trend": {
            "form": [f for f, _ in trend], "fatigue": [t for _, t in trend], "tips": tips, "weeks": HISTORY_WEEKS,
            "emptyText": ("Lo storico si riempie giocando: avanza la prima settimana." if state.main_squad
                          else "Nessun atleta in rosa: lo storico parte quando tessererai i primi atleti."),
        },
        "actions": actions,
        "season": _season(state),
        "objectives": _objectives(state),
        "heat": _heat(state),
        "news": [{"text": f"★ {m}", "star": True} for m in state.milestones[:MILESTONE_LINES]]
        + [{"text": e, "star": False} for e in state.news_log[:NEWS_LINES]],
        "top": _top(state),
    }


def empty_dashboard_snapshot() -> dict:
    """Lo scheletro con tutte le chiavi (valori vuoti): la vista QML lo mostra finché non c'è una partita, senza mai leggere chiavi mancanti."""
    kpi = {"key": "", "title": "", "value": "", "sub": "", "tone": "", "target": 0, "hint": ""}
    return {
        "pill": {"level": "ok", "text": ""},
        "kpis": [dict(kpi) for _ in range(4)],
        "trend": {"form": [], "fatigue": [], "tips": [], "weeks": HISTORY_WEEKS, "emptyText": ""},
        "actions": [],
        "season": {"lead": "", "progress": {"value": 0, "max": 1, "text": ""}, "records": "", "contracts": "",
                   "showTimeline": False, "weeks": [], "phases": []},
        "objectives": [],
        "heat": None,
        "news": [],
        "top": {"rows": [], "emptyText": ""},
    }
