"""Classifica finale in stile diretta TV, mostrata quando si chiude il visualizzatore Godot.

Disegna soltanto i `EventStanding` già calcolati dal modello (posizioni, misure, ritirati): non cambia
nulla del risultato. Colori e disposizione ricalcano l'HUD di Godot (`godot_viewer/scripts/HUD.gd`).
Grafica originale, nessun marchio reale.
"""

from __future__ import annotations

import zlib
from typing import List, Optional

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QPainter
from PyQt6.QtWidgets import QWidget

from models.entities import EVENTS, EventResult, EventStanding

BG_NAVY = QColor(14, 19, 51, 238)
BG_ROW = QColor(22, 29, 69, 240)
BG_PLAYER = QColor(26, 61, 107, 235)
BG_PLACE = QColor(36, 48, 97)
CYAN = QColor(13, 222, 204)
MAGENTA = QColor(235, 41, 122)
AMBER = QColor(250, 194, 46)
TEXT_DARK = QColor(12, 17, 46)
TEXT_MUTED = QColor(173, 194, 230)
PLAYER_TEXT = QColor(92, 219, 255)
WHITE = QColor(255, 255, 255)

MAX_WIDTH = 820
HEADER_H = 40
SUBBAR_H = 26
MIN_ROW_H = 22
MAX_ROW_H = 44
GAP = 3


def team_color(team: str) -> QColor:
    """Colore stabile per squadra (come `_team_color` del visualizzatore Godot, ma qui non serve che coincida)."""
    return QColor.fromHsv(zlib.crc32(team.encode("utf-8")) % 360, 190, 230)


class ResultsBoardWidget(QWidget):
    """Tabellone «ORDINE D'ARRIVO» / «CLASSIFICA FINALE» con tutti i partecipanti della gara."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._result: Optional[EventResult] = None
        self._meet = ""
        self.setMinimumHeight(240)

    def set_result(self, result: EventResult, meet_name: str) -> None:
        self._result = result
        self._meet = meet_name
        self.update()

    # ---- contenuto
    def title_text(self) -> str:
        res = self._result
        if res is None:
            return ""
        gender = f"{res.gender} " if res.gender in ("M", "F") else ""
        return f"{gender}{res.event_name.upper()}  •  {self._meet.upper()}"

    def subtitle_text(self) -> str:
        res = self._result
        if res is None:
            return ""
        ev = EVENTS.get(res.event_name)
        return "CLASSIFICA FINALE" if ev is not None and ev.unit == "m" else "ORDINE D'ARRIVO"

    def row_texts(self) -> List[tuple]:
        """[(posizione o '-', nome, squadra, valore, is_player, fuori_classifica)] nell'ordine ufficiale."""
        res = self._result
        if res is None:
            return []
        out = []
        for s in sorted(res.standings, key=lambda st: st.placement):
            out.append(self._row_of(res, s))
        return out

    @staticmethod
    def _row_of(res: EventResult, s: EventStanding) -> tuple:
        if s.is_player and res.withdrew_injured:
            return ("-", s.athlete_name, s.team_name, "RIT.", True, True)
        if s.is_player and res.disqualified:
            return ("-", s.athlete_name, s.team_name, "SQ.", True, True)
        return (str(s.placement), s.athlete_name, s.team_name, s.mark_display, s.is_player, False)

    # ---- disegno
    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt API)
        res = self._result
        if res is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rows = self.row_texts()
        w, h = self.width(), self.height()
        bw = min(MAX_WIDTH, w - 32)
        x0 = (w - bw) / 2.0
        n = max(1, len(rows))
        avail = h - 24 - HEADER_H - SUBBAR_H - 2 * GAP
        row_h = max(MIN_ROW_H, min(MAX_ROW_H, avail / n - GAP))
        shown = min(n, max(1, int(avail // (row_h + GAP))))
        total_h = HEADER_H + SUBBAR_H + 2 * GAP + shown * (row_h + GAP)
        y = max(8.0, (h - total_h) / 2.0)

        # intestazione (barra magenta a sinistra)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(BG_NAVY)
        p.drawRoundedRect(QRectF(x0, y, bw, HEADER_H), 3, 3)
        p.setBrush(MAGENTA)
        p.drawRect(QRectF(x0, y, 6, HEADER_H))
        p.setPen(WHITE)
        p.setFont(self._font(15, heavy=True))
        p.drawText(QRectF(x0 + 18, y, bw - 36, HEADER_H), Qt.AlignmentFlag.AlignVCenter, self.title_text())
        y += HEADER_H + GAP

        # sottotitolo ciano
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(CYAN)
        p.drawRect(QRectF(x0, y, bw, SUBBAR_H))
        p.setPen(TEXT_DARK)
        p.setFont(self._font(11, heavy=True))
        p.drawText(QRectF(x0 + 18, y, bw - 36, SUBBAR_H), Qt.AlignmentFlag.AlignVCenter, self.subtitle_text())
        y += SUBBAR_H + GAP

        name_pt = max(10, min(17, int(row_h * 0.42)))
        for place, name, team, value, is_player, out in rows[:shown]:
            self._draw_row(p, QRectF(x0, y, bw, row_h), place, name, team, value, is_player, out, name_pt)
            y += row_h + GAP

        if len(rows) > shown:
            p.setPen(TEXT_MUTED)
            p.setFont(self._font(10, heavy=False))
            p.drawText(QRectF(x0, y, bw, 18), Qt.AlignmentFlag.AlignRight, f"… altri {len(rows) - shown} classificati")

        # vento (100m, lungo): in basso a destra come nella diretta
        if res.wind_ms is not None:
            note = "  (N.O.)" if res.wind_illegal else ""
            p.setPen(AMBER if res.wind_illegal else WHITE)
            p.setFont(self._font(11, heavy=True))
            p.drawText(QRectF(x0, h - 26, bw, 20), Qt.AlignmentFlag.AlignRight,
                       f"VENTO  {res.wind_ms:+.1f} m/s{note}")
        p.end()

    def _draw_row(self, p: QPainter, r: QRectF, place: str, name: str, team: str, value: str,
                  is_player: bool, out: bool, pt: int) -> None:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(BG_PLAYER if is_player else BG_ROW)
        p.drawRoundedRect(r, 2, 2)

        pad = 8.0
        box = QRectF(r.x() + pad, r.y() + 3, r.height() * 1.25, r.height() - 6)
        first = place == "1"
        p.setBrush(CYAN if first else BG_PLACE)
        p.drawRoundedRect(box, 3, 3)
        p.setPen(TEXT_DARK if first else WHITE)
        p.setFont(self._font(pt, heavy=True))
        p.drawText(box, Qt.AlignmentFlag.AlignCenter, place)

        sx = box.right() + 10
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(team_color(team))
        p.drawRect(QRectF(sx, r.y() + 4, 5, r.height() - 8))

        value_w = 120.0
        team_w = min(200.0, r.width() * 0.26)
        nx = sx + 15
        name_w = r.right() - pad - value_w - team_w - nx - 8
        p.setPen(PLAYER_TEXT if is_player else (TEXT_MUTED if out else WHITE))
        f = self._font(pt, heavy=False)
        p.setFont(f)
        p.drawText(QRectF(nx, r.y(), name_w, r.height()), Qt.AlignmentFlag.AlignVCenter,
                   p.fontMetrics().elidedText(name.upper(), Qt.TextElideMode.ElideRight, int(name_w)))

        tx = nx + name_w + 8
        p.setPen(TEXT_MUTED)
        p.setFont(self._font(max(9, pt - 4), heavy=False))
        p.drawText(QRectF(tx, r.y(), team_w, r.height()), Qt.AlignmentFlag.AlignVCenter,
                   p.fontMetrics().elidedText(team, Qt.TextElideMode.ElideRight, int(team_w)))

        p.setPen(AMBER if out else WHITE)
        p.setFont(self._font(pt + 2, heavy=True))
        p.drawText(QRectF(r.right() - pad - value_w, r.y(), value_w, r.height()),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, value)

    @staticmethod
    def _font(pt: int, heavy: bool) -> QFont:
        f = QFont()
        f.setPointSize(pt)
        f.setWeight(QFont.Weight.ExtraBold if heavy else QFont.Weight.DemiBold)
        return f
