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
    PeriodizationPhase,
    RaceAttitude,
    Specialty,
    SeasonPhase,
    TrainingFocus,
    WeatherCondition,
)
from models.generator import generate_vertical_slice_roster
from models.simulation import advance_week, apply_weekly_training, weekly_finances


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
            # 3 events + 4x100m relay, each worth 8+7+...+1 = 36 points,
            # minus the 8th-place point nobody takes in the empty 1500m slot
            self.assertEqual(sum(p for _t, p in summary.team_standings), 4 * 36 - 1)
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
            from models.database import V3_COLUMNS, V4_COLUMNS

            conn = sqlite3.connect(path)
            try:
                for columns in (V3_COLUMNS, V4_COLUMNS):
                    for table, cols in columns.items():
                        for col, _def in cols:
                            conn.execute(f"ALTER TABLE {table} DROP COLUMN {col}")
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
            self.assertIn(reserve.name.split(" ", 1)[1], res.player_athlete_name)
            self.assertNotIn(injured.name.split(" ", 1)[1], res.player_athlete_name)
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
            self.assertEqual(win.tabs.count(), 7)
            self.assertEqual(win.roster_tab.table.rowCount(), 10)
            self.assertEqual(win.calendar_tab.lineup_table.rowCount(), 3)
            self.assertEqual(win.staff_tab.table.rowCount(), 3)
            self.assertEqual(win.staff_tab.coach_table.rowCount(), 3)
            self.assertEqual(len(win.relay_tab._slot_combos["4x100m"]), 5)
            self.assertTrue(win.relay_tab._slot_combos["4x100m"][0].isEnabled())
            self.assertFalse(win.relay_tab._slot_combos["4x400m"][0].isEnabled())  # no 400m in prototype

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

            win.close()


if __name__ == "__main__":
    unittest.main()
