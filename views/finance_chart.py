"""Grafico a barre dei bilanci mensili (D.3), disegnato con QPainter: nessuna dipendenza in più (requirements.txt non cambia).

Per ogni mese una barra verde (entrate) e una rossa (uscite), la stessa scala per tutti; sotto, «S{stagione}·{mese}».
La parte che si calcola (altezze) è una funzione statica, provata senza guardare lo schermo.
"""

from __future__ import annotations

from typing import List, Sequence, Tuple

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QWidget

from models.entities import MonthlyReport

INCOME_COLOR = QColor("#34d399")
EXPENSE_COLOR = QColor("#f87171")
AXIS_COLOR = QColor("#475569")
TEXT_COLOR = QColor("#94a3b8")
MAX_BARS = 12  # ultimi 12 mesi


class MonthlyBarsWidget(QWidget):
    """Entrate e uscite degli ultimi mesi (dal più vecchio al più recente, da sinistra a destra)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._reports: List[MonthlyReport] = []
        self.setMinimumHeight(170)

    def set_reports(self, reports_oldest_first: Sequence[MonthlyReport]) -> None:
        self._reports = list(reports_oldest_first)[-MAX_BARS:]
        self.update()

    @staticmethod
    def bar_heights(reports: Sequence[MonthlyReport], plot_height: float) -> List[Tuple[float, float]]:
        """(altezza entrate, altezza uscite) in pixel per mese: scala comune, il valore massimo riempie `plot_height`."""
        peak = max((max(r.total_income, r.total_expenses) for r in reports), default=0)
        if peak <= 0:
            return [(0.0, 0.0) for _ in reports]
        return [(plot_height * r.total_income / peak, plot_height * r.total_expenses / peak) for r in reports]

    def paintEvent(self, _event) -> None:  # noqa: N802 - firma Qt
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        w, h = self.width(), self.height()
        painter.fillRect(0, 0, w, h, QColor("#0b1228"))
        font = QFont(painter.font())
        font.setPixelSize(11)
        painter.setFont(font)
        painter.setPen(QPen(TEXT_COLOR))
        if not self._reports:
            painter.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, "Nessun mese chiuso: il primo bilancio arriva dopo 4 settimane.")
            painter.end()
            return
        left, right, top, bottom = 56, 12, 16, 24
        plot_h, plot_w = h - top - bottom, w - left - right
        base_y = top + plot_h
        peak = max(max(r.total_income, r.total_expenses) for r in self._reports)
        painter.drawText(QRectF(4, top - 8, left - 8, 16), Qt.AlignmentFlag.AlignRight, f"€{peak:,}")
        painter.drawText(QRectF(4, base_y - 8, left - 8, 16), Qt.AlignmentFlag.AlignRight, "€0")
        painter.setPen(QPen(AXIS_COLOR))
        painter.drawLine(left, int(base_y), left + plot_w, int(base_y))
        slot = plot_w / max(1, len(self._reports))
        bar_w = max(3.0, min(22.0, slot * 0.32))
        for i, (rep, (inc_h, exp_h)) in enumerate(zip(self._reports, self.bar_heights(self._reports, plot_h))):
            cx = left + slot * (i + 0.5)
            painter.fillRect(QRectF(cx - bar_w - 1, base_y - inc_h, bar_w, inc_h), INCOME_COLOR)
            painter.fillRect(QRectF(cx + 1, base_y - exp_h, bar_w, exp_h), EXPENSE_COLOR)
            painter.setPen(QPen(TEXT_COLOR))
            painter.drawText(QRectF(cx - slot / 2, base_y + 4, slot, 16), Qt.AlignmentFlag.AlignCenter, f"S{rep.season}·{rep.month}")
        painter.end()
