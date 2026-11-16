"""Gare in diretta: animazione delle corse in pista e tabellone dei tentativi nei concorsi.

L'esito è quello già simulato (`CompetitionSummary`): qui lo si mette in scena, non lo si cambia.
"""

from __future__ import annotations

import math
import random
import zlib
from typing import List, Optional, Sequence

from PyQt6.QtCore import QElapsedTimer, QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from models.entities import EVENTS, CompetitionSummary, EventResult, EventStanding

# Distanza percorsa (m) e durata target dell'animazione (s) a velocità 1x: None = tempo reale
TRACK_DISTANCES = {"100m": 100, "400m": 400, "1500m": 1500, "4x100m": 400, "4x400m": 1600}
TRACK_TARGET_SECONDS = {"100m": None, "400m": 24.0, "1500m": 26.0, "4x100m": 16.0, "4x400m": 28.0}
FIELD_ROUNDS = 4
DNF_PROGRESS = 0.42  # un atleta ritirato si ferma a questo punto della gara
PRE_START_SECONDS = 3.0  # "Ai vostri posti" -> "Pronti" -> sparo
GUN_AT = 2.4  # istante dello sparo nella sequenza di partenza
REACTION_RANGE = (0.12, 0.22)  # tempo di reazione ai blocchi (fa parte del tempo ufficiale)


def is_field_event(event_name: str) -> bool:
    ev = EVENTS.get(event_name)
    return ev is not None and ev.unit == "m"


def _rng(*parts: object) -> random.Random:
    """Generatore deterministico: la stessa gara si rivede sempre uguale."""
    return random.Random(zlib.crc32("|".join(str(p) for p in parts).encode()))


def _velocity(kind: str, u: float) -> float:
    """Velocità relativa (sempre > 0) al tempo normalizzato u in [0, 1] per tipo di gara."""
    if kind == "100m":  # forte accelerazione fino a ~60 m, poi leggero calo
        return (1.0 - math.exp(-u / 0.14)) * (1.0 - 0.07 * max(0.0, (u - 0.6) / 0.4)) + 0.02
    if kind == "400m":  # partenza veloce, calo nella seconda metà
        return (1.0 - math.exp(-u / 0.05)) * (1.0 - 0.16 * u) + 0.02
    if kind == "1500m":  # gruppo compatto, poi volata finale
        return (1.0 - math.exp(-u / 0.02)) * (0.92 + 0.05 * u + 1.3 * max(0.0, u - 0.88) ** 1.4) + 0.02
    # staffette: ogni frazione riparte (cambio al volo), con un po' di calo a fine frazione
    s = (u * 4.0) % 1.0
    return 0.72 + 0.28 * (1.0 - math.exp(-s / 0.2)) - 0.06 * s


_CURVE_STEPS = 600
_G_TABLES: dict = {}


def _g_table(kind: str) -> List[float]:
    """Spazio percorso (normalizzato, 0..1) a passi uniformi di tempo: integrale della velocità."""
    table = _G_TABLES.get(kind)
    if table is None:
        cum = [0.0]
        for i in range(1, _CURVE_STEPS + 1):
            u0, u1 = (i - 1) / _CURVE_STEPS, i / _CURVE_STEPS
            cum.append(cum[-1] + 0.5 * (_velocity(kind, u0) + _velocity(kind, u1)) / _CURVE_STEPS)
        table = [c / cum[-1] for c in cum]
        _G_TABLES[kind] = table
    return table


def curve_kind(event_name: str) -> str:
    return "relay" if event_name.startswith("4x") else event_name


def curve_progress(kind: str, u: float, phase: float = 0.0, amp: float = 0.006) -> float:
    """Frazione di percorso (0..1) al tempo normalizzato `u`: 0 al via, 1 esatto all'arrivo.

    Monotona crescente; `phase`/`amp` aggiungono solo piccoli sorpassi scenici.
    """
    u = max(0.0, min(1.0, u))
    table = _g_table(kind)
    pos = u * _CURVE_STEPS
    i = min(_CURVE_STEPS - 1, int(pos))
    g = table[i] + (table[i + 1] - table[i]) * (pos - i)
    return g + amp * math.sin(phase + 7.0 * u) * u * (1.0 - u)


def reaction_time(seed: object, name: str) -> float:
    return _rng(seed, "reaction", name).uniform(*REACTION_RANGE)


def position_fraction(event_name: str, race_t: float, mark: float, reaction: float, phase: float = 0.0) -> float:
    """Frazione di percorso al tempo di gara `race_t` (dallo sparo) per chi chiude in `mark` secondi.

    Il tempo di reazione è incluso nel tempo ufficiale: corre per (mark - reaction) secondi
    e taglia il traguardo esattamente a `mark`.
    """
    return curve_progress(curve_kind(event_name), (race_t - reaction) / max(1e-6, mark - reaction), phase)


def format_race_time(seconds: float) -> str:
    if seconds >= 60:
        return f"{int(seconds // 60)}:{seconds % 60:05.2f}"
    return f"{seconds:.2f}s"


def generate_attempts(mark: float, rng: random.Random, rounds: int = FIELD_ROUNDS) -> List[Optional[float]]:
    """Tentativi di un concorso: uno uguale al risultato finale, gli altri più bassi o nulli (None)."""
    best_round = rng.randrange(rounds)
    attempts: List[Optional[float]] = []
    for i in range(rounds):
        if i == best_round:
            attempts.append(mark)
        elif rng.random() < 0.15:
            attempts.append(None)
        else:
            attempts.append(round(mark * rng.uniform(0.90, 0.992), 2))
    return attempts


def _short(name: str, limit: int = 22) -> str:
    return name if len(name) <= limit else name[: limit - 1] + "…"


def make_crowd(width: int, height: int, seed: object) -> QPixmap:
    """Tribune con la folla, disegnate una volta sola e in modo deterministico."""
    pm = QPixmap(max(1, width), height)
    pm.fill(QColor("#0b1220"))
    q = QPainter(pm)
    rng = _rng("crowd", seed, width)
    for tier in range(max(1, (height - 6) // 17)):
        y0 = 8 + tier * 17
        q.fillRect(0, y0 + 11, width, 6, QColor("#1b2638"))
        x = rng.randint(0, 5)
        while x < width:
            col = QColor.fromHsv(rng.randint(0, 359), rng.randint(60, 200), rng.randint(110, 230))
            q.fillRect(x, y0, 5, 5, QColor("#e2b48f" if rng.random() < 0.6 else "#8a5a3c"))  # testa
            q.fillRect(x - 1, y0 + 5, 7, 6, col)  # busto
            x += rng.randint(7, 10)
    q.end()
    return pm


# --------------------------------------------------------------------------- corse
class TrackRaceWidget(QWidget):
    """Corsie con gli atleti che avanzano verso il traguardo."""

    finished = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(400)
        self._runners: List[dict] = []
        self._event = "100m"
        self._distance = 100
        self._result: Optional[EventResult] = None
        self._crowd_cache: Optional[QPixmap] = None
        self._winner_time = 1.0
        self._scale = 1.0  # secondi di gara per secondo di animazione
        self._t = 0.0  # secondi di animazione dall'inizio (compresa la sequenza di partenza)
        self._done = False

    def set_race(self, event_name: str, result: EventResult, seed: object) -> None:
        self._event = event_name
        self._distance = TRACK_DISTANCES.get(event_name, 100)
        self._result = result
        self._crowd_cache = None
        self._runners = []
        valid = []
        for s in result.standings:
            is_dnf = s.is_player and result.withdrew_injured
            if not is_dnf:
                valid.append(s.mark_value)
            self._runners.append(
                {
                    "s": s,
                    "dnf": is_dnf,
                    "phase": _rng(seed, s.athlete_name).uniform(0, 6.28),
                    "react": reaction_time(seed, s.athlete_name),
                }
            )
        self._winner_time = max(0.5, min(valid) if valid else 1.0)
        target = TRACK_TARGET_SECONDS.get(event_name)
        self._scale = 1.0 if target is None else max(1.0, self._winner_time / target)
        self._t = 0.0
        self._done = False
        self.update()

    # ---- tempo
    @property
    def race_time(self) -> float:
        """Secondi di gara trascorsi dallo sparo (0 durante la sequenza di partenza)."""
        return max(0.0, self._t - GUN_AT) * self._scale

    @property
    def race_clock(self) -> float:
        return min(self._winner_time, self.race_time)

    @property
    def start_phase(self) -> str:
        if self._t < GUN_AT * 0.5:
            return "AI VOSTRI POSTI"
        if self._t < GUN_AT:
            return "PRONTI"
        if self._t < GUN_AT + 0.7:
            return "VIA!"
        return ""

    def _last_finish(self) -> float:
        return max((r["s"].mark_value for r in self._runners if not r["dnf"]), default=0.0)

    def advance(self, dt: float) -> None:
        if self._done:
            return
        self._t += dt
        end_anim = GUN_AT + self._last_finish() / self._scale + 1.2
        if self._t >= end_anim:
            self._t = end_anim
            self._done = True
            self.finished.emit()
        self.update()

    def skip_to_end(self) -> None:
        if not self._done:
            self._t = 1e6
            self.advance(0.0)

    def fraction(self, runner: dict) -> float:
        """Frazione di pista percorsa dall'atleta in questo istante."""
        t = self.race_time
        if runner["dnf"]:
            f = position_fraction(self._event, t, self._winner_time * 1.25, runner["react"], runner["phase"])
            return min(DNF_PROGRESS, f * 0.9)
        return position_fraction(self._event, t, runner["s"].mark_value, runner["react"], runner["phase"])

    def _has_finished(self, runner: dict) -> bool:
        return (not runner["dnf"]) and self.race_time >= runner["s"].mark_value

    # ------------------------------------------------------------------ disegno
    CROWD_H = 78
    LEFT_W = 200
    MINIMAP_H = 30

    def meters(self, r: dict) -> float:
        """Posizione in metri; dopo il traguardo l'atleta rallenta (solo scena)."""
        d = self._distance
        m = self.fraction(r) * d
        if self._has_finished(r):
            t_end = r["s"].mark_value
            probe = 0.1 * max(1.0, self._scale)
            v_end = (d - position_fraction(self._event, t_end - probe, t_end, r["react"], r["phase"]) * d) / probe
            m += v_end * 1.0 * (1.0 - math.exp(-(self.race_time - t_end) / 1.0))
        return m

    def _speed_ratio(self, r: dict) -> float:
        """Velocità istantanea relativa (0..1) per cadenza e posa."""
        if self.race_time <= 0:
            return 0.0
        if self._has_finished(r):
            return max(0.0, 0.8 * math.exp(-(self.race_time - r["s"].mark_value) / 1.0))
        d = self._distance
        step = max(0.05, 0.01 * self._winner_time)
        t = self.race_time
        f0 = position_fraction(self._event, t - step, r["s"].mark_value, r["react"], r["phase"])
        f1 = position_fraction(self._event, t + step, r["s"].mark_value, r["react"], r["phase"])
        v = max(0.0, (f1 - f0)) * d / (2 * step)
        mean = d / max(0.5, r["s"].mark_value)
        return max(0.0, min(1.0, v / (1.3 * mean)))

    @staticmethod
    def _kit(name: str) -> QColor:
        return QColor.fromHsv(zlib.crc32(name.encode()) % 360, 170, 215)

    @staticmethod
    def _skin(name: str) -> QColor:
        tones = ["#f1c7a0", "#d9a066", "#a8714a", "#6b4429", "#3b2416"]
        return QColor(tones[zlib.crc32(("skin" + name).encode()) % len(tones)])

    def _crowd(self, width: int) -> QPixmap:
        """Folla pre-disegnata (deterministica): si ricostruisce solo al cambio di larghezza."""
        if self._crowd_cache is None or self._crowd_cache.width() != width:
            self._crowd_cache = make_crowd(width, self.CROWD_H, self._event)
        return self._crowd_cache

    @staticmethod
    def _draw_runner(
        p: QPainter, x: float, ground: float, h: float, phase: float, ratio: float,
        kit: QColor, skin: QColor, crouch: bool, is_player: bool,
    ) -> None:
        u = h / 10.0
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 70))
        p.drawEllipse(QPointF(x, ground), 3.2 * u, 0.7 * u)

        lean = 0.95 if crouch else 0.12 + 0.30 * ratio
        hip = QPointF(x, ground - (3.4 if crouch else 4.7) * u)
        sh = QPointF(hip.x() + 3.0 * u * math.sin(lean), hip.y() - 3.0 * u * math.cos(lean))
        head = QPointF(sh.x() + 1.2 * u * math.sin(lean + 0.1), sh.y() - 1.2 * u * math.cos(lean + 0.1))

        def limb(a: QPointF, ang1: float, l1: float, ang2: float, l2: float):
            b = QPointF(a.x() + l1 * math.sin(ang1), a.y() + l1 * math.cos(ang1))
            c = QPointF(b.x() + l2 * math.sin(ang2), b.y() + l2 * math.cos(ang2))
            return b, c

        def draw_limb(a, b, c, col, w) -> None:
            pen = QPen(col, w)
            pen.setCapStyle(Qt.PenCapStyle.SquareCap)
            p.setPen(pen)
            p.drawLine(a, b)
            p.drawLine(b, c)

        amp = 0.45 + 0.55 * ratio
        shorts = QColor("#1e293b")
        for k in (1, 0):  # prima il lato lontano, poi quello vicino
            ph = phase + k * math.pi
            if crouch:
                leg_a, knee_flex = (0.9, 0.4) if k == 0 else (-0.3, 1.5)
            else:
                leg_a = amp * math.sin(ph)
                knee_flex = 0.35 + 1.25 * ratio * max(0.0, math.sin(ph + 1.3))
            kn, ft = limb(hip, leg_a, 2.4 * u, leg_a - knee_flex, 2.3 * u)
            draw_limb(hip, kn, ft, skin.darker(130) if k else skin, 1.1 * u)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#f8fafc"))
            p.drawRect(QRectF(ft.x() - 0.2 * u, ft.y() - 0.3 * u, 1.1 * u, 0.6 * u))  # scarpa
            if k == 1:
                arm_a = -amp * 1.1 * math.sin(ph + math.pi)
                el, hand = limb(sh, arm_a if not crouch else 0.3, 1.6 * u, (arm_a if not crouch else 0.2) + 1.2, 1.5 * u)
                draw_limb(sh, el, hand, skin.darker(130), 0.9 * u)
        # busto e calzoncini
        pen = QPen(kit, 1.9 * u)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        p.setPen(pen)
        p.drawLine(hip, sh)
        pen = QPen(shorts, 1.9 * u)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        p.setPen(pen)
        p.drawLine(hip, QPointF(hip.x() + 0.9 * u * math.sin(lean), hip.y() - 0.9 * u * math.cos(lean)))
        for k in (0,):
            ph = phase
            arm_a = -amp * 1.1 * math.sin(ph + math.pi) if not crouch else -0.2
            el, hand = limb(sh, arm_a, 1.6 * u, arm_a + 1.2, 1.5 * u)
            draw_limb(sh, el, hand, skin, 0.9 * u)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(skin)
        p.drawRect(QRectF(head.x() - 0.8 * u, head.y() - 0.9 * u, 1.7 * u, 1.7 * u))
        p.setBrush(QColor("#fbbf24") if is_player else QColor("#111827"))
        p.drawRect(QRectF(head.x() - 0.9 * u, head.y() - 1.0 * u, 1.9 * u, 0.7 * u))  # capelli / fascia

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt API)
        p = QPainter(self)
        w, hgt = self.width(), self.height()
        p.fillRect(self.rect(), QColor("#0b1220"))
        n = len(self._runners)
        if n == 0:
            p.end()
            return
        d = self._distance
        res = self._result
        font = QFont(self.font())
        font.setPointSize(9)
        p.setFont(font)

        p.drawPixmap(0, 0, self._crowd(w))
        track_top = self.CROWD_H + 4
        mini = self.MINIMAP_H if d > 100 else 0
        track_bottom = hgt - mini - 22
        lane_h = (track_bottom - track_top) / n
        x_left, x_right = self.LEFT_W, w - 10

        meters = [self.meters(r) for r in self._runners]
        # camera: 100 m tutta la pista, altrimenti segue (capofila + atleta del club) / 2
        if d <= 100:
            view_w, cam = 118.0, -6.0
        else:
            view_w = 70.0
            leader = max(meters)
            mine = [m for m, r in zip(meters, self._runners) if r["s"].is_player]
            focus = (leader + mine[0]) / 2 if mine else leader
            cam = max(-8.0, min(d + 14.0 - view_w, focus - 0.62 * view_w))
        px = (x_right - x_left) / view_w

        def sx(m: float) -> float:
            return x_left + (m - cam) * px

        # corsie
        for i in range(n):
            y = track_top + i * lane_h
            p.fillRect(int(x_left), int(y), int(x_right - x_left), int(lane_h) + 1,
                       QColor("#a8431c" if i % 2 else "#b84d22"))
            p.fillRect(int(x_left), int(y), int(x_right - x_left), 2, QColor("#f1f5f9"))
        p.fillRect(int(x_left), int(track_bottom), int(x_right - x_left), 2, QColor("#f1f5f9"))

        # zone cambio staffetta
        if self._event.startswith("4x"):
            for k in (1, 2, 3):
                zx = sx(d * k / 4.0 - 10)
                p.fillRect(int(zx), int(track_top), int(20 * px), int(track_bottom - track_top), QColor(250, 204, 21, 55))

        # tacche dei metri e numeri
        step = 10 if d <= 400 else 50
        p.setPen(QColor(255, 255, 255, 70))
        first = int(max(0, math.floor(cam / step) * step))
        for mt in range(first, int(min(d + 16, cam + view_w + step)) + 1, step):
            xx = sx(mt)
            if x_left <= xx <= x_right:
                p.drawLine(int(xx), int(track_top), int(xx), int(track_bottom))
                p.setPen(QColor("#cbd5e1"))
                p.drawText(int(xx - 14), int(track_bottom + 15), 28, 14, Qt.AlignmentFlag.AlignCenter, f"{mt}")
                p.setPen(QColor(255, 255, 255, 70))

        # linea di partenza
        sxs = sx(0)
        if x_left <= sxs <= x_right:
            p.fillRect(int(sxs - 1), int(track_top), 3, int(track_bottom - track_top), QColor("#f8fafc"))

        # traguardo + nastro
        fx = sx(d)
        first_done = any(self._has_finished(r) for r in self._runners)
        if x_left <= fx <= x_right + 20:
            sq = 6
            for j in range(int((track_bottom - track_top) // sq) + 1):
                for k in range(2):
                    p.fillRect(int(fx + k * sq - 3), int(track_top + j * sq), sq, sq,
                               QColor("#f8fafc" if (j + k) % 2 == 0 else "#0f172a"))
            tape_y = int(track_top - 6)
            if not first_done:
                p.fillRect(int(fx - 40), tape_y, 40, 3, QColor("#f87171"))
            else:
                p.fillRect(int(fx - 40), tape_y, 14, 3, QColor("#f87171"))
                p.fillRect(int(fx + 20), tape_y + 8, 12, 3, QColor("#f87171"))

        # atleti
        # classifica live: chi ha finito ha il piazzamento ufficiale, gli altri vanno per posizione
        order = sorted(
            range(n),
            key=lambda i: (0, self._runners[i]["s"].placement)
            if self._has_finished(self._runners[i])
            else (1, -meters[i]),
        )
        crouch = self.race_time <= 0.0
        for i, r in enumerate(self._runners):
            s: EventStanding = r["s"]
            y = track_top + i * lane_h + lane_h / 2
            ratio = self._speed_ratio(r)
            cycle = 0.7 + 1.6 * ratio
            phase = 2 * math.pi * cycle * max(0.0, self._t - GUN_AT) + r["phase"]
            xx = sx(meters[i])
            sprite_h = min(lane_h * 0.92, 54)
            kit = QColor("#fbbf24") if s.is_player else self._kit(s.team_name)
            if x_left - 20 <= xx <= x_right + 20:
                self._draw_runner(p, xx, y + sprite_h * 0.42, sprite_h, phase, ratio, kit,
                                  self._skin(s.athlete_name), crouch, s.is_player)
            else:  # fuori inquadratura
                p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
                p.setPen(QColor("#fbbf24" if s.is_player else "#94a3b8"))
                p.drawText(int(x_left + 6), int(y + 4), f"◀ {int(cam - meters[i])} m" if xx < x_left else f"{int(meters[i] - cam - view_w)} m ▶")
            # numero corsia sul blocco di partenza
            if x_left <= sx(0) <= x_right:
                p.setPen(QColor("#fde68a"))
                p.drawText(int(sx(0) - 18), int(y + 4), str(i + 1))

        # pannello a sinistra: classifica live
        p.fillRect(0, int(track_top), self.LEFT_W - 6, int(track_bottom - track_top), QColor("#0f172a"))
        for rank, i in enumerate(order, start=1):
            r = self._runners[i]
            s = r["s"]
            y = track_top + rank * lane_h - lane_h / 2
            fin = self._has_finished(r)
            place = f"{s.placement}°" if fin else (f"{rank}" if self.race_time > 0 else str(i + 1))
            p.setPen(QColor("#fbbf24" if s.is_player else "#e2e8f0"))
            bold = QFont(font)
            bold.setBold(s.is_player)
            p.setFont(bold)
            p.drawText(8, int(y - 1), f"{place:>3}  {_short(s.athlete_name if not self._event.startswith('4x') else s.team_name, 22)}")
            p.setPen(QColor("#64748b"))
            p.setFont(font)
            if self._event.startswith("4x") and not r["dnf"]:
                legs = s.athlete_name.split(" / ")
                leg = min(3, int(max(0.0, min(0.999, meters[i] / d)) * 4))
                sub = f"Fraz. {leg + 1}" + (f": {legs[leg]}" if len(legs) == 4 else "")
            else:
                sub = s.team_name
            p.drawText(30, int(y + 12), _short(sub, 26))
            if fin:
                p.setPen(QColor("#fbbf24" if s.is_player else "#e2e8f0"))
                p.drawText(self.LEFT_W - 70, int(y - 1), 64, 14, Qt.AlignmentFlag.AlignRight, s.mark_display)
            elif r["dnf"] and self.race_time > self._winner_time * 0.8:
                p.setPen(QColor("#f87171"))
                p.drawText(self.LEFT_W - 70, int(y - 1), 64, 14, Qt.AlignmentFlag.AlignRight, "RIT")

        # minimappa
        if mini:
            my = track_bottom + 22
            p.fillRect(int(x_left), my + 8, int(x_right - x_left), 4, QColor("#334155"))
            vx0 = x_left + (x_right - x_left) * max(0.0, cam) / d
            vw = (x_right - x_left) * min(1.0, view_w / d)
            p.fillRect(int(vx0), my + 4, int(vw), 12, QColor(56, 189, 248, 50))
            for i, r in enumerate(self._runners):
                mx = x_left + (x_right - x_left) * max(0.0, min(1.0, meters[i] / d))
                p.setBrush(QColor("#fbbf24" if r["s"].is_player else "#94a3b8"))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawRect(int(mx - 3), my + 6, 7, 8)

        # banner: partenza, foto finish, record, squalifica
        phase_txt = self.start_phase
        marks = sorted(r["s"].mark_value for r in self._runners if not r["dnf"])
        photo = len(marks) > 1 and marks[1] - marks[0] <= 0.05
        banners: List[tuple] = []
        if phase_txt:
            banners.append((phase_txt, "#fbbf24" if phase_txt == "VIA!" else "#f8fafc"))
        if first_done and photo and self.race_time < self._winner_time + 3.0 * self._scale:
            banners.append(("FOTO FINISH", "#38bdf8"))
        if res is not None and self._done_all():
            if res.is_club_record:
                banners.append(("RECORD SOCIALE!", "#34d399"))
            elif res.is_pb:
                banners.append(("PRIMATO PERSONALE!", "#34d399"))
            if res.disqualified:
                banners.append(("SQUADRA SQUALIFICATA", "#f87171"))
        if banners:
            big = QFont(font)
            big.setPointSize(26)
            big.setBold(True)
            p.setFont(big)
            text, col = banners[-1]
            area = QRectF(x_left, track_top, x_right - x_left, track_bottom - track_top)
            p.setPen(QColor(0, 0, 0, 170))
            p.drawText(area.adjusted(2, 2, 2, 2), Qt.AlignmentFlag.AlignCenter, text)
            p.setPen(QColor(col))
            p.drawText(area, Qt.AlignmentFlag.AlignCenter, text)

        # vento
        if res is not None and res.wind_ms is not None:
            p.setFont(font)
            p.fillRect(w - 156, 4, 148, 20, QColor(11, 18, 32, 220))
            p.setPen(QColor("#fca5a5" if res.wind_illegal else "#e2e8f0"))
            arrow = "→" if res.wind_ms >= 0 else "←"
            p.drawText(w - 152, 6, 140, 16, Qt.AlignmentFlag.AlignRight, f"Vento {arrow} {res.wind_ms:+.1f} m/s")
        p.end()

    def _done_all(self) -> bool:
        return self.race_time >= self._last_finish() + 0.3


# --------------------------------------------------------------------------- concorsi
class FieldBoardWidget(QTableWidget):
    """Tabellone dei tentativi: un tentativo per atleta ad ogni round, poi la classifica."""

    finished = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(0, FIELD_ROUNDS + 3, parent)
        self.setHorizontalHeaderLabels(
            ["Atleta"] + [f"Prova {i + 1}" for i in range(FIELD_ROUNDS)] + ["Migliore", "Pos"]
        )
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._steps: List[tuple] = []
        self._step = 0
        self._acc = 0.0
        self._step_time = 0.28
        self._done = False
        self._attempts: List[List[Optional[float]]] = []
        self._standings: List[EventStanding] = []
        self._unit = "m"

    def set_race(self, event_name: str, result: EventResult, seed: object) -> None:
        order = list(result.standings)
        _rng(seed, event_name).shuffle(order)  # ordine di gara: non anticipa la classifica
        self._standings = order
        self._unit = EVENTS[event_name].unit
        self._attempts = []
        self.setRowCount(len(order))
        for row, s in enumerate(order):
            if s.is_player and result.withdrew_injured:
                self._attempts.append([None] * FIELD_ROUNDS)
            else:
                self._attempts.append(generate_attempts(s.mark_value, _rng(seed, event_name, s.athlete_name)))
            name = QTableWidgetItem(f"{s.athlete_name}  ·  {s.team_name}")
            if s.is_player:
                name.setForeground(QColor("#fbbf24"))
            self.setItem(row, 0, name)
            for col in range(1, FIELD_ROUNDS + 3):
                item = QTableWidgetItem("")
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.setItem(row, col, item)
        self._steps = [(rnd, row) for rnd in range(FIELD_ROUNDS) for row in range(len(order))]
        self._step = 0
        self._acc = 0.0
        self._done = False

    def advance(self, dt: float) -> None:
        if self._done:
            return
        self._acc += dt
        while self._acc >= self._step_time and self._step < len(self._steps):
            self._acc -= self._step_time
            self._reveal(self._step)
            self._step += 1
        if self._step >= len(self._steps) and self._acc >= 0.6:
            self._finish()

    def skip_to_end(self) -> None:
        while self._step < len(self._steps):
            self._reveal(self._step)
            self._step += 1
        if not self._done:
            self._finish()

    def _reveal(self, idx: int) -> None:
        rnd, row = self._steps[idx]
        value = self._attempts[row][rnd]
        item = self.item(row, 1 + rnd)
        item.setText("X" if value is None else f"{value:.2f}")
        item.setForeground(QColor("#f87171" if value is None else "#e2e8f0"))
        best = max((v for v in self._attempts[row][: rnd + 1] if v is not None), default=None)
        self.item(row, FIELD_ROUNDS + 1).setText("—" if best is None else f"{best:.2f}")
        self.scrollToItem(item)

    def _finish(self) -> None:
        self._done = True
        for row, s in enumerate(self._standings):
            self.item(row, FIELD_ROUNDS + 1).setText(s.mark_display)
            pos = self.item(row, FIELD_ROUNDS + 2)
            pos.setText(f"{s.placement}°")
            if s.placement == 1:
                pos.setForeground(QColor("#fbbf24"))
        self.finished.emit()


class FieldSceneWidget(QWidget):
    """Scena laterale di un concorso: salto in lungo (rincorsa, stacco, sabbia) o getto del peso."""

    CROWD_H = 62

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(230)
        self.kind = "lj"
        self.lo, self.hi = 0.0, 8.0  # misure della gara: definiscono il righello
        self.cur: Optional[dict] = None
        self.t = 0.0
        self.dur = 1.0

    def configure(self, event_name: str, marks: Sequence[float]) -> None:
        self.kind = "lj" if event_name == "Salto in Lungo" else "sp"
        good = [m for m in marks if m > 0]
        self.lo = min(good) if good else 1.0
        self.hi = max(good) if good else 8.0
        self.cur = None
        self.update()

    def begin(self, name: str, team: str, is_player: bool, dist: float, foul: bool, animate: bool, n: int, total: int) -> None:
        self.cur = {
            "name": name, "team": team, "player": is_player, "dist": dist,
            "foul": foul, "animate": animate, "n": n, "total": total,
        }
        self.t, self.dur = 0.0, 1.0
        self.update()

    def set_time(self, t: float, dur: float) -> None:
        self.t, self.dur = t, dur
        self.update()

    def clear(self) -> None:
        self.cur = None
        self.update()

    # ---- geometria
    def _world(self) -> tuple:
        if self.kind == "lj":
            return -9.0, self.hi + 1.6
        return -3.0, self.hi + 3.0

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor("#0b1220"))
        p.drawPixmap(0, 0, make_crowd(w, self.CROWD_H, self.kind))
        ground = h - 44
        wx0, wx1 = self._world()
        left, right = 14, w - 14
        px = (right - left) / (wx1 - wx0)

        def sx(m: float) -> float:
            return left + (m - wx0) * px

        font = QFont(self.font())
        font.setPointSize(9)
        p.setFont(font)
        # sfondo: muretto con cartelloni, poi terreno
        p.fillRect(0, self.CROWD_H, w, int(ground - self.CROWD_H), QColor("#111c33"))
        p.fillRect(0, int(ground - 26), w, 22, QColor("#1e3a5f"))
        for k in range(0, w, 70):
            p.fillRect(k + 6, int(ground - 22), 54, 14, QColor("#0f172a"))
        if self.kind == "lj":
            p.fillRect(left, int(ground), int(sx(0) - left), int(h - ground), QColor("#a8431c"))  # rincorsa
            p.fillRect(int(sx(0)), int(ground), int(sx(1.0) - sx(0)), int(h - ground), QColor("#a8431c"))
            p.fillRect(int(sx(1.0)), int(ground - 4), int(right - sx(1.0)), int(h - ground + 4), QColor("#e7d3a1"))  # sabbia
            p.fillRect(int(sx(0) - 1), int(ground - 2), 5, 4, QColor("#f8fafc"))  # asse di battuta
        else:
            p.fillRect(left, int(ground), right - left, int(h - ground), QColor("#1f5130"))
            p.setBrush(QColor("#cbd5e1"))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(sx(-1.0), ground + 8), 1.6 * px, 7)  # cerchio di lancio
        p.fillRect(left, int(ground), right - left, 2, QColor("#f1f5f9"))
        # righello
        step = 1 if self.kind == "lj" else 2
        start = int(math.ceil(max(1.0, self.lo * 0.7) / step) * step)
        p.setPen(QColor(15, 23, 42, 200) if self.kind == "lj" else QColor(255, 255, 255, 160))
        for mt in range(start, int(wx1), step):
            xx = sx(mt)
            p.drawLine(int(xx), int(ground), int(xx), int(ground + 8))
            p.drawText(int(xx - 16), int(ground + 24), 32, 14, Qt.AlignmentFlag.AlignCenter, f"{mt}m")

        cur = self.cur
        if cur is None:
            p.end()
            return
        t, dur = self.t, self.dur
        d = cur["dist"]
        sprite_h = min(70.0, (ground - self.CROWD_H) * 0.55)
        kit = QColor("#fbbf24") if cur["player"] else QColor.fromHsv(zlib.crc32(cur["team"].encode()) % 360, 170, 215)
        skin = TrackRaceWidget._skin(cur["name"])

        def flag(x: float, label: str, col: str) -> None:
            p.setPen(QPen(QColor("#e2e8f0"), 2))
            p.drawLine(int(x), int(ground), int(x), int(ground - 34))
            p.fillRect(int(x), int(ground - 34), 62, 16, QColor(col))
            p.setPen(QColor("#0f172a"))
            p.drawText(int(x + 3), int(ground - 34), 58, 16, Qt.AlignmentFlag.AlignCenter, label)

        label = "NULLO" if cur["foul"] else f"{d:.2f}"
        colour = "#f87171" if cur["foul"] else "#34d399"
        flag_x = sx(0.0 if cur["foul"] else d)

        if not cur["animate"]:
            flag(flag_x, label, colour)
        elif self.kind == "lj":
            run_end, jump_end = 1.15, 1.85
            if t < run_end:
                x_m = -9.0 + 9.0 * (t / run_end)
                ratio = min(1.0, 0.3 + t)
                TrackRaceWidget._draw_runner(p, sx(x_m), ground, sprite_h, 2 * math.pi * 2.0 * t, ratio, kit, skin, False, cur["player"])
            elif t < jump_end:
                s_ = (t - run_end) / (jump_end - run_end)
                x_m = d * s_
                air = 4.0 * (0.35 * (d / 7.0) + 1.0) * s_ * (1.0 - s_)
                TrackRaceWidget._draw_runner(p, sx(x_m), ground - air * px * 0.55, sprite_h, 1.2, 1.0, kit, skin, False, cur["player"])
            else:
                # atterraggio: sabbia che schizza e bandierina con la misura
                TrackRaceWidget._draw_runner(p, sx(d), ground, sprite_h, 0.0, 0.0, kit, skin, True, cur["player"])
                age = t - jump_end
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor("#e7d3a1"))
                for k in range(8):
                    a_ = k * 0.8
                    r_ = min(1.0, age * 2.5)
                    p.drawRect(QRectF(sx(d) + math.cos(a_) * 22 * r_, ground - 6 - abs(math.sin(a_)) * 26 * r_, 4, 4))
                if age > 0.25:
                    flag(flag_x, label, colour)
        else:  # getto del peso
            wind_end, fly_end = 1.0, 2.0
            ring_x = sx(-1.0)
            if t < wind_end:
                spin = 2 * math.pi * 1.6 * t
                TrackRaceWidget._draw_runner(p, ring_x, ground, sprite_h, spin, 0.25 + 0.4 * t, kit, skin, t < 0.35, cur["player"])
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor("#94a3b8"))
                p.drawEllipse(QPointF(ring_x + 6, ground - sprite_h * 0.78), 4.5, 4.5)
            else:
                TrackRaceWidget._draw_runner(p, ring_x, ground, sprite_h, 1.0, 0.1, kit, skin, False, cur["player"])
                s_ = min(1.0, (t - wind_end) / (fly_end - wind_end))
                bx = 0.3 + (d - 0.3) * s_
                apex = 3.2 + 0.14 * d
                by = 2.0 * (1 - s_) + 4.0 * apex * s_ * (1.0 - s_)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor("#e2e8f0"))
                p.drawEllipse(QPointF(sx(bx), ground - by * px * 0.6 - 4), 5, 5)
                if t >= fly_end:
                    flag(flag_x, label, colour)

        # etichetta attuale
        p.setFont(font)
        p.setPen(QColor("#fbbf24" if cur["player"] else "#e2e8f0"))
        p.fillRect(left, self.CROWD_H + 6, 330, 20, QColor(11, 18, 32, 210))
        p.drawText(left + 6, self.CROWD_H + 6, 322, 20, Qt.AlignmentFlag.AlignVCenter,
                   f"Prova {cur['n']}/{cur['total']} — {cur['name']} ({cur['team']})")
        p.end()


class FieldEventWidget(QWidget):
    """Concorso completo: scena animata sopra, tabellone dei tentativi sotto.

    Solo le prove dell'atleta del club sono animate per intero; le altre scorrono veloci."""

    finished = pyqtSignal()
    PLAYER_SECONDS = {"lj": 2.9, "sp": 2.6}
    OTHER_SECONDS = 0.22

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.scene = FieldSceneWidget()
        self.board = FieldBoardWidget()
        lay.addWidget(self.scene, stretch=3)
        lay.addWidget(self.board, stretch=2)
        self.board.finished.connect(self._board_done)
        self._step = 0
        self._acc = 0.0
        self._started = False
        self._done = False
        self._event = "Salto in Lungo"

    def set_race(self, event_name: str, result: EventResult, seed: object) -> None:
        self._event = event_name
        self.board.set_race(event_name, result, seed)
        self.scene.configure(event_name, [s.mark_value for s in result.standings])
        self._step = 0
        self._acc = 0.0
        self._started = False
        self._done = False

    def _is_player(self, row: int) -> bool:
        return self.board._standings[row].is_player

    def _begin_step(self) -> None:
        rnd, row = self.board._steps[self._step]
        s = self.board._standings[row]
        value = self.board._attempts[row][rnd]
        valid = [v for v in self.board._attempts[row] if v is not None]
        dist = value if value is not None else (max(valid) * 0.97 if valid else s.mark_value * 0.95)
        self.scene.begin(
            s.athlete_name, s.team_name, s.is_player, dist, value is None,
            animate=s.is_player, n=rnd + 1, total=FIELD_ROUNDS,
        )

    def advance(self, dt: float) -> None:
        if self._done:
            return
        self._acc += dt
        kind = self.scene.kind
        steps = self.board._steps
        while self._step < len(steps):
            if not self._started:
                self._begin_step()
                self._started = True
            _rnd, row = steps[self._step]
            dur = self.PLAYER_SECONDS[kind] if self._is_player(row) else self.OTHER_SECONDS
            if self._acc < dur:
                self.scene.set_time(self._acc, dur)
                return
            self._acc -= dur
            self.board._reveal(self._step)
            self._step += 1
            self._started = False
        self.scene.clear()
        if self._acc >= 0.6:
            self.board._finish()

    def skip_to_end(self) -> None:
        if self._done:
            return
        while self._step < len(self.board._steps):
            self.board._reveal(self._step)
            self._step += 1
        self.scene.clear()
        self.board._finish()

    def _board_done(self) -> None:
        if not self._done:
            self._done = True
            self.finished.emit()


# --------------------------------------------------------------------------- dialog
class RaceViewerDialog(QDialog):
    """Mostra una dopo l'altra le gare del meeting. Si può accelerare, saltare o chiudere."""

    SPEEDS = (1.0, 2.0, 4.0)

    def __init__(self, summary: CompetitionSummary, parent=None) -> None:
        super().__init__(parent)
        self.summary = summary
        self.setWindowTitle(f"Gare in diretta — {summary.meet_name}")
        self.resize(900, 560)
        self._index = -1
        self._speed_idx = 0
        self._paused = False
        self._race_done = True

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(8)

        self.title = QLabel()
        self.title.setObjectName("AppTitle")
        root.addWidget(self.title)
        self.info = QLabel()
        self.info.setObjectName("SubTitle")
        root.addWidget(self.info)

        self.stack = QStackedWidget()
        from views.race_3d import Track3DWidget  # import tardivo: race_3d usa questo modulo

        self.track2d = TrackRaceWidget()
        self.track3d = Track3DWidget()
        self.track = self.track3d  # vista in uso per le corse (3D di default)
        self.field = FieldEventWidget()
        self.stack.addWidget(self.track2d)
        self.stack.addWidget(self.track3d)
        self.stack.addWidget(self.field)
        root.addWidget(self.stack, stretch=1)

        self.clock = QLabel("")
        self.clock.setStyleSheet("font-size: 18px; font-weight: 800; color: #f8fafc;")
        root.addWidget(self.clock)
        self.podium = QLabel("")
        self.podium.setObjectName("SectionHeader")
        self.podium.setWordWrap(True)
        root.addWidget(self.podium)

        bar = QHBoxLayout()
        self.btn_pause = QPushButton("⏸ Pausa")
        self.btn_pause.clicked.connect(self._toggle_pause)
        self.btn_speed = QPushButton("Velocità 1x")
        self.btn_speed.clicked.connect(self._cycle_speed)
        self.btn_view = QPushButton("Vista 2D")
        self.btn_view.setToolTip("Passa dalla vista 3D alla vista 2D (più leggera)")
        self.btn_view.clicked.connect(self._toggle_view)
        self.btn_skip = QPushButton("⏩ Salta alla fine")
        self.btn_skip.clicked.connect(self._skip_race)
        self.btn_next = QPushButton("Prossima gara ▶")
        self.btn_next.setObjectName("PrimaryButton")
        self.btn_next.clicked.connect(self._next)
        self.btn_close = QPushButton("Vai ai risultati")
        self.btn_close.clicked.connect(self.accept)
        for b in (self.btn_pause, self.btn_speed, self.btn_view, self.btn_skip):
            bar.addWidget(b)
        bar.addStretch()
        bar.addWidget(self.btn_close)
        bar.addWidget(self.btn_next)
        root.addLayout(bar)

        self.track2d.finished.connect(self._on_race_finished)
        self.track3d.finished.connect(self._on_race_finished)
        self.field.finished.connect(self._on_race_finished)
        self._clock = QElapsedTimer()
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)

        self._next()

    # ---- controllo
    def _seed(self) -> str:
        return f"{self.summary.week}-{self.summary.meet_name}"

    def _next(self) -> None:
        if not self._race_done:
            self._skip_race()
            return
        self._index += 1
        results = self.summary.event_results
        if self._index >= len(results):
            self.accept()
            return
        res = results[self._index]
        total = len(results)
        self.title.setText(f"{res.event_name} — gara {self._index + 1} di {total}")
        wind = "" if res.wind_ms is None else f"  |  Vento: {res.wind_ms:+.1f} m/s" + (" (non omologato)" if res.wind_illegal else "")
        self.info.setText(
            f"Meteo: {self.summary.weather.value}  |  Pista: {self.summary.track_surface}{wind}"
            f"  |  Atteggiamento: {res.attitude}"
        )
        self.podium.setText("")
        self.clock.setText("")
        self._race_done = False
        if is_field_event(res.event_name):
            self.field.set_race(res.event_name, res, self._seed())
            self.stack.setCurrentWidget(self.field)
        else:
            self.track.set_race(res.event_name, res, self._seed())
            self.stack.setCurrentWidget(self.track)
        self.btn_next.setEnabled(False)
        self.btn_skip.setEnabled(True)
        self._clock.start()
        self._timer.start()

    def _current_widget(self):
        return self.stack.currentWidget()

    def _tick(self) -> None:
        dt = self._clock.restart() / 1000.0
        if self._paused or self._race_done:
            return
        w = self._current_widget()
        w.advance(dt * self.SPEEDS[self._speed_idx])
        if w is self.track:
            self.clock.setText(f"⏱ {format_race_time(self.track.race_clock)}")

    def _toggle_view(self) -> None:
        """Cambia fra vista 3D e 2D senza perdere il punto della gara."""
        old = self.track
        new = self.track2d if old is self.track3d else self.track3d
        if self.stack.currentWidget() is old and 0 <= self._index < len(self.summary.event_results):
            res = self.summary.event_results[self._index]
            new.set_race(res.event_name, res, self._seed())
            new._t, new._done = old._t, old._done
            self.stack.setCurrentWidget(new)
        self.track = new
        self.btn_view.setText("Vista 3D" if new is self.track2d else "Vista 2D")

    def _toggle_pause(self) -> None:
        self._paused = not self._paused
        self.btn_pause.setText("▶ Riprendi" if self._paused else "⏸ Pausa")

    def _cycle_speed(self) -> None:
        self._speed_idx = (self._speed_idx + 1) % len(self.SPEEDS)
        self.btn_speed.setText(f"Velocità {int(self.SPEEDS[self._speed_idx])}x")

    def _skip_race(self) -> None:
        if not self._race_done:
            self._current_widget().skip_to_end()

    def _on_race_finished(self) -> None:
        self._race_done = True
        self.btn_skip.setEnabled(False)
        last = self._index >= len(self.summary.event_results) - 1
        self.btn_next.setText("Vai ai risultati ▶" if last else "Prossima gara ▶")
        self.btn_next.setEnabled(True)
        res = self.summary.event_results[self._index]
        top: Sequence[EventStanding] = sorted(res.standings, key=lambda s: s.placement)[:3]
        self.podium.setText("   ".join(f"{s.placement}° {s.athlete_name} {s.mark_display}" for s in top))
        if self.stack.currentWidget() is self.track:
            self.clock.setText(f"⏱ {format_race_time(self.track.race_clock)}")
        note = []
        if res.withdrew_injured:
            note.append(f"{res.player_athlete_name} si è ritirato per infortunio")
        if res.disqualified:
            note.append("squadra squalificata")
        if note:
            self.info.setText(self.info.text() + "  |  " + ", ".join(note))

    def done(self, r: int) -> None:  # chiusura: ferma il timer
        self._timer.stop()
        super().done(r)
