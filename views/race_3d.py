"""Vista 3D realistica delle corse in pista su stadio ovale completo da 400 m.

Motore 3D software con QPainter:
- Circuito ovale reale da 400 m (rettilineo principale + 2 curve + rettilineo opposto):
  - 100 m sul rettilineo principale con partenza dalla lunetta e blocchi 3D.
  - 400 m e staffette con partenza sfalsata in curva (e rientro alla corda nella 4x400 m).
  - 1500 m (3 giri e 3/4) con partenza a cascata in controrettilineo, gruppo compatto alla corda
    con sorpassi in seconda/terza corsia, campana dell'ultimo giro e volata finale.
- Regia multi-camera TV, texture procedurali, ombreggiatura cilindrica 3D degli atleti,
  carrello Rail-Cam, giudici e HUD televisivo compatto con radar dell'ovale.
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
    QPainterPath,
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
STRAIGHT = 84.39  # lunghezza dei rettilinei dell'ovale standard da 400 m
R_IN = 36.5  # raggio interno della curva (m)
CAM_BACK = 10.2
CAM_SIDE = 10.8
CAM_HEIGHT = 4.35
FOV_DEG = 29.0

# Sponsor di fantasia per i cartelloni LED a bordo pista
SPONSORS = [
    ("TEF SPORT", "#b91c1c", "#f8fafc"),
    ("AURORA", "#1d4ed8", "#f8fafc"),
    ("VELOCITÀ", "#047857", "#f8fafc"),
    ("ATLETICA PIÙ", "#6d28d9", "#f8fafc"),
    ("FASTLANE", "#c2410c", "#f8fafc"),
    ("CRONO LAB", "#0f172a", "#38bdf8"),
]


# --------------------------------------------------------------------------- matematica 3D e geometria ovale
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


def _smoothstep(t: float) -> float:
    u = _clamp(t, 0.0, 1.0)
    return u * u * (3.0 - 2.0 * u)


def _lerp3(a: Vec, b: Vec, t: float) -> Vec:
    return (_lerp(a[0], b[0], t), _lerp(a[1], b[1], t), _lerp(a[2], b[2], t))


def oval_pose(dist_from_finish: float, lat_z: float, ref_lat: Optional[float] = None) -> Tuple[float, float, float, float]:
    """Mappa (metri mancanti al traguardo, distanza dal cordolo interno) su (x, z, yaw, curvatura).

    `dist_from_finish = 0` coincide col traguardo (`x = STRAIGHT`, `z = lat_z`, `yaw = 0`).
    Se `ref_lat` è impostato (es. 1500m a cascata), usa quella corsia come riferimento d'arco
    così il gruppo resta compatto anziché sfalsato per giro.
    """
    r_arc = R_IN + (lat_z if ref_lat is None else ref_lat)
    r = R_IN + lat_z
    arc = math.pi * r_arc
    lap = 2.0 * STRAIGHT + 2.0 * arc
    s_fwd = (-dist_from_finish) % lap
    if s_fwd < arc:
        ang = math.pi * 0.5 - s_fwd / r_arc
        return STRAIGHT + r * math.cos(ang), -R_IN + r * math.sin(ang), math.atan2(-math.cos(ang), math.sin(ang)), 1.0 / r
    if s_fwd < arc + STRAIGHT:
        t = s_fwd - arc
        return STRAIGHT - t, -R_IN - r, math.pi, 0.0
    if s_fwd < 2.0 * arc + STRAIGHT:
        sc = s_fwd - arc - STRAIGHT
        ang = math.pi * 1.5 - sc / r_arc
        return r * math.cos(ang), -R_IN + r * math.sin(ang), math.atan2(-math.cos(ang), math.sin(ang)), 1.0 / r
    t = s_fwd - 2.0 * arc - STRAIGHT
    return t, lat_z, 0.0, 0.0


class Camera:
    """Camera a foro stenopeico. Mondo: x lungo il rettilineo, y in alto, z attraverso le corsie."""

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
    """Taglia un poligono (in coordinate camera) contro il piano vicino."""
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
    """Mattonella granulare ad alta risoluzione (512x256) in tartan/Mondo con lucentezza e usura di corsia."""
    w, h = 512, 256
    img = QImage(w, h, QImage.Format.Format_RGB32)
    base = QColor(base_hex)
    img.fill(base)
    q = QPainter(img)
    rng = random.Random(101 if not rain else 202)
    for y in range(0, h, 3):
        delta = rng.randint(-6, 6)
        col = base.lighter(100 + delta) if delta > 0 else base.darker(100 - delta)
        q.fillRect(0, y, w, 2, col)
    # leggera corsia di calpestio centrale + riflesso speculare longitudinale
    wear = QLinearGradient(0, 0, 0, h)
    wear.setColorAt(0.0, QColor(255, 255, 255, 14))
    wear.setColorAt(0.48, QColor(0, 0, 0, 18))
    wear.setColorAt(1.0, QColor(255, 255, 255, 10))
    q.fillRect(0, 0, w, h, wear)
    light = base.lighter(126)
    dark = base.darker(124)
    light.setAlpha(90)
    dark.setAlpha(100)
    for _ in range(5200):
        q.fillRect(rng.randrange(w), rng.randrange(h), 2, 2, light if rng.random() < 0.48 else dark)
    sheen = QLinearGradient(0, 0, w, h)
    if rain:
        sheen.setColorAt(0.0, QColor(200, 225, 255, 22))
        sheen.setColorAt(0.5, QColor(225, 240, 255, 48))
        sheen.setColorAt(1.0, QColor(180, 210, 240, 20))
    else:
        sheen.setColorAt(0.0, QColor(255, 244, 214, 14))
        sheen.setColorAt(0.5, QColor(255, 248, 230, 24))
        sheen.setColorAt(1.0, QColor(255, 238, 200, 8))
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
    light.setAlpha(85)
    dark.setAlpha(85)
    for _ in range(1200):
        q.fillRect(rng.randrange(w), rng.randrange(h), 2, 2, light if rng.random() < 0.5 else dark)
    q.end()
    return QPixmap.fromImage(img)


def make_soft_shadow_pm() -> QPixmap:
    """Ombra ellittica morbida a caduta radiale sotto gli atleti."""
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


def make_crowd_strip(width: int = 512, height: int = 160, density: float = 0.85, dark: bool = False, dof_blur: bool = False) -> QPixmap:
    """Gradinata con gradoni, spettatori densi, flash fotografici e opzionale sfocatura DoF."""
    pm = QPixmap(width, height)
    base = QColor("#1e293b" if dark else "#334155")
    pm.fill(base)
    q = QPainter(pm)
    rng = random.Random(19 if not dark else 43)
    rows = 12
    row_h = height / rows
    skins = ("#e8be98", "#d3a279", "#ab724c", "#74492c", "#472b1c")
    seat_col = QColor("#172554" if not dark else "#0f172a")
    for r in range(rows):
        y0 = int(r * row_h)
        rh = int(math.ceil(row_h))
        depth_dim = 100 + int((rows - r) * 3.2)
        step_col = QColor("#2a3444" if r % 2 == 0 else "#364357").darker(depth_dim)
        if dark:
            step_col = step_col.darker(128)
        q.fillRect(0, y0, width, rh, step_col)
        # ombra gradino e bordino superiore gradone
        q.fillRect(0, y0, width, 1, QColor(148, 163, 184, 50))
        q.fillRect(0, y0 + rh - 2, width, 2, QColor(6, 10, 20, 175))
        x = rng.randint(1, 5)
        while x < width - 4:
            if rng.random() > density:
                q.fillRect(x, y0 + 3, 5, rh - 5, seat_col)
                x += rng.randint(7, 11)
                continue
            hue = rng.randint(0, 359)
            sat = rng.randint(25, 145)
            val = rng.randint(80, 200) if not dark else rng.randint(50, 145)
            shirt = QColor.fromHsv(hue, sat, val)
            skin = QColor(rng.choice(skins))
            if dark:
                skin = skin.darker(125)
            # spalle arrotondate + torso + testa + eventuale cappellino/sciarpa
            q.fillRect(x - 1, y0 + int(rh * 0.42), 7, int(rh * 0.56), shirt)
            q.fillRect(x, y0 + int(rh * 0.36), 5, 2, shirt.lighter(115))
            q.fillRect(x + 1, y0 + int(rh * 0.14), 4, int(rh * 0.28), skin)
            hair = QColor("#f8fafc" if rng.random() < 0.08 else ("#111827" if rng.random() < 0.70 else "#78350f"))
            q.fillRect(x + 1, y0 + int(rh * 0.06), 4, 2, hair)
            if rng.random() < 0.04:
                q.fillRect(x - 2, y0 + 1, 9, 2, QColor("#fbbf24" if rng.random() < 0.5 else "#38bdf8"))
            x += rng.randint(6, 8)
    # scalette di accesso con corrimano metallico
    for aisle in (width // 4, width // 2, (3 * width) // 4):
        q.fillRect(aisle - 4, 0, 8, height, QColor(30, 41, 59, 195))
        q.fillRect(aisle - 1, 0, 2, height, QColor(203, 213, 225, 120))
    for _ in range(12):
        fx, fy = rng.randint(8, width - 8), rng.randint(8, height - 16)
        glow = QRadialGradient(fx, fy, 7)
        glow.setColorAt(0.0, QColor(255, 255, 240, 220))
        glow.setColorAt(1.0, QColor(255, 255, 240, 0))
        q.setBrush(QBrush(glow))
        q.setPen(Qt.PenStyle.NoPen)
        q.drawEllipse(QPointF(fx, fy), 7, 7)
    haze = QLinearGradient(0, 0, 0, height)
    haze.setColorAt(0.0, QColor(148, 163, 184, 58 if (not dark or dof_blur) else 20))
    haze.setColorAt(1.0, QColor(15, 23, 42, 40))
    q.fillRect(0, 0, width, height, haze)
    q.end()
    if dof_blur:
        small = pm.scaled(max(16, int(width * 0.36)), max(8, int(height * 0.36)), Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
        pm = small.scaled(width, height, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    return pm


# --------------------------------------------------------------------------- primitive 3D condivise
_SHARED_BOARDS: Dict[int, QPixmap] = {}
_SHARED_SHADOW: Optional[QPixmap] = None


def draw_poly(p: QPainter, cam: Camera, pts: Sequence[Vec], color) -> None:
    cs = clip_near([cam.to_cam(q) for q in pts])
    if len(cs) < 3:
        return
    p.setBrush(color if isinstance(color, QBrush) else QBrush(QColor(color)))
    p.drawPolygon(QPolygonF([QPointF(*cam.proj(c)) for c in cs]))


def draw_textured_quad(p: QPainter, cam: Camera, corners: Sequence[Vec], pm: QPixmap) -> None:
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


def draw_textured_ground_quad(p: QPainter, cam: Camera, corners: Sequence[Vec], pm: QPixmap, fallback_col: str) -> None:
    cs = [cam.to_cam(q) for q in corners]
    if all(c[2] < NEAR for c in cs):
        return
    if any(c[2] < NEAR * 2.2 for c in cs) or max(c[2] for c in cs) > 85.0:
        draw_poly(p, cam, corners, fallback_col)
        return
    dst = QPolygonF([QPointF(*cam.proj(c)) for c in cs])
    src = QPolygonF([QPointF(0, 0), QPointF(pm.width(), 0), QPointF(pm.width(), pm.height()), QPointF(0, pm.height())])
    t = QTransform()
    if not QTransform.quadToQuad(src, dst, t):
        draw_poly(p, cam, corners, fallback_col)
        return
    p.save()
    p.setTransform(t, True)
    p.drawPixmap(0, 0, pm)
    p.restore()


def draw_line3(p: QPainter, cam: Camera, a: Vec, b: Vec, radius: float, color: QColor) -> None:
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


def draw_shaded_limb(
    p: QPainter, cam: Camera, a: Vec, b: Vec, r0: float, r1: float, color: QColor, lit_side: float = 1.0,
) -> None:
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
    if mr >= 2.4:
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
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(QPointF(ax, ay), ra, ra)
    p.drawEllipse(QPointF(bx, by), rb, rb)
    p.drawPolygon(poly)
    if mr >= 2.2:
        p.setPen(QPen(QColor(15, 23, 42, 85), 0.85))
        p.drawLine(QPointF(ax + nx * ra, ay + ny * ra), QPointF(bx + nx * rb, by + ny * rb))
        p.drawLine(QPointF(ax - nx * ra, ay - ny * ra), QPointF(bx - nx * rb, by - ny * rb))
        p.setPen(Qt.PenStyle.NoPen)


def get_sponsor_board(idx: int) -> QPixmap:
    pm = _SHARED_BOARDS.get(idx)
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
        _SHARED_BOARDS[idx] = pm
    return pm


def get_soft_shadow() -> QPixmap:
    global _SHARED_SHADOW
    if _SHARED_SHADOW is None:
        _SHARED_SHADOW = make_soft_shadow_pm()
    return _SHARED_SHADOW


def draw_spike_shoe_3d(
    p: QPainter,
    cam: Camera,
    ankle: Vec,
    toe: Vec,
    shoe_col: QColor,
    is_near: bool = True,
) -> None:
    """Scarpa chiodata bicolore con colletto alla caviglia, tallone e piastra suola."""
    col = shoe_col if is_near else shoe_col.darker(120)
    draw_shaded_limb(p, cam, ankle, toe, 0.044, 0.026, col)
    # suola contrastata + tallone rinforzato
    ca, cb = cam.to_cam(ankle), cam.to_cam(toe)
    if ca[2] < NEAR or cb[2] < NEAR:
        return
    ax, ay = cam.proj(ca)
    bx, by = cam.proj(cb)
    ra = max(1.2, 0.042 * cam.f / ca[2])
    rb = max(1.0, 0.026 * cam.f / cb[2])
    if math.hypot(bx - ax, by - ay) < 3.0 and ra < 2.2:
        return
    sole = QColor("#0f172a") if shoe_col.lightness() > 140 else QColor("#f8fafc")
    p.setPen(QPen(sole, max(1.1, ra * 0.42), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.drawLine(QPointF(ax, ay + ra * 0.62), QPointF(bx, by + rb * 0.55))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#f8fafc" if is_near else "#cbd5e1"))
    p.drawEllipse(QPointF(ax, ay - ra * 0.15), max(1.0, ra * 0.62), max(1.0, ra * 0.46))


def draw_floodlight_pylon_3d(
    p: QPainter,
    cam: Camera,
    base: Vec,
    aim_dir: Vec,
    height: float = 34.0,
    evening: bool = False,
) -> None:
    """Torre faro dello stadio con piloni metallici, pannello LED e alone luminoso serale."""
    c_base = cam.to_cam(base)
    if c_base[2] < -4.0:
        return
    dx, _, dz = aim_dir
    mag = math.hypot(dx, dz) or 1.0
    ux, uz = dx / mag, dz / mag
    rx, rz = -uz, ux
    top = (base[0] + ux * 3.8, height, base[2] + uz * 3.8)
    draw_line3(p, cam, base, top, 0.52, QColor("#334155" if evening else "#64748b"))
    draw_line3(p, cam, (base[0] + rx * 0.9, 0.0, base[2] + rz * 0.9), (top[0] + rx * 0.45, height - 1.5, top[2] + rz * 0.45), 0.24, QColor("#475569" if evening else "#94a3b8"))
    # piastra fari inclinata verso il campo
    hw = 3.2
    p0 = (top[0] - rx * hw, height - 1.2, top[2] - rz * hw)
    p1 = (top[0] + rx * hw, height - 1.2, top[2] + rz * hw)
    p2 = (top[0] + rx * hw + ux * 0.8, height + 2.4, top[2] + rz * hw + uz * 0.8)
    p3 = (top[0] - rx * hw + ux * 0.8, height + 2.4, top[2] - rz * hw + uz * 0.8)
    draw_poly(p, cam, [p0, p1, p2, p3], "#1e293b")
    lamp_col = "#fef9c3" if evening else "#e2e8f0"
    for frac in (-0.65, -0.22, 0.22, 0.65):
        lp_lo = (top[0] + rx * hw * frac, height - 0.6, top[2] + rz * hw * frac)
        lp_hi = (top[0] + rx * hw * frac + ux * 0.6, height + 1.8, top[2] + rz * hw * frac + uz * 0.6)
        draw_line3(p, cam, lp_lo, lp_hi, 0.42, QColor(lamp_col))
    if evening:
        ct = cam.to_cam((top[0] + ux * 0.4, height + 0.6, top[2] + uz * 0.4))
        if ct[2] >= NEAR:
            sx, sy = cam.proj(ct)
            rad = _clamp(6.8 * cam.f / ct[2], 14.0, 95.0)
            halo = QRadialGradient(sx, sy, rad)
            halo.setColorAt(0.0, QColor(254, 249, 195, 165))
            halo.setColorAt(0.35, QColor(254, 240, 138, 65))
            halo.setColorAt(1.0, QColor(254, 240, 138, 0))
            p.setBrush(QBrush(halo))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(sx, sy), rad, rad)


def draw_athlete_head_3d(
    p: QPainter,
    cam: Camera,
    head_pos: Vec,
    yaw: float,
    skin: QColor,
    bib: int,
    is_player: bool = False,
    crouch: bool = False,
    effort: bool = False,
    celebrate: bool = False,
    cap_col: Optional[str] = None,
) -> Optional[Tuple[float, float, float, float]]:
    """Disegna testa 3D scolpita con occhi, sopracciglia, naso, bocca, orecchie e capelli orientati alla camera.

    Ritorna `(hx, hy, r, depth)` se visibile davanti al piano vicino.
    """
    hc = cam.to_cam(head_pos)
    if hc[2] < NEAR:
        return None
    hx, hy = cam.proj(hc)
    r = max(2.2, 0.116 * cam.f / hc[2])

    fwd = (math.cos(yaw), 0.0, math.sin(yaw))
    fx = _dot(fwd, cam.right)  # >0 guarda a destra sullo schermo, <0 a sinistra
    fz = _dot(fwd, cam.fwd)    # <0 guarda verso la camera, >0 dà le spalle
    front_vis = _clamp(0.60 - fz * 0.85, 0.0, 1.0)
    face_shift = _clamp(fx, -0.85, 0.85) * 0.40

    # orecchio sul lato posteriore rispetto alla direzione dello sguardo
    if abs(fx) > 0.22 and r >= 4.0:
        ear_x = hx - (1.0 if fx > 0 else -1.0) * r * 0.86
        p.setBrush(skin.darker(118))
        p.drawEllipse(QPointF(ear_x, hy + r * 0.06), r * 0.16, r * 0.25)

    # cranio + mascella scolpita con luce direzionale tardo pomeriggio e contorno morbido
    hgrad = QRadialGradient(hx + r * (0.30 if fx >= 0 else -0.30), hy - r * 0.28, r * 1.38)
    hgrad.setColorAt(0.0, skin.lighter(124))
    hgrad.setColorAt(0.50, skin)
    hgrad.setColorAt(1.0, skin.darker(142))
    p.setBrush(QBrush(hgrad))
    p.setPen(QPen(QColor(15, 23, 42, 85), 0.85) if r >= 3.2 else Qt.PenStyle.NoPen)
    if r >= 4.2:
        jaw_shift = face_shift * r * 0.55
        head_path = QPainterPath()
        head_path.moveTo(hx - r * 0.90, hy + r * 0.08)
        head_path.cubicTo(hx - r * 0.96, hy - r * 1.15, hx + r * 0.96, hy - r * 1.15, hx + r * 0.90, hy + r * 0.08)
        head_path.cubicTo(hx + r * 0.80, hy + r * 0.72, hx + jaw_shift + r * 0.34, hy + r * 1.06, hx + jaw_shift, hy + r * 1.08)
        head_path.cubicTo(hx + jaw_shift - r * 0.34, hy + r * 1.06, hx - r * 0.80, hy + r * 0.72, hx - r * 0.90, hy + r * 0.08)
        p.drawPath(head_path)
    else:
        p.drawEllipse(QPointF(hx, hy - r * 0.04), r * 0.92, r * 1.04)
    p.setPen(Qt.PenStyle.NoPen)
    if r >= 6.0 and front_vis > 0.2:
        p.setBrush(QColor(255, 248, 232, 42))
        p.drawEllipse(QPointF(hx + (face_shift + 0.22) * r, hy - r * 0.16), r * 0.22, r * 0.14)

    # tratti del volto (visibili appena la testa supera ~4 px di raggio e non è completamente girata)
    if r >= 4.0 and front_vis > 0.15:
        ex_mid = hx + face_shift * r
        eye_y = hy + (0.20 if crouch else -0.14) * r
        nose_y = hy + (0.40 if crouch else 0.10) * r
        mouth_y = hy + (0.62 if crouch else 0.42) * r
        sep = r * 0.28 * (0.30 + 0.70 * front_vis)
        eye_rx = max(1.0, r * 0.13 * (0.55 + 0.45 * front_vis))
        eye_ry = max(0.8, r * 0.09)

        # due occhi (o occhio in vista di profilo) con sclera, iride, pupilla e sopracciglia
        eye_offsets = [-sep, sep * 0.78] if fx >= 0 else [-sep * 0.78, sep]
        if front_vis < 0.32:
            eye_offsets = [eye_offsets[1 if fx >= 0 else 0]]
        brow_col = QColor("#111827") if bib % 3 else QColor("#3b1a08")
        for eo in eye_offsets:
            ex = ex_mid + eo
            p.setBrush(skin.darker(118))
            p.drawEllipse(QPointF(ex, eye_y), eye_rx * 1.22, eye_ry * 1.28)
            p.setBrush(QColor("#f8fafc"))
            p.drawEllipse(QPointF(ex, eye_y), eye_rx, eye_ry)
            ir_x = ex + face_shift * eye_rx * 0.35
            p.setBrush(QColor("#1e1b18"))
            p.drawEllipse(QPointF(ir_x, eye_y), eye_rx * 0.56, eye_ry * 0.78)
            if r >= 8.5:
                p.setBrush(QColor("#ffffff"))
                p.drawEllipse(QPointF(ir_x + eye_rx * 0.18, eye_y - eye_ry * 0.22), max(0.6, eye_rx * 0.20), max(0.6, eye_rx * 0.20))
            # sopracciglio naturale
            tilt = (0.03 if eo < 0 else -0.03) if effort else (-0.04 if celebrate else 0.0)
            p.setPen(QPen(brow_col, max(0.9, r * 0.065), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawLine(
                QPointF(ex - eye_rx * 1.05, eye_y - eye_ry * 1.85 - tilt * r),
                QPointF(ex + eye_rx * 1.05, eye_y - eye_ry * 1.85 + tilt * r),
            )
            p.setPen(Qt.PenStyle.NoPen)

        # naso (ponte + punta leggermente ombreggiata)
        nx = hx + face_shift * r * 1.20
        p.setPen(QPen(skin.darker(132), max(0.8, r * 0.07), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(ex_mid, eye_y + eye_ry * 0.6), QPointF(nx, nose_y))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(skin.darker(124))
        p.drawEllipse(QPointF(nx, nose_y), max(0.8, r * 0.10), max(0.7, r * 0.07))

        # bocca ed espressione (naturale e proporzionata)
        mx = hx + face_shift * r * 1.02
        mw = max(1.2, r * 0.24 * (0.6 + 0.4 * front_vis))
        lip_col = skin.darker(155)
        if celebrate:
            p.setBrush(QColor("#6b2c26"))
            p.drawChord(QRectF(mx - mw, mouth_y - r * 0.05, 2 * mw, r * 0.28), 180 * 16, 180 * 16)
            p.setBrush(QColor("#f8fafc"))
            p.drawRect(QRectF(mx - mw * 0.70, mouth_y - r * 0.01, mw * 1.40, max(1.0, r * 0.08)))
        elif effort:
            p.setBrush(QColor("#5c2824"))
            p.drawEllipse(QPointF(mx, mouth_y + r * 0.02), mw * 0.72, max(0.9, r * 0.09))
            if r >= 8.0:
                p.setBrush(QColor("#e2e8f0"))
                p.drawRect(QRectF(mx - mw * 0.45, mouth_y - r * 0.02, mw * 0.90, max(0.7, r * 0.045)))
        else:
            p.setPen(QPen(lip_col, max(0.9, r * 0.07), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawLine(QPointF(mx - mw * 0.70, mouth_y), QPointF(mx + mw * 0.70, mouth_y))
            p.setPen(Qt.PenStyle.NoPen)

    # capelli o cappellino da giudice
    if cap_col is not None:
        p.setBrush(QColor(cap_col))
        p.drawChord(QRectF(hx - r * 1.08, hy - r * 1.20, 2.16 * r, 1.55 * r), 12 * 16, 156 * 16)
        # visiera
        visor_x = hx + (1.0 if fx >= 0 else -1.0) * r * 0.65
        p.drawEllipse(QPointF(visor_x, hy - r * 0.45), r * 0.55, r * 0.16)
    else:
        hair = QColor("#111827") if bib % 3 != 0 else QColor("#451a03")
        p.setBrush(hair)
        style = bib % 4
        if style == 1:  # volume riccio
            p.drawChord(QRectF(hx - r * 1.06, hy - r * 1.28, 2.12 * r, 2.10 * r), 20 * 16, 170 * 16)
        elif style == 2:  # capelli raccolti con chignon posteriore
            p.drawChord(QRectF(hx - r * 1.00, hy - r * 1.16, 2.00 * r, 1.95 * r), 30 * 16, 150 * 16)
            bun_x = hx - (1.0 if fx >= 0 else -1.0) * r * 0.98
            p.drawEllipse(QPointF(bun_x, hy - r * 0.35), r * 0.34, r * 0.34)
        else:  # taglio atletico corto
            p.drawChord(QRectF(hx - r * 1.00, hy - r * 1.16, 2.00 * r, 1.90 * r), 30 * 16, 150 * 16)
        if is_player:
            p.setBrush(QColor("#fbbf24"))
            p.drawRect(QRectF(hx - r * 0.96, hy - r * 0.56, 1.92 * r, max(1.4, r * 0.20)))

    return (hx, hy, r, hc[2])


def draw_singlet_torso_3d(
    p: QPainter,
    cam: Camera,
    to_world,
    hip_lf: float,
    hip_h: float,
    sh_lf_val: float,
    sh_y_val: float,
    s_lean: float,
    c_lean: float,
    twist: float,
    kit: QColor,
    skin: QColor,
    bib: int,
    crouch_mode: bool,
    font_base: QFont,
) -> None:
    """Disegna bacino atletico, torace a V con muscolatura scapolare/pettorale, pieghe tessuto e pettorale."""
    shorts = QColor("#0f172a")
    draw_shaded_limb(p, cam, to_world(hip_lf, hip_h - 0.04, 0.0), to_world(hip_lf + 0.11 * s_lean, hip_h + 0.12 * c_lean, 0.0), 0.122, 0.114, shorts)
    # torace a V muscolare base (clavicole + deltoidi scoperti)
    wl = to_world(hip_lf + 0.10 * s_lean, hip_h + 0.10 * c_lean, -0.118)
    wr = to_world(hip_lf + 0.10 * s_lean, hip_h + 0.10 * c_lean, 0.118)
    sl_out = to_world(sh_lf_val + 0.14 * twist, sh_y_val, -0.192)
    sr_out = to_world(sh_lf_val - 0.14 * twist, sh_y_val, 0.192)
    draw_poly(p, cam, [wl, wr, sr_out, sl_out], skin.darker(110))
    # cappe dei deltoidi alle spalle
    for side_s, tw_s in ((-1.0, 0.14), (1.0, -0.14)):
        draw_shaded_limb(
            p, cam,
            to_world(sh_lf_val + tw_s * twist, sh_y_val, side_s * 0.135),
            to_world(sh_lf_val + tw_s * twist, sh_y_val - 0.03, side_s * 0.195),
            0.068, 0.060, skin if side_s > 0 else skin.darker(118),
        )

    # canotta smanicata sagomata sul torace con bretelle e riflesso speculare tessuto
    sl_in = to_world(sh_lf_val + 0.14 * twist, sh_y_val + 0.01, -0.130)
    sr_in = to_world(sh_lf_val - 0.14 * twist, sh_y_val + 0.01, 0.130)
    chest_mid_y = _lerp(hip_h + 0.10 * c_lean, sh_y_val, 0.72)
    chest_mid_lf = _lerp(hip_lf + 0.10 * s_lean, sh_lf_val, 0.72)
    cl_pt = to_world(chest_mid_lf + 0.02 * s_lean, chest_mid_y, -0.155)
    cr_pt = to_world(chest_mid_lf + 0.02 * s_lean, chest_mid_y, 0.155)
    draw_poly(p, cam, [wl, wr, cr_pt, cl_pt], kit.lighter(112))
    # bretelle sinistra e destra
    draw_poly(p, cam, [cl_pt, to_world(chest_mid_lf, chest_mid_y, -0.062), to_world(sh_lf_val + 0.14 * twist, sh_y_val + 0.01, -0.072), sl_in], kit.lighter(116))
    draw_poly(p, cam, [to_world(chest_mid_lf, chest_mid_y, 0.062), cr_pt, sr_in, to_world(sh_lf_val - 0.14 * twist, sh_y_val + 0.01, 0.072)], kit.lighter(116))
    # ombreggiatura pettorale/costato + pieghe diagonali di tensione sul tessuto
    draw_poly(p, cam, [wl, to_world(hip_lf + 0.10 * s_lean, hip_h + 0.10 * c_lean, 0.01), to_world(chest_mid_lf, chest_mid_y, 0.01), cl_pt], kit.darker(124))
    draw_line3(p, cam, to_world(hip_lf + 0.15 * s_lean, hip_h + 0.15 * c_lean, -0.05), to_world(chest_mid_lf, chest_mid_y - 0.03, 0.09), 0.010, kit.darker(135))
    draw_line3(p, cam, to_world(hip_lf + 0.24 * s_lean, hip_h + 0.24 * c_lean, 0.02), to_world(chest_mid_lf, chest_mid_y - 0.01, 0.13), 0.008, kit.lighter(135))
    draw_line3(p, cam, to_world(chest_mid_lf, chest_mid_y, 0.05), cr_pt, 0.012, QColor(255, 250, 235, 75))

    # pettorale di gara bianco con numero
    ch_lo = hip_lf + 0.22 * s_lean
    ch_hi = hip_lf + 0.42 * s_lean
    y_lo, y_hi = hip_h + 0.22 * c_lean, hip_h + 0.42 * c_lean
    bib_pts = [to_world(ch_lo + 0.04, y_lo, -0.09), to_world(ch_lo + 0.04, y_lo, 0.09), to_world(ch_hi + 0.04, y_hi, 0.09), to_world(ch_hi + 0.04, y_hi, -0.09)]
    draw_poly(p, cam, bib_pts, "#f8fafc")
    if not crouch_mode:
        bc = cam.to_cam(to_world((ch_lo + ch_hi) * 0.5 + 0.05, (y_lo + y_hi) * 0.5, 0.0))
        if NEAR <= bc[2] < 24.0:
            bx, by = cam.proj(bc)
            bf = QFont(font_base)
            bf.setPointSize(max(6, int(0.11 * cam.f / bc[2])))
            bf.setBold(True)
            p.setFont(bf)
            p.setPen(QColor("#0f172a"))
            p.drawText(QRectF(bx - 16, by - 10, 32, 20), Qt.AlignmentFlag.AlignCenter, str(bib))
            p.setPen(Qt.PenStyle.NoPen)


def draw_official_3d(p: QPainter, cam: Camera, x: float, z: float, cap_col: str = "#f8fafc") -> None:
    c = cam.to_cam((x, 0.9, z))
    if c[2] < NEAR * 2 or c[2] > 75.0:
        return
    draw_textured_ground_quad(
        p, cam,
        [(x - 0.35, 0.016, z - 0.22), (x + 0.35, 0.016, z - 0.22), (x + 0.35, 0.016, z + 0.22), (x - 0.35, 0.016, z + 0.22)],
        get_soft_shadow(), "#0f172a",
    )
    for sz in (-0.10, 0.10):
        draw_shaded_limb(p, cam, (x, 0.05, z + sz), (x, 0.85, z + sz), 0.070, 0.082, QColor("#1e293b"))
        draw_shaded_limb(p, cam, (x, 0.03, z + sz), (x + 0.14, 0.03, z + sz), 0.042, 0.032, QColor("#0f172a"))
    draw_shaded_limb(p, cam, (x, 0.82, z), (x, 1.42, z), 0.15, 0.17, QColor("#f8fafc"))
    for sz in (-0.21, 0.21):
        draw_shaded_limb(p, cam, (x, 1.38, z + sz), (x + 0.04, 0.95, z + sz), 0.050, 0.038, QColor("#d9a066"))
    draw_shaded_limb(p, cam, (x, 1.40, z), (x, 1.54, z), 0.052, 0.048, QColor("#d9a066"))
    draw_athlete_head_3d(p, cam, (x, 1.66, z), yaw=0.4, skin=QColor("#d9a066"), bib=1, cap_col=cap_col)


# --------------------------------------------------------------------------- vista 3D
class Track3DWidget(TrackRaceWidget):
    """Vista 3D su stadio ovale da 400 m con regia multi-camera e gruppo realistico."""

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
        self._replay_active = False
        self._replay_target_t = 0.0

    # ---- replay dell'arrivo: stessa posa (funzione pura di _t), solo un'altra camera e un t più indietro
    def start_replay(self, lookback: float = 3.0) -> None:
        """Riavvolge a `lookback` secondi prima dell'arrivo del vincitore e riparte al rallentatore
        da un'altra inquadratura. Non ri-simula nulla: la posa di ogni atleta resta la stessa
        funzione pura di _t già usata in diretta."""
        rewind_race_time = max(0.0, self._winner_time - lookback)
        self._t = GUN_AT + rewind_race_time / self._scale
        self._replay_target_t = GUN_AT + self._winner_time / self._scale
        self._done = False
        self._replay_active = True
        self.update()

    def end_replay(self) -> None:
        """Torna al fotogramma statico di fine gara (stesso `end_anim` di `advance()`)."""
        self._replay_active = False
        self._t = GUN_AT + self._last_finish() / self._scale + 1.2
        self._done = True
        self.update()

    def _replay_camera(self, poses: Sequence[Tuple[float, float, float, float]], leader_idx: int, w: int, h: int) -> Camera:
        """Inquadratura bassa e ravvicinata dal lato pista, in stile moviola: diversa da quelle
        broadcast usate in diretta, per far sentire che è davvero un replay."""
        lx, lz, lyaw, _ = poses[leader_idx]
        fwd_x, fwd_z = math.cos(lyaw), math.sin(lyaw)
        side_x, side_z = -fwd_z, fwd_x
        pos = (lx - 2.0 * fwd_x + 9.0 * side_x, 1.05, lz - 2.0 * fwd_z + 9.0 * side_z)
        target = (lx + 3.0 * fwd_x, 1.05, lz + 3.0 * fwd_z)
        return Camera(pos, target, 24.0, w, h)

    # ---- geometria dell'ovale e stile stadio
    def _track_width(self) -> float:
        return max(1, len(self._runners)) * LANE_W

    def _lane_z(self, i: int) -> float:
        return (i + 0.5) * LANE_W

    def _is_oval_race(self) -> bool:
        return self._distance > 100

    def _is_pack_race(self) -> bool:
        """Gare con rientro alla corda e gruppo compatto (1500m, o 4x400m dopo la prima curva)."""
        return self._distance >= 1500

    def _is_evening_final(self) -> bool:
        """Meeting nazionali/internazionali hanno atmosfera serale sotto i riflettori."""
        return self._tier in (CompetitionTier.NAZIONALE, CompetitionTier.INTERNAZIONALE)

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
            base = 0.96
        elif self._tier == CompetitionTier.NAZIONALE:
            base = 0.88
        elif self._tier == CompetitionTier.REGIONALE:
            base = 0.72
        else:
            base = 0.52
        leader = max((self.meters(r) for r in self._runners), default=0.0)
        progress = _clamp(leader / self._distance, 0.0, 1.0) if self._distance else 0.0
        swell = 0.10 * _smoothstep((progress - 0.6) / 0.4)  # la tribuna si scalda nell'ultimo tratto
        if self._result is not None and (self._result.is_club_record or self._result.is_pb):
            swell += 0.05 * _smoothstep((progress - 0.6) / 0.4)  # risultato di rilievo: ancora più calore
        return min(0.98, base + swell)

    def _crowd_pm(self, dark: bool, dof_blur: bool = False) -> QPixmap:
        bucket = int(round(self._crowd_density() * 10))
        key = (dark, bucket, dof_blur)
        pm = self._crowd_strip_cache.get(key)
        if pm is None:
            pm = make_crowd_strip(512, 160, density=bucket / 10.0, dark=dark, dof_blur=dof_blur)
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

    # ---- posizionamento sull'ovale (compreso il gruppo a cascata/corda nei 1500m)
    def _runner_world_poses(self, meters: Sequence[float]) -> List[Tuple[float, float, float, float]]:
        """Calcola (x, z, yaw, curvatura) per ogni atleta in base alla disciplina."""
        d = self._distance
        n = len(meters)
        if not self._is_oval_race():
            # 100 m: rettilineo finale che arriva al traguardo x = STRAIGHT
            poses: List[Tuple[float, float, float, float]] = []
            for i, m in enumerate(meters):
                x = STRAIGHT - (100.0 - m)
                poses.append((x, self._lane_z(i), 0.0, 0.0))
            return poses

        # gare sull'ovale da 400 m (400m, 4x100m, 1500m, 4x400m)
        lat_zs = [self._lane_z(i) for i in range(n)]
        if self._event == "1500m":
            # partenza a cascata in corsia, poi rientro morbido verso la corda (corsia 1) con sorpassi in corsia 2/3
            order = sorted(range(n), key=lambda i: -meters[i])
            placed: List[Tuple[float, float]] = []  # (metri, lat_z)
            for idx in order:
                m = meters[idx]
                merge = _clamp(m / 65.0, 0.0, 1.0)
                target_z = _lerp(self._lane_z(idx), 0.52, merge)
                # evita sovrapposizioni nel gruppo allargando in 2ª/3ª corsia
                while any(abs(pm - m) < 1.55 and abs(pz - target_z) < 0.56 for pm, pz in placed):
                    target_z += 0.58
                lat_zs[idx] = min(self._track_width() - 0.4, target_z)
                placed.append((m, lat_zs[idx]))
        elif self._event == "4x400m":
            # prima frazione (fino a 500 m) in corsia, poi rientro graduale alla corda
            order = sorted(range(n), key=lambda i: -meters[i])
            placed = []
            for idx in order:
                m = meters[idx]
                if m <= 400.0:
                    lat_zs[idx] = self._lane_z(idx)
                else:
                    merge = _clamp((m - 400.0) / 80.0, 0.0, 1.0)
                    target_z = _lerp(self._lane_z(idx), 0.55, merge)
                    while any(abs(pm - m) < 1.55 and abs(pz - target_z) < 0.56 for pm, pz in placed):
                        target_z += 0.58
                    lat_zs[idx] = min(self._track_width() - 0.4, target_z)
                placed.append((m, lat_zs[idx]))

        poses = []
        ref_lat = 0.52 if self._event == "1500m" else None
        for i, m in enumerate(meters):
            rl = 0.55 if (self._event == "4x400m" and m > 400.0) else ref_lat
            poses.append(oval_pose(d - m, lat_zs[i], ref_lat=rl))
        return poses

    def _finish_hold(self) -> float:
        """Quanto indugiare sul fotofinish prima di tagliare sul vincitore: il distacco 1°-2° è
        già noto (il modello ha calcolato il risultato prima della messa in scena), quindi la
        regia può decidere in anticipo invece di reagire a un arrivo che non vede ancora."""
        margin = self._finish_margin
        if margin < 0.12:
            return 1.7
        if margin < 0.4:
            return 1.0
        return 0.55

    # ---- regia multi-camera TV
    def _make_camera(self, meters: Sequence[float], poses: Sequence[Tuple[float, float, float, float]], w: int, h: int) -> Camera:
        d = self._distance
        tw = self._track_width()
        leader = max(meters) if meters else 0.0
        leader_idx = max(range(len(meters)), key=lambda i: meters[i]) if meters else 0

        if self._replay_active:
            self._cam_label = "REPLAY"
            return self._replay_camera(poses, leader_idx, w, h)

        if not self._is_oval_race():
            mine = [m for m, r in zip(meters, self._runners) if r["s"].is_player]
            focus = (0.68 * leader + 0.32 * mine[0]) if (mine and leader - mine[0] < 12.0) else leader
            start_x = STRAIGHT - 100.0
            blk_pos = (start_x + 3.45, 0.80, tw + 2.75)
            blk_tgt = (start_x - 0.55, 0.46, tw * 0.46)
            fx = STRAIGHT - (100.0 - _clamp(focus, 2.0, d - 4.0))
            u_d = _smoothstep((leader - 2.0) / 24.0)
            bcast_pos = (fx + _lerp(5.0, CAM_BACK, u_d), _lerp(1.55, CAM_HEIGHT, u_d), tw + _lerp(5.8, CAM_SIDE, u_d))
            bcast_tgt = (fx - _lerp(2.2, 3.0, u_d), _lerp(0.75, 0.90, u_d), tw * 0.46)
            bcast_fov = _lerp(28.0, FOV_DEG, u_d)
            fin_pos = (STRAIGHT + 5.6, 3.15, tw + 12.8)
            fin_tgt = (STRAIGHT - 1.4, 0.92, tw * 0.44)

            if self._t < GUN_AT + 0.35 and leader < 5.0:
                self._cam_label = "BLOCCHI"
                return Camera(blk_pos, blk_tgt, 31.0, w, h)
            hold = self._finish_hold()
            if self.race_time > self._winner_time + hold * self._scale:
                self._cam_label = "VINCITORE"
                wx, wz, _, _ = poses[leader_idx]
                w_blend = _smoothstep((self.race_time - (self._winner_time + hold * self._scale)) / (0.30 * self._scale))
                w_pos = _lerp3(fin_pos, (wx + 4.0, 1.44, wz + 3.4), w_blend)
                w_tgt = _lerp3(fin_tgt, (wx - 0.35, 1.15, wz), w_blend)
                return Camera(w_pos, w_tgt, _lerp(26.5, 25.5, w_blend), w, h)
            if leader >= d - 24.0:
                # raccordo fluido tra ripresa laterale e primo piano angolato sul fotofinish
                f_blend = _smoothstep((leader - (d - 24.0)) / 10.0)
                self._cam_label = "FOTOFINISH" if f_blend > 0.45 else "TELECAMERA DIRETTA"
                return Camera(_lerp3(bcast_pos, fin_pos, f_blend), _lerp3(bcast_tgt, fin_tgt, f_blend), _lerp(bcast_fov, 26.5, f_blend), w, h)
            if leader < 26.0:
                c_blend = _smoothstep((self._t - (GUN_AT + 0.35)) / 0.55)
                self._cam_label = "SPINTA" if c_blend > 0.35 else "BLOCCHI"
                return Camera(_lerp3(blk_pos, bcast_pos, c_blend), _lerp3(blk_tgt, bcast_tgt, c_blend), _lerp(31.0, bcast_fov, c_blend), w, h)
            self._cam_label = "TELECAMERA DIRETTA"
            return Camera(bcast_pos, bcast_tgt, bcast_fov, w, h)

        # ---- Regia per gare su pista ovale (400m, 1500m, 4x100m, 4x400m)
        lx, lz, lyaw, _ = poses[leader_idx]
        fwd_x, fwd_z = math.cos(lyaw), math.sin(lyaw)
        center_x, center_z = STRAIGHT * 0.5, -R_IN
        in_x, in_z = _norm((center_x - lx, 0.0, center_z - lz))[0], _norm((center_x - lx, 0.0, center_z - lz))[2]

        # Post-arrivo: Winner-Cam ravvicinata (il distacco 1°-2° è già noto: fotofinish più lungo se l'arrivo è in volata)
        if self.race_time > self._winner_time + self._finish_hold() * self._scale:
            self._cam_label = "WINNER-CAM"
            pos = (lx + 4.4 * fwd_x - 4.0 * in_x, 1.48, lz + 4.4 * fwd_z - 4.0 * in_z)
            target = (lx - 0.8 * fwd_x, 1.12, lz - 0.8 * fwd_z)
            return Camera(pos, target, 27.0, w, h)

        # Volata sul rettilineo finale (ultimi 55m): Finish-Cam dal traguardo
        if leader >= d - 55.0:
            self._cam_label = "FINISH-CAM"
            pos = (STRAIGHT + 9.5, 4.6, tw + 15.5)
            target = (_lerp(lx, STRAIGHT - 1.5, 0.55), 1.0, tw * 0.35)
            return Camera(pos, target, 29.0, w, h)

        # Partenza: inquadratura ampia dal lato interno sul gruppo alla linea di partenza
        if self._t < GUN_AT + 0.8:
            self._cam_label = "START-CAM"
            pos = (lx + 11.0 * fwd_x + 16.0 * in_x, 5.2, lz + 11.0 * fwd_z + 16.0 * in_z)
            target = (lx - 2.0 * fwd_x, 0.9, lz - 2.0 * fwd_z)
            return Camera(pos, target, 30.0, w, h)

        # Ripresa dinamica dall'interno pista verso il gruppo e le tribune curve sullo sfondo (stile 1500m TV!)
        self._cam_label = "OVAL-CAM"
        # in rettilineo/curva la camera sta sul prato interno guardando verso il gruppo e le tribune esterne
        pos = (lx + 7.2 * fwd_x + 15.2 * in_x, 4.6, lz + 7.2 * fwd_z + 15.2 * in_z)
        target = (lx - 1.2 * fwd_x, 0.95, lz - 1.2 * fwd_z)
        return Camera(pos, target, 28.0, w, h)

    # ---- primitive 3D (delegate alle funzioni condivise)
    def _poly(self, p: QPainter, cam: Camera, pts: Sequence[Vec], color) -> None:
        draw_poly(p, cam, pts, color)

    def _textured_quad(self, p: QPainter, cam: Camera, corners: Sequence[Vec], pm: QPixmap) -> None:
        draw_textured_quad(p, cam, corners, pm)

    def _textured_ground_quad(self, p: QPainter, cam: Camera, corners: Sequence[Vec], pm: QPixmap, fallback_col: str) -> None:
        draw_textured_ground_quad(p, cam, corners, pm, fallback_col)

    def _line3(self, p: QPainter, cam: Camera, a: Vec, b: Vec, radius: float, color: QColor) -> None:
        draw_line3(p, cam, a, b, radius, color)

    def _shaded_limb(
        self, p: QPainter, cam: Camera, a: Vec, b: Vec, r0: float, r1: float, color: QColor, lit_side: float = 1.0,
    ) -> None:
        draw_shaded_limb(p, cam, a, b, r0, r1, color, lit_side)

    def _board(self, idx: int) -> QPixmap:
        return get_sponsor_board(idx)

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

    def _clock_face_pm(self, clock_txt: str) -> QPixmap:
        key = f"clk:{clock_txt}"
        pm = self._scoreboard_cache.get(key)
        if pm is None:
            pm = QPixmap(128, 56)
            pm.fill(QColor("#090f1d"))
            q = QPainter(pm)
            f = QFont("Arial", 22)
            f.setBold(True)
            q.setFont(f)
            q.setPen(QColor("#facc15"))
            q.drawText(QRectF(4, 4, 120, 48), Qt.AlignmentFlag.AlignCenter, clock_txt)
            q.end()
            self._scoreboard_cache[key] = pm
        return pm

    # ---- scenografia completa dell'ovale a 360°
    def _draw_sky(self, p: QPainter, w: int, h: int) -> None:
        rain = self._weather == WeatherCondition.PIOGGIA
        hot = self._weather == WeatherCondition.CALDO
        evening = self._is_evening_final() or self._season_phase == SeasonPhase.INDOOR

        sky = QLinearGradient(0, 0, 0, h * 0.56)
        if evening:
            sky.setColorAt(0.0, QColor("#030712"))
            sky.setColorAt(0.55, QColor("#0f172a"))
            sky.setColorAt(1.0, QColor("#1e293b"))
        elif rain:
            sky.setColorAt(0.0, QColor("#334155"))
            sky.setColorAt(0.6, QColor("#5d6d82"))
            sky.setColorAt(1.0, QColor("#94a3b8"))
        elif hot:
            sky.setColorAt(0.0, QColor("#1e3a8a"))
            sky.setColorAt(0.58, QColor("#60a5fa"))
            sky.setColorAt(1.0, QColor("#fdba74"))
        else:
            # tardo pomeriggio dorato stile giochi sportivi 2010
            sky.setColorAt(0.0, QColor("#1e3a8a"))
            sky.setColorAt(0.56, QColor("#60a5fa"))
            sky.setColorAt(1.0, QColor("#fed7aa"))
        p.fillRect(0, 0, w, h, QBrush(sky))
        p.setPen(Qt.PenStyle.NoPen)
        p.fillRect(0, int(h * 0.36), w, int(h * 0.64), QColor("#14221a" if evening else "#24522e"))

        if not evening and not rain:
            sun = QRadialGradient(w * 0.14, h * 0.13, w * 0.28)
            sun.setColorAt(0.0, QColor(255, 248, 210, 175))
            sun.setColorAt(0.42, QColor(253, 224, 150, 75))
            sun.setColorAt(1.0, QColor(255, 250, 220, 0))
            p.setBrush(QBrush(sun))
            p.drawEllipse(QPointF(w * 0.14, h * 0.13), w * 0.28, w * 0.28)
            for cx, cy, rw, rh in ((0.36, 0.11, 0.12, 0.032), (0.68, 0.08, 0.15, 0.036), (0.85, 0.14, 0.10, 0.025)):
                cloud = QRadialGradient(w * cx, h * cy, w * rw)
                cloud.setColorAt(0.0, QColor(255, 250, 240, 75))
                cloud.setColorAt(1.0, QColor(255, 255, 255, 0))
                p.setBrush(QBrush(cloud))
                p.drawEllipse(QPointF(w * cx, h * cy), w * rw, h * rh)

    def _draw_stand_section(
        self, p: QPainter, cam: Camera, a: Vec, b: Vec, out_a: Vec, out_b: Vec,
        crowd_pm: QPixmap, big: bool, evening: bool, rain: bool,
        crowd_dof_pm: Optional[QPixmap] = None,
    ) -> None:
        """Disegna un blocco di tribuna (muretto + corrimano + 1°/2° anello DoF + tettoia)."""
        ca = cam.to_cam(a)
        cb = cam.to_cam(b)
        if ca[2] < -12.0 and cb[2] < -12.0:
            return
        # basso muretto in cemento con fascia superiore
        self._poly(p, cam, [(a[0], 0.0, a[2]), (b[0], 0.0, b[2]), (b[0], 1.35, b[2]), (a[0], 1.35, a[2])], "#475569" if not evening else "#334155")
        self._line3(p, cam, (a[0], 1.35, a[2]), (b[0], 1.35, b[2]), 0.06, QColor("#cbd5e1"))
        # primo anello
        p0 = (a[0], 1.35, a[2])
        p1 = (b[0], 1.35, b[2])
        d_scale = 0.45 if big else 1.0
        m_a = (_lerp(a[0], out_a[0], d_scale), 8.2, _lerp(a[2], out_a[2], d_scale))
        m_b = (_lerp(b[0], out_b[0], d_scale), 8.2, _lerp(b[2], out_b[2], d_scale))
        self._poly(p, cam, [p0, p1, m_b, m_a], "#334155" if evening else "#475569")
        self._textured_quad(p, cam, [m_a, m_b, p1, p0], crowd_pm)
        if big:
            n_a = (_lerp(a[0], out_a[0], 0.50), 9.5, _lerp(a[2], out_a[2], 0.50))
            n_b = (_lerp(b[0], out_b[0], 0.50), 9.5, _lerp(b[2], out_b[2], 0.50))
            self._poly(p, cam, [m_a, m_b, n_b, n_a], "#1e293b")
            self._line3(p, cam, n_a, n_b, 0.07, QColor("#fbbf24" if evening else "#94a3b8"))
            t_a = (out_a[0], 18.5, out_a[2])
            t_b = (out_b[0], 18.5, out_b[2])
            self._poly(p, cam, [n_a, n_b, t_b, t_a], "#293548" if evening else "#3b495e")
            self._textured_quad(p, cam, [t_a, t_b, n_b, n_a], crowd_dof_pm or crowd_pm)
            # fascia superiore, nervature e tettoia
            r_back_a = (out_a[0], 21.0, out_a[2])
            r_back_b = (out_b[0], 21.0, out_b[2])
            r_front_a = (_lerp(a[0], out_a[0], 0.25), 19.6, _lerp(a[2], out_a[2], 0.25))
            r_front_b = (_lerp(b[0], out_b[0], 0.25), 19.6, _lerp(b[2], out_b[2], 0.25))
            self._poly(p, cam, [t_a, t_b, r_back_b, r_back_a], "#0f172a")
            self._poly(p, cam, [r_back_a, r_back_b, r_front_b, r_front_a], "#94a3b8" if not rain else "#475569")
            self._line3(p, cam, r_back_a, r_front_a, 0.09, QColor("#64748b"))
            if evening:
                self._line3(p, cam, r_front_a, r_front_b, 0.20, QColor("#fef08a"))

    def _draw_oval_stadium(self, p: QPainter, cam: Camera) -> None:
        tw = self._track_width()
        rain = self._weather == WeatherCondition.PIOGGIA
        evening = self._is_evening_final()
        big = self._is_evening_final()
        crowd_pm = self._crowd_pm(dark=(rain or evening), dof_blur=False)
        crowd_dof = self._crowd_pm(dark=(rain or evening), dof_blur=True)
        c1, c2, c3 = self._track_colors()

        # ---- 1. Tribune 360° intorno all'ovale
        stand_depth = 26.0 if big else 13.0
        # Rettilineo opposto (z < -2*R_IN - tw - 4)
        z_in_b = -2.0 * R_IN - tw - 4.0
        for s_idx in range(4):
            x0, x1 = s_idx * (STRAIGHT / 4.0), (s_idx + 1) * (STRAIGHT / 4.0) + 0.15
            self._draw_stand_section(
                p, cam, (x0, 0.0, z_in_b), (x1, 0.0, z_in_b),
                (x0, 0.0, z_in_b - stand_depth), (x1, 0.0, z_in_b - stand_depth),
                crowd_pm, big, evening, rain, crowd_dof,
            )
        # Rettilineo principale (z > tw + 4) — visibile quando si corre nel rettilineo opposto
        z_in_h = tw + 4.5
        for s_idx in range(4):
            x0, x1 = (s_idx + 1) * (STRAIGHT / 4.0) + 0.15, s_idx * (STRAIGHT / 4.0)
            self._draw_stand_section(
                p, cam, (x0, 0.0, z_in_h), (x1, 0.0, z_in_h),
                (x0, 0.0, z_in_h + stand_depth), (x1, 0.0, z_in_h + stand_depth),
                crowd_pm, big, evening, rain, crowd_dof,
            )
        # Curve di testata (Curva 1 a x=STRAIGHT, Curva 2 a x=0) — sfumate leggermente con DoF
        r_s_in = R_IN + tw + 4.2
        r_s_out = r_s_in + stand_depth
        for cx, a_start in ((STRAIGHT, -math.pi * 0.5), (0.0, math.pi * 0.5)):
            steps = 8
            for k in range(steps):
                a0 = a_start + (math.pi * k) / steps
                a1 = a_start + (math.pi * (k + 1)) / steps
                p0 = (cx + r_s_in * math.cos(a0), 0.0, -R_IN + r_s_in * math.sin(a0))
                p1 = (cx + r_s_in * math.cos(a1), 0.0, -R_IN + r_s_in * math.sin(a1))
                o0 = (cx + r_s_out * math.cos(a0), 0.0, -R_IN + r_s_out * math.sin(a0))
                o1 = (cx + r_s_out * math.cos(a1), 0.0, -R_IN + r_s_out * math.sin(a1))
                self._draw_stand_section(p, cam, p0, p1, o0, o1, crowd_dof, big, evening, rain, crowd_dof)

        # Maxischermo sopra la Curva 2 (lato partenza 100m, leggermente sfalsato rispetto al centro)
        sb_a = math.pi * 1.18
        sb_r = r_s_in + (14.0 if big else 8.0)
        sx0 = sb_r * math.cos(sb_a - 0.14)
        sz0 = -R_IN + sb_r * math.sin(sb_a - 0.14)
        sx1 = sb_r * math.cos(sb_a + 0.14)
        sz1 = -R_IN + sb_r * math.sin(sb_a + 0.14)
        y_lo = 13.5 if big else 7.8
        self._poly(p, cam, [(sx0, y_lo, sz0), (sx1, y_lo, sz1), (sx1, y_lo + 6.2, sz1), (sx0, y_lo + 6.2, sz0)], "#0f172a")
        self._textured_quad(p, cam, [(sx0, y_lo + 6.2, sz0), (sx1, y_lo + 6.2, sz1), (sx1, y_lo, sz1), (sx0, y_lo, sz0)], self._scoreboard_pm(format_race_time(self.race_clock)))

        # Torri faro ai quattro angoli dello stadio
        pylon_h = 34.0 if big else 27.0
        for px_t, pz_t in ((-28.0, z_in_b - stand_depth * 0.72), (STRAIGHT + 28.0, z_in_b - stand_depth * 0.72), (-28.0, z_in_h + stand_depth * 0.72), (STRAIGHT + 28.0, z_in_h + stand_depth * 0.72)):
            draw_floodlight_pylon_3d(p, cam, (px_t, 0.0, pz_t), (STRAIGHT * 0.5 - px_t, 0.0, -R_IN - pz_t), height=pylon_h, evening=evening)

        # Fascia esterna intorno all'ovale (disegnata PRIMA del prato centrale così non lo copre!)
        out_col = "#1e293b" if evening else "#25582e"
        self._poly(p, cam, [(-48.0, -0.02, -2.0 * R_IN - 22.0), (STRAIGHT + 48.0, -0.02, -2.0 * R_IN - 22.0), (STRAIGHT + 48.0, -0.02, tw + 22.0), (-48.0, -0.02, tw + 22.0)], out_col)

        # ---- 2. Prato centrale e lunette (D-zones)
        band = 14.0
        xb = 0.0
        while xb < STRAIGHT:
            x1 = min(STRAIGHT, xb + band + 0.1)
            light = int(xb // band) % 2 == 0
            g_hex = "#2d7539" if light else "#348440"
            if rain or evening:
                g_hex = QColor(g_hex).darker(122).name()
            self._textured_ground_quad(
                p, cam,
                [(xb, 0.0, -2.0 * R_IN), (x1, 0.0, -2.0 * R_IN), (x1, 0.0, 0.0), (xb, 0.0, 0.0)],
                self._grass_tile(g_hex), g_hex,
            )
            xb += band
        # Linee bianche campo centrale
        self._poly(p, cam, [(4.0, 0.008, -58.0), (STRAIGHT - 4.0, 0.008, -58.0), (STRAIGHT - 4.0, 0.008, -57.7), (4.0, 0.008, -57.7)], QColor(248, 250, 252, 95))
        self._poly(p, cam, [(4.0, 0.008, -14.3), (STRAIGHT - 4.0, 0.008, -14.3), (STRAIGHT - 4.0, 0.008, -14.0), (4.0, 0.008, -14.0)], QColor(248, 250, 252, 95))
        # Lunette (sintetico scuro nei grandi stadi, erba negli altri)
        d_col = "#334155" if evening else ("#2e7a3b" if not rain else "#225a2c")
        for cx, a_start in ((STRAIGHT, -math.pi * 0.5), (0.0, math.pi * 0.5)):
            steps = 12
            for k in range(steps):
                a0 = a_start + (math.pi * k) / steps
                a1 = a_start + (math.pi * (k + 1)) / steps
                self._poly(
                    p, cam,
                    [(cx, 0.0, -R_IN), (cx + R_IN * math.cos(a0), 0.0, -R_IN + R_IN * math.sin(a0)), (cx + R_IN * math.cos(a1), 0.0, -R_IN + R_IN * math.sin(a1))],
                    d_col,
                )

        # Attrezzi reali nelle lunette interne (materasso salto in alto + gabbia lanci)
        # Materasso salto in alto nella lunetta est (x ~ STRAIGHT + 14)
        hx0, hz0 = STRAIGHT + 12.0, -R_IN - 2.0
        self._poly(p, cam, [(hx0, 0.0, hz0 - 3.0), (hx0 + 4.0, 0.0, hz0 - 3.0), (hx0 + 4.0, 0.72, hz0 + 3.0), (hx0, 0.72, hz0 + 3.0)], "#1d4ed8")
        self._poly(p, cam, [(hx0, 0.72, hz0 - 3.0), (hx0 + 4.0, 0.72, hz0 - 3.0), (hx0 + 4.0, 0.72, hz0 + 3.0), (hx0, 0.72, hz0 + 3.0)], "#2563eb")
        for rz_p in (hz0 - 2.4, hz0 + 2.4):
            self._line3(p, cam, (hx0 - 0.3, 0.0, rz_p), (hx0 - 0.3, 2.5, rz_p), 0.06, QColor("#e2e8f0"))
        self._line3(p, cam, (hx0 - 0.3, 2.25, hz0 - 2.4), (hx0 - 0.3, 2.25, hz0 + 2.4), 0.03, QColor("#facc15"))
        # Gabbia lanci nella lunetta ovest (x ~ -16)
        gx0, gz0 = -16.0, -R_IN
        cage_pts = [
            (gx0 + 4.2 * math.cos(math.pi * (0.65 + k * 0.175)), 0.0, gz0 + 4.2 * math.sin(math.pi * (0.65 + k * 0.175)))
            for k in range(5)
        ]
        for k in range(4):
            gp0, gp1 = cage_pts[k], cage_pts[k + 1]
            self._poly(p, cam, [gp0, gp1, (gp1[0], 5.2, gp1[2]), (gp0[0], 5.2, gp0[2])], QColor(15, 23, 42, 65))
            self._line3(p, cam, (gp0[0], 5.2, gp0[2]), (gp1[0], 5.2, gp1[2]), 0.06, QColor("#cbd5e1"))
            self._line3(p, cam, (gp0[0], 2.6, gp0[2]), (gp1[0], 2.6, gp1[2]), 0.04, QColor("#94a3b8"))
        for gp in cage_pts:
            self._line3(p, cam, gp, (gp[0], 5.2, gp[2]), 0.07, QColor("#94a3b8"))

        # ---- 3. Pista 400m completa (2 rettilinei + bretella 100m + 2 curve)
        n = len(self._runners)
        # Rettilineo principale + bretella partenza 100 m (-22m .. STRAIGHT)
        for seg_x0 in (-22.0, 0.0, 21.0, 42.0, 63.0):
            seg_x1 = 0.0 if seg_x0 < 0 else min(STRAIGHT, seg_x0 + 21.2)
            for i in range(n):
                z0, z1 = i * LANE_W, (i + 1) * LANE_W
                col = c1 if i % 2 == 0 else c2
                self._textured_ground_quad(
                    p, cam,
                    [(seg_x0, 0.004, z0), (seg_x1, 0.004, z0), (seg_x1, 0.004, z1), (seg_x0, 0.004, z1)],
                    self._track_tile(col), col,
                )
        # Rettilineo opposto
        for seg_x0 in (0.0, 21.0, 42.0, 63.0):
            seg_x1 = min(STRAIGHT, seg_x0 + 21.2)
            for i in range(n):
                z0 = -2.0 * R_IN - (i + 1) * LANE_W
                z1 = -2.0 * R_IN - i * LANE_W
                col = c1 if i % 2 == 0 else c2
                self._textured_ground_quad(
                    p, cam,
                    [(seg_x0, 0.004, z0), (seg_x1, 0.004, z0), (seg_x1, 0.004, z1), (seg_x0, 0.004, z1)],
                    self._track_tile(col), col,
                )
        # Curve 1 e 2 (16 spicchi ciascuna per raccordi lisci anche da vicino)
        for cx, a_start in ((STRAIGHT, -math.pi * 0.5), (0.0, math.pi * 0.5)):
            steps = 16
            for k in range(steps):
                a0 = a_start + (math.pi * k) / steps
                a1 = a_start + (math.pi * (k + 1)) / steps
                c0, s0 = math.cos(a0), math.sin(a0)
                c1_, s1_ = math.cos(a1), math.sin(a1)
                # pista intera + linee bianche di corsia essenziali
                self._textured_ground_quad(
                    p, cam,
                    [
                        (cx + R_IN * c0, 0.004, -R_IN + R_IN * s0),
                        (cx + (R_IN + tw) * c0, 0.004, -R_IN + (R_IN + tw) * s0),
                        (cx + (R_IN + tw) * c1_, 0.004, -R_IN + (R_IN + tw) * s1_),
                        (cx + R_IN * c1_, 0.004, -R_IN + R_IN * s1_),
                    ],
                    self._track_tile(c1 if k % 2 == 0 else c2), c1 if k % 2 == 0 else c2,
                )
                # cordolo bianco interno in curva
                self._poly(
                    p, cam,
                    [
                        (cx + (R_IN - 0.18) * c0, 0.012, -R_IN + (R_IN - 0.18) * s0),
                        (cx + R_IN * c0, 0.012, -R_IN + R_IN * s0),
                        (cx + R_IN * c1_, 0.012, -R_IN + R_IN * s1_),
                        (cx + (R_IN - 0.18) * c1_, 0.012, -R_IN + (R_IN - 0.18) * s1_),
                    ],
                    "#f8fafc",
                )
                # linee bianche corsie in curva (1..n)
                for li in range(1, n + 1):
                    rl = R_IN + li * LANE_W
                    self._line3(
                        p, cam,
                        (cx + rl * c0, 0.012, -R_IN + rl * s0),
                        (cx + rl * c1_, 0.012, -R_IN + rl * s1_),
                        0.025, QColor("#f8fafc"),
                    )

        # ---- 4. Linee corsie rettilinei, partenza, traguardo e cartelloni LED
        for i in range(n + 1):
            z_h = i * LANE_W
            z_b = -2.0 * R_IN - i * LANE_W
            self._poly(p, cam, [(-22.0, 0.012, z_h - 0.025), (STRAIGHT, 0.012, z_h - 0.025), (STRAIGHT, 0.012, z_h + 0.025), (-22.0, 0.012, z_h + 0.025)], "#f8fafc")
            self._poly(p, cam, [(0.0, 0.012, z_b - 0.025), (STRAIGHT, 0.012, z_b - 0.025), (STRAIGHT, 0.012, z_b + 0.025), (0.0, 0.012, z_b + 0.025)], "#f8fafc")

        # Linea bianca di partenza 100 m (x = STRAIGHT - 100) e numeri corsia
        if not self._is_oval_race():
            sx0 = STRAIGHT - 100.0
            self._poly(p, cam, [(sx0 - 0.04, 0.013, 0.0), (sx0 + 0.04, 0.013, 0.0), (sx0 + 0.04, 0.013, tw), (sx0 - 0.04, 0.013, tw)], "#ffffff")
            for i in range(n):
                zc = self._lane_z(i)
                self._textured_quad(
                    p, cam,
                    [(sx0 + 0.45, 0.014, zc - 0.32), (sx0 + 1.05, 0.014, zc - 0.32), (sx0 + 1.05, 0.014, zc + 0.32), (sx0 + 0.45, 0.014, zc + 0.32)],
                    self._lane_num_pm(i + 1),
                )
        elif self._event == "1500m":
            # linea di partenza a cascata dei 1500m (300m prima del traguardo = in controrettilineo)
            pts_w = [oval_pose(1500.0, i * LANE_W, ref_lat=0.52)[:2] for i in range(n + 1)]
            for k in range(n):
                self._line3(p, cam, (pts_w[k][0], 0.014, pts_w[k][1]), (pts_w[k + 1][0], 0.014, pts_w[k + 1][1]), 0.04, QColor("#ffffff"))

        # Traguardo fisso su x = STRAIGHT (rettilineo principale)
        self._poly(p, cam, [(STRAIGHT - 0.04, 0.014, 0.0), (STRAIGHT + 0.04, 0.014, 0.0), (STRAIGHT + 0.04, 0.014, tw), (STRAIGHT - 0.04, 0.014, tw)], "#ffffff")
        cells = max(4, int(tw / 0.28))
        cw = tw / cells
        for j in range(cells):
            for k in range(2):
                x0 = STRAIGHT + 0.04 + k * 0.24
                self._poly(p, cam, [(x0, 0.014, j * cw), (x0 + 0.24, 0.014, j * cw), (x0 + 0.24, 0.014, (j + 1) * cw), (x0, 0.014, (j + 1) * cw)], "#f8fafc" if (j + k) % 2 == 0 else "#0f172a")

        # Cartelloni LED sempre sullo sfondo rispetto alla camera (mai davanti alle corsie né specchiati)
        seg = 7.0
        bx = -14.0
        idx = 0
        cam_inside = cam.pos[2] < 0.0
        z_back_wall = -2.0 * R_IN - tw - 3.85
        while bx < STRAIGHT:
            bx1 = min(STRAIGHT, bx + seg - 0.15)
            pm = self._board(idx)
            if not cam_inside:
                # ombra di contatto a terra + cartelloni lungo il bordo interno + fascia sul muretto opposto
                self._poly(p, cam, [(bx, 0.015, -1.4), (bx1, 0.015, -1.4), (bx1, 0.015, -0.9), (bx, 0.015, -0.9)], QColor(15, 23, 42, 70))
                self._textured_quad(p, cam, [(bx, 0.85, -1.4), (bx1, 0.85, -1.4), (bx1, 0.04, -1.4), (bx, 0.04, -1.4)], pm)
                if bx >= 0.0:
                    self._textured_quad(p, cam, [(bx, 1.05, z_back_wall), (bx1, 1.05, z_back_wall), (bx1, 0.10, z_back_wall), (bx, 0.10, z_back_wall)], self._board(idx + 3))
            elif bx >= 0.0:
                zb = -2.0 * R_IN - tw - 1.6
                zh = tw + 1.8
                self._textured_quad(p, cam, [(bx, 0.90, zb), (bx1, 0.90, zb), (bx1, 0.04, zb), (bx, 0.04, zb)], pm)
                self._textured_quad(p, cam, [(bx1, 0.90, zh), (bx, 0.90, zh), (bx, 0.04, zh), (bx1, 0.04, zh)], pm)
            bx += seg
            idx += 1

    def _draw_official(self, p: QPainter, cam: Camera, x: float, z: float, cap_col: str = "#f8fafc") -> None:
        draw_official_3d(p, cam, x, z, cap_col)

    def _draw_props(self, p: QPainter, cam: Camera, poses: Sequence[Tuple[float, float, float, float]]) -> None:
        n = len(self._runners)
        tw = self._track_width()

        # blocchi di partenza dettagliati (binario centrale + pedali inclinati), sparo e coni nei 100 m
        if not self._is_oval_race():
            sx0 = STRAIGHT - 100.0
            # tacche metriche 20/40/60/80m, anemometro ai 50m e carrello camera su binario TV lungo il cordolo
            for dist_m in (20.0, 40.0, 60.0, 80.0):
                tx = sx0 + dist_m
                self._poly(p, cam, [(tx - 0.05, 0.013, -0.35), (tx + 0.05, 0.013, -0.35), (tx + 0.05, 0.013, 0.0), (tx - 0.05, 0.013, 0.0)], "#f8fafc")
                self._poly(p, cam, [(tx - 0.05, 0.013, tw), (tx + 0.05, 0.013, tw), (tx + 0.05, 0.013, tw + 0.35), (tx - 0.05, 0.013, tw + 0.35)], "#f8fafc")
            # anemometro ai 50m
            wx_an = sx0 + 50.0
            self._line3(p, cam, (wx_an, 0.0, -0.85), (wx_an, 1.25, -0.85), 0.035, QColor("#cbd5e1"))
            self._poly(p, cam, [(wx_an - 0.16, 1.22, -0.92), (wx_an + 0.16, 1.22, -0.92), (wx_an + 0.16, 1.32, -0.78), (wx_an - 0.16, 1.32, -0.78)], "#f59e0b")
            # binario e dolly telecamera mobile sul lato interno
            self._line3(p, cam, (sx0 + 2.0, 0.05, -0.95), (STRAIGHT - 4.0, 0.05, -0.95), 0.03, QColor("#64748b"))
            dolly_x = sx0 + _clamp(max((p_[0] - sx0 for p_ in poses), default=0.0), 3.0, 92.0)
            self._poly(p, cam, [(dolly_x - 0.35, 0.06, -1.10), (dolly_x + 0.35, 0.06, -1.10), (dolly_x + 0.35, 0.38, -0.80), (dolly_x - 0.35, 0.38, -0.80)], "#1e293b")
            self._poly(p, cam, [(dolly_x - 0.18, 0.38, -1.02), (dolly_x + 0.22, 0.38, -1.02), (dolly_x + 0.22, 0.62, -0.82), (dolly_x - 0.18, 0.62, -0.82)], "#334155")
            if cam.to_cam((sx0, 0.0, tw * 0.5))[2] > -10.0:
                for i in range(n):
                    z = self._lane_z(i)
                    self._poly(p, cam, [(sx0 - 0.90, 0.018, z - 0.12), (sx0 - 0.78, 0.018, z - 0.12), (sx0 - 0.78, 0.03, z + 0.12), (sx0 - 0.90, 0.03, z + 0.12)], "#334155")
                    self._line3(p, cam, (sx0 - 0.88, 0.035, z), (sx0 - 0.14, 0.035, z), 0.035, QColor("#cbd5e1"))
                    for px_off, pz_s in ((-0.35, 0.11), (-0.64, -0.11)):
                        bx = sx0 + px_off
                        pz0, pz1 = z + pz_s - 0.08, z + pz_s + 0.08
                        self._poly(p, cam, [(bx - 0.13, 0.02, pz0), (bx + 0.02, 0.15, pz0), (bx + 0.02, 0.15, pz1), (bx - 0.13, 0.02, pz1)], "#1e293b")
                        self._poly(p, cam, [(bx - 0.04, 0.09, pz0 + 0.01), (bx + 0.01, 0.14, pz0 + 0.01), (bx + 0.01, 0.14, pz1 - 0.01), (bx - 0.04, 0.09, pz1 - 0.01)], "#f59e0b")
                    self._textured_quad(p, cam, [(sx0 - 1.25, 0.34, z + 0.38), (sx0 - 1.25, 0.34, z + 0.12), (sx0 - 1.25, 0.01, z + 0.12), (sx0 - 1.25, 0.01, z + 0.38)], self._cone_pm(i + 1))
                self._draw_official(p, cam, sx0 - 2.6, -1.8)
                # pistola starter alzata al Pronti + vampata/fumo allo sparo
                if self._t >= GUN_AT * 0.45 and self.race_time <= 0.45:
                    self._line3(p, cam, (sx0 - 2.6, 1.42, -1.72), (sx0 - 2.45, 1.88, -1.62), 0.038, QColor("#e2b48b"))
                    if 0.0 <= self.race_time <= 0.42:
                        gc = cam.to_cam((sx0 - 2.42, 1.98, -1.60))
                        if gc[2] >= NEAR:
                            gx_, gy_ = cam.proj(gc)
                            sr_g = max(4.0, (0.28 + self.race_time * 1.4) * cam.f / gc[2])
                            sm = QRadialGradient(gx_, gy_, sr_g)
                            sm.setColorAt(0.0, QColor(255, 250, 220, 230 if self.race_time < 0.12 else 110))
                            sm.setColorAt(0.45, QColor(248, 250, 252, 130))
                            sm.setColorAt(1.0, QColor(248, 250, 252, 0))
                            p.setBrush(QBrush(sm))
                            p.setPen(Qt.PenStyle.NoPen)
                            p.drawEllipse(QPointF(gx_, gy_), sr_g, sr_g)

        # portale d'arrivo fisso a x = STRAIGHT con torretta fotofinish e cronometri bordo pista
        if cam.to_cam((STRAIGHT, 2.0, tw * 0.5))[2] > -15.0:
            for z in (-0.85, tw + 0.85):
                self._line3(p, cam, (STRAIGHT, 0.0, z), (STRAIGHT, 5.2, z), 0.14, QColor("#e2e8f0"))
                self._line3(p, cam, (STRAIGHT + 0.38, 0.0, z), (STRAIGHT + 0.38, 5.2, z), 0.075, QColor("#94a3b8"))
                self._line3(p, cam, (STRAIGHT, 2.6, z), (STRAIGHT + 0.38, 2.9, z), 0.04, QColor("#cbd5e1"))
            self._line3(p, cam, (STRAIGHT, 5.2, -0.85), (STRAIGHT, 5.2, tw + 0.85), 0.16, QColor("#e2e8f0"))
            self._textured_quad(p, cam, [(STRAIGHT, 5.15, tw + 0.85), (STRAIGHT, 5.15, -0.85), (STRAIGHT, 4.25, -0.85), (STRAIGHT, 4.25, tw + 0.85)], self._gantry_pm())
            # torretta e telecamera fotofinish sul lato interno
            self._line3(p, cam, (STRAIGHT, 0.0, -2.2), (STRAIGHT, 3.8, -2.2), 0.085, QColor("#cbd5e1"))
            self._poly(p, cam, [(STRAIGHT - 0.24, 3.7, -2.4), (STRAIGHT + 0.24, 3.7, -2.4), (STRAIGHT + 0.24, 4.15, -2.0), (STRAIGHT - 0.24, 4.15, -2.0)], "#facc15")
            self._poly(p, cam, [(STRAIGHT - 0.12, 3.8, -2.0), (STRAIGHT + 0.12, 3.8, -2.0), (STRAIGHT + 0.12, 4.02, -1.75), (STRAIGHT - 0.12, 4.02, -1.75)], "#0f172a")
            # cronometro digitale giallo a bordo pista (bordo interno + bordo esterno)
            clk_pm = self._clock_face_pm(format_race_time(self.race_clock))
            for cz in (-0.8, tw + 0.6):
                self._poly(p, cam, [(STRAIGHT - 0.45, 0.0, cz), (STRAIGHT + 0.45, 0.0, cz), (STRAIGHT + 0.45, 0.92, cz), (STRAIGHT - 0.45, 0.92, cz)], "#eab308")
                self._textured_quad(p, cam, [(STRAIGHT - 0.38, 0.78, cz + 0.03), (STRAIGHT + 0.38, 0.78, cz + 0.03), (STRAIGHT + 0.38, 0.18, cz + 0.03), (STRAIGHT - 0.38, 0.18, cz + 0.03)], clk_pm)
            self._draw_official(p, cam, STRAIGHT + 2.2, -2.8)

            if not any(self._has_finished(r) for r in self._runners):
                self._line3(p, cam, (STRAIGHT, 1.08, 0.0), (STRAIGHT, 1.08, tw), 0.020, QColor(239, 68, 68, 175))
            elif self.race_time < self._winner_time + 0.45 * self._scale:
                drop = _clamp((self.race_time - self._winner_time) / (0.45 * self._scale), 0.0, 1.0)
                self._line3(p, cam, (STRAIGHT, 1.08, 0.0), (STRAIGHT + 0.55, _lerp(0.95, 0.12, drop), 0.65), 0.018, QColor("#f8fafc"))
                self._line3(p, cam, (STRAIGHT, 1.08, tw), (STRAIGHT + 0.55, _lerp(0.95, 0.12, drop), tw - 0.65), 0.018, QColor("#f8fafc"))

    # ---- atleti 3D orientati lungo qualsiasi tangente dell'ovale
    def _draw_athlete(
        self,
        p: QPainter,
        cam: Camera,
        x: float,
        z: float,
        yaw: float,
        curv: float,
        meters_done: float,
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
        use_blocks = not self._is_pack_race()
        cf, sf = math.cos(yaw), math.sin(yaw)
        rf, rz_f = -sf, cf  # vettore unitario verso destra (esterno corsia)

        # lieve inclinazione verso l'interno quando si corre in curva!
        bank = -0.14 * ratio if curv > 0 else 0.0

        def to_world(lf: float, ly: float, lr: float) -> Vec:
            lr_b = lr + ly * bank
            return (x + lf * cf + lr_b * rf, ly, z + lf * sf + lr_b * rz_f)

        if self.race_time <= 0.0 and use_blocks:
            set_blend = _smoothstep((t_anim - GUN_AT * 0.48) / 0.36)
            breathe = 0.008 * math.sin(t_anim * 3.2) * (1.0 - set_blend)
            hip_h = _lerp(0.42, 0.85, set_blend) + breathe
            hip_lf = _lerp(-0.62, -0.52, set_blend)
            sh_lf = _lerp(-0.22, -0.06, set_blend)
            sh_y = _lerp(0.60, 0.68, set_blend) + breathe
            lean = math.atan2(sh_lf - hip_lf, sh_y - hip_h)
            crouch_mode = True
            drive_blend = 0.0
            clearance = 0.0
            standing_start = False
        elif self.race_time <= 0.0:
            # partenza in piedi nei 1500m
            hip_h, hip_lf, lean = 0.94, -0.10, 0.22
            crouch_mode = False
            standing_start = True
            drive_blend = 0.0
            clearance = 1.0
        else:
            crouch_mode = False
            standing_start = False
            clearance = _smoothstep(self.race_time / 0.45) if use_blocks else 1.0
            if not self._is_oval_race():
                # nei 100m: transizione fluida dai blocchi -> fase di spinta fino a ~26m -> lanciato -> affondo
                drive_blend = _smoothstep(meters_done / 26.0)
                finish_dip = 0.34 * _smoothstep((meters_done - (d - 1.6)) / 1.6) if meters_done <= d + 0.3 else 0.0
            else:
                drive_blend = _smoothstep(self.race_time / 1.6)
                finish_dip = 0.25 * _smoothstep((meters_done - (d - 1.4)) / 1.4) if meters_done <= d + 0.2 else 0.0
            crouch_lean = 1.24 if use_blocks else 0.22
            run_lean = 0.06 if celebrate else (_lerp(0.76 if use_blocks else 0.22, 0.12 + 0.12 * ratio, drive_blend) + finish_dip)
            lean = _lerp(crouch_lean, run_lean, clearance)
            bounce = 0.045 * abs(math.sin(phase)) * ratio * clearance
            hip_h = _lerp(0.84 if use_blocks else 0.93, 0.93 + bounce - (0.04 * (1.0 - drive_blend) if use_blocks else 0.0), clearance)
            hip_lf = _lerp(-0.46 if use_blocks else 0.0, 0.0, clearance)

        # ombra morbida proiettata dalla luce direzionale tardo-pomeridiana
        sun_dx, sun_dz = -0.34, -0.24
        sh_len = 0.56 + (0.16 * ratio if not crouch_mode else 0.10)
        cx_s, _, cz_s = to_world(hip_lf, 0.0, 0.0)
        self._textured_ground_quad(
            p, cam,
            [
                (cx_s + sun_dx - sh_len, 0.015, cz_s + sun_dz - 0.30),
                (cx_s + sun_dx + sh_len, 0.015, cz_s + sun_dz - 0.30),
                (cx_s + sun_dx + sh_len, 0.015, cz_s + sun_dz + 0.30),
                (cx_s + sun_dx - sh_len, 0.015, cz_s + sun_dz + 0.30),
            ],
            self._shadow_pm(), "#0f172a",
        )

        twist = 0.0 if (crouch_mode or standing_start or celebrate) else 0.16 * ratio * math.sin(phase)
        s_lean, c_lean = math.sin(lean), math.cos(lean)
        torso_len = 0.56
        if crouch_mode:
            sh_y_val, sh_lf_val = sh_y, sh_lf
            neck_lf, neck_y = sh_lf_val + 0.065, sh_y_val + 0.015
            head_lf, head_y = neck_lf + 0.085, neck_y - 0.025
        else:
            sh_lf_val = hip_lf + torso_len * s_lean
            sh_y_val = hip_h + torso_len * c_lean
            neck_lf, neck_y = sh_lf_val + 0.11 * s_lean, sh_y_val + 0.11 * c_lean
            head_lf, head_y = neck_lf + 0.11 * s_lean, neck_y + 0.11 * c_lean

        shorts = QColor("#0f172a")
        spike_col = kit.lighter(135) if is_player else QColor("#f8fafc")
        amp = 0.48 + 0.56 * ratio
        # determina quale lato dell'atleta (destro +1 o sinistro -1) è più vicino alla camera
        cam_vec = _sub(cam.pos, (x, 0.9, z))
        near_sign = 1.0 if (cam_vec[0] * rf + cam_vec[2] * rz_f) >= 0.0 else -1.0

        def leg_local(thigh_a: float, knee_flex: float, side: float) -> Tuple[Tuple[float, float, float], Tuple[float, float, float], Tuple[float, float, float]]:
            l1, l2 = 0.46, 0.45
            kn = (hip_lf + l1 * math.sin(thigh_a), hip_h - 0.02 - l1 * math.cos(thigh_a), side * 0.105)
            shin_a = thigh_a - knee_flex
            ak = (kn[0] + l2 * math.sin(shin_a), max(0.03, kn[1] - l2 * math.cos(shin_a)), side * 0.105)
            to = (ak[0] + 0.16 * math.cos(shin_a * 0.4), max(0.02, ak[1] - 0.03), side * 0.105)
            return kn, ak, to

        def arm_local(sh_lf_s: float, upper_a: float, elbow_bend: float, side: float) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
            l1, l2 = 0.30, 0.27
            el = (sh_lf_s + l1 * math.sin(upper_a), sh_y_val - 0.03 - l1 * math.cos(upper_a), side * 0.195)
            fore_a = upper_a + elbow_bend
            ha = (el[0] + l2 * math.sin(fore_a), el[1] - l2 * math.cos(fore_a), side * 0.195)
            return el, ha

        def draw_side(side: float) -> None:
            is_near = side == near_sign
            shade_skin = skin if is_near else skin.darker(128)
            shade_shorts = shorts if is_near else shorts.darker(125)
            ph = phase + (0.0 if side > 0 else math.pi)
            hip_l = (hip_lf, hip_h - 0.02, side * 0.105)
            sh_lf_s = sh_lf_val - side * 0.14 * twist
            sh_l = (sh_lf_s, sh_y_val - 0.03, side * 0.195)

            if crouch_mode:
                if side > 0:
                    kn_l = (-0.24, _lerp(0.24, 0.46, set_blend), side * 0.105)
                    ak_l = (-0.42, 0.13, side * 0.105)
                    to_l = (-0.34, 0.04, side * 0.105)
                else:
                    kn_l = (-0.36, _lerp(0.11, 0.32, set_blend), side * 0.105)
                    ak_l = (-0.70, 0.13, side * 0.105)
                    to_l = (-0.62, 0.04, side * 0.105)
                el_l = (-0.08, (sh_y_val + 0.04) * 0.52, side * 0.195)
                ha_l = (-0.05, 0.03, side * 0.195)
            elif standing_start:
                kn_l, ak_l, to_l = leg_local(0.28 * side, 0.25 if side > 0 else 0.45, side)
                el_l, ha_l = arm_local(sh_lf_s, -0.35 * side, 1.3, side)
            elif celebrate:
                thigh_a = 0.22 * math.sin(ph)
                kn_l, ak_l, to_l = leg_local(thigh_a, 0.25 + 0.35 * max(0.0, math.sin(ph)), side)
                el_l = (sh_lf_s + 0.06, sh_y_val + 0.20, side * 0.36)
                ha_l = (sh_lf_s + 0.10, sh_y_val + 0.44, side * 0.44)
            else:
                thigh_a = (amp * math.sin(ph) + 0.18 * (1.0 - drive_blend)) * clearance + 0.35 * (1.0 - clearance) * side
                knee_flex = (0.28 + 1.58 * ratio * max(0.0, math.sin(ph + 1.25))) * clearance + 0.55 * (1.0 - clearance)
                kn_l, ak_l, to_l = leg_local(thigh_a, knee_flex, side)
                # oscillazione braccia più esplosiva in fase di spinta, più composta al lanciato
                arm_drive = amp * (1.28 - 0.14 * drive_blend)
                arm_a = -arm_drive * math.sin(ph) * clearance - 0.25 * (1.0 - clearance) * side
                el_l, ha_l = arm_local(sh_lf_s, arm_a, 1.35 + 0.35 * max(0.0, math.sin(ph)), side)

            # sotto-segmenti muscolari mid-poly: quadricipite, gastrocnemio, bicipite, avambraccio
            quad_m = (_lerp(hip_l[0], kn_l[0], 0.48), _lerp(hip_l[1], kn_l[1], 0.48), hip_l[2])
            shorts_m = (_lerp(hip_l[0], kn_l[0], 0.54), _lerp(hip_l[1], kn_l[1], 0.54), hip_l[2])
            calf_l = (_lerp(kn_l[0], ak_l[0], 0.36), _lerp(kn_l[1], ak_l[1], 0.36), kn_l[2])
            bicep_l = (_lerp(sh_l[0], el_l[0], 0.50), _lerp(sh_l[1], el_l[1], 0.50), sh_l[2])
            fore_l = (_lerp(el_l[0], ha_l[0], 0.40), _lerp(el_l[1], ha_l[1], 0.40), el_l[2])
            hip_w, kn_w, ak_w, to_w = to_world(*hip_l), to_world(*kn_l), to_world(*ak_l), to_world(*to_l)
            quad_w, shorts_w, calf_w = to_world(*quad_m), to_world(*shorts_m), to_world(*calf_l)
            sh_w, el_w, ha_w = to_world(*sh_l), to_world(*el_l), to_world(*ha_l)
            bicep_w, fore_w = to_world(*bicep_l), to_world(*fore_l)

            self._shaded_limb(p, cam, hip_w, quad_w, 0.088, 0.080, shade_skin)
            self._shaded_limb(p, cam, quad_w, kn_w, 0.078, 0.052, shade_skin)
            self._shaded_limb(p, cam, hip_w, shorts_w, 0.094, 0.080, shade_shorts)
            self._shaded_limb(p, cam, kn_w, calf_w, 0.056, 0.070, shade_skin)
            self._shaded_limb(p, cam, calf_w, ak_w, 0.068, 0.034, shade_skin)
            draw_spike_shoe_3d(p, cam, ak_w, to_w, spike_col, is_near=is_near)
            if self._weather == WeatherCondition.PIOGGIA and self.race_time > 0.0 and ak_l[1] < 0.22:
                sc = cam.to_cam((ak_w[0], 0.04, ak_w[2]))
                if sc[2] >= NEAR:
                    sx_p, sy_p = cam.proj(sc)
                    p.setBrush(QColor(226, 232, 240, 145))
                    for dx_s, dy_s in ((-4.0, -3.0), (0.0, -6.0), (4.0, -2.5)):
                        p.drawEllipse(QPointF(sx_p + dx_s, sy_p + dy_s), 1.6, 1.6)
            self._shaded_limb(p, cam, sh_w, bicep_w, 0.062, 0.058, shade_skin)
            self._shaded_limb(p, cam, bicep_w, el_w, 0.056, 0.043, shade_skin)
            self._shaded_limb(p, cam, el_w, fore_w, 0.044, 0.046, shade_skin)
            self._shaded_limb(p, cam, fore_w, ha_w, 0.045, 0.026, shade_skin)
            # mano scolpita
            self._shaded_limb(p, cam, ha_w, to_world(ha_l[0] + 0.05 * s_lean, ha_l[1] - 0.02, ha_l[2]), 0.030, 0.018, shade_skin.darker(108))
            if has_baton and side > 0 and not crouch_mode:
                b_fwd, b_up = 0.14 * s_lean + 0.10, 0.14 * c_lean
                self._shaded_limb(
                    p, cam,
                    to_world(ha_l[0] - b_fwd, ha_l[1] - b_up, ha_l[2]),
                    to_world(ha_l[0] + b_fwd, ha_l[1] + b_up, ha_l[2]),
                    0.022, 0.022, QColor("#facc15"),
                )

        draw_side(-near_sign)

        draw_singlet_torso_3d(
            p, cam, to_world, hip_lf, hip_h, sh_lf_val, sh_y_val,
            s_lean, c_lean, twist, kit, skin, bib, crouch_mode, self.font(),
        )

        self._shaded_limb(p, cam, to_world(sh_lf_val, sh_y_val, 0.0), to_world(neck_lf, neck_y, 0.0), 0.062, 0.052, skin.darker(108))
        draw_side(near_sign)

        effort = self.race_time > 0.0 and not celebrate
        h_info = draw_athlete_head_3d(
            p, cam, to_world(head_lf, head_y, 0.0), yaw, skin, bib,
            is_player=is_player, crouch=crouch_mode, effort=effort, celebrate=celebrate,
        )
        if h_info is not None:
            hx, hy, r, depth = h_info
            if is_player:
                tri_h = max(9.0, min(16.0, r * 1.45))
                tri_w = tri_h * 0.9
                tip_y = hy - r * 1.35 - 4.0
                p.setPen(QPen(QColor("#0f172a"), 1.3))
                p.setBrush(QColor("#facc15"))
                p.drawPolygon(QPolygonF([
                    QPointF(hx - tri_w, tip_y - tri_h),
                    QPointF(hx + tri_w, tip_y - tri_h),
                    QPointF(hx, tip_y),
                ]))
                p.setPen(Qt.PenStyle.NoPen)
                if depth < 85 and self._cam_label not in ("BLOCK-CAM", "BLOCCHI"):
                    font = QFont(self.font())
                    font.setPointSize(9)
                    font.setBold(True)
                    p.setFont(font)
                    label = _short(name, 16).upper()
                    tag_w = QFontMetrics(font).horizontalAdvance(label) + 16
                    rect = QRectF(hx - tag_w / 2, tip_y - tri_h - 24, tag_w, 19)
                    p.setBrush(QColor(11, 18, 32, 225))
                    p.setPen(QPen(QColor("#facc15"), 1.2))
                    p.drawRoundedRect(rect, 5, 5)
                    p.setPen(QColor("#facc15"))
                    p.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)
                    p.setPen(Qt.PenStyle.NoPen)

    def _draw_rain_overlay(self, p: QPainter, w: int, h: int) -> None:
        if self._weather != WeatherCondition.PIOGGIA:
            return
        p.setPen(QPen(QColor(203, 213, 225, 55), 1.1))
        rng = random.Random(int(self._t * 60) % 17)
        for _ in range(55):
            rx, ry = rng.randint(0, w), rng.randint(0, h)
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
        poses = self._runner_world_poses(meters)
        cam = self._make_camera(meters, poses, w, h)

        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        self._draw_sky(p, w, h)
        self._draw_oval_stadium(p, cam)
        p.setPen(Qt.PenStyle.NoPen)

        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        leader_idx = max(range(n), key=lambda i: meters[i])
        self._draw_props(p, cam, poses)

        is_relay = self._event.startswith("4x")
        order = sorted(range(n), key=lambda i: -cam.to_cam((poses[i][0], 0.0, poses[i][1]))[2])
        for i in order:
            r = self._runners[i]
            s = r["s"]
            rx, rz, ryaw, rcurv = poses[i]
            ratio = self._speed_ratio(r)
            phase = 2 * math.pi * (0.75 + 1.65 * ratio) * max(0.0, self._t - GUN_AT) + r["phase"]
            kit = QColor("#f59e0b") if s.is_player else self._kit(s.team_name)
            tag = s.athlete_name
            if is_relay:
                legs = s.athlete_name.split(" / ")
                if len(legs) == 4:
                    tag = legs[min(3, int(max(0.0, min(0.999, meters[i] / self._distance)) * 4))]
            bib = (zlib.crc32(s.athlete_name.encode()) % 890) + 100
            celebrate = (i == leader_idx) and self.race_time > self._winner_time + self._finish_hold() * self._scale
            self._draw_athlete(
                p, cam, rx, rz, ryaw, rcurv, meters[i], phase, ratio,
                kit, self._skin(s.athlete_name), s.is_player, tag, bib, is_relay, celebrate=celebrate,
            )

        self._draw_rain_overlay(p, w, h)
        # Bloom morbido tardo pomeriggio / riflettori stile 2010 + leggera vignettatura
        evening = self._is_evening_final() or self._season_phase == SeasonPhase.INDOOR
        if self._weather != WeatherCondition.PIOGGIA:
            bloom = QRadialGradient(w * (0.18 if not evening else 0.50), h * 0.14, max(w, h) * 0.55)
            bloom.setColorAt(0.0, QColor(255, 242, 200, 34 if not evening else 24))
            bloom.setColorAt(0.55, QColor(254, 215, 170, 12 if not evening else 8))
            bloom.setColorAt(1.0, QColor(0, 0, 0, 0))
            p.fillRect(0, 0, w, h, QBrush(bloom))
        vig = QRadialGradient(w * 0.5, h * 0.5, max(w, h) * 0.74)
        vig.setColorAt(0.76, QColor(0, 0, 0, 0))
        vig.setColorAt(1.0, QColor(0, 0, 0, 58))
        p.fillRect(0, 0, w, h, QBrush(vig))

        p.setPen(Qt.PenStyle.NoPen)
        self._paint_hud(p, meters, poses, w, h)
        p.end()

    # ---- HUD televisivo stile Diretta Sportiva 2010 (glassmorphism, accenti lucidi, font bold italic)
    def _draw_glass_panel(self, p: QPainter, rect: QRectF, accent_hex: str = "#38bdf8", radius: float = 7.0) -> None:
        bg = QLinearGradient(rect.left(), rect.top(), rect.left(), rect.bottom())
        bg.setColorAt(0.0, QColor(14, 24, 44, 224))
        bg.setColorAt(0.55, QColor(8, 15, 29, 232))
        bg.setColorAt(1.0, QColor(4, 9, 19, 238))
        p.setBrush(QBrush(bg))
        p.setPen(QPen(QColor(accent_hex), 1.4))
        p.drawRoundedRect(rect, radius, radius)
        # riflesso lucido superiore effetto vetro anni 2010
        p.setPen(Qt.PenStyle.NoPen)
        gloss = QLinearGradient(rect.left(), rect.top(), rect.left(), rect.top() + rect.height() * 0.45)
        gloss.setColorAt(0.0, QColor(255, 255, 255, 34))
        gloss.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setBrush(QBrush(gloss))
        p.drawRoundedRect(QRectF(rect.left() + 1.5, rect.top() + 1.5, rect.width() - 3.0, rect.height() * 0.45), max(1.0, radius - 1.5), max(1.0, radius - 1.5))

    def _paint_hud(self, p: QPainter, meters: Sequence[float], poses: Sequence[Tuple[float, float, float, float]], w: int, h: int) -> None:
        d = self._distance
        n = len(self._runners)
        res = self._result
        font = QFont(self.font())
        font.setPointSize(9)
        font.setBold(True)
        font.setItalic(True)
        p.setFont(font)

        order = sorted(
            range(n),
            key=lambda i: (0, self._runners[i]["s"].placement)
            if self._has_finished(self._runners[i])
            else (1, -meters[i]),
        )

        show_full_board = (self.race_time <= 0.0) or self._done_all()
        if show_full_board:
            row_h = 20
            panel = QRectF(12, 12, 246, 30 + n * row_h)
            self._draw_glass_panel(p, panel, "#38bdf8" if self._done_all() else "#f97316", 7.0)
            hdr_grad = QLinearGradient(panel.left(), panel.top(), panel.right(), panel.top())
            hdr_grad.setColorAt(0.0, QColor(14, 116, 144, 180) if self._done_all() else QColor(194, 65, 12, 185))
            hdr_grad.setColorAt(1.0, QColor(15, 23, 42, 200))
            p.fillRect(QRectF(panel.left() + 1, panel.top() + 1, panel.width() - 2, 22), QBrush(hdr_grad))
            hdr_f = QFont(font)
            hdr_f.setPointSize(8)
            p.setFont(hdr_f)
            p.setPen(QColor("#f8fafc"))
            hdr_txt = f"ORDINE D'ARRIVO · {self._event.upper()}" if self._done_all() else f"LISTA DI PARTENZA · {self._event.upper()}"
            p.drawText(QRectF(panel.left() + 10, panel.top() + 2, panel.width() - 20, 20), Qt.AlignmentFlag.AlignVCenter, hdr_txt)

            for rank, i in enumerate(order, start=1):
                r = self._runners[i]
                s = r["s"]
                fin = self._has_finished(r)
                y = panel.top() + 25 + (rank - 1) * row_h
                if s.is_player:
                    p.setBrush(QColor(249, 115, 22, 46))
                    p.drawRect(QRectF(panel.left() + 2, y, panel.width() - 4, row_h))
                kit_col = QColor("#fbbf24") if s.is_player else self._kit(s.team_name)
                p.setBrush(kit_col)
                p.drawRect(QRectF(panel.left() + 6, y + 4, 4, row_h - 8))
                place = f"{s.placement}°" if fin else f"C{i + 1}"
                row_f = QFont(font)
                row_f.setItalic(True)
                row_f.setBold(True if s.is_player else False)
                p.setFont(row_f)
                p.setPen(QColor("#fbbf24" if s.is_player else "#e2e8f0"))
                name = s.team_name if self._event.startswith("4x") else s.athlete_name
                p.drawText(QRectF(panel.left() + 15, y, 28, row_h), Qt.AlignmentFlag.AlignVCenter, place)
                p.drawText(QRectF(panel.left() + 44, y, 130, row_h), Qt.AlignmentFlag.AlignVCenter, _short(name, 16))
                if fin:
                    p.setPen(QColor("#38bdf8" if rank == 1 else ("#fbbf24" if s.is_player else "#cbd5e1")))
                    p.drawText(QRectF(panel.right() - 68, y, 60, row_h), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, s.mark_display)
                elif r["dnf"] and self.race_time > self._winner_time * 0.8:
                    p.setPen(QColor("#f87171"))
                    p.drawText(QRectF(panel.right() - 68, y, 60, row_h), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "RIT")
            p.setFont(font)

        elif self._event == "100m" and 0.25 <= self.race_time <= 3.6:
            react_ord = sorted(range(n), key=lambda i: self._runners[i]["react"])
            shown = react_ord[:3]
            pl_idx = next((i for i, r in enumerate(self._runners) if r["s"].is_player), None)
            if pl_idx is not None and pl_idx not in shown:
                shown.append(pl_idx)
            rp_h = 28 + len(shown) * 18
            rp = QRectF(12, 12, 224, rp_h)
            self._draw_glass_panel(p, rp, "#38bdf8", 7.0)
            p.fillRect(QRectF(rp.left() + 1, rp.top() + 1, rp.width() - 2, 21), QColor(14, 116, 144, 160))
            hdr_f = QFont(font)
            hdr_f.setPointSize(8)
            p.setFont(hdr_f)
            p.setPen(QColor("#f8fafc"))
            p.drawText(QRectF(rp.left() + 8, rp.top() + 1, rp.width() - 16, 20), Qt.AlignmentFlag.AlignVCenter, "REAZIONE AI BLOCCHI")
            for k_r, i in enumerate(shown):
                r = self._runners[i]
                s = r["s"]
                ry = rp.top() + 24 + k_r * 18
                p.setPen(QColor("#fbbf24" if s.is_player else "#e2e8f0"))
                p.drawText(QRectF(rp.left() + 8, ry, 140, 18), Qt.AlignmentFlag.AlignVCenter, _short(s.athlete_name, 16))
                p.setPen(QColor("#38bdf8" if not s.is_player else "#fbbf24"))
                p.drawText(QRectF(rp.right() - 66, ry, 58, 18), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, f"{r['react']:.3f}s")
            p.setFont(font)

        # Barra inferiore Diretta Televisiva Sportiva (sfondo glass + bordi azzurro/arancio + cronometro lucido)
        bar_y = h - 46.0
        bar_w = min(w - 24.0, 820.0)
        bar_x = (w - bar_w) / 2.0
        bar = QRectF(bar_x, bar_y, bar_w, 34)
        self._draw_glass_panel(p, bar, "#38bdf8", 7.0)

        ev_rect = QRectF(bar.left() + 5, bar.top() + 5, 108, 24)
        ev_grad = QLinearGradient(ev_rect.left(), ev_rect.top(), ev_rect.left(), ev_rect.bottom())
        ev_grad.setColorAt(0.0, QColor("#fb923c"))
        ev_grad.setColorAt(1.0, QColor("#c2410c"))
        p.setBrush(QBrush(ev_grad))
        p.setPen(QPen(QColor("#fdba74"), 1.0))
        p.drawRoundedRect(ev_rect, 4, 4)
        p.setPen(Qt.PenStyle.NoPen)
        b_f = QFont(font)
        b_f.setPointSize(8)
        b_f.setBold(True)
        b_f.setItalic(True)
        p.setFont(b_f)
        p.setPen(QColor("#ffffff"))
        p.drawText(ev_rect, Qt.AlignmentFlag.AlignCenter, f"LIVE · {self._event.upper()}")

        cx_pos = ev_rect.right() + 14
        win_mark = self._runners[order[0]]["s"].mark_value if order else 0.0
        for pos_idx, i in enumerate(order[:3], start=1):
            r = self._runners[i]
            s = r["s"]
            p.setPen(QColor("#fbbf24" if s.is_player else ("#f8fafc" if pos_idx == 1 else "#cbd5e1")))
            nm = s.team_name if self._event.startswith("4x") else s.athlete_name.split()[-1]
            lbl = f"{pos_idx}° {_short(nm, 10)}"
            if self._event == "100m" and self._done_all() and pos_idx == 2 and not r["dnf"]:
                gap = max(0.0, s.mark_value - win_mark)
                if gap <= 0.35:
                    lbl = f"{lbl} +{gap:.2f}"
            p.drawText(QRectF(cx_pos, bar.top(), 118, 34), Qt.AlignmentFlag.AlignVCenter, lbl)
            cx_pos += 118

        leader_m = max(meters) if meters else 0.0
        if d >= 1500:
            laps_total = 4
            rem = max(0.0, d - leader_m)
            lap_now = min(laps_total, max(1, laps_total - int(rem // 400)))
            lap_txt = "ULTIMO GIRO" if (rem <= 400.0 and not self._done_all()) else f"GIRO {lap_now}/{laps_total}"
            p.setPen(QColor("#facc15" if "ULTIMO" in lap_txt else "#38bdf8"))
            p.drawText(QRectF(bar.right() - 260, bar.top(), 120, 34), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, lap_txt)
        elif res is not None and res.wind_ms is not None:
            arrow = "→" if res.wind_ms >= 0 else "←"
            p.setPen(QColor("#fca5a5" if res.wind_illegal else "#38bdf8"))
            p.drawText(QRectF(bar.right() - 258, bar.top(), 118, 34), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, f"VENTO {arrow} {res.wind_ms:+.1f}")

        # Cronometro ultra-fluido lucido in basso a destra nella barra broadcast
        clk_rect = QRectF(bar.right() - 128, bar.top() + 4, 122, 26)
        clk_grad = QLinearGradient(clk_rect.left(), clk_rect.top(), clk_rect.left(), clk_rect.bottom())
        clk_grad.setColorAt(0.0, QColor("#0284c7"))
        clk_grad.setColorAt(0.5, QColor("#0369a1"))
        clk_grad.setColorAt(1.0, QColor("#0c4a6e"))
        p.setBrush(QBrush(clk_grad))
        p.setPen(QPen(QColor("#7dd3fc"), 1.2))
        p.drawRoundedRect(clk_rect, 5, 5)
        p.setPen(Qt.PenStyle.NoPen)
        clk_f = QFont(font)
        clk_f.setPointSize(13)
        clk_f.setBold(True)
        clk_f.setItalic(True)
        p.setFont(clk_f)
        p.setPen(QColor("#ffffff"))
        p.drawText(clk_rect, Qt.AlignmentFlag.AlignCenter, format_race_time(self.race_clock))
        p.setFont(font)

        # badge telecamera broadcast in alto a destra
        cam_w = max(124.0, QFontMetrics(b_f).horizontalAdvance(self._cam_label) + 34.0)
        cam_pill = QRectF(w - cam_w - 12.0, 12, cam_w, 24)
        self._draw_glass_panel(p, cam_pill, "#f97316", 5.0)
        p.setBrush(QColor("#ef4444"))
        p.drawEllipse(QPointF(cam_pill.left() + 12, cam_pill.center().y()), 3.5, 3.5)
        p.setFont(b_f)
        p.setPen(QColor("#f8fafc"))
        p.drawText(QRectF(cam_pill.left() + 20, cam_pill.top(), cam_pill.width() - 26, cam_pill.height()), Qt.AlignmentFlag.AlignVCenter, self._cam_label)
        p.setFont(font)

        # radar ovale compatto in basso a destra per le gare sull'ovale (400m, 1500m, staffette)
        if self._is_oval_race():
            rw, rh = 112.0, 56.0
            rx0, ry0 = w - rw - 14.0, bar_y - rh - 10.0
            self._draw_glass_panel(p, QRectF(rx0, ry0, rw, rh), "#38bdf8", 8.0)
            p.setPen(QPen(QColor("#475569"), 5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(QRectF(rx0 + 12, ry0 + 10, rw - 24, rh - 20), 16, 16)
            p.setPen(Qt.PenStyle.NoPen)
            for i, r in enumerate(self._runners):
                px_m, pz_m, _, _ = poses[i]
                nx = (px_m + R_IN) / (STRAIGHT + 2 * R_IN)
                nz = (-pz_m) / (2 * R_IN)
                mx = rx0 + 12 + _clamp(nx, 0.0, 1.0) * (rw - 24)
                my = ry0 + 10 + _clamp(1.0 - nz, 0.0, 1.0) * (rh - 20)
                p.setBrush(QColor("#fbbf24" if r["s"].is_player else "#cbd5e1"))
                p.drawEllipse(QPointF(mx, my), 3.4 if r["s"].is_player else 2.5, 3.4 if r["s"].is_player else 2.5)

        # banner partenza / fotofinish / record in stile grafico TV lucido
        phase_txt = self.start_phase
        marks = sorted(r["s"].mark_value for r in self._runners if not r["dnf"])
        photo = len(marks) > 1 and marks[1] - marks[0] <= 0.05
        first_done = any(self._has_finished(r) for r in self._runners)
        banners: List[Tuple[str, str]] = []
        if phase_txt:
            banners.append((phase_txt, "#f97316" if phase_txt == "VIA!" else "#38bdf8"))
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
            big.setPointSize(19)
            big.setBold(True)
            big.setItalic(True)
            p.setFont(big)
            text, col = banners[-1]
            tw_txt = QFontMetrics(big).horizontalAdvance(text) + 42
            box = QRectF((w - tw_txt) / 2, bar_y - 46, tw_txt, 38)
            self._draw_glass_panel(p, box, col, 8.0)
            p.setPen(QColor("#f8fafc" if col == "#38bdf8" else col))
            p.drawText(box, Qt.AlignmentFlag.AlignCenter, text)
