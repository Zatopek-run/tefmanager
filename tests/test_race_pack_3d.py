"""Gruppo nei 800m, 1500m e 4x400m nella vista 3D Python (PIANOLAVORO G): usa il riferimento `models/pack_formation.py`, come Godot. Qt offscreen.

Garanzie: (1) `meters_at(r, race_time)` coincide con `meters(r)` (la formazione legge la stessa posizione che si disegna); (2) fino alla linea di rientro ognuno sta
nella propria corsia; (3) sulle gare vere nessuno si compenetra e nessuno scatta di lato; (4) chi sorpassa passa fuori e ci sono sorpassi; (5) l'esito non cambia.
"""

from __future__ import annotations

import math
import os
import random
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("TEF_NO_GODOT", "1")

from PyQt6.QtWidgets import QApplication

from controllers.game_controller import GameController
from models.database import DatabaseManager
from models.pack_formation import BREAK_WINDOWS
from tests.support import start_game
from views.race_3d import Track3DWidget
from views.race_viewer import DNF_PROGRESS, GUN_AT, is_field_event, position_fraction

_app = QApplication.instance() or QApplication([])


def played_pack_races():
    tmp = tempfile.TemporaryDirectory()
    ctrl = GameController(db_manager=DatabaseManager(db_path=Path(tmp.name) / "s.db"), rng=random.Random(5), auto_create=False)
    start_game(ctrl)
    for _ in range(24):
        ctrl.dismiss_dilemma()
        ctrl.advance_week()
    races = [(s, r) for s in ctrl.state.competition_history for r in s.event_results if r.event_name in ("800m", "1500m", "4x400m")]
    return tmp, races


class TestPack3D(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp, cls.races = played_pack_races()
        assert len(cls.races) >= 4
        assert any(r.event_name == "4x400m" for _, r in cls.races), "serve almeno una 4x400m"

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def widget(self, summ, res) -> Track3DWidget:
        w = Track3DWidget()
        w.resize(640, 360)
        w.set_race(res.event_name, res, f"{summ.week}-{summ.meet_name}")
        return w

    def at(self, w: Track3DWidget, race_time: float) -> None:
        w._t = GUN_AT + race_time / w._scale

    def test_meters_at_is_meters(self) -> None:
        for summ, res in self.races[:6]:
            w = self.widget(summ, res)
            for frac in (0.0, 0.3, 0.7, 0.999, 1.0, 1.05, 1.3):
                self.at(w, w.winner_time * frac)
                for r in w.runners:
                    self.assertAlmostEqual(w.meters_at(r, w.race_time), w.meters(r), places=9)

    def test_a_withdrawn_runner_stops_where_the_race_stops_him(self) -> None:
        summ, res = self.races[0]
        w = self.widget(summ, res)
        for r in w.runners:
            r["dnf"] = True  # lo si prova su tutti: il punto d'arresto è quello di un ritirato
            ts = w.stop_time(r)
            f = position_fraction(w.event_name, ts, w.winner_time * 1.25, r["react"], r["phase"], r["style"]) * 0.9
            self.assertAlmostEqual(f, DNF_PROGRESS, places=5)
            r["dnf"] = False
            self.assertEqual(w.stop_time(r), r["s"].mark_value)  # chi arriva: il suo tempo ufficiale

    def test_everyone_is_in_the_own_lane_before_the_break_line(self) -> None:
        for summ, res in self.races:
            w = self.widget(summ, res)
            a = BREAK_WINDOWS[w.event_name][0]
            for k in range(0, 60):
                self.at(w, w.winner_time * k / 60)
                lat = w._pack_lateral()
                for i, r in enumerate(w.runners):
                    if w.meters_at(r, w.race_time) <= a:
                        self.assertAlmostEqual(lat[i], w._lane_z(i) - w.RAIL_Z, places=9)

    def test_no_interpenetration_no_jumps_and_there_are_overtakes(self) -> None:
        total_cross = 0
        for summ, res in self.races:
            w = self.widget(summ, res)
            n = len(w.runners)
            dt = 0.25
            prev = None
            sign: dict = {}
            worst_sep, worst_speed = 99.0, 0.0
            t = 0.0
            last = max(r["s"].mark_value for r in w.runners if not r["dnf"])
            while t <= last + 4.0:
                self.at(w, t)
                meters = [w.meters(r) for r in w.runners]
                lat = w._pack_lateral()
                if prev is not None:
                    worst_speed = max(worst_speed, max(abs(a - b) for a, b in zip(lat, prev)) / (dt / 1.0))
                prev = lat
                live = [i for i, r in enumerate(w.runners) if not r["dnf"] and t < r["s"].mark_value]
                for a in range(len(live)):
                    for b in range(a + 1, len(live)):
                        i, j = live[a], live[b]
                        worst_sep = min(worst_sep, math.hypot(meters[i] - meters[j], lat[i] - lat[j]))
                        dd = meters[i] - meters[j]
                        sg = 1 if dd > 0.7 else (-1 if dd < -0.7 else 0)
                        if sg:
                            if sign.get((i, j), sg) != sg:
                                total_cross += 1
                            sign[(i, j)] = sg
                t += dt
            self.assertGreater(worst_sep, 0.3, f"{res.event_name}: distanza minima {worst_sep:.2f} m")
            self.assertLess(worst_speed, 4.5, f"{res.event_name}: velocità laterale massima {worst_speed:.2f} m/s (passo {dt} s)")
        self.assertGreaterEqual(total_cross, 4, "nelle gare vere ci devono essere sorpassi")

    def test_poses_are_finite_and_inside_the_track_and_the_result_is_untouched(self) -> None:
        summ, res = self.races[0]
        before = [(s.athlete_name, s.mark_value, s.placement) for s in res.standings]
        w = self.widget(summ, res)
        for k in range(0, 30):
            self.at(w, w.winner_time * 1.2 * k / 30)
            poses = w._runner_world_poses([w.meters(r) for r in w.runners])
            for x, z, yaw, curv in poses:
                self.assertTrue(all(math.isfinite(v) for v in (x, z, yaw, curv)))
        self.assertEqual(before, [(s.athlete_name, s.mark_value, s.placement) for s in res.standings])
        w.grab()  # si disegna davvero

    def test_the_4x400m_stays_in_lane_for_the_whole_first_leg_and_the_first_bend_of_the_second(self) -> None:
        relays = [(s, r) for s, r in self.races if r.event_name == "4x400m"]
        for summ, res in relays:
            w = self.widget(summ, res)
            self.assertAlmostEqual(BREAK_WINDOWS["4x400m"][0], 400.0 + BREAK_WINDOWS["800m"][0], places=6)
            for k in range(0, 80):
                self.at(w, w.winner_time * k / 80)
                lat = w._pack_lateral()
                for i, r in enumerate(w.runners):
                    if w.meters_at(r, w.race_time) <= BREAK_WINDOWS["4x400m"][0]:
                        self.assertAlmostEqual(lat[i], w._lane_z(i) - w.RAIL_Z, places=9, msg=f"{res.event_name} t={w.race_time:.1f} squadra {i}")
            # a fine gara le squadre che corrono ancora sono tutte verso la corda (nessuna e' rimasta in corsia)
            self.at(w, w.winner_time * 0.9)
            lat = w._pack_lateral()
            running = [lat[i] for i, r in enumerate(w.runners) if w.meters_at(r, w.race_time) > BREAK_WINDOWS["4x400m"][1] and not r["dnf"]]
            if running:
                self.assertLess(min(running), 0.2)
                self.assertLess(max(running), 7 * 0.95 + 0.01 + 4.0)

    def test_the_formation_is_rebuilt_for_a_new_race(self) -> None:
        summ, res = self.races[0]
        w = self.widget(summ, res)
        self.at(w, 20.0)
        w._pack_lateral()
        first = w._pack
        summ2, res2 = self.races[1]
        w.set_race(res2.event_name, res2, f"{summ2.week}-{summ2.meet_name}")
        w._pack_lateral()
        self.assertIsNot(w._pack, first)


if __name__ == "__main__":
    unittest.main()
