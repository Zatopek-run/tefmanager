"""Vista 3D realistica delle corse in pista con stile televisivo.

Motore 3D software disegnato con QPainter: stadio completo con rettilineo, curve e rettilineo opposto,
tribune su due anelli con copertura e torri faro, cartelloni a bordo pista, blocchi di partenza,
portale d'arrivo con fotofinish e atleti con anatomia articolata e biomeccanica di corsa realistica.
Non richiede OpenGL né dipendenze esterne. Legge solo posizioni e tempi da `TrackRaceWidget`.
"""

from __future__ import annotations

import math
import random
import zlib
from typing import Dict, List, Optional, Sequence, Tuple

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QLinearGradient,
    QPainter,
    QPen,
    QPixmap,
    QPolygonF,
    QRadialGradient,
    QTransform,
)

from models.entities import CompetitionTier, SeasonPhase, WeatherCondition
from views.race_viewer import GUN_AT, TrackRaceWidget, _short, format_race_time

Vec = Tuple[float, float, float]

NEAR = 0.35  # piano di taglio vicino (m)
LANE_W = 1.22  # larghezza standard di una corsia (m)
R_IN = 34.0  # raggio interno della curva dello stadio (m)
CAM_BACK = 8.8  # camera davanti al capofila, ripresa frontale di tre quarti
CAM_SIDE = 7.4  # spostamento laterale fuori dalla corsia 8
CAM_HEIGHT = 2.85
FOV_DEG = 42.0

# Sponsor di fantasia per i cartelloni a bordo pista
SPONSORS = [
    ("TEF SPORT", "#b91c1c", "#f8fafc"),
    ("AURORA", "#1d4ed8", "#f8fafc"),
    ("VELOCITÀ", "#047857", "#f8fafc"),
    ("ATLETICA PIÙ", "#6d28d9", "#f8fafc"),
    ("FASTLANE", "#c2410c", "#f8fafc"),
    ("CRONO LAB", "#0f172a", "#38bdf8"),
]


# --------------------------------------------------------------------------- matematica 3D
def _sub(a: Vec, b: Vec) -> Vec:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a: Vec, b: Vec) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a: Vec, b: Vec) -> Vec:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(a: Vec) -> Vec:
    n = math.sqrt(_dot(a, a)) or 1.0
    return (a[0] / n, a[1] / n, a[2] / n)


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


class Camera:
    """Camera a foro stenopeico. Mondo: x lungo la pista, y in alto, z attraverso le corsie."""

    __slots__ = ("pos", "right", "up", "fwd", "f", "cx", "cy")

    def __init__(self, pos: Vec, target: Vec, fov_deg: float, width: int, height: int) -> None:
        self.pos = pos
        self.fwd = _norm(_sub(target, pos))
        self.right = _norm(_cross(self.fwd, (0.0, 1.0, 0.0)))
        self.up = _cross(self.right, self.fwd)
        self.f = (height / 2.0) / math.tan(math.radians(fov_deg) / 2.0)
        self.cx, self.cy = width / 2.0, height / 2.0

    def to_cam(self, p: Vec) -> Vec:
        d = _sub(p, self.pos)
        return (_dot(d, self.right), _dot(d, self.up), _dot(d, self.fwd))

    def proj(self, c: Vec) -> Tuple[float, float]:
        return (self.cx + self.f * c[0] / c[2], self.cy - self.f * c[1] / c[2])


def clip_near(pts: Sequence[Vec]) -> List[Vec]:
    """Taglia un poligono (in coordinate camera) contro il piano vicino: evita le inversioni
    di prospettiva quando un vertice sta dietro o troppo vicino alla camera."""
    out: List[Vec] = []
    n = len(pts)
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        a_in, b_in = a[2] >= NEAR, b[2] >= NEAR
        if a_in:
            out.append(a)
        if a_in != b_in:
            t = (NEAR - a[2]) / (b[2] - a[2])
            out.append((a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]), NEAR))
    return out


def clip_segment_near(a: Vec, b: Vec) -> Optional[Tuple[Vec, Vec]]:
    if a[2] < NEAR and b[2] < NEAR:
        return None
    if a[2] >= NEAR and b[2] >= NEAR:
        return a, b
    t = (NEAR - a[2]) / (b[2] - a[2])
    mid = (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]), NEAR)
    return (a, mid) if a[2] >= NEAR else (mid, b)


# --------------------------------------------------------------------------- texture statiche in cache
def make_crowd_strip(width: int = 384, height: int = 120, density: float = 0.85, dark: bool = False) -> QPixmap:
    """Gradinata con sedili, gradini in cemento e spettatori dettagliati per mappatura prospettica."""
    pm = QPixmap(width, height)
    base = QColor("#334155" if dark else "#475569")
    pm.fill(base)
    q = QPainter(pm)
    rng = random.Random(19 if not dark else 43)
    rows = 8
    row_h = height / rows
    skins = ("#f1c7a0", "#dfb086", "#b87e56", "#7a4e30", "#4b2e1e")
    for r in range(rows):
        y0 = int(r * row_h)
        rh = int(math.ceil(row_h))
        # gradino e ombra sotto la fila
        step_col = QColor("#3b495e" if r % 2 == 0 else "#46556b")
        if dark:
            step_col = step_col.darker(125)
        q.fillRect(0, y0, width, rh, step_col)
        q.fillRect(0, y0 + rh - 2, width, 2, QColor(15, 23, 42, 130))
        x = rng.randint(1, 5)
        while x < width - 4:
            if rng.random() > density:
                # sedile vuoto
                q.fillRect(x, y0 + 3, 6, rh - 5, QColor("#1e3a5f"))
                x += rng.randint(8, 12)
                continue
            # spettatore con torso, spalle, testa e a volte cappellino/sciarpa
            hue = rng.randint(0, 359)
            sat = rng.randint(35, 165)
            val = rng.randint(95, 215) if not dark else rng.randint(65, 165)
            shirt = QColor.fromHsv(hue, sat, val)
            skin = QColor(rng.choice(skins))
            if dark:
                skin = skin.darker(118)
            q.fillRect(x - 1, y0 + int(rh * 0.42), 8, int(rh * 0.52), shirt)
            q.fillRect(x + 1, y0 + int(rh * 0.14), 4, int(rh * 0.30), skin)
            if rng.random() < 0.28:
                q.fillRect(x, y0 + int(rh * 0.08), 6, 2, shirt.lighter(120))
            else:
                q.fillRect(x + 1, y0 + int(rh * 0.08), 4, 2, QColor("#1e293b" if rng.random() < 0.7 else "#78350f"))
            x += rng.randint(7, 10)
    # corrimano e scalette verticali
    for aisle in (width // 3, (2 * width) // 3):
        q.fillRect(aisle - 3, 0, 6, height, QColor("#64748b" if not dark else "#475569"))
        for r in range(rows):
            q.fillRect(aisle - 3, int(r * row_h), 6, 2, QColor("#94a3b8"))
    q.end()
    return pm


# --------------------------------------------------------------------------- vista 3D
class Track3DWidget(TrackRaceWidget):
    """Stessa gara della vista 2D, vista in prospettiva televisiva con stadio completo."""

    _board_cache: Dict[int, QPixmap] = {}
    _crowd_strip_cache: Dict[Tuple[bool, int], QPixmap] = {}
    _lane_num_cache: Dict[int, QPixmap] = {}
    _gantry_cache: Optional[QPixmap] = None
    _scoreboard_cache: Dict[str, QPixmap] = {}

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(420)

    # ---- geometria e stile stadio
    def _track_width(self) -> float:
        return max(1, len(self._runners)) * LANE_W

    def _lane_z(self, i: int) -> float:
        return (i + 0.5) * LANE_W

    def _is_blue_track(self) -> bool:
        surf = (self._surface or "").lower()
        return self._tier == CompetitionTier.INTERNAZIONALE or "mondo" in surf or "blu" in surf

    def _track_colors(self) -> Tuple[str, str, str]:
        """Ritorna (corsia pari, corsia dispari, zona esterna/lunetta)."""
        rain = self._weather == WeatherCondition.PIOGGIA
        if self._is_blue_track():
            c1, c2, c3 = ("#1a4f96", "#1e59a8", "#163f78") if rain else ("#1f62b5", "#246bc4", "#1b4f96")
        else:
            c1, c2, c3 = ("#8f3220", "#9c3925", "#7a2a1b") if rain else ("#b34128", "#be482e", "#9a3520")
        return c1, c2, c3

    def _crowd_density(self) -> float:
        if self._tier == CompetitionTier.INTERNAZIONALE:
            return 0.96
        if self._tier == CompetitionTier.NAZIONALE:
            return 0.88
        if self._tier == CompetitionTier.REGIONALE:
            return 0.72
        return 0.52

    def _crowd_pm(self, dark: bool) -> QPixmap:
        bucket = int(round(self._crowd_density() * 10))
        key = (dark, bucket)
        pm = self._crowd_strip_cache.get(key)
        if pm is None:
            pm = make_crowd_strip(384, 120, density=bucket / 10.0, dark=dark)
            self._crowd_strip_cache[key] = pm
        return pm

    def _make_camera(self, meters: Sequence[float], w: int, h: int) -> Camera:
        d = self._distance
        tw = self._track_width()
        leader = max(meters) if meters else 0.0
        mine = [m for m, r in zip(meters, self._runners) if r["s"].is_player]
        # insegue il capofila ma tiene vicino anche l'atleta del club se non troppo staccato
        if mine and leader - mine[0] < 12.0:
            focus = 0.65 * leader + 0.35 * mine[0]
        else:
            focus = leader
        # inquadratura morbida: dai blocchi fino al portale d'arrivo
        focus = _clamp(focus, 1.2, d + 2.5)
        start_blend = _clamp(self.race_time / 1.8, 0.0, 1.0)
        cam_back = _lerp(6.8, CAM_BACK, start_blend)
        cam_side = _lerp(5.8, CAM_SIDE, start_blend)
        cam_h = _lerp(2.35, CAM_HEIGHT, start_blend)
        # sul finale stringe leggermente per inquadrare bene lo scatto sul traguardo
        if focus > d - 10.0:
            fin_blend = _clamp((focus - (d - 10.0)) / 10.0, 0.0, 1.0)
            cam_back = _lerp(cam_back, 7.6, fin_blend)
            cam_side = _lerp(cam_side, 6.2, fin_blend)
        pos = (focus + cam_back, cam_h, tw + cam_side)
        target = (focus - 3.2, 0.92, tw * 0.44)
        return Camera(pos, target, FOV_DEG, w, h)

    # ---- primitive 3D
    def _poly(self, p: QPainter, cam: Camera, pts: Sequence[Vec], color) -> None:
        cs = clip_near([cam.to_cam(q) for q in pts])
        if len(cs) < 3:
            return
        p.setBrush(color if isinstance(color, QBrush) else QBrush(QColor(color)))
        p.drawPolygon(QPolygonF([QPointF(*cam.proj(c)) for c in cs]))

    def _line3(self, p: QPainter, cam: Camera, a: Vec, b: Vec, radius: float, color: QColor) -> None:
        seg = clip_segment_near(cam.to_cam(a), cam.to_cam(b))
        if seg is None:
            return
        ca, cb = seg
        (x0, y0), (x1, y1) = cam.proj(ca), cam.proj(cb)
        width = max(1.2, 2.0 * radius * cam.f / max(NEAR, (ca[2] + cb[2]) / 2.0))
        pen = QPen(color, width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawLine(QPointF(x0, y0), QPointF(x1, y1))
        p.setPen(Qt.PenStyle.NoPen)

    def _tapered_limb(
        self,
        p: QPainter,
        cam: Camera,
        a: Vec,
        b: Vec,
        r0: float,
        r1: float,
        color: QColor,
        highlight: Optional[QColor] = None,
    ) -> None:
        """Disegna un segmento muscolare rastremato in 3D con estremità arrotondate e luce direzionale."""
        seg = clip_segment_near(cam.to_cam(a), cam.to_cam(b))
        if seg is None:
            return
        ca, cb = seg
        ax, ay = cam.proj(ca)
        bx, by = cam.proj(cb)
        ra = max(1.2, r0 * cam.f / ca[2])
        rb = max(1.2, r1 * cam.f / cb[2])
        dx, dy = bx - ax, by - ay
        dist = math.hypot(dx, dy)
        if dist < 0.5:
            p.setBrush(color)
            p.drawEllipse(QPointF(ax, ay), ra, ra)
            return
        nx, ny = -dy / dist, dx / dist
        poly = QPolygonF(
            [
                QPointF(ax + nx * ra, ay + ny * ra),
                QPointF(bx + nx * rb, by + ny * rb),
                QPointF(bx - nx * rb, by - ny * rb),
                QPointF(ax - nx * ra, ay - ny * ra),
            ]
        )
        p.setBrush(color)
        p.drawPolygon(poly)
        p.drawEllipse(QPointF(ax, ay), ra, ra)
        p.drawEllipse(QPointF(bx, by), rb, rb)
        if highlight is not None and ra > 2.4:
            # sottile riflesso sul lato illuminato (superiore/frontale)
            side = -1.0 if ny > 0 else 1.0
            h_poly = QPolygonF(
                [
                    QPointF(ax + side * nx * ra * 0.15, ay + side * ny * ra * 0.15),
                    QPointF(bx + side * nx * rb * 0.15, by + side * ny * rb * 0.15),
                    QPointF(bx + side * nx * rb * 0.85, by + side * ny * rb * 0.85),
                    QPointF(ax + side * nx * ra * 0.85, ay + side * ny * ra * 0.85),
                ]
            )
            p.setBrush(highlight)
            p.drawPolygon(h_poly)

    def _textured_quad(self, p: QPainter, cam: Camera, corners: Sequence[Vec], pm: QPixmap) -> None:
        """Mappa una pixmap su un quadrilatero 3D (alto-sx, alto-dx, basso-dx, basso-sx)."""
        cs = [cam.to_cam(q) for q in corners]
        if any(c[2] < NEAR * 2 for c in cs):
            return
        dst = QPolygonF([QPointF(*cam.proj(c)) for c in cs])
        src = QPolygonF([QPointF(0, 0), QPointF(pm.width(), 0), QPointF(pm.width(), pm.height()), QPointF(0, pm.height())])
        t = QTransform()
        if not QTransform.quadToQuad(src, dst, t):
            return
        p.save()
        p.setTransform(t, True)
        p.drawPixmap(0, 0, pm)
        p.restore()

    def _board(self, idx: int) -> QPixmap:
        pm = self._board_cache.get(idx)
        if pm is None:
            text, col, fg = SPONSORS[idx % len(SPONSORS)]
            pm = QPixmap(256, 56)
            pm.fill(QColor(col))
            q = QPainter(pm)
            grad = QLinearGradient(0, 0, 0, 56)
            grad.setColorAt(0.0, QColor(col).lighter(115))
            grad.setColorAt(1.0, QColor(col).darker(120))
            q.fillRect(0, 0, 256, 56, grad)
            q.fillRect(0, 0, 256, 4, QColor("#e2e8f0"))
            q.fillRect(0, 52, 256, 4, QColor("#0f172a"))
            q.fillRect(0, 0, 5, 56, QColor("#1e293b"))
            q.setPen(QColor(fg))
            f = QFont("Arial", 20)
            f.setBold(True)
            q.setFont(f)
            q.drawText(QRectF(8, 4, 244, 48), Qt.AlignmentFlag.AlignCenter, text)
            q.end()
            self._board_cache[idx] = pm
        return pm

    def _lane_num_pm(self, num: int) -> QPixmap:
        pm = self._lane_num_cache.get(num)
        if pm is None:
            pm = QPixmap(64, 64)
            pm.fill(Qt.GlobalColor.transparent)
            q = QPainter(pm)
            q.setPen(QColor(248, 250, 252, 220))
            f = QFont("Arial", 42)
            f.setBold(True)
            q.setFont(f)
            q.drawText(QRectF(0, 0, 64, 64), Qt.AlignmentFlag.AlignCenter, str(num))
            q.end()
            self._lane_num_cache[num] = pm
        return pm

    def _gantry_pm(self) -> QPixmap:
        if Track3DWidget._gantry_cache is None:
            pm = QPixmap(320, 48)
            pm.fill(QColor("#0f172a"))
            q = QPainter(pm)
            q.fillRect(0, 0, 320, 5, QColor("#fbbf24"))
            q.fillRect(0, 43, 320, 5, QColor("#fbbf24"))
            q.setPen(QColor("#f8fafc"))
            f = QFont("Arial", 21)
            f.setBold(True)
            q.setFont(f)
            q.drawText(QRectF(0, 4, 320, 40), Qt.AlignmentFlag.AlignCenter, "ARRIVO")
            q.end()
            Track3DWidget._gantry_cache = pm
        return Track3DWidget._gantry_cache

    def _scoreboard_pm(self, clock_txt: str) -> QPixmap:
        # memorizza per decimo di secondo per non ridisegnare inutilmente ogni frame identico
        pm = self._scoreboard_cache.get(clock_txt)
        if pm is None:
            if len(self._scoreboard_cache) > 8:
                self._scoreboard_cache.clear()
            pm = QPixmap(280, 96)
            pm.fill(QColor("#090f1d"))
            q = QPainter(pm)
            q.setPen(QPen(QColor("#334155"), 4))
            q.drawRect(2, 2, 276, 92)
            q.fillRect(6, 6, 268, 24, QColor("#1e293b"))
            f_hdr = QFont("Arial", 11)
            f_hdr.setBold(True)
            q.setFont(f_hdr)
            q.setPen(QColor("#fbbf24"))
            q.drawText(QRectF(8, 6, 264, 24), Qt.AlignmentFlag.AlignCenter, self._event.upper())
            f_clk = QFont("Arial", 32)
            f_clk.setBold(True)
            q.setFont(f_clk)
            q.setPen(QColor("#f8fafc"))
            q.drawText(QRectF(8, 32, 264, 58), Qt.AlignmentFlag.AlignCenter, clock_txt)
            q.end()
            self._scoreboard_cache[clock_txt] = pm
        return pm

    # ---- scenografia stadio completo
    def _draw_sky(self, p: QPainter, cam: Camera, w: int, h: int) -> None:
        # proietta l'orizzonte reale per allineare il gradiente di cielo e terreno
        hz_cam = (0.0, 0.0, 1.0)  # direzione approssimativa dell'orizzonte
        _ = hz_cam
        rain = self._weather == WeatherCondition.PIOGGIA
        hot = self._weather == WeatherCondition.CALDO
        indoor = self._season_phase == SeasonPhase.INDOOR

        sky = QLinearGradient(0, 0, 0, h * 0.56)
        if indoor:
            sky.setColorAt(0.0, QColor("#0f172a"))
            sky.setColorAt(1.0, QColor("#1e293b"))
        elif rain:
            sky.setColorAt(0.0, QColor("#475569"))
            sky.setColorAt(0.6, QColor("#64748b"))
            sky.setColorAt(1.0, QColor("#94a3b8"))
        elif hot:
            sky.setColorAt(0.0, QColor("#1d4ed8"))
            sky.setColorAt(0.65, QColor("#60a5fa"))
            sky.setColorAt(1.0, QColor("#fde68a"))
        else:
            sky.setColorAt(0.0, QColor("#2563eb"))
            sky.setColorAt(0.62, QColor("#60a5fa"))
            sky.setColorAt(1.0, QColor("#dbeafe"))
        p.fillRect(0, 0, w, h, QBrush(sky))
        p.setPen(Qt.PenStyle.NoPen)

        # terreno lontano oltre lo stadio
        p.fillRect(0, int(h * 0.42), w, int(h * 0.58), QColor("#1f4d2b" if not rain else "#1a3c24"))

        if not indoor and not rain:
            # nuvole morbide e bagliore solare
            sun = QRadialGradient(w * 0.16, h * 0.14, w * 0.22)
            sun.setColorAt(0.0, QColor(255, 250, 220, 140))
            sun.setColorAt(1.0, QColor(255, 250, 220, 0))
            p.setBrush(QBrush(sun))
            p.drawEllipse(QPointF(w * 0.16, h * 0.14), w * 0.22, w * 0.22)
            p.setBrush(QColor(255, 255, 255, 45))
            for cx, cy, rx, ry in ((0.42, 0.12, 95, 18), (0.68, 0.09, 120, 22), (0.85, 0.15, 80, 16)):
                p.drawEllipse(QPointF(w * cx, h * cy), rx, ry)

    def _draw_stadium_bowl(self, p: QPainter, cam: Camera, w: int) -> None:
        d = self._distance
        tw = self._track_width()
        cam_x = cam.pos[0]
        xa = max(-16.0, cam_x - 165.0)
        xb = min(d + 20.0, cam_x + 35.0)
        rain = self._weather == WeatherCondition.PIOGGIA
        big_stadium = self._tier in (CompetitionTier.NAZIONALE, CompetitionTier.INTERNAZIONALE)
        crowd_far = self._crowd_pm(dark=rain)

        # ---- tribuna opposta (al di là del prato e del rettilineo opposto, z = -2*R_IN - tw - 4)
        z_back = -2.0 * R_IN - tw - 4.0
        seg = 22.0
        s_xa = max(-24.0, cam_x - 175.0)
        s_xb = min(d + 24.0, cam_x + 45.0)
        x = math.floor(s_xa / seg) * seg
        while x < s_xb:
            x0, x1 = x - 0.15, x + seg + 0.15
            # muretto di bordo tribuna
            self._poly(p, cam, [(x0, 0.0, z_back), (x1, 0.0, z_back), (x1, 1.4, z_back), (x0, 1.4, z_back)], "#64748b")
            # primo anello continuo (nessuno spiraglio di cielo)
            q1 = [(x0, 1.4, z_back), (x1, 1.4, z_back), (x1, 8.2, z_back - 12.0), (x0, 8.2, z_back - 12.0)]
            self._poly(p, cam, q1, "#475569")
            self._textured_quad(p, cam, [q1[3], q1[2], q1[1], q1[0]], crowd_far)
            if big_stadium:
                # fascia intermedia + secondo anello + parete posteriore e tettoia raccordata
                self._poly(
                    p, cam,
                    [(x0, 8.2, z_back - 12.0), (x1, 8.2, z_back - 12.0), (x1, 9.6, z_back - 13.5), (x0, 9.6, z_back - 13.5)],
                    "#334155",
                )
                q2 = [(x0, 9.6, z_back - 13.5), (x1, 9.6, z_back - 13.5), (x1, 18.5, z_back - 26.0), (x0, 18.5, z_back - 26.0)]
                self._poly(p, cam, q2, "#3b495e")
                self._textured_quad(p, cam, [q2[3], q2[2], q2[1], q2[0]], crowd_far)
                # parete di fondo tra gradinata e tettoia (nessuno spiraglio vuoto)
                self._poly(
                    p, cam,
                    [(x0, 18.5, z_back - 26.0), (x1, 18.5, z_back - 26.0), (x1, 21.2, z_back - 27.5), (x0, 21.2, z_back - 27.5)],
                    "#1e293b",
                )
                # tettoia metallica dello stadio
                self._poly(
                    p, cam,
                    [(x0, 21.2, z_back - 27.5), (x1, 21.2, z_back - 27.5), (x1, 19.6, z_back - 7.0), (x0, 19.6, z_back - 7.0)],
                    "#cbd5e1" if not rain else "#64748b",
                )
                self._poly(
                    p, cam,
                    [(x0, 19.6, z_back - 7.0), (x1, 19.6, z_back - 7.0), (x1, 18.9, z_back - 7.0), (x0, 18.9, z_back - 7.0)],
                    "#0f172a",
                )
            else:
                # cornice superiore tribuna locale
                self._poly(
                    p, cam,
                    [(x0, 8.2, z_back - 12.0), (x1, 8.2, z_back - 12.0), (x1, 9.2, z_back - 12.2), (x0, 9.2, z_back - 12.2)],
                    "#94a3b8",
                )
            x += seg

        # torri faro lungo la tribuna opposta
        for fx in (-20.0, 40.0, 100.0):
            if cam_x - 170.0 <= fx <= cam_x + 40.0:
                top_y = 26.5 if big_stadium else 16.5
                fz = z_back - (25.0 if big_stadium else 12.5)
                self._line3(p, cam, (fx, 9.0, fz), (fx, top_y, fz + 2.0), 0.32, QColor("#64748b"))
                self._poly(
                    p, cam,
                    [(fx - 2.8, top_y - 1.3, fz + 2.1), (fx + 2.8, top_y - 1.3, fz + 2.1),
                     (fx + 2.8, top_y + 1.5, fz + 2.1), (fx - 2.8, top_y + 1.5, fz + 2.1)],
                    "#1e293b",
                )
                self._poly(
                    p, cam,
                    [(fx - 2.4, top_y - 1.0, fz + 2.2), (fx + 2.4, top_y - 1.0, fz + 2.2),
                     (fx + 2.4, top_y + 1.2, fz + 2.2), (fx - 2.4, top_y + 1.2, fz + 2.2)],
                    "#fef9c3",
                )

        # ---- curva di testata dietro la partenza (raccordata esattamente con l'ovale!)
        cx_start = -16.0
        if cam_x - 165.0 < cx_start + 5.0:
            steps = 8
            r_stand_in = R_IN + tw + 4.0
            r_stand_out = r_stand_in + (22.0 if big_stadium else 12.0)
            y_top = 16.5 if big_stadium else 8.2
            for k in range(steps):
                a0 = math.pi * 0.5 + (math.pi * k) / steps
                a1 = math.pi * 0.5 + (math.pi * (k + 1)) / steps
                p0 = (cx_start + r_stand_in * math.cos(a0), 1.2, -R_IN + r_stand_in * math.sin(a0))
                p1 = (cx_start + r_stand_in * math.cos(a1), 1.2, -R_IN + r_stand_in * math.sin(a1))
                p2 = (cx_start + r_stand_out * math.cos(a1), y_top, -R_IN + r_stand_out * math.sin(a1))
                p3 = (cx_start + r_stand_out * math.cos(a0), y_top, -R_IN + r_stand_out * math.sin(a0))
                # muretto basso
                w0 = (p0[0], 0.0, p0[2])
                w1 = (p1[0], 0.0, p1[2])
                self._poly(p, cam, [w0, w1, p1, p0], "#64748b")
                self._poly(p, cam, [p0, p1, p2, p3], "#3f4d63")
                self._textured_quad(p, cam, [p3, p2, p1, p0], crowd_far)
                if big_stadium:
                    # copertura curva
                    r_roof = r_stand_in + 6.0
                    rf0 = (cx_start + r_stand_out * math.cos(a0), 19.0, -R_IN + r_stand_out * math.sin(a0))
                    rf1 = (cx_start + r_stand_out * math.cos(a1), 19.0, -R_IN + r_stand_out * math.sin(a1))
                    rf2 = (cx_start + r_roof * math.cos(a1), 18.0, -R_IN + r_roof * math.sin(a1))
                    rf3 = (cx_start + r_roof * math.cos(a0), 18.0, -R_IN + r_roof * math.sin(a0))
                    self._poly(p, cam, [rf0, rf1, rf2, rf3], "#94a3b8")

            # maxischermo dello stadio in curva
            sb_a = math.pi * 1.12
            sb_r = r_stand_in + 13.0
            sx0 = cx_start + sb_r * math.cos(sb_a - 0.14)
            sz0 = -R_IN + sb_r * math.sin(sb_a - 0.14)
            sx1 = cx_start + sb_r * math.cos(sb_a + 0.14)
            sz1 = -R_IN + sb_r * math.sin(sb_a + 0.14)
            y_lo = 13.0 if big_stadium else 7.5
            y_hi = y_lo + 6.5
            self._poly(p, cam, [(sx0, y_lo, sz0), (sx1, y_lo, sz1), (sx1, y_hi, sz1), (sx0, y_hi, sz0)], "#0f172a")
            clk = format_race_time(self.race_clock)
            self._textured_quad(p, cam, [(sx0, y_hi, sz0), (sx1, y_hi, sz1), (sx1, y_lo, sz1), (sx0, y_lo, sz0)], self._scoreboard_pm(clk))

        # ---- prato interno (campo in erba a bande + lunetta)
        band = 10.0
        x = math.floor(xa / band) * band
        while x < xb:
            light = int(x // band) % 2 == 0
            g = "#2e7a3b" if light else "#358943"
            if rain:
                g = QColor(g).darker(118)
            self._poly(p, cam, [(x, 0.0, -2.0 * R_IN), (x + band + 0.1, 0.0, -2.0 * R_IN), (x + band + 0.1, 0.0, 0.0), (x, 0.0, 0.0)], g)
            x += band
        # linee bianche del campo interno (campo centrale)
        self._poly(p, cam, [(max(0.0, xa), 0.008, -56.0), (min(d, xb), 0.008, -56.0), (min(d, xb), 0.008, -55.7), (max(0.0, xa), 0.008, -55.7)], QColor(248, 250, 252, 110))
        self._poly(p, cam, [(max(0.0, xa), 0.008, -10.3), (min(d, xb), 0.008, -10.3), (min(d, xb), 0.008, -10.0), (max(0.0, xa), 0.008, -10.0)], QColor(248, 250, 252, 110))
        # fossa della sabbia nell'interno pista per dare profondità realistica
        if xa < 60.0 and xb > 10.0:
            self._poly(p, cam, [(18.0, 0.01, -7.2), (27.0, 0.01, -7.2), (27.0, 0.01, -4.4), (18.0, 0.01, -4.4)], "#d9c293")
            self._poly(p, cam, [(-4.0, 0.01, -6.2), (18.0, 0.01, -6.2), (18.0, 0.01, -5.0), (-4.0, 0.01, -5.0)], self._track_colors()[2])

        # fascia esterna alla corsia 8 (dove scorrono i cartelloni / camera)
        self._poly(p, cam, [(xa - 4.0, 0.0, tw), (xb + 16.0, 0.0, tw), (xb + 16.0, 0.0, tw + 24.0), (xa - 4.0, 0.0, tw + 24.0)], "#296935" if not rain else "#20532a")

        # ---- curva pista e rettilineo opposto (danno la forma di un vero stadio ovale)
        c1, c2, c3 = self._track_colors()
        # rettilineo opposto lontano
        self._poly(p, cam, [(xa, 0.0, -2.0 * R_IN - tw), (xb, 0.0, -2.0 * R_IN - tw), (xb, 0.0, -2.0 * R_IN), (xa, 0.0, -2.0 * R_IN)], c3)
        self._poly(p, cam, [(xa, 0.01, -2.0 * R_IN - 0.15), (xb, 0.01, -2.0 * R_IN - 0.15), (xb, 0.01, -2.0 * R_IN), (xa, 0.01, -2.0 * R_IN)], "#e2e8f0")

        # curva dietro la partenza (visibile quando la camera guarda da x>0 verso x<0)
        if cam_x - 165.0 < cx_start + 2.0:
            n_seg = 10
            for k in range(n_seg):
                a0 = math.pi * 0.5 + (math.pi * k) / n_seg
                a1 = math.pi * 0.5 + (math.pi * (k + 1)) / n_seg
                # prato della lunetta (D-zone)
                self._poly(
                    p, cam,
                    [
                        (cx_start, 0.0, -R_IN),
                        (cx_start + R_IN * math.cos(a0), 0.0, -R_IN + R_IN * math.sin(a0)),
                        (cx_start + R_IN * math.cos(a1), 0.0, -R_IN + R_IN * math.sin(a1)),
                    ],
                    "#2e7a3b" if not rain else "#225a2c",
                )
                # pista in curva
                self._poly(
                    p, cam,
                    [
                        (cx_start + R_IN * math.cos(a0), 0.002, -R_IN + R_IN * math.sin(a0)),
                        (cx_start + (R_IN + tw) * math.cos(a0), 0.002, -R_IN + (R_IN + tw) * math.sin(a0)),
                        (cx_start + (R_IN + tw) * math.cos(a1), 0.002, -R_IN + (R_IN + tw) * math.sin(a1)),
                        (cx_start + R_IN * math.cos(a1), 0.002, -R_IN + R_IN * math.sin(a1)),
                    ],
                    c1 if k % 2 == 0 else c2,
                )
                # cordolo bianco interno in curva
                self._poly(
                    p, cam,
                    [
                        (cx_start + (R_IN - 0.2) * math.cos(a0), 0.01, -R_IN + (R_IN - 0.2) * math.sin(a0)),
                        (cx_start + R_IN * math.cos(a0), 0.01, -R_IN + R_IN * math.sin(a0)),
                        (cx_start + R_IN * math.cos(a1), 0.01, -R_IN + R_IN * math.sin(a1)),
                        (cx_start + (R_IN - 0.2) * math.cos(a1), 0.01, -R_IN + (R_IN - 0.2) * math.sin(a1)),
                    ],
                    "#f1f5f9",
                )

        # ---- corsie del rettilineo principale con leggera alternanza tonale realistica
        n = len(self._runners)
        for i in range(n):
            z0, z1 = i * LANE_W, (i + 1) * LANE_W
            col = c1 if i % 2 == 0 else c2
            self._poly(p, cam, [(xa, 0.004, z0), (xb, 0.004, z0), (xb, 0.004, z1), (xa, 0.004, z1)], col)

        # cordolo interno in alluminio bianco (leggero rilievo 3D)
        self._poly(p, cam, [(xa, 0.0, -0.22), (xb, 0.0, -0.22), (xb, 0.06, -0.22), (xa, 0.06, -0.22)], "#cbd5e1")
        self._poly(p, cam, [(xa, 0.06, -0.22), (xb, 0.06, -0.22), (xb, 0.06, 0.0), (xa, 0.06, 0.0)], "#f8fafc")

    def _draw_track_marks(self, p: QPainter, cam: Camera) -> None:
        d = self._distance
        n = len(self._runners)
        tw = self._track_width()
        cam_x = cam.pos[0]
        xa, xb = max(-16.0, cam_x - 165.0), min(d + 20.0, cam_x + 30.0)

        # linee delle corsie (5 cm)
        for i in range(n + 1):
            z = i * LANE_W
            self._poly(p, cam, [(xa, 0.012, z - 0.025), (xb, 0.012, z - 0.025), (xb, 0.012, z + 0.025), (xa, 0.012, z + 0.025)], "#f8fafc")

        # tacche trasversali
        step = 10 if d <= 400 else 50
        first = int(max(10, math.floor(xa / step) * step))
        for mt in range(first, int(min(d - 1, xb)) + 1, step):
            self._poly(p, cam, [(mt - 0.03, 0.011, 0.0), (mt + 0.03, 0.011, 0.0), (mt + 0.03, 0.011, tw), (mt - 0.03, 0.011, tw)], QColor(248, 250, 252, 85))

        # linea di partenza e numeri di corsia verniciati sulla pista
        if xa <= 1.0:
            self._poly(p, cam, [(-0.04, 0.013, 0.0), (0.04, 0.013, 0.0), (0.04, 0.013, tw), (-0.04, 0.013, tw)], "#ffffff")
            for i in range(n):
                zc = self._lane_z(i)
                # numero corsia davanti alla linea di partenza
                self._textured_quad(
                    p, cam,
                    [(0.45, 0.014, zc - 0.32), (1.05, 0.014, zc - 0.32), (1.05, 0.014, zc + 0.32), (0.45, 0.014, zc + 0.32)],
                    self._lane_num_pm(i + 1),
                )

        # zone cambio staffetta: linee gialle nette ai bordi dei 20m (più realistiche e nitide su pista blu/rossa)
        if self._event.startswith("4x"):
            for k in (1, 2, 3):
                cx = d * k / 4.0
                if xa <= cx + 10 and xb >= cx - 10:
                    self._poly(p, cam, [(cx - 10, 0.013, 0.0), (cx + 10, 0.013, 0.0), (cx + 10, 0.013, tw), (cx - 10, 0.013, tw)], QColor(250, 204, 21, 24))
                    for zx in (cx - 10.0, cx + 10.0):
                        self._poly(p, cam, [(zx - 0.06, 0.014, 0.0), (zx + 0.06, 0.014, 0.0), (zx + 0.06, 0.014, tw), (zx - 0.06, 0.014, tw)], "#facc15")

        # linea del traguardo bianca + scacchiera bicolore al centro
        if xb >= d - 0.5 and xa <= d + 1.0:
            self._poly(p, cam, [(d - 0.04, 0.014, 0.0), (d + 0.04, 0.014, 0.0), (d + 0.04, 0.014, tw), (d - 0.04, 0.014, tw)], "#ffffff")
            cells = max(4, int(tw / 0.28))
            cw = tw / cells
            for j in range(cells):
                for k in range(2):
                    x0 = d + 0.04 + k * 0.24
                    col = "#f8fafc" if (j + k) % 2 == 0 else "#0f172a"
                    self._poly(p, cam, [(x0, 0.014, j * cw), (x0 + 0.24, 0.014, j * cw), (x0 + 0.24, 0.014, (j + 1) * cw), (x0, 0.014, (j + 1) * cw)], col)

    def _draw_blocks_and_boards(self, p: QPainter, cam: Camera) -> None:
        d = self._distance
        n = len(self._runners)
        tw = self._track_width()
        cam_x = cam.pos[0]

        # blocchi di partenza 3D (binario centrale + due pedali inclinati)
        if cam_x > -4.0 and cam_x < 45.0:
            for i in range(n):
                z = self._lane_z(i)
                # binario centrale in alluminio
                self._poly(p, cam, [(-0.85, 0.02, z - 0.04), (-0.15, 0.02, z - 0.04), (-0.15, 0.05, z + 0.04), (-0.85, 0.05, z + 0.04)], "#94a3b8")
                # pedale anteriore e posteriore
                for bx in (-0.36, -0.66):
                    self._poly(p, cam, [(bx - 0.12, 0.02, z - 0.18), (bx, 0.14, z - 0.18), (bx, 0.14, z + 0.18), (bx - 0.12, 0.02, z + 0.18)], "#1e293b")
                    self._poly(p, cam, [(bx - 0.02, 0.14, z - 0.18), (bx + 0.02, 0.14, z - 0.18), (bx + 0.02, 0.14, z + 0.18), (bx - 0.02, 0.14, z + 0.18)], "#e2e8f0")

        # cartelloni LED lungo il bordo interno (tra corsia 1 e prato, z = -1.35)
        seg = 6.0
        x = math.floor(max(-16.0, cam_x - 135.0) / seg) * seg
        while x < min(d + 16.0, cam_x + 20.0):
            pm = self._board(int(x // seg))
            self._textured_quad(
                p, cam,
                [(x, 0.85, -1.35), (x + seg - 0.15, 0.85, -1.35), (x + seg - 0.15, 0.04, -1.35), (x, 0.04, -1.35)],
                pm,
            )
            x += seg

        # portale d'arrivo e torretta cronometro (visibili solo quando ci si avvicina o al traguardo)
        if cam_x >= d - 95.0:
            # pali laterali e traversa reticolare
            for z in (-0.85, tw + 0.85):
                self._line3(p, cam, (d, 0.0, z), (d, 5.2, z), 0.13, QColor("#e2e8f0"))
                self._line3(p, cam, (d + 0.35, 0.0, z), (d + 0.35, 5.2, z), 0.07, QColor("#94a3b8"))
            self._line3(p, cam, (d, 5.2, -0.85), (d, 5.2, tw + 0.85), 0.15, QColor("#e2e8f0"))
            self._textured_quad(
                p, cam,
                [(d, 5.15, tw + 0.85), (d, 5.15, -0.85), (d, 4.25, -0.85), (d, 4.25, tw + 0.85)],
                self._gantry_pm(),
            )
            # palo fotofinish a bordo pista
            self._poly(p, cam, [(d - 0.35, 0.0, -0.75), (d + 0.35, 0.0, -0.75), (d + 0.35, 0.95, -0.75), (d - 0.35, 0.95, -0.75)], "#1e293b")
            self._poly(p, cam, [(d - 0.25, 0.95, -0.75), (d + 0.25, 0.95, -0.75), (d + 0.25, 1.35, -0.75), (d - 0.25, 1.35, -0.75)], "#fbbf24")

        # nastro sul traguardo (si spezza al passaggio del primo)
        if not any(self._has_finished(r) for r in self._runners):
            self._line3(p, cam, (d, 1.08, 0.0), (d, 1.08, tw), 0.025, QColor("#ef4444"))
        elif self.race_time < self._winner_time + 1.5 * self._scale:
            # lembi del nastro spezzato ai lati
            self._line3(p, cam, (d, 1.08, 0.0), (d + 0.8, 0.72, 0.9), 0.022, QColor("#ef4444"))
            self._line3(p, cam, (d, 1.08, tw), (d + 0.8, 0.72, tw - 0.9), 0.022, QColor("#ef4444"))

    # ---- atleti 3D anatomici e biomeccanica
    def _draw_athlete(
        self,
        p: QPainter,
        cam: Camera,
        x: float,
        z: float,
        phase: float,
        ratio: float,
        kit: QColor,
        skin: QColor,
        is_player: bool,
        name: str,
        bib: int,
        has_baton: bool,
    ) -> None:
        d = self._distance
        # 1) stato posturale: blocchi ("Ai vostri posti" -> "Pronti") / accelerazione / corsa / tuffo finale
        t_anim = self._t
        if self.race_time <= 0.0:
            # fase 1: ai vostri posti -> fase 2: pronti (fianchi sollevati, spalle sopra le mani dietro la linea)
            set_blend = _clamp((t_anim - GUN_AT * 0.45) / 0.38, 0.0, 1.0)
            hip_h = _lerp(0.46, 0.78, set_blend)
            hip_x = _lerp(x - 0.58, x - 0.50, set_blend)
            sh_x = _lerp(x - 0.16, x - 0.12, set_blend)
            sh_y = _lerp(0.54, 0.65, set_blend)
            lean = math.atan2(sh_x - hip_x, sh_y - hip_h)
            crouch_mode = True
            drive_blend = 0.0
        else:
            crouch_mode = False
            drive_blend = _clamp(self.race_time / 1.6, 0.0, 1.0)
            finish_dip = 0.24 * _clamp((x - (d - 1.4)) / 1.4, 0.0, 1.0) if x <= d + 0.2 else 0.0
            lean = _lerp(0.66, 0.14 + 0.14 * ratio, drive_blend) + finish_dip
            bounce = 0.045 * abs(math.sin(phase)) * ratio
            hip_h = 0.93 + bounce
            hip_x = x

        # ombra morbida sul tartan (si allunga leggermente in corsa)
        sh_pts = [
            (hip_x + 0.44 * math.cos(a), 0.018, z + 0.24 * math.sin(a))
            for a in (i * math.pi / 5 for i in range(10))
        ]
        self._poly(p, cam, sh_pts, QColor(0, 0, 0, 72))

        # torsione spalle-bacino sincronizzata con la falcata
        twist = 0.0 if crouch_mode else 0.16 * ratio * math.sin(phase)
        s_lean, c_lean = math.sin(lean), math.cos(lean)
        hip = (hip_x, hip_h, z)
        torso_len = 0.56
        if crouch_mode:
            sh_mid = (sh_x, sh_y, z)
            neck_top = (sh_mid[0] + 0.055, sh_mid[1] + 0.015, z)
            head = (neck_top[0] + 0.05, neck_top[1] - 0.015, z)
        else:
            sh_mid = (hip_x + torso_len * s_lean, hip_h + torso_len * c_lean, z)
            neck_top = (sh_mid[0] + 0.11 * s_lean, sh_mid[1] + 0.11 * c_lean, z)
            head = (neck_top[0] + 0.11 * s_lean, neck_top[1] + 0.11 * c_lean, z)

        shorts = QColor("#0f172a")
        spike_col = kit.lighter(135) if is_player else QColor("#f8fafc")
        amp = 0.50 + 0.58 * ratio
        near_sign = 1.0 if cam.pos[2] > z else -1.0

        def leg_chain(origin: Vec, thigh_a: float, knee_flex: float) -> Tuple[Vec, Vec, Vec]:
            # angolo 0 = verticale verso il basso; + = avanti (+x)
            l1, l2 = 0.46, 0.45
            knee = (origin[0] + l1 * math.sin(thigh_a), origin[1] - l1 * math.cos(thigh_a), origin[2])
            shin_a = thigh_a - knee_flex
            ankle = (knee[0] + l2 * math.sin(shin_a), max(0.03, knee[1] - l2 * math.cos(shin_a)), origin[2])
            toe = (ankle[0] + 0.16 * math.cos(shin_a * 0.4), max(0.02, ankle[1] - 0.03), origin[2])
            return knee, ankle, toe

        def arm_chain(origin: Vec, upper_a: float, elbow_bend: float) -> Tuple[Vec, Vec]:
            l1, l2 = 0.30, 0.27
            elbow = (origin[0] + l1 * math.sin(upper_a), origin[1] - l1 * math.cos(upper_a), origin[2])
            fore_a = upper_a + elbow_bend
            hand = (elbow[0] + l2 * math.sin(fore_a), elbow[1] - l2 * math.cos(fore_a), origin[2])
            return elbow, hand

        def draw_side(side: float) -> None:
            is_near = side == near_sign
            shade_skin = skin if is_near else skin.darker(132)
            hl_skin = skin.lighter(115) if is_near else None
            shade_shorts = shorts if is_near else shorts.darker(130)
            ph = phase + (0.0 if side > 0 else math.pi)
            hip_s = (hip[0], hip[1] - 0.02, hip[2] + side * 0.105)
            sh_s = (
                sh_mid[0] - side * 0.14 * twist,
                sh_mid[1] - 0.03,
                sh_mid[2] + side * 0.195,
            )

            if crouch_mode:
                # piedi sui due pedali dei blocchi, mani appoggiate a terra dietro la linea!
                if side > 0:
                    knee = (x - 0.24, _lerp(0.24, 0.46, set_blend), hip_s[2])
                    ankle = (x - 0.42, 0.13, hip_s[2])
                    toe = (x - 0.34, 0.04, hip_s[2])
                else:
                    knee = (x - 0.36, _lerp(0.11, 0.32, set_blend), hip_s[2])
                    ankle = (x - 0.70, 0.13, hip_s[2])
                    toe = (x - 0.62, 0.04, hip_s[2])
                elbow = (x - 0.06, (sh_s[1] + 0.04) * 0.52, sh_s[2])
                hand = (x - 0.07, 0.03, sh_s[2])
            else:
                thigh_a = amp * math.sin(ph) + 0.15 * (1.0 - drive_blend)
                # flessione del ginocchio in fase di recupero (quando la gamba torna avanti)
                knee_flex = 0.28 + 1.55 * ratio * max(0.0, math.sin(ph + 1.25))
                knee, ankle, toe = leg_chain(hip_s, thigh_a, knee_flex)
                arm_a = -amp * 1.15 * math.sin(ph)
                elbow, hand = arm_chain(sh_s, arm_a, 1.35 + 0.35 * max(0.0, math.sin(ph)))

            # coscia: pantaloncino nella metà superiore, quadricipite sotto
            mid_thigh = (_lerp(hip_s[0], knee[0], 0.55), _lerp(hip_s[1], knee[1], 0.55), hip_s[2])
            self._tapered_limb(p, cam, hip_s, knee, 0.088, 0.060, shade_skin, hl_skin)
            self._tapered_limb(p, cam, hip_s, mid_thigh, 0.102, 0.086, shade_shorts)
            # polpaccio con muscolatura e scarpa chiodata
            calf_mid = (_lerp(knee[0], ankle[0], 0.38), _lerp(knee[1], ankle[1], 0.38), knee[2])
            self._tapered_limb(p, cam, knee, calf_mid, 0.060, 0.066, shade_skin, hl_skin)
            self._tapered_limb(p, cam, calf_mid, ankle, 0.064, 0.036, shade_skin, hl_skin)
            self._tapered_limb(p, cam, ankle, toe, 0.040, 0.028, spike_col if is_near else spike_col.darker(120))

            # braccio e avambraccio
            self._tapered_limb(p, cam, sh_s, elbow, 0.056, 0.044, shade_skin, hl_skin)
            self._tapered_limb(p, cam, elbow, hand, 0.043, 0.028, shade_skin)
            if has_baton and side > 0 and not crouch_mode:
                # testimone di staffetta stretto in mano
                b_dir = (0.14 * s_lean + 0.10, 0.14 * c_lean, 0.0)
                self._tapered_limb(
                    p, cam,
                    (hand[0] - b_dir[0], hand[1] - b_dir[1], hand[2]),
                    (hand[0] + b_dir[0], hand[1] + b_dir[1], hand[2]),
                    0.022, 0.022, QColor("#facc15"),
                )

        # ordine di profondità: lato lontano -> bacino/busto/collo -> lato vicino
        far = -near_sign
        draw_side(far)

        # bacino e pantaloncini
        self._tapered_limb(p, cam, (hip[0], hip[1] - 0.04, hip[2]), (hip[0] + 0.10 * s_lean, hip[1] + 0.11 * c_lean, hip[2]), 0.145, 0.140, shorts)
        # busto anatomico (trapezio 3D tra vita e petto con canotta)
        waist_l = (hip[0] + 0.10 * s_lean, hip[1] + 0.10 * c_lean, z - 0.12)
        waist_r = (hip[0] + 0.10 * s_lean, hip[1] + 0.10 * c_lean, z + 0.12)
        sh_l = (sh_mid[0] + 0.14 * twist, sh_mid[1], z - 0.18)
        sh_r = (sh_mid[0] - 0.14 * twist, sh_mid[1], z + 0.18)
        self._poly(p, cam, [waist_l, waist_r, sh_r, sh_l], kit)
        # lato in ombra del busto e fascia dorsale
        self._poly(p, cam, [waist_l, (hip[0] + 0.10 * s_lean, hip[1] + 0.10 * c_lean, z), sh_mid, sh_l], kit.darker(118))

        # pettorale di gara bianco sul torace
        chest_lo = (hip[0] + 0.24 * s_lean, hip[1] + 0.24 * c_lean, z)
        chest_hi = (hip[0] + 0.44 * s_lean, hip[1] + 0.44 * c_lean, z)
        bib_pts = [
            (chest_lo[0] + 0.04, chest_lo[1], z - 0.09),
            (chest_lo[0] + 0.04, chest_lo[1], z + 0.09),
            (chest_hi[0] + 0.04, chest_hi[1], z + 0.09),
            (chest_hi[0] + 0.04, chest_hi[1], z - 0.09),
        ]
        self._poly(p, cam, bib_pts, "#f8fafc")

        # collo
        self._tapered_limb(p, cam, sh_mid, neck_top, 0.062, 0.052, skin.darker(108))

        draw_side(near_sign)

        # testa tridimensionale con profilo, ombra e chioma
        hc = cam.to_cam(head)
        if hc[2] >= NEAR:
            hx, hy = cam.proj(hc)
            r = max(2.0, 0.112 * cam.f / hc[2])
            p.setBrush(skin)
            p.drawEllipse(QPointF(hx, hy), r * 0.96, r * 1.12)
            # ombra sul lato inferiore/posteriore del volto
            p.setBrush(skin.darker(125))
            p.drawChord(QRectF(hx - r * 0.96, hy - r * 1.12, 1.92 * r, 2.24 * r), 200 * 16, 130 * 16)
            # capelli voluminosi
            hair = QColor("#111827") if bib % 3 != 0 else QColor("#451a03")
            p.setBrush(hair)
            p.drawChord(QRectF(hx - r * 1.02, hy - r * 1.18, 2.04 * r, 2.10 * r), 35 * 16, 155 * 16)
            if is_player:
                # sottile fascetta oro del club
                p.setBrush(QColor("#fbbf24"))
                p.drawChord(QRectF(hx - r * 1.0, hy - r * 1.12, 2.0 * r, 1.95 * r), 22 * 16, 136 * 16)

            if is_player and hc[2] < 85:
                font = QFont(self.font())
                font.setPointSize(9)
                font.setBold(True)
                p.setFont(font)
                label = _short(name, 16).upper()
                tag_w = QFontMetrics(font).horizontalAdvance(label) + 16
                rect = QRectF(hx - tag_w / 2, hy - r * 1.2 - 30, tag_w, 19)
                p.setBrush(QColor(11, 18, 32, 225))
                p.setPen(QPen(QColor("#fbbf24"), 1.2))
                p.drawRoundedRect(rect, 5, 5)
                p.setPen(QColor("#fbbf24"))
                p.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor("#fbbf24"))
                p.drawPolygon(
                    QPolygonF(
                        [
                            QPointF(hx - 5, rect.bottom()),
                            QPointF(hx + 5, rect.bottom()),
                            QPointF(hx, rect.bottom() + 6),
                        ]
                    )
                )

    def _draw_rain_overlay(self, p: QPainter, w: int, h: int) -> None:
        if self._weather != WeatherCondition.PIOGGIA:
            return
        pen = QPen(QColor(203, 213, 225, 55), 1.1)
        p.setPen(pen)
        phase = int(self._t * 60)
        rng = random.Random(phase % 17)
        for _ in range(55):
            rx = rng.randint(0, w)
            ry = rng.randint(0, h)
            p.drawLine(rx, ry, rx - 8, ry + 22)
        p.setPen(Qt.PenStyle.NoPen)

    # ---- paint
    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt API)
        p = QPainter(self)
        w, h = self.width(), self.height()
        n = len(self._runners)
        if n == 0:
            p.fillRect(self.rect(), QColor("#0b1220"))
            p.end()
            return
        meters = [self.meters(r) for r in self._runners]
        cam = self._make_camera(meters, w, h)

        # antialiasing spento sulle grandi superfici per mantenere fluidità a 60 fps
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        self._draw_sky(p, cam, w, h)
        self._draw_stadium_bowl(p, cam, w)
        p.setPen(Qt.PenStyle.NoPen)
        self._draw_track_marks(p, cam)

        # oggetti in 3D + atleti con antialiasing attivo
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self._draw_blocks_and_boards(p, cam)

        is_relay = self._event.startswith("4x")
        order = sorted(range(n), key=lambda i: -cam.to_cam((meters[i], 0.0, self._lane_z(i)))[2])
        for i in order:  # dal più lontano al più vicino
            r = self._runners[i]
            s = r["s"]
            ratio = self._speed_ratio(r)
            phase = 2 * math.pi * (0.75 + 1.65 * ratio) * max(0.0, self._t - GUN_AT) + r["phase"]
            kit = QColor("#f59e0b") if s.is_player else self._kit(s.team_name)
            tag = s.athlete_name
            if is_relay:
                legs = s.athlete_name.split(" / ")
                if len(legs) == 4:
                    tag = legs[min(3, int(max(0.0, min(0.999, meters[i] / self._distance)) * 4))]
            bib = (zlib.crc32(s.athlete_name.encode()) % 890) + 100
            self._draw_athlete(
                p, cam, meters[i], self._lane_z(i), phase, ratio,
                kit, self._skin(s.athlete_name), s.is_player, tag, bib, is_relay,
            )
        self._draw_rain_overlay(p, w, h)
        p.setPen(Qt.PenStyle.NoPen)
        self._paint_hud(p, meters, w, h)
        p.end()

    # ---- HUD stile regia TV
    def _paint_hud(self, p: QPainter, meters: Sequence[float], w: int, h: int) -> None:
        d = self._distance
        n = len(self._runners)
        res = self._result
        font = QFont(self.font())
        font.setPointSize(9)
        p.setFont(font)

        # classifica live in alto a sinistra
        order = sorted(
            range(n),
            key=lambda i: (0, self._runners[i]["s"].placement)
            if self._has_finished(self._runners[i])
            else (1, -meters[i]),
        )
        row_h = 21
        panel = QRectF(12, 12, 246, 30 + n * row_h)
        p.setBrush(QColor(9, 15, 29, 215))
        p.setPen(QPen(QColor(51, 65, 85, 180), 1))
        p.drawRoundedRect(panel, 7, 7)
        p.setPen(Qt.PenStyle.NoPen)
        # intestazione pannello
        p.fillRect(QRectF(panel.left() + 1, panel.top() + 1, panel.width() - 2, 22), QColor(30, 41, 59, 210))
        hdr_f = QFont(font)
        hdr_f.setPointSize(8)
        hdr_f.setBold(True)
        p.setFont(hdr_f)
        p.setPen(QColor("#38bdf8"))
        p.drawText(QRectF(panel.left() + 10, panel.top() + 2, panel.width() - 20, 20), Qt.AlignmentFlag.AlignVCenter, f"LIVE · {self._event.upper()}")

        for rank, i in enumerate(order, start=1):
            r = self._runners[i]
            s = r["s"]
            fin = self._has_finished(r)
            y = panel.top() + 25 + (rank - 1) * row_h
            if s.is_player:
                p.setBrush(QColor(245, 158, 11, 38))
                p.drawRect(QRectF(panel.left() + 2, y, panel.width() - 4, row_h))
            # tacca colore maglia
            kit_col = QColor("#fbbf24") if s.is_player else self._kit(s.team_name)
            p.setBrush(kit_col)
            p.drawRect(QRectF(panel.left() + 6, y + 4, 4, row_h - 8))

            place = f"{s.placement}°" if fin else (f"{rank}°" if self.race_time > 0 else f"C{i + 1}")
            bold = QFont(font)
            bold.setBold(s.is_player)
            p.setFont(bold)
            p.setPen(QColor("#fbbf24" if s.is_player else "#e2e8f0"))
            name = s.team_name if self._event.startswith("4x") else s.athlete_name
            p.drawText(QRectF(panel.left() + 15, y, 30, row_h), Qt.AlignmentFlag.AlignVCenter, place)
            p.drawText(QRectF(panel.left() + 45, y, 130, row_h), Qt.AlignmentFlag.AlignVCenter, _short(name, 16))
            if fin:
                p.drawText(QRectF(panel.right() - 68, y, 60, row_h), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, s.mark_display)
            elif r["dnf"] and self.race_time > self._winner_time * 0.8:
                p.setPen(QColor("#f87171"))
                p.drawText(QRectF(panel.right() - 68, y, 60, row_h), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "RIT")
        p.setFont(font)

        # cronometro stile grafico TV al centro in alto
        pill = QRectF(w / 2 - 72, 12, 144, 32)
        p.setBrush(QColor(15, 23, 42, 230))
        p.setPen(QPen(QColor("#fbbf24"), 1.5))
        p.drawRoundedRect(pill, 7, 7)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#b91c1c"))
        p.drawRoundedRect(QRectF(pill.left() + 3, pill.top() + 3, 26, pill.height() - 6), 4, 4)
        clock_font = QFont(font)
        clock_font.setPointSize(12)
        clock_font.setBold(True)
        p.setFont(clock_font)
        p.setPen(QColor("#f8fafc"))
        p.drawText(QRectF(pill.left() + 26, pill.top(), pill.width() - 30, pill.height()), Qt.AlignmentFlag.AlignCenter, format_race_time(self.race_clock))
        p.setFont(font)

        # vento e meteo
        if res is not None and res.wind_ms is not None:
            arrow = "→" if res.wind_ms >= 0 else "←"
            box = QRectF(w - 170, 12, 158, 24)
            p.setBrush(QColor(9, 15, 29, 215))
            p.setPen(QPen(QColor(51, 65, 85, 180), 1))
            p.drawRoundedRect(box, 6, 6)
            p.setPen(QColor("#fca5a5" if res.wind_illegal else "#e2e8f0"))
            p.drawText(box, Qt.AlignmentFlag.AlignCenter, f"Vento {arrow} {res.wind_ms:+.1f} m/s")
            p.setPen(Qt.PenStyle.NoPen)

        # minimappa per distanze > 100m
        if d > 100:
            x0, x1, y = 274.0, w - 20.0, h - 28.0
            p.setBrush(QColor(9, 15, 29, 215))
            p.setPen(QPen(QColor(51, 65, 85, 180), 1))
            p.drawRoundedRect(QRectF(x0 - 10, y - 12, x1 - x0 + 20, 32), 6, 6)
            p.setPen(Qt.PenStyle.NoPen)
            p.fillRect(QRectF(x0, y + 2, x1 - x0, 4), QColor("#334155"))
            for i, r in enumerate(self._runners):
                mx = x0 + (x1 - x0) * max(0.0, min(1.0, meters[i] / d))
                p.setBrush(QColor("#fbbf24" if r["s"].is_player else "#94a3b8"))
                p.drawEllipse(QPointF(mx, y + 4), 4.5, 4.5)

        # banner partenza / fotofinish / record
        phase_txt = self.start_phase
        marks = sorted(r["s"].mark_value for r in self._runners if not r["dnf"])
        photo = len(marks) > 1 and marks[1] - marks[0] <= 0.05
        first_done = any(self._has_finished(r) for r in self._runners)
        banners: List[Tuple[str, str]] = []
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
            tw_txt = QFontMetrics(big).horizontalAdvance(text) + 42
            box = QRectF((w - tw_txt) / 2, h * 0.24, tw_txt, 50)
            p.setBrush(QColor(9, 15, 29, 200))
            p.setPen(QPen(QColor(col), 2))
            p.drawRoundedRect(box, 10, 10)
            p.setPen(QColor(col))
            p.drawText(box, Qt.AlignmentFlag.AlignCenter, text)
