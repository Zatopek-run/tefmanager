"""Storico di forma, fatica e risultati per atleta (PIANOLAVORO G.1/G.2), per i grafici. Senza Qt e **senza RNG**.

Sta in `Athlete.history` (colonna `athletes.history_json`, schema v26): `{"weekly": [[forma, fatica, infortunato], ...],
"results": [{"season", "week", "event", "gender", "place", "of", "mark", "pb", "out"}, ...]}`, dal più vecchio al più
recente. **Nessun effetto sul gioco**: si scrive e basta (le partite già in corso partono con i grafici vuoti).
"""
from __future__ import annotations

import json
from typing import Dict, List, Optional, Tuple

from models.entities import HISTORY_RESULTS, HISTORY_WEEKS, Athlete, EventResult, GameState


def record_weekly(state: GameState) -> None:
    """Passo 21d del tick (a fine tick, `TICK.md`): aggiunge (forma, fatica, infortunato) di ogni atleta, tenendo le ultime HISTORY_WEEKS."""
    for a in state.athletes:
        weekly = a.history.setdefault("weekly", [])
        weekly.append([int(a.form), int(a.fatigue), 1 if a.injured_weeks > 0 else 0])
        del weekly[:-HISTORY_WEEKS]


def record_result(state: GameState, athlete: Athlete, result: EventResult) -> None:
    """Aggiunge una gara individuale allo storico dell'atleta (chiamata da `simulate_competition`), tenendo le ultime HISTORY_RESULTS."""
    results = athlete.history.setdefault("results", [])
    results.append(
        {
            "season": state.season_number,
            "week": state.week,
            "event": result.event_name,
            "gender": result.gender,
            "place": int(result.placement),
            "of": int(result.total_competitors),
            "mark": result.player_mark,
            "pb": bool(result.is_pb),
            "out": bool(result.withdrew_injured),
        }
    )
    del results[:-HISTORY_RESULTS]


def weekly_series(athlete: Athlete) -> List[Tuple[int, int, bool]]:
    """(forma, fatica, infortunato) delle ultime settimane, dalla più vecchia alla più recente (vuota = nessuno storico)."""
    return [(int(f), int(t), bool(i)) for f, t, i in athlete.history.get("weekly", [])]


def results_series(athlete: Athlete) -> List[dict]:
    """Ultime gare individuali, dalla più vecchia alla più recente."""
    return list(athlete.history.get("results", []))


def result_percentile(result: dict) -> float:
    """Posizione di una gara in 0..100 (100 = vittoria, 0 = ultimo o ritirato): confrontabile tra discipline diverse."""
    n = int(result.get("of", 0))
    if result.get("out") or n <= 1:
        return 100.0 if (n <= 1 and not result.get("out")) else 0.0
    return 100.0 * (n - int(result.get("place", n))) / (n - 1)


def history_to_json(history: Dict[str, list]) -> str:
    return json.dumps(history, separators=(",", ":"))


def history_from_json(raw: Optional[str]) -> Dict[str, list]:
    """Storico da una colonna JSON: voci non valide scartate, liste tagliate ai limiti, JSON rotto = nessuno storico."""
    try:
        data = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    out: Dict[str, list] = {}
    weekly = []
    for row in data.get("weekly", []) if isinstance(data.get("weekly"), list) else []:
        try:
            weekly.append([int(row[0]), int(row[1]), 1 if row[2] else 0])
        except (TypeError, ValueError, IndexError, KeyError):
            continue
    results = [r for r in data.get("results", []) if isinstance(r, dict) and "place" in r and "of" in r] if isinstance(data.get("results"), list) else []
    if weekly:
        out["weekly"] = weekly[-HISTORY_WEEKS:]
    if results:
        out["results"] = results[-HISTORY_RESULTS:]
    return out
