"""Stile di passo per corridore (PIANOLAVORO G: «le gare di corsa sono piatte»), Qt offscreen.

Garanzie: (1) con stile 0 la curva è **identica a prima** (regressione); (2) con qualunque stile il via resta 0 e l'arrivo **esattamente** `mark_value`, e la
posizione non torna mai indietro; (3) lo stile è deterministico (stesso meeting e nome → stesso numero) e le staffette non ne hanno; (4) sulle gare vere ci sono
sorpassi in corsa e **l'esito non cambia** (stessi tempi, stessa classifica); (5) l'esportazione per Godot porta lo stesso stile.
"""

from __future__ import annotations

import math
import os
import random
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("TEF_NO_GODOT", "1")

from PyQt6.QtWidgets import QApplication

from controllers.game_controller import GameController
from models.database import DatabaseManager
from models.race_export import export_race
from tests.support import start_game
from views.race_viewer import (
    PACE_AMPLITUDE,
    TrackRaceWidget,
    _CURVE_STEPS,
    _g_table,
    curve_progress,
    is_field_event,
    pace_amplitude,
    pace_style,
    runner_style,
    position_fraction,
    warp_time,
)

_app = QApplication.instance() or QApplication([])
KINDS = ("100m", "400m", "800m", "1500m", "relay")


def legacy_progress(kind: str, u: float, phase: float = 0.0, amp: float = 0.006) -> float:
    """La curva di prima dello stile di passo, riscritta qui: lo stile 0 deve darne esattamente i valori."""
    u = max(0.0, min(1.0, u))
    table = _g_table(kind)
    pos = u * _CURVE_STEPS
    i = min(_CURVE_STEPS - 1, int(pos))
    g = table[i] + (table[i + 1] - table[i]) * (pos - i)
    return g + amp * math.sin(phase + 7.0 * u) * u * (1.0 - u)


class TestTheCurve(unittest.TestCase):
    def test_style_zero_is_exactly_the_old_curve(self) -> None:
        for kind in KINDS:
            for phase in (0.0, 1.3, 4.7):
                for k in range(0, 1001, 7):
                    u = k / 1000
                    self.assertEqual(curve_progress(kind, u, phase), legacy_progress(kind, u, phase))
                    self.assertEqual(curve_progress(kind, u, phase, style=0.0), legacy_progress(kind, u, phase))

    def test_start_and_finish_are_fixed_for_every_style(self) -> None:
        for kind in KINDS:
            for style in (-1.0, -0.5, 0.0, 0.37, 1.0):
                self.assertEqual(curve_progress(kind, 0.0, 2.0, style=style), 0.0)
                self.assertAlmostEqual(curve_progress(kind, 1.0, 3.0, style=style), 1.0, places=9)
                self.assertEqual(warp_time(kind, 0.0, style), 0.0)
                self.assertEqual(warp_time(kind, 1.0, style), 1.0 + style * pace_amplitude(kind) * math.sin(math.pi))  # sin(π)≈1e-16

    def test_every_style_is_monotone(self) -> None:
        for kind in KINDS:
            for style in (-1.0, -0.6, 0.6, 1.0):
                prev = -1.0
                for k in range(0, 2001):
                    v = curve_progress(kind, k / 2000, 0.0, 0.0, style)  # senza l'ondeggiamento di fase: la sola deformazione
                    self.assertGreaterEqual(v + 1e-12, prev, f"{kind} stile {style} u={k / 2000}")
                    prev = v

    def test_the_warp_is_monotone_by_construction(self) -> None:
        """u' = u + s·AMP·sin(πu) ha derivata 1 + s·AMP·π·cos(πu) ≥ 0 se |s|·AMP·π ≤ 1: vale per ogni gara con |s| ≤ 1."""
        for kind, amp in PACE_AMPLITUDE.items():
            self.assertLessEqual(amp * math.pi, 1.0, kind)

    def test_relays_have_no_style(self) -> None:
        self.assertEqual(pace_amplitude("relay"), 0.0)
        for k in range(0, 101, 5):
            self.assertEqual(curve_progress("relay", k / 100, 0.7, style=1.0), curve_progress("relay", k / 100, 0.7))

    def test_a_front_runner_leads_in_the_middle_and_a_kicker_trails(self) -> None:
        for kind in ("400m", "800m", "1500m"):
            mid_front = curve_progress(kind, 0.5, 0.0, 0.0, 1.0)
            mid_flat = curve_progress(kind, 0.5, 0.0, 0.0, 0.0)
            mid_kick = curve_progress(kind, 0.5, 0.0, 0.0, -1.0)
            self.assertGreater(mid_front, mid_flat)
            self.assertLess(mid_kick, mid_flat)
            # e a fine gara lo stile si inverte: chi è partito forte rallenta, chi ha aspettato va più forte
            late = lambda s: curve_progress(kind, 1.0, 0.0, 0.0, s) - curve_progress(kind, 0.97, 0.0, 0.0, s)
            self.assertLess(late(1.0), late(0.0))
            self.assertGreater(late(-1.0), late(0.0))


class TestThePaceStyle(unittest.TestCase):
    def test_it_is_deterministic_in_range_and_depends_on_the_name(self) -> None:
        a = pace_style("12-Meeting", "Mario Rossi")
        self.assertEqual(a, pace_style("12-Meeting", "Mario Rossi"))
        self.assertNotEqual(a, pace_style("12-Meeting", "Luigi Verdi"))
        self.assertNotEqual(a, pace_style("13-Meeting", "Mario Rossi"))
        values = [pace_style("m", f"Atleta {i}") for i in range(400)]
        self.assertTrue(all(-1.0 <= v <= 1.0 for v in values))
        self.assertLess(min(values), -0.8)
        self.assertGreater(max(values), 0.8)  # copre tutto l'intervallo
        self.assertLess(abs(sum(values) / len(values)), 0.15)  # e non è sbilanciato


def played_meetings(seeds=(3, 5, 7), weeks=16):
    out = []
    for seed in seeds:
        tmp = tempfile.TemporaryDirectory()
        ctrl = GameController(db_manager=DatabaseManager(db_path=Path(tmp.name) / "s.db"), rng=random.Random(seed), auto_create=False)
        start_game(ctrl)
        for _ in range(weeks):
            ctrl.dismiss_dilemma()
            ctrl.advance_week()
        out.append((tmp, ctrl.state.competition_history))
    return out


def track_races(history):
    for summ in history:
        for res in summ.event_results:
            if not is_field_event(res.event_name) and not res.event_name.startswith("4x"):
                yield summ, res


def crossings(w: TrackRaceWidget, dead: float = 0.7, steps: int = 240) -> int:
    """Sorpassi veri: coppie la cui differenza di posizione cambia segno con almeno `dead` metri da entrambe le parti."""
    rs = [r for r in w.runners if not r["dnf"]]
    pos = [[position_fraction(w.event_name, w.winner_time * k / steps, r["s"].mark_value, r["react"], r["phase"], r["style"]) * w.distance for r in rs] for k in range(steps + 1)]
    count = 0
    for a in range(len(rs)):
        for b in range(a + 1, len(rs)):
            last = 0
            for k in range(steps + 1):
                d = pos[k][a] - pos[k][b]
                sgn = 1 if d > dead else (-1 if d < -dead else 0)
                if sgn:
                    if last and sgn != last:
                        count += 1
                    last = sgn
    return count


class TestOnRealRaces(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.meetings = played_meetings()
        cls.races = [(s, r) for _tmp, h in cls.meetings for s, r in track_races(h)]
        assert len(cls.races) > 40

    @classmethod
    def tearDownClass(cls) -> None:
        for tmp, _h in cls.meetings:
            tmp.cleanup()

    def widget(self, summ, res) -> TrackRaceWidget:
        w = TrackRaceWidget()
        w.set_race(res.event_name, res, f"{summ.week}-{summ.meet_name}")
        return w

    def test_there_are_real_overtakes_in_the_races_of_the_game(self) -> None:
        by_event = {}
        for summ, res in self.races:
            by_event.setdefault(res.event_name, []).append(crossings(self.widget(summ, res)))
        for event in ("400m", "800m", "1500m"):
            self.assertTrue(by_event[event], event)
            share = sum(1 for c in by_event[event] if c) / len(by_event[event])
            self.assertGreaterEqual(share, 0.8, f"{event}: gare con almeno un sorpasso {share:.0%}")

    def test_without_style_the_same_races_are_flat(self) -> None:
        """Il confronto che dà senso alla modifica: stesse gare, stile azzerato → quasi nessun sorpasso."""
        import views.race_viewer as rv

        flat = dict(rv.PACE_AMPLITUDE)
        try:
            for k in rv.PACE_AMPLITUDE:
                rv.PACE_AMPLITUDE[k] = 0.0
            flat_counts = [crossings(self.widget(s, r)) for s, r in self.races if r.event_name == "800m"]
        finally:
            rv.PACE_AMPLITUDE.update(flat)
        styled = [crossings(self.widget(s, r)) for s, r in self.races if r.event_name == "800m"]
        self.assertGreater(sum(styled), 2 * sum(flat_counts))

    def test_the_result_is_untouched_everyone_finishes_exactly_at_the_official_time(self) -> None:
        for summ, res in self.races[:60]:
            before = [(s.athlete_name, s.mark_value, s.placement) for s in res.standings]
            w = self.widget(summ, res)
            for r in w.runners:
                if r["dnf"]:
                    continue
                mark = r["s"].mark_value
                self.assertAlmostEqual(position_fraction(w.event_name, mark, mark, r["react"], r["phase"], r["style"]), 1.0, places=9)
                self.assertLess(position_fraction(w.event_name, mark - 0.01, mark, r["react"], r["phase"], r["style"]), 1.0)
                self.assertEqual(position_fraction(w.event_name, 0.0, mark, r["react"], r["phase"], r["style"]), 0.0)
            self.assertEqual(before, [(s.athlete_name, s.mark_value, s.placement) for s in res.standings])

    def test_the_order_at_the_line_is_always_the_official_one(self) -> None:
        """Chi taglia il traguardo prima (tempo minore) è davanti agli altri nell'istante in cui li supera: l'ordine d'arrivo è quello ufficiale."""
        for summ, res in self.races[:60]:
            w = self.widget(summ, res)
            rs = sorted((r for r in w.runners if not r["dnf"]), key=lambda r: r["s"].placement)
            for a, b in zip(rs, rs[1:]):
                t = a["s"].mark_value  # il migliore ha appena tagliato: il successivo non può averlo già fatto
                pa = position_fraction(w.event_name, t, a["s"].mark_value, a["react"], a["phase"], a["style"])
                pb = position_fraction(w.event_name, t, b["s"].mark_value, b["react"], b["phase"], b["style"])
                self.assertAlmostEqual(pa, 1.0, places=9)
                self.assertLessEqual(pb, 1.0 + 1e-9)
                self.assertLessEqual(a["s"].mark_value, b["s"].mark_value)


class TestRunnerStyleFollowsThePlan(unittest.TestCase):
    """Q41b: il tuo atleta con un piano non neutro corre nello stile del piano; tutti gli altri restano casuali."""

    def standing(self, name: str, is_player: bool):
        from models.entities import EventStanding

        return EventStanding(athlete_name=name, team_name="Noi" if is_player else "Altri", is_player=is_player, mark_value=100.0, mark_display="1:40.00")

    def result(self, plan):
        from models.entities import EventResult

        return EventResult(
            event_name="1500m", player_athlete_name="Mario Rossi", placement=1, total_competitors=8, player_mark="3:40.00",
            prize_money=0, prestige_gained=0, plan_style=plan,
        )

    def test_without_a_plan_everybody_is_random_as_before(self) -> None:
        for is_player in (True, False):
            s = self.standing("Mario Rossi", is_player)
            self.assertEqual(runner_style(self.result(None), s, "4-Meet"), pace_style("4-Meet", "Mario Rossi"))

    def test_rivals_ignore_the_plan(self) -> None:
        rival = self.standing("Luigi Verdi", False)
        self.assertEqual(runner_style(self.result(0.8), rival, "4-Meet"), pace_style("4-Meet", "Luigi Verdi"))

    def test_the_player_follows_the_plan_with_a_little_randomness(self) -> None:
        from models.entities import PLAN_STYLE_JITTER

        s = self.standing("Mario Rossi", True)
        base = pace_style("4-Meet", "Mario Rossi")
        self.assertAlmostEqual(runner_style(self.result(0.5), s, "4-Meet"), 0.5 + PLAN_STYLE_JITTER * base)
        # i due estremi del piano restano distinti da qualunque scostamento casuale
        self.assertGreater(runner_style(self.result(0.8), s, "4-Meet"), runner_style(self.result(-0.7), s, "4-Meet"))

    def test_the_style_is_clamped_to_the_staging_range(self) -> None:
        s = self.standing("Mario Rossi", True)
        for plan in (1.0, -1.0):
            for seed in range(50):
                self.assertTrue(-1.0 <= runner_style(self.result(plan), s, f"{seed}-Meet") <= 1.0)

    def test_the_finish_stays_exact_with_the_plan_style(self) -> None:
        for plan in (-1.0, -0.4, 0.8, 1.0):
            self.assertAlmostEqual(curve_progress("1500m", 1.0, style=plan), 1.0, places=9)
            self.assertAlmostEqual(curve_progress("1500m", 0.0, style=plan), 0.0, places=9)


class TestExport(unittest.TestCase):
    def test_the_export_carries_the_same_style_and_upgrades_old_databases(self) -> None:
        tmp, history = played_meetings(seeds=(3,))[0]
        self.addCleanup(tmp.cleanup)
        summ, res = next(track_races(history))
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "race_results.db"
            race_id = export_race(summ, res, path)
            with closing(sqlite3.connect(str(path))) as conn:
                rows = conn.execute("SELECT athlete_name, pace_style FROM race_results WHERE race_id = ?", (race_id,)).fetchall()
            seed = f"{summ.week}-{summ.meet_name}"
            self.assertEqual(len(rows), len(res.standings))
            for name, style in rows:
                std = next(s for s in res.standings if s.athlete_name == name)
                self.assertAlmostEqual(style, runner_style(res, std, seed), places=4)  # stessa funzione delle viste PyQt
                self.assertTrue(-1.0 <= style <= 1.0)
            # un file di un'esportazione precedente (senza la colonna) riceve la colonna invece di far fallire l'inserimento
            old = Path(d) / "old.db"
            with closing(sqlite3.connect(str(old))) as conn:
                conn.executescript(
                    "CREATE TABLE races (race_id INTEGER PRIMARY KEY, event_name TEXT NOT NULL, meet_name TEXT NOT NULL, distance_m REAL NOT NULL DEFAULT 100, wind_ms REAL NOT NULL DEFAULT 0);"
                    "CREATE TABLE race_results (race_id INTEGER NOT NULL, lane INTEGER NOT NULL, athlete_name TEXT NOT NULL, team_name TEXT NOT NULL DEFAULT '', "
                    "gender TEXT NOT NULL DEFAULT 'M', is_player INTEGER NOT NULL DEFAULT 0, reaction_time REAL NOT NULL, final_time REAL NOT NULL, "
                    "status TEXT NOT NULL DEFAULT 'OK', bib INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (race_id, lane));"
                )
            export_race(summ, res, old)
            with closing(sqlite3.connect(str(old))) as conn:
                self.assertIn("pace_style", {r[1] for r in conn.execute("PRAGMA table_info(race_results)")})
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM race_results").fetchone()[0], len(res.standings))


if __name__ == "__main__":
    unittest.main()
