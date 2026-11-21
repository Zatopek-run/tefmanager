"""Dati della scheda atleta (PIANOLAVORO G.2): radar, potenziale, condizione, storico gare, confronto. Funzioni pure, senza Qt e senza RNG.

`athlete_snapshot` restituisce solo dict, liste, stringhe, numeri e booleani con chiavi stringa (passa a QML senza perdite): testi, livelli e
soglie si decidono qui, la vista QML disegna e basta. Nessuna scrittura sullo stato.
"""
from __future__ import annotations

from typing import List, Optional

from models.entities import (
    EVENTS,
    HISTORY_RESULTS,
    STAT_LEVEL_GOOD,
    STAT_LEVEL_GREAT,
    STAT_LEVEL_MID,
    Athlete,
    GameState,
)
from models.history import result_percentile, results_series
from models.personal_bests import events_with_best, progression
from models.simulation import body_fit_score

RADAR_AXES = (("Velocità", "speed"), ("Resistenza", "stamina"), ("Forza", "strength"), ("Tecnica", "technique"), ("Resilienza", "resilience"))
COMPARISON_ROWS = 8  # al più gli 8 migliori della disciplina (più l'atleta, se fuori)


def stat_level(value: int, invert: bool = False) -> str:
    """Livello di una caratteristica 0-100: `great`, `good`, `mid`, `low`. `invert` per la fatica (meno è meglio)."""
    score = 100 - value if invert else value
    if score >= STAT_LEVEL_GREAT:
        return "great"
    if score >= STAT_LEVEL_GOOD:
        return "good"
    if score >= STAT_LEVEL_MID:
        return "mid"
    return "low"


def _bar(label: str, value: int, invert: bool = False, tip: str = "") -> dict:
    return {"label": label, "value": int(value), "level": stat_level(value, invert), "tip": tip}


def _peers(state: GameState, a: Athlete) -> List[Athlete]:
    """Gli atleti della Prima Squadra della stessa disciplina (l'atleta compreso, anche se del vivaio)."""
    peers = [p for p in state.main_squad if p.specialty == a.specialty]
    if all(p.id != a.id for p in peers):
        peers.append(a)
    return peers


def _radar(a: Athlete, peers: List[Athlete]) -> dict:
    others = [p for p in peers if p.id != a.id]
    axes = []
    for label, attr in RADAR_AXES:
        row = {"label": label, "value": int(getattr(a, attr))}
        row["avg"] = round(sum(getattr(p, attr) for p in others) / len(others)) if others else None
        axes.append(row)
    return {"axes": axes, "hasAvg": bool(others), "avgLabel": f"Media {a.specialty.value} in rosa ({len(others)})" if others else ""}


def _potential(a: Athlete) -> dict:
    pct = max(0, min(100, round(100 * a.overall / a.potential))) if a.potential > 0 else 100
    left = max(0, a.potential - a.overall)
    text = "Ha raggiunto il potenziale" if left == 0 else f"Mancano {left} punti al potenziale"
    return {"overall": a.overall, "potential": a.potential, "pct": pct, "text": text,
            "stars": max(1, min(5, round(a.potential / 20)))}


def _performance(a: Athlete) -> dict:
    points = []
    for r in results_series(a):
        pct = result_percentile(r)
        tip = f"{r.get('event', '')}: " + ("ritirato" if r.get("out") else f"{r.get('place')}° su {r.get('of')} — {r.get('mark', '')}") + (" · primato personale" if r.get("pb") else "")
        points.append({"label": f"S{r.get('season', '?')}·{r.get('week', '?')}", "event": r.get("event", ""), "percentile": pct,
                       "place": int(r.get("place", 0)), "of": int(r.get("of", 0)), "pb": bool(r.get("pb")), "out": bool(r.get("out")), "tip": tip})
    wins = sum(1 for p in points if p["place"] == 1 and not p["out"])
    podiums = sum(1 for p in points if 1 <= p["place"] <= 3 and not p["out"])
    summary = f"{len(points)} gare · {wins} vittorie · {podiums} podi" if points else ""
    return {"points": points, "max": HISTORY_RESULTS, "summary": summary,
            "emptyText": "Nessuna gara individuale ancora: lo storico si riempie giocando."}


def _records(a: Athlete) -> dict:
    """Primati personali per gara e loro progressione (Q43). Per ogni gara: primato, miglioramento totale e i punti del grafico, con
    `y` in 0-1 e **il miglioramento sempre verso l'alto** (tempi più bassi e misure più alte salgono allo stesso modo)."""
    items = []
    for event in events_with_best(a):
        steps = progression(a, event)
        unit = EVENTS[event].unit
        first, last = steps[0], steps[-1]
        span = last["value"] - first["value"]
        points = []
        for i, step in enumerate(steps):
            y = 0.5 if len(steps) == 1 or span == 0 else (step["value"] - first["value"]) / span
            when = f"S{step['season']}·{step['week']}"
            tip = f"{event}: {step['display']} — {when}" + (f", {step['meet']}" if step["meet"] else "") + (" (primo risultato)" if i == 0 else "")
            points.append({"label": when, "y": max(0.0, min(1.0, y)), "display": step["display"], "tip": tip})
        gain = ""
        if len(steps) > 1:
            sign = "−" if EVENTS[event].lower_is_better else "+"
            gain = f"{sign}{abs(span):.2f}{unit} in {len(steps) - 1} miglioramenti"
        items.append({"event": event, "best": last["display"], "since": f"S{last['season']}·{last['week']}", "gain": gain, "points": points})
    return {"items": items, "emptyText": "Nessun primato ancora: il primo risultato valido di ogni gara lo fissa."}


def _comparison(a: Athlete, peers: List[Athlete]) -> dict:
    ranked = sorted(peers, key=lambda p: (-p.overall, p.name))
    rank = next(i for i, p in enumerate(ranked, start=1) if p.id == a.id)
    shown = ranked[:COMPARISON_ROWS]
    if all(p.id != a.id for p in shown):
        shown = shown[:-1] + [a]
    rows = [{"name": p.name, "ovr": p.overall, "me": p.id == a.id, "rank": ranked.index(p) + 1} for p in shown]
    top = max((p.overall for p in ranked), default=1) or 1
    return {"title": f"Confronto: {a.specialty.value} in rosa", "rank": rank, "of": len(ranked), "top": top,
            "text": f"{rank}° su {len(ranked)} per valutazione", "rows": rows}


def athlete_snapshot(state: GameState, a: Athlete) -> dict:
    """Tutto ciò che la parte grafica della scheda atleta mostra, già pronto."""
    peers = _peers(state, a)
    return {
        "name": a.name,
        "radar": _radar(a, peers),
        "potential": _potential(a),
        "physical": [_bar("Velocità", a.speed), _bar("Resistenza", a.stamina), _bar("Forza", a.strength),
                     _bar("Potenza", a.power), _bar("Resilienza", a.resilience)],
        "technical": [_bar("Tecnica", a.technique), _bar("Struttura fisica", body_fit_score(a)),
                      _bar("Valutazione (OVR)", a.overall), _bar("Potenziale", a.potential)],
        "condition": [_bar("Forma", a.form), _bar("Fatica", a.fatigue, invert=True), _bar("Sonno", a.sleep_quality),
                      _bar("Alimentazione", a.nutrition)],
        "performance": _performance(a),
        "records": _records(a),
        "comparison": _comparison(a, peers),
    }


def empty_athlete_snapshot() -> dict:
    """Scheletro con tutte le chiavi (valori vuoti), per mostrare la vista QML prima dei dati senza leggere chiavi mancanti."""
    return {
        "name": "",
        "radar": {"axes": [{"label": l, "value": 0, "avg": None} for l, _ in RADAR_AXES], "hasAvg": False, "avgLabel": ""},
        "potential": {"overall": 0, "potential": 0, "pct": 0, "text": "", "stars": 1},
        "physical": [], "technical": [], "condition": [],
        "performance": {"points": [], "max": HISTORY_RESULTS, "summary": "", "emptyText": ""},
        "records": {"items": [], "emptyText": ""},
        "comparison": {"title": "", "rank": 1, "of": 1, "top": 1, "text": "", "rows": []},
    }
