"""Vista 3D (a basso numero di poligoni) delle corse in pista.

Motore 3D software disegnato con QPainter: camera in prospettiva, pista con corsie che fuggono
verso l'orizzonte, tribune, cartelloni e atleti con scheletro tridimensionale. Non serve
OpenGL né altre librerie. Legge solo posizioni e tempi da `TrackRaceWidget`: l'esito della
gara (tempi di arrivo, ordine) resta quello già simulato.
"""

from __future__ import annotations

import math
from typing import Dict, List, NamedTuple, Optional, Sequence, Tuple

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
    QTransform,
)

from views.race_viewer import GUN_AT, TrackRaceWidget, _short, make_crowd, start_stance

Vec = Tuple[float, float, float]

NEAR = 0.35  # piano di taglio vicino (m)
LANE_W = 1.22  # larghezza di una corsia (m)
CAM_BACK = 10.0  # la camera sta davanti al capofila, guardando indietro verso gli atleti
CAM_SIDE = 6.5  # e di lato rispetto al centro della pista
CAM_HEIGHT = 2.6
FOV_DEG = 48.0

# Sponsor di fantasia per i cartelloni
SPONSORS = [
    ("TEF SPORT", "#b91c1c"),
    ("AURORA", "#1d4ed8"),
    ("VELOCITÀ", "#047857"),
    ("ATLETICA PIÙ", "#7c3aed"),
    ("FASTLANE", "#c2410c"),
    ("TRACK & FIELD", "#0e7490"),
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


def make_crowd_tile(width: int = 256, height: int = 70) -> QPixmap:
    """Texture della folla con sfondo trasparente (sotto va il cemento della tribuna)."""
    import random as _random

    pm = QPixmap(width, height)
    pm.fill(Qt.GlobalColor.transparent)
    q = QPainter(pm)
    rng = _random.Random(7)
    for tier in range((height - 6) // 12):
        y0 = 4 + tier * 12
        x = rng.randint(0, 4)
        while x < width:
            col = QColor.fromHsv(rng.randint(0, 359), rng.randint(30, 120), rng.randint(110, 205))
            q.fillRect(x, y0, 4, 4, QColor("#e2b48f" if rng.random() < 0.6 else "#8a5a3c"))
            q.fillRect(x - 1, y0 + 4, 6, 5, col)
            x += rng.randint(6, 9)
    q.end()
    return pm



def figure_joints(hip: Vec, yaw: float, lean: float, legs, arms, torso: float = 0.55) -> dict:
    """Giunti di una figura a scheletro con orientamento libero (funzione pura, testabile).

    `yaw` ruota attorno all'asse y (0 = guarda verso +x). `legs`/`arms` sono due coppie
    ((a1, a2), (a1, a2)): lato +w (a destra di chi guarda +x) e lato -w. Gli angoli partono dalla
    verticale verso il basso e sono positivi in avanti: a1 = coscia/braccio, a2 = stinco/avambraccio
    (assoluto, non relativo)."""
    u = (math.cos(yaw), 0.0, math.sin(yaw))
    w = (-math.sin(yaw), 0.0, math.cos(yaw))

    def limb(origin: Vec, a1: float, l1: float, a2: float, l2: float) -> Tuple[Vec, Vec]:
        mid = (origin[0] + l1 * math.sin(a1) * u[0], origin[1] - l1 * math.cos(a1), origin[2] + l1 * math.sin(a1) * u[2])
        end = (mid[0] + l2 * math.sin(a2) * u[0], mid[1] - l2 * math.cos(a2), mid[2] + l2 * math.sin(a2) * u[2])
        return mid, end

    sl, cl = math.sin(lean), math.cos(lean)
    chest = (hip[0] + torso * sl * u[0], hip[1] + torso * cl, hip[2] + torso * sl * u[2])
    head = (chest[0] + 0.22 * sl * u[0], chest[1] + 0.22 * cl, chest[2] + 0.22 * sl * u[2])
    sides = []
    for k, side in enumerate((1.0, -1.0)):
        hs = (hip[0] + side * 0.1 * w[0], hip[1], hip[2] + side * 0.1 * w[2])
        knee, ankle = limb(hs, legs[k][0], 0.45, legs[k][1], 0.45)
        sh = (chest[0] + side * 0.21 * w[0], chest[1] - 0.04, chest[2] + side * 0.21 * w[2])
        elbow, hand = limb(sh, arms[k][0], 0.30, arms[k][1], 0.27)
        sides.append({"side": side, "hip": hs, "knee": knee, "ankle": ankle, "shoulder": sh, "elbow": elbow, "hand": hand})
    return {"hip": hip, "chest": chest, "head": head, "u": u, "w": w, "sides": sides}


# --------------------------------------------------------------------------- posa del velocista
class SprintPose(NamedTuple):
    """Posa di un velocista per `figure_joints`: l'anca sta a `x + dx` (m) rispetto alla sua posizione in pista."""

    dx: float
    hip_h: float
    lean: float
    legs: tuple
    arms: tuple


def _ik2(ox: float, oy: float, tx: float, ty: float, l1: float, l2: float, bend: float) -> Tuple[float, float]:
    """Catena a due ossa nel piano (x, y) dall'origine al bersaglio: angoli assoluti (a1, a2) dalla
    verticale verso il basso, positivi in avanti. `bend` = +1 articolazione in avanti (ginocchio),
    -1 indietro (gomito). Se il bersaglio è fuori portata l'arto si tende lungo la sua direzione."""
    dx, dy = tx - ox, ty - oy
    hyp = math.hypot(dx, dy) or 1e-6
    d = min(hyp, (l1 + l2) * 0.9995)
    alpha = math.acos(max(-1.0, min(1.0, (l1 * l1 + d * d - l2 * l2) / (2.0 * l1 * d))))
    a1 = math.atan2(dx, -dy) + bend * alpha
    mx, my = ox + l1 * math.sin(a1), oy - l1 * math.cos(a1)
    ex, ey = ox + dx * d / hyp, oy + dy * d / hyp
    return a1, math.atan2(ex - mx, -(ey - my))


# Blocchi di partenza, nel sistema "linea di partenza" (x = 0 alla linea, mani dietro): anca (x, y)
# e inclinazione del busto per "ai vostri posti" e per "set" (bacino sopra le spalle).
_ON_MARKS = (-0.60, 0.45, 1.256)
_SET = (-0.524, 0.72, 1.717)
_HANDS = (-0.03, 0.02)  # mani a terra dietro la linea
_FRONT_FOOT = (-0.48, 0.10)  # caviglia sul blocco anteriore (ginocchio a ~90° nel "set")
_REAR_FOOT = (-0.98, 0.10)  # caviglia sul blocco posteriore (nel "ai posti" il ginocchio tocca terra)
_TORSO = 0.55


def stance_pose(blocks: float) -> SprintPose:
    """Posa sui blocchi: 0 = "ai vostri posti" (ginocchio posteriore a terra), 1 = "set" (bacino alto).
    Mani e piedi restano fermi: l'anca sale e gli arti si adattano (cinematica inversa)."""
    b = max(0.0, min(1.0, blocks))
    hx = _ON_MARKS[0] + (_SET[0] - _ON_MARKS[0]) * b
    hy = _ON_MARKS[1] + (_SET[1] - _ON_MARKS[1]) * b
    lean = _ON_MARKS[2] + (_SET[2] - _ON_MARKS[2]) * b
    sx = _TORSO * math.sin(lean)
    sy = hy + _TORSO * math.cos(lean) - 0.04  # spalla (come in `figure_joints`)
    front = _ik2(0.0, hy, _FRONT_FOOT[0] - hx, _FRONT_FOOT[1], 0.45, 0.45, 1.0)
    rear = _ik2(0.0, hy, _REAR_FOOT[0] - hx, _REAR_FOOT[1], 0.45, 0.45, 1.0)
    arm = _ik2(sx, sy, _HANDS[0] - hx, _HANDS[1], 0.30, 0.27, -1.0)
    return SprintPose(hx, hy, lean, (front, rear), (arm, arm))


def drive_pose(phase: float, ratio: float, rise: float) -> SprintPose:
    """Corsa del velocista. `rise` 1 = corsa eretta; più basso = fase di spinta: busto in avanti,
    anca più bassa, gambe che spingono indietro e braccia che pompano di più."""
    r = max(0.0, min(1.0, rise))
    d = 1.0 - r
    amp = 0.45 + 0.55 * ratio
    lean = 0.10 + 0.28 * ratio + 0.65 * d
    legs, arms = [], []
    for k in (0, 1):
        ph = phase + k * math.pi
        la = amp * math.sin(ph) - 0.20 * d
        kf = 0.35 + 1.25 * ratio * max(0.0, math.sin(ph + 1.3))
        aa = -amp * 1.15 * (1.0 + 0.25 * d) * math.sin(ph)
        legs.append((la, la - kf))
        arms.append((aa, aa + 1.2))
    hip_h = 0.95 - 0.10 * d
    low = min(s["ankle"][1] for s in figure_joints((0.0, hip_h, 0.0), 0.0, lean, legs, arms)["sides"])
    hip_h += max(0.0, 0.04 - low)  # i piedi non vanno mai sotto terra
    return SprintPose(0.0, hip_h, lean, tuple(legs), tuple(arms))


def sprint_pose(phase: float, ratio: float, blocks: float, push: float, rise: float) -> SprintPose:
    """Posa dalla partenza alla corsa: blocchi (`blocks`), stacco (`push`), spinta (`rise`)."""
    st = stance_pose(blocks)
    if push <= 0.0:
        return st
    dr = drive_pose(phase, ratio, rise)
    if push >= 1.0:
        return dr

    def mix(a: float, b: float) -> float:
        return a + (b - a) * push

    def mix2(a, b):
        return tuple(tuple(mix(x, y) for x, y in zip(ja, jb)) for ja, jb in zip(a, b))

    mixed = SprintPose(mix(st.dx, dr.dx), mix(st.hip_h, dr.hip_h), mix(st.lean, dr.lean), mix2(st.legs, dr.legs), mix2(st.arms, dr.arms))
    low = min(s["ankle"][1] for s in figure_joints((0.0, mixed.hip_h, 0.0), 0.0, mixed.lean, mixed.legs, mixed.arms)["sides"])
    return mixed._replace(hip_h=mixed.hip_h + max(0.0, 0.04 - low))  # anche nel raccordo i piedi restano sopra terra


class Scene3D:
    """Primitive di disegno 3D condivise dalle viste in prospettiva (corse e concorsi).

    Va mescolata a un QWidget: usa `self.font()`."""

    _board_cache: Dict[int, QPixmap] = {}
    _crowd_tile: Optional[QPixmap] = None

    def _get_crowd_tile(self) -> QPixmap:
        if self._crowd_tile is None:
            self._crowd_tile = make_crowd_tile()
        return self._crowd_tile


    def _poly(self, p: QPainter, cam: Camera, pts: Sequence[Vec], color) -> None:
        cs = clip_near([cam.to_cam(q) for q in pts])
        if len(cs) < 3:
            return
        p.setBrush(color if isinstance(color, QBrush) else QBrush(QColor(color)))
        p.drawPolygon(QPolygonF([QPointF(*cam.proj(c)) for c in cs]))

    def _poly_tex(self, p: QPainter, cam: Camera, pts: Sequence[Vec], tile: QPixmap, tint: int = 100) -> None:
        cs = clip_near([cam.to_cam(q) for q in pts])
        if len(cs) < 3:
            return
        depth = sum(c[2] for c in cs) / len(cs)
        scale = max(0.35, min(2.5, cam.f * 0.045 / depth))
        brush = QBrush(tile)
        brush.setTransform(QTransform().scale(scale, scale))
        p.setBrush(brush)
        p.drawPolygon(QPolygonF([QPointF(*cam.proj(c)) for c in cs]))
        if tint != 100:
            p.setBrush(QColor(0, 0, 0, 255 - int(255 * tint / 100)))
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

    def _board(self, idx: int) -> QPixmap:
        pm = self._board_cache.get(idx)
        if pm is None:
            text, col = SPONSORS[idx % len(SPONSORS)]
            pm = QPixmap(256, 56)
            pm.fill(QColor(col))
            q = QPainter(pm)
            q.fillRect(0, 0, 256, 6, QColor("#f8fafc"))
            q.setPen(QColor("#f8fafc"))
            f = QFont("Arial", 22)
            f.setBold(True)
            q.setFont(f)
            q.drawText(QRectF(0, 6, 256, 50), Qt.AlignmentFlag.AlignCenter, text)
            q.end()
            self._board_cache[idx] = pm
        return pm

    def _textured_quad(self, p: QPainter, cam: Camera, corners: Sequence[Vec], pm: QPixmap) -> None:
        """Mappa un'immagine su un quadrilatero 3D (angoli: alto-sx, alto-dx, basso-dx, basso-sx).
        Serve solo per cartelloni lontani dalla camera: se un angolo è dietro, si salta."""
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

    def _draw_stand(self, p: QPainter, cam: Camera, side: float, base: float, xa: float, xb: float) -> None:
        """Tribuna lunga a due ordini di gradoni lungo x. `side` = verso in cui sale (±1 su z),
        `base` = z del piede della tribuna."""
        tile = self._get_crowd_tile()
        concrete = "#7d8aa0"
        seg = 14.0
        x = math.floor(xa / seg) * seg
        while x < xb:
            x0, x1 = x - 0.3, x + seg + 0.3

            def zz(dz: float) -> float:
                return base + side * dz

            tiers = [((0.4, 5.0), (5.0, 14.0), 100), ((5.6, 17.0), (16.0, 38.0), 84)]
            for (y_lo, y_hi), (d_lo, d_hi), tint in tiers:
                quad = [(x0, y_lo, zz(d_lo)), (x1, y_lo, zz(d_lo)), (x1, y_hi, zz(d_hi)), (x0, y_hi, zz(d_hi))]
                shade = QColor(concrete).darker(100 + (100 - tint))
                self._poly(p, cam, quad, shade)
                self._poly_tex(p, cam, quad, tile)
            x += seg

    def _draw_head(self, p: QPainter, cam: Camera, head: Vec, skin: QColor, is_player: bool, name: str) -> None:
        hc = cam.to_cam(head)
        if hc[2] < NEAR:
            return
        hx, hy = cam.proj(hc)
        r = 0.115 * cam.f / hc[2]
        p.setBrush(skin)
        p.drawEllipse(QPointF(hx, hy), r, r * 1.08)
        p.setBrush(QColor("#fbbf24") if is_player else QColor("#111827"))
        p.drawChord(QRectF(hx - r, hy - r * 1.08, 2 * r, 2.16 * r), 20 * 16, 140 * 16)  # fascia / capelli

        if is_player and hc[2] < 90:
            font = QFont(self.font())  # type: ignore[attr-defined]
            font.setPointSize(9)
            font.setBold(True)
            p.setFont(font)
            label = _short(name, 18).upper()
            tag_w = QFontMetrics(font).horizontalAdvance(label) + 16
            rect = QRectF(hx - tag_w / 2, hy - r - 34, tag_w, 18)
            p.setBrush(QColor(11, 18, 32, 220))
            p.drawRoundedRect(rect, 4, 4)
            p.setPen(QColor("#fbbf24"))
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#fbbf24"))
            p.drawPolygon(QPolygonF([QPointF(hx - 5, hy - r - 15), QPointF(hx + 5, hy - r - 15), QPointF(hx, hy - r - 8)]))

    def _draw_shadow(self, p: QPainter, cam: Camera, x: float, z: float, rx: float = 0.5, rz: float = 0.28) -> None:
        pts = [(x + rx * math.cos(a), 0.02, z + rz * math.sin(a)) for a in [i * math.pi / 6 for i in range(12)]]
        self._poly(p, cam, pts, QColor(0, 0, 0, 80))

    def _draw_figure(
        self, p: QPainter, cam: Camera, hip: Vec, yaw: float, lean: float, legs, arms,
        kit: QColor, skin: QColor, is_player: bool, name: str,
    ) -> dict:
        """Disegna una figura a scheletro con orientamento libero (vedi `figure_joints`).
        Il lato più vicino alla camera si disegna per ultimo. Restituisce i giunti."""
        j = figure_joints(hip, yaw, lean, legs, arms)
        w = j["w"]
        near = 1.0 if (cam.pos[0] - hip[0]) * w[0] + (cam.pos[2] - hip[2]) * w[2] > 0 else -1.0
        shorts = QColor("#1e293b")

        def draw_side(s: dict) -> None:
            col = skin.darker(100 if s["side"] == near else 140)
            self._line3(p, cam, s["hip"], s["knee"], 0.075, col)
            self._line3(p, cam, s["knee"], s["ankle"], 0.055, col)
            ax, ay, az = s["ankle"]
            self._line3(p, cam, s["ankle"], (ax + 0.16 * j["u"][0], max(0.03, ay - 0.03), az + 0.16 * j["u"][2]), 0.045, QColor("#f8fafc"))
            self._line3(p, cam, s["shoulder"], s["elbow"], 0.05, col)
            self._line3(p, cam, s["elbow"], s["hand"], 0.045, col)

        far = next(s for s in j["sides"] if s["side"] != near)
        near_s = next(s for s in j["sides"] if s["side"] == near)
        draw_side(far)
        self._line3(p, cam, j["hip"], j["chest"], 0.14, kit)
        sl = math.sin(lean)
        top = (hip[0] + 0.1 * sl * j["u"][0], hip[1] + 0.12, hip[2] + 0.1 * sl * j["u"][2])
        self._line3(p, cam, (hip[0], hip[1] - 0.05, hip[2]), top, 0.15, shorts)
        draw_side(near_s)
        self._draw_head(p, cam, j["head"], skin, is_player, name)
        return j



# --------------------------------------------------------------------------- vista
class Track3DWidget(Scene3D, TrackRaceWidget):
    """Stessa gara della vista 2D, vista in prospettiva."""


    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(420)
        self._crowd_tile: Optional[QPixmap] = None

    # ---- geometria del mondo
    def _track_width(self) -> float:
        return max(1, len(self._runners)) * LANE_W

    def _lane_z(self, i: int) -> float:
        return (i + 0.5) * LANE_W

    def _make_camera(self, meters: Sequence[float], w: int, h: int) -> Camera:
        d = self._distance
        leader = max(meters) if meters else 0.0
        focus = max(0.0, min(d + 6.0, leader))
        zc = self._track_width() / 2.0
        pos = (focus + CAM_BACK, CAM_HEIGHT, zc + CAM_SIDE)
        target = (focus - 5.0, 0.9, zc)
        return Camera(pos, target, FOV_DEG, w, h)


    # ---- scenografia
    def _draw_environment(self, p: QPainter, cam: Camera, w: int, h: int) -> None:
        d = self._distance
        tw = self._track_width()
        cam_x = cam.pos[0]
        xa, xb = max(-70.0, cam_x - 150.0), min(d + 70.0, cam_x + 40.0)

        # cielo
        sky = QLinearGradient(0, 0, 0, h * 0.55)
        sky.setColorAt(0.0, QColor("#4f8fd6"))
        sky.setColorAt(1.0, QColor("#cfe5f3"))
        p.fillRect(0, 0, w, h, QBrush(sky))
        p.setPen(Qt.PenStyle.NoPen)

        tile = self._get_crowd_tile()
        concrete = "#7d8aa0"

        self._draw_stand(p, cam, -1.0, 0.0, xa, xb)  # lato opposto (z<0)
        self._draw_stand(p, cam, 1.0, tw, xa, xb)  # lato vicino (z>larghezza pista)
        end_x = -34.0
        for k in range(4):  # tribuna di testata (dietro gli atleti all'inizio)
            z0 = -38.0 + k * (tw + 76.0) / 4.0
            z1 = z0 + (tw + 76.0) / 4.0 + 0.3
            quad = [(end_x, 0.4, z0), (end_x, 0.4, z1), (end_x - 22.0, 16.0, z1), (end_x - 22.0, 16.0, z0)]
            self._poly(p, cam, quad, QColor(concrete).darker(115))
            self._poly_tex(p, cam, quad, tile)

        # prato rasato a bande (interno e fascia esterna)
        band = 8.0
        x = math.floor(xa / band) * band
        while x < xb:
            light = int(x // band) % 2 == 0
            g_in, g_out = ("#2f7d3d", "#2a6f37") if light else ("#34873f", "#2f7a3d")
            self._poly(p, cam, [(x, 0.0, -5.0), (x + band + 0.05, 0.0, -5.0), (x + band + 0.05, 0.0, -0.3), (x, 0.0, -0.3)], g_in)
            self._poly(p, cam, [(x, 0.0, tw), (x + band + 0.05, 0.0, tw), (x + band + 0.05, 0.0, tw + 14.0), (x, 0.0, tw + 14.0)], g_out)
            x += band
        # pista
        self._poly(p, cam, [(xa, 0.0, 0.0), (xb, 0.0, 0.0), (xb, 0.0, tw), (xa, 0.0, tw)], "#b5472a")
        self._poly(p, cam, [(xa, 0.01, -0.3), (xb, 0.01, -0.3), (xb, 0.01, 0.0), (xa, 0.01, 0.0)], "#f1f5f9")

    def _draw_track_marks(self, p: QPainter, cam: Camera) -> None:
        d = self._distance
        n = len(self._runners)
        tw = self._track_width()
        cam_x = cam.pos[0]
        xa, xb = max(-12.0, cam_x - 150.0), min(d + 30.0, cam_x + 25.0)
        # linee delle corsie
        for i in range(n + 1):
            z = i * LANE_W
            self._poly(p, cam, [(xa, 0.012, z - 0.03), (xb, 0.012, z - 0.03), (xb, 0.012, z + 0.03), (xa, 0.012, z + 0.03)], "#f1f5f9")
        # tacche trasversali e numeri
        step = 10 if d <= 400 else 50
        first = int(max(0, math.floor(xa / step) * step))
        for mt in range(first, int(min(d + 30.0, xb)) + 1, step):
            self._poly(p, cam, [(mt - 0.06, 0.011, 0.0), (mt + 0.06, 0.011, 0.0), (mt + 0.06, 0.011, tw), (mt - 0.06, 0.011, tw)], QColor(255, 255, 255, 110))
        # partenza
        self._poly(p, cam, [(-0.08, 0.013, 0.0), (0.08, 0.013, 0.0), (0.08, 0.013, tw), (-0.08, 0.013, tw)], "#ffffff")
        for i in range(n):
            z = self._lane_z(i)
            self._poly(p, cam, [(-0.45, 0.04, z - 0.2), (-0.15, 0.04, z - 0.2), (-0.15, 0.04, z + 0.2), (-0.45, 0.04, z + 0.2)], "#1e293b")  # blocchi
        # zone cambio staffetta
        if self._event.startswith("4x"):
            for k in (1, 2, 3):
                cx = d * k / 4.0
                self._poly(p, cam, [(cx - 10, 0.014, 0.0), (cx + 10, 0.014, 0.0), (cx + 10, 0.014, tw), (cx - 10, 0.014, tw)], QColor(250, 204, 21, 90))

        # traguardo a scacchi
        cells = max(2, int(tw / 0.3))
        cw = tw / cells
        for j in range(cells):
            for k in range(2):
                if (j + k) % 2 == 0:
                    x0 = d + k * 0.3
                    self._poly(p, cam, [(x0, 0.015, j * cw), (x0 + 0.3, 0.015, j * cw), (x0 + 0.3, 0.015, (j + 1) * cw), (x0, 0.015, (j + 1) * cw)], "#0f172a")

    def _draw_boards_and_finish(self, p: QPainter, cam: Camera) -> None:
        d = self._distance
        tw = self._track_width()
        cam_x = cam.pos[0]
        seg = 6.0
        x = math.floor(max(-30.0, cam_x - 120.0) / seg) * seg
        idx = 0
        while x < min(d + 30.0, cam_x + 20.0):
            pm = self._board(int(x // seg))
            self._textured_quad(p, cam, [(x, 1.0, -1.0), (x + seg - 0.2, 1.0, -1.0), (x + seg - 0.2, 0.05, -1.0), (x, 0.05, -1.0)], pm)
            x += seg
            idx += 1

        # portale del traguardo
        for z in (-0.9, tw + 0.9):
            self._line3(p, cam, (d, 0.0, z), (d, 5.2, z), 0.12, QColor("#e2e8f0"))
        self._line3(p, cam, (d, 5.2, -0.9), (d, 5.2, tw + 0.9), 0.16, QColor("#e2e8f0"))
        banner = QPixmap(256, 40)
        banner.fill(QColor("#0f172a"))
        q = QPainter(banner)
        q.setPen(QColor("#fbbf24"))
        f = QFont("Arial", 20)
        f.setBold(True)
        q.setFont(f)
        q.drawText(QRectF(0, 0, 256, 40), Qt.AlignmentFlag.AlignCenter, "ARRIVO")
        q.end()
        self._textured_quad(p, cam, [(d, 5.2, tw + 0.9), (d, 5.2, -0.9), (d, 4.3, -0.9), (d, 4.3, tw + 0.9)], banner)
        # nastro
        if not any(self._has_finished(r) for r in self._runners):
            self._line3(p, cam, (d, 1.1, 0.0), (d, 1.1, tw), 0.03, QColor("#f87171"))

    # ---- atleti
    def _draw_athlete(
        self, p: QPainter, cam: Camera, x: float, z: float, phase: float, ratio: float,
        stance: Tuple[float, float, float], kit: QColor, skin: QColor, is_player: bool, name: str,
    ) -> None:
        """`stance` = (blocks, push, rise) di `start_stance`: dai blocchi alla corsa eretta."""
        pose = sprint_pose(phase, ratio, *stance)
        self._draw_shadow(p, cam, x + pose.dx + 0.15, z)
        self._draw_figure(p, cam, (x + pose.dx, pose.hip_h, z), 0.0, pose.lean, pose.legs, pose.arms, kit, skin, is_player, name)

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

        # le grandi superfici non hanno bisogno di antialiasing (e costano molto): solo atleti e HUD
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        self._draw_environment(p, cam, w, h)
        p.setPen(Qt.PenStyle.NoPen)
        self._draw_track_marks(p, cam)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self._draw_boards_and_finish(p, cam)

        order = sorted(range(n), key=lambda i: -cam.to_cam((meters[i], 0.0, self._lane_z(i)))[2])
        for i in order:  # dal più lontano al più vicino
            r = self._runners[i]
            s = r["s"]
            ratio = self._speed_ratio(r)
            phase = 2 * math.pi * (0.7 + 1.6 * ratio) * max(0.0, self._t - GUN_AT) + r["phase"]
            kit = QColor("#fbbf24") if s.is_player else self._kit(s.team_name)
            tag = s.athlete_name
            if self._event.startswith("4x"):  # in staffetta il cartellino mostra il frazionista in corsa
                legs = s.athlete_name.split(" / ")
                if len(legs) == 4:
                    tag = legs[min(3, int(max(0.0, min(0.999, meters[i] / self._distance)) * 4))]
            stance = start_stance(self._t, self.race_time, r["react"], meters[i])
            self._draw_athlete(p, cam, meters[i], self._lane_z(i), phase, ratio, stance, kit, self._skin(s.athlete_name), s.is_player, tag)
        p.setPen(Qt.PenStyle.NoPen)
        self._paint_hud(p, meters, w, h)
        p.end()

    # ---- HUD 2D sopra la scena
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
        row_h = 20
        panel = QRectF(10, 10, 232, 8 + n * row_h)
        p.setBrush(QColor(11, 18, 32, 205))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(panel, 6, 6)
        for rank, i in enumerate(order, start=1):
            r = self._runners[i]
            s = r["s"]
            fin = self._has_finished(r)
            y = panel.top() + 4 + (rank - 1) * row_h
            place = f"{s.placement}°" if fin else (f"{rank}°" if self.race_time > 0 else f"C{i + 1}")
            bold = QFont(font)
            bold.setBold(s.is_player)
            p.setFont(bold)
            p.setPen(QColor("#fbbf24" if s.is_player else "#e2e8f0"))
            name = s.team_name if self._event.startswith("4x") else s.athlete_name
            p.drawText(QRectF(panel.left() + 8, y, 34, row_h), Qt.AlignmentFlag.AlignVCenter, place)
            p.drawText(QRectF(panel.left() + 42, y, 120, row_h), Qt.AlignmentFlag.AlignVCenter, _short(name, 16))
            if fin:
                p.drawText(QRectF(panel.right() - 66, y, 60, row_h), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, s.mark_display)
            elif r["dnf"] and self.race_time > self._winner_time * 0.8:
                p.setPen(QColor("#f87171"))
                p.drawText(QRectF(panel.right() - 66, y, 60, row_h), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "RIT")
        p.setFont(font)

        # cronometro al centro in alto
        pill = QRectF(w / 2 - 62, 10, 124, 28)
        p.setBrush(QColor("#7f1d1d"))
        p.setPen(QPen(QColor("#fca5a5"), 1))
        p.drawRoundedRect(pill, 8, 8)
        clock_font = QFont(font)
        clock_font.setPointSize(12)
        clock_font.setBold(True)
        p.setFont(clock_font)
        p.setPen(QColor("#f8fafc"))
        from views.race_viewer import format_race_time

        p.drawText(pill, Qt.AlignmentFlag.AlignCenter, f"⏱ {format_race_time(self.race_clock)}")
        p.setFont(font)

        # vento
        if res is not None and res.wind_ms is not None:
            arrow = "→" if res.wind_ms >= 0 else "←"
            box = QRectF(w - 160, 10, 150, 22)
            p.setBrush(QColor(11, 18, 32, 205))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(box, 6, 6)
            p.setPen(QColor("#fca5a5" if res.wind_illegal else "#e2e8f0"))
            p.drawText(box, Qt.AlignmentFlag.AlignCenter, f"Vento {arrow} {res.wind_ms:+.1f} m/s")

        # minimappa per le distanze lunghe
        if d > 100:
            x0, x1, y = 260.0, w - 20.0, h - 26.0
            p.setBrush(QColor(11, 18, 32, 205))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(QRectF(x0 - 10, y - 12, x1 - x0 + 20, 30), 6, 6)
            p.fillRect(QRectF(x0, y + 2, x1 - x0, 4), QColor("#334155"))
            for i, r in enumerate(self._runners):
                mx = x0 + (x1 - x0) * max(0.0, min(1.0, meters[i] / d))
                p.setBrush(QColor("#fbbf24" if r["s"].is_player else "#94a3b8"))
                p.drawRect(QRectF(mx - 3, y - 2, 7, 12))

        # banner: partenza, foto finish, record, squalifica
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
            big.setPointSize(28)
            big.setBold(True)
            p.setFont(big)
            text, col = banners[-1]
            area = QRectF(0, h * 0.30, w, 60)
            p.setPen(QColor(0, 0, 0, 180))
            p.drawText(area.adjusted(2, 2, 2, 2), Qt.AlignmentFlag.AlignCenter, text)
            p.setPen(QColor(col))
            p.drawText(area, Qt.AlignmentFlag.AlignCenter, text)
