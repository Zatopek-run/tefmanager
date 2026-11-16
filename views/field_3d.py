"""Vista 3D dei concorsi: salto in lungo e getto del peso.

Stesso motore software di `race_3d` (QPainter, nessun OpenGL). La vista legge solo lo stato di
`FieldSceneWidget` (`cur`, `t`, `dur`): la misura di ogni prova è già decisa dal modello e la
scena la mette in scena senza cambiarla (il tallone atterra esattamente a `dist`, l'attrezzo
cade esattamente a `dist`). Le fasi usano gli stessi istanti della vista 2D.

Mondo: `x` lungo la pedana / la direzione del lancio (origine = linea di battuta o bordo anteriore
del cerchio, da cui si misura), `y` in alto, `z` di lato. La camera sta a `z > 0`, così chi corre
verso `+x` attraversa lo schermo da sinistra a destra e il braccio destro è quello vicino.
"""

from __future__ import annotations

import math
import zlib
from typing import Any, Dict, List, NamedTuple, Optional, Tuple

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QLinearGradient, QPainter, QPen

from views.race_3d import NEAR, Camera, Scene3D, Vec, figure_joints
from views.race_viewer import FieldSceneWidget, TrackRaceWidget

FOV_DEG = 52.0
RUNWAY_W = 1.22  # larghezza della pedana (m)
LJ_Z = RUNWAY_W / 2.0  # asse della pedana
PIT_X0 = 1.0  # inizio della sabbia dalla linea di battuta
PIT_HALF_W = 1.38  # la buca è larga 2,76 m
RING_R = 1.067  # cerchio del peso: diametro 2,135 m
RING_CX = -RING_R  # centro del cerchio: il bordo anteriore sta a x = 0
SECTOR_HALF = math.radians(17.46)  # settore di 34,92°
RUN_START = -9.0  # inizio rincorsa (come nella vista 2D)

SAND = "#e7d3a1"
SAND_DENT = "#bfa56d"


# --------------------------------------------------------------------------- pose (funzioni pure)
class Pose(NamedTuple):
    hip: Vec
    yaw: float
    lean: float
    legs: Tuple[Tuple[float, float], Tuple[float, float]]
    arms: Tuple[Tuple[float, float], Tuple[float, float]]


def _smooth(k: float) -> float:
    k = max(0.0, min(1.0, k))
    return k * k * (3.0 - 2.0 * k)


def _grounded(pose: "Pose", min_y: float) -> "Pose":
    """Alza l'anca quanto basta perché nessuna caviglia scenda sotto `min_y` (piedi mai nel terreno)."""
    low = min(s["ankle"][1] for s in figure_joints(pose.hip, pose.yaw, pose.lean, pose.legs, pose.arms)["sides"])
    if low >= min_y:
        return pose
    return pose._replace(hip=(pose.hip[0], pose.hip[1] + min_y - low, pose.hip[2]))


def _mix(a: Any, b: Any, k: float) -> Any:
    """Interpolazione lineare di numeri e di tuple annidate."""
    if isinstance(a, tuple):
        return tuple(_mix(x, y, k) for x, y in zip(a, b))
    return a + (b - a) * k


# Pose chiave del salto in lungo: (lean, gambe, braccia). Gamba/braccio 0 = lato +z.
_LJ_TAKEOFF = (0.10, ((1.35, 0.35), (-0.35, -0.50)), ((-0.9, -0.6), (2.2, 2.0)))
_LJ_HANG = (-0.05, ((0.55, -0.45), (-0.45, -1.0)), ((2.7, 2.6), (2.7, 2.6)))
_LJ_PIKE = (0.45, ((1.0, 1.2), (0.9, 1.1)), ((1.6, 1.7), (1.6, 1.7)))
_LJ_LAND = (0.75, ((1.1, 1.5), (1.1, 1.5)), ((1.3, 1.4), (1.3, 1.4)))

_land_j = figure_joints((0.0, 0.0, 0.0), 0.0, _LJ_LAND[0], _LJ_LAND[1], _LJ_LAND[2])["sides"][0]["ankle"]
LJ_LAND_REACH = _land_j[0]  # distanza orizzontale anca -> tallone nella posa d'atterraggio
LJ_LAND_HIP_Y = 0.04 - _land_j[1]  # altezza dell'anca con il tallone appena sopra la sabbia


def lj_pose(d: float, t: float, run_end: float, jump_end: float) -> Tuple[Pose, str, float]:
    """Posa del saltatore al tempo `t`. Restituisce (posa, fase, età dall'atterraggio).

    Fasi: "run" (rincorsa), "air" (volo), "land" (a terra). A fine volo il tallone sta
    esattamente a `x = d`: è la misura."""
    if t < run_end:
        ratio = min(1.0, 0.3 + t)
        x = RUN_START + (0.0 - RUN_START) * (t / run_end)
        ph = 2 * math.pi * 2.0 * t
        amp = 0.45 + 0.55 * ratio
        legs, arms = [], []
        for k in range(2):
            p_ = ph + k * math.pi
            la = amp * math.sin(p_)
            kf = 0.35 + 1.25 * ratio * max(0.0, math.sin(p_ + 1.3))
            legs.append((la, la - kf))
            aa = -amp * 1.15 * math.sin(p_)
            arms.append((aa, aa + 1.2))
        return Pose((x, 0.95, LJ_Z), 0.0, 0.10 + 0.28 * ratio, (legs[0], legs[1]), (arms[0], arms[1])), "run", 0.0
    if t < jump_end:
        s = (t - run_end) / (jump_end - run_end)
        if s < 0.5:
            lean, legs, arms = _mix(_LJ_TAKEOFF, _LJ_HANG, _smooth(s / 0.5))
        elif s < 0.82:
            lean, legs, arms = _mix(_LJ_HANG, _LJ_PIKE, _smooth((s - 0.5) / 0.32))
        else:
            lean, legs, arms = _mix(_LJ_PIKE, _LJ_LAND, _smooth((s - 0.82) / 0.18))
        rise = 0.55 + 0.05 * d
        base = 0.95 + (LJ_LAND_HIP_Y - 0.95) * _smooth((s - 0.55) / 0.45)
        y = base + rise * 4.0 * s * (1.0 - s)
        x = d * s - LJ_LAND_REACH * s ** 3
        return _grounded(Pose((x, y, LJ_Z), 0.0, lean, legs, arms), 0.04), "air", 0.0
    age = t - jump_end
    lean = min(0.95, _LJ_LAND[0] + 0.5 * age)
    return Pose((d - LJ_LAND_REACH, LJ_LAND_HIP_Y, LJ_Z), 0.0, lean, _LJ_LAND[1], _LJ_LAND[2]), "land", age


# Getto del peso: (lean, gambe, braccia, altezza anca). Braccio 0 = braccio che lancia (destro).
_SP_CROUCH = (0.45, ((0.8, 0.3), (-0.2, -1.7)), ((0.5, 2.6), (1.2, 1.0)), 0.72)
_SP_RELEASE = (-0.12, ((0.3, 0.05), (-0.7, -0.8)), ((2.2, 2.2), (1.4, 1.0)), 1.0)
# anca: dal fondo del cerchio al bordo anteriore. SP_HIP_X1 tiene la punta del piede davanti
# (anca + ~0,4 m) dietro il fermapiede (x = -0,08): un lancio valido non deve sembrare nullo.
SP_HIP_X0, SP_HIP_X1 = RING_CX - 0.45, -0.80


def sp_pose(t: float, wind_end: float) -> Pose:
    """Posa del lanciatore al tempo `t` (rotazione fino a `wind_end`, poi rilascio e recupero)."""
    s = min(1.0, t / wind_end)
    spin = _smooth(min(1.0, s / 0.8))
    yaw = math.pi + 3.0 * math.pi * spin  # mezzo giro + un giro: da di spalle a verso +x
    x = SP_HIP_X0 + (SP_HIP_X1 - SP_HIP_X0) * spin
    ext = _smooth((s - 0.75) / 0.25)
    lean, legs, arms, hy = _mix(_SP_CROUCH, _SP_RELEASE, ext)
    if t < wind_end and ext < 1.0:  # passi durante la rotazione
        ph = 2 * math.pi * 2.0 * s
        sw = 0.3 * math.sin(ph) * (1.0 - ext) * (1.0 - spin)  # il passo si spegne quando l'anca è arrivata
        legs = ((legs[0][0] + sw, legs[0][1] + sw), (legs[1][0] - sw, legs[1][1] - sw))
        hy += 0.05 * math.sin(2 * ph) * (1.0 - ext)
    if t >= wind_end:  # dopo il rilascio: inerzia in avanti e braccio che scende
        k = _smooth((t - wind_end) / 0.5)
        lean += 0.55 * k
        hy -= 0.05 * k
        x += 0.10 * k
        arms = ((_mix(2.2, 1.2, k), _mix(2.2, 1.2, k)), arms[1])
    return _grounded(Pose((x, hy, 0.0), yaw, lean, legs, arms), 0.03)


def sp_release_point(wind_end: float) -> Vec:
    """Dove la mano lascia l'attrezzo (inizio del volo)."""
    pose = sp_pose(wind_end, wind_end)
    hand = figure_joints(pose.hip, pose.yaw, pose.lean, pose.legs, pose.arms)["sides"][0]["hand"]
    return (hand[0], hand[1], hand[2])


def sp_shot_position(d: float, t: float, wind_end: float, fly_end: float) -> Vec:
    """Posizione dell'attrezzo: in mano fino al rilascio, poi parabola che chiude a `x = d`."""
    if t < wind_end:
        pose = sp_pose(t, wind_end)
        h = figure_joints(pose.hip, pose.yaw, pose.lean, pose.legs, pose.arms)["sides"][0]["hand"]
        return (h[0], h[1] + 0.04, h[2])
    x0, y0, z0 = sp_release_point(wind_end)
    s = min(1.0, (t - wind_end) / (fly_end - wind_end))
    apex = 3.2 + 0.14 * d
    return (x0 + (d - x0) * s, y0 * (1.0 - s) + 4.0 * apex * s * (1.0 - s), z0 * (1.0 - s))


# --------------------------------------------------------------------------- vista
class FieldScene3D(Scene3D, FieldSceneWidget):
    """Stessa prova della scena 2D, vista in prospettiva con camera che segue l'azione."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(230)  # come la scena 2D: non toglie spazio al tabellone

    # ---- stato della scena al tempo corrente
    def _frame(self) -> Dict[str, Any]:
        cur = self.cur
        lj = self.kind == "lj"
        out: Dict[str, Any] = {"pose": None, "ball": None, "age": 0.0, "focus": 0.0, "ty": 1.0, "show_flag": False, "show_mark": False, "static": False}
        mid = (self.lo + self.hi) / 2.0
        if cur is None:
            out.update(static=True, focus=mid)
            return out
        d, foul, animate = cur["dist"], cur["foul"], cur["animate"]
        if lj:
            if not animate:  # prova di un altro atleta: stessa inquadratura fissa di tutte (niente stacchi)
                out.update(static=True, focus=mid, show_flag=not foul, show_mark=not foul)
                return out
            pose, phase, age = lj_pose(d, self.t, self.LJ_RUN_END, self.LJ_JUMP_END)
            out.update(pose=pose, phase=phase, age=age, focus=max(RUN_START, min(d - 0.8, pose.hip[0])))
            out["show_mark"] = phase == "land" and not foul
            out["show_flag"] = phase == "land" and age > 0.25
            return out
        we, fe = self.SP_WIND_END, self.SP_FLY_END
        if not animate:
            out.update(static=True, focus=mid, show_flag=not foul, show_mark=not foul)
            return out
        pose = sp_pose(self.t, we)
        hold = we + 0.35  # la camera resta sul lanciatore durante il recupero, poi segue l'attrezzo
        s = _smooth((self.t - hold) / (fe - hold)) if self.t > hold else 0.0
        ball = sp_shot_position(d, self.t, we, fe)
        out.update(pose=pose, ball=ball, focus=0.75 * d * s)
        out["ty"] = 1.0 + 0.55 * max(0.0, ball[1] - 1.0) * _smooth((self.t - we - 0.1) / 0.4)  # inclina piano verso l'attrezzo
        out["show_mark"] = self.t >= fe and not foul
        out["show_flag"] = self.t >= fe
        return out

    def _camera(self, fr: Dict[str, Any], w: int, h: int) -> Camera:
        focus, ty = fr["focus"], fr["ty"]
        if fr["static"]:
            # inquadratura d'insieme, ferma: dipende solo dalle misure della gara (lo/hi), non dalla prova.
            # Così le prove veloci degli altri atleti non fanno saltare la camera.
            span = max(1.0, self.hi - self.lo)
            if self.kind == "lj":
                return Camera((focus - 1.0 - 0.25 * span, 2.4, LJ_Z + 7.0 + 0.3 * span), (focus + 0.5, 0.35, LJ_Z), FOV_DEG, w, h)
            return Camera((focus - 8.0 - 0.7 * span, 3.2, 6.0 + 0.2 * span), (focus, 0.3, 0.0), FOV_DEG, w, h)
        # camera bassa e ravvicinata, dietro e di lato all'azione (come nelle riprese arcade di atletica)
        if self.kind == "lj":
            return Camera((focus - 4.0, 1.5, LJ_Z + 4.2), (focus + 2.4, 0.95, LJ_Z), FOV_DEG, w, h)
        return Camera((focus - 6.0, 2.3, 4.0), (focus + 3.5, ty, 0.2), FOV_DEG, w, h)

    # ---- scenografia
    def _label3(self, p: QPainter, cam: Camera, pos: Vec, text: str, placed: List[Tuple[float, float]], color: str = "#f8fafc") -> None:
        """Etichetta ancorata a un punto 3D. Si salta se cade a meno di 34 px da una già disegnata
        (in lontananza le distanze si ammassano): si chiama dal più vicino al più lontano."""
        c = cam.to_cam(pos)
        if c[2] < NEAR * 4:
            return
        x, y = cam.proj(c)
        if any(abs(x - px) < 34 and abs(y - py) < 14 for px, py in placed):
            return
        placed.append((x, y))
        rect = QRectF(x - 30, y - 8, 60, 16)
        p.setPen(QColor(0, 0, 0, 150))
        p.drawText(rect.adjusted(1, 1, 1, 1), Qt.AlignmentFlag.AlignCenter, text)
        p.setPen(QColor(color))
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
        p.setPen(Qt.PenStyle.NoPen)

    def _strip(self, p: QPainter, cam: Camera, a: Tuple[float, float], b: Tuple[float, float], half_w: float, color, y: float = 0.012) -> None:
        """Striscia piatta (linea di campo) fra due punti (x, z) del piano."""
        dx, dz = b[0] - a[0], b[1] - a[1]
        n = math.hypot(dx, dz) or 1.0
        ox, oz = -dz / n * half_w, dx / n * half_w
        self._poly(p, cam, [(a[0] + ox, y, a[1] + oz), (b[0] + ox, y, b[1] + oz), (b[0] - ox, y, b[1] - oz), (a[0] - ox, y, a[1] - oz)], color)

    def _backdrop(self, p: QPainter, cam: Camera, w: int, h: int, stands_z: float, wall_z: float, grass_z0: float, xa: float, xb: float) -> None:
        sky = QLinearGradient(0, 0, 0, h * 0.55)
        sky.setColorAt(0.0, QColor("#4f8fd6"))
        sky.setColorAt(1.0, QColor("#cfe5f3"))
        p.fillRect(0, 0, w, h, QBrush(sky))
        p.setPen(Qt.PenStyle.NoPen)
        self._draw_stand(p, cam, -1.0, stands_z, xa, xb)
        # prato rasato a bande, solo fra il piede della tribuna e la camera (altrimenti copre la folla)
        band = 8.0
        x = math.floor(xa / band) * band
        while x < xb:
            col = "#2f7d3d" if int(x // band) % 2 == 0 else "#34873f"
            self._poly(p, cam, [(x, 0.0, grass_z0), (x + band + 0.05, 0.0, grass_z0), (x + band + 0.05, 0.0, 40.0), (x, 0.0, 40.0)], col)
            x += band
        # cartelloni
        seg = 6.0
        x = math.floor(xa / seg) * seg
        while x < xb:
            pm = self._board(int(x // seg))
            self._textured_quad(p, cam, [(x, 1.0, wall_z), (x + seg - 0.2, 1.0, wall_z), (x + seg - 0.2, 0.05, wall_z), (x, 0.05, wall_z)], pm)
            x += seg

    def _draw_long_jump_ground(self, p: QPainter, cam: Camera, w: int, h: int, focus: float) -> None:
        xa, xb = focus - 55.0, focus + 45.0
        self._backdrop(p, cam, w, h, -9.0, -6.0, -9.0, xa, xb)
        self._poly(p, cam, [(xa, 0.005, -5.5), (xb, 0.005, -5.5), (xb, 0.005, 16.0), (xa, 0.005, 16.0)], "#b5472a")  # tartan
        x_end = max(self.hi, 8.0) + 4.0
        # pedana, linee e asse di battuta
        for z in (0.0, RUNWAY_W):
            self._strip(p, cam, (xa, z), (0.0, z), 0.03, "#f1f5f9")
        self._poly(p, cam, [(-0.2, 0.012, 0.0), (0.0, 0.012, 0.0), (0.0, 0.012, RUNWAY_W), (-0.2, 0.012, RUNWAY_W)], "#ffffff")
        self._poly(p, cam, [(0.0, 0.012, 0.0), (0.1, 0.012, 0.0), (0.1, 0.012, RUNWAY_W), (0.0, 0.012, RUNWAY_W)], "#7c8798")  # plastilina
        # buca: bordo e sabbia
        z0, z1 = LJ_Z - PIT_HALF_W, LJ_Z + PIT_HALF_W
        self._poly(p, cam, [(PIT_X0 - 0.15, 0.02, z0 - 0.15), (x_end + 0.15, 0.02, z0 - 0.15), (x_end + 0.15, 0.02, z1 + 0.15), (PIT_X0 - 0.15, 0.02, z1 + 0.15)], "#cbd5e1")
        self._poly(p, cam, [(PIT_X0, 0.03, z0), (x_end, 0.03, z0), (x_end, 0.03, z1), (PIT_X0, 0.03, z1)], SAND)
        # righello a bordo buca (lato camera)
        font = QFont(self.font())
        font.setPointSize(8)
        font.setBold(True)
        p.setFont(font)
        first = int(max(1.0, math.ceil(self.lo * 0.7)))
        placed: List[Tuple[float, float]] = []
        for m in range(first, int(x_end)):
            self._poly(p, cam, [(m - 0.03, 0.035, z1), (m + 0.03, 0.035, z1), (m + 0.03, 0.035, z1 + 0.35), (m - 0.03, 0.035, z1 + 0.35)], "#f8fafc")
            self._label3(p, cam, (float(m), 0.05, z1 + 0.75), f"{m} m", placed)

    def _draw_shot_put_ground(self, p: QPainter, cam: Camera, w: int, h: int, focus: float) -> None:
        xa, xb = focus - 50.0, focus + 55.0
        self._backdrop(p, cam, w, h, -14.0, -12.0, -14.0, xa, xb)
        reach = max(self.hi, 10.0) + 6.0
        # settore: linee a ±17,46° dal centro del cerchio
        for sgn in (-1.0, 1.0):
            ex = RING_CX + reach * math.cos(SECTOR_HALF)
            ez = sgn * reach * math.sin(SECTOR_HALF)
            self._strip(p, cam, (RING_CX, 0.0), (ex, ez), 0.05, "#f1f5f9")
        # archi delle distanze (ogni 2 m) con la misura
        font = QFont(self.font())
        font.setPointSize(8)
        font.setBold(True)
        p.setFont(font)
        step = 2 if reach < 40 else 5
        first = max(step, int(math.ceil(max(1.0, self.lo * 0.6) / step) * step))
        placed: List[Tuple[float, float]] = []
        for m in range(first, int(reach), step):
            r = RING_R + m
            n = 12
            pts = [(RING_CX + r * math.cos(-SECTOR_HALF + 2 * SECTOR_HALF * i / n), r * math.sin(-SECTOR_HALF + 2 * SECTOR_HALF * i / n)) for i in range(n + 1)]
            for a, b in zip(pts, pts[1:]):
                self._strip(p, cam, a, b, 0.035, QColor(255, 255, 255, 170))
            self._label3(p, cam, (RING_CX + r * math.cos(SECTOR_HALF * 0.78), 0.08, r * math.sin(SECTOR_HALF * 0.78) + 0.35), f"{m} m", placed)
        # cerchio di lancio e fermapiede
        ring = [(RING_CX + RING_R * math.cos(a), 0.02, RING_R * math.sin(a)) for a in [i * math.pi / 12 for i in range(24)]]
        self._poly(p, cam, ring, "#e2e8f0")
        inner = [(RING_CX + (RING_R - 0.06) * math.cos(a), 0.025, (RING_R - 0.06) * math.sin(a)) for a in [i * math.pi / 12 for i in range(24)]]
        self._poly(p, cam, inner, "#9ca3af")
        self._poly(p, cam, [(-0.08, 0.1, -0.55), (0.08, 0.1, -0.55), (0.08, 0.1, 0.55), (-0.08, 0.1, 0.55)], "#f8fafc")  # fermapiede (sopra)
        self._poly(p, cam, [(-0.08, 0.0, 0.55), (0.08, 0.0, 0.55), (0.08, 0.1, 0.55), (-0.08, 0.1, 0.55)], "#94a3b8")  # fianco vicino

    # ---- elementi di scena
    def _flag(self, p: QPainter, cam: Camera, x: float, z: float, label: str, color: str) -> None:
        top = cam.to_cam((x, 1.5, z))
        if top[2] < NEAR * 3:
            return
        self._line3(p, cam, (x, 0.0, z), (x, 1.5, z), 0.025, QColor("#e2e8f0"))
        sx, sy = cam.proj(top)
        scale = max(0.8, min(1.6, 14.0 / top[2] + 0.7))
        bw, bh = 62 * scale, 16 * scale
        font = QFont(self.font())
        font.setPointSize(max(8, int(9 * scale)))
        font.setBold(True)
        p.setFont(font)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(color))
        p.drawRect(QRectF(sx, sy, bw, bh))
        p.setPen(QColor("#0f172a"))
        p.drawText(QRectF(sx, sy, bw, bh), Qt.AlignmentFlag.AlignCenter, label)
        p.setPen(Qt.PenStyle.NoPen)

    def _dent(self, p: QPainter, cam: Camera, x: float, z: float, rx: float, rz: float, color: str) -> None:
        pts = [(x + rx * math.cos(a), 0.045, z + rz * math.sin(a)) for a in [i * math.pi / 8 for i in range(16)]]
        self._poly(p, cam, pts, color)

    def _spray(self, p: QPainter, cam: Camera, x: float, z: float, age: float, color: str, spread: float) -> None:
        r = min(1.0, age * 2.5)
        if r <= 0.0 or age > 1.2:
            return
        p.setBrush(QColor(color))
        p.setPen(Qt.PenStyle.NoPen)
        for k in range(10):
            a = k * 0.63
            pos = (x + spread * math.cos(a) * r, 0.08 + 0.9 * abs(math.sin(a)) * r * (1.0 - 0.45 * r), z + spread * 0.8 * math.sin(2.3 * a) * r)
            c = cam.to_cam(pos)
            if c[2] < NEAR * 2:
                continue
            px, py = cam.proj(c)
            size = max(2.0, 0.06 * cam.f / c[2])
            p.drawRect(QRectF(px - size / 2, py - size / 2, size, size))

    # ---- paint
    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt API)
        p = QPainter(self)
        w, h = self.width(), self.height()
        lj = self.kind == "lj"
        fr = self._frame()
        cam = self._camera(fr, w, h)

        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)  # grandi superfici senza antialiasing
        if lj:
            self._draw_long_jump_ground(p, cam, w, h, fr["focus"])
        else:
            self._draw_shot_put_ground(p, cam, w, h, fr["focus"])
        p.setPen(Qt.PenStyle.NoPen)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        cur = self.cur
        if cur is not None:
            d, foul = cur["dist"], cur["foul"]
            kit = QColor("#fbbf24") if cur["player"] else QColor.fromHsv(zlib.crc32(cur["team"].encode()) % 360, 170, 215)
            skin = TrackRaceWidget._skin(cur["name"])
            label = "NULLO" if foul else f"{d:.2f}"
            colour = "#f87171" if foul else "#34d399"
            mark_z = LJ_Z if lj else 0.0
            if fr["show_mark"]:
                if lj:
                    self._dent(p, cam, d - 0.15, mark_z, 0.55, 0.5, SAND_DENT)
                else:
                    self._dent(p, cam, d, mark_z, 0.35, 0.28, "#1b4d2b")
            pose: Optional[Pose] = fr["pose"]
            if pose is not None:
                self._draw_shadow(p, cam, pose.hip[0], pose.hip[2], 0.55, 0.3)
                self._draw_figure(p, cam, pose.hip, pose.yaw, pose.lean, pose.legs, pose.arms, kit, skin, cur["player"], cur["name"])
            if fr["ball"] is not None:
                bx, by, bz = fr["ball"]
                self._draw_shadow(p, cam, bx, bz, 0.12, 0.1)
                p.setPen(Qt.PenStyle.NoPen)
                if self.t > self.SP_WIND_END:  # scia breve: un attrezzo lontano è un puntino
                    for k in (3, 2, 1):
                        tk = max(self.SP_WIND_END, self.t - 0.05 * k)
                        ck = cam.to_cam(sp_shot_position(d, tk, self.SP_WIND_END, self.SP_FLY_END))
                        if ck[2] >= NEAR:
                            kx, ky = cam.proj(ck)
                            rk = max(2.0, 0.05 * cam.f / ck[2])
                            p.setBrush(QColor(226, 232, 240, 45 * (4 - k)))
                            p.drawEllipse(QPointF(kx, ky), rk, rk)
                c = cam.to_cam((bx, by, bz))
                if c[2] >= NEAR:
                    sx, sy = cam.proj(c)
                    r = max(4.0, 0.063 * cam.f / c[2])
                    p.setBrush(QColor("#e2e8f0"))
                    p.setPen(QPen(QColor("#475569"), 1))
                    p.drawEllipse(QPointF(sx, sy), r, r)
                    p.setPen(Qt.PenStyle.NoPen)
            if fr["show_mark"] and cur["animate"]:
                age = fr["age"] if lj else self.t - self.SP_FLY_END
                self._spray(p, cam, d if not lj else d - 0.1, mark_z, age, SAND if lj else "#3f7d4a", 0.9 if lj else 0.5)
            if fr["show_flag"]:
                self._flag(p, cam, 0.0 if foul else d, (LJ_Z - PIT_HALF_W - 0.4) if lj else 0.9, label, colour)
            self._paint_hud(p, w, h, fr, label, colour)
        p.end()

    def _paint_hud(self, p: QPainter, w: int, h: int, fr: Dict[str, Any], label: str, colour: str) -> None:
        cur = self.cur
        assert cur is not None
        font = QFont(self.font())
        font.setPointSize(9)
        p.setFont(font)
        p.setPen(QColor("#fbbf24" if cur["player"] else "#e2e8f0"))
        p.fillRect(QRectF(14, 10, 330, 20), QColor(11, 18, 32, 210))
        p.drawText(QRectF(20, 10, 322, 20), Qt.AlignmentFlag.AlignVCenter,
                   f"Prova {cur['n']}/{cur['total']} — {cur['name']} ({cur['team']})")
        if (fr["show_flag"] and cur["animate"]) or (cur["foul"] and not cur["animate"]):  # misura/nullo in grande
            big = QFont(font)
            big.setPointSize(26)
            big.setBold(True)
            p.setFont(big)
            text = label if label == "NULLO" else f"{label} m"
            area = QRectF(0, h * 0.14, w, 54)
            p.setPen(QColor(0, 0, 0, 180))
            p.drawText(area.adjusted(2, 2, 2, 2), Qt.AlignmentFlag.AlignCenter, text)
            p.setPen(QColor(colour))
            p.drawText(area, Qt.AlignmentFlag.AlignCenter, text)
