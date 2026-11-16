"""Vista 3D dei concorsi (Salto in Lungo e Getto del Peso) nello stadio dell'ovale.

Condivide camera, proiezione, ombreggiatura muscolare, texture e giudici con `views/race_3d.py`.
Sostituisce la scena 2D di `FieldSceneWidget` mantenendone intatta l'API per `FieldEventWidget` e i test.
"""

from __future__ import annotations

import math
import random
import zlib
from typing import Dict, Optional, Sequence, Tuple

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
)

from models.entities import CompetitionTier, WeatherCondition
from views.race_3d import (
    NEAR,
    Camera,
    Vec,
    _clamp,
    _lerp,
    draw_line3,
    draw_official_3d,
    draw_poly,
    draw_shaded_limb,
    draw_textured_ground_quad,
    draw_textured_quad,
    get_soft_shadow,
    get_sponsor_board,
    make_crowd_strip,
    make_grass_tile,
    make_track_tile,
)
from views.race_viewer import FieldSceneWidget, TrackRaceWidget, _short


def make_sand_tile() -> QPixmap:
    """Texture granulare della sabbia rastrellata nella buca del salto in lungo."""
    w, h = 256, 128
    img = QImage(w, h, QImage.Format.Format_RGB32)
    base = QColor("#dec48d")
    img.fill(base)
    q = QPainter(img)
    rng = random.Random(505)
    # solchi leggeri della rastrellatura longitudinale
    for y in range(0, h, 4):
        col = base.darker(106) if (y // 4) % 2 == 0 else base.lighter(104)
        q.fillRect(0, y, w, 2, col)
    light = base.lighter(118)
    dark = base.darker(122)
    light.setAlpha(95)
    dark.setAlpha(95)
    for _ in range(1800):
        q.fillRect(rng.randrange(w), rng.randrange(h), 2, 1, light if rng.random() < 0.45 else dark)
    q.end()
    return QPixmap.fromImage(img)


class Field3DSceneWidget(FieldSceneWidget):
    """Scena 3D televisiva per Salto in Lungo e Getto del Peso."""

    _sand_tile_cache: Optional[QPixmap] = None
    _track_cache: Dict[Tuple[str, bool], QPixmap] = {}
    _grass_cache: Dict[str, QPixmap] = {}
    _crowd_cache_3d: Dict[Tuple[bool, int], QPixmap] = {}
    _marker_cache: Dict[int, QPixmap] = {}

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(280)
        self._cam_label = "PIT-CAM"

    def _is_evening(self) -> bool:
        return self._tier in (CompetitionTier.NAZIONALE, CompetitionTier.INTERNAZIONALE)

    def _is_blue_track(self) -> bool:
        surf = (self._surface or "").lower()
        return self._tier == CompetitionTier.INTERNAZIONALE or "mondo" in surf or "blu" in surf

    def _sand_pm(self) -> QPixmap:
        if Field3DSceneWidget._sand_tile_cache is None:
            Field3DSceneWidget._sand_tile_cache = make_sand_tile()
        return Field3DSceneWidget._sand_tile_cache

    def _track_pm(self) -> QPixmap:
        rain = self._weather == WeatherCondition.PIOGGIA
        col = ("#1a549c" if rain else "#1f62b5") if self._is_blue_track() else ("#8f3220" if rain else "#b34128")
        key = (col, rain)
        pm = self._track_cache.get(key)
        if pm is None:
            pm = make_track_tile(col, rain=rain)
            self._track_cache[key] = pm
        return pm

    def _grass_pm(self, hex_col: str) -> QPixmap:
        pm = self._grass_cache.get(hex_col)
        if pm is None:
            pm = make_grass_tile(hex_col)
            self._grass_cache[hex_col] = pm
        return pm

    def _crowd_pm(self) -> QPixmap:
        rain = self._weather == WeatherCondition.PIOGGIA
        dark = rain or self._is_evening()
        dens = 9 if self._tier == CompetitionTier.INTERNAZIONALE else (8 if self._tier == CompetitionTier.NAZIONALE else 7)
        key = (dark, dens)
        pm = self._crowd_cache_3d.get(key)
        if pm is None:
            pm = make_crowd_strip(512, 160, density=dens / 10.0, dark=dark)
            self._crowd_cache_3d[key] = pm
        return pm

    def _dist_marker_pm(self, meters: int) -> QPixmap:
        pm = self._marker_cache.get(meters)
        if pm is None:
            pm = QPixmap(48, 28)
            pm.fill(QColor("#0f172a"))
            q = QPainter(pm)
            q.setPen(QPen(QColor("#facc15"), 2))
            q.drawRect(1, 1, 46, 26)
            q.setPen(QColor("#f8fafc"))
            f = QFont("Arial", 13)
            f.setBold(True)
            q.setFont(f)
            q.drawText(QRectF(0, 0, 48, 28), Qt.AlignmentFlag.AlignCenter, f"{meters}m")
            q.end()
            self._marker_cache[meters] = pm
        return pm

    # ---- camera regia TV
    def _make_camera(self, w: int, h: int) -> Camera:
        cur = self.cur
        if self.kind == "lj":
            if cur is None or not cur["animate"]:
                self._cam_label = "PIT-CAM"
                return Camera((5.8, 2.5, 8.2), (4.6, 0.75, 0.0), 30.0, w, h)
            t = self.t
            d = cur["dist"]
            run_end = 1.20
            if t < run_end:
                self._cam_label = "RUNWAY-CAM"
                x_m = -14.0 + 14.0 * (t / run_end)
                return Camera((x_m + 5.6, 1.55, 5.0), (x_m + 0.8, 0.92, 0.0), 30.0, w, h)
            self._cam_label = "PIT-CAM"
            mid = max(3.5, d * 0.54)
            return Camera((mid + 1.4, 2.55, 9.4), (mid - 0.1, 1.05, 0.0), 31.0, w, h)

        # Getto del peso
        if cur is None or not cur["animate"]:
            self._cam_label = "SECTOR-CAM"
            return Camera((7.5, 3.2, 11.0), (6.5, 0.7, 0.0), 32.0, w, h)
        t = self.t
        d = cur["dist"]
        if t < 1.15:
            self._cam_label = "RING-CAM"
            return Camera((2.4, 1.75, 4.4), (-1.1, 0.95, 0.0), 30.0, w, h)
        self._cam_label = "SECTOR-CAM"
        s_ = _clamp((t - 1.0) / 1.05, 0.0, 1.0)
        fx = _lerp(1.5, d * 0.65, s_)
        return Camera((fx + 5.0, 3.3, 12.2), (fx, 0.75, 0.0), 32.0, w, h)

    # ---- sfondo stadio comune
    def _draw_stadium_backdrop(self, p: QPainter, cam: Camera, w: int, h: int, x_min: float, x_max: float) -> None:
        rain = self._weather == WeatherCondition.PIOGGIA
        evening = self._is_evening()
        sky = QLinearGradient(0, 0, 0, h * 0.56)
        if evening:
            sky.setColorAt(0.0, QColor("#050914"))
            sky.setColorAt(0.65, QColor("#0f172a"))
            sky.setColorAt(1.0, QColor("#1e293b"))
        elif rain:
            sky.setColorAt(0.0, QColor("#3f4c5e"))
            sky.setColorAt(1.0, QColor("#94a3b8"))
        else:
            sky.setColorAt(0.0, QColor("#1d4ed8"))
            sky.setColorAt(0.62, QColor("#60a5fa"))
            sky.setColorAt(1.0, QColor("#dbeafe"))
        p.fillRect(0, 0, w, h, QBrush(sky))
        p.setPen(Qt.PenStyle.NoPen)
        p.fillRect(0, int(h * 0.36), w, int(h * 0.64), QColor("#152c1c" if evening else "#24522e"))

        # prato a bande intorno alla pedana
        band = 8.0
        xb = math.floor(x_min / band) * band
        while xb < x_max:
            light = int(xb // band) % 2 == 0
            g_hex = "#2d7539" if light else "#348440"
            if rain or evening:
                g_hex = QColor(g_hex).darker(120).name()
            draw_textured_ground_quad(
                p, cam,
                [(xb, 0.0, -14.0), (xb + band + 0.1, 0.0, -14.0), (xb + band + 0.1, 0.0, 12.0), (xb, 0.0, 12.0)],
                self._grass_pm(g_hex), g_hex,
            )
            xb += band

        # tribuna dello stadio sullo sfondo + cartelloni LED (più arretrati nel peso per il settore a 35°)
        crowd_pm = self._crowd_pm()
        z_board = -4.2 if self.kind == "lj" else -7.5
        z_stand = -15.0 if self.kind == "lj" else -18.5
        seg = 16.0
        sx = math.floor((x_min - 36.0) / seg) * seg
        while sx < x_max + 36.0:
            x0, x1 = sx - 0.1, sx + seg + 0.1
            draw_poly(p, cam, [(x0, 0.0, z_stand), (x1, 0.0, z_stand), (x1, 1.3, z_stand), (x0, 1.3, z_stand)], "#475569")
            q1 = [(x0, 1.3, z_stand), (x1, 1.3, z_stand), (x1, 9.2, z_stand - 9.0), (x0, 9.2, z_stand - 9.0)]
            draw_poly(p, cam, q1, "#334155")
            draw_textured_quad(p, cam, [q1[3], q1[2], q1[1], q1[0]], crowd_pm)
            if evening:
                draw_poly(p, cam, [(x0, 9.2, z_stand - 9.0), (x1, 9.2, z_stand - 9.0), (x1, 13.5, z_stand - 11.0), (x0, 13.5, z_stand - 11.0)], "#0f172a")
                draw_line3(p, cam, (x0, 13.2, z_stand - 4.5), (x1, 13.2, z_stand - 4.5), 0.16, QColor("#fef08a"))
            sx += seg

        bseg = 5.5
        bx = math.floor((x_min - 28.0) / bseg) * bseg
        idx = 0
        while bx < x_max + 28.0:
            pm = get_sponsor_board(idx)
            draw_textured_quad(p, cam, [(bx, 0.85, z_board), (bx + bseg - 0.15, 0.85, z_board), (bx + bseg - 0.15, 0.04, z_board), (bx, 0.04, z_board)], pm)
            bx += bseg
            idx += 1

    # ---- atleta articolato 3D locale
    def _draw_actor(
        self, p: QPainter, cam: Camera, x: float, hip_h: float, lean: float,
        kit: QColor, skin: QColor, is_player: bool, bib: int,
        leg_l: Tuple[float, float], leg_r: Tuple[float, float],
        arm_l: Tuple[float, float], arm_r: Tuple[float, float],
        ground_shadow_y: float = 0.015,
        shot_in_hand: bool = False,
    ) -> None:
        # ombra morbida a terra
        draw_textured_ground_quad(
            p, cam,
            [(x - 0.55, ground_shadow_y, -0.32), (x + 0.45, ground_shadow_y, -0.32), (x + 0.45, ground_shadow_y, 0.32), (x - 0.55, ground_shadow_y, 0.32)],
            get_soft_shadow(), "#0f172a",
        )
        s_l, c_l = math.sin(lean), math.cos(lean)
        hip = (x, hip_h, 0.0)
        sh_mid = (x + 0.56 * s_l, hip_h + 0.56 * c_l, 0.0)
        neck = (sh_mid[0] + 0.11 * s_l, sh_mid[1] + 0.11 * c_l, 0.0)
        head = (neck[0] + 0.11 * s_l, neck[1] + 0.11 * c_l, 0.0)
        shorts = QColor("#0f172a")
        spike_col = kit.lighter(135) if is_player else QColor("#f8fafc")

        def draw_leg(side: float, angles: Tuple[float, float]) -> None:
            th_a, kn_flex = angles
            is_near = side > 0
            col_s = skin if is_near else skin.darker(128)
            col_sh = shorts if is_near else shorts.darker(125)
            hs = (hip[0], hip[1] - 0.02, side * 0.105)
            kn = (hs[0] + 0.46 * math.sin(th_a), hs[1] - 0.46 * math.cos(th_a), hs[2])
            sh_a = th_a - kn_flex
            ak = (kn[0] + 0.45 * math.sin(sh_a), max(0.03, kn[1] - 0.45 * math.cos(sh_a)), hs[2])
            to = (ak[0] + 0.16 * math.cos(sh_a * 0.4), max(0.02, ak[1] - 0.03), hs[2])
            mid_t = (_lerp(hs[0], kn[0], 0.55), _lerp(hs[1], kn[1], 0.55), hs[2])
            calf_m = (_lerp(kn[0], ak[0], 0.38), _lerp(kn[1], ak[1], 0.38), hs[2])
            draw_shaded_limb(p, cam, hs, kn, 0.092, 0.060, col_s)
            draw_shaded_limb(p, cam, hs, mid_t, 0.105, 0.088, col_sh)
            draw_shaded_limb(p, cam, kn, calf_m, 0.060, 0.068, col_s)
            draw_shaded_limb(p, cam, calf_m, ak, 0.065, 0.036, col_s)
            draw_shaded_limb(p, cam, ak, to, 0.042, 0.028, spike_col if is_near else spike_col.darker(120))

        def draw_arm(side: float, angles: Tuple[float, float]) -> None:
            up_a, el_bend = angles
            is_near = side > 0
            col_s = skin if is_near else skin.darker(128)
            ss = (sh_mid[0], sh_mid[1] - 0.03, side * 0.195)
            el = (ss[0] + 0.30 * math.sin(up_a), ss[1] - 0.30 * math.cos(up_a), ss[2])
            fa = up_a + el_bend
            ha = (el[0] + 0.27 * math.sin(fa), el[1] - 0.27 * math.cos(fa), ss[2])
            draw_shaded_limb(p, cam, ss, el, 0.058, 0.045, col_s)
            draw_shaded_limb(p, cam, el, ha, 0.044, 0.028, col_s)
            if shot_in_hand and is_near:
                hc = cam.to_cam(ha)
                if hc[2] >= NEAR:
                    hx, hy = cam.proj(hc)
                    sr = max(3.0, 0.068 * cam.f / hc[2])
                    sg = QRadialGradient(hx + sr * 0.3, hy - sr * 0.3, sr * 1.4)
                    sg.setColorAt(0.0, QColor("#e2e8f0"))
                    sg.setColorAt(0.55, QColor("#64748b"))
                    sg.setColorAt(1.0, QColor("#1e293b"))
                    p.setBrush(QBrush(sg))
                    p.drawEllipse(QPointF(hx, hy), sr, sr)

        draw_leg(-1.0, leg_l)
        draw_arm(-1.0, arm_l)
        draw_shaded_limb(p, cam, (hip[0], hip[1] - 0.04, 0.0), (hip[0] + 0.10 * s_l, hip[1] + 0.11 * c_l, 0.0), 0.145, 0.140, shorts)
        wl = (hip[0] + 0.10 * s_l, hip[1] + 0.10 * c_l, -0.12)
        wr = (hip[0] + 0.10 * s_l, hip[1] + 0.10 * c_l, 0.12)
        sl = (sh_mid[0], sh_mid[1], -0.18)
        sr = (sh_mid[0], sh_mid[1], 0.18)
        draw_poly(p, cam, [wl, wr, sr, sl], kit.lighter(108))
        draw_poly(p, cam, [wl, (hip[0] + 0.10 * s_l, hip[1] + 0.10 * c_l, 0.0), sh_mid, sl], kit.darker(120))
        ch_lo = (hip[0] + 0.24 * s_l + 0.04, hip[1] + 0.24 * c_l, 0.0)
        ch_hi = (hip[0] + 0.44 * s_l + 0.04, hip[1] + 0.44 * c_l, 0.0)
        draw_poly(p, cam, [(ch_lo[0], ch_lo[1], -0.09), (ch_lo[0], ch_lo[1], 0.09), (ch_hi[0], ch_hi[1], 0.09), (ch_hi[0], ch_hi[1], -0.09)], "#f8fafc")
        draw_shaded_limb(p, cam, sh_mid, neck, 0.062, 0.052, skin.darker(108))
        draw_leg(1.0, leg_r)
        draw_arm(1.0, arm_r)

        hc = cam.to_cam(head)
        if hc[2] >= NEAR:
            hx, hy = cam.proj(hc)
            r = max(2.4, 0.115 * cam.f / hc[2])
            hg = QRadialGradient(hx + r * 0.25, hy - r * 0.25, r * 1.35)
            hg.setColorAt(0.0, skin.lighter(118))
            hg.setColorAt(0.55, skin)
            hg.setColorAt(1.0, skin.darker(135))
            p.setBrush(QBrush(hg))
            p.drawEllipse(QPointF(hx, hy), r * 0.96, r * 1.12)
            p.setBrush(QColor("#111827") if bib % 3 else QColor("#451a03"))
            p.drawChord(QRectF(hx - r * 1.02, hy - r * 1.18, 2.04 * r, 2.10 * r), 35 * 16, 155 * 16)
            if is_player:
                p.setBrush(QColor("#fbbf24"))
                p.drawChord(QRectF(hx - r * 1.0, hy - r * 1.12, 2.0 * r, 1.95 * r), 22 * 16, 136 * 16)

    # ---- Salto in Lungo 3D
    def _paint_long_jump(self, p: QPainter, cam: Camera) -> None:
        # pedana di rincorsa in tartan (-24m .. 1.0m)
        track_pm = self._track_pm()
        for rx0 in (-24.0, -16.0, -8.0, 0.0):
            rx1 = min(1.0, rx0 + 8.05)
            draw_textured_ground_quad(p, cam, [(rx0, 0.004, -0.61), (rx1, 0.004, -0.61), (rx1, 0.004, 0.61), (rx0, 0.004, 0.61)], track_pm, "#b34128")
        for z_line in (-0.61, 0.61):
            draw_poly(p, cam, [(-24.0, 0.01, z_line - 0.025), (1.0, 0.01, z_line - 0.025), (1.0, 0.01, z_line + 0.025), (-24.0, 0.01, z_line + 0.025)], "#f8fafc")

        # asse di battuta bianco + striscia rossa in plastilina per i falli + sensori ottici
        draw_poly(p, cam, [(-0.20, 0.013, -0.61), (0.0, 0.013, -0.61), (0.0, 0.013, 0.61), (-0.20, 0.013, 0.61)], "#ffffff")
        draw_poly(p, cam, [(0.0, 0.016, -0.61), (0.10, 0.016, -0.61), (0.10, 0.016, 0.61), (0.0, 0.016, 0.61)], "#dc2626")
        for zs in (-0.85, 0.85):
            draw_poly(p, cam, [(-0.12, 0.0, zs - 0.08), (0.12, 0.0, zs - 0.08), (0.12, 0.22, zs + 0.08), (-0.12, 0.22, zs + 0.08)], "#eab308")

        # buca della sabbia incassata con bordo rialzato e sabbia granulare (1.0m .. 10.4m)
        pw = 1.45
        sand_pm = self._sand_pm()
        draw_poly(p, cam, [(0.88, 0.0, -pw - 0.14), (10.52, 0.0, -pw - 0.14), (10.52, 0.06, -pw - 0.14), (0.88, 0.06, -pw - 0.14)], "#cbd5e1")
        draw_poly(p, cam, [(0.88, 0.05, -pw - 0.14), (10.52, 0.05, -pw - 0.14), (10.52, 0.05, pw + 0.14), (0.88, 0.05, pw + 0.14)], "#94a3b8")
        for sx0 in (1.0, 5.7):
            sx1 = min(10.4, sx0 + 4.75)
            draw_textured_ground_quad(p, cam, [(sx0, 0.055, -pw), (sx1, 0.055, -pw), (sx1, 0.055, pw), (sx0, 0.055, pw)], sand_pm, "#dec48d")
        # ombra interna sul bordo superiore della fossa
        draw_poly(p, cam, [(1.0, 0.058, -pw), (10.4, 0.058, -pw), (10.4, 0.058, -pw + 0.22), (1.0, 0.058, -pw + 0.22)], QColor(15, 23, 42, 65))

        # coni segnamisura lungo la buca (5m..9m) + linea laser del primato/miglior salto della gara
        for mt in range(5, 10):
            draw_textured_quad(p, cam, [(mt - 0.22, 0.34, -pw - 0.22), (mt + 0.22, 0.34, -pw - 0.22), (mt + 0.22, 0.05, -pw - 0.22), (mt - 0.22, 0.05, -pw - 0.22)], self._dist_marker_pm(mt))
            draw_line3(p, cam, (mt, 0.06, -pw), (mt, 0.06, -pw + 0.25), 0.02, QColor("#f8fafc"))
        if 1.2 < self.hi < 10.2:
            draw_line3(p, cam, (self.hi, 0.062, -pw), (self.hi, 0.062, pw), 0.024, QColor("#34d399"))

        # giudice alla battuta
        draw_official_3d(p, cam, -0.1, -2.0)

        cur = self.cur
        if cur is None:
            return
        t = self.t
        d = cur["dist"]
        foul = cur["foul"]
        kit = QColor("#f59e0b") if cur["player"] else QColor.fromHsv(zlib.crc32(cur["team"].encode()) % 360, 170, 215)
        skin = TrackRaceWidget._skin(cur["name"])
        bib = (zlib.crc32(cur["name"].encode()) % 890) + 100

        run_end, jump_end = 1.20, 1.98
        landed = (not cur["animate"]) or (t >= jump_end)

        # bandierina del giudice (bianca se valido, rossa se nullo)
        flag_up = landed
        fy0, fy1 = (0.95, 1.75) if flag_up else (0.55, 0.95)
        fx_j, fz_j = 0.05, -1.75
        draw_line3(p, cam, (fx_j, fy0, fz_j), (fx_j, fy1, fz_j), 0.018, QColor("#e2e8f0"))
        flag_col = "#ef4444" if foul else "#f8fafc"
        draw_poly(p, cam, [(fx_j, fy1, fz_j), (fx_j + 0.35, fy1, fz_j), (fx_j + 0.35, fy1 - 0.24, fz_j), (fx_j, fy1 - 0.24, fz_j)], flag_col)

        if not cur["animate"]:
            # prova rapida avversario: impronta + linea di misura in sabbia
            lx = 0.05 if foul else d
            if not foul:
                draw_poly(p, cam, [(lx - 0.25, 0.06, -0.25), (lx + 0.25, 0.06, -0.25), (lx + 0.25, 0.06, 0.25), (lx - 0.25, 0.06, 0.25)], QColor(120, 88, 40, 140))
                draw_line3(p, cam, (lx, 0.064, -pw), (lx, 0.064, pw), 0.025, QColor("#fbbf24"))
            return

        x_takeoff = 0.06 if foul else -0.04
        if t < run_end:
            u = t / run_end
            x_m = _lerp(-14.0, x_takeoff, u)
            ph = 2.0 * math.pi * 2.5 * t
            ratio = _clamp(0.45 + 0.55 * u, 0.0, 1.0)
            amp = 0.5 + 0.55 * ratio
            # negli ultimi 0.15s leggero abbassamento del penultimo appoggio prima dello stacco
            pre_dip = 0.10 * _clamp((t - 1.05) / 0.15, 0.0, 1.0)
            ll = (amp * math.sin(ph), 0.3 + 1.45 * max(0.0, math.sin(ph + 1.2)))
            lr = (amp * math.sin(ph + math.pi), 0.3 + 1.45 * max(0.0, math.sin(ph + math.pi + 1.2)))
            al = (-amp * 1.1 * math.sin(ph), 1.35)
            ar = (-amp * 1.1 * math.sin(ph + math.pi), 1.35)
            self._draw_actor(p, cam, x_m, 0.94 - pre_dip + 0.04 * abs(math.sin(ph)), 0.18, kit, skin, cur["player"], bib, ll, lr, al, ar)
        elif t < jump_end:
            s_ = (t - run_end) / (jump_end - run_end)
            x_m = _lerp(x_takeoff, d, s_)
            apex = 0.72 + 0.03 * d
            air_y = 4.0 * apex * s_ * (1.0 - s_)
            if s_ < 0.42:
                # fase di stacco / sospensione (hitch-kick)
                k = s_ / 0.42
                lean = _lerp(0.05, -0.10, k)
                ll = (_lerp(1.05, -0.45, k), _lerp(1.15, 0.40, k))
                lr = (_lerp(-0.55, 0.95, k), _lerp(0.25, 1.25, k))
                al = (_lerp(-1.9, -2.5, k), 0.35)
                ar = (_lerp(1.4, -2.3, k), 0.45)
            else:
                # chiusura a forbice (pike) prima dell'impatto in sabbia
                k = (s_ - 0.42) / 0.58
                lean = _lerp(-0.08, 0.58, k)
                ll = (_lerp(-0.35, 1.32, k), _lerp(0.45, 0.22, k))
                lr = (_lerp(0.95, 1.36, k), _lerp(1.15, 0.22, k))
                al = (_lerp(-2.4, 0.95, k), 0.25)
                ar = (_lerp(-2.2, 1.05, k), 0.25)
            self._draw_actor(p, cam, x_m, 0.95 + air_y, lean, kit, skin, cur["player"], bib, ll, lr, al, ar, ground_shadow_y=0.058)
        else:
            # atterraggio nella sabbia + cratere + spruzzo parabolico di granelli + linea laser misura
            age = t - jump_end
            draw_poly(p, cam, [(d - 0.32, 0.06, -0.32), (d + 0.32, 0.06, -0.32), (d + 0.32, 0.06, 0.32), (d - 0.32, 0.06, 0.32)], QColor(120, 88, 40, 145))
            self._draw_actor(p, cam, d - 0.12, 0.52, 0.72, kit, skin, cur["player"], bib, (1.15, 1.35), (1.22, 1.30), (1.05, 0.25), (0.95, 0.35), ground_shadow_y=0.06)
            # schizzo di sabbia in 3D
            if age < 0.75:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor("#ebd6a3"))
                for k in range(22):
                    ang = -0.9 + (k / 21.0) * 1.8
                    vx = 2.6 * math.cos(ang) + (k % 3) * 0.45
                    vz = 1.6 * math.sin(ang)
                    vy0 = 2.4 + (k % 4) * 0.45
                    px_ = d + 0.15 + vx * age
                    pz_ = vz * age
                    py_ = max(0.06, 0.12 + vy0 * age - 4.9 * age * age)
                    c_pt = cam.to_cam((px_, py_, pz_))
                    if c_pt[2] >= NEAR:
                        sx_, sy_ = cam.proj(c_pt)
                        r_g = max(1.5, 0.028 * cam.f / c_pt[2])
                        p.drawEllipse(QPointF(sx_, sy_), r_g, r_g)
            # linea laser della misura raggiunta
            line_col = "#ef4444" if foul else "#fbbf24"
            draw_line3(p, cam, (d, 0.065, -pw), (d, 0.065, pw), 0.026, QColor(line_col))

    # ---- Getto del Peso 3D
    def _paint_shot_put(self, p: QPainter, cam: Camera) -> None:
        # pedana circolare in cemento (-2.14 .. 0.0) e fermapiedi
        ring_cx = -1.07
        steps = 16
        for k in range(steps):
            a0 = (2.0 * math.pi * k) / steps
            a1 = (2.0 * math.pi * (k + 1)) / steps
            draw_poly(
                p, cam,
                [(ring_cx, 0.01, 0.0), (ring_cx + 1.07 * math.cos(a0), 0.01, 1.07 * math.sin(a0)), (ring_cx + 1.07 * math.cos(a1), 0.01, 1.07 * math.sin(a1))],
                "#94a3b8",
            )
            draw_line3(
                p, cam,
                (ring_cx + 1.07 * math.cos(a0), 0.014, 1.07 * math.sin(a0)),
                (ring_cx + 1.07 * math.cos(a1), 0.014, 1.07 * math.sin(a1)),
                0.03, QColor("#f8fafc"),
            )
        # fermapiedi curvo davanti alla pedana
        draw_poly(p, cam, [(-0.08, 0.01, -0.58), (0.04, 0.01, -0.58), (0.04, 0.12, 0.58), (-0.08, 0.12, 0.58)], "#f8fafc")

        # linee bianche del settore di lancio (34.92°) e archi delle misure
        ang_s = math.radians(17.46)
        for sign in (-1.0, 1.0):
            draw_line3(p, cam, (0.0, 0.012, 0.0), (24.0 * math.cos(ang_s), 0.012, sign * 24.0 * math.sin(ang_s)), 0.03, QColor("#f8fafc"))
        for mt in (10, 14, 18, 22):
            for k in range(6):
                t0 = -ang_s + (2 * ang_s * k) / 6
                t1 = -ang_s + (2 * ang_s * (k + 1)) / 6
                draw_line3(p, cam, (mt * math.cos(t0), 0.012, mt * math.sin(t0)), (mt * math.cos(t1), 0.012, mt * math.sin(t1)), 0.022, QColor(248, 250, 252, 160))
        if self.hi > 2.0:
            for k in range(6):
                t0 = -ang_s + (2 * ang_s * k) / 6
                t1 = -ang_s + (2 * ang_s * (k + 1)) / 6
                draw_line3(p, cam, (self.hi * math.cos(t0), 0.014, self.hi * math.sin(t0)), (self.hi * math.cos(t1), 0.014, self.hi * math.sin(t1)), 0.026, QColor("#34d399"))

        draw_official_3d(p, cam, 0.4, -2.6)

        cur = self.cur
        if cur is None:
            return
        t = self.t
        d = cur["dist"]
        foul = cur["foul"]
        kit = QColor("#f59e0b") if cur["player"] else QColor.fromHsv(zlib.crc32(cur["team"].encode()) % 360, 170, 215)
        skin = TrackRaceWidget._skin(cur["name"])
        bib = (zlib.crc32(cur["name"].encode()) % 890) + 100

        wind_end, fly_end = 1.0, 2.05
        if not cur["animate"]:
            lx = 0.5 if foul else d
            if not foul:
                draw_poly(p, cam, [(lx - 0.18, 0.02, -0.18), (lx + 0.18, 0.02, -0.18), (lx + 0.18, 0.02, 0.18), (lx - 0.18, 0.02, 0.18)], QColor(40, 28, 12, 160))
                draw_line3(p, cam, (lx, 0.022, -1.2), (lx, 0.022, 1.2), 0.028, QColor("#fbbf24"))
            return

        if t < wind_end:
            u = t / wind_end
            x_m = _lerp(-1.55, -0.35, u * u)
            lean = _lerp(0.55, 0.12, u)
            hip_h = _lerp(0.76, 0.94, u)
            self._draw_actor(p, cam, x_m, hip_h, lean, kit, skin, cur["player"], bib, (-0.35, 0.6), (0.35, 0.4), (0.9, 0.4), (-0.4, 2.3), shot_in_hand=True)
        else:
            # rilascio e volo parabolico del peso metallico
            self._draw_actor(p, cam, -0.30, 0.96, 0.25, kit, skin, cur["player"], bib, (-0.25, 0.25), (0.35, 0.35), (-0.5, 0.4), (1.85, 0.15), shot_in_hand=False)
            s_ = _clamp((t - wind_end) / (fly_end - wind_end), 0.0, 1.0)
            bx = _lerp(0.15, d, s_)
            apex = 2.8 + 0.13 * d
            by = 2.05 * (1.0 - s_) + 4.0 * apex * s_ * (1.0 - s_)
            # ombra sul prato sotto il peso
            draw_textured_ground_quad(p, cam, [(bx - 0.25, 0.015, -0.25), (bx + 0.25, 0.015, -0.25), (bx + 0.25, 0.015, 0.25), (bx - 0.25, 0.015, 0.25)], get_soft_shadow(), "#0f172a")
            bc = cam.to_cam((bx, max(0.08, by), 0.0))
            if bc[2] >= NEAR:
                sx_, sy_ = cam.proj(bc)
                sr = max(3.0, 0.075 * cam.f / bc[2])
                sg = QRadialGradient(sx_ + sr * 0.3, sy_ - sr * 0.3, sr * 1.4)
                sg.setColorAt(0.0, QColor("#f8fafc"))
                sg.setColorAt(0.55, QColor("#64748b"))
                sg.setColorAt(1.0, QColor("#1e293b"))
                p.setBrush(QBrush(sg))
                p.drawEllipse(QPointF(sx_, sy_), sr, sr)
            if t >= fly_end:
                draw_line3(p, cam, (d, 0.022, -1.6), (d, 0.022, 1.6), 0.028, QColor("#ef4444" if foul else "#fbbf24"))

    # ---- HUD TV
    def _paint_hud(self, p: QPainter, w: int, h: int) -> None:
        font = QFont(self.font())
        font.setPointSize(9)
        p.setFont(font)

        # badge camera in alto a destra
        cam_pill = QRectF(w - 134, 10, 122, 22)
        p.setBrush(QColor(9, 15, 29, 190))
        p.setPen(QPen(QColor(51, 65, 85, 170), 1))
        p.drawRoundedRect(cam_pill, 4, 4)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#ef4444"))
        p.drawEllipse(QPointF(cam_pill.left() + 12, cam_pill.center().y()), 3.5, 3.5)
        bf = QFont(font)
        bf.setPointSize(8)
        bf.setBold(True)
        p.setFont(bf)
        p.setPen(QColor("#e2e8f0"))
        p.drawText(QRectF(cam_pill.left() + 20, cam_pill.top(), cam_pill.width() - 24, cam_pill.height()), Qt.AlignmentFlag.AlignVCenter, self._cam_label)

        cur = self.cur
        if cur is None:
            return
        # pillola atleta + prova in alto a sinistra
        card = QRectF(12, 10, 340, 26)
        p.setBrush(QColor(9, 15, 29, 215))
        p.setPen(QPen(QColor("#fbbf24" if cur["player"] else "#475569"), 1.2))
        p.drawRoundedRect(card, 5, 5)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#b45309" if cur["player"] else "#1e293b"))
        p.drawRoundedRect(QRectF(card.left() + 3, card.top() + 3, 64, 20), 3, 3)
        p.setPen(QColor("#fef3c7" if cur["player"] else "#cbd5e1"))
        p.drawText(QRectF(card.left() + 3, card.top() + 3, 64, 20), Qt.AlignmentFlag.AlignCenter, f"PROVA {cur['n']}/{cur['total']}")
        p.setFont(font)
        p.setPen(QColor("#fbbf24" if cur["player"] else "#f8fafc"))
        p.drawText(QRectF(card.left() + 74, card.top(), card.width() - 80, 26), Qt.AlignmentFlag.AlignVCenter, _short(f"{cur['name']} · {cur['team']}", 34))

        # risultato misurato a terra dopo atterraggio / lancio
        done_thresh = 1.98 if self.kind == "lj" else 2.05
        if (not cur["animate"]) or self.t >= done_thresh:
            txt = "NULLO" if cur["foul"] else f"{cur['dist']:.2f} m"
            col = "#ef4444" if cur["foul"] else "#10b981"
            res_box = QRectF(w - 134, h - 42, 122, 30)
            p.setBrush(QColor(9, 15, 29, 225))
            p.setPen(QPen(QColor(col), 1.8))
            p.drawRoundedRect(res_box, 5, 5)
            rf = QFont(font)
            rf.setPointSize(12)
            rf.setBold(True)
            p.setFont(rf)
            p.setPen(QColor(col))
            p.drawText(res_box, Qt.AlignmentFlag.AlignCenter, txt)

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        w, h = self.width(), self.height()
        cam = self._make_camera(w, h)

        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        x_min, x_max = (-24.0, 14.0) if self.kind == "lj" else (-8.0, 26.0)
        self._draw_stadium_backdrop(p, cam, w, h, x_min, x_max)
        p.setPen(Qt.PenStyle.NoPen)

        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if self.kind == "lj":
            self._paint_long_jump(p, cam)
        else:
            self._paint_shot_put(p, cam)

        vig = QRadialGradient(w * 0.5, h * 0.5, max(w, h) * 0.72)
        vig.setColorAt(0.75, QColor(0, 0, 0, 0))
        vig.setColorAt(1.0, QColor(0, 0, 0, 65))
        p.fillRect(0, 0, w, h, QBrush(vig))

        p.setPen(Qt.PenStyle.NoPen)
        self._paint_hud(p, w, h)
        p.end()
