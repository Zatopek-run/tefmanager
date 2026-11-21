"""Ospite delle viste QML (PIANOLAVORO G, scelta C): `QQuickWidget` + token del design system + raccolta degli errori QML.

Regole (dal parere di revisione del 2026-11-21):
- **Gli errori QML non sono silenziosi.** Ogni avviso del motore (binding rotti, `undefined`, file mancanti) finisce in `warnings`;
  i test asseriscono che la lista sia vuota dopo il caricamento e dopo ogni `refresh`.
- **Ripiego.** Se il file non si carica, o il grafo di scena non parte (`sceneGraphError`: nessuna GPU/RHI), `failed` diventa
  vero e il chiamante usa la vista QWidget. `TEF_NO_QML=1` lo forza (come `TEF_NO_GODOT` per Godot).
- **Solo ciò che il backend software sa disegnare**: rettangoli, gradienti, `Canvas`, testo. Niente `MultiEffect`, `ShaderEffect`, `DropShadow`.
- **Animazioni spente sulla piattaforma offscreen** (test e screenshot): `Theme.animScale` = 0, altrimenti `grab()` prende fotogrammi a metà.
- Stile dei controlli «Basic» (lo stile nativo di Windows rifiuta gli sfondi personalizzati e riempie il log di avvisi).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import QUrl, pyqtSignal
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtQml import QQmlError
from PyQt6.QtQuickControls2 import QQuickStyle
from PyQt6.QtQuickWidgets import QQuickWidget

from views import theme

QML_DIR_NAME = "qml"
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")  # prima di qualsiasi QML; vale per tutta l'app
_style_set = False


def _ensure_basic_style() -> None:
    """`QQuickStyle.setStyle` va chiamato una sola volta e prima del primo QML: la seconda finestra non deve ripeterlo."""
    global _style_set
    if not _style_set:
        QQuickStyle.setStyle("Basic")
        _style_set = True


def qml_dir() -> Path:
    """Cartella dei file QML (nel pacchetto PyInstaller: `--add-data "views/qml:views/qml"`)."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / "views" / QML_DIR_NAME


def qml_disabled() -> bool:
    return os.environ.get("TEF_NO_QML", "") not in ("", "0")


def theme_tokens(animations: Optional[bool] = None) -> Dict[str, Any]:
    """I token di `views/theme.py` per QML (una sola fonte: cambiare un colore lì lo cambia anche qui)."""
    if animations is None:
        animations = QGuiApplication.platformName() != "offscreen"
    family = theme.load_fonts()
    return {
        "bg": theme.BG, "bgRaised": theme.BG_RAISED, "surface": theme.SURFACE, "surface2": theme.SURFACE_2,
        "border": theme.BORDER, "borderStrong": theme.BORDER_STRONG, "text": theme.TEXT, "textMuted": theme.TEXT_MUTED,
        "textFaint": theme.TEXT_FAINT, "accent": theme.ACCENT, "accentDim": theme.ACCENT_DIM, "good": theme.GOOD,
        "warn": theme.WARN, "bad": theme.BAD, "info": theme.INFO, "orange": theme.ORANGE,
        "fsXs": theme.FS_XS, "fsSm": theme.FS_SM, "fsMd": theme.FS_MD, "fsLg": theme.FS_LG, "fsXl": theme.FS_XL, "fsXxl": theme.FS_XXL,
        "sp1": theme.SP_1, "sp2": theme.SP_2, "sp3": theme.SP_3, "sp4": theme.SP_4, "sp5": theme.SP_5, "sp6": theme.SP_6,
        "radiusSm": theme.RADIUS_SM, "radiusMd": theme.RADIUS_MD, "radiusLg": theme.RADIUS_LG,
        "heatCold": "#262c63", "heatMid": "#0f8f85", "heatHot": "#fbbf24",
        "fontFamily": family, "animScale": 1.0 if animations else 0.0,
    }


class QmlHost(QQuickWidget):
    """Una vista QML dentro un widget. `warnings` raccoglie ogni avviso; `failed` dice se serve il ripiego."""

    failed_signal = pyqtSignal(str)  # emesso se la vista smette di funzionare dopo la creazione (es. grafo di scena non avviato)

    def __init__(self, qml_file: str, context: Dict[str, Any], parent=None, animations: Optional[bool] = None) -> None:
        _ensure_basic_style()
        super().__init__(parent)
        self.warnings: List[str] = []
        self.failed: bool = False
        self.failure: str = ""
        self.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)
        self.setClearColor(theme.qcolor(theme.BG))
        self.engine().warnings.connect(self._on_warnings)
        self.sceneGraphError.connect(self._on_scene_graph_error)
        self.engine().addImportPath(str(qml_dir()))
        ctx = self.rootContext()
        ctx.setContextProperty("Theme", theme_tokens(animations))
        for name, obj in context.items():
            ctx.setContextProperty(name, obj)
        self.setSource(QUrl.fromLocalFile(str(qml_dir() / qml_file)))
        if self.status() != QQuickWidget.Status.Ready:
            self._fail("QML non caricato: " + "; ".join(e.toString() for e in self.errors()))

    def _on_warnings(self, errors: List[QQmlError]) -> None:
        self.warnings.extend(e.toString() for e in errors)

    def _on_scene_graph_error(self, _error, message: str) -> None:
        self._fail(f"grafo di scena non avviato: {message}")

    def _fail(self, why: str) -> None:
        self.failed, self.failure = True, why
        self.warnings.append(why)
        self.failed_signal.emit(why)
