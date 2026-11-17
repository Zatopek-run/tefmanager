"""Esporta i risultati di una gara (100m o 400m) in un DB SQLite letto dal visualizzatore Godot (godot_viewer/).

Il modello decide tutto: qui si *copiano* tempi e ordine già calcolati. Le uniche cose ricavate sono la
corsia (sorteggio deterministico) e il tempo di reazione (stessa funzione della vista 2D/3D PyQt).
`final_time` = `mark_value` ed include già la reazione, come in `views/race_viewer.py`.
"""

from __future__ import annotations

import random
import sqlite3
import statistics
import zlib
from contextlib import closing
from pathlib import Path
from typing import List, Optional

from models.entities import CompetitionSummary, EventResult, EventStanding
from models.generator import infer_gender
from views.race_viewer import _rng, generate_attempts, reaction_time

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "godot_viewer" / "data" / "schema.sql"
MAX_LANES = 8
DISTANCES_M = {
    "100m": 100,
    "400m": 400,
    "1500m": 1500,
    "4x100m": 400,
    "4x400m": 1600,
    "Salto in Lungo": 0,
}  # gare supportate dal visualizzatore Godot


def race_seed(summary: CompetitionSummary) -> str:
    """Stesso seed della vista PyQt (`RaceDialog._seed`): la gara si rivede uguale."""
    return f"{summary.week}-{summary.meet_name}"


def draw_lanes(seed: object, athlete_names: List[str]) -> dict:
    """Sorteggio deterministico delle corsie 1..N (non dipende dall'ordine di arrivo)."""
    lanes = list(range(1, len(athlete_names) + 1))
    random.Random(zlib.crc32(f"{seed}|lanes".encode())).shuffle(lanes)
    return dict(zip(sorted(athlete_names), lanes))


def _stop_status(result: EventResult, standing: EventStanding) -> Optional[str]:
    if standing.is_player and result.withdrew_injured:
        return "DNF"
    if standing.is_player and result.disqualified:
        return "DQ"
    return None


def _runnable(result: EventResult, standing: EventStanding, seed: str) -> bool:
    """Chi finisce la gara deve avere un risultato coerente."""
    if _stop_status(result, standing) is not None:
        return True
    if result.event_name == "Salto in Lungo":
        return standing.mark_value > 0.2
    return standing.mark_value > reaction_time(seed, standing.athlete_name)


def export_race(summary: CompetitionSummary, result: EventResult, db_path: Path) -> int:
    """Scrive la gara in `db_path` (creandolo se serve) e ritorna il `race_id`.

    Il ritirato per infortunio ('DNF') e la staffetta squalificata ('DQ') entrano con un tempo di riferimento
    per la velocità di corsa fino al punto d'arresto. Se ci sono più corridori delle corsie, o tempi
    incoerenti, solleva ValueError (il chiamante ripiega sulla vista interna): niente scarti silenziosi.
    """
    if result.event_name not in DISTANCES_M:
        raise ValueError(f"Evento non supportato dal visualizzatore: {result.event_name}.")
    seed = race_seed(summary)
    standings = sorted(result.standings, key=lambda s: s.placement)
    if len(standings) > MAX_LANES:
        raise ValueError(f"{len(standings)} corridori: più delle {MAX_LANES} corsie.")
    if not all(_runnable(result, s, seed) for s in standings):
        raise ValueError("Tempo ufficiale incoerente con il tempo di reazione.")
    finishers = [s.mark_value for s in standings if _stop_status(result, s) is None]
    if not finishers:
        raise ValueError(f"Nessun classificato per {result.event_name}.")
    reference_time = statistics.median(finishers)
    lanes = draw_lanes(seed, [s.athlete_name for s in standings])

    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(str(db_path))) as conn:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        race_id = conn.execute("SELECT COALESCE(MAX(race_id), 0) + 1 FROM races").fetchone()[0]
        conn.execute(
            "INSERT INTO races (race_id, event_name, meet_name, distance_m, wind_ms) VALUES (?, ?, ?, ?, ?)",
            (race_id, result.event_name, summary.meet_name, DISTANCES_M[result.event_name], result.wind_ms or 0.0),
        )
        conn.executemany(
            "INSERT INTO race_results (race_id, lane, athlete_name, team_name, gender, is_player, reaction_time, final_time, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    race_id,
                    lanes[s.athlete_name],
                    s.athlete_name,
                    s.team_name,
                    result.gender if result.gender in ("M", "F") else infer_gender(s.athlete_name),
                    int(s.is_player),
                    round(reaction_time(seed, s.athlete_name), 3),
                    reference_time if _stop_status(result, s) is not None else s.mark_value,
                    _stop_status(result, s) or "OK",
                )
                for s in standings
            ],
        )
        if result.event_name == "Salto in Lungo":
            attempt_rows = []
            for s in standings:
                lane = lanes[s.athlete_name]
                if _stop_status(result, s) is not None:
                    continue
                for rnd, val in enumerate(
                    generate_attempts(s.mark_value, _rng("lj", seed, s.athlete_name)),
                    start=1,
                ):
                    is_foul = 1 if val is None else 0
                    mark = round(s.mark_value * 0.96, 2) if val is None else float(val)
                    attempt_rows.append((race_id, lane, rnd, mark, is_foul))
            conn.executemany(
                "INSERT INTO field_attempts (race_id, lane, round_num, mark_m, is_foul) VALUES (?, ?, ?, ?, ?)",
                attempt_rows,
            )
        conn.commit()
    return race_id


def find_100m(summary: CompetitionSummary) -> Optional[EventResult]:
    return next((r for r in summary.event_results if r.event_name == "100m"), None)


def main() -> None:
    """`python -m models.race_export [salvataggio.db] [uscita.db]`: esporta i 100m dell'ultimo meeting."""
    import sys

    from models.database import DatabaseManager

    save_path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("race_results.db")
    state = DatabaseManager(save_path).load_game()
    if state is None or not state.competition_history:
        raise SystemExit("Nessun meeting nel salvataggio.")
    for summary in reversed(state.competition_history):
        result = find_100m(summary)
        if result is not None:
            race_id = export_race(summary, result, out_path)
            print(f"Esportata la gara {race_id} ({summary.meet_name}) in {out_path}")
            return
    raise SystemExit("Nessuna gara dei 100m nello storico.")


if __name__ == "__main__":
    main()
