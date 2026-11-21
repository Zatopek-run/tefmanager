"""Adatta le colonne delle tabelle al contenuto (PIANOLAVORO G): niente più «Tom…», «icenzi» né intestazioni tagliate.

Un filtro di eventi dell'applicazione sistema ogni `QTableWidget` quando diventa visibile: le colonne di solo testo si adattano al
contenuto, quelle con widget dentro le celle (combo, pulsanti) prendono la larghezza del widget più largo, l'ultima colonna si allarga.
Una tabella si esclude con `table.setProperty("fit", False)`. Se non c'è spazio compare la barra di scorrimento orizzontale.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QEvent, QObject
from PyQt6.QtWidgets import QApplication, QHeaderView, QTableWidget

MIN_SECTION = 44
CELL_WIDGET_PAD = 12
HEADER_PAD = 22  # l'intestazione deve poter mostrare il suo testo (e la freccia di ordinamento)


def fit_table(table: QTableWidget) -> None:
    header = table.horizontalHeader()
    cols = table.columnCount()
    if cols == 0:
        return
    header.setMinimumSectionSize(MIN_SECTION)
    header.setStretchLastSection(True)
    rows = min(table.rowCount(), 12)
    fm = header.fontMetrics()
    for c in range(cols):
        widgets = [table.cellWidget(r, c) for r in range(rows)]
        widgets = [w for w in widgets if w is not None]
        if widgets:
            label = table.horizontalHeaderItem(c)
            head_w = fm.horizontalAdvance(label.text()) + HEADER_PAD if label is not None else 0
            width = max(max(w.sizeHint().width() for w in widgets) + CELL_WIDGET_PAD, head_w)
            header.setSectionResizeMode(c, QHeaderView.ResizeMode.Interactive)
            table.setColumnWidth(c, width)
        else:
            header.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)


class TableFitter(QObject):
    """Filtro di eventi: alla comparsa di una tabella ne adatta le colonne."""

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 - firma Qt
        if event.type() == QEvent.Type.Show and isinstance(obj, QTableWidget) and obj.property("fit") is not False:
            fit_table(obj)
        return False


_fitter: Optional[TableFitter] = None


def install_table_fitter() -> None:
    """Installa il filtro una sola volta per applicazione."""
    global _fitter
    app = QApplication.instance()
    if app is not None and _fitter is None:
        _fitter = TableFitter(app)
        app.installEventFilter(_fitter)
