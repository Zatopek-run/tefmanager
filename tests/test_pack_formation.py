"""Formazione del gruppo nelle gare con rientro alla corda (PIANOLAVORO G): riferimento Python di `models/pack_formation.py`. **Senza Qt.**

Garanzie: (1) fino alla linea di rientro ognuno sta esattamente nella propria corsia; (2) dopo, chi è davanti prende la corda e chi segue sta in fila;
(3) chi sorpassa passa all'esterno e **non spinge fuori** chi viene superato; (4) nessun salto laterale (velocità laterale limitata) e nessuna
compenetrazione; (5) è una funzione pura del tempo (si può riavvolgere); (6) un ritirato fermo lascia la corda e non blocca gli altri.
"""

from __future__ import annotations

import math
import unittest

from models.pack_formation import (
    BREAK_WINDOWS,
    GAP_AHEAD,
    GAP_BEHIND,
    LEAVE_SECONDS,
    MAX_SLOT,
    EXIT_MIN,
    EXIT_STEP,
    OUTER_LAT,
    SEP_LAT,
    SLOT_W,
    PackFormation,
    applies_to,
    assign_exit_lats,
    assign_slots,
    smoothstep,
)

LANE_W = 1.22
REACTION = 0.15


def lanes(n: int):
    return [i * LANE_W for i in range(n)]


def constant_speed(speeds, starts=None):
    """dist_fn: ognuno corre a velocità costante dopo la reazione (partenza allineata, o `starts` m più avanti)."""
    starts = starts or [0.0] * len(speeds)
    return lambda i, t: starts[i] + max(0.0, t - REACTION) * speeds[i]


def simulate(kind, speeds, seconds=60.0, dt=0.1, stops=None, starts=None):
    dist = constant_speed(speeds, starts)
    n = len(speeds)
    formation = PackFormation(kind, lanes(n), dist, stops)
    rows = []
    t = 0.0
    while t <= seconds:
        rows.append((t, [dist(i, t) for i in range(n)], formation.lateral_offsets(t)))
        t += dt
    return rows


class TestBasics(unittest.TestCase):
    def test_only_800_1500_and_4x400_have_a_break(self) -> None:
        self.assertTrue(applies_to("800m") and applies_to("1500m") and applies_to("4x400m"))
        self.assertFalse(any(applies_to(k) for k in ("100m", "400m", "4x100m")))
        self.assertEqual(PackFormation("400m", lanes(4), constant_speed([7] * 4)).lateral_offsets(20.0), lanes(4))

    def test_the_800m_break_is_the_end_of_the_first_bend(self) -> None:
        self.assertAlmostEqual(BREAK_WINDOWS["800m"][0], math.pi * 36.8, places=1)

    def test_the_4x400m_break_is_the_end_of_the_first_bend_of_the_second_leg(self) -> None:
        # 400 m di prima frazione in corsia sfalsata + la prima curva della seconda (come l'800m)
        self.assertAlmostEqual(BREAK_WINDOWS["4x400m"][0], 400.0 + BREAK_WINDOWS["800m"][0], places=6)
        self.assertAlmostEqual(BREAK_WINDOWS["4x400m"][1] - BREAK_WINDOWS["4x400m"][0], BREAK_WINDOWS["800m"][1] - BREAK_WINDOWS["800m"][0], places=6)

    def test_smoothstep(self) -> None:
        self.assertEqual((smoothstep(1, 3, 0), smoothstep(1, 3, 5), smoothstep(1, 3, 2)), (0.0, 1.0, 0.5))

    def test_slots_follow_the_current_row_then_position_and_gaps(self) -> None:
        # tre in fila ben distanziati: tutti sulla corda; due affiancati: la corsia interna prende la corda
        self.assertEqual(assign_slots([30, 20, 10], [0, 0, 0], [0, 1, 2], [True] * 3), [0, 0, 0])
        self.assertEqual(assign_slots([10, 10], [0, 0], [0, 1.22], [True, True]), [0, 1])
        self.assertEqual(assign_slots([10, 10], [0, 0], [1.22, 0], [True, True]), [1, 0])
        # isteresi: chi è già dentro tiene la corda anche se l'altro lo ha appena superato di poco
        self.assertEqual(assign_slots([10.5, 10.0], [1, 0], [1.22, 0], [True, True]), [1, 0])
        # ...ma l'altro rientra quando ha lasciato GAP_BEHIND metri
        self.assertEqual(assign_slots([13.1, 10.0], [1, 0], [1.22, 0], [True, True]), [0, 0])
        self.assertEqual(assign_slots([10, 5], [0, 0], [0, 1], [True, False]), [0, -1])  # un assente non occupa nessuna fila

    def test_a_closed_runner_widens_and_the_slot_count_is_capped(self) -> None:
        slots = assign_slots([10.0] * 10, [10.0] * 10, lanes(10), [True] * 10)
        self.assertEqual(max(slots), MAX_SLOT)
        self.assertEqual(slots[:MAX_SLOT + 1], list(range(MAX_SLOT + 1)))


class TestInTheLane(unittest.TestCase):
    def test_nobody_leaves_the_lane_before_the_break(self) -> None:
        a = BREAK_WINDOWS["800m"][0]
        for row in simulate("800m", [6.5, 6.6, 6.7, 6.4, 6.55, 6.45, 6.62, 6.3], seconds=30):
            t, dists, lat = row
            for i, d in enumerate(dists):
                if d <= a:
                    self.assertEqual(lat[i], lanes(8)[i], f"t={t:.1f} corridore {i} a {d:.1f} m")

    def test_the_4x400m_stays_in_lane_for_the_first_leg_and_the_first_bend_of_the_second(self) -> None:
        a = BREAK_WINDOWS["4x400m"][0]
        rows = simulate("4x400m", [6.5, 6.6, 6.7, 6.4, 6.55, 6.45, 6.62, 6.3], seconds=110)
        seen_after = False
        for t, dists, lat in rows:
            for i, d in enumerate(dists):
                if d <= a:
                    self.assertEqual(lat[i], lanes(8)[i], f"t={t:.1f} squadra {i} a {d:.1f} m")
                elif d > BREAK_WINDOWS["4x400m"][1] + 5:
                    seen_after = True
        self.assertTrue(seen_after)
        final = rows[-1][2]
        self.assertAlmostEqual(min(final), 0.0, places=6)  # dopo la linea di rientro qualcuno e' sulla corda

    def test_the_1500_converges_to_the_rail_from_the_start(self) -> None:
        rows = simulate("1500m", [6.4, 6.5, 6.6, 6.55], seconds=40)
        final = rows[-1][2]
        self.assertAlmostEqual(min(final), 0.0, places=6)  # qualcuno è sulla corda


class TestTheRail(unittest.TestCase):
    def test_in_file_everybody_is_on_the_rail(self) -> None:
        # distanziati di oltre GAP_BEHIND uno dall'altro: tutti in fila sulla corda, ognuno col suo spazio
        rows = simulate("800m", [6.6, 6.6, 6.6, 6.6], starts=[0, -5, -10, -15], seconds=40)
        self.assertTrue(all(abs(x) < 1e-6 for x in rows[-1][2]), rows[-1][2])

    def test_those_within_a_stride_never_share_a_row(self) -> None:
        rows = simulate("800m", [6.5] * 4, starts=[2.0, 1.0, 0.0, -1.0], seconds=40)  # gruppo compatto: servono più file
        lat = rows[-1][2]
        d = rows[-1][1]
        self.assertAlmostEqual(min(lat), 0.0, places=6)
        for i in range(4):
            for j in range(i + 1, 4):
                if abs(d[i] - d[j]) < GAP_AHEAD:
                    self.assertGreaterEqual(abs(lat[i] - lat[j]), 0.6)  # spalla a spalla (la distanza minima è piena solo sotto SEP_FULL)

    def test_laterals_stay_inside_the_track(self) -> None:
        for kind in ("800m", "1500m"):
            for _t, _d, lat in simulate(kind, [6.2 + 0.06 * i for i in range(8)], seconds=90):
                for x in lat:
                    self.assertGreaterEqual(x, -1e-9)
                    self.assertLessEqual(x, max(MAX_SLOT * SLOT_W, 7 * LANE_W) + 1.0)  # la spinta di distanza minima può portare un po' oltre la corsia 8 (la pista ne misura 9,76)


class TestOvertaking(unittest.TestCase):
    def setUp(self) -> None:
        # A (0) parte avanti e va piano, B (1) lo raggiunge e lo supera sul rettilineo opposto
        self.rows = simulate("800m", [6.0, 6.6], starts=[22.0, 0.0], seconds=60, dt=0.05)

    def pass_window(self):
        return [r for r in self.rows if -GAP_BEHIND - 1 < r[1][1] - r[1][0] < GAP_AHEAD + 1]

    def test_the_overtaker_goes_outside_and_comes_back_without_pushing_the_other(self) -> None:
        window = self.pass_window()
        self.assertTrue(window)
        self.assertGreater(max(r[2][1] for r in window), SLOT_W * 0.5, "chi sorpassa deve passare all'esterno")
        self.assertLess(max(r[2][0] for r in window), 0.25, "chi viene superato non va spinto fuori")
        final = self.rows[-1][2]
        self.assertAlmostEqual(final[1], 0.0, places=6)  # dopo il sorpasso rientra sulla corda
        self.assertAlmostEqual(final[0], 0.0, places=6)

    def test_the_overtaker_waits_for_clearance_before_cutting_in(self) -> None:
        for _t, d, lat in self.rows:
            ahead = d[1] - d[0]
            if 0.0 < ahead < GAP_BEHIND - 0.8:  # ancora vicino davanti all'altro: non è già sulla corda
                self.assertGreater(lat[1], 0.1, f"rientrato troppo presto a {ahead:.2f} m")


class TestSmoothAndPure(unittest.TestCase):
    SPEEDS = [6.0, 6.7, 6.2, 6.6, 6.1, 6.5, 6.3, 6.4]

    def test_no_lateral_jumps(self) -> None:
        rows = simulate("800m", self.SPEEDS, seconds=70, dt=0.05, starts=[8, 3, 0, 6, 2, 4, 1, 5])
        worst = 0.0
        for (t0, _d0, l0), (t1, _d1, l1) in zip(rows, rows[1:]):
            for a, b in zip(l0, l1):
                worst = max(worst, abs(b - a) / (t1 - t0))
        self.assertLess(worst, 3.0, f"velocità laterale massima {worst:.2f} m/s")

    def test_no_two_runners_interpenetrate(self) -> None:
        rows = simulate("800m", self.SPEEDS, seconds=70, dt=0.05, starts=[8, 3, 0, 6, 2, 4, 1, 5])
        worst = 99.0
        for _t, d, lat in rows:
            for i in range(8):
                for j in range(i + 1, 8):
                    worst = min(worst, math.hypot(d[i] - d[j], lat[i] - lat[j]))
        self.assertGreater(worst, 0.45, f"distanza minima fra due corridori {worst:.2f} m")

    def test_it_is_a_pure_function_of_time(self) -> None:
        dist = constant_speed(self.SPEEDS, [8, 3, 0, 6, 2, 4, 1, 5])
        times = (5.0, 12.5, 30.0, 47.2)
        f1 = PackFormation("1500m", lanes(8), dist)
        f2 = PackFormation("1500m", lanes(8), dist)  # un'altra istanza, interrogata in ordine inverso (come nel ralenti)
        forward = [f1.lateral_offsets(t) for t in times]
        backward = [f2.lateral_offsets(t) for t in reversed(times)][::-1]
        self.assertEqual(forward, backward)
        self.assertEqual(f1.lateral_offsets(30.0), f1.lateral_offsets(30.0))


class TestRandomFields(unittest.TestCase):
    """Campi casuali (seme fisso): le garanzie valgono per ogni configurazione, non solo per quelle scritte a mano."""

    def fields(self):
        import random

        rng = random.Random(20261121)
        for _ in range(24):
            n = rng.randint(3, 8)
            yield (
                rng.choice(["800m", "1500m"]),
                [rng.uniform(5.8, 6.9) for _ in range(n)],
                [rng.uniform(0.0, 12.0) for _ in range(n)],
            )

    def test_no_interpenetration_no_jumps_and_always_inside_the_track(self) -> None:
        for kind, speeds, starts in self.fields():
            rows = simulate(kind, speeds, seconds=80, dt=0.1, starts=starts)
            n = len(speeds)
            for (t0, _d0, l0), (t1, d1, l1) in zip(rows, rows[1:]):
                for i in range(n):
                    self.assertLess(abs(l1[i] - l0[i]) / (t1 - t0), 3.2, f"{kind} {speeds} corridore {i} t={t1:.1f}")
                    self.assertGreaterEqual(l1[i], -1e-9)
                    self.assertLessEqual(l1[i], max(MAX_SLOT * SLOT_W, (n - 1) * LANE_W) + 1.0)
                for i in range(n):
                    for j in range(i + 1, n):
                        self.assertGreater(math.hypot(d1[i] - d1[j], l1[i] - l1[j]), 0.35, f"{kind} {speeds} {starts} corridori {i},{j} t={t1:.1f}")

    def test_the_rail_is_always_taken_by_someone_after_the_break(self) -> None:
        for kind, speeds, starts in self.fields():
            rows = simulate(kind, speeds, seconds=80, dt=0.5, starts=starts)
            a_end = BREAK_WINDOWS[kind][1]
            for _t, d, lat in rows:
                if all(x > a_end + 20 for x in d):
                    self.assertAlmostEqual(min(lat), 0.0, places=3, msg=f"{kind} {speeds}")


class TestStopping(unittest.TestCase):
    def test_those_who_stop_get_different_rows_from_the_outside_in(self) -> None:
        lats = assign_exit_lats([30.0, None, 10.0, 20.0, 10.0])
        self.assertEqual(lats[2], OUTER_LAT)  # primo a fermarsi (a parità, l'indice minore)
        self.assertEqual(lats[4], OUTER_LAT - EXIT_STEP)
        self.assertEqual(lats[3], OUTER_LAT - 2 * EXIT_STEP)
        self.assertEqual(lats[0], OUTER_LAT - 3 * EXIT_STEP)
        self.assertEqual(lats[1], OUTER_LAT)  # chi non si ferma non ha una fila d'uscita (non usata)
        many = assign_exit_lats([float(i) for i in range(20)])
        self.assertTrue(all(x >= EXIT_MIN for x in many))

    def test_finishers_leave_the_rail_without_crossing_the_pack(self) -> None:
        """Il campo arriva, rallenta oltre il traguardo e l'ultimo attraversa quelli già fermi: nessun salto laterale e nessuna compenetrazione."""
        speeds = [6.9, 6.8, 6.7, 6.6, 6.5, 6.4, 6.3, 6.2]
        total = 800.0
        finish = [REACTION + (total - 3.0 * i) / v for i, v in enumerate(speeds)]  # tutti partono sulla linea; partenza diversa per non avere tempi uguali

        def dist(i: int, t: float) -> float:
            run = max(0.0, t - REACTION) * speeds[i]
            if run <= total:
                return run
            return total + 6.0 * (1.0 - math.exp(-(t - REACTION - total / speeds[i]) / 1.1)) * 1.1  # rallenta come dopo il traguardo

        stops = [REACTION + total / v for v in speeds]
        f = PackFormation("800m", lanes(8), dist, stops)
        prev = None
        worst_speed, worst_sep = 0.0, 99.0
        t = 100.0
        while t < max(stops) + 8.0:
            lat = f.lateral_offsets(t)
            d = [dist(i, t) for i in range(8)]
            if prev is not None:
                worst_speed = max(worst_speed, max(abs(a - b) for a, b in zip(lat, prev)) / 0.05)
            for i in range(8):
                for j in range(i + 1, 8):
                    worst_sep = min(worst_sep, math.hypot(d[i] - d[j], lat[i] - lat[j]))
            prev = lat
            t += 0.05
        self.assertLess(worst_speed, 3.2, f"velocità laterale massima {worst_speed:.2f} m/s")
        self.assertGreater(worst_sep, 0.45, f"distanza minima {worst_sep:.2f} m")


class TestWithdrawn(unittest.TestCase):
    def setUp(self) -> None:
        # il corridore 0 guida e si ferma a 20 s; gli altri due lo seguono a 4 e 8 m
        self.stop = 20.0

        def dist(i: int, t: float) -> float:
            if i == 0:
                return 6.0 * (min(t, self.stop) - REACTION) if t > REACTION else 0.0
            return max(0.0, t - REACTION) * 6.0 - [0, 4.0, 8.0][i]

        self.dist = dist
        self.f = PackFormation("800m", lanes(3), dist, [self.stop, None, None])

    def test_a_stopped_runner_leaves_the_rail_gradually(self) -> None:
        self.assertLess(self.f.lateral_offsets(19.0)[0], 0.01)  # prima dell'arresto è sulla corda
        mid = self.f.lateral_offsets(self.stop + LEAVE_SECONDS / 2)[0]
        self.assertTrue(0.0 < mid < OUTER_LAT)
        self.assertAlmostEqual(self.f.lateral_offsets(self.stop + LEAVE_SECONDS + 0.5)[0], OUTER_LAT, places=6)

    def test_he_does_not_block_those_who_arrive_afterwards(self) -> None:
        # a 34 s gli altri due hanno raggiunto e superato il punto dell'arresto: la corda è libera
        self.assertEqual(self.f.lateral_offsets(34.0)[1:], [0.0, 0.0])


if __name__ == "__main__":
    unittest.main()
