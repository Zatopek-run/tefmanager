"""Unit and integration tests for Track & Field Manager (v2 Vertical Slice & Career)."""

from __future__ import annotations

import copy
import os
import random
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("TEF_NO_GODOT", "1")  # i test non devono aprire finestre Godot

from PyQt6.QtWidgets import QApplication

from controllers.game_controller import GameController
from models.database import DatabaseManager
from models.entities import (
    CompetitionTier,
    GameState,
    PeriodizationPhase,
    RaceAttitude,
    Specialty,
    SeasonPhase,
    TrainingFocus,
    WeatherCondition,
)
from models.generator import generate_vertical_slice_roster
from models.simulation import advance_week, apply_weekly_training, weekly_finances


def _drop_columns_after(conn, version: int) -> None:
    """Turn a current save file back into the layout of an older schema version."""
    from models.database import MIGRATIONS

    for from_version, columns in MIGRATIONS.items():
        if from_version < version:
            continue
        for table, cols in columns.items():
            for col, _def in cols:
                conn.execute(f"ALTER TABLE {table} DROP COLUMN {col}")


class TestRaceViewer(unittest.TestCase):
    """Live race viewer: animation helpers and the dialog stepping through a meet."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_progress_and_attempts(self) -> None:
        from views.race_viewer import FIELD_ROUNDS, curve_progress, generate_attempts

        for kind in ("100m", "400m", "1500m", "relay"):
            for phase in (0.0, 1.3, 2.7, 4.1, 6.0):
                prev = -1.0
                for i in range(0, 1001):
                    v = curve_progress(kind, i / 1000, phase)
                    self.assertGreater(v, prev - 1e-12, (kind, phase, i))  # mai all'indietro
                    prev = v
            self.assertEqual(curve_progress(kind, 0.0, 2.0), 0.0)
            self.assertAlmostEqual(curve_progress(kind, 1.0, 3.0), 1.0, places=9)
        for seed in range(30):
            att = generate_attempts(7.25, random.Random(seed))
            self.assertEqual(len(att), FIELD_ROUNDS)
            self.assertIn(7.25, att)
            self.assertTrue(all(a is None or a <= 7.25 for a in att))

    def test_runners_cross_the_line_exactly_at_their_mark(self) -> None:
        """La messa in scena non cambia l'esito: tempo di arrivo = tempo ufficiale, stesso ordine."""
        from views.race_viewer import position_fraction, reaction_time, is_field_event

        with tempfile.TemporaryDirectory() as tmpdir:
            ctrl = GameController(db_manager=DatabaseManager(db_path=Path(tmpdir) / "rv2.db"), rng=random.Random(15))
            ctrl.state.week = 4
            summary = advance_week(ctrl.state, rng=random.Random(15)).competition_summary
            assert summary is not None
            checked = 0
            for res in summary.event_results:
                if is_field_event(res.event_name):
                    continue
                arrivals = []
                for s in res.standings:
                    r = reaction_time("seed", s.athlete_name)
                    self.assertTrue(0.12 <= r <= 0.22)
                    self.assertAlmostEqual(position_fraction(res.event_name, s.mark_value, s.mark_value, r), 1.0, places=9)
                    self.assertLess(position_fraction(res.event_name, s.mark_value - 0.01, s.mark_value, r), 1.0)
                    self.assertEqual(position_fraction(res.event_name, 0.0, s.mark_value, r), 0.0)
                    arrivals.append((s.mark_value, s.placement))
                    checked += 1
                self.assertEqual([p for _m, p in sorted(arrivals)], sorted(p for _m, p in arrivals))
            self.assertGreater(checked, 10)

    def test_start_sequence_and_skip_during_countdown(self) -> None:
        from views.race_viewer import RaceViewerDialog

        with tempfile.TemporaryDirectory() as tmpdir:
            ctrl = GameController(db_manager=DatabaseManager(db_path=Path(tmpdir) / "rv3.db"), rng=random.Random(15))
            ctrl.state.week = 4
            summary = advance_week(ctrl.state, rng=random.Random(15)).competition_summary
            assert summary is not None
            dlg = RaceViewerDialog(summary)
            self.assertEqual(dlg.track.start_phase, "AI VOSTRI POSTI")
            self.assertEqual(dlg.track.race_time, 0.0)
            dlg.track.advance(1.5)
            self.assertEqual(dlg.track.start_phase, "PRONTI")
            dlg.track.advance(1.0)
            self.assertEqual(dlg.track.start_phase, "VIA!")
            dlg.track.advance(2.0)
            self.assertGreater(dlg.track.race_time, 0.5)  # il cronometro parte dallo sparo
            dlg._cycle_speed()
            dlg._toggle_pause()
            dlg._toggle_pause()
            dlg._skip_race()  # anche in piena corsa
            self.assertTrue(dlg._race_done)
            dlg.close()
            # saltare durante il conto alla rovescia
            dlg2 = RaceViewerDialog(summary)
            dlg2._skip_race()
            self.assertTrue(dlg2._race_done)
            self.assertEqual(dlg2.track.race_clock, min(r.mark_value for r in summary.event_results[0].standings))
            dlg2.close()

    def test_field_event_animates_only_player_attempts(self) -> None:
        import copy

        from views.race_viewer import FIELD_ROUNDS, FieldEventWidget

        with tempfile.TemporaryDirectory() as tmpdir:
            ctrl = GameController(db_manager=DatabaseManager(db_path=Path(tmpdir) / "rv4.db"), rng=random.Random(15))
            ctrl.state.week = 8
            summary = advance_week(ctrl.state, rng=random.Random(15)).competition_summary
            assert summary is not None
            jump = next(r for r in summary.event_results if r.event_name == "Salto in Lungo")
            shot = copy.deepcopy(jump)
            shot.event_name = "Getto del Peso"
            for st in shot.standings:
                st.mark_value = round(st.mark_value * 2.2, 2)
                st.mark_display = f"{st.mark_value:.2f}m"
            for res in (jump, shot):
                widget = FieldEventWidget()
                done = []
                widget.finished.connect(lambda: done.append(True))
                widget.set_race(res.event_name, res, "seed")
                elapsed, animated = 0.0, set()
                while not done and elapsed < 120:
                    widget.advance(0.05)
                    elapsed += 0.05
                    cur = widget.scene.cur
                    if cur and cur["animate"]:
                        animated.add((cur["n"], cur["name"]))
                self.assertTrue(done, res.event_name)
                self.assertEqual(len(animated), FIELD_ROUNDS)  # solo le prove del club sono animate
                self.assertLess(elapsed, 45)  # niente gare da un minuto di attesa
                best = {widget.board.item(r, FIELD_ROUNDS + 1).text() for r in range(widget.board.rowCount())}
                self.assertTrue({s.mark_display for s in res.standings} <= best)
                widget.close()
            # saltare a metà non lascia il tabellone incompleto
            skipped = FieldEventWidget()
            skipped.set_race(jump.event_name, jump, "seed")
            skipped.advance(1.0)
            skipped.skip_to_end()
            self.assertEqual(skipped.board.item(0, FIELD_ROUNDS + 2).text()[-1], "°")

    def test_3d_clipping_and_camera(self) -> None:
        from views.race_3d import NEAR, Camera, clip_near, clip_segment_near

        cam = Camera((0.0, 2.0, 0.0), (10.0, 1.0, 0.0), 48.0, 800, 400)
        ahead = cam.proj(cam.to_cam((10.0, 1.0, 0.0)))
        self.assertAlmostEqual(ahead[0], 400.0, delta=1.0)  # al centro dello schermo
        # un poligono che attraversa il piano vicino non deve avere vertici dietro la camera
        poly = [cam.to_cam(q) for q in [(-20.0, 0.0, -5.0), (30.0, 0.0, -5.0), (30.0, 0.0, 5.0), (-20.0, 0.0, 5.0)]]
        clipped = clip_near(poly)
        self.assertGreaterEqual(len(clipped), 3)
        self.assertTrue(all(c[2] >= NEAR - 1e-9 for c in clipped))
        self.assertEqual(clip_near([cam.to_cam((-5.0, 0.0, 0.0)), cam.to_cam((-6.0, 1.0, 0.0)), cam.to_cam((-7.0, 0.0, 1.0))]), [])
        self.assertIsNone(clip_segment_near(cam.to_cam((-5.0, 0.0, 0.0)), cam.to_cam((-6.0, 0.0, 0.0))))
        seg = clip_segment_near(cam.to_cam((-5.0, 1.0, 0.0)), cam.to_cam((5.0, 1.0, 0.0)))
        assert seg is not None
        self.assertTrue(seg[0][2] >= NEAR - 1e-9 and seg[1][2] >= NEAR - 1e-9)

    def test_track_views_paint_in_every_state(self) -> None:
        """Il disegno non deve mai sollevare eccezioni: corse, staffette, ritirati, squalifiche."""
        import copy

        from PyQt6.QtGui import QImage

        from views.race_3d import Track3DWidget
        from views.race_viewer import TrackRaceWidget, is_field_event

        with tempfile.TemporaryDirectory() as tmpdir:
            ctrl = GameController(db_manager=DatabaseManager(db_path=Path(tmpdir) / "rv5.db"), rng=random.Random(15))
            ctrl.state.week = 4
            summary = advance_week(ctrl.state, rng=random.Random(15)).competition_summary
            assert summary is not None
            results = [r for r in summary.event_results if not is_field_event(r.event_name)]
            withdrawn = copy.deepcopy(results[0])
            withdrawn.withdrew_injured = True
            disqualified = copy.deepcopy(next(r for r in results if r.event_name.startswith("4x")))
            disqualified.disqualified = True
            results += [withdrawn, disqualified]
            painted = 0
            for cls in (Track3DWidget, TrackRaceWidget):
                for res in results:
                    widget = cls()
                    widget.resize(960, 520)
                    widget.set_race(res.event_name, res, "seed")
                    for step in (0.0, 1.0, 2.0, 1.0, 3.0, 6.0, 400.0):  # attesa, "pronti", via, corsa, arrivi
                        widget.advance(step)
                        image = QImage(960, 520, QImage.Format.Format_ARGB32)
                        widget.render(image)
                        painted += 1
                    widget.skip_to_end()
                    widget.render(QImage(960, 520, QImage.Format.Format_ARGB32))
                    widget.close()
            self.assertGreater(painted, 40)

    def test_view_toggle_keeps_race_position(self) -> None:
        from views.race_3d import Track3DWidget
        from views.race_viewer import RaceViewerDialog

        with tempfile.TemporaryDirectory() as tmpdir:
            ctrl = GameController(db_manager=DatabaseManager(db_path=Path(tmpdir) / "rv6.db"), rng=random.Random(15))
            ctrl.state.week = 4
            summary = advance_week(ctrl.state, rng=random.Random(15)).competition_summary
            assert summary is not None
            dlg = RaceViewerDialog(summary)
            self.assertIsInstance(dlg.track, Track3DWidget)  # 3D di default
            dlg.track.advance(5.0)
            t = dlg.track._t
            dlg._toggle_view()
            self.assertIs(dlg.track, dlg.track2d)
            self.assertAlmostEqual(dlg.track._t, t)
            self.assertIs(dlg.stack.currentWidget(), dlg.track2d)
            dlg._toggle_view()
            self.assertIs(dlg.track, dlg.track3d)
            dlg._skip_race()
            self.assertTrue(dlg._race_done)
            self.assertEqual(dlg.track.race_clock, min(r.mark_value for r in summary.event_results[0].standings))
            dlg.close()

    def test_dialog_plays_every_event(self) -> None:
        from views.race_viewer import RaceViewerDialog

        with tempfile.TemporaryDirectory() as tmpdir:
            ctrl = GameController(db_manager=DatabaseManager(db_path=Path(tmpdir) / "rv.db"), rng=random.Random(15))
            ctrl.state.week = 4
            rep = advance_week(ctrl.state, rng=random.Random(15))
            summary = rep.competition_summary
            assert summary is not None
            dlg = RaceViewerDialog(summary)
            seen = 0
            while True:
                seen += 1
                dlg._skip_race()
                self.assertTrue(dlg._race_done)
                self.assertTrue(dlg.podium.text().startswith("1°"))
                if dlg._index >= len(summary.event_results) - 1:
                    break
                dlg._next()
            self.assertEqual(seen, len(summary.event_results))
            dlg.close()


class TestBodyBuild(unittest.TestCase):
    """Height and weight change race scores according to the event."""

    def _athlete(self, specialty, height, weight, gender: str = "M"):
        from models.generator import generate_athlete

        a = generate_athlete(specialty=specialty, rng=random.Random(5), gender=gender)
        a.height_cm, a.weight_kg = height, weight
        return a

    def test_build_suits_the_event(self) -> None:
        from models.entities import EVENTS, Specialty
        from models.simulation import BODY_MOD_MAX, BODY_MOD_MIN, body_fit_score, body_modifier

        heavy_thrower = self._athlete(Specialty.THROWS, 192, 105)
        small_thrower = self._athlete(Specialty.THROWS, 168, 66)
        self.assertGreater(body_modifier(heavy_thrower, "Getto del Peso"), 0.8)
        self.assertLess(body_modifier(small_thrower, "Getto del Peso"), -2.0)
        self.assertGreater(body_fit_score(heavy_thrower), body_fit_score(small_thrower))

        lean = self._athlete(Specialty.MIDDLE_DISTANCE, 176, 63)
        bulky = self._athlete(Specialty.MIDDLE_DISTANCE, 176, 90)
        self.assertGreater(body_modifier(lean, "1500m"), body_modifier(bulky, "1500m"))

        for a in (heavy_thrower, small_thrower, lean, bulky):
            for ev in EVENTS:
                self.assertTrue(BODY_MOD_MIN <= body_modifier(a, ev) <= BODY_MOD_MAX)

    def test_build_moves_expected_score_and_old_saves_are_neutral(self) -> None:
        from models.entities import EVENTS, Specialty
        from models.simulation import expected_event_score

        ev = EVENTS["Getto del Peso"]
        good = self._athlete(Specialty.THROWS, 192, 105)
        bad = self._athlete(Specialty.THROWS, 168, 66)
        neutral = self._athlete(Specialty.THROWS, 0, 0)
        for a in (bad, neutral):
            for attr in ("strength", "technique", "speed", "stamina", "form", "fatigue"):
                setattr(a, attr, getattr(good, attr))
        self.assertGreater(expected_event_score(good, ev), expected_event_score(neutral, ev))
        self.assertGreater(expected_event_score(neutral, ev), expected_event_score(bad, ev))


class TestVerticalSliceAndMechanics(unittest.TestCase):
    """Tests vertical slice, periodization, wind records, staff, dilemmas, and SQLite v2."""

    def test_vertical_slice_initial_setup(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db = DatabaseManager(db_path=Path(tmpdir) / "vs.db")
            ctrl = GameController(db_manager=db, rng=random.Random(42))
            self.assertEqual(ctrl.state.game_mode, "vertical_slice")
            self.assertEqual(ctrl.state.season_phase, SeasonPhase.OUTDOOR)
            self.assertEqual(len(ctrl.state.athletes), 10)
            self.assertEqual(ctrl.state.active_events, ["100m", "Salto in Lungo", "1500m"])
            self.assertEqual(len(ctrl.state.staff), 3)  # physio, doctor, mental coach
            self.assertEqual(len(ctrl.state.coaches), 3)  # one per specialty in the roster
            self.assertEqual(len(ctrl.state.objectives), 3)

    def test_periodization_tapering_and_recovery(self) -> None:
        roster = generate_vertical_slice_roster(rng=random.Random(10))
        sprinter = roster[0]
        sprinter.fatigue = 75
        sprinter.training_focus = TrainingFocus.REST
        sprinter.periodization = PeriodizationPhase.SCARICO
        apply_weekly_training(sprinter, rng=random.Random(10))
        self.assertLess(sprinter.fatigue, 55)

    def test_two_meets_and_sqlite_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db = DatabaseManager(db_path=Path(tmpdir) / "roundtrip.db")
            ctrl = GameController(db_manager=db, rng=random.Random(99))

            # Advance through Week 8 (completing Meet #1 on Week 4 and Meet #2 on Week 8)
            for _ in range(8):
                ctrl.advance_week()
                if ctrl.state.pending_dilemma is not None:
                    ctrl.resolve_dilemma(accepted=False)

            self.assertEqual(ctrl.state.week, 9)
            self.assertTrue(ctrl.state.is_vertical_slice_complete)
            self.assertEqual(len(ctrl.state.competition_history), 2)

            loaded = db.load_game()
            self.assertIsNotNone(loaded)
            assert loaded is not None
            self.assertEqual(loaded.week, 9)
            self.assertEqual(len(loaded.athletes), 10)
            self.assertEqual(len(loaded.competition_history), 2)
            self.assertEqual(loaded.reputation, ctrl.state.reputation)

    def test_wind_illegal_does_not_set_club_record(self) -> None:
        from models import simulation as sim

        with tempfile.TemporaryDirectory() as tmpdir:
            db = DatabaseManager(db_path=Path(tmpdir) / "wind.db")
            ctrl = GameController(db_manager=db, rng=random.Random(55))
            ctrl.state.week = 4

            orig_roll = sim._roll_meet_wind
            sim._roll_meet_wind = lambda _w, _s, _r: 2.8  # Force illegal tailwind > 2.0 m/s
            try:
                summary = sim.simulate_competition(ctrl.state, rng=random.Random(55))
            finally:
                sim._roll_meet_wind = orig_roll

            sprint_res = next(er for er in summary.event_results if er.event_name == "100m")
            self.assertTrue(sprint_res.wind_illegal)
            self.assertFalse(sprint_res.is_club_record)
            self.assertNotIn("100m", ctrl.state.club_records)

    def test_staff_track_and_career_season_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db = DatabaseManager(db_path=Path(tmpdir) / "career.db")
            ctrl = GameController(db_manager=db, rng=random.Random(77))
            ctrl.start_new_game(team_name="CUS Test", game_mode="career")
            self.assertEqual(len(ctrl.state.athletes), 16)
            self.assertEqual(len(ctrl.state.active_events), 5)

            ctrl.toggle_staff(4)  # Hire Physio
            self.assertTrue(any(s.id == 4 and s.hired for s in ctrl.state.staff))

            old_cond = ctrl.state.track_condition
            self.assertTrue(ctrl.maintain_track())
            self.assertGreater(ctrl.state.track_condition, old_cond)

            # Advance 12 weeks -> transitions Outdoor -> Cross
            for _ in range(12):
                advance_week(ctrl.state, rng=random.Random(77))
            self.assertEqual(ctrl.state.season_phase, SeasonPhase.CROSS)


class TestMaxithlonInspiredMechanics(unittest.TestCase):
    """Youth academy, scouting points, race attitude, home gate, club league, debt, fidelity."""

    def _ctrl(self, tmpdir: str, seed: int = 1, mode: str = "vertical_slice") -> GameController:
        db = DatabaseManager(db_path=Path(tmpdir) / f"m{seed}.db")
        ctrl = GameController(db_manager=db, rng=random.Random(seed))
        if mode != "vertical_slice":
            ctrl.start_new_game(team_name="CUS Test", game_mode=mode)
        return ctrl

    def test_scouting_points_and_escalating_fees(self) -> None:
        from controllers.game_controller import scouting_search_cost

        self.assertEqual(scouting_search_cost(0, 0), (2, 150))
        self.assertEqual(scouting_search_cost(3, 2), (4, 1850))  # 7 pts total (2200) - 3 pts (350)
        with tempfile.TemporaryDirectory() as tmpdir:
            ctrl = self._ctrl(tmpdir)
            budget = ctrl.state.budget
            kids = ctrl.run_youth_scouting(specialty=Specialty.JUMPS, high_potential=True)
            self.assertTrue(1 <= len(kids) <= 4)
            for k in kids:
                self.assertTrue(14 <= k.age <= 17)
                self.assertEqual(k.specialty, Specialty.JUMPS)
                self.assertGreaterEqual(k.potential, 85)
            self.assertEqual(ctrl.state.scouting_points_left, 4)
            self.assertEqual(ctrl.state.budget, budget - 600)
            ctrl.run_youth_scouting(specialty=Specialty.JUMPS, high_potential=True)
            self.assertEqual(ctrl.state.scouting_points_left, 0)
            self.assertEqual(ctrl.run_youth_scouting(), [])  # out of points
            ctrl.advance_week()
            self.assertEqual(ctrl.state.scouting_points_left, 8)
            self.assertEqual(ctrl.scouting_results, [])  # unsigned kids leave

    def test_youth_squad_rules(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ctrl = self._ctrl(tmpdir, seed=4)
            kids = []
            while not kids:
                kids = ctrl.run_youth_scouting()
            kid = kids[0]
            self.assertTrue(ctrl.sign_youth(kid))
            self.assertIn(kid, ctrl.state.youth_squad)
            self.assertEqual(kid.weekly_wage, 0)
            # Never selected for meets
            ctrl.auto_fill_lineup()
            self.assertNotIn(kid.id, ctrl.state.event_lineup.values())
            # Trains faster than an identical main-squad athlete
            twin = copy.deepcopy(kid)
            twin.in_youth_squad = False
            for a in (kid, twin):
                a.potential, a.speed, a.stamina, a.strength, a.technique = 95, 40, 40, 40, 40
                a.training_focus = TrainingFocus.TECHNIQUE
                a.age = 16
            for seed in range(40):
                for a in (kid, twin):
                    a.fatigue = 0
                    apply_weekly_training(a, rng=random.Random(seed))
            self.assertGreater(kid.technique, twin.technique)
            # Promotion: joins main squad and gets paid
            self.assertTrue(ctrl.promote_youth(kid.id))
            self.assertFalse(kid.in_youth_squad)
            self.assertGreater(kid.weekly_wage, 0)

    def test_auto_promotion_at_18(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ctrl = self._ctrl(tmpdir, seed=5)
            kids = []
            while not kids:
                kids = ctrl.run_youth_scouting()
            kid = kids[0]
            ctrl.sign_youth(kid)
            kid.age = 18
            ctrl.advance_week()
            self.assertFalse(kid.in_youth_squad)

    def test_race_attitude_tradeoffs(self) -> None:
        from models import simulation as sim

        means = {}
        fatigue = {}
        for attitude in (RaceAttitude.PRUDENTE, RaceAttitude.AGGRESSIVO):
            marks, fat = [], []
            for seed in range(60):
                with tempfile.TemporaryDirectory() as tmpdir:
                    ctrl = self._ctrl(tmpdir, seed=7)
                    ctrl.state.week = 4
                    for ev in ctrl.state.active_events:
                        ctrl.state.event_attitude[ev] = attitude.value
                    sprinter_id = ctrl.state.event_lineup["100m"]
                    sprinter = next(a for a in ctrl.state.athletes if a.id == sprinter_id)
                    sprinter.fatigue = 20
                    summary = sim.simulate_competition(ctrl.state, rng=random.Random(seed))
                    res = next(er for er in summary.event_results if er.event_name == "100m")
                    if not res.withdrew_injured:
                        marks.append(next(s.mark_value for s in res.standings if s.is_player))
                        fat.append(sprinter.fatigue)
            means[attitude] = sum(marks) / len(marks)
            fatigue[attitude] = sum(fat) / len(fat)
        self.assertLess(means[RaceAttitude.AGGRESSIVO], means[RaceAttitude.PRUDENTE])  # faster
        self.assertGreater(fatigue[RaceAttitude.AGGRESSIVO], fatigue[RaceAttitude.PRUDENTE])

    def test_withdrawal_is_last_and_scores_nothing(self) -> None:
        from models import simulation as sim

        with tempfile.TemporaryDirectory() as tmpdir:
            ctrl = self._ctrl(tmpdir, seed=8)
            ctrl.state.week = 4
            for a in ctrl.state.athletes:
                a.fatigue = 100  # near-certain in-race injury
            ctrl.state.event_attitude = {ev: "Aggressivo" for ev in ctrl.state.active_events}
            summary = None
            for seed in range(20):
                summary = sim.simulate_competition(ctrl.state, rng=random.Random(seed))
                if any(er.withdrew_injured for er in summary.event_results):
                    break
                for a in ctrl.state.athletes:
                    a.injured_weeks, a.fatigue = 0, 100
            assert summary is not None
            dnf = next(er for er in summary.event_results if er.withdrew_injured)
            self.assertEqual(dnf.placement, dnf.total_competitors)
            self.assertEqual(dnf.prize_money, 0)
            self.assertEqual(dnf.player_mark, "Ritirato")
            athlete = next(a for a in ctrl.state.athletes if a.name == dnf.player_athlete_name)
            self.assertTrue(athlete.is_injured)

    def test_home_meet_gate_and_away_travel(self) -> None:
        from models import simulation as sim

        with tempfile.TemporaryDirectory() as tmpdir:
            ctrl = self._ctrl(tmpdir, seed=9)
            ctrl.state.week = 4  # meet #1: home
            self.assertTrue(ctrl.state.next_meet_is_home)
            home = sim.simulate_competition(ctrl.state, rng=random.Random(1))
            self.assertTrue(home.is_home)
            self.assertEqual(home.travel_cost, 0)
            self.assertGreater(home.ticket_income, 0)
            self.assertLessEqual(home.spectators, ctrl.state.stand_seats)
            ctrl.state.week = 8  # meet #2: away
            away = sim.simulate_competition(ctrl.state, rng=random.Random(1))
            self.assertFalse(away.is_home)
            self.assertGreater(away.travel_cost, 0)
            self.assertEqual(away.ticket_income, 0)

    def test_club_league_points(self) -> None:
        from models import simulation as sim

        with tempfile.TemporaryDirectory() as tmpdir:
            ctrl = self._ctrl(tmpdir, seed=10)
            ctrl.state.week = 4
            ctrl.state.prestige = -1000  # keep the same category for this test
            ctrl.state.event_lineup["1500m"] = None  # empty slot: rivals still score
            summary = sim.simulate_competition(ctrl.state, rng=random.Random(2))
            self.assertEqual(len(summary.team_standings), 8)
            # 3 M events + 3 F events + 4x100m M + 4x100m F, each worth 8+7+...+1 = 36 points,
            # minus the 8th-place point nobody takes in the empty 1500m slot and each withdrawal/DQ
            dropped = sum(1 for er in summary.event_results if er.withdrew_injured or er.disqualified)
            self.assertEqual(sum(p for _t, p in summary.team_standings), 8 * 36 - 1 - dropped)
            self.assertEqual(dict(summary.team_standings), ctrl.state.league_table)
            self.assertGreater(summary.team_placement, 0)

    def test_facilities_gym_and_stands(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ctrl = self._ctrl(tmpdir, seed=11)
            budget = ctrl.state.budget
            self.assertTrue(ctrl.upgrade_gym())
            self.assertEqual(ctrl.state.gym_level, 1)
            self.assertEqual(ctrl.state.budget, budget - 2500)
            self.assertTrue(ctrl.expand_stands())
            self.assertEqual(ctrl.state.stand_seats, 1000)
            fin = weekly_finances(ctrl.state)
            self.assertEqual(fin["gym_upkeep"], 40)

    def test_debt_interest_and_bankruptcy(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ctrl = self._ctrl(tmpdir, seed=12)
            ctrl.state.week = 2
            ctrl.state.budget = -10000
            ctrl.advance_week()
            self.assertTrue(any(t.category == "Interessi" for t in ctrl.state.transactions))
            self.assertFalse(ctrl.state.bankrupt)
            ctrl.state.budget = -30000
            ctrl.advance_week()
            self.assertTrue(ctrl.state.bankrupt)
            week = ctrl.state.week
            self.assertIsNone(ctrl.advance_week())  # game over: no more weeks
            self.assertEqual(ctrl.state.week, week)

    def test_fidelity_and_individual_sponsors(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ctrl = self._ctrl(tmpdir, seed=13)
            base = weekly_finances(ctrl.state)
            star = ctrl.state.main_squad[0]
            star.age, star.fans = 25, 400
            self.assertEqual(weekly_finances(ctrl.state)["individual_sponsors"], 100)
            ctrl.release_athlete(ctrl.state.main_squad[-1].id)
            self.assertEqual(ctrl.state.fidelity, 92)
            self.assertLess(weekly_finances(ctrl.state)["sponsor"], base["sponsor"])

    def test_veterans_decline(self) -> None:
        roster = generate_vertical_slice_roster(rng=random.Random(3))
        vet = roster[0]
        vet.age = 36
        vet.potential = vet.speed  # no headroom to grow back
        vet.training_focus = TrainingFocus.REST
        start = vet.speed + vet.stamina + vet.strength
        for seed in range(30):
            apply_weekly_training(vet, rng=random.Random(seed))
        self.assertLess(vet.speed + vet.stamina + vet.strength, start)

    def test_sqlite_v3_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ctrl = self._ctrl(tmpdir, seed=14)
            kids = []
            while not kids:
                kids = ctrl.run_youth_scouting()
            ctrl.sign_youth(kids[0])
            ctrl.state.event_attitude["100m"] = "Aggressivo"
            ctrl.upgrade_gym()
            for _ in range(4):
                ctrl.advance_week()
                if ctrl.state.pending_dilemma is not None:
                    ctrl.resolve_dilemma(accepted=False)
            loaded = ctrl.db.load_game()
            assert loaded is not None
            self.assertEqual(len(loaded.youth_squad), len(ctrl.state.youth_squad))
            self.assertEqual(loaded.event_attitude, ctrl.state.event_attitude)
            self.assertEqual(loaded.gym_level, 1)
            self.assertEqual(loaded.league_table, ctrl.state.league_table)
            self.assertEqual(loaded.fidelity, ctrl.state.fidelity)
            comp = loaded.competition_history[0]
            orig = ctrl.state.competition_history[0]
            self.assertEqual(comp.team_standings, orig.team_standings)
            self.assertEqual(comp.ticket_income, orig.ticket_income)
            self.assertEqual(comp.event_results[0].attitude, orig.event_results[0].attitude)
            self.assertEqual(
                [a.fans for a in loaded.athletes], [a.fans for a in ctrl.state.athletes]
            )

    def test_v2_save_is_migrated_not_wiped(self) -> None:
        import sqlite3

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "old.db"
            ctrl = GameController(db_manager=DatabaseManager(db_path=path), rng=random.Random(15))
            ctrl.state.team_name = "Vecchio Salvataggio"
            ctrl.db.save_game(ctrl.state)
            # Downgrade the file to the v2 layout (drop v3 columns, reset version)
            conn = sqlite3.connect(path)
            try:
                _drop_columns_after(conn, 2)
                conn.execute("DROP TABLE coaches")
                # v2 saves had coaches as staff "roles"
                conn.execute(
                    "INSERT INTO staff (id, name, role, skill, weekly_cost, hired, description) "
                    "VALUES (1, 'Coach Andrea Valeri', 'Coach Velocità', 3, 260, 1, '')"
                )
                conn.execute("PRAGMA user_version = 2")
                conn.commit()
            finally:
                conn.close()
            loaded = DatabaseManager(db_path=path).load_game()
            assert loaded is not None
            self.assertEqual(loaded.team_name, "Vecchio Salvataggio")
            self.assertEqual(len(loaded.athletes), 10)
            self.assertEqual(loaded.stand_seats, 500)
            self.assertEqual(loaded.youth_squad, [])
            # athletes of old saves get a stable body profile and the default nationality
            self.assertTrue(all(150 <= a.height_cm <= 205 and a.weight_kg > 0 for a in loaded.athletes))
            self.assertTrue(all(a.nationality == "Italia" for a in loaded.athletes))
            again = DatabaseManager(db_path=path).load_game()
            assert again is not None
            self.assertEqual([a.height_cm for a in again.athletes], [a.height_cm for a in loaded.athletes])
            # Opening it through the controller turns the old coach role into a real coach
            ctrl2 = GameController(db_manager=DatabaseManager(db_path=path), rng=random.Random(1))
            self.assertEqual([c.name for c in ctrl2.state.coaches], ["Andrea Valeri"])
            self.assertEqual(ctrl2.state.coaches[0].skills["speed"], 81)  # 3-star -> level 3
            self.assertFalse(any(st.role.value.startswith("Coach") for st in ctrl2.state.staff))
            sprinters = [a for a in ctrl2.state.athletes if a.specialty == Specialty.SPRINTS]
            self.assertTrue(all(ctrl2.state.coach_of(a) is not None for a in sprinters))
            self.assertIn("4x100m", ctrl2.state.relays)


class TestCoachesAndRelays(unittest.TestCase):
    """Coaches with their own skills & workload; 4x100m / 4x400m relays with harmony."""

    def _ctrl(self, tmpdir: str, seed: int = 1, mode: str = "vertical_slice") -> GameController:
        db = DatabaseManager(db_path=Path(tmpdir) / f"c{seed}.db")
        ctrl = GameController(db_manager=db, rng=random.Random(seed))
        if mode != "vertical_slice":
            ctrl.start_new_game(team_name="CUS Test", game_mode=mode)
        return ctrl

    @staticmethod
    def _technique_after(coach, load: int = 1, weeks: int = 40) -> int:
        a = generate_vertical_slice_roster(rng=random.Random(3))[0]
        a.potential, a.technique, a.age = 98, 40, 22
        a.training_focus = TrainingFocus.TECHNIQUE
        for seed in range(weeks):
            a.fatigue = 0
            apply_weekly_training(a, rng=random.Random(seed), coach=coach, coach_load=load)
        return a.technique

    def test_coach_skill_and_workload_drive_growth(self) -> None:
        from models.generator import generate_coach

        great = generate_coach(Specialty.SPRINTS, "technique", None, tier=5, rng=random.Random(1))
        weak = generate_coach(Specialty.SPRINTS, "speed", None, tier=5, rng=random.Random(1))
        wrong = generate_coach(Specialty.THROWS, "technique", None, tier=5, rng=random.Random(1))
        with_great = self._technique_after(great)
        self.assertGreater(with_great, self._technique_after(weak))  # skill in the trained quality
        self.assertGreater(self._technique_after(weak), self._technique_after(None))
        self.assertEqual(self._technique_after(wrong), self._technique_after(None))  # other specialty
        self.assertGreater(with_great, self._technique_after(great, load=12))  # overloaded coach

    def test_hire_rules_and_auto_assignment(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ctrl = self._ctrl(tmpdir, seed=2)
            s = ctrl.state
            sprinter = next(a for a in s.athletes if a.specialty == Specialty.SPRINTS)
            ctrl.fire_coach(s.coach_of(sprinter).id)
            self.assertIsNone(s.coach_of(sprinter))
            budget = s.budget
            self.assertTrue(ctrl.hire_coach(Specialty.SPRINTS, "speed", "technique", tier=2))
            self.assertEqual(s.budget, budget - 3000)
            new = s.coaches[-1]
            self.assertEqual((new.skills["speed"], new.skills["technique"], new.skills["stamina"]), (74, 64, 25))
            self.assertEqual(s.coach_of(sprinter), new)  # uncoached sprinters picked up
            # one hire per week
            self.assertFalse(ctrl.hire_coach(Specialty.JUMPS, "technique", None, tier=1))
            # youth coaches can't follow main-squad athletes; specialists only their discipline
            jumper = next(a for a in s.athletes if a.specialty == Specialty.JUMPS)
            self.assertFalse(ctrl.assign_coach(jumper.id, new.id))
            ctrl.advance_week()
            self.assertTrue(ctrl.hire_coach(None, "speed", "stamina", tier=1))
            self.assertFalse(ctrl.assign_coach(jumper.id, s.coaches[-1].id))
            self.assertIn("Allenatori", {t.category for t in s.transactions})

    def test_promoted_youth_changes_coach(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ctrl = self._ctrl(tmpdir, seed=3)
            ctrl.hire_coach(None, "speed", "technique", tier=1)
            youth_coach = ctrl.state.coaches[-1]
            kids = []
            while not kids:
                kids = ctrl.run_youth_scouting(specialty=Specialty.SPRINTS)
            kid = kids[0]
            ctrl.sign_youth(kid)
            self.assertEqual(ctrl.state.coach_of(kid), youth_coach)
            ctrl.promote_youth(kid.id)
            coach = ctrl.state.coach_of(kid)
            self.assertIsNotNone(coach)
            self.assertEqual(coach.specialty, Specialty.SPRINTS)

    def test_coach_skills_fade(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ctrl = self._ctrl(tmpdir, seed=4)
            before = sum(sum(c.skills.values()) for c in ctrl.state.coaches)
            for _ in range(30):
                advance_week(ctrl.state, rng=random.Random(_))
            self.assertLess(sum(sum(c.skills.values()) for c in ctrl.state.coaches), before)

    def test_active_relays_by_mode_and_season(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ctrl = self._ctrl(tmpdir, seed=5)
            self.assertEqual(ctrl.state.active_relays, ["4x100m"])
            self.assertTrue(ctrl.state.relays["4x100m"].is_complete)
            ctrl.start_new_game("X", "career")
            s = ctrl.state
            self.assertEqual(s.active_relays, ["4x100m", "4x400m"])
            # 8 athletes: both relays get 4 legs, nobody runs twice
            self.assertTrue(all(r.is_complete for r in s.relays.values()))
            ids = [aid for r in s.relays.values() for aid in r.all_ids()]
            self.assertEqual(len(ids), len(set(ids)))
            s.season_phase = SeasonPhase.CROSS
            self.assertEqual(s.active_relays, [])
            s.season_phase = SeasonPhase.INDOOR
            self.assertEqual(s.active_relays, ["4x400m"])

    def test_relay_changes_order_cooldown_and_exclusivity(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ctrl = self._ctrl(tmpdir, seed=6, mode="career")
            s = ctrl.state
            relay = s.relays["4x100m"]
            relay.harmony = 80
            legs = list(relay.member_ids)
            # swapping order is free
            self.assertTrue(ctrl.set_relay_slot("4x100m", 0, legs[3]))
            self.assertEqual(relay.member_ids[0], legs[3])
            self.assertEqual(relay.member_ids[3], legs[0])
            self.assertEqual(relay.harmony, 80)
            # an athlete can't run two relays
            other_leg = s.relays["4x400m"].member_ids[0]
            self.assertFalse(ctrl.set_relay_slot("4x100m", 1, other_leg))
            # replacing a healthy runner: -25% harmony, then a 4-week wait
            from models.generator import generate_athlete

            outsider = generate_athlete(specialty=Specialty.SPRINTS, rng=random.Random(1), gender="M")
            outsider.id = 99
            s.athletes.append(outsider)  # all 8 career men are already in a relay
            self.assertTrue(ctrl.set_relay_slot("4x100m", 4, outsider.id))  # empty reserve slot: free
            self.assertEqual(relay.harmony, 80)
            self.assertTrue(ctrl.set_relay_slot("4x400m", 0, None))  # frees a 4x400m runner
            self.assertTrue(ctrl.set_relay_slot("4x100m", 1, other_leg))
            self.assertEqual(relay.harmony, 60)
            self.assertFalse(ctrl.set_relay_slot("4x100m", 2, None))  # cooldown
            self.assertFalse(ctrl.auto_build_relay("4x100m"))

    def test_relay_harmony_grows_and_low_harmony_risks_dq(self) -> None:
        from models import simulation as sim

        with tempfile.TemporaryDirectory() as tmpdir:
            ctrl = self._ctrl(tmpdir, seed=7)
            s = ctrl.state
            for a in s.athletes:
                a.injured_weeks = 0
            relay = s.relays["4x100m"]
            start = relay.harmony
            sim._update_relay_harmony(s, raced=set())
            self.assertEqual(relay.harmony, start + 4)
            sim._update_relay_harmony(s, raced={"4x100m"})
            self.assertEqual(relay.harmony, start + 14)
        self.assertGreater(sim._relay_dq_chance(0, False), 0.3)
        self.assertEqual(sim._relay_dq_chance(80, False), 0.0)

    def test_relay_race_uses_reserve_and_spares_individual_form(self) -> None:
        from models import simulation as sim

        with tempfile.TemporaryDirectory() as tmpdir:
            ctrl = self._ctrl(tmpdir, seed=8)
            s = ctrl.state
            s.week = 4
            s.prestige = -1000
            for ev in s.active_events:
                s.event_lineup[ev] = None  # only the relay runs
                s.event_lineup_f[ev] = None
            relay = s.relays["4x100m"]
            relay.harmony = 100
            by_id = {a.id: a for a in s.athletes}
            injured = by_id[relay.member_ids[1]]
            injured.injured_weeks = 2
            reserve = by_id[relay.reserve_id]
            fatigue = {a.id: a.fatigue for a in s.athletes}
            summary = sim.simulate_competition(s, rng=random.Random(3))
            res = next(er for er in summary.event_results if er.event_name == "4x100m")
            def label(a) -> str:  # how the relay team label shows a runner
                return f"{a.name[0]}. {a.name.split(' ', 1)[-1]}"

            self.assertIn(label(reserve), res.player_athlete_name)
            self.assertNotIn(label(injured), res.player_athlete_name)
            self.assertEqual({a.id: a.fatigue for a in s.athletes}, fatigue)
            self.assertIn("4x100m", s.club_records)

    def test_sqlite_v4_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ctrl = self._ctrl(tmpdir, seed=9, mode="career")
            ctrl.hire_coach(None, "speed", "technique", tier=3)
            ctrl.state.relays["4x400m"].harmony = 77
            ctrl.db.save_game(ctrl.state)
            loaded = ctrl.db.load_game()
            assert loaded is not None
            self.assertEqual(
                [(c.name, c.specialty, c.skills) for c in loaded.coaches],
                [(c.name, c.specialty, c.skills) for c in ctrl.state.coaches],
            )
            self.assertEqual([a.coach_id for a in loaded.athletes], [a.coach_id for a in ctrl.state.athletes])
            self.assertEqual(loaded.relays["4x400m"].harmony, 77)
            self.assertEqual(loaded.relays["4x100m"].member_ids, ctrl.state.relays["4x100m"].member_ids)
            self.assertEqual(loaded.coach_hired_week, ctrl.state.week)


class TestRivalClubs(unittest.TestCase):
    """Persistent rival clubs whose athletes develop, retire and react to the player."""

    def _ctrl(self, tmpdir: str, seed: int = 1, mode: str = "vertical_slice") -> GameController:
        db = DatabaseManager(db_path=Path(tmpdir) / f"r{seed}.db")
        ctrl = GameController(db_manager=db, rng=random.Random(seed))
        if mode != "vertical_slice":
            ctrl.start_new_game(team_name="CUS Test", game_mode=mode)
        return ctrl

    @staticmethod
    def _club(ambition: float = 1.0, age: int = 20, skill: float = 50.0):
        from models.entities import EVENTS, RivalAthlete, RivalClub

        club = RivalClub(name="Test AC", tier=CompetitionTier.PROVINCIALE, ambition=ambition)
        for ev in EVENTS:
            club.athletes[ev] = RivalAthlete(name=f"X {ev}", event=ev, age=age, skill=skill)
        return club

    def test_clubs_are_created_for_every_category(self) -> None:
        from models.entities import EVENTS
        from models.generator import RIVAL_TEAMS

        with tempfile.TemporaryDirectory() as tmpdir:
            s = self._ctrl(tmpdir).state
            self.assertEqual(len(s.rival_clubs), 28)
            for tier, names in RIVAL_TEAMS.items():
                self.assertEqual([c.name for c in s.rivals_in(tier)], names)
            self.assertTrue(all(set(c.athletes) == set(EVENTS) for c in s.rival_clubs))
            self.assertTrue(all(set(c.female_athletes) == set(EVENTS) for c in s.rival_clubs))
            # stronger categories have stronger clubs
            prov = sum(c.level() for c in s.rivals_in(CompetitionTier.PROVINCIALE))
            naz = sum(c.level() for c in s.rivals_in(CompetitionTier.NAZIONALE))
            self.assertGreater(naz, prov)

    def test_lazio_csv_and_province_rival_selection(self) -> None:
        from models.generator import LAZIO_PROVINCES, RIVAL_TEAMS, load_lazio_clubs

        by_prov = load_lazio_clubs()
        self.assertEqual(set(by_prov), set(LAZIO_PROVINCES))
        self.assertGreater(sum(len(v) for v in by_prov.values()), 200)

        with tempfile.TemporaryDirectory() as tmpdir:
            for prov in LAZIO_PROVINCES:
                ctrl = self._ctrl(tmpdir, seed=31)
                ctrl.start_new_game(team_name="Atletica Test", game_mode="career", province=prov)
                s = ctrl.state
                self.assertEqual(len(s.rival_clubs), 28)
                prov_clubs = [c.name for c in s.rivals_in(CompetitionTier.PROVINCIALE)]
                reg_clubs = [c.name for c in s.rivals_in(CompetitionTier.REGIONALE)]
                self.assertEqual(len(prov_clubs), 7)
                self.assertEqual(len(reg_clubs), 7)
                self.assertTrue(set(prov_clubs).isdisjoint(set(reg_clubs)))
                if len(by_prov[prov]) >= 7:
                    self.assertTrue(all(name in by_prov[prov] for name in prov_clubs))
                self.assertEqual(
                    [c.name for c in s.rivals_in(CompetitionTier.INTERNAZIONALE)],
                    RIVAL_TEAMS[CompetitionTier.INTERNAZIONALE],
                )

    def test_meets_feature_the_same_named_rivals(self) -> None:
        from models import simulation as sim

        with tempfile.TemporaryDirectory() as tmpdir:
            s = self._ctrl(tmpdir, seed=2).state
            s.week = 4
            s.prestige = -1000
            summary = sim.simulate_competition(s, rng=random.Random(1))
            for er in summary.event_results:
                if er.event_name.startswith("4x"):
                    continue
                expected = {c.athletes_for(er.gender)[er.event_name].name for c in s.rivals_in()}
                rivals = {st.athlete_name for st in er.standings if not st.is_player}
                self.assertEqual(rivals, expected)
            for gender in ("M", "F"):
                lj = next(
                    er for er in summary.event_results
                    if er.event_name == "Salto in Lungo" and er.gender == gender
                )
                if not lj.wind_illegal:
                    self.assertTrue(
                        all(c.athletes_for(gender)["Salto in Lungo"].pb is not None for c in s.rivals_in())
                    )

    def test_young_rivals_improve_and_veterans_decline(self) -> None:
        from models.simulation import progress_rivals

        young, old = self._club(age=20), self._club(age=32)
        s = GameState(rival_clubs=[young, old])
        for week in range(1, 37):
            s.week = week
            progress_rivals(s, random.Random(week))
        self.assertGreater(young.level(), 53)
        self.assertLess(old.level(), 45)
        self.assertEqual(len(young.history), 9)  # one snapshot every 4 weeks
        self.assertGreater(young.trend, 0)

    def test_ambition_speeds_up_growth(self) -> None:
        from models.simulation import progress_rivals

        eager, lazy = self._club(ambition=1.6), self._club(ambition=0.6)
        s = GameState(rival_clubs=[eager, lazy])
        for week in range(1, 25):
            s.week = week
            progress_rivals(s, random.Random(week))
        self.assertGreater(eager.level(), lazy.level() + 1.5)

    def test_season_renewal_retires_veterans(self) -> None:
        from models.simulation import renew_rivals_for_season

        club = self._club(ambition=1.5, age=32)
        s = GameState(rival_clubs=[club], season_number=2)
        news = renew_rivals_for_season(s, random.Random(1))
        self.assertTrue(all(18 <= a.age <= 22 for a in club.athletes.values()))
        self.assertFalse(any(a.name.startswith("X ") for a in club.athletes.values()))
        self.assertGreater(club.offset, 0)  # ambitious clubs recruit better
        self.assertLess(club.ambition, 1.5)  # and calm down a bit
        self.assertEqual(len(news), 4)

    def test_beaten_clubs_get_more_ambitious(self) -> None:
        from models.simulation import _adapt_rival_ambition

        with tempfile.TemporaryDirectory() as tmpdir:
            s = self._ctrl(tmpdir, seed=3).state
            clubs = s.rivals_in()
            before = {c.name: c.ambition for c in clubs}
            points = {s.team_name: 20, clubs[0].name: 10, clubs[1].name: 40}
            _adapt_rival_ambition(s, points)
            self.assertAlmostEqual(clubs[0].ambition, min(1.6, before[clubs[0].name] + 0.04))
            self.assertAlmostEqual(clubs[1].ambition, max(0.6, before[clubs[1].name] - 0.02))

    def test_rivals_progress_over_a_career(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            s = self._ctrl(tmpdir, seed=4, mode="career").state
            start = sum(c.level() for c in s.rival_clubs)
            for _ in range(40):  # through the start of season 2 (rivals age & retire)
                advance_week(s, rng=random.Random(_))
            self.assertEqual(s.season_number, 2)
            self.assertGreater(sum(c.level() for c in s.rival_clubs), start)

    def test_rivals_roundtrip_and_old_saves_get_rivals(self) -> None:
        import sqlite3

        with tempfile.TemporaryDirectory() as tmpdir:
            ctrl = self._ctrl(tmpdir, seed=5)
            club = ctrl.state.rival_clubs[3]
            club.ambition, club.history = 1.33, [40.0, 41.5]
            club.athletes["100m"].pb, club.athletes["100m"].pb_display = 11.2, "11.20s"
            ctrl.db.save_game(ctrl.state)
            loaded = ctrl.db.load_game()
            assert loaded is not None
            lc = loaded.rival_clubs[3]
            self.assertEqual((lc.name, lc.tier, lc.ambition, lc.history), (club.name, club.tier, 1.33, [40.0, 41.5]))
            self.assertEqual(lc.athletes["100m"].pb_display, "11.20s")
            self.assertEqual(lc.offset, club.offset)
            # A v4 save (no rivals column) gets fresh rivals when opened
            path = ctrl.db.db_path
            conn = sqlite3.connect(path)
            try:
                _drop_columns_after(conn, 4)
                conn.execute("PRAGMA user_version = 4")
                conn.commit()
            finally:
                conn.close()
            ctrl2 = GameController(db_manager=DatabaseManager(db_path=path), rng=random.Random(1))
            self.assertEqual(len(ctrl2.state.rival_clubs), 28)


class TestPromotionAndRelegation(unittest.TestCase):
    """End-of-season verdict from the league table: top 2 up, last one down."""

    def _career(self, tmpdir: str, seed: int = 1) -> GameController:
        ctrl = GameController(db_manager=DatabaseManager(db_path=Path(tmpdir) / f"p{seed}.db"), rng=random.Random(seed))
        ctrl.start_new_game(team_name="CUS Test", game_mode="career")
        return ctrl

    @staticmethod
    def _force_position(state: GameState, position: int) -> None:
        """Rig the league table so the player finishes in the given position."""
        names = [c.name for c in state.rivals_in()]
        table = {}
        points = 1000
        for pos in range(1, len(names) + 2):
            team = state.team_name if pos == position else names.pop(0)
            table[team] = points
            points -= 100  # gaps no single meet (max ~40 pts) can close
        state.league_table = table

    def _end_season(self, ctrl: GameController):
        ctrl.state.week = 36
        ctrl.state.season_phase = SeasonPhase.INDOOR
        return ctrl.advance_week()

    def test_prestige_no_longer_promotes_mid_season(self) -> None:
        from models import simulation as sim

        with tempfile.TemporaryDirectory() as tmpdir:
            ctrl = self._career(tmpdir)
            ctrl.state.week = 4
            ctrl.state.prestige = 5000
            summary = sim.simulate_competition(ctrl.state, rng=random.Random(1))
            self.assertIsNone(summary.promoted_to)
            self.assertEqual(ctrl.state.tier, CompetitionTier.PROVINCIALE)

    def test_top_two_are_promoted(self) -> None:
        from models.entities import SeasonOutcome

        for position in (1, 2):
            with tempfile.TemporaryDirectory() as tmpdir:
                ctrl = self._career(tmpdir)
                seen = []
                ctrl.season_ended.connect(seen.append)
                self._force_position(ctrl.state, position)
                report = self._end_season(ctrl)
                assert report is not None and report.season_end is not None
                self.assertEqual(report.season_end.outcome, SeasonOutcome.PROMOTED)
                self.assertEqual(report.season_end.placement, position)
                self.assertEqual(ctrl.state.tier, CompetitionTier.REGIONALE)
                self.assertEqual(ctrl.state.season_number, 2)
                self.assertEqual(ctrl.state.league_table, {})
                self.assertEqual(seen, [report.season_end])

    def test_third_place_stays(self) -> None:
        from models.entities import SeasonOutcome

        with tempfile.TemporaryDirectory() as tmpdir:
            ctrl = self._career(tmpdir)
            ctrl.state.tier = CompetitionTier.NAZIONALE
            self._force_position(ctrl.state, 3)
            report = self._end_season(ctrl)
            self.assertEqual(report.season_end.outcome, SeasonOutcome.STAYED)
            self.assertEqual(ctrl.state.tier, CompetitionTier.NAZIONALE)

    def test_last_place_is_relegated(self) -> None:
        from models.entities import SeasonOutcome

        with tempfile.TemporaryDirectory() as tmpdir:
            ctrl = self._career(tmpdir)
            ctrl.state.tier = CompetitionTier.NAZIONALE
            self._force_position(ctrl.state, 8)
            report = self._end_season(ctrl)
            self.assertEqual(report.season_end.outcome, SeasonOutcome.RELEGATED)
            self.assertEqual(ctrl.state.tier, CompetitionTier.REGIONALE)
            self.assertTrue(any("RETROCESSIONE" in m for m in ctrl.state.milestones))

    def test_category_limits(self) -> None:
        from models.entities import SeasonOutcome

        with tempfile.TemporaryDirectory() as tmpdir:
            ctrl = self._career(tmpdir)
            self._force_position(ctrl.state, 8)  # can't go below Provinciale
            self.assertEqual(self._end_season(ctrl).season_end.outcome, SeasonOutcome.STAYED)
            self.assertEqual(ctrl.state.tier, CompetitionTier.PROVINCIALE)
        with tempfile.TemporaryDirectory() as tmpdir:
            ctrl = self._career(tmpdir)
            ctrl.state.tier = CompetitionTier.INTERNAZIONALE
            self._force_position(ctrl.state, 1)  # top category: the title
            self.assertEqual(self._end_season(ctrl).season_end.outcome, SeasonOutcome.CHAMPION)
            self.assertEqual(ctrl.state.tier, CompetitionTier.INTERNAZIONALE)

    def test_league_standings_include_everyone(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            s = self._career(tmpdir).state
            self.assertEqual(len(s.league_standings()), 8)
            self.assertEqual(s.weeks_to_season_end, 36)
            s.league_table = {s.rivals_in()[0].name: 3}
            self.assertEqual(s.league_standings()[0], (s.rivals_in()[0].name, 3))
            zero_points = sorted(t for t, p in s.league_standings() if p == 0)
            self.assertEqual([t for t, _p in s.league_standings()[1:]], zero_points)  # ties: alphabetical
            self.assertEqual(s.league_position, 2 + zero_points.index(s.team_name))

    def test_season_history_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ctrl = self._career(tmpdir)
            self._force_position(ctrl.state, 1)
            self._end_season(ctrl)
            loaded = ctrl.db.load_game()
            assert loaded is not None
            self.assertEqual(len(loaded.season_history), 1)
            h, o = loaded.season_history[0], ctrl.state.season_history[0]
            self.assertEqual((h.season, h.tier, h.placement, h.outcome, h.new_tier, h.final_table),
                             (o.season, o.tier, o.placement, o.outcome, o.new_tier, o.final_table))


class TestPyQtViewsV2(unittest.TestCase):
    """Smoke tests for MainWindow (6 tabs) and updated Dialogs."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_mainwindow_and_dialogs(self) -> None:
        from views.dialogs import (
            CompetitionResultsDialog,
            EthicalDilemmaDialog,
            NewGameDialog,
            RecruitAthleteDialog,
        )
        from views.main_window import MainWindow

        with tempfile.TemporaryDirectory() as tmpdir:
            db = DatabaseManager(db_path=Path(tmpdir) / "ui_v2.db")
            ctrl = GameController(db_manager=db, rng=random.Random(15))
            win = MainWindow(controller=ctrl)

            self.assertEqual(win.windowTitle(), "Track & Field Manager")
            self.assertEqual(win.tabs.count(), 9)
            self.assertEqual(win.rivals_tab.clubs_table.rowCount(), 7)
            self.assertEqual(win.rivals_tab.compare_table.rowCount(), 3)
            self.assertEqual(win.rivals_tab.roster_table.rowCount(), 3)
            self.assertEqual(win.roster_tab.table.rowCount(), 10)
            self.assertEqual(win.calendar_tab.lineup_table.rowCount(), 6)
            self.assertEqual(win.staff_tab.table.rowCount(), 3)
            self.assertEqual(win.staff_tab.coach_table.rowCount(), 3)
            self.assertEqual(len(win.relay_tab._slot_combos["4x100m"]), 5)
            self.assertTrue(win.relay_tab._slot_combos["4x100m"][0].isEnabled())
            self.assertFalse(win.relay_tab._slot_combos["4x400m"][0].isEnabled())  # no 400m in prototype

            from models.entities import NATIONALITIES
            from views.athlete_dialog import AthleteDetailDialog, stat_colors

            self.assertEqual(stat_colors(85)[0], "#16a34a")
            self.assertEqual(stat_colors(30)[0], "#ef4444")
            self.assertEqual(stat_colors(80, invert=True)[0], "#ef4444")  # molta fatica = rosso
            first = ctrl.state.athletes[0]
            self.assertTrue(150 <= first.height_cm <= 205 and 45 <= first.weight_kg <= 140)
            self.assertIn(first.nationality, NATIONALITIES)
            detail = AthleteDetailDialog(ctrl, ctrl.state.athletes[0].id)
            self.assertEqual(detail.tabs.count(), 3)
            detail.refresh()
            detail.close()

            new_dlg = NewGameDialog()
            self.assertEqual(new_dlg.game_mode, "vertical_slice")
            new_dlg.close()

            prospects = ctrl.generate_free_agents(count=4)
            rec_dlg = RecruitAthleteDialog(prospects, ctrl.state.budget)
            self.assertEqual(rec_dlg.table.rowCount(), 4)
            rec_dlg.close()

            ctrl.state.week = 4
            rep = advance_week(ctrl.state, rng=random.Random(15))
            assert rep.competition_summary is not None
            comp_dlg = CompetitionResultsDialog(rep.competition_summary)
            self.assertEqual(comp_dlg.events_table.rowCount(), 8)  # 3 M + 3 F + 4x100m M + 4x100m F
            self.assertEqual(comp_dlg.team_table.rowCount(), 8)
            comp_dlg.close()

            # Youth academy tab reflects scouting and signing
            kids = ctrl.run_youth_scouting()
            self.assertEqual(win.youth_tab.results_table.rowCount(), len(kids))
            ctrl.sign_youth(kids[0])
            self.assertEqual(win.youth_tab.youth_table.rowCount(), 1)
            self.assertEqual(win.roster_tab.table.rowCount(), 10)  # academy kids stay out of the roster
            self.assertEqual(win.calendar_tab.lineup_table.columnCount(), 5)

            if ctrl.state.pending_dilemma is not None:
                dil_dlg = EthicalDilemmaDialog(ctrl.state.pending_dilemma)
                dil_dlg.close()

            from models.entities import SeasonEndResult, SeasonOutcome
            from views.dialogs import SeasonEndDialog

            result = SeasonEndResult(
                season=1, tier=CompetitionTier.REGIONALE, placement=8,
                outcome=SeasonOutcome.RELEGATED, final_table=ctrl.state.league_standings(),
                new_tier=CompetitionTier.PROVINCIALE,
            )
            season_dlg = SeasonEndDialog(result, ctrl.state.team_name)
            self.assertEqual(season_dlg.table.rowCount(), 8)
            season_dlg.close()

            win.close()


class TestRaceExport(unittest.TestCase):
    """Esportazione dei 100m verso il visualizzatore Godot (godot_viewer/)."""

    def _summary(self):
        from models.entities import CompetitionSummary, EventResult, EventStanding

        marks = [9.87, 9.93, 10.05, 10.2]
        standings = [
            EventStanding(f"Atleta {i}", f"Club {i}", i == 1, m, f"{m:.2f}s", placement=i + 1)
            for i, m in enumerate(marks)
        ]
        result = EventResult(
            event_name="100m", player_athlete_name="Atleta 1", placement=2, total_competitors=4,
            player_mark="9.93s", prize_money=0, prestige_gained=0, standings=standings,
        )
        summary = CompetitionSummary(
            week=3, tier=list(CompetitionTier)[0], season_phase=list(SeasonPhase)[0], meet_name="Meeting di prova",
            weather=list(WeatherCondition)[0], track_surface="Tartan", event_results=[result],
            total_prize_money=0, total_prestige_gained=0,
        )
        return summary, result

    def test_export_copies_official_times_and_is_deterministic(self):
        import sqlite3
        from models.race_export import export_race

        summary, result = self._summary()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "race_results.db"
            race_id = export_race(summary, result, path)
            self.assertEqual(export_race(summary, result, path), race_id + 1)
            conn = sqlite3.connect(str(path))
            rows = conn.execute(
                "SELECT lane, athlete_name, reaction_time, final_time FROM race_results WHERE race_id = ?",
                (race_id,),
            ).fetchall()
            again = conn.execute(
                "SELECT lane, athlete_name, reaction_time, final_time FROM race_results WHERE race_id = ?",
                (race_id + 1,),
            ).fetchall()
            conn.close()
        self.assertEqual(sorted(r[3] for r in rows), [9.87, 9.93, 10.05, 10.2])  # tempi invariati
        self.assertEqual(sorted(r[0] for r in rows), [1, 2, 3, 4])              # corsie uniche
        self.assertTrue(all(0 < r[2] < r[3] for r in rows))                       # reazione inclusa nel tempo
        self.assertEqual(sorted(rows), sorted(again))                             # stesso sorteggio

    def test_export_marks_injured_player_as_dnf_and_refuses_overfull_races(self):
        import sqlite3
        from models.race_export import export_race

        summary, result = self._summary()
        result.withdrew_injured = True  # il giocatore (Atleta 1) si ritira
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "race_results.db"
            race_id = export_race(summary, result, path)
            conn = sqlite3.connect(str(path))
            rows = {r[0]: r[1:] for r in conn.execute(
                "SELECT athlete_name, status, final_time FROM race_results WHERE race_id = ?", (race_id,))}
            conn.close()
            self.assertEqual(rows["Atleta 1"][0], "DNF")
            self.assertTrue(all(v[0] == "OK" for k, v in rows.items() if k != "Atleta 1"))
            others = sorted(v[1] for k, v in rows.items() if k != "Atleta 1")
            self.assertEqual(others, [9.87, 10.05, 10.2])            # i classificati mantengono il tempo
            self.assertTrue(9.87 < rows["Atleta 1"][1] < 10.2)        # riferimento = mediana, nessun tempo inventato fuori scala

            result.standings = result.standings * 3                    # 12 corridori: troppi per 8 corsie
            with self.assertRaises(ValueError):
                export_race(summary, result, path)

    def test_export_400m_records_distance_and_refuses_unsupported_events(self):
        import sqlite3
        from models.race_export import export_race

        summary, result = self._summary()
        result.event_name = "400m"
        for s, m in zip(result.standings, [45.1, 45.8, 46.4, 47.0]):
            s.mark_value = m
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "race_results.db"
            race_id = export_race(summary, result, path)
            conn = sqlite3.connect(str(path))
            event, distance = conn.execute("SELECT event_name, distance_m FROM races WHERE race_id = ?", (race_id,)).fetchone()
            times = sorted(r[0] for r in conn.execute("SELECT final_time FROM race_results WHERE race_id = ?", (race_id,)))
            conn.close()
            self.assertEqual((event, distance), ("400m", 400))
            self.assertEqual(times, [45.1, 45.8, 46.4, 47.0])
            result.event_name = "1500m"
            for st, t in zip(result.standings, [232.4, 234.1, 236.8, 239.0]):
                st.mark_value = t
            race_1500 = export_race(summary, result, path)
            conn = sqlite3.connect(str(path))
            ev1500, dist1500 = conn.execute(
                "SELECT event_name, distance_m FROM races WHERE race_id = ?", (race_1500,)
            ).fetchone()
            conn.close()
            self.assertEqual((ev1500, dist1500), ("1500m", 1500))
            result.event_name = "4x100m"
            for st, t in zip(result.standings, [40.2, 40.9, 41.4, 42.1]):
                st.mark_value = t
            race_4x1 = export_race(summary, result, path)
            conn = sqlite3.connect(str(path))
            ev4x1, dist4x1 = conn.execute(
                "SELECT event_name, distance_m FROM races WHERE race_id = ?", (race_4x1,)
            ).fetchone()
            conn.close()
            self.assertEqual((ev4x1, dist4x1), ("4x100m", 400))

            result.event_name = "Salto in Lungo"
            for st, m in zip(result.standings, [7.72, 7.56, 7.45, 7.28]):
                st.mark_value = m
            race_lj = export_race(summary, result, path)
            conn = sqlite3.connect(str(path))
            ev_lj, dist_lj = conn.execute(
                "SELECT event_name, distance_m FROM races WHERE race_id = ?", (race_lj,)
            ).fetchone()
            attempts_cnt = conn.execute(
                "SELECT COUNT(*) FROM field_attempts WHERE race_id = ?", (race_lj,)
            ).fetchone()[0]
            conn.close()
            self.assertEqual((ev_lj, dist_lj), ("Salto in Lungo", 0))
            self.assertEqual(attempts_cnt, 16)

            result.event_name = "Getto del Peso"
            for st, m in zip(result.standings, [19.42, 18.60, 17.85, 17.40]):
                st.mark_value = m
            race_sp = export_race(summary, result, path)
            conn = sqlite3.connect(str(path))
            ev_sp, dist_sp = conn.execute(
                "SELECT event_name, distance_m FROM races WHERE race_id = ?", (race_sp,)
            ).fetchone()
            attempts_sp = conn.execute(
                "SELECT COUNT(*) FROM field_attempts WHERE race_id = ?", (race_sp,)
            ).fetchone()[0]
            conn.close()
            self.assertEqual((ev_sp, dist_sp), ("Getto del Peso", 0))
            self.assertEqual(attempts_sp, 16)

            result.event_name = "Lancio del Disco"
            with self.assertRaises(ValueError):
                export_race(summary, result, path)

    def test_godot_viewer_is_skipped_when_disabled_and_only_for_supported_events(self):
        import views.godot_launcher as gl

        self.assertIsNone(gl.find_godot())           # TEF_NO_GODOT attivo nei test
        self.assertIsNone(gl.viewer_available("100m"))
        self.assertIsNone(gl.viewer_available("400m"))
        self.assertIsNone(gl.viewer_available("1500m"))
        self.assertIsNone(gl.viewer_available("4x100m"))
        self.assertIsNone(gl.viewer_available("Salto in Lungo"))
        self.assertIsNone(gl.viewer_available("Getto del Peso"))
        self.assertIn("400m", gl.GODOT_EVENTS)
        self.assertIn("1500m", gl.GODOT_EVENTS)
        self.assertIn("4x100m", gl.GODOT_EVENTS)
        self.assertIn("4x400m", gl.GODOT_EVENTS)
        self.assertIn("Salto in Lungo", gl.GODOT_EVENTS)
        self.assertIn("Getto del Peso", gl.GODOT_EVENTS)
        summary, result = self._summary()
        self.assertIsNone(gl.launch_race_viewer(summary, result, lambda code: None))  # -> vista interna

    def test_next_race_db_path_ignores_locked_stale_file(self) -> None:
        from unittest import mock
        import views.godot_launcher as gl

        with tempfile.TemporaryDirectory() as td:
            save_path = Path(td) / "savegame.db"
            locked_db = Path(td) / "race_results.db"
            stale_db = Path(td) / "race_results_old.db"
            locked_db.write_bytes(b"locked")
            stale_db.write_bytes(b"stale")
            orig_unlink = Path.unlink

            def fake_unlink(p: Path, missing_ok: bool = False) -> None:
                if p.name == "race_results.db":
                    raise PermissionError(32, "locked")
                orig_unlink(p, missing_ok=missing_ok)

            with (
                mock.patch.object(gl, "get_default_save_path", return_value=save_path),
                mock.patch.object(Path, "unlink", fake_unlink),
            ):
                fresh = gl._next_race_db_path()
            self.assertEqual(fresh.parent, Path(td))
            self.assertNotEqual(fresh.name, "race_results.db")
            self.assertTrue(fresh.name.startswith("race_results_"))
            self.assertFalse(stale_db.exists())
            self.assertTrue(locked_db.exists())

    def test_godot_class_cache_detection(self) -> None:
        import views.godot_launcher as gl

        self.assertEqual(gl._missing_class_names(gl.GODOT_PROJECT), set())
        with tempfile.TemporaryDirectory() as td:
            proj = Path(td)
            (proj / "scripts").mkdir()
            (proj / "scripts" / "Foo.gd").write_text("class_name FooBar\nextends RefCounted\n", encoding="utf-8")
            self.assertEqual(gl._missing_class_names(proj), {"FooBar"})
            (proj / ".godot").mkdir()
            (proj / ".godot" / "global_script_class_cache.cfg").write_text(
                'list=[{"class": &"FooBar", "path": "res://scripts/Foo.gd"}]\n',
                encoding="utf-8",
            )
            self.assertEqual(gl._missing_class_names(proj), set())

    def test_export_race_includes_inferred_gender(self) -> None:
        import sqlite3
        from models.generator import infer_gender
        from models.race_export import export_race

        self.assertEqual(infer_gender("Giulia Rossi"), "F")
        self.assertEqual(infer_gender("Marco Valenti"), "M")
        summary, result = self._summary()
        result.standings[0].athlete_name = "Giulia Conti"
        result.standings[1].athlete_name = "Marco Valenti"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gender.db"
            race_id = export_race(summary, result, path)
            conn = sqlite3.connect(str(path))
            genders = dict(conn.execute("SELECT athlete_name, gender FROM race_results WHERE race_id = ?", (race_id,)))
            conn.close()
            self.assertEqual(genders["Giulia Conti"], "F")
            self.assertEqual(genders["Marco Valenti"], "M")


class TestGenderDivisions(unittest.TestCase):
    """Separate Men's (M) and Women's (F) athletic divisions across sim, DB, and export."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_mixed_roster_lineups_and_separate_records(self) -> None:
        from models import simulation as sim

        with tempfile.TemporaryDirectory() as tmpdir:
            db = DatabaseManager(db_path=Path(tmpdir) / "mf.db")
            ctrl = GameController(db_manager=db, rng=random.Random(21))
            s = ctrl.state

            genders = {a.gender for a in s.main_squad}
            self.assertEqual(genders, {"M", "F"})
            self.assertTrue(all(a.id is not None for a in s.main_squad))
            by_id = {a.id: a for a in s.main_squad}

            # Every event has a male lineup slot and a female lineup slot matched by gender
            for ev in s.active_events:
                m_id = s.event_lineup.get(ev)
                f_id = s.event_lineup_f.get(ev)
                if m_id is not None:
                    self.assertEqual(by_id[m_id].gender, "M")
                if f_id is not None:
                    self.assertEqual(by_id[f_id].gender, "F")

            s.week = 4
            s.prestige = -1000
            summary = sim.simulate_competition(s, rng=random.Random(4))
            indiv = [er for er in summary.event_results if not er.event_name.startswith("4x")]
            self.assertEqual(len(indiv), len(s.active_events) * 2)
            self.assertEqual(
                [(er.event_name, er.gender) for er in indiv],
                [(ev, g) for g in ("M", "F") for ev in s.active_events],
            )

            # Club records stay separated between Maschile and Femminile
            self.assertIn("100m", s.club_records)
            self.assertIn("100m", s.club_records_f)
            self.assertNotEqual(s.club_records["100m"][2], s.club_records_f["100m"][2])

            # Women's 100m time sits in realistic women's range (> 10.49s)
            f_100 = next(er for er in indiv if er.event_name == "100m" and er.gender == "F")
            self.assertGreater(min(st.mark_value for st in f_100.standings), 10.49)

    def test_v7_to_v8_migration_and_roundtrip(self) -> None:
        import sqlite3
        from models.simulation import upgrade_legacy_state

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "v7mig.db"
            db = DatabaseManager(db_path=path)
            ctrl = GameController(db_manager=db, rng=random.Random(7))
            ctrl.state.week = 4
            summary = advance_week(ctrl.state, rng=random.Random(7)).competition_summary
            assert summary is not None
            db.save_game(ctrl.state)

            # Verify v8 roundtrip preserves F lineup, F club records, and EventResult.gender
            loaded_v8 = db.load_game()
            assert loaded_v8 is not None
            self.assertEqual(loaded_v8.event_lineup_f, ctrl.state.event_lineup_f)
            self.assertEqual(loaded_v8.club_records_f, ctrl.state.club_records_f)
            self.assertEqual(
                [er.gender for er in loaded_v8.competition_history[0].event_results],
                [er.gender for er in ctrl.state.competition_history[0].event_results],
            )

            # Simulate a v7 database without v8 columns and with empty female_athletes
            for club in ctrl.state.rival_clubs:
                club.female_athletes.clear()
            db.save_game(ctrl.state)
            conn = sqlite3.connect(str(path))
            try:
                _drop_columns_after(conn, 7)
                conn.execute("PRAGMA user_version = 7")
                conn.commit()
            finally:
                conn.close()

            migrated_db = DatabaseManager(db_path=path)
            migrated = migrated_db.load_game()
            assert migrated is not None
            upgrade_legacy_state(migrated, rng=random.Random(7))
            self.assertTrue(all(a.gender in ("M", "F") for a in migrated.athletes))
            self.assertTrue(all(len(c.female_athletes) > 0 for c in migrated.rival_clubs))
            self.assertTrue(any(v is not None for v in migrated.event_lineup_f.values()))

    def test_export_race_respects_explicit_female_division(self) -> None:
        import sqlite3
        from models.race_export import export_race

        with tempfile.TemporaryDirectory() as tmpdir:
            db = DatabaseManager(db_path=Path(tmpdir) / "exp.db")
            ctrl = GameController(db_manager=db, rng=random.Random(12))
            ctrl.state.week = 4
            summary = advance_week(ctrl.state, rng=random.Random(12)).competition_summary
            assert summary is not None
            f_100 = next(er for er in summary.event_results if er.event_name == "100m" and er.gender == "F")
            race_path = Path(tmpdir) / "race_f.db"
            race_id = export_race(summary, f_100, race_path)
            conn = sqlite3.connect(str(race_path))
            rows = conn.execute("SELECT gender FROM race_results WHERE race_id = ?", (race_id,)).fetchall()
            conn.close()
            self.assertEqual(len(rows), len(f_100.standings))
            self.assertTrue(all(r[0] == "F" for r in rows))

    def test_male_and_female_relays_career_sim_and_v9_migration(self) -> None:
        import sqlite3
        from models.simulation import upgrade_legacy_state
        from views.tabs import RelayTab

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "relays_mf.db"
            db = DatabaseManager(db_path=path)
            ctrl = GameController(db_manager=db, rng=random.Random(19))
            ctrl.start_new_game("CUS Relays", "career")
            s = ctrl.state

            # Both M and F 4x100m and 4x400m start complete with zero shared runners
            for g in ("M", "F"):
                pool = s.relays_for(g)
                self.assertEqual(set(pool), {"4x100m", "4x400m"})
                self.assertTrue(all(r.is_complete for r in pool.values()))
                ids = [aid for r in pool.values() for aid in r.all_ids()]
                self.assertEqual(len(ids), len(set(ids)))
                by_id = {a.id: a for a in s.athletes}
                self.assertTrue(all(by_id[aid].gender == g for aid in ids))

            # Cross-gender relay slot assignment is rejected
            first_f = next(a for a in s.main_squad if a.gender == "F")
            first_m = next(a for a in s.main_squad if a.gender == "M")
            self.assertFalse(ctrl.set_relay_slot("4x100m", 0, first_f.id, gender="M"))
            self.assertFalse(ctrl.set_relay_slot("4x100m", 0, first_m.id, gender="F"))

            # Simulate an outdoor meet -> runs both 4x100m (M) and 4x100m (F)
            s.relays["4x100m"].harmony = 100
            s.relays_f["4x100m"].harmony = 100
            s.week = 4
            s.prestige = -1000
            summary = advance_week(s, rng=random.Random(5)).competition_summary
            assert summary is not None
            r4x1 = [er for er in summary.event_results if er.event_name == "4x100m"]
            self.assertEqual([(er.gender, er.display_event_name) for er in r4x1], [
                ("M", "4x100m (M)"),
                ("F", "4x100m (F)"),
            ])
            f_relay = next(er for er in r4x1 if er.gender == "F")
            self.assertGreaterEqual(min(st.mark_value for st in f_relay.standings), 40.8)
            self.assertIn("4x100m", s.club_records)
            self.assertIn("4x100m", s.club_records_f)

            # UI RelayTab division switch shows female squad
            tab = RelayTab(ctrl)
            tab.refresh(s)
            tab.division_combo.setCurrentIndex(1)  # Femminile (F)
            self.assertIn("4x100m (F)", tab._titles["4x100m"].text())
            self.assertEqual(tab._slot_combos["4x100m"][0].currentData(), s.relays_f["4x100m"].member_ids[0])
            tab.close()

            # v8 -> v9 migration preserves/rebuilds relays_f
            s.relays_f["4x400m"].harmony = 88
            db.save_game(s)
            reloaded = db.load_game()
            assert reloaded is not None
            self.assertEqual(reloaded.relays_f["4x400m"].harmony, 88)

            conn = sqlite3.connect(str(path))
            try:
                _drop_columns_after(conn, 8)
                conn.execute("PRAGMA user_version = 8")
                conn.commit()
            finally:
                conn.close()

            mig_db = DatabaseManager(db_path=path)
            migrated = mig_db.load_game()
            assert migrated is not None
            upgrade_legacy_state(migrated, rng=random.Random(19))
            self.assertEqual(set(migrated.relays_f), {"4x100m", "4x400m"})
            self.assertTrue(all(r.is_complete for r in migrated.relays_f.values()))

    def test_100m_senior_curve_matches_fidal_ranges(self) -> None:
        from models.entities import EVENTS
        from models.simulation import _score_to_mark

        ev = EVENTS["100m"]
        # Provinciale senior rival avg (~42): M ~11.62s, F ~12.79s (wind=0.0)
        m_prov, _ = _score_to_mark(ev, 42.0, wind_ms=0.0, gender="M")
        f_prov, _ = _score_to_mark(ev, 42.0, wind_ms=0.0, gender="F")
        self.assertGreater(m_prov, 11.45)
        self.assertLess(m_prov, 11.80)
        self.assertGreater(f_prov, 12.60)
        self.assertLess(f_prov, 13.00)

        # Tail provincial M (~33): ~11.91s; Nazionale (~70): ~10.74s; Internazionale (~84): ~10.30s
        m_tail, _ = _score_to_mark(ev, 33.0, wind_ms=0.0, gender="M")
        m_naz, _ = _score_to_mark(ev, 70.0, wind_ms=0.0, gender="M")
        m_int, _ = _score_to_mark(ev, 84.0, wind_ms=0.0, gender="M")
        self.assertTrue(11.80 <= m_tail <= 12.05)
        self.assertTrue(10.60 <= m_naz <= 10.85)
        self.assertTrue(10.15 <= m_int <= 10.45)
        self.assertGreater(m_tail, m_prov)
        self.assertGreater(m_prov, m_naz)
        self.assertGreater(m_naz, m_int)

    def test_400m_regional_senior_curve_matches_fidal_ranges(self) -> None:
        from models.entities import EVENTS
        from models.simulation import _score_to_mark

        ev = EVENTS["400m"]
        # Provinciale avg (42): M ~53.21s (FIDAL SM median ~53.6s), F ~59.85s
        m_prov, _ = _score_to_mark(ev, 42.0, gender="M")
        f_prov, _ = _score_to_mark(ev, 42.0, gender="F")
        self.assertTrue(52.5 <= m_prov <= 54.0)
        self.assertTrue(58.5 <= f_prov <= 61.0)

        # Regionale avg (56) & top (66): M ~50.74s / ~48.98s; F ~56.96s / ~54.90s
        m_reg, _ = _score_to_mark(ev, 56.0, gender="M")
        m_reg_top, _ = _score_to_mark(ev, 66.0, gender="M")
        f_reg, _ = _score_to_mark(ev, 56.0, gender="F")
        f_reg_top, _ = _score_to_mark(ev, 66.0, gender="F")
        self.assertTrue(49.8 <= m_reg <= 51.6)
        self.assertTrue(48.3 <= m_reg_top <= 49.6)
        self.assertTrue(56.0 <= f_reg <= 58.0)
        self.assertTrue(54.2 <= f_reg_top <= 56.0)

        # Internazionale avg (84): M ~45.82s, F ~51.20s
        m_int, _ = _score_to_mark(ev, 84.0, gender="M")
        f_int, _ = _score_to_mark(ev, 84.0, gender="F")
        self.assertTrue(45.0 <= m_int <= 46.6)
        self.assertTrue(50.2 <= f_int <= 52.0)

    def test_1500m_regional_senior_curve_matches_fidal_ranges(self) -> None:
        from models.entities import EVENTS
        from models.simulation import _score_to_mark

        ev = EVENTS["1500m"]
        # Provinciale avg (42): M ~4:24.12 (264.1s), F ~5:02.36 (302.4s)
        m_prov, _ = _score_to_mark(ev, 42.0, gender="M")
        f_prov, _ = _score_to_mark(ev, 42.0, gender="F")
        self.assertTrue(258.0 <= m_prov <= 270.0)
        self.assertTrue(295.0 <= f_prov <= 310.0)

        # Regionale avg (56) & top (66): M ~4:08.16 / ~3:56.76; F ~4:42.48 / ~4:28.28
        m_reg, _ = _score_to_mark(ev, 56.0, gender="M")
        m_reg_top, _ = _score_to_mark(ev, 66.0, gender="M")
        f_reg, _ = _score_to_mark(ev, 56.0, gender="F")
        f_reg_top, _ = _score_to_mark(ev, 66.0, gender="F")
        self.assertTrue(244.0 <= m_reg <= 252.0)
        self.assertTrue(234.0 <= m_reg_top <= 240.0)
        self.assertTrue(278.0 <= f_reg <= 288.0)
        self.assertTrue(265.0 <= f_reg_top <= 272.0)

        # Nazionale avg (70) & Internazionale avg (84)
        m_naz, _ = _score_to_mark(ev, 70.0, gender="M")
        m_int, _ = _score_to_mark(ev, 84.0, gender="M")
        f_naz, _ = _score_to_mark(ev, 70.0, gender="F")
        f_int, _ = _score_to_mark(ev, 84.0, gender="F")
        self.assertTrue(228.0 <= m_naz <= 236.0)
        self.assertTrue(212.0 <= m_int <= 220.0)
        self.assertTrue(258.0 <= f_naz <= 268.0)
        self.assertTrue(238.0 <= f_int <= 248.0)

    def test_long_jump_curve_matches_fidal_ranges(self) -> None:
        from models.entities import EVENTS
        from models.simulation import _score_to_mark

        ev = EVENTS["Salto in Lungo"]

        def mark(score: float, gender: str) -> float:
            return _score_to_mark(ev, score, gender=gender)[0]

        # Ancora REALE: campionati regionali Lazio 2025, lungo F vinto con 5,75 (+0.3); M in testa con 6,52 dopo
        # 2 turni (gara sospesa). Le altre ancore (provinciale, media regionale) sono STIME, non dati FIDAL.
        # Provinciale (42): M ~5.90, F ~4.80
        self.assertTrue(5.5 <= mark(42.0, "M") <= 6.3)
        self.assertTrue(4.5 <= mark(42.0, "F") <= 5.2)
        # Regionale media (56) e vincitore regionale (66): M ~6.53 / ~6.98, F ~5.39 / ~5.80
        self.assertTrue(6.2 <= mark(56.0, "M") <= 6.8)
        self.assertTrue(6.6 <= mark(66.0, "M") <= 7.2)
        self.assertTrue(5.1 <= mark(56.0, "F") <= 5.6)
        self.assertTrue(5.5 <= mark(66.0, "F") <= 6.0)
        # Nazionale (70) e internazionale (84). Riferimento reale: Assoluti 2025, M 8,26 / 7,96 / 7,47,
        # F 6,78 / 6,41 / 6,20: i livelli di gioco stanno sotto i finalisti d'élite.
        self.assertTrue(6.8 <= mark(70.0, "M") <= 7.4)
        self.assertTrue(7.5 <= mark(84.0, "M") <= 8.1)
        self.assertTrue(5.7 <= mark(70.0, "F") <= 6.2)
        self.assertTrue(6.3 <= mark(84.0, "F") <= 6.8)
        # Monotona in score e mai oltre il record del mondo, nemmeno con vento a favore.
        for gender, record in (("M", 8.95), ("F", 7.52)):
            marks = [mark(s, gender) for s in range(15, 119, 3)]
            self.assertEqual(marks, sorted(marks))
            self.assertAlmostEqual(_score_to_mark(ev, 118.0, wind_ms=2.0, gender=gender)[0], record)
        self.assertGreater(
            _score_to_mark(ev, 60.0, wind_ms=2.0)[0], _score_to_mark(ev, 60.0, wind_ms=0.0)[0]
        )

    def test_shot_put_curve_matches_fidal_ranges(self) -> None:
        from models.entities import EVENTS
        from models.simulation import _score_to_mark

        ev = EVENTS["Getto del Peso"]

        def mark(score: float, gender: str) -> float:
            return _score_to_mark(ev, score, gender=gender)[0]

        # Ancora REALE: campionati regionali Lazio 2025, peso F vinto con 13,75. Peso M vincitore regionale: solo un
        # dato Veneto (15,58, anno non confermato). Provinciale e media regionale sono STIME, non dati FIDAL.
        # Provinciale (42): M ~10.82, F ~9.00
        self.assertTrue(10.0 <= mark(42.0, "M") <= 12.0)
        self.assertTrue(8.2 <= mark(42.0, "F") <= 10.0)
        # Regionale media (56) e vincitore regionale (66): M ~13.76 / ~15.86, F ~11.77 / ~13.74
        self.assertTrue(12.8 <= mark(56.0, "M") <= 14.5)
        self.assertTrue(15.0 <= mark(66.0, "M") <= 16.5)
        self.assertTrue(10.8 <= mark(56.0, "F") <= 12.5)
        self.assertTrue(13.0 <= mark(66.0, "F") <= 14.3)
        # Nazionale (70) e internazionale (84). Riferimento reale: Assoluti 2025, M 22,82 / 21,02 / 20,38,
        # F 15,55 / 15,41 / 14,54: i livelli di gioco stanno sotto i finalisti d'élite.
        self.assertTrue(16.0 <= mark(70.0, "M") <= 17.5)
        self.assertTrue(19.0 <= mark(84.0, "M") <= 20.5)
        self.assertTrue(13.8 <= mark(70.0, "F") <= 15.2)
        self.assertTrue(16.6 <= mark(84.0, "F") <= 18.0)
        # Monotona in score e mai oltre il record del mondo.
        for gender, record in (("M", 23.56), ("F", 22.63)):
            marks = [mark(s, gender) for s in range(15, 119, 3)]
            self.assertEqual(marks, sorted(marks))
            self.assertAlmostEqual(mark(118.0, gender), record)


class TestStartScreenAndUX(unittest.TestCase):
    """Tests for StartScreen, multi-slot saves, sidebar navigation, dashboard actions, and roster filters."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_start_screen_non_destructive_and_multislot_flow(self) -> None:
        from views.main_window import MainWindow

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            saves_dir = root / "saves"
            legacy_path = root / "savegame.db"

            ctrl = GameController(
                auto_create=False,
                saves_dir=saves_dir,
                legacy_save_path=legacy_path,
                rng=random.Random(21),
            )
            win = MainWindow(controller=ctrl, start_on_menu=True)
            self.assertFalse(ctrl.has_active_game)
            self.assertFalse(legacy_path.exists())
            self.assertEqual(list(saves_dir.glob("*.db")), [])
            self.assertIs(win.root_stack.currentWidget(), win.start_screen)
            self.assertTrue(win.start_screen.continue_card.isHidden())
            self.assertEqual(win.start_screen.saves_table.rowCount(), 0)

            # Crea la prima carriera dallo schermo di partenza
            win.start_screen.name_input.setText("Atletica Test")
            win.start_screen.mode_combo.setCurrentIndex(0)  # career
            win.start_screen._on_start_new()
            self.assertTrue(ctrl.has_active_game)
            self.assertEqual(ctrl.state.team_name, "Atletica Test")
            self.assertEqual(ctrl.state.game_mode, "career")
            self.assertIs(win.root_stack.currentWidget(), win.game_page)

            # Ritorna al menu: vede lo slot e la card Continua
            win.show_start_screen()
            self.assertFalse(win.start_screen.continue_card.isHidden())
            self.assertEqual(win.start_screen.cont_club.text(), "Atletica Test")
            self.assertEqual(win.start_screen.saves_table.rowCount(), 1)

            # Crea una seconda partita senza sovrascrivere la prima
            win.start_screen.name_input.setText("Atletica Roma")
            win.start_screen.mode_combo.setCurrentIndex(1)  # vertical_slice
            win.start_screen._on_start_new()
            self.assertEqual(ctrl.state.team_name, "Atletica Roma")

            win.show_start_screen()
            self.assertEqual(win.start_screen.saves_table.rowCount(), 2)

            # Carica il primo salvataggio ("Atletica Test")
            slots = ctrl.list_save_slots()
            target = next(s for s in slots if s.team_name == "Atletica Test")
            target_row = slots.index(target)
            win.start_screen.saves_table.selectRow(target_row)
            win.start_screen._on_load_selected()
            self.assertEqual(ctrl.state.team_name, "Atletica Test")
            self.assertIs(win.root_stack.currentWidget(), win.game_page)

            # Elimina uno slot direttamente via controller
            roma = next(s for s in ctrl.list_save_slots() if s.team_name == "Atletica Roma")
            self.assertTrue(ctrl.delete_save_slot(roma.path))
            win.show_start_screen()
            self.assertEqual(win.start_screen.saves_table.rowCount(), 1)

            # Compatibilità con vecchio savegame.db nella cartella principale
            legacy_db = DatabaseManager(db_path=legacy_path)
            legacy_ctrl = GameController(db_manager=legacy_db, rng=random.Random(7))
            legacy_ctrl.start_new_game(team_name="Legacy Club", game_mode="vertical_slice")
            win.show_start_screen()
            names = {s.team_name for s in ctrl.list_save_slots()}
            self.assertEqual(names, {"Atletica Test", "Legacy Club"})
            win.close()

    def test_sidebar_navigation_action_center_and_roster_filters(self) -> None:
        from views.main_window import MainWindow

        with tempfile.TemporaryDirectory() as tmpdir:
            db = DatabaseManager(db_path=Path(tmpdir) / "ux.db")
            ctrl = GameController(db_manager=db, rng=random.Random(15))
            win = MainWindow(controller=ctrl)

            # Navigazione sidebar <-> stack
            self.assertEqual(win.tabs.currentIndex(), 0)
            win._nav_buttons[3].click()
            self.assertEqual(win.tabs.currentIndex(), 3)
            self.assertTrue(win._nav_buttons[3].isChecked())

            # Navigazione dal Centro Azioni della Dashboard
            win.dashboard_tab.navigate_requested.emit(7)
            self.assertEqual(win.tabs.currentIndex(), 7)
            self.assertTrue(win._nav_buttons[7].isChecked())

            # Filtri e ordinamento in Rosa
            total = len(ctrl.state.main_squad)
            self.assertEqual(win.roster_tab.table.rowCount(), total)
            win.roster_tab._set_gender_filter("F")
            f_count = sum(1 for a in ctrl.state.main_squad if a.gender == "F")
            self.assertEqual(win.roster_tab.table.rowCount(), f_count)
            win.roster_tab._set_gender_filter("ALL")
            self.assertEqual(win.roster_tab.table.rowCount(), total)

            win.roster_tab.search_input.setText(ctrl.state.main_squad[0].name.split()[0])
            self.assertGreaterEqual(win.roster_tab.table.rowCount(), 1)
            self.assertLessEqual(win.roster_tab.table.rowCount(), total)
            win.roster_tab.search_input.clear()

            # Ordinamento per OVR (col 4) mantiene allineati i cellWidget
            win.roster_tab._on_header_clicked(4)
            self.assertEqual(win.roster_tab.table.rowCount(), total)
            self.assertIsNotNone(win.roster_tab.table.cellWidget(0, 14))
            self.assertIsNotNone(win.roster_tab.table.cellWidget(0, 15))
            self.assertIsNotNone(win.roster_tab.table.cellWidget(0, 16))

            # Filtro M/F in Calendario & Gare
            self.assertEqual(win.calendar_tab.lineup_table.rowCount(), 6)
            win.calendar_tab._set_division_filter("M")
            self.assertEqual(win.calendar_tab.lineup_table.rowCount(), 3)
            win.calendar_tab._set_division_filter("ALL")
            self.assertEqual(win.calendar_tab.lineup_table.rowCount(), 6)

            win.close()

            # Pool settimanale persistente del Mercato Svincolati + confronto rosa (senza dialog modali connessi)
            from views.dialogs import RecruitAthleteDialog

            ctrl2 = GameController(db_manager=DatabaseManager(db_path=Path(tmpdir) / "pool.db"), rng=random.Random(15))
            pool1 = ctrl2.get_free_agent_market(count=5)
            pool2 = ctrl2.get_free_agent_market(count=5)
            self.assertEqual([a.name for a in pool1], [a.name for a in pool2])
            rec_dlg = RecruitAthleteDialog(pool1, ctrl2.state.budget, roster=ctrl2.state.main_squad)
            self.assertTrue(len(rec_dlg.compare_label.text()) > 0)
            rec_dlg.close()

            ctrl2.state.budget = 50000
            self.assertTrue(ctrl2.recruit_athlete(pool1[0]))
            pool3 = ctrl2.get_free_agent_market(count=5)
            self.assertNotIn(pool1[0].name, [a.name for a in pool3])

            ctrl2.advance_week()
            pool_next_week = ctrl2.get_free_agent_market(count=5)
            self.assertEqual(len(pool_next_week), 5)

            # Vista Albo & Record (indice 8)
            from models.entities import SeasonEndResult, SeasonOutcome

            win2 = MainWindow(controller=ctrl2)
            ctrl2.state.club_records["100m"] = (10.85, "10.85s", "Marco Verdi")
            ctrl2.state.club_records_f["100m"] = (11.95, "11.95s", "Giulia Neri")
            ctrl2.state.season_history.append(
                SeasonEndResult(
                    season=1,
                    tier=CompetitionTier.PROVINCIALE,
                    placement=1,
                    outcome=SeasonOutcome.PROMOTED,
                    final_table=[],
                    new_tier=CompetitionTier.REGIONALE,
                )
            )
            win2.dashboard_tab.navigate_requested.emit(8)
            self.assertEqual(win2.tabs.currentIndex(), 8)
            win2.records_tab.refresh(ctrl2.state)
            self.assertEqual(win2.records_tab.records_m_table.rowCount(), 1)
            self.assertEqual(win2.records_tab.records_f_table.rowCount(), 1)
            self.assertEqual(win2.records_tab.seasons_table.rowCount(), 1)
            win2.close()


if __name__ == "__main__":
    unittest.main()
