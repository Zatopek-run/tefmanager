"""Avvia il visualizzatore Godot dei 100m (godot_viewer/) come processo esterno.

Il gioco esporta la gara in un DB SQLite (`models.race_export`), lancia Godot e attende che si chiuda
(a fine gara si chiude da solo con `--autoquit`). Se Godot, il progetto o il plugin godot-sqlite non ci sono,
`launch_race_viewer` ritorna None e il chiamante usa la vista interna.

Variabili d'ambiente: TEF_GODOT = percorso di godot.exe; TEF_NO_GODOT = disattiva il visualizzatore.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Callable, Optional

from PyQt6.QtCore import QObject, QProcess, QProcessEnvironment

from models.database import get_default_save_path
from models.entities import CompetitionSummary, EventResult
from models.race_export import export_race

GODOT_PROJECT = Path(__file__).resolve().parent.parent / "godot_viewer"
SQLITE_PLUGIN = GODOT_PROJECT / "addons" / "godot-sqlite" / "gdsqlite.gdextension"
GODOT_EVENTS = ("100m",)  # gare che il visualizzatore Godot sa mettere in scena


def find_godot() -> Optional[Path]:
    """Cerca l'eseguibile di Godot 4 (TEF_GODOT, scoop, PATH). None se non c'è o è disattivato."""
    if os.environ.get("TEF_NO_GODOT"):
        return None
    candidates = []
    if os.environ.get("TEF_GODOT"):
        candidates.append(Path(os.environ["TEF_GODOT"]))
    candidates.append(Path.home() / "scoop" / "apps" / "godot" / "current" / "godot.exe")
    on_path = shutil.which("godot")
    if on_path:
        candidates.append(Path(on_path))
    return next((c for c in candidates if c.is_file()), None)


def viewer_available(event_name: str) -> Optional[Path]:
    """Ritorna il percorso di Godot se per `event_name` si può usare il visualizzatore, altrimenti None."""
    if event_name not in GODOT_EVENTS:
        return None
    if not (GODOT_PROJECT / "project.godot").is_file() or not SQLITE_PLUGIN.is_file():
        return None
    return find_godot()


def race_db_path() -> Path:
    return get_default_save_path().parent / "race_results.db"


def launch_race_viewer(
    summary: CompetitionSummary,
    result: EventResult,
    on_finished: Callable[[int], None],
    parent: Optional[QObject] = None,
) -> Optional[QProcess]:
    """Esporta la gara e avvia Godot. `on_finished(codice_uscita)` viene chiamata alla chiusura. None se non riesce."""
    godot = viewer_available(result.event_name)
    if godot is None:
        return None
    db_path = race_db_path()
    try:
        db_path.unlink(missing_ok=True)  # un file nuovo per ogni gara: Godot non è in esecuzione
        race_id = export_race(summary, result, db_path)
    except Exception:  # export fallito (dati incoerenti, disco, …): si ripiega sulla vista interna
        return None

    env = QProcessEnvironment.systemEnvironment()
    env.insert("TEF_RACE_DB", str(db_path))
    proc = QProcess(parent)
    proc.setProcessEnvironment(env)
    proc.setWorkingDirectory(str(GODOT_PROJECT))
    proc.finished.connect(lambda code, _status: on_finished(code))
    proc.start(str(godot), ["--path", str(GODOT_PROJECT), "--", f"--race={race_id}", "--autoquit"])
    if not proc.waitForStarted(5000):
        return None
    return proc
