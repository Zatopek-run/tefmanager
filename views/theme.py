"""Design system del gioco (PIANOLAVORO G): colori, scala tipografica, spaziature, raggi, font. Una sola fonte per tutta l'interfaccia.

I widget disegnati a mano (`views/widgets.py`) e il foglio di stile (`views/styles.py`) leggono da qui: cambiare un colore
qui lo cambia ovunque. Niente PyQt oltre a `QColor`/`QFontDatabase`.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List

from PyQt6.QtGui import QColor, QFont, QFontDatabase

# ---- Colori (tema scuro: blu notte con un solo accento, il turchese del gioco)
BG = "#0a0f1f"  # sfondo finestra
BG_RAISED = "#0e1428"  # barre e pannelli laterali
SURFACE = "#121a33"  # schede (card)
SURFACE_2 = "#18224a"  # elementi sopra le schede (celle, input)
BORDER = "#222d57"  # contorni sottili
BORDER_STRONG = "#2f3d73"
TEXT = "#e9eefc"
TEXT_MUTED = "#93a0c6"
TEXT_FAINT = "#5f6d96"
ACCENT = "#19d3c0"  # turchese
ACCENT_DIM = "#0f8f85"
GOOD = "#34d399"
WARN = "#fbbf24"
BAD = "#f87171"
INFO = "#60a5fa"
ORANGE = "#fb923c"  # terzo livello delle caratteristiche (tra giallo e rosso)

# ---- Scala tipografica (pixel) e pesi
FONT_FAMILY = "Inter"
FONT_FALLBACKS = ["Segoe UI", "Bahnschrift", "Noto Sans", "Arial", "sans-serif"]
FS_XS, FS_SM, FS_MD, FS_LG, FS_XL, FS_XXL = 11, 12, 13, 15, 20, 28

# ---- Spaziatura (scala di 4) e raggi
SP_1, SP_2, SP_3, SP_4, SP_5, SP_6 = 4, 8, 12, 16, 20, 24
RADIUS_SM, RADIUS_MD, RADIUS_LG = 6, 10, 14


def qcolor(hex_color: str, alpha: float = 1.0) -> QColor:
    c = QColor(hex_color)
    c.setAlphaF(max(0.0, min(1.0, alpha)))
    return c


def mix(a: str, b: str, t: float) -> QColor:
    """Colore a metà strada tra `a` (t=0) e `b` (t=1)."""
    ca, cb = QColor(a), QColor(b)
    t = max(0.0, min(1.0, t))
    return QColor(
        round(ca.red() + (cb.red() - ca.red()) * t),
        round(ca.green() + (cb.green() - ca.green()) * t),
        round(ca.blue() + (cb.blue() - ca.blue()) * t),
    )


def level_color(level: str) -> str:
    """Gravità → colore: `ok`, `warn`, `danger` (come la proprietà `severity` dei pulsanti)."""
    return {"ok": GOOD, "warn": WARN, "danger": BAD}.get(level, TEXT_MUTED)


# ---- Font incluso nel progetto (Inter, licenza OFL: `assets/fonts/Inter-LICENSE.txt`)
def _font_dir() -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))  # PyInstaller: cartella temporanea del pacchetto
    return base / "assets" / "fonts"


_loaded_family: str = ""


def load_fonts() -> str:
    """Registra i file di `assets/fonts/` e restituisce la famiglia da usare (quella di ripiego se manca il file)."""
    global _loaded_family
    if _loaded_family:
        return _loaded_family
    families: List[str] = []
    for path in sorted(_font_dir().glob("*.ttf")):
        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id >= 0:
            families += QFontDatabase.applicationFontFamilies(font_id)
    _loaded_family = FONT_FAMILY if FONT_FAMILY in families else ""
    return _loaded_family or FONT_FALLBACKS[0]


def font_stack() -> str:
    """Elenco `font-family` per i fogli di stile: Inter e poi i ripieghi di sistema."""
    return ", ".join(f'"{f}"' if " " in f else f for f in [FONT_FAMILY] + FONT_FALLBACKS)


def make_font(px: int, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    """Font del design system a una dimensione in pixel (per il disegno a mano)."""
    font = QFont(FONT_FAMILY)
    font.setStyleHint(QFont.StyleHint.SansSerif)
    font.setPixelSize(px)
    font.setWeight(weight)
    return font
