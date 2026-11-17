"""Unit and integration tests for Track & Field Manager (v2 Vertical Slice & Career)."""

from __future__ import annotations

import copy
import os
import random
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

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

    def _athlete(self, specialty, height, weight):
        from models.generator import generate_athlete

        a = generate_athlete(specialty=specialty, rng=random.Random(5))
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
            self.assertEqual(len(ctrl.state.athletes), 8)
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
            # 3 events + 4x100m relay, each worth 8+7+...+1 = 36 points, minus the
            # 8th-place point nobody takes in the empty 1500m slot and for each withdrawal/DQ
            dropped = sum(1 for er in summary.event_results if er.withdrew_injured or er.disqualified)
            self.assertEqual(sum(p for _t, p in summary.team_standings), 4 * 36 - 1 - dropped)
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

            outsider = generate_athlete(specialty=Specialty.SPRINTS, rng=random.Random(1))
            outsider.id = 99
            s.athletes.append(outsider)  # all 8 career athletes are already in a relay
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
            # stronger categories have stronger clubs
            prov = sum(c.level() for c in s.rivals_in(CompetitionTier.PROVINCIALE))
            naz = sum(c.level() for c in s.rivals_in(CompetitionTier.NAZIONALE))
            self.assertGreater(naz, prov)

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
                expected = {c.athletes[er.event_name].name for c in s.rivals_in()}
                rivals = {st.athlete_name for st in er.standings if not st.is_player}
                self.assertEqual(rivals, expected)
            lj = next(er for er in summary.event_results if er.event_name == "Salto in Lungo")
            if not lj.wind_illegal:
                self.assertTrue(all(c.athletes["Salto in Lungo"].pb is not None for c in s.rivals_in()))

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
            self.assertEqual(win.tabs.count(), 8)
            self.assertEqual(win.rivals_tab.clubs_table.rowCount(), 7)
            self.assertEqual(win.rivals_tab.compare_table.rowCount(), 3)
            self.assertEqual(win.rivals_tab.roster_table.rowCount(), 3)
            self.assertEqual(win.roster_tab.table.rowCount(), 10)
            self.assertEqual(win.calendar_tab.lineup_table.rowCount(), 3)
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
            self.assertEqual(comp_dlg.events_table.rowCount(), 4)  # 3 events + 4x100m relay
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


if __name__ == "__main__":
    unittest.main()
