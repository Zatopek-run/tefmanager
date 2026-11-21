"""Widget grafici del gioco (PIANOLAVORO G), disegnati con QPainter: nessuna dipendenza in più (requirements.txt non cambia).

Tutti leggono colori e font da `views/theme.py`. La parte che si calcola (posizioni, colori delle celle) sta in funzioni
statiche o di modulo, provate senza guardare lo schermo; il disegno è `paintEvent`.
"""
from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from models.dashboard import HeatMap, SeasonTimeline, heat_level
from views import theme

BADGE_LEVEL_ROLE = Qt.ItemDataRole.UserRole + 7  # livello (`ok`/`warn`/`danger`) di un badge nelle tabelle


# ---------------------------------------------------------------- funzioni pure (provate senza schermo)
def line_points(
    values: Sequence[float], left: float, top: float, width: float, height: float, vmin: float = 0.0, vmax: float = 100.0
) -> List[Tuple[float, float]]:
    """Punti (x, y) di una serie: x equidistanti da `left` a `left + width` (un solo punto sta al centro), y in pixel con vmax in alto."""
    n = len(values)
    span = (vmax - vmin) or 1.0
    out: List[Tuple[float, float]] = []
    for i, v in enumerate(values):
        x = left + (width * i / (n - 1) if n > 1 else width / 2)
        y = top + height * (1.0 - (max(vmin, min(vmax, v)) - vmin) / span)
        out.append((x, y))
    return out


def nearest_index(x: float, left: float, width: float, n: int) -> int:
    """Indice del punto più vicino a `x` per una serie di `n` punti distribuiti come in `line_points`."""
    if n <= 1:
        return 0
    frac = (x - left) / width if width else 0.0
    return max(0, min(n - 1, round(frac * (n - 1))))


def short_event_name(name: str) -> str:
    """Nome breve di una gara per le intestazioni strette: «100m» resta, «Salto in Lungo» → «Lungo», «Getto del Peso» → «Peso»."""
    return name if any(ch.isdigit() for ch in name) else name.split()[-1]


HEAT_COLD, HEAT_MID, HEAT_HOT = "#262c63", "#0f8f85", "#fbbf24"


def heat_color(level: float) -> QColor:
    """0..1 → colore della cella: indaco (freddo) → turchese → oro (caldo)."""
    if level < 0.5:
        return theme.mix(HEAT_COLD, HEAT_MID, level / 0.5)
    return theme.mix(HEAT_MID, HEAT_HOT, (level - 0.5) / 0.5)


def readable_on(background: QColor) -> QColor:
    """Testo scuro su sfondi chiari, chiaro su sfondi scuri."""
    luminance = 0.299 * background.red() + 0.587 * background.green() + 0.114 * background.blue()
    return QColor("#0a0f1f") if luminance > 150 else QColor(theme.TEXT)


# ---------------------------------------------------------------- componenti piccoli
def make_card(title: str = "", hint: str = "") -> Tuple[QFrame, QVBoxLayout, QHBoxLayout]:
    """Scheda del design system: contenitore `Card`, titolo a sinistra e suggerimento a destra. Restituisce (scheda, corpo, intestazione)."""
    card = QFrame()
    card.setObjectName("Card")
    outer = QVBoxLayout(card)
    outer.setContentsMargins(theme.SP_4, theme.SP_3, theme.SP_4, theme.SP_4)
    outer.setSpacing(theme.SP_3)
    head = QHBoxLayout()
    head.setSpacing(theme.SP_2)
    if title:
        t = QLabel(title)
        t.setObjectName("CardHeading")
        head.addWidget(t)
    head.addStretch()
    if hint:
        h = QLabel(hint)
        h.setObjectName("CardHint")
        head.addWidget(h)
    outer.addLayout(head)
    return card, outer, head


class StatusPill(QLabel):
    """Pallino colorato e testo: verde se tutto ok, ambra se c'è da guardare, rosso se c'è un'urgenza (dilemma, gara scoperta…)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("StatusPill")
        self._level = "ok"
        self.set_level("ok", "Tutto ok")

    @property
    def level(self) -> str:
        return self._level

    def set_level(self, level: str, text: str) -> None:
        self._level = level
        self.setProperty("level", level)
        self.setText(f"●  {text}")
        self.style().unpolish(self)
        self.style().polish(self)


def check_icon(done: bool, size: int = 18) -> QIcon:
    """Spunta vera al posto di «[ ]»: cerchio pieno con segno di spunta se fatto, anello vuoto altrimenti."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    r = QRectF(1.5, 1.5, size - 3, size - 3)
    if done:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(theme.GOOD))
        p.drawEllipse(r)
        pen = QPen(QColor(theme.BG), 2.0)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        path = QPainterPath()
        path.moveTo(size * 0.30, size * 0.52)
        path.lineTo(size * 0.45, size * 0.66)
        path.lineTo(size * 0.72, size * 0.36)
        p.drawPath(path)
    else:
        p.setPen(QPen(QColor(theme.TEXT_FAINT), 1.6))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(r)
    p.end()
    return QIcon(pm)


class BadgeDelegate(QStyledItemDelegate):
    """Cella a «pillola» colorata: il testo è quello della cella (mai abbreviato: la colonna si allarga), il colore viene dal livello in `BADGE_LEVEL_ROLE`."""

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        level = index.data(BADGE_LEVEL_ROLE) or "ok"
        color = QColor(theme.level_color(str(level)))
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())
        font = theme.make_font(theme.FS_SM, QFont.Weight.DemiBold)
        painter.setFont(font)
        fm = painter.fontMetrics()
        w = min(option.rect.width() - 8, fm.horizontalAdvance(text) + 20)
        rect = QRectF(
            option.rect.x() + (option.rect.width() - w) / 2, option.rect.y() + (option.rect.height() - 22) / 2, w, 22
        )
        fill = QColor(color)
        fill.setAlphaF(0.16)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(fill)
        painter.drawRoundedRect(rect, 11, 11)
        painter.setPen(color)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, fm.elidedText(text, Qt.TextElideMode.ElideRight, int(w - 12)))
        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:
        fm = option.fontMetrics
        return QSize(fm.horizontalAdvance(index.data(Qt.ItemDataRole.DisplayRole) or "") + 28, 30)


# ---------------------------------------------------------------- grafico forma e fatica
class TrendChart(QWidget):
    """Forma e fatica medie della rosa nelle ultime settimane (G.1): due linee su scala 0-100, area sotto la forma, ultimo valore in evidenza."""

    MARGIN_LEFT, MARGIN_RIGHT, MARGIN_TOP, MARGIN_BOTTOM = 34, 18, 30, 24

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._form: List[float] = []
        self._fatigue: List[float] = []
        self._hover: Optional[int] = None
        self._empty_text = "Lo storico si riempie giocando: avanza la prima settimana."
        self.setMinimumHeight(190)
        self.setMouseTracking(True)

    def set_empty_text(self, text: str) -> None:
        """Messaggio da mostrare finché non c'è nessuno storico (dipende dal perché: partita appena iniziata o società senza atleti)."""
        self._empty_text = text
        self.update()

    def set_series(self, form: Sequence[float], fatigue: Sequence[float]) -> None:
        self._form, self._fatigue = list(form), list(fatigue)
        self._hover = None
        self.update()

    def plot_rect(self) -> QRectF:
        return QRectF(
            self.MARGIN_LEFT,
            self.MARGIN_TOP,
            max(1, self.width() - self.MARGIN_LEFT - self.MARGIN_RIGHT),
            max(1, self.height() - self.MARGIN_TOP - self.MARGIN_BOTTOM),
        )

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - firma Qt
        if not self._form:
            return
        pr = self.plot_rect()
        idx = nearest_index(event.position().x(), pr.left(), pr.width(), len(self._form))
        if idx != self._hover:
            self._hover = idx
            self.update()
        weeks_ago = len(self._form) - 1 - idx
        when = "ultima settimana" if weeks_ago == 0 else f"{weeks_ago} sett. fa"
        QToolTip.showText(
            event.globalPosition().toPoint(),
            f"{when}: forma {self._form[idx]:.0f} · fatica {self._fatigue[idx]:.0f}",
            self,
        )

    def leaveEvent(self, _event) -> None:  # noqa: N802
        self._hover = None
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802 - firma Qt
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pr = self.plot_rect()
        small = theme.make_font(theme.FS_XS)
        p.setFont(small)
        # griglia e scala
        for v in (0, 25, 50, 75, 100):
            y = pr.top() + pr.height() * (1 - v / 100)
            p.setPen(QPen(QColor(theme.BORDER), 1, Qt.PenStyle.DotLine if v not in (0, 100) else Qt.PenStyle.SolidLine))
            p.drawLine(QPointF(pr.left(), y), QPointF(pr.right(), y))
            p.setPen(QColor(theme.TEXT_FAINT))
            p.drawText(QRectF(0, y - 8, self.MARGIN_LEFT - 8, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, str(v))
        if not self._form:
            p.setPen(QColor(theme.TEXT_MUTED))
            p.setFont(theme.make_font(theme.FS_SM))
            p.drawText(pr, Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, self._empty_text)
            p.end()
            return
        n = len(self._form)
        form_pts = [QPointF(x, y) for x, y in line_points(self._form, pr.left(), pr.top(), pr.width(), pr.height())]
        fat_pts = [QPointF(x, y) for x, y in line_points(self._fatigue, pr.left(), pr.top(), pr.width(), pr.height())]
        # area sotto la forma
        if n > 1:
            area = QPainterPath(QPointF(form_pts[0].x(), pr.bottom()))
            for pt in form_pts:
                area.lineTo(pt)
            area.lineTo(QPointF(form_pts[-1].x(), pr.bottom()))
            area.closeSubpath()
            grad = QLinearGradient(0, pr.top(), 0, pr.bottom())
            grad.setColorAt(0, theme.qcolor(theme.ACCENT, 0.28))
            grad.setColorAt(1, theme.qcolor(theme.ACCENT, 0.0))
            p.fillPath(area, QBrush(grad))
        for pts, color in ((fat_pts, theme.WARN), (form_pts, theme.ACCENT)):
            pen = QPen(QColor(color), 2.4)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            if n > 1:
                path = QPainterPath(pts[0])
                for pt in pts[1:]:
                    path.lineTo(pt)
                p.drawPath(path)
        # punto evidenziato: quello sotto il mouse, altrimenti l'ultimo
        idx = self._hover if self._hover is not None else n - 1
        if self._hover is not None:
            p.setPen(QPen(theme.qcolor(theme.TEXT, 0.25), 1))
            p.drawLine(QPointF(form_pts[idx].x(), pr.top()), QPointF(form_pts[idx].x(), pr.bottom()))
        for pts, color in ((fat_pts, theme.WARN), (form_pts, theme.ACCENT)):
            p.setPen(QPen(QColor(theme.SURFACE), 2))
            p.setBrush(QColor(color))
            p.drawEllipse(pts[idx], 4.5, 4.5)
        # legenda con i valori del punto evidenziato
        x = pr.left()
        for label, series, color in (("Forma", self._form, theme.ACCENT), ("Fatica", self._fatigue, theme.WARN)):
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(color))
            p.drawEllipse(QPointF(x + 4, 12), 4, 4)
            p.setPen(QColor(theme.TEXT))
            p.setFont(theme.make_font(theme.FS_SM, QFont.Weight.DemiBold))
            text = f"{label} {series[idx]:.0f}"
            p.drawText(QRectF(x + 14, 3, 120, 18), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text)
            x += 14 + p.fontMetrics().horizontalAdvance(text) + 18
        # etichette dell'asse x
        p.setFont(small)
        p.setPen(QColor(theme.TEXT_FAINT))
        p.drawText(QRectF(pr.left() - 10, pr.bottom() + 6, 120, 16), Qt.AlignmentFlag.AlignLeft, f"{n - 1} sett. fa" if n > 1 else "")
        p.drawText(QRectF(pr.right() - 110, pr.bottom() + 6, 120, 16), Qt.AlignmentFlag.AlignRight, "ultima")
        p.end()


# ---------------------------------------------------------------- heat map atleti × gare
class HeatMapWidget(QWidget):
    """Dove gli atleti sono forti e deboli (G.1): una cella per atleta e gara, colorata dal punteggio atteso. La gara migliore di ogni atleta ha un anello."""

    ROW_H, HEAD_H, LEGEND_H, NAME_W, GAP = 32, 28, 26, 168, 4

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._hm: Optional[HeatMap] = None
        self.setMouseTracking(True)
        self.setMinimumHeight(self.HEAD_H + self.ROW_H * 3 + self.LEGEND_H)

    def set_heat_map(self, hm: Optional[HeatMap]) -> None:
        self._hm = hm
        rows = len(hm.athletes) if hm else 3
        self.setMinimumHeight(self.HEAD_H + self.ROW_H * rows + self.LEGEND_H)
        self.update()

    def cell_rect(self, row: int, col: int) -> QRectF:
        assert self._hm is not None
        cols = len(self._hm.events)
        cw = (self.width() - self.NAME_W) / cols
        return QRectF(
            self.NAME_W + cw * col + self.GAP / 2,
            self.HEAD_H + self.ROW_H * row + self.GAP / 2,
            cw - self.GAP,
            self.ROW_H - self.GAP,
        )

    def cell_at(self, x: float, y: float) -> Optional[Tuple[int, int]]:
        if self._hm is None:
            return None
        for r in range(len(self._hm.athletes)):
            for c in range(len(self._hm.events)):
                if self.cell_rect(r, c).contains(x, y):
                    return r, c
        return None

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        hit = self.cell_at(event.position().x(), event.position().y())
        if hit is None or self._hm is None:
            QToolTip.hideText()
            return
        r, c = hit
        a, ev, score = self._hm.athletes[r], self._hm.events[c], self._hm.scores[r][c]
        QToolTip.showText(
            event.globalPosition().toPoint(),
            f"{a.name} · {ev}: punteggio atteso {score:.0f} (forma {a.form}, fatica {a.fatigue})",
            self,
        )

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._hm is None:
            p.setPen(QColor(theme.TEXT_MUTED))
            p.setFont(theme.make_font(theme.FS_SM))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Nessun atleta da confrontare: tessera i primi atleti.")
            p.end()
            return
        hm = self._hm
        cols = len(hm.events)
        cw = (self.width() - self.NAME_W) / cols
        p.setFont(theme.make_font(theme.FS_XS, QFont.Weight.DemiBold))
        p.setPen(QColor(theme.TEXT_MUTED))
        for c, ev in enumerate(hm.events):
            p.drawText(QRectF(self.NAME_W + cw * c, 0, cw, self.HEAD_H), Qt.AlignmentFlag.AlignCenter, short_event_name(ev))
        name_font = theme.make_font(theme.FS_SM)
        cell_font = theme.make_font(theme.FS_SM, QFont.Weight.Bold)
        for r, a in enumerate(hm.athletes):
            y = self.HEAD_H + self.ROW_H * r
            p.setFont(name_font)
            p.setPen(QColor(theme.TEXT if not a.is_injured else theme.TEXT_FAINT))
            label = p.fontMetrics().elidedText(a.name, Qt.TextElideMode.ElideRight, self.NAME_W - 14)
            p.drawText(QRectF(0, y, self.NAME_W - 10, self.ROW_H), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, label)
            for c in range(cols):
                rect = self.cell_rect(r, c)
                color = heat_color(heat_level(hm.scores[r][c]))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(color)
                p.drawRoundedRect(rect, theme.RADIUS_SM, theme.RADIUS_SM)
                p.setFont(cell_font)
                p.setPen(readable_on(color))
                p.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"{hm.scores[r][c]:.0f}")
                if c == hm.best_columns[r]:
                    p.setPen(QPen(QColor(theme.TEXT), 1.6))
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    p.drawRoundedRect(rect.adjusted(1, 1, -1, -1), theme.RADIUS_SM, theme.RADIUS_SM)
        # legenda
        ly = self.HEAD_H + self.ROW_H * len(hm.athletes) + 8
        bar = QRectF(self.NAME_W + 4, ly + 2, min(180.0, cw * cols * 0.5), 8)
        grad = QLinearGradient(bar.left(), 0, bar.right(), 0)
        grad.setColorAt(0, heat_color(0.0))
        grad.setColorAt(0.5, heat_color(0.5))
        grad.setColorAt(1, heat_color(1.0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(grad))
        p.drawRoundedRect(bar, 4, 4)
        p.setFont(theme.make_font(theme.FS_XS))
        p.setPen(QColor(theme.TEXT_FAINT))
        p.drawText(QRectF(bar.left() - 70, ly - 3, 64, 16), Qt.AlignmentFlag.AlignRight, "debole")
        p.drawText(QRectF(bar.right() + 6, ly - 3, 140, 16), Qt.AlignmentFlag.AlignLeft, "forte · anello = specialità")
        p.end()


# ---------------------------------------------------------------- timeline della stagione
class SeasonTimelineWidget(QWidget):
    """La stagione in una riga (G.1): una casella per settimana, gare in rilievo, Preparazione tratteggiata, «oggi» evidenziato, nomi delle fasi sotto."""

    PAD_X, TOP, CELL_H, RACE_H = 6, 22, 14, 30

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._tl: Optional[SeasonTimeline] = None
        self._phases: List[str] = []
        self.setMouseTracking(True)
        self.setMinimumHeight(80)

    def set_timeline(self, tl: Optional[SeasonTimeline], phase_names: Sequence[str] = ()) -> None:
        self._tl, self._phases = tl, list(phase_names)
        self.update()

    def cell_x(self, index: int) -> Tuple[float, float]:
        """(x, larghezza) della casella `index` (da 0)."""
        assert self._tl is not None
        n = len(self._tl.weeks)
        step = (self.width() - 2 * self.PAD_X) / n
        return self.PAD_X + step * index, max(2.0, step - 2)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._tl is None:
            return
        n = len(self._tl.weeks)
        step = (self.width() - 2 * self.PAD_X) / n
        i = int((event.position().x() - self.PAD_X) // step) if step else -1
        if 0 <= i < n:
            w = self._tl.weeks[i]
            kind = "gara" if w.is_race else ("Preparazione" if w.is_prep else "allenamento")
            now = " · oggi" if w.is_current else ""
            QToolTip.showText(event.globalPosition().toPoint(), f"Settimana {w.number}: {kind}{now}", self)

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._tl is None:
            p.end()
            return
        tl = self._tl
        base_y = self.TOP + self.RACE_H  # le caselle poggiano su una linea di base comune
        phase_idx = -1
        p.setFont(theme.make_font(theme.FS_XS))
        for i, w in enumerate(tl.weeks):
            x, cw = self.cell_x(i)
            h = self.RACE_H if w.is_race else self.CELL_H
            rect = QRectF(x, base_y - h, cw, h)
            alpha = 0.38 if w.is_past else 1.0
            if w.is_race:
                color = theme.qcolor(theme.ACCENT, alpha)
            elif w.is_prep:
                color = theme.qcolor(theme.TEXT_FAINT, 0.5 * alpha + 0.2)
            else:
                color = theme.qcolor(theme.BORDER_STRONG, alpha)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(color)
            p.drawRoundedRect(rect, 3, 3)
            if w.is_prep:
                p.setBrush(QBrush(theme.qcolor(theme.BG, 0.55), Qt.BrushStyle.BDiagPattern))
                p.drawRoundedRect(rect, 3, 3)
            if w.is_phase_start:
                phase_idx += 1
                p.setPen(QPen(theme.qcolor(theme.TEXT_FAINT, 0.7), 1))
                p.drawLine(QPointF(x - 1, base_y + 5), QPointF(x - 1, base_y + 22))
                if 0 <= phase_idx < len(self._phases):
                    p.setPen(QColor(theme.TEXT_MUTED))
                    p.drawText(QRectF(x + 3, base_y + 6, 120, 16), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._phases[phase_idx])
            if w.is_current:
                p.setPen(QPen(QColor(theme.TEXT), 2))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(rect.adjusted(-2, -2, 2, 2), 4, 4)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(theme.TEXT))
                tri = QPainterPath(QPointF(x + cw / 2, base_y - h - 4))
                tri.lineTo(QPointF(x + cw / 2 - 5, base_y - h - 11))
                tri.lineTo(QPointF(x + cw / 2 + 5, base_y - h - 11))
                tri.closeSubpath()
                p.drawPath(tri)
        p.end()
