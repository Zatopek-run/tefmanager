"""Lotto B.1: piano gara di 800m e 1500m (ritmo iniziale + scatto finale) applicato dal modello.

Senza Qt (`PYTHONPATH=. python3 -m unittest tests.test_race_strategy`). Le cifre sono quelle confermate il 2026-11-20 (`entities.py`, `BALANCE.md`):
i test fissano la struttura (monotonia, simmetria, costo in fatica, nessuna chiamata in più all'RNG), non il bilanciamento.
"""

from __future__ import annotations

import copy
import random
import tempfile
import unittest
from pathlib import Path

from models.database import DatabaseManager
from models.entities import (
    KICK_EFFECTS,
    PACE_EFFECTS,
    STRATEGY_EVENTS,
    STRATEGY_STAMINA_REF,
    CompetitionTier,
    RaceKick,
    RacePace,
)
from models.simulation import (
    race_strategy_effect,
    simulate_competition,
    strategy_endurance_factor,
    strategy_label,
)
from tests.test_assignments import make_state

TIER = CompetitionTier.PROVINCIALE
STRONG = 99  # fattore 1 in ogni categoria
WEAK = 0  # fattore al minimo (crollo)


class TestStrategyEffect(unittest.TestCase):
    def test_neutral_plan_has_no_effect(self) -> None:
        for stamina in (WEAK, 50, STRONG):
            self.assertEqual(race_strategy_effect(stamina, TIER, RacePace.MEDIO, RaceKick.NESSUNO), (0.0, 0))

    def test_fast_start_plus_last_lap_gives_plan_points_and_fatigue_for_a_strong_runner(self) -> None:
        score, fatigue = race_strategy_effect(STRONG, TIER, RacePace.VELOCE, RaceKick.ULTIMO_GIRO)
        self.assertEqual(score, PACE_EFFECTS[RacePace.VELOCE][0] + KICK_EFFECTS[RaceKick.ULTIMO_GIRO][0])
        self.assertEqual(score, 7.0)  # +3 ritmo, +4 scatto: come nel piano
        self.assertEqual(fatigue, 10 + 15)  # il piano scrive «+23», ma le sue stesse cifre (10 + 15) danno 25

    def test_slow_pace_costs_score_and_saves_fatigue_for_a_strong_runner(self) -> None:
        score, fatigue = race_strategy_effect(STRONG, TIER, RacePace.LENTO, RaceKick.NESSUNO)
        self.assertEqual(score, -2.0)
        self.assertLess(fatigue, 0)

    def test_kicks_are_ordered_by_points_and_fatigue(self) -> None:
        effects = [race_strategy_effect(STRONG, TIER, RacePace.MEDIO, k) for k in (RaceKick.NESSUNO, RaceKick.ULTIMI_200, RaceKick.ULTIMO_GIRO)]
        self.assertEqual(sorted(effects), effects)

    def test_endurance_factor_is_monotonic_bounded_and_tier_relative(self) -> None:
        for tier in CompetitionTier:
            factors = [strategy_endurance_factor(s, tier) for s in range(0, 101)]
            self.assertEqual(factors, sorted(factors))
            self.assertEqual(max(factors), 1.0)
            self.assertLess(min(factors), 0)
            self.assertAlmostEqual(strategy_endurance_factor(STRATEGY_STAMINA_REF[tier], tier), 0.5)
        # lo stesso atleta «regge» meno il piano in una categoria più alta
        self.assertGreater(
            strategy_endurance_factor(60, CompetitionTier.PROVINCIALE), strategy_endurance_factor(60, CompetitionTier.NAZIONALE)
        )

    def test_without_stamina_the_fast_plan_backfires_and_slow_helps(self) -> None:
        fast, _ = race_strategy_effect(WEAK, TIER, RacePace.VELOCE, RaceKick.ULTIMO_GIRO)
        slow, _ = race_strategy_effect(WEAK, TIER, RacePace.LENTO, RaceKick.NESSUNO)
        self.assertLess(fast, 0)  # crollo
        self.assertGreater(slow, 0)

    def test_fatigue_does_not_depend_on_endurance(self) -> None:
        fatigues = {race_strategy_effect(s, TIER, RacePace.VELOCE, RaceKick.ULTIMO_GIRO)[1] for s in (WEAK, 50, STRONG)}
        self.assertEqual(len(fatigues), 1)

    def test_label(self) -> None:
        self.assertEqual(strategy_label(RacePace.MEDIO, RaceKick.NESSUNO), "")
        self.assertIn("Veloce", strategy_label(RacePace.VELOCE, RaceKick.ULTIMO_GIRO))


def _meet_state(seed: int = 3):
    """Stato in settimana di gara con un mezzofondista molto resistente convocato nei 1500m (M)."""
    state = make_state(seed)
    state.week = 4
    runner_id = state.lineup_for("M")["1500m"]
    runner = next(a for a in state.athletes if a.id == runner_id)
    runner.stamina = STRONG
    runner.fatigue = 20
    return state, runner


class TestStrategyInSimulation(unittest.TestCase):
    def run_meet(self, pace: RacePace, kick: RaceKick, event: str = "1500m"):
        state, runner = _meet_state()
        state.race_strategy[event] = {"pace": pace.value, "kick": kick.value}
        summary = simulate_competition(state, rng=random.Random(11))
        result = next(r for r in summary.event_results if r.event_name == event and r.gender == "M")
        return state, runner, summary, result

    def test_strategy_changes_mark_and_fatigue_but_not_the_rng_sequence(self) -> None:
        base_state, base_runner, base_summary, base = self.run_meet(RacePace.MEDIO, RaceKick.NESSUNO)
        state, runner, summary, res = self.run_meet(RacePace.VELOCE, RaceKick.ULTIMO_GIRO)
        player_mark = lambda r: next(s.mark_value for s in r.standings if s.is_player)
        self.assertLess(player_mark(res), player_mark(base))  # 1500m: tempo più basso = meglio
        self.assertEqual(runner.fatigue - base_runner.fatigue, 25)
        # stesse estrazioni: gli avversari fanno gli stessi tempi
        rivals = lambda r: [(s.athlete_name, s.mark_value) for s in r.standings if not s.is_player]
        self.assertEqual(rivals(res), rivals(base))
        # e le altre gare individuali restano identiche (le staffette no: la fatica del 1500m può toccare chi ci corre)
        other = lambda s: [
            (r.event_name, r.gender, r.player_mark)
            for r in s.event_results
            if "x" not in r.event_name and not (r.event_name == "1500m" and r.gender == "M")
        ]
        self.assertEqual(other(summary), other(base_summary))

    def test_other_events_ignore_the_strategy(self) -> None:
        state, _ = _meet_state()
        state.race_strategy["100m"] = {"pace": "Veloce", "kick": "Ultimo giro"}
        plain, _ = _meet_state()
        a = simulate_competition(state, rng=random.Random(11))
        b = simulate_competition(plain, rng=random.Random(11))
        self.assertEqual([r.player_mark for r in a.event_results], [r.player_mark for r in b.event_results])

    def test_result_shows_the_plan_only_when_not_neutral(self) -> None:
        _s, _r, _sum, plain = self.run_meet(RacePace.MEDIO, RaceKick.NESSUNO)
        self.assertNotIn("·", plain.attitude)
        _s, _r, _sum, planned = self.run_meet(RacePace.VELOCE, RaceKick.ULTIMI_200)
        self.assertIn("Ritmo Veloce", planned.attitude)
        self.assertIn("Ultimi 200m", planned.attitude)

    def test_deterministic_with_the_same_seed(self) -> None:
        a = self.run_meet(RacePace.VELOCE, RaceKick.ULTIMI_200)[3]
        b = self.run_meet(RacePace.VELOCE, RaceKick.ULTIMI_200)[3]
        self.assertEqual(a.player_mark, b.player_mark)


class TestStrategyState(unittest.TestCase):
    def test_default_and_unknown_values_fall_back_to_neutral(self) -> None:
        state = make_state(3)
        self.assertEqual(state.strategy_for("800m"), (RacePace.MEDIO, RaceKick.NESSUNO))
        state.race_strategy["800m"] = {"pace": "Boh", "kick": "Mah"}
        self.assertEqual(state.strategy_for("800m"), (RacePace.MEDIO, RaceKick.NESSUNO))
        state.race_strategy["800m"] = {"pace": "Veloce"}
        self.assertEqual(state.strategy_for("800m"), (RacePace.VELOCE, RaceKick.NESSUNO))

    def test_strategy_events_are_the_middle_distance_events(self) -> None:
        self.assertEqual(set(STRATEGY_EVENTS), {"800m", "1500m"})

    def test_strategy_roundtrips_through_the_database(self) -> None:
        state = make_state(3)
        state.race_strategy = {"800m": {"pace": "Lento", "kick": "Ultimi 200m"}, "1500m": {"pace": "Veloce", "kick": "Ultimo giro"}}
        with tempfile.TemporaryDirectory() as tmp:
            db = DatabaseManager(db_path=Path(tmp) / "s.db")
            db.save_game(state)
            loaded = db.load_game()
        self.assertEqual(loaded.race_strategy, state.race_strategy)
        self.assertEqual(loaded.strategy_for("800m"), (RacePace.LENTO, RaceKick.ULTIMI_200))


if __name__ == "__main__":
    unittest.main()
