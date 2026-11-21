"""Icone vettoriali del gioco (PIANOLAVORO G): Material Design Icons via `qtawesome` (MIT), colorate dai token di `views/theme.py`.

Se `qtawesome` manca, le icone sono vuote e l'interfaccia resta usabile (solo testo). Le icone sono in cache per (nome, colori).
"""
from __future__ import annotations

import os
from functools import lru_cache

from PyQt6.QtGui import QIcon

from views import theme

os.environ.setdefault("QT_API", "pyqt6")  # qtawesome sceglie il binding da qui (qtpy)

try:  # pragma: no cover - dipende dall'installazione
    import qtawesome as _qta
except Exception:  # noqa: BLE001 - qualunque problema = nessuna icona
    _qta = None

# pagina della barra laterale → icona (nomi MDI)
NAV_ICONS = {
    "Dashboard": "mdi6.view-dashboard-outline",
    "Rosa": "mdi6.run-fast",
    "Vivaio": "mdi6.seed-outline",
    "Calendario": "mdi6.calendar-month-outline",
    "Staffette": "mdi6.relation-many-to-many",
    "Rivali": "mdi6.sword-cross",
    "Ranking": "mdi6.podium-gold",
    "Staff": "mdi6.account-tie-outline",
    "Finanze": "mdi6.cash-multiple",
    "Albo": "mdi6.trophy-outline",
    "Infrastrutture": "mdi6.office-building-outline",
    "Menu": "mdi6.arrow-left",
}
UI_ICONS = {"save": "mdi6.content-save-outline", "play": "mdi6.play", "menu": "mdi6.menu-down", "next": "mdi6.skip-next"}


def available() -> bool:
    return _qta is not None


@lru_cache(maxsize=128)
def icon(name: str, color: str = theme.TEXT_MUTED, color_on: str = theme.ACCENT) -> QIcon:
    """Icona `name` (MDI) in `color`, e in `color_on` quando il pulsante è selezionato (stato On)."""
    if _qta is None:
        return QIcon()
    try:
        return _qta.icon(name, color=color, color_on=color_on, color_active=theme.TEXT, color_selected=color_on)
    except Exception:  # noqa: BLE001 - nome sconosciuto: nessuna icona, mai un'eccezione verso Qt
        return QIcon()


def nav_icon_for(label: str) -> QIcon:
    """Icona per l'etichetta di una voce della barra laterale (anche con i contatori in coda, es. «Rosa & Allenamenti (9 st.)»)."""
    clean = label.replace("&&", "&")
    for key, name in NAV_ICONS.items():
        if clean.startswith(key):
            return icon(name)
    return QIcon()
