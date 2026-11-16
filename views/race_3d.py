"""Vista 3D realistica delle corse in pista con regia multi-camera stile ripresa TV.

Motore 3D software disegnato con QPainter:
- Regia televisiva a 4 camere (Block-Cam rasoterra ai blocchi, Telephoto Broadcast Cam in corsa,
  Finish Line-Scan Cam sul traguardo, Follow-Cam sul vincitore).
- Texture procedurali pre-calcolate per pista tartan/Mondo granulare, erba e folla sfocata.
- Atleti con ombreggiatura cilindrica 3D, muscolatura rastremata, pettorale numerato,
  ombra morbida direzionale proiettata a terra e dettagli a bordo pista (Rail-Cam, giudici, coni).
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
    QImage,
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
CAM_BACK = 10.2
CAM_SIDE = 10.8
CAM_HEIGHT = 4.35
FOV_DEG = 29.0

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


# --------------------------------------------------------------------------- texture procedurali in cache
def make_track_tile(base_hex: str, rain: bool = False) -> QPixmap:
    """Genera una mattonella granulare realistica della pista (tartan/Mondo) con micro-usura."""
    w, h = 256, 128
    img = QImage(w, h, QImage.Format.Format_RGB32)
    base = QColor(base_hex)
    img.fill(base)
    q = QPainter(img)
    rng = random.Random(101 if not rain else 202)
    # leggere striature longitudinali della gomma
    for y in range(0, h, 3):
        delta = rng.randint(-7, 7)
        col = base.lighter(100 + delta) if delta > 0 else base.darker(100 - delta)
        q.fillRect(0, y, w, 2, col)
    # granuli EPDM del manto sintetico
    light = base.lighter(122)
    dark = base.darker(122)
    light.setAlpha(95)
    dark.setAlpha(105)
    for _ in range(1800):
        gx, gy = rng.randrange(w), rng.randrange(h)
        q.fillRect(gx, gy, 2, 1, light if rng.random() < 0.45 else dark)
    if rain:
        # riflessi lucidi della pista bagnata
        sheen = QLinearGradient(0, 0, w, h)
        sheen.setColorAt(0.0, QColor(200, 225, 255, 22))
        sheen.setColorAt(0.5, QColor(220, 238, 255, 45))
        sheen.setColorAt(1.0, QColor(180, 210, 240, 18))
        q.fillRect(0, 0, w, h, sheen)
    q.end()
    return QPixmap.fromImage(img)


def make_grass_tile(base_hex: str) -> QPixmap:
    """Mattonella del prato interno con grana organica del manto erboso."""
    w, h = 192, 192
    img = QImage(w, h, QImage.Format.Format_RGB32)
    base = QColor(base_hex)
    img.fill(base)
    q = QPainter(img)
    rng = random.Random(303)
    light = base.lighter(115)
    dark = base.darker(118)
    light.setAlpha(90)
    dark.setAlpha(90)
    for _ in range(1400):
        q.fillRect(rng.randrange(w), rng.randrange(h), 2, 2, light if rng.random() < 0.5 else dark)
    q.end()
    return QPixmap.fromImage(img)


def make_soft_shadow_pm() -> QPixmap:
    """Ombra ellittica morbida a caduta radiale da proiettare sotto i piedi degli atleti."""
    pm = QPixmap(96, 48)
    pm.fill(Qt.GlobalColor.transparent)
    q = QPainter(pm)
    grad = QRadialGradient(48, 24, 46)
    grad.setColorAt(0.0, QColor(0, 0, 0, 125))
    grad.setColorAt(0.55, QColor(0, 0, 0, 68))
    grad.setColorAt(1.0, QColor(0, 0, 0, 0))
    q.setBrush(QBrush(grad))
    q.setPen(Qt.PenStyle.NoPen)
    q.drawEllipse(2, 2, 92, 44)
    q.end()
    return pm


def make_crowd_strip(width: int = 512, height: int = 160, density: float = 0.85, dark: bool = False) -> QPixmap:
    """Gradinata con sfocatura ottica naturale, ombreggiature di fila e flash fotografici."""
    pm = QPixmap(width, height)
    base = QColor("#2a3444" if dark else "#3b4759")
    pm.fill(base)
    q = QPainter(pm)
    rng = random.Random(19 if not dark else 43)
    rows = 11
    row_h = height / rows
    skins = ("#e8be98", "#d3a279", "#ab724c", "#74492c", "#472b1c")
    for r in range(rows):
        y0 = int(r * row_h)
        rh = int(math.ceil(row_h))
        depth_dim = 100 + int((rows - r) * 2.5)
        step_col = QColor("#323d4e" if r % 2 == 0 else "#3b485c").darker(depth_dim)
        if dark:
            step_col = step_col.darker(120)
        q.fillRect(0, y0, width, rh, step_col)
        q.fillRect(0, y0 + rh - 2, width, 2, QColor(8, 13, 24, 150))
        x = rng.randint(1, 5)
        while x < width - 4:
            if rng.random() > density:
                q.fillRect(x, y0 + 3, 6, rh - 4, QColor("#172554"))
                x += rng.randint(8, 12)
                continue
            hue = rng.randint(0, 359)
            sat = rng.randint(25, 135)
            val = rng.randint(80, 195) if not dark else rng.randint(55, 145)
            shirt = QColor.fromHsv(hue, sat, val)
            skin = QColor(rng.choice(skins))
            if dark:
                skin = skin.darker(120)
            q.fillRect(x - 1, y0 + int(rh * 0.42), 8, int(rh * 0.56), shirt)
            q.fillRect(x + 1, y0 + int(rh * 0.14), 4, int(rh * 0.30), skin)
            hair = QColor("#111827" if rng.random() < 0.72 else "#78350f")
            q.fillRect(x + 1, y0 + int(rh * 0.06), 4, 2, hair)
            x += rng.randint(6, 9)
    # scalette verticali con leggera sfocatura atmosferica verso l'alto
    for aisle in (width // 4, width // 2, (3 * width) // 4):
        q.fillRect(aisle - 3, 0, 6, height, QColor(71, 85, 105, 180))
    # qualche punto luminoso dei flash fotografici in tribuna
    for _ in range(10):
        fx, fy = rng.randint(8, width - 8), rng.randint(8, height - 16)
        glow = QRadialGradient(fx, fy, 7)
        glow.setColorAt(0.0, QColor(255, 255, 240, 210))
        glow.setColorAt(1.0, QColor(255, 255, 240, 0))
        q.setBrush(QBrush(glow))
        q.setPen(Qt.PenStyle.NoPen)
        q.drawEllipse(QPointF(fx, fy), 7, 7)
    # leggero velo atmosferico dall'alto per effetto teleobiettivo
    haze = QLinearGradient(0, 0, 0, height)
    haze.setColorAt(0.0, QColor(148, 163, 184, 52 if not dark else 30))
    haze.setColorAt(1.0, QColor(15, 23, 42, 24))
    q.fillRect(0, 0, width, height, haze)
    q.end()
    return pm


# --------------------------------------------------------------------------- vista 3D broadcast
class Track3DWidget(TrackRaceWidget):
    """Vista 3D con regia TV multi-camera, texture reali e atleti ombreggiati."""

    _board_cache: Dict[int, QPixmap] = {}
    _crowd_strip_cache: Dict[Tuple[bool, int], QPixmap] = {}
    _track_tile_cache: Dict[Tuple[str, bool], QPixmap] = {}
    _grass_tile_cache: Dict[str, QPixmap] = {}
    _shadow_pm_cache: Optional[QPixmap] = None
    _lane_num_cache: Dict[int, QPixmap] = {}
    _gantry_cache: Optional[QPixmap] = None
    _scoreboard_cache: Dict[str, QPixmap] = {}
    _cone_cache: Dict[int, QPixmap] = {}

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(420)
        self._cam_label = "BROADCAST"

    # ---- geometria e stile stadio
    def _track_width(self) -> float:
        return max(1, len(self._runners)) * LANE_W

    def _lane_z(self, i: int) -> float:
        return (i + 0.5) * LANE_W

    def _is_blue_track(self) -> bool:
        surf = (self._surface or "").lower()
        return self._tier == CompetitionTier.INTERNAZIONALE or "mondo" in surf or "blu" in surf

    def _track_colors(self) -> Tuple[str, str, str]:
        rain = self._weather == WeatherCondition.PIOGGIA
        if self._is_blue_track():
            return ("#184c91", "#1d57a3", "#153d73") if rain else ("#1d5fb0", "#2267bd", "#194c8f")
        return ("#88301e", "#943723", "#732719") if rain else ("#ad3f26", "#b8452b", "#94331f")

    def _track_tile(self, hex_col: str) -> QPixmap:
        rain = self._weather == WeatherCondition.PIOGGIA
        key = (hex_col, rain)
        pm = self._track_tile_cache.get(key)
        if pm is None:
            pm = make_track_tile(hex_col, rain=rain)
            self._track_tile_cache[key] = pm
        return pm

    def _grass_tile(self, hex_col: str) -> QPixmap:
        pm = self._grass_tile_cache.get(hex_col)
        if pm is None:
            pm = make_grass_tile(hex_col)
            self._grass_tile_cache[hex_col] = pm
        return pm

    def _shadow_pm(self) -> QPixmap:
        if Track3DWidget._shadow_pm_cache is None:
            Track3DWidget._shadow_pm_cache = make_soft_shadow_pm()
        return Track3DWidget._shadow_pm_cache

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
            pm = make_crowd_strip(512, 160, density=bucket / 10.0, dark=dark)
            self._crowd_strip_cache[key] = pm
        return pm

    def _cone_pm(self, num: int) -> QPixmap:
        pm = self._cone_cache.get(num)
        if pm is None:
            pm = QPixmap(32, 36)
            pm.fill(Qt.GlobalColor.transparent)
            q = QPainter(pm)
            q.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            q.setPen(Qt.PenStyle.NoPen)
            q.setBrush(QColor("#eab308"))
            q.drawPolygon(QPolygonF([QPointF(8, 2), QPointF(24, 2), QPointF(29, 34), QPointF(3, 34)]))
            q.setPen(QColor("#0f172a"))
            f = QFont("Arial", 15)
            f.setBold(True)
            q.setFont(f)
            q.drawText(QRectF(3, 5, 26, 26), Qt.AlignmentFlag.AlignCenter, str(num))
            q.end()
            self._cone_cache[num] = pm
        return pm

    # ---- regia multi-camera TV
    def _make_camera(self, meters: Sequence[float], w: int, h: int) -> Camera:
        d = self._distance
        tw = self._track_width()
        leader = max(meters) if meters else 0.0
        leader_idx = max(range(len(meters)), key=lambda i: meters[i]) if meters else 0
        mine = [m for m, r in zip(meters, self._runners) if r["s"].is_player]
        if mine and leader - mine[0] < 12.0:
            focus = 0.68 * leader + 0.32 * mine[0]
        else:
            focus = leader

        # Camera 1: Block-Cam rasoterra in partenza (t < GUN_AT + 0.45)
        if self._t < GUN_AT + 0.45 and leader < 6.0:
            self._cam_label = "BLOCK-CAM"
            pos = (3.45, 0.80, tw + 2.75)
            target = (-0.55, 0.46, tw * 0.46)
            return Camera(pos, target, 31.0, w, h)

        # Camera 4: Follow-Cam sul vincitore dopo il traguardo
        if self.race_time > self._winner_time + 1.0 * self._scale:
            self._cam_label = "WINNER-CAM"
            wx = meters[leader_idx]
            wz = self._lane_z(leader_idx)
            pos = (wx + 6.2, 1.45, wz + 6.2)
            target = (wx - 1.2, 1.0, wz)
            return Camera(pos, target, 30.0, w, h)

        # Camera 3: Finish Line-Scan Cam negli ultimi 13 metri
        if leader >= d - 13.0:
            self._cam_label = "FINISH-CAM"
            pos = (d + 4.4, 4.4, tw + 16.0)
            target = (d - 1.2, 0.85, tw * 0.48)
            return Camera(pos, target, 28.0, w, h)

        # Camera 2: Main Elevated Telephoto Broadcast Cam
        self._cam_label = "BROADCAST"
        focus = _clamp(focus, 4.0, d - 4.0)
        pos = (focus + CAM_BACK, CAM_HEIGHT, tw + CAM_SIDE)
        target = (focus - 3.0, 0.90, tw * 0.46)
        return Camera(pos, target, FOV_DEG, w, h)

    # ---- primitive 3D
    def _poly(self, p: QPainter, cam: Camera, pts: Sequence[Vec], color) -> None:
        cs = clip_near([cam.to_cam(q) for q in pts])
        if len(cs) < 3:
            return
        p.setBrush(color if isinstance(color, QBrush) else QBrush(QColor(color)))
        p.drawPolygon(QPolygonF([QPointF(*cam.proj(c)) for c in cs]))

    def _textured_quad(self, p: QPainter, cam: Camera, corners: Sequence[Vec], pm: QPixmap) -> None:
        """Mappa una pixmap in prospettiva esatta su un quadrilatero 3D (alto-sx, alto-dx, basso-dx, basso-sx)."""
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

    def _textured_ground_quad(self, p: QPainter, cam: Camera, corners: Sequence[Vec], pm: QPixmap, fallback_col: str) -> None:
        """Usa la texture prospettica se il quad è davanti al piano vicino, altrimenti fallback poligonale."""
        cs = [cam.to_cam(q) for q in corners]
        if any(c[2] < NEAR * 2.2 for c in cs):
            self._poly(p, cam, corners, fallback_col)
            return
        dst = QPolygonF([QPointF(*cam.proj(c)) for c in cs])
        src = QPolygonF([QPointF(0, 0), QPointF(pm.width(), 0), QPointF(pm.width(), pm.height()), QPointF(0, pm.height())])
        t = QTransform()
        if not QTransform.quadToQuad(src, dst, t):
            self._poly(p, cam, corners, fallback_col)
            return
        p.save()
        p.setTransform(t, True)
        p.drawPixmap(0, 0, pm)
        p.restore()

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

    def _shaded_limb(
        self,
        p: QPainter,
        cam: Camera,
        a: Vec,
        b: Vec,
        r0: float,
        r1: float,
        color: QColor,
        lit_side: float = 1.0,
    ) -> None:
        """Segmento anatomico 3D con ombreggiatura cilindrica continua (luce chiave -> ombra -> riflesso)."""
        seg = clip_segment_near(cam.to_cam(a), cam.to_cam(b))
        if seg is None:
            return
        ca, cb = seg
        ax, ay = cam.proj(ca)
        bx, by = cam.proj(cb)
        ra = max(1.3, r0 * cam.f / ca[2])
        rb = max(1.3, r1 * cam.f / cb[2])
        dx, dy = bx - ax, by - ay
        dist = math.hypot(dx, dy)
        if dist < 0.6:
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
        mx, my = (ax + bx) * 0.5, (ay + by) * 0.5
        mr = max(ra, rb)
        if mr >= 2.5:
            grad = QLinearGradient(
                mx - lit_side * nx * mr, my - lit_side * ny * mr,
                mx + lit_side * nx * mr, my + lit_side * ny * mr,
            )
            grad.setColorAt(0.0, color.darker(142))
            grad.setColorAt(0.38, color)
            grad.setColorAt(0.72, color.lighter(124))
            grad.setColorAt(1.0, color.darker(112))
            p.setBrush(QBrush(grad))
        else:
            p.setBrush(color)
        p.drawPolygon(poly)
        p.drawEllipse(QPointF(ax, ay), ra, ra)
        p.drawEllipse(QPointF(bx, by), rb, rb)

    def _board(self, idx: int) -> QPixmap:
        pm = self._board_cache.get(idx)
        if pm is None:
            text, col, fg = SPONSORS[idx % len(SPONSORS)]
            pm = QPixmap(256, 56)
            pm.fill(QColor(col))
            q = QPainter(pm)
            grad = QLinearGradient(0, 0, 0, 56)
            grad.setColorAt(0.0, QColor(col).lighter(116))
            grad.setColorAt(0.45, QColor(col))
            grad.setColorAt(1.0, QColor(col).darker(125))
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
            q.setPen(QColor(248, 250, 252, 225))
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

    # ---- scenografia stadio
    def _draw_sky(self, p: QPainter, w: int, h: int) -> None:
        rain = self._weather == WeatherCondition.PIOGGIA
        hot = self._weather == WeatherCondition.CALDO
        indoor = self._season_phase == SeasonPhase.INDOOR

        sky = QLinearGradient(0, 0, 0, h * 0.56)
        if indoor:
            sky.setColorAt(0.0, QColor("#0b1120"))
            sky.setColorAt(1.0, QColor("#1e293b"))
        elif rain:
            sky.setColorAt(0.0, QColor("#3f4c5e"))
            sky.setColorAt(0.6, QColor("#5d6d82"))
            sky.setColorAt(1.0, QColor("#94a3b8"))
        elif hot:
            sky.setColorAt(0.0, QColor("#1e40af"))
            sky.setColorAt(0.65, QColor("#60a5fa"))
            sky.setColorAt(1.0, QColor("#fde68a"))
        else:
            sky.setColorAt(0.0, QColor("#1d4ed8"))
            sky.setColorAt(0.62, QColor("#60a5fa"))
            sky.setColorAt(1.0, QColor("#dbeafe"))
        p.fillRect(0, 0, w, h, QBrush(sky))
        p.setPen(Qt.PenStyle.NoPen)

        p.fillRect(0, int(h * 0.38), w, int(h * 0.62), QColor("#24522e" if not rain else "#1b3a22"))

        if not indoor and not rain:
            sun = QRadialGradient(w * 0.14, h * 0.12, w * 0.22)
            sun.setColorAt(0.0, QColor(255, 250, 220, 140))
            sun.setColorAt(1.0, QColor(255, 250, 220, 0))
            p.setBrush(QBrush(sun))
            p.drawEllipse(QPointF(w * 0.14, h * 0.12), w * 0.22, w * 0.22)

    def _draw_stadium_bowl(self, p: QPainter, cam: Camera) -> None:
        d = self._distance
        tw = self._track_width()
        cam_x = cam.pos[0]
        xa = max(-16.0, cam_x - 175.0)
        xb = min(d + 24.0, cam_x + 35.0)
        rain = self._weather == WeatherCondition.PIOGGIA
        big_stadium = self._tier in (CompetitionTier.NAZIONALE, CompetitionTier.INTERNAZIONALE)
        crowd_far = self._crowd_pm(dark=rain)

        # ---- tribuna opposta e curve
        z_back = -2.0 * R_IN - tw - 4.0
        seg = 24.0
        s_xa = max(-24.0, cam_x - 185.0)
        s_xb = min(d + 28.0, cam_x + 48.0)
        x = math.floor(s_xa / seg) * seg
        while x < s_xb:
            x0, x1 = x - 0.15, x + seg + 0.15
            self._poly(p, cam, [(x0, 0.0, z_back), (x1, 0.0, z_back), (x1, 1.4, z_back), (x0, 1.4, z_back)], "#64748b")
            q1 = [(x0, 1.4, z_back), (x1, 1.4, z_back), (x1, 8.2, z_back - 12.0), (x0, 8.2, z_back - 12.0)]
            self._poly(p, cam, q1, "#475569")
            self._textured_quad(p, cam, [q1[3], q1[2], q1[1], q1[0]], crowd_far)
            if big_stadium:
                self._poly(
                    p, cam,
                    [(x0, 8.2, z_back - 12.0), (x1, 8.2, z_back - 12.0), (x1, 9.6, z_back - 13.5), (x0, 9.6, z_back - 13.5)],
                    "#334155",
                )
                q2 = [(x0, 9.6, z_back - 13.5), (x1, 9.6, z_back - 13.5), (x1, 18.5, z_back - 26.0), (x0, 18.5, z_back - 26.0)]
                self._poly(p, cam, q2, "#3b495e")
                self._textured_quad(p, cam, [q2[3], q2[2], q2[1], q2[0]], crowd_far)
                self._poly(
                    p, cam,
                    [(x0, 18.5, z_back - 26.0), (x1, 18.5, z_back - 26.0), (x1, 21.2, z_back - 27.5), (x0, 21.2, z_back - 27.5)],
                    "#1e293b",
                )
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
                self._poly(
                    p, cam,
                    [(x0, 8.2, z_back - 12.0), (x1, 8.2, z_back - 12.0), (x1, 9.2, z_back - 12.2), (x0, 9.2, z_back - 12.2)],
                    "#94a3b8",
                )
            x += seg

        # torri faro
        for fx in (-20.0, 40.0, 100.0):
            if cam_x - 180.0 <= fx <= cam_x + 45.0:
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

        # curva di testata dietro la partenza
        cx_start = -16.0
        if cam_x - 175.0 < cx_start + 5.0:
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
                self._poly(p, cam, [(p0[0], 0.0, p0[2]), (p1[0], 0.0, p1[2]), p1, p0], "#64748b")
                self._poly(p, cam, [p0, p1, p2, p3], "#3f4d63")
                self._textured_quad(p, cam, [p3, p2, p1, p0], crowd_far)
                if big_stadium:
                    r_roof = r_stand_in + 6.0
                    rf0 = (cx_start + r_stand_out * math.cos(a0), 19.0, -R_IN + r_stand_out * math.sin(a0))
                    rf1 = (cx_start + r_stand_out * math.cos(a1), 19.0, -R_IN + r_stand_out * math.sin(a1))
                    rf2 = (cx_start + r_roof * math.cos(a1), 18.0, -R_IN + r_roof * math.sin(a1))
                    rf3 = (cx_start + r_roof * math.cos(a0), 18.0, -R_IN + r_roof * math.sin(a0))
                    self._poly(p, cam, [rf0, rf1, rf2, rf3], "#94a3b8")

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

        # ---- prato interno con texture granulare e bande
        band = 14.0
        x = math.floor(xa / band) * band
        while x < xb:
            light = int(x // band) % 2 == 0
            g_hex = "#2e7a3b" if light else "#358943"
            if rain:
                g_hex = QColor(g_hex).darker(118).name()
            g_pm = self._grass_tile(g_hex)
            self._textured_ground_quad(
                p, cam,
                [(x, 0.0, -2.0 * R_IN), (x + band + 0.1, 0.0, -2.0 * R_IN), (x + band + 0.1, 0.0, 0.0), (x, 0.0, 0.0)],
                g_pm, g_hex,
            )
            x += band
        # linee del campo interno e lunetta cementata dietro le gare di campo
        self._poly(p, cam, [(max(0.0, xa), 0.008, -56.0), (min(d, xb), 0.008, -56.0), (min(d, xb), 0.008, -55.7), (max(0.0, xa), 0.008, -55.7)], QColor(248, 250, 252, 110))
        self._poly(p, cam, [(max(0.0, xa), 0.008, -10.3), (min(d, xb), 0.008, -10.3), (min(d, xb), 0.008, -10.0), (max(0.0, xa), 0.008, -10.0)], QColor(248, 250, 252, 110))
        if xa < 60.0 and xb > 10.0:
            self._poly(p, cam, [(18.0, 0.01, -7.2), (27.0, 0.01, -7.2), (27.0, 0.01, -4.4), (18.0, 0.01, -4.4)], "#d9c293")
            self._poly(p, cam, [(-4.0, 0.01, -6.2), (18.0, 0.01, -6.2), (18.0, 0.01, -5.0), (-4.0, 0.01, -5.0)], self._track_colors()[2])

        # fascia esterna alla corsia 8 + binario del carrello Rail-Cam
        out_g = "#276432" if not rain else "#1e4e27"
        self._poly(p, cam, [(xa - 4.0, 0.0, tw), (xb + 16.0, 0.0, tw), (xb + 16.0, 0.0, tw + 26.0), (xa - 4.0, 0.0, tw + 26.0)], out_g)
        self._poly(p, cam, [(xa, 0.01, tw + 0.9), (xb, 0.01, tw + 0.9), (xb, 0.01, tw + 1.05), (xa, 0.01, tw + 1.05)], "#94a3b8")

        # ---- rettilineo opposto e curva dietro la partenza
        c1, c2, c3 = self._track_colors()
        self._poly(p, cam, [(xa, 0.0, -2.0 * R_IN - tw), (xb, 0.0, -2.0 * R_IN - tw), (xb, 0.0, -2.0 * R_IN), (xa, 0.0, -2.0 * R_IN)], c3)
        self._poly(p, cam, [(xa, 0.01, -2.0 * R_IN - 0.15), (xb, 0.01, -2.0 * R_IN - 0.15), (xb, 0.01, -2.0 * R_IN), (xa, 0.01, -2.0 * R_IN)], "#e2e8f0")

        if cam_x - 175.0 < cx_start + 2.0:
            n_seg = 10
            d_col = "#64748b" if self._tier == CompetitionTier.INTERNAZIONALE else ("#2e7a3b" if not rain else "#225a2c")
            for k in range(n_seg):
                a0 = math.pi * 0.5 + (math.pi * k) / n_seg
                a1 = math.pi * 0.5 + (math.pi * (k + 1)) / n_seg
                self._poly(
                    p, cam,
                    [
                        (cx_start, 0.0, -R_IN),
                        (cx_start + R_IN * math.cos(a0), 0.0, -R_IN + R_IN * math.sin(a0)),
                        (cx_start + R_IN * math.cos(a1), 0.0, -R_IN + R_IN * math.sin(a1)),
                    ],
                    d_col,
                )
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

        # ---- corsie del rettilineo principale con texture granulare in prospettiva reale!
        n = len(self._runners)
        t_seg = 16.0
        tx = math.floor(xa / t_seg) * t_seg
        while tx < xb:
            x0, x1 = max(xa, tx), min(xb, tx + t_seg + 0.08)
            if x1 > x0 + 0.1:
                for i in range(n):
                    z0, z1 = i * LANE_W, (i + 1) * LANE_W
                    col = c1 if i % 2 == 0 else c2
                    self._textured_ground_quad(
                        p, cam,
                        [(x0, 0.004, z0), (x1, 0.004, z0), (x1, 0.004, z1), (x0, 0.004, z1)],
                        self._track_tile(col), col,
                    )
            tx += t_seg

        # cordolo interno in alluminio bianco
        self._poly(p, cam, [(xa, 0.0, -0.22), (xb, 0.0, -0.22), (xb, 0.06, -0.22), (xa, 0.06, -0.22)], "#cbd5e1")
        self._poly(p, cam, [(xa, 0.06, -0.22), (xb, 0.06, -0.22), (xb, 0.06, 0.0), (xa, 0.06, 0.0)], "#f8fafc")

    def _draw_track_marks(self, p: QPainter, cam: Camera) -> None:
        d = self._distance
        n = len(self._runners)
        tw = self._track_width()
        cam_x = cam.pos[0]
        xa, xb = max(-16.0, cam_x - 175.0), min(d + 24.0, cam_x + 32.0)

        for i in range(n + 1):
            z = i * LANE_W
            self._poly(p, cam, [(xa, 0.012, z - 0.025), (xb, 0.012, z - 0.025), (xb, 0.012, z + 0.025), (xa, 0.012, z + 0.025)], "#f8fafc")

        step = 10 if d <= 400 else 50
        first = int(max(10, math.floor(xa / step) * step))
        for mt in range(first, int(min(d - 1, xb)) + 1, step):
            self._poly(p, cam, [(mt - 0.03, 0.011, 0.0), (mt + 0.03, 0.011, 0.0), (mt + 0.03, 0.011, tw), (mt - 0.03, 0.011, tw)], QColor(248, 250, 252, 85))

        if xa <= 1.0:
            self._poly(p, cam, [(-0.04, 0.013, 0.0), (0.04, 0.013, 0.0), (0.04, 0.013, tw), (-0.04, 0.013, tw)], "#ffffff")
            for i in range(n):
                zc = self._lane_z(i)
                self._textured_quad(
                    p, cam,
                    [(0.45, 0.014, zc - 0.32), (1.05, 0.014, zc - 0.32), (1.05, 0.014, zc + 0.32), (0.45, 0.014, zc + 0.32)],
                    self._lane_num_pm(i + 1),
                )

        if self._event.startswith("4x"):
            for k in (1, 2, 3):
                cx = d * k / 4.0
                if xa <= cx + 10 and xb >= cx - 10:
                    self._poly(p, cam, [(cx - 10, 0.013, 0.0), (cx + 10, 0.013, 0.0), (cx + 10, 0.013, tw), (cx - 10, 0.013, tw)], QColor(250, 204, 21, 24))
                    for zx in (cx - 10.0, cx + 10.0):
                        self._poly(p, cam, [(zx - 0.06, 0.014, 0.0), (zx + 0.06, 0.014, 0.0), (zx + 0.06, 0.014, tw), (zx - 0.06, 0.014, tw)], "#facc15")

        if xb >= d - 0.5 and xa <= d + 1.0:
            self._poly(p, cam, [(d - 0.04, 0.014, 0.0), (d + 0.04, 0.014, 0.0), (d + 0.04, 0.014, tw), (d - 0.04, 0.014, tw)], "#ffffff")
            cells = max(4, int(tw / 0.28))
            cw = tw / cells
            for j in range(cells):
                for k in range(2):
                    x0 = d + 0.04 + k * 0.24
                    col = "#f8fafc" if (j + k) % 2 == 0 else "#0f172a"
                    self._poly(p, cam, [(x0, 0.014, j * cw), (x0 + 0.24, 0.014, j * cw), (x0 + 0.24, 0.014, (j + 1) * cw), (x0, 0.014, (j + 1) * cw)], col)

    def _draw_official(self, p: QPainter, cam: Camera, x: float, z: float, cap_col: str = "#f8fafc") -> None:
        """Giudice di gara a bordo pista (camicia chiara, pantaloni scuri, scarpe, cappellino)."""
        c = cam.to_cam((x, 0.9, z))
        if c[2] < NEAR * 2 or c[2] > 75.0:
            return
        self._textured_ground_quad(
            p, cam,
            [(x - 0.35, 0.016, z - 0.22), (x + 0.35, 0.016, z - 0.22), (x + 0.35, 0.016, z + 0.22), (x - 0.35, 0.016, z + 0.22)],
            self._shadow_pm(), "#0f172a",
        )
        for sz in (-0.10, 0.10):
            self._shaded_limb(p, cam, (x, 0.05, z + sz), (x, 0.85, z + sz), 0.070, 0.082, QColor("#1e293b"))
            self._shaded_limb(p, cam, (x, 0.03, z + sz), (x + 0.14, 0.03, z + sz), 0.042, 0.032, QColor("#0f172a"))
        self._shaded_limb(p, cam, (x, 0.82, z), (x, 1.42, z), 0.15, 0.17, QColor("#f8fafc"))
        for sz in (-0.21, 0.21):
            self._shaded_limb(p, cam, (x, 1.38, z + sz), (x + 0.04, 0.95, z + sz), 0.050, 0.038, QColor("#d9a066"))
        self._shaded_limb(p, cam, (x, 1.40, z), (x, 1.54, z), 0.052, 0.048, QColor("#d9a066"))
        hc = cam.to_cam((x, 1.66, z))
        if hc[2] >= NEAR:
            hx, hy = cam.proj(hc)
            r = max(2.0, 0.10 * cam.f / hc[2])
            p.setBrush(QColor("#d9a066"))
            p.drawEllipse(QPointF(hx, hy), r, r * 1.1)
            p.setBrush(QColor(cap_col))
            p.drawChord(QRectF(hx - r * 1.1, hy - r * 1.15, 2.2 * r, 1.6 * r), 15 * 16, 150 * 16)

    def _draw_blocks_and_props(self, p: QPainter, cam: Camera, leader_x: float) -> None:
        d = self._distance
        n = len(self._runners)
        tw = self._track_width()
        cam_x = cam.pos[0]

        # blocchi di partenza 3D + coni gialli con numero corsia + giudice di partenza
        if cam_x > -4.0 and cam_x < 45.0:
            for i in range(n):
                z = self._lane_z(i)
                self._poly(p, cam, [(-0.85, 0.02, z - 0.04), (-0.15, 0.02, z - 0.04), (-0.15, 0.05, z + 0.04), (-0.85, 0.05, z + 0.04)], "#94a3b8")
                for bx in (-0.36, -0.66):
                    self._poly(p, cam, [(bx - 0.12, 0.02, z - 0.18), (bx, 0.14, z - 0.18), (bx, 0.14, z + 0.18), (bx - 0.12, 0.02, z + 0.18)], "#1e293b")
                    self._poly(p, cam, [(bx - 0.02, 0.14, z - 0.18), (bx + 0.02, 0.14, z - 0.18), (bx + 0.02, 0.14, z + 0.18), (bx - 0.02, 0.14, z + 0.18)], "#e2e8f0")
                # cono giallo accanto al blocco
                self._textured_quad(
                    p, cam,
                    [(-1.15, 0.34, z + 0.38), (-1.15, 0.34, z + 0.12), (-1.15, 0.01, z + 0.12), (-1.15, 0.01, z + 0.38)],
                    self._cone_pm(i + 1),
                )
            self._draw_official(p, cam, -2.6, -1.8)

        # cartelloni LED lungo il bordo interno (z = -1.35)
        seg = 6.0
        x = math.floor(max(-16.0, cam_x - 145.0) / seg) * seg
        while x < min(d + 18.0, cam_x + 22.0):
            pm = self._board(int(x // seg))
            self._textured_quad(
                p, cam,
                [(x, 0.85, -1.35), (x + seg - 0.15, 0.85, -1.35), (x + seg - 0.15, 0.04, -1.35), (x, 0.04, -1.35)],
                pm,
            )
            x += seg

        # carrello Rail-Cam motorizzato che segue il capofila sul binario esterno
        if self._cam_label == "BROADCAST":
            rx = _clamp(leader_x + 0.5, 2.0, d - 2.0)
            rz = tw + 1.0
            self._poly(p, cam, [(rx - 0.55, 0.08, rz - 0.25), (rx + 0.55, 0.08, rz - 0.25), (rx + 0.55, 0.30, rz + 0.25), (rx - 0.55, 0.30, rz + 0.25)], "#0f172a")
            self._poly(p, cam, [(rx - 0.22, 0.30, rz - 0.15), (rx + 0.22, 0.30, rz - 0.15), (rx + 0.22, 0.68, rz + 0.15), (rx - 0.22, 0.68, rz + 0.15)], "#334155")

        # portale d'arrivo, torretta fotofinish e giudici all'arrivo
        if cam_x >= d - 95.0:
            for z in (-0.85, tw + 0.85):
                self._line3(p, cam, (d, 0.0, z), (d, 5.2, z), 0.13, QColor("#e2e8f0"))
                self._line3(p, cam, (d + 0.35, 0.0, z), (d + 0.35, 5.2, z), 0.07, QColor("#94a3b8"))
            self._line3(p, cam, (d, 5.2, -0.85), (d, 5.2, tw + 0.85), 0.15, QColor("#e2e8f0"))
            self._textured_quad(
                p, cam,
                [(d, 5.15, tw + 0.85), (d, 5.15, -0.85), (d, 4.25, -0.85), (d, 4.25, tw + 0.85)],
                self._gantry_pm(),
            )
            # palo telecamera fotofinish giallo
            self._line3(p, cam, (d, 0.0, -2.2), (d, 3.8, -2.2), 0.08, QColor("#cbd5e1"))
            self._poly(p, cam, [(d - 0.22, 3.7, -2.35), (d + 0.22, 3.7, -2.35), (d + 0.22, 4.1, -2.05), (d - 0.22, 4.1, -2.05)], "#facc15")
            # centralina cronometraggio gialla a bordo pista
            self._poly(p, cam, [(d - 0.4, 0.0, -0.8), (d + 0.4, 0.0, -0.8), (d + 0.4, 0.9, -0.8), (d - 0.4, 0.9, -0.8)], "#eab308")
            self._draw_official(p, cam, d + 2.2, -2.8)

        if not any(self._has_finished(r) for r in self._runners):
            self._line3(p, cam, (d, 1.08, 0.0), (d, 1.08, tw), 0.025, QColor("#ef4444"))
        elif self.race_time < self._winner_time + 1.5 * self._scale:
            self._line3(p, cam, (d, 1.08, 0.0), (d + 0.8, 0.72, 0.9), 0.022, QColor("#ef4444"))
            self._line3(p, cam, (d, 1.08, tw), (d + 0.8, 0.72, tw - 0.9), 0.022, QColor("#ef4444"))

    # ---- atleti 3D ombreggiati
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
        celebrate: bool = False,
    ) -> None:
        d = self._distance
        t_anim = self._t
        if self.race_time <= 0.0:
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
            finish_dip = 0.25 * _clamp((x - (d - 1.4)) / 1.4, 0.0, 1.0) if x <= d + 0.2 else 0.0
            lean = 0.06 if celebrate else (_lerp(0.68, 0.14 + 0.14 * ratio, drive_blend) + finish_dip)
            bounce = 0.045 * abs(math.sin(phase)) * ratio
            hip_h = 0.93 + bounce
            hip_x = x

        # ombra morbida direzionale proiettata sul tartan
        sun_dx, sun_dz = -0.22, -0.18
        self._textured_ground_quad(
            p, cam,
            [
                (hip_x + sun_dx - 0.52, 0.015, z + sun_dz - 0.30),
                (hip_x + sun_dx + 0.52, 0.015, z + sun_dz - 0.30),
                (hip_x + sun_dx + 0.52, 0.015, z + sun_dz + 0.30),
                (hip_x + sun_dx - 0.52, 0.015, z + sun_dz + 0.30),
            ],
            self._shadow_pm(), "#0f172a",
        )

        twist = 0.0 if (crouch_mode or celebrate) else 0.16 * ratio * math.sin(phase)
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
            shade_skin = skin if is_near else skin.darker(128)
            shade_shorts = shorts if is_near else shorts.darker(125)
            ph = phase + (0.0 if side > 0 else math.pi)
            hip_s = (hip[0], hip[1] - 0.02, hip[2] + side * 0.105)
            sh_s = (sh_mid[0] - side * 0.14 * twist, sh_mid[1] - 0.03, sh_mid[2] + side * 0.195)

            if crouch_mode:
                if side > 0:
                    knee = (x - 0.24, _lerp(0.24, 0.46, set_blend), hip_s[2])
                    ankle = (x - 0.42, 0.13, hip_s[2])
                    toe = (x - 0.34, 0.04, hip_s[2])
                else:
                    knee = (x - 0.36, _lerp(0.11, 0.32, set_blend), hip_s[2])
                    ankle = (x - 0.70, 0.13, hip_s[2])
                    toe = (x - 0.62, 0.04, hip_s[2])
                elbow = (x - 0.08, (sh_s[1] + 0.04) * 0.52, sh_s[2])
                hand = (x - 0.05, 0.03, sh_s[2])
            elif celebrate:
                thigh_a = 0.22 * math.sin(ph)
                knee, ankle, toe = leg_chain(hip_s, thigh_a, 0.25 + 0.35 * max(0.0, math.sin(ph)))
                elbow = (sh_s[0] + 0.06, sh_s[1] + 0.20, sh_s[2] + side * 0.18)
                hand = (elbow[0] + 0.04, elbow[1] + 0.24, elbow[2] + side * 0.08)
            else:
                thigh_a = amp * math.sin(ph) + 0.15 * (1.0 - drive_blend)
                knee_flex = 0.28 + 1.55 * ratio * max(0.0, math.sin(ph + 1.25))
                knee, ankle, toe = leg_chain(hip_s, thigh_a, knee_flex)
                arm_a = -amp * 1.15 * math.sin(ph)
                elbow, hand = arm_chain(sh_s, arm_a, 1.35 + 0.35 * max(0.0, math.sin(ph)))

            mid_thigh = (_lerp(hip_s[0], knee[0], 0.55), _lerp(hip_s[1], knee[1], 0.55), hip_s[2])
            self._shaded_limb(p, cam, hip_s, knee, 0.092, 0.060, shade_skin)
            self._shaded_limb(p, cam, hip_s, mid_thigh, 0.105, 0.088, shade_shorts)
            calf_mid = (_lerp(knee[0], ankle[0], 0.38), _lerp(knee[1], ankle[1], 0.38), knee[2])
            self._shaded_limb(p, cam, knee, calf_mid, 0.060, 0.068, shade_skin)
            self._shaded_limb(p, cam, calf_mid, ankle, 0.065, 0.036, shade_skin)
            self._shaded_limb(p, cam, ankle, toe, 0.042, 0.028, spike_col if is_near else spike_col.darker(120))

            self._shaded_limb(p, cam, sh_s, elbow, 0.058, 0.045, shade_skin)
            self._shaded_limb(p, cam, elbow, hand, 0.044, 0.028, shade_skin)
            if has_baton and side > 0 and not crouch_mode:
                b_dir = (0.14 * s_lean + 0.10, 0.14 * c_lean, 0.0)
                self._shaded_limb(
                    p, cam,
                    (hand[0] - b_dir[0], hand[1] - b_dir[1], hand[2]),
                    (hand[0] + b_dir[0], hand[1] + b_dir[1], hand[2]),
                    0.022, 0.022, QColor("#facc15"),
                )

        far = -near_sign
        draw_side(far)

        self._shaded_limb(p, cam, (hip[0], hip[1] - 0.04, hip[2]), (hip[0] + 0.10 * s_lean, hip[1] + 0.11 * c_lean, hip[2]), 0.145, 0.140, shorts)
        waist_l = (hip[0] + 0.10 * s_lean, hip[1] + 0.10 * c_lean, z - 0.12)
        waist_r = (hip[0] + 0.10 * s_lean, hip[1] + 0.10 * c_lean, z + 0.12)
        sh_l = (sh_mid[0] + 0.14 * twist, sh_mid[1], z - 0.18)
        sh_r = (sh_mid[0] - 0.14 * twist, sh_mid[1], z + 0.18)
        self._poly(p, cam, [waist_l, waist_r, sh_r, sh_l], kit.lighter(108))
        self._poly(p, cam, [waist_l, (hip[0] + 0.10 * s_lean, hip[1] + 0.10 * c_lean, z), sh_mid, sh_l], kit.darker(120))

        # pettorale di gara bianco (con numero leggibile nelle riprese ravvicinate)
        chest_lo = (hip[0] + 0.24 * s_lean, hip[1] + 0.24 * c_lean, z)
        chest_hi = (hip[0] + 0.44 * s_lean, hip[1] + 0.44 * c_lean, z)
        bib_pts = [
            (chest_lo[0] + 0.04, chest_lo[1], z - 0.09),
            (chest_lo[0] + 0.04, chest_lo[1], z + 0.09),
            (chest_hi[0] + 0.04, chest_hi[1], z + 0.09),
            (chest_hi[0] + 0.04, chest_hi[1], z - 0.09),
        ]
        self._poly(p, cam, bib_pts, "#f8fafc")
        if not crouch_mode:
            bc = cam.to_cam(((chest_lo[0] + chest_hi[0]) * 0.5 + 0.05, (chest_lo[1] + chest_hi[1]) * 0.5, z))
            if NEAR <= bc[2] < 22.0:
                bx, by = cam.proj(bc)
                bf = QFont(self.font())
                bf.setPointSize(max(6, int(0.11 * cam.f / bc[2])))
                bf.setBold(True)
                p.setFont(bf)
                p.setPen(QColor("#0f172a"))
                p.drawText(QRectF(bx - 16, by - 10, 32, 20), Qt.AlignmentFlag.AlignCenter, str(bib))
                p.setPen(Qt.PenStyle.NoPen)

        self._shaded_limb(p, cam, sh_mid, neck_top, 0.062, 0.052, skin.darker(108))
        draw_side(near_sign)

        # testa scolpita con gradiente radiale
        hc = cam.to_cam(head)
        if hc[2] >= NEAR:
            hx, hy = cam.proj(hc)
            r = max(2.2, 0.114 * cam.f / hc[2])
            hgrad = QRadialGradient(hx + r * 0.25, hy - r * 0.25, r * 1.35)
            hgrad.setColorAt(0.0, skin.lighter(118))
            hgrad.setColorAt(0.55, skin)
            hgrad.setColorAt(1.0, skin.darker(135))
            p.setBrush(QBrush(hgrad))
            p.drawEllipse(QPointF(hx, hy), r * 0.96, r * 1.12)
            hair = QColor("#111827") if bib % 3 != 0 else QColor("#451a03")
            p.setBrush(hair)
            p.drawChord(QRectF(hx - r * 1.02, hy - r * 1.18, 2.04 * r, 2.10 * r), 35 * 16, 155 * 16)
            if is_player:
                p.setBrush(QColor("#fbbf24"))
                p.drawChord(QRectF(hx - r * 1.0, hy - r * 1.12, 2.0 * r, 1.95 * r), 22 * 16, 136 * 16)

            if is_player and hc[2] < 85 and self._cam_label != "BLOCK-CAM":
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

        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        self._draw_sky(p, w, h)
        self._draw_stadium_bowl(p, cam)
        p.setPen(Qt.PenStyle.NoPen)
        self._draw_track_marks(p, cam)

        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        leader_x = max(meters) if meters else 0.0
        leader_idx = max(range(n), key=lambda i: meters[i])
        self._draw_blocks_and_props(p, cam, leader_x)

        is_relay = self._event.startswith("4x")
        order = sorted(range(n), key=lambda i: -cam.to_cam((meters[i], 0.0, self._lane_z(i)))[2])
        for i in order:
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
            celebrate = (i == leader_idx) and self.race_time > self._winner_time + 1.0 * self._scale
            self._draw_athlete(
                p, cam, meters[i], self._lane_z(i), phase, ratio,
                kit, self._skin(s.athlete_name), s.is_player, tag, bib, is_relay, celebrate=celebrate,
            )

        self._draw_rain_overlay(p, w, h)
        # leggera vignettatura ottica da teleobiettivo
        vig = QRadialGradient(w * 0.5, h * 0.5, max(w, h) * 0.72)
        vig.setColorAt(0.75, QColor(0, 0, 0, 0))
        vig.setColorAt(1.0, QColor(0, 0, 0, 70))
        p.fillRect(0, 0, w, h, QBrush(vig))

        p.setPen(Qt.PenStyle.NoPen)
        self._paint_hud(p, meters, w, h)
        p.end()

    # ---- HUD televisivo compatto (lascia libero il centro della ripresa)
    def _paint_hud(self, p: QPainter, meters: Sequence[float], w: int, h: int) -> None:
        d = self._distance
        n = len(self._runners)
        res = self._result
        font = QFont(self.font())
        font.setPointSize(9)
        p.setFont(font)

        order = sorted(
            range(n),
            key=lambda i: (0, self._runners[i]["s"].placement)
            if self._has_finished(self._runners[i])
            else (1, -meters[i]),
        )

        # Lista di partenza compatta prima dello sparo, oppure ordine d'arrivo completo dopo la gara;
        # durante la corsa resta solo una barra inferiore stile TV per non coprire lo stadio.
        show_full_board = (self.race_time <= 0.0) or self._done_all()
        if show_full_board:
            row_h = 20
            panel = QRectF(12, 12, 238, 28 + n * row_h)
            p.setBrush(QColor(9, 15, 29, 210))
            p.setPen(QPen(QColor(51, 65, 85, 180), 1))
            p.drawRoundedRect(panel, 6, 6)
            p.setPen(Qt.PenStyle.NoPen)
            p.fillRect(QRectF(panel.left() + 1, panel.top() + 1, panel.width() - 2, 21), QColor(30, 41, 59, 210))
            hdr_f = QFont(font)
            hdr_f.setPointSize(8)
            hdr_f.setBold(True)
            p.setFont(hdr_f)
            p.setPen(QColor("#38bdf8"))
            hdr_txt = f"ORDINE D'ARRIVO · {self._event.upper()}" if self._done_all() else f"CORSIE · {self._event.upper()}"
            p.drawText(QRectF(panel.left() + 10, panel.top() + 2, panel.width() - 20, 20), Qt.AlignmentFlag.AlignVCenter, hdr_txt)

            for rank, i in enumerate(order, start=1):
                r = self._runners[i]
                s = r["s"]
                fin = self._has_finished(r)
                y = panel.top() + 24 + (rank - 1) * row_h
                if s.is_player:
                    p.setBrush(QColor(245, 158, 11, 38))
                    p.drawRect(QRectF(panel.left() + 2, y, panel.width() - 4, row_h))
                kit_col = QColor("#fbbf24") if s.is_player else self._kit(s.team_name)
                p.setBrush(kit_col)
                p.drawRect(QRectF(panel.left() + 6, y + 4, 4, row_h - 8))
                place = f"{s.placement}°" if fin else f"C{i + 1}"
                bold = QFont(font)
                bold.setBold(s.is_player)
                p.setFont(bold)
                p.setPen(QColor("#fbbf24" if s.is_player else "#e2e8f0"))
                name = s.team_name if self._event.startswith("4x") else s.athlete_name
                p.drawText(QRectF(panel.left() + 15, y, 28, row_h), Qt.AlignmentFlag.AlignVCenter, place)
                p.drawText(QRectF(panel.left() + 44, y, 126, row_h), Qt.AlignmentFlag.AlignVCenter, _short(name, 16))
                if fin:
                    p.drawText(QRectF(panel.right() - 66, y, 58, row_h), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, s.mark_display)
                elif r["dnf"] and self.race_time > self._winner_time * 0.8:
                    p.setPen(QColor("#f87171"))
                    p.drawText(QRectF(panel.right() - 66, y, 58, row_h), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "RIT")
            p.setFont(font)

        # Barra inferiore broadcast TV (cronometro + top 3/club + vento + badge camera)
        bar_y = h - 42.0
        bar_w = min(w - 24.0, 740.0)
        bar_x = (w - bar_w) / 2.0
        bar = QRectF(bar_x, bar_y, bar_w, 30)
        p.setBrush(QColor(9, 15, 29, 222))
        p.setPen(QPen(QColor(71, 85, 105, 190), 1))
        p.drawRoundedRect(bar, 5, 5)
        p.setPen(Qt.PenStyle.NoPen)

        # tag evento + badge oro
        ev_rect = QRectF(bar.left() + 4, bar.top() + 4, 86, 22)
        p.setBrush(QColor("#b45309"))
        p.drawRoundedRect(ev_rect, 3, 3)
        b_f = QFont(font)
        b_f.setPointSize(8)
        b_f.setBold(True)
        p.setFont(b_f)
        p.setPen(QColor("#fef3c7"))
        p.drawText(ev_rect, Qt.AlignmentFlag.AlignCenter, self._event.upper())

        # top 3 live compatto al centro della barra
        cx_pos = ev_rect.right() + 12
        for pos_idx, i in enumerate(order[:3], start=1):
            r = self._runners[i]
            s = r["s"]
            p.setPen(QColor("#fbbf24" if s.is_player else "#cbd5e1"))
            nm = s.team_name if self._event.startswith("4x") else s.athlete_name.split()[-1]
            chunk = f"{pos_idx}° {_short(nm, 11)}"
            p.drawText(QRectF(cx_pos, bar.top(), 118, 30), Qt.AlignmentFlag.AlignVCenter, chunk)
            cx_pos += 118

        # vento dentro la barra
        if res is not None and res.wind_ms is not None:
            arrow = "→" if res.wind_ms >= 0 else "←"
            p.setPen(QColor("#fca5a5" if res.wind_illegal else "#94a3b8"))
            p.drawText(QRectF(bar.right() - 235, bar.top(), 115, 30), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, f"{arrow} {res.wind_ms:+.1f} m/s")

        # cronometro stile Seiko/Omega sulla destra della barra
        clk_rect = QRectF(bar.right() - 112, bar.top() + 3, 108, 24)
        p.setBrush(QColor("#991b1b"))
        p.drawRoundedRect(clk_rect, 4, 4)
        clk_f = QFont(font)
        clk_f.setPointSize(11)
        clk_f.setBold(True)
        p.setFont(clk_f)
        p.setPen(QColor("#f8fafc"))
        p.drawText(clk_rect, Qt.AlignmentFlag.AlignCenter, format_race_time(self.race_clock))
        p.setFont(font)

        # badge camera discreto in alto a destra (stile "LIVE | CAM")
        cam_pill = QRectF(w - 134, 12, 122, 22)
        p.setBrush(QColor(9, 15, 29, 185))
        p.setPen(QPen(QColor(51, 65, 85, 160), 1))
        p.drawRoundedRect(cam_pill, 4, 4)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#ef4444"))
        p.drawEllipse(QPointF(cam_pill.left() + 12, cam_pill.center().y()), 3.5, 3.5)
        p.setFont(b_f)
        p.setPen(QColor("#e2e8f0"))
        p.drawText(QRectF(cam_pill.left() + 20, cam_pill.top(), cam_pill.width() - 24, cam_pill.height()), Qt.AlignmentFlag.AlignVCenter, self._cam_label)
        p.setFont(font)

        # minimappa per distanze > 100m sopra la barra inferiore
        if d > 100:
            x0, x1, y = bar_x + 10, bar_x + bar_w - 10, bar_y - 14.0
            p.fillRect(QRectF(x0, y, x1 - x0, 3), QColor(51, 65, 85, 200))
            for i, r in enumerate(self._runners):
                mx = x0 + (x1 - x0) * max(0.0, min(1.0, meters[i] / d))
                p.setBrush(QColor("#fbbf24" if r["s"].is_player else "#94a3b8"))
                p.drawEllipse(QPointF(mx, y + 1.5), 4.0, 4.0)

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
            big.setPointSize(24)
            big.setBold(True)
            p.setFont(big)
            text, col = banners[-1]
            tw_txt = QFontMetrics(big).horizontalAdvance(text) + 42
            box = QRectF((w - tw_txt) / 2, 16, tw_txt, 44)
            p.setBrush(QColor(9, 15, 29, 205))
            p.setPen(QPen(QColor(col), 2))
            p.drawRoundedRect(box, 8, 8)
            p.setPen(QColor(col))
            p.drawText(box, Qt.AlignmentFlag.AlignCenter, text)
