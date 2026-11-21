"""Primati personali per gara e loro progressione nel tempo (Q43, 2026-11-21): funzioni pure, senza Qt e **senza RNG**.

Ogni atleta ha un primato **per gara** (`Athlete.pb_log`, colonna `athletes.pb_json`, schema v27): `{evento: [voce, ...]}` con
`voce = {"season", "week", "value", "display", "meet"}`, dal più vecchio al più recente. Si aggiunge una voce **solo** quando una
gara individuale con vento valido e senza ritiro migliora il primato di quella gara (la prima gara di un evento è sempre un primato):
l'ultima voce è quindi il primato attuale e l'elenco è la sua progressione. Si tengono le ultime `PB_LOG_MAX` voci per gara.
Prima c'era un solo PB per atleta, confrontato con ogni gara (difetto trovato: AUDIT R44).
"""
from __future__ import annotations

import json
from typing import Dict, List, Optional, Sequence

from models.entities import EVENTS, PB_LOG_MAX, Athlete

_NO_PB = "—"


def _lower_is_better(event: str) -> bool:
    return EVENTS[event].lower_is_better


def progression(athlete: Athlete, event: str) -> List[dict]:
    """Miglioramenti del primato in `event`, dal più vecchio al più recente (vuota = nessun primato)."""
    return list(athlete.pb_log.get(event, []))


def best_entry(athlete: Athlete, event: str) -> Optional[dict]:
    steps = athlete.pb_log.get(event)
    return steps[-1] if steps else None


def best_value(athlete: Athlete, event: str) -> Optional[float]:
    entry = best_entry(athlete, event)
    return float(entry["value"]) if entry else None


def best_display(athlete: Athlete, event: str) -> Optional[str]:
    entry = best_entry(athlete, event)
    return str(entry["display"]) if entry else None


def is_improvement(event: str, value: float, athlete: Athlete) -> bool:
    """`value` migliora il primato di `event` (o è il primo): tempi più bassi, misure più alte; il pari non è un miglioramento."""
    current = best_value(athlete, event)
    if current is None:
        return True
    return value < current if _lower_is_better(event) else value > current


def record_best(athlete: Athlete, event: str, value: float, display: str, season: int, week: int, meet: str) -> None:
    """Registra un nuovo primato di `event` (il chiamante ha già controllato `is_improvement`), tenendo le ultime `PB_LOG_MAX` voci."""
    steps = athlete.pb_log.setdefault(event, [])
    steps.append({"season": int(season), "week": int(week), "value": float(value), "display": str(display), "meet": str(meet)})
    del steps[:-PB_LOG_MAX]


def events_with_best(athlete: Athlete) -> List[str]:
    """Le gare in cui l'atleta ha un primato, nell'ordine di `EVENTS` (quindi stabile)."""
    return [e for e in EVENTS if athlete.pb_log.get(e)]


def _recency(athlete: Athlete, event: str) -> tuple:
    entry = best_entry(athlete, event)
    return (entry["season"], entry["week"]) if entry else (0, 0)


def headline_events(athlete: Athlete, entered: Sequence[str]) -> List[str]:
    """Le gare da mostrare in una cella sola (elenco della rosa): quelle in cui l'atleta è **iscritto** e ha un primato, nell'ordine
    dato; se non ce n'è nessuna, le (al più due) gare con il primato più recente."""
    shown = [e for e in entered if e in EVENTS and athlete.pb_log.get(e)]
    if shown:
        return shown
    recent = sorted(events_with_best(athlete), key=lambda e: _recency(athlete, e), reverse=True)
    return recent[:2]


def summary_text(athlete: Athlete, entered: Sequence[str]) -> str:
    """Testo del primato per la cella della rosa: «11.20s» con una gara, «100m 11.20s · Salto in Lungo 6.40m» con due; «—» se nessuno."""
    events = headline_events(athlete, entered)
    if not events:
        return _NO_PB
    if len(events) == 1:
        return str(best_display(athlete, events[0]))
    return " · ".join(f"{e} {best_display(athlete, e)}" for e in events)


def sort_value(athlete: Athlete, entered: Sequence[str]) -> float:
    """Valore per ordinare la colonna: il primato della prima gara mostrata (0 senza primati)."""
    events = headline_events(athlete, entered)
    return best_value(athlete, events[0]) or 0.0 if events else 0.0


def pb_log_to_json(log: Dict[str, list]) -> str:
    return json.dumps(log, separators=(",", ":"))


def pb_log_from_json(raw: Optional[str]) -> Dict[str, list]:
    """Primati da una colonna JSON: gare sconosciute e voci non valide scartate, liste tagliate a `PB_LOG_MAX`, JSON rotto = nessun primato."""
    try:
        data = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    out: Dict[str, list] = {}
    for event, steps in data.items():
        if event not in EVENTS or not isinstance(steps, list):
            continue
        clean = []
        for step in steps:
            try:
                clean.append(
                    {
                        "season": int(step["season"]),
                        "week": int(step["week"]),
                        "value": float(step["value"]),
                        "display": str(step["display"]),
                        "meet": str(step.get("meet", "")),
                    }
                )
            except (TypeError, ValueError, KeyError, AttributeError):
                continue
        if clean:
            out[event] = clean[-PB_LOG_MAX:]
    return out
