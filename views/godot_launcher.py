"""Avvia il visualizzatore Godot dei 100m (godot_viewer/) come processo esterno.

Il gioco esporta la gara in un DB SQLite (`models.race_export`), lancia Godot e attende che si chiuda
(a fine gara si chiude da solo con `--autoquit`). Se Godot, il progetto o il plugin godot-sqlite non ci sono,
`launch_race_viewer` ritorna None e il chiamante usa la vista interna.

Variabili d'ambiente: TEF_GODOT = percorso di godot.exe; TEF_NO_GODOT = disattiva il visualizzatore.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Callable, Optional

from PyQt6.QtCore import QObject, QProcess, QProcessEnvironment
from PyQt6.QtGui import QWindow
from PyQt6.QtWidgets import QWidget

from models.database import get_default_save_path
from models.entities import CompetitionSummary, EventResult
from models.race_export import export_race

GODOT_PROJECT = Path(__file__).resolve().parent.parent / "godot_viewer"
SQLITE_PLUGIN = GODOT_PROJECT / "addons" / "godot-sqlite" / "gdsqlite.gdextension"
GODOT_EVENTS = ("100m", "400m", "800m", "1500m", "4x100m", "4x400m", "Salto in Lungo", "Getto del Peso")  # elenco esatto


def find_godot() -> Optional[Path]:
    """Cerca l'eseguibile di Godot 4 (TEF_GODOT, root progetto, scoop, PATH). None se non c'è o è disattivato."""
    if os.environ.get("TEF_NO_GODOT"):
        return None
    candidates = []
    if os.environ.get("TEF_GODOT"):
        candidates.append(Path(os.environ["TEF_GODOT"]))
    project_root = GODOT_PROJECT.parent
    candidates.extend(
        sorted(p for p in project_root.glob("Godot*.exe") if "console" not in p.name.lower())
    )
    candidates.append(project_root / "godot.exe")
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


def _cleanup_stale_race_dbs(directory: Path) -> None:
    """Rimuove vecchi file race_results*.db non più bloccati da Godot (best-effort)."""
    for old in directory.glob("race_results*.db"):
        try:
            old.unlink(missing_ok=True)
        except OSError:
            pass


def _next_race_db_path() -> Path:
    """Percorso DB univoco per ogni avvio: evita WinError 32 se un Godot precedente sta ancora chiudendo."""
    base_dir = get_default_save_path().parent
    base_dir.mkdir(parents=True, exist_ok=True)
    _cleanup_stale_race_dbs(base_dir)
    return base_dir / f"race_results_{os.getpid()}_{uuid.uuid4().hex[:8]}.db"


def _missing_class_names(project_dir: Path) -> set[str]:
    """Ritorna i `class_name` dichiarati nei .gd del progetto ma assenti dalla cache Godot."""
    declared: set[str] = set()
    for folder in ("models", "scripts", "autoload"):
        root = project_dir / folder
        if not root.is_dir():
            continue
        for gd in root.rglob("*.gd"):
            try:
                text = gd.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            m = re.search(r"^\s*class_name\s+([A-Za-z_][A-Za-z0-9_]*)", text, re.MULTILINE)
            if m:
                declared.add(m.group(1))
    if not declared:
        return set()
    cache = project_dir / ".godot" / "global_script_class_cache.cfg"
    if not cache.is_file():
        return declared
    try:
        cached_text = cache.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return declared
    cached = set(re.findall(r'"class":\s*&"([A-Za-z_][A-Za-z0-9_]*)"', cached_text))
    return declared - cached


def _ensure_class_cache_fresh(godot: Path, project_dir: Path = GODOT_PROJECT) -> None:
    """Se mancano `class_name` in `.godot/global_script_class_cache.cfg`, riesegue `--import`."""
    if not _missing_class_names(project_dir):
        return
    try:
        subprocess.run(
            [str(godot), "--headless", "--path", str(project_dir), "--import"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        pass


def launch_race_viewer(
    summary: CompetitionSummary,
    result: EventResult,
    on_finished: Callable[[int], None],
    parent: Optional[QObject] = None,
    embed: bool = False,
    size: Optional[tuple[int, int]] = None,
) -> Optional[QProcess]:
    """Esporta la gara e avvia Godot. `on_finished(codice_uscita)` viene chiamata alla chiusura. None se non riesce."""
    godot = viewer_available(result.event_name)
    if godot is None:
        return None
    _ensure_class_cache_fresh(godot)
    db_path = _next_race_db_path()
    try:
        race_id = export_race(summary, result, db_path)
    except Exception:  # export fallito (dati incoerenti, disco, …): si ripiega sulla vista interna
        return None

    env = QProcessEnvironment.systemEnvironment()
    env.insert("TEF_RACE_DB", str(db_path))
    proc = QProcess(parent)
    proc.setProcessEnvironment(env)
    proc.setWorkingDirectory(str(GODOT_PROJECT))
    proc.finished.connect(lambda code, _status: on_finished(code))
    args = ["--path", str(GODOT_PROJECT)]
    if embed and sys.platform == "win32":
        w, h = size if size else (960, 540)
        args.extend(["-w", "--resolution", f"{max(640, w)}x{max(360, h)}", "--position", "-32000,-32000"])
    args.extend(["--", f"--race={race_id}", "--autoquit"])
    proc.start(str(godot), args)
    if not proc.waitForStarted(5000):
        return None
    return proc


def find_process_hwnd(pid: int) -> int:
    """Su Windows ritorna l'HWND visibile principale associato a `pid`, oppure 0."""
    if sys.platform != "win32" or pid <= 0:
        return 0
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    found: list[int] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def _enum_cb(hwnd: int, _lp: int) -> bool:
        if user32.IsWindowVisible(hwnd):
            proc_id = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(proc_id))
            if proc_id.value == pid:
                found.append(int(hwnd))
                return False
        return True

    user32.EnumWindows(_enum_cb, 0)
    return found[0] if found else 0


def embed_hwnd(hwnd: int, host: QWidget) -> Optional[QWidget]:
    """Incapsula una finestra esterna (`hwnd`) senza bordi dentro `host` su Windows."""
    if sys.platform != "win32" or not hwnd:
        return None
    import ctypes

    user32 = ctypes.windll.user32
    gwl_style = -16
    ws_child = 0x40000000
    strip_flags = 0x00C00000 | 0x00040000 | 0x00020000 | 0x00010000 | 0x00080000  # caption, frame, min/max, sysmenu
    swp_flags = 0x0002 | 0x0001 | 0x0004 | 0x0020  # NOMOVE | NOSIZE | NOZORDER | FRAMECHANGED
    style = user32.GetWindowLongW(hwnd, gwl_style)
    # WS_CHILD: senza, la finestra resta "owned" ma di un altro processo e non partecipa
    # al routing tastiera del genitore (i tasti di gioco non arrivavano mai a Godot).
    user32.SetWindowLongW(hwnd, gwl_style, (style & ~strip_flags) | ws_child)
    user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, swp_flags)
    qwin = QWindow.fromWinId(hwnd)
    container = QWidget.createWindowContainer(qwin, host)
    focus_embedded_hwnd(hwnd)
    return container


def focus_embedded_hwnd(hwnd: int) -> None:
    """Passa il focus tastiera a `hwnd`, che vive nel processo Godot separato.

    `SetFocus` da solo non basta tra processi diversi: ognuno ha la propria coda
    messaggi, serve `AttachThreadInput` per far seguire il focus al thread di Godot.
    """
    if sys.platform != "win32" or not hwnd:
        return
    import ctypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    cur_thread = kernel32.GetCurrentThreadId()
    target_thread = user32.GetWindowThreadProcessId(hwnd, None)
    attached = False
    if target_thread and target_thread != cur_thread:
        attached = bool(user32.AttachThreadInput(cur_thread, target_thread, True))
    user32.SetFocus(hwnd)
    if attached:
        user32.AttachThreadInput(cur_thread, target_thread, False)
