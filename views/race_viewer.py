"""Gare in diretta: animazione delle corse in pista e tabellone dei tentativi nei concorsi.

L'esito è quello già simulato (`CompetitionSummary`): qui lo si mette in scena, non lo si cambia.
"""

from __future__ import annotations

import math
import random
import zlib
from typing import List, Optional, Sequence

from PyQt6.QtCore import QElapsedTimer, QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QFont, QLinearGradient, QPainter, QPen, QPixmap, QPolygonF
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

from models.entities import (
    EVENTS,
    CompetitionSummary,
    CompetitionTier,
    EventResult,
    EventStanding,
    SeasonPhase,
    WeatherCondition,
)

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
    if kind == "100m":  # spinta esplosiva dai blocchi, accelerazione fino a ~60 m, poi leggero calo
        return (0.22 + 0.78 * (1.0 - math.exp(-u / 0.10))) * (1.0 - 0.07 * max(0.0, (u - 0.6) / 0.4))
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
    """Tribune realistiche con gradinate, corrimano, cartelloni e spettatori."""
    pm = QPixmap(max(1, width), height)
    pm.fill(QColor("#1e293b"))
    q = QPainter(pm)
    rng = _rng("crowd", seed, width)
    tiers = max(2, (height - 16) // 16)
    skins = ("#f1c7a0", "#dfb086", "#b87e56", "#7a4e30", "#4b2e1e")
    for tier in range(tiers):
        y0 = 6 + tier * 15
        # gradone in cemento con leggero stacco tonale
        q.fillRect(0, y0, width, 15, QColor("#293548" if tier % 2 == 0 else "#334155"))
        q.fillRect(0, y0 + 13, width, 2, QColor("#0f172a"))
        x = rng.randint(1, 5)
        while x < width - 4:
            col = QColor.fromHsv(rng.randint(0, 359), rng.randint(45, 180), rng.randint(105, 220))
            skin = QColor(rng.choice(skins))
            q.fillRect(x, y0 + 2, 4, 4, skin)
            q.fillRect(x, y0 + 1, 4, 2, QColor("#111827" if rng.random() < 0.75 else "#78350f"))
            q.fillRect(x - 1, y0 + 6, 6, 7, col)
            x += rng.randint(6, 9)
    # muretto inferiore con cartelloni sponsor di fantasia
    wall_y = height - 16
    q.fillRect(0, wall_y, width, 16, QColor("#0f172a"))
    q.fillRect(0, wall_y, width, 2, QColor("#94a3b8"))
    boards = [("TEF SPORT", "#b91c1c"), ("AURORA", "#1d4ed8"), ("VELOCITÀ", "#047857"), ("FASTLANE", "#c2410c"), ("CRONO LAB", "#0e7490")]
    f = QFont("Arial", 8)
    f.setBold(True)
    q.setFont(f)
    bx, idx = 6, 0
    while bx < width - 20:
        txt, bcol = boards[idx % len(boards)]
        bw = 96
        q.fillRect(bx, wall_y + 3, bw, 12, QColor(bcol))
        q.setPen(QColor("#f8fafc"))
        q.drawText(bx, wall_y + 3, bw, 12, Qt.AlignmentFlag.AlignCenter, txt)
        bx += bw + 6
        idx += 1
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
        self._weather = WeatherCondition.SERENO
        self._surface = "Tartan"
        self._tier = CompetitionTier.REGIONALE
        self._season_phase = SeasonPhase.OUTDOOR
        self._spectators = 800

    def set_environment(
        self,
        weather: Optional[WeatherCondition] = None,
        track_surface: str = "",
        tier: Optional[CompetitionTier] = None,
        season_phase: Optional[SeasonPhase] = None,
        spectators: int = 800,
    ) -> None:
        if weather is not None:
            self._weather = weather
        if track_surface:
            self._surface = track_surface
        if tier is not None:
            self._tier = tier
        if season_phase is not None:
            self._season_phase = season_phase
        self._spectators = spectators
        self.update()

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

    def _track_lane_colors(self) -> tuple[str, str]:
        surf = (self._surface or "").lower()
        blue = self._tier == CompetitionTier.INTERNAZIONALE or "mondo" in surf or "blu" in surf
        rain = self._weather == WeatherCondition.PIOGGIA
        if blue:
            return ("#1a4f96", "#1e59a8") if rain else ("#1f62b5", "#246bc4")
        return ("#8f3220", "#9c3925") if rain else ("#a84020", "#b84826")

    @staticmethod
    def _draw_tapered_2d(p: QPainter, a: QPointF, b: QPointF, r0: float, r1: float, col: QColor) -> None:
        dx, dy = b.x() - a.x(), b.y() - a.y()
        dist = math.hypot(dx, dy)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col)
        if dist < 0.4:
            p.drawEllipse(a, r0, r0)
            return
        nx, ny = -dy / dist, dx / dist
        p.drawPolygon(
            QPolygonF(
                [
                    QPointF(a.x() + nx * r0, a.y() + ny * r0),
                    QPointF(b.x() + nx * r1, b.y() + ny * r1),
                    QPointF(b.x() - nx * r1, b.y() - ny * r1),
                    QPointF(a.x() - nx * r0, a.y() - ny * r0),
                ]
            )
        )
        p.drawEllipse(a, r0, r0)
        p.drawEllipse(b, r1, r1)

    @staticmethod
    def _draw_runner(
        p: QPainter, x: float, ground: float, h: float, phase: float, ratio: float,
        kit: QColor, skin: QColor, crouch: bool, is_player: bool,
        set_blend: float = 1.0,
    ) -> None:
        u = h / 10.0
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 75))
        p.drawEllipse(QPointF(x, ground), 2.8 * u, 0.55 * u)

        if crouch:
            lean = 1.15 + 0.08 * set_blend
            hip = QPointF(x - (2.2 - 0.5 * set_blend) * u, ground - (2.7 + 1.1 * set_blend) * u)
        else:
            lean = 0.14 + 0.28 * ratio
            bounce = 0.25 * abs(math.sin(phase)) * ratio
            hip = QPointF(x, ground - (4.7 + bounce) * u)
        sh = QPointF(hip.x() + 2.95 * u * math.sin(lean), hip.y() - 2.95 * u * math.cos(lean))
        neck = QPointF(sh.x() + 0.55 * u * math.sin(lean), sh.y() - 0.55 * u * math.cos(lean))
        head = QPointF(neck.x() + 0.65 * u * math.sin(lean + 0.08), neck.y() - 0.65 * u * math.cos(lean + 0.08))

        def limb(a: QPointF, ang1: float, l1: float, ang2: float, l2: float):
            b = QPointF(a.x() + l1 * math.sin(ang1), a.y() + l1 * math.cos(ang1))
            c = QPointF(b.x() + l2 * math.sin(ang2), b.y() + l2 * math.cos(ang2))
            return b, c

        amp = 0.50 + 0.56 * ratio
        shorts = QColor("#0f172a")
        spike_col = kit.lighter(135) if is_player else QColor("#f8fafc")
        for k in (1, 0):  # prima il lato lontano, poi quello vicino
            ph = phase + k * math.pi
            col_s = skin.darker(132) if k else skin
            col_sh = shorts.darker(125) if k else shorts
            if crouch:
                if k == 0:
                    kn = QPointF(x - 1.2 * u, ground - (1.3 + 0.9 * set_blend) * u)
                    ft = QPointF(x - 2.2 * u, ground - 0.4 * u)
                else:
                    kn = QPointF(x - 1.8 * u, ground - (0.6 + 1.0 * set_blend) * u)
                    ft = QPointF(x - 3.4 * u, ground - 0.4 * u)
                el = QPointF((sh.x() + x - 0.3 * u) * 0.5, (sh.y() + ground) * 0.5)
                hand = QPointF(x - 0.3 * u, ground - 0.15 * u)
            else:
                leg_a = amp * math.sin(ph)
                knee_flex = 0.30 + 1.50 * ratio * max(0.0, math.sin(ph + 1.25))
                kn, ft = limb(hip, leg_a, 2.45 * u, leg_a - knee_flex, 2.35 * u)
                arm_a = -amp * 1.15 * math.sin(ph + math.pi)
                el, hand = limb(sh, arm_a, 1.55 * u, arm_a + 1.35, 1.45 * u)
            mid_thigh = QPointF(hip.x() + (kn.x() - hip.x()) * 0.52, hip.y() + (kn.y() - hip.y()) * 0.52)
            TrackRaceWidget._draw_tapered_2d(p, hip, kn, 0.56 * u, 0.38 * u, col_s)
            TrackRaceWidget._draw_tapered_2d(p, hip, mid_thigh, 0.64 * u, 0.54 * u, col_sh)
            TrackRaceWidget._draw_tapered_2d(p, kn, ft, 0.38 * u, 0.22 * u, col_s)
            TrackRaceWidget._draw_tapered_2d(p, ft, QPointF(ft.x() + 0.85 * u, ft.y() + 0.12 * u), 0.24 * u, 0.16 * u, spike_col)
            if k == 1:
                TrackRaceWidget._draw_tapered_2d(p, sh, el, 0.36 * u, 0.28 * u, col_s)
                TrackRaceWidget._draw_tapered_2d(p, el, hand, 0.27 * u, 0.18 * u, col_s)

        # busto sagomato e canotta
        TrackRaceWidget._draw_tapered_2d(p, hip, sh, 0.72 * u, 0.92 * u, kit)
        TrackRaceWidget._draw_tapered_2d(p, hip, QPointF(hip.x() + 0.95 * u * math.sin(lean), hip.y() - 0.95 * u * math.cos(lean)), 0.76 * u, 0.74 * u, shorts)
        # pettorale bianco sul torace
        bib_c = QPointF((hip.x() + sh.x() * 1.4) / 2.4 + 0.35 * u, (hip.y() + sh.y() * 1.4) / 2.4)
        p.setBrush(QColor("#f8fafc"))
        p.drawRect(QRectF(bib_c.x() - 0.28 * u, bib_c.y() - 0.35 * u, 0.55 * u, 0.68 * u))
        # collo e braccio vicino
        TrackRaceWidget._draw_tapered_2d(p, sh, neck, 0.36 * u, 0.30 * u, skin.darker(108))
        if crouch:
            el = QPointF((sh.x() + x - 0.2 * u) * 0.5, (sh.y() + ground) * 0.5)
            hand = QPointF(x - 0.2 * u, ground - 0.12 * u)
        else:
            arm_a = -amp * 1.15 * math.sin(phase + math.pi)
            el, hand = limb(sh, arm_a, 1.55 * u, arm_a + 1.35, 1.45 * u)
        TrackRaceWidget._draw_tapered_2d(p, sh, el, 0.36 * u, 0.28 * u, skin)
        TrackRaceWidget._draw_tapered_2d(p, el, hand, 0.27 * u, 0.18 * u, skin)
        # testa arrotondata con capelli
        p.setBrush(skin)
        p.drawEllipse(head, 0.72 * u, 0.82 * u)
        p.setBrush(QColor("#111827"))
        p.drawChord(QRectF(head.x() - 0.75 * u, head.y() - 0.88 * u, 1.50 * u, 1.40 * u), 20 * 16, 155 * 16)
        if is_player:
            p.setBrush(QColor("#fbbf24"))
            p.drawChord(QRectF(head.x() - 0.75 * u, head.y() - 0.82 * u, 1.50 * u, 1.25 * u), 18 * 16, 144 * 16)
            tip_y = head.y() - 1.15 * u
            tri_h = max(6.0, 1.35 * u)
            tri_w = max(5.0, 0.95 * u)
            p.setPen(QPen(QColor("#0f172a"), 1.2))
            p.setBrush(QColor("#facc15"))
            p.drawPolygon(QPolygonF([
                QPointF(head.x() - tri_w, tip_y - tri_h),
                QPointF(head.x() + tri_w, tip_y - tri_h),
                QPointF(head.x(), tip_y),
            ]))
            p.setPen(Qt.PenStyle.NoPen)

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

        # corsie con colore coerente con superficie e categoria
        c_even, c_odd = self._track_lane_colors()
        for i in range(n):
            y = track_top + i * lane_h
            p.fillRect(int(x_left), int(y), int(x_right - x_left), int(lane_h) + 1,
                       QColor(c_odd if i % 2 else c_even))
            p.fillRect(int(x_left), int(y), int(x_right - x_left), 2, QColor("#f8fafc"))
        p.fillRect(int(x_left), int(track_bottom), int(x_right - x_left), 2, QColor("#f8fafc"))

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

        # linea di partenza e blocchi
        sxs = sx(0)
        if x_left <= sxs <= x_right:
            p.fillRect(int(sxs - 1), int(track_top), 3, int(track_bottom - track_top), QColor("#f8fafc"))
            for i in range(n):
                by = track_top + i * lane_h + lane_h * 0.52
                p.fillRect(int(sxs - 2.2 * px), int(by), int(1.9 * px), 4, QColor("#334155"))

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
        set_blend = max(0.0, min(1.0, (self._t - GUN_AT * 0.45) / 0.38))
        for i, r in enumerate(self._runners):
            s: EventStanding = r["s"]
            y = track_top + i * lane_h + lane_h / 2
            ratio = self._speed_ratio(r)
            cycle = 0.75 + 1.65 * ratio
            phase = 2 * math.pi * cycle * max(0.0, self._t - GUN_AT) + r["phase"]
            xx = sx(meters[i])
            sprite_h = min(lane_h * 0.92, 54)
            kit = QColor("#f59e0b") if s.is_player else self._kit(s.team_name)
            if x_left - 20 <= xx <= x_right + 20:
                self._draw_runner(p, xx, y + sprite_h * 0.42, sprite_h, phase, ratio, kit,
                                  self._skin(s.athlete_name), crouch, s.is_player, set_blend=set_blend)
            else:  # fuori inquadratura
                p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
                p.setPen(QColor("#fbbf24" if s.is_player else "#94a3b8"))
                p.drawText(int(x_left + 6), int(y + 4), f"◀ {int(cam - meters[i])} m" if xx < x_left else f"{int(meters[i] - cam - view_w)} m ▶")
            # numero corsia sul blocco di partenza
            if x_left <= sx(0) <= x_right:
                p.setPen(QColor("#fde68a"))
                p.drawText(int(sx(0) - 24), int(y + 4), str(i + 1))

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
            p.setBrush(QColor(11, 18, 32, 230))
            p.setPen(QPen(QColor(51, 65, 85, 200), 1))
            p.drawRoundedRect(QRectF(w - 158, 4, 150, 22), 5, 5)
            p.setPen(QColor("#fca5a5" if res.wind_illegal else "#e2e8f0"))
            arrow = "→" if res.wind_ms >= 0 else "←"
            p.drawText(w - 154, 5, 142, 20, Qt.AlignmentFlag.AlignCenter, f"Vento {arrow} {res.wind_ms:+.1f} m/s")
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
        self._crowd_cache: Optional[QPixmap] = None
        self._weather = WeatherCondition.SERENO
        self._surface = "Tartan"
        self._tier = CompetitionTier.REGIONALE

    def set_environment(
        self,
        weather: Optional[WeatherCondition] = None,
        track_surface: str = "",
        tier: Optional[CompetitionTier] = None,
    ) -> None:
        if weather is not None:
            self._weather = weather
        if track_surface:
            self._surface = track_surface
        if tier is not None:
            self._tier = tier
        self.update()

    def configure(self, event_name: str, marks: Sequence[float]) -> None:
        self.kind = "lj" if event_name == "Salto in Lungo" else "sp"
        good = [m for m in marks if m > 0]
        self.lo = min(good) if good else 1.0
        self.hi = max(good) if good else 8.0
        self.cur = None
        self._crowd_cache = None
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

    def _crowd(self, width: int) -> QPixmap:
        if self._crowd_cache is None or self._crowd_cache.width() != width:
            self._crowd_cache = make_crowd(width, self.CROWD_H, self.kind)
        return self._crowd_cache

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor("#0b1220"))
        ground = h - 44
        wx0, wx1 = self._world()
        left, right = 14, w - 14
        px = (right - left) / (wx1 - wx0)

        def sx(m: float) -> float:
            return left + (m - wx0) * px

        font = QFont(self.font())
        font.setPointSize(9)
        p.setFont(font)

        # cielo realistico in alto, poi tribuna dello stadio, cartelloni e pedana
        rain = self._weather == WeatherCondition.PIOGGIA
        stand_h = min(self.CROWD_H, max(44, int((ground - 22) * 0.36)))
        sky_h = max(30, int(ground - 22 - stand_h - 10))
        sky = QLinearGradient(0, 0, 0, sky_h)
        if rain:
            sky.setColorAt(0.0, QColor("#475569"))
            sky.setColorAt(1.0, QColor("#94a3b8"))
        else:
            sky.setColorAt(0.0, QColor("#1d4ed8"))
            sky.setColorAt(0.65, QColor("#60a5fa"))
            sky.setColorAt(1.0, QColor("#dbeafe"))
        p.fillRect(0, 0, w, sky_h, QBrush(sky))
        # tribuna con folla (senza duplicare i cartelloni) e prato sullo sfondo
        crowd_pm = self._crowd(w)
        crowd_top = sky_h
        p.drawPixmap(0, crowd_top, crowd_pm, 0, 0, w, min(stand_h, crowd_pm.height() - 16))
        p.fillRect(0, int(ground - 32), w, 10, QColor("#2a6f37" if not rain else "#22572c"))
        p.fillRect(0, int(ground - 22), w, 22, QColor("#1e293b"))
        p.fillRect(0, int(ground - 22), w, 2, QColor("#94a3b8"))
        boards = [("TEF SPORT", "#b91c1c"), ("AURORA", "#1d4ed8"), ("VELOCITÀ", "#047857"), ("FASTLANE", "#c2410c")]
        for idx, k in enumerate(range(0, w, 110)):
            btxt, bcol = boards[idx % len(boards)]
            p.fillRect(k + 4, int(ground - 18), 100, 14, QColor(bcol))
            p.setPen(QColor("#f8fafc"))
            p.drawText(k + 4, int(ground - 18), 100, 14, Qt.AlignmentFlag.AlignCenter, btxt)

        surf = (self._surface or "").lower()
        blue = self._tier == CompetitionTier.INTERNAZIONALE or "mondo" in surf or "blu" in surf
        tartan_col = "#1f62b5" if blue else "#b34128"
        if self.kind == "lj":
            # rincorsa in tartan, asse di battuta in legno + plastilina rossa, fossa di sabbia stratificata
            p.fillRect(left, int(ground), int(sx(1.0) - left), int(h - ground), QColor(tartan_col))
            p.fillRect(left, int(ground), int(sx(1.0) - left), 3, QColor("#e2e8f0"))
            p.fillRect(int(sx(1.0)), int(ground - 3), int(right - sx(1.0)), int(h - ground + 3), QColor("#cbb27c"))
            p.fillRect(int(sx(1.0)), int(ground - 2), int(right - sx(1.0)), int(h - ground - 6), QColor("#e7d3a1"))
            p.fillRect(int(sx(1.0)), int(ground - 4), 4, int(h - ground + 4), QColor("#94a3b8"))  # bordo fossa
            p.fillRect(int(sx(0) - 3), int(ground - 2), 8, 5, QColor("#f8fafc"))  # asse di battuta
            p.fillRect(int(sx(0) + 5), int(ground - 2), 3, 4, QColor("#dc2626"))  # plastilina fallo
        else:
            # pedana di lancio + settore in erba rasata a bande
            band_w = max(24, int(2.0 * px))
            for bx in range(left, right, band_w):
                col = "#2f7d3d" if ((bx - left) // band_w) % 2 == 0 else "#358943"
                p.fillRect(bx, int(ground), min(band_w, right - bx), int(h - ground), QColor(col))
            p.setBrush(QColor("#cbd5e1"))
            p.setPen(QPen(QColor("#475569"), 2))
            p.drawEllipse(QPointF(sx(-1.0), ground + 9), 1.5 * px, 7)  # cerchio di lancio
            p.fillRect(int(sx(0.35)), int(ground - 3), 5, 5, QColor("#f8fafc"))  # fermapiedi
        p.fillRect(left, int(ground), right - left, 2, QColor("#f8fafc"))
        # righello delle misure
        step = 1 if self.kind == "lj" else 2
        start = int(math.ceil(max(1.0, self.lo * 0.7) / step) * step)
        p.setPen(QColor(15, 23, 42, 210) if self.kind == "lj" else QColor(248, 250, 252, 200))
        for mt in range(start, int(wx1), step):
            xx = sx(mt)
            p.drawLine(int(xx), int(ground), int(xx), int(ground + 9))
            p.drawText(int(xx - 16), int(ground + 24), 32, 14, Qt.AlignmentFlag.AlignCenter, f"{mt}m")

        cur = self.cur
        if cur is None:
            p.end()
            return
        t, dur = self.t, self.dur
        _ = dur
        d = cur["dist"]
        sprite_h = min(72.0, (ground - self.CROWD_H) * 0.56)
        kit = QColor("#f59e0b") if cur["player"] else QColor.fromHsv(zlib.crc32(cur["team"].encode()) % 360, 170, 215)
        skin = TrackRaceWidget._skin(cur["name"])

        def flag(x: float, label: str, col: str) -> None:
            p.setPen(QPen(QColor("#f8fafc"), 2))
            p.drawLine(int(x), int(ground), int(x), int(ground - 36))
            p.setBrush(QColor(col))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(QRectF(x, ground - 36, 62, 18), 3, 3)
            p.setPen(QColor("#0f172a"))
            p.drawText(int(x + 2), int(ground - 36), 58, 18, Qt.AlignmentFlag.AlignCenter, label)

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
                TrackRaceWidget._draw_runner(p, sx(x_m), ground - air * px * 0.55, sprite_h, 1.3 + 0.8 * s_, 1.0, kit, skin, False, cur["player"])
            else:
                # atterraggio nella sabbia con spruzzo e impronta
                TrackRaceWidget._draw_runner(p, sx(d), ground + 2, sprite_h, 0.3, 0.0, kit, skin, True, cur["player"], set_blend=0.2)
                age = t - jump_end
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor("#e7d3a1"))
                for k in range(12):
                    a_ = k * 0.55
                    r_ = min(1.0, age * 2.4)
                    p.drawEllipse(QPointF(sx(d) + math.cos(a_) * 26 * r_, ground - 4 - abs(math.sin(a_)) * 28 * r_), 2.5, 2.5)
                if age > 0.25:
                    flag(flag_x, label, colour)
        else:  # getto del peso
            wind_end, fly_end = 1.0, 2.0
            ring_x = sx(-1.0)
            if t < wind_end:
                spin = 2 * math.pi * 1.6 * t
                TrackRaceWidget._draw_runner(p, ring_x, ground, sprite_h, spin, 0.25 + 0.4 * t, kit, skin, t < 0.35, cur["player"], set_blend=0.35)
                p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor("#64748b"))
                p.drawEllipse(QPointF(ring_x + 7, ground - sprite_h * 0.78), 5.0, 5.0)
                p.setBrush(QColor("#e2e8f0"))
                p.drawEllipse(QPointF(ring_x + 5.5, ground - sprite_h * 0.78 - 1.5), 1.8, 1.8)
            else:
                TrackRaceWidget._draw_runner(p, ring_x, ground, sprite_h, 1.0, 0.1, kit, skin, False, cur["player"])
                s_ = min(1.0, (t - wind_end) / (fly_end - wind_end))
                bx = 0.3 + (d - 0.3) * s_
                apex = 3.2 + 0.14 * d
                by = 2.0 * (1 - s_) + 4.0 * apex * s_ * (1.0 - s_)
                p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                p.setPen(Qt.PenStyle.NoPen)
                # ombra sul prato sotto la sfera
                p.setBrush(QColor(0, 0, 0, 75))
                p.drawEllipse(QPointF(sx(bx), ground + 2), 6, 2)
                # sfera metallica con riflesso
                shot_pos = QPointF(sx(bx), ground - by * px * 0.6 - 4)
                p.setBrush(QColor("#475569"))
                p.drawEllipse(shot_pos, 5.5, 5.5)
                p.setBrush(QColor("#e2e8f0"))
                p.drawEllipse(QPointF(shot_pos.x() - 1.6, shot_pos.y() - 1.6), 2.0, 2.0)
                if t >= fly_end:
                    flag(flag_x, label, colour)

        # etichetta attuale
        p.setFont(font)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(9, 15, 29, 215))
        p.drawRoundedRect(QRectF(left, 8, 340, 22), 5, 5)
        p.setPen(QColor("#fbbf24" if cur["player"] else "#e2e8f0"))
        p.drawText(left + 8, 8, 324, 22, Qt.AlignmentFlag.AlignVCenter,
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
        from views.field_3d import Field3DSceneWidget  # import tardivo: field_3d usa FieldSceneWidget

        self.scene = Field3DSceneWidget()
        self.board = FieldBoardWidget()
        lay.addWidget(self.scene, stretch=3)
        lay.addWidget(self.board, stretch=2)
        self.board.finished.connect(self._board_done)
        self._step = 0
        self._acc = 0.0
        self._started = False
        self._done = False
        self._event = "Salto in Lungo"

    def set_environment(
        self,
        weather: Optional[WeatherCondition] = None,
        track_surface: str = "",
        tier: Optional[CompetitionTier] = None,
    ) -> None:
        self.scene.set_environment(weather, track_surface, tier)

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
        self.resize(1160, 740)
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
        self.godot_page = QWidget()
        self.godot_layout = QVBoxLayout(self.godot_page)
        self.godot_layout.setContentsMargins(0, 0, 0, 0)
        self.godot_status = QLabel("")
        self.godot_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.godot_status.setWordWrap(True)
        self.godot_status.setStyleSheet("font-size: 18px; font-weight: 700; color: #cbd5e1;")
        self.godot_layout.addWidget(self.godot_status)
        self.stack.addWidget(self.godot_page)
        self._godot = None  # QProcess del visualizzatore Godot, se la gara è in corso lì
        self._godot_container = None
        self._godot_killed = False
        self._godot_clock = QElapsedTimer()
        self._embed_attempts = 0
        self._embed_timer = QTimer(self)
        self._embed_timer.setInterval(40)
        self._embed_timer.timeout.connect(self._poll_godot_window)
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
        self.title.setText(f"{res.display_event_name} — gara {self._index + 1} di {total}")
        wind = "" if res.wind_ms is None else f"  |  Vento: {res.wind_ms:+.1f} m/s" + (" (non omologato)" if res.wind_illegal else "")
        self.info.setText(
            f"Meteo: {self.summary.weather.value}  |  Pista: {self.summary.track_surface}{wind}"
            f"  |  Atteggiamento: {res.attitude}"
        )
        self.podium.setText("")
        self.clock.setText("")
        self._race_done = False
        if self._start_godot(res):
            pass  # la gara si vede nel visualizzatore Godot; si prosegue quando si chiude
        elif is_field_event(res.event_name):
            self._show_internal_field(res)
        else:
            self._show_internal_race(res)
        self.btn_next.setEnabled(False)
        self.btn_skip.setEnabled(True)
        self._clock.start()
        self._timer.start()

    def _show_internal_field(self, res: EventResult) -> None:
        self.field.set_environment(self.summary.weather, self.summary.track_surface, self.summary.tier)
        self.field.set_race(res.event_name, res, self._seed())
        self.stack.setCurrentWidget(self.field)

    def _show_internal_race(self, res: EventResult) -> None:
        self.track.set_environment(
            self.summary.weather, self.summary.track_surface, self.summary.tier,
            self.summary.season_phase, self.summary.spectators,
        )
        self.track.set_race(res.event_name, res, self._seed())
        self.stack.setCurrentWidget(self.track)

    def _start_godot(self, res: EventResult) -> bool:
        """Prova a far vedere la gara nel visualizzatore Godot integrato nella finestra."""
        from views.godot_launcher import launch_race_viewer

        self._cleanup_godot_embed()
        size = (max(640, self.stack.width()), max(360, self.stack.height()))
        proc = launch_race_viewer(
            self.summary, res, self._on_godot_finished, parent=self, embed=True, size=size
        )
        if proc is None:
            return False
        self._godot = proc
        self._godot_killed = False
        self._godot_clock.start()
        self._embed_attempts = 0
        self.godot_status.setText(f"{res.event_name}: avvio visualizzatore 3D…")
        self.godot_status.show()
        self.stack.setCurrentWidget(self.godot_page)
        self._embed_timer.start()
        self.btn_pause.setEnabled(False)
        self.btn_speed.setEnabled(False)
        self.btn_view.setEnabled(False)
        return True

    def _poll_godot_window(self) -> None:
        if self._godot is None:
            self._embed_timer.stop()
            return
        self._embed_attempts += 1
        from views.godot_launcher import embed_hwnd, find_process_hwnd

        hwnd = find_process_hwnd(self._godot.processId())
        if hwnd:
            self._embed_timer.stop()
            container = embed_hwnd(hwnd, self.godot_page)
            if container is not None:
                self._godot_container = container
                self.godot_status.hide()
                self.godot_layout.addWidget(container, stretch=1)
                return
        if self._embed_attempts >= 150:
            self._embed_timer.stop()
            self.godot_status.setText(
                "Gara in corso nel visualizzatore 3D (Godot).\n"
                "Si chiude da solo a fine gara; puoi anche premere «Salta alla fine»."
            )

    def _cleanup_godot_embed(self) -> None:
        self._embed_timer.stop()
        if self._godot_container is not None:
            self.godot_layout.removeWidget(self._godot_container)
            self._godot_container.setParent(None)
            self._godot_container.deleteLater()
            self._godot_container = None
        self.godot_status.setText("")
        self.godot_status.show()

    def _on_godot_finished(self, exit_code: int = 0) -> None:
        if self._godot is None:
            return
        crashed = exit_code != 0 and not self._godot_killed and self._godot_clock.elapsed() < 5000
        self._godot = None
        self._cleanup_godot_embed()
        self.btn_pause.setEnabled(True)
        self.btn_speed.setEnabled(True)
        self.btn_view.setEnabled(True)
        if crashed and 0 <= self._index < len(self.summary.event_results):
            res = self.summary.event_results[self._index]
            if is_field_event(res.event_name):
                self._show_internal_field(res)
            else:
                self._show_internal_race(res)
            self._clock.start()
            return
        self._on_race_finished()

    def _current_widget(self):
        return self.stack.currentWidget()

    def _tick(self) -> None:
        dt = self._clock.restart() / 1000.0
        if self._paused or self._race_done or self._godot is not None:
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
            new.set_environment(
                self.summary.weather, self.summary.track_surface, self.summary.tier,
                self.summary.season_phase, self.summary.spectators,
            )
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
        if self._godot is not None:
            self._godot_killed = True
            self._godot.kill()  # chiude Godot: finished -> _on_godot_finished
            return
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

    def done(self, r: int) -> None:  # chiusura: ferma il timer e il visualizzatore Godot
        self._timer.stop()
        self._cleanup_godot_embed()
        if self._godot is not None:
            proc, self._godot = self._godot, None
            proc.kill()
            proc.waitForFinished(2000)
        super().done(r)
