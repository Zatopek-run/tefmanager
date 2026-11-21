"""Tabellone live della gara in diretta (PIANOLAVORO G.3): classifica, velocità e distacchi al tempo `t`, per le corse in pista.

**Sola lettura.** Usa le stesse funzioni del renderer (`position_fraction`, `reaction_time`) sugli stessi dati (`runners` di
`TrackRaceWidget`): non cambia tempi, ordine né misure, e a tempo pieno la classifica coincide con quella ufficiale (c'è un test).
Restituisce solo dict, liste, stringhe, numeri e booleani con chiavi stringa (passa a QML senza perdite).
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from models.bibs import BibKey, bib_of
from views.race_viewer import DNF_PROGRESS, TrackRaceWidget, format_race_time, position_fraction

KMH = 3.6  # m/s → km/h


def _fraction(runner: dict, event: str, t: float, winner_time: float) -> float:
    """Frazione di pista percorsa: la stessa formula di `TrackRaceWidget.fraction`."""
    if runner["dnf"]:
        f = position_fraction(event, t, winner_time * 1.25, runner["react"], runner["phase"])
        return min(DNF_PROGRESS, f * 0.9)
    return position_fraction(event, t, runner["s"].mark_value, runner["react"], runner["phase"])


def _speed_ms(runner: dict, event: str, distance: int, t: float, winner_time: float) -> float:
    """Velocità istantanea in m/s (derivata della posizione, come per la cadenza dei passi), 0 fermi, ritirati e arrivati."""
    if t <= 0 or runner["dnf"] or t >= runner["s"].mark_value:
        return 0.0
    step = max(0.05, 0.01 * winner_time)
    f0 = position_fraction(event, t - step, runner["s"].mark_value, runner["react"], runner["phase"])
    f1 = position_fraction(event, t + step, runner["s"].mark_value, runner["react"], runner["phase"])
    return max(0.0, (f1 - f0)) * distance / (2 * step)


def live_board(
    runners: Sequence[dict],
    event: str,
    distance: int,
    race_time: float,
    winner_time: float,
    bibs: Optional[Dict[BibKey, int]] = None,
    phase: str = "",
    replay: bool = False,
    race_id: str = "",
) -> dict:
    """Tabellone al tempo di gara `race_time` (dallo sparo). Le righe restano nell'ordine dei corridori (identità stabile per QML);
    `rank` dà il posto. Ordine: arrivati per piazzamento ufficiale, poi in gara per metri percorsi, poi i ritirati."""
    t = max(0.0, race_time)
    rows: List[dict] = []
    for i, r in enumerate(runners):
        s = r["s"]
        finished = (not r["dnf"]) and t >= s.mark_value
        meters = min(float(distance), _fraction(r, event, t, winner_time) * distance)
        if finished:
            meters = float(distance)
        speed = _speed_ms(r, event, distance, t, winner_time)
        avg = (distance / s.mark_value) if finished else (meters / t if t > 0 else 0.0)
        rows.append({
            "rid": i, "name": s.athlete_name, "team": s.team_name, "bib": bib_of(bibs, s) if bibs else 0, "isPlayer": bool(s.is_player),
            "kit": TrackRaceWidget._kit(s.athlete_name).name(),
            "meters": meters, "pct": meters / distance if distance else 0.0, "finished": finished, "dnf": bool(r["dnf"]),
            "speedKmh": speed * KMH, "avgKmh": avg * KMH, "place": int(s.placement), "mark": s.mark_value, "markText": s.mark_display,
            "gap": "", "rank": 0,
        })

    def order(row: dict) -> Tuple:
        if row["dnf"]:
            return (2, -row["meters"], row["rid"])
        if row["finished"]:
            return (0, row["place"], row["rid"])
        return (1, -row["meters"], row["rid"])

    ranked = sorted(rows, key=order)
    for rank, row in enumerate(ranked, start=1):
        row["rank"] = rank
    leader = ranked[0] if ranked else None
    for row in ranked:
        if leader is None or row is leader:
            continue
        if row["dnf"]:
            row["gap"] = "ritirato" if t > 0 else ""
        elif row["finished"] and leader["finished"]:
            row["gap"] = f"+{row['mark'] - leader['mark']:.2f} s"
        elif t > 0:
            row["gap"] = f"+{max(0.0, leader['meters'] - row['meters']):.1f} m"
    if leader is not None and leader["finished"]:
        leader["gap"] = leader["markText"]
    second = ranked[1] if len(ranked) > 1 and not ranked[1]["dnf"] else None
    gap_text = ""
    if leader is not None and second is not None and t > 0:
        gap_text = second["gap"] if second["gap"] else ""
    done = bool(ranked) and all(r["finished"] or r["dnf"] for r in ranked)
    return {
        "event": event, "distance": distance, "clock": format_race_time(min(winner_time, t)),
        "started": t > 0, "done": done,
        "leader": leader["name"] if leader else "", "leaderKmh": leader["speedKmh"] if leader else 0.0,
        "firstSecond": gap_text, "phase": phase, "replay": replay, "raceId": race_id, "rows": rows,
    }


def empty_board() -> dict:
    """Scheletro con tutte le chiavi (valori vuoti) per mostrare la vista QML prima della prima gara."""
    return {"event": "", "distance": 0, "clock": "", "started": False, "done": False, "leader": "", "leaderKmh": 0.0,
            "firstSecond": "", "phase": "", "replay": False, "rows": [], "raceId": ""}
