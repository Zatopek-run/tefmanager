"""Lotto B.3: cambio nelle staffette (Conservativo / Normale / Aggressivo).

Senza Qt (`PYTHONPATH=. python3 -m unittest tests.test_relay_strategy`). Le cifre sono quelle misurate e confermate il
2026-11-20 (`entities.py`, `BALANCE.md` sezione D): punti di squadra −1 / 0 / +2 e rischio di squalifica −10 / 0 / +10 punti
percentuali, sommati al rischio finale (dopo il ×0,5 della 4x400m) e limitati tra 0 e 1. I test fissano la struttura
(formula, nessuna estrazione RNG in più, salvataggio), non il bilanciamento: quello sta nelle misure di Q25.
"""

from __future__ import annotations

import random
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from models.database import DatabaseManager
from models.entities import (
    RELAY_CHANGE_EFFECTS,
    RELAY_DQ_MARK,
    RELAY_DQ_MULT,
    RELAY_STRATEGY_EVENTS,
    RELAYS,
    RelayChange,
)
from models.simulation import _relay_dq_chance, relay_change_label, simulate_competition
from tests.test_assignments import make_state

CONS, NORM, AGGR = RelayChange.CONSERVATIVO, RelayChange.NORMALE, RelayChange.AGGRESSIVO


def _old_formula(harmony: int, substituted: bool, relay_name: str) -> float:
    """La probabilità di squalifica prima di B.3 (Q20), riscritta qui per provare che «Normale» non la cambia."""
    base = max(0.0, (60 - harmony) * 0.006) + (0.03 if substituted else 0.0)
    return base * RELAY_DQ_MULT.get(relay_name, 1.0)


class TestChangeFigures(unittest.TestCase):
    def test_confirmed_figures(self) -> None:
        self.assertEqual(RELAY_CHANGE_EFFECTS[CONS], (-1.0, -0.10))
        self.assertEqual(RELAY_CHANGE_EFFECTS[NORM], (0.0, 0.0))
        self.assertEqual(RELAY_CHANGE_EFFECTS[AGGR], (2.0, 0.10))

    def test_every_choice_has_figures_and_events_are_the_relays(self) -> None:
        self.assertEqual(set(RELAY_CHANGE_EFFECTS), set(RelayChange))
        self.assertEqual(set(RELAY_STRATEGY_EVENTS), set(RELAYS))
        self.assertEqual(set(RELAY_STRATEGY_EVENTS), {"4x100m", "4x400m"})

    def test_more_aggressive_means_more_points_and_more_risk(self) -> None:
        effects = [RELAY_CHANGE_EFFECTS[c] for c in (CONS, NORM, AGGR)]
        self.assertEqual(sorted(effects), effects)
        self.assertEqual(len({e[0] for e in effects}), 3)
        self.assertEqual(len({e[1] for e in effects}), 3)

    def test_label(self) -> None:
        self.assertEqual(relay_change_label(NORM), "")
        self.assertEqual(relay_change_label(AGGR), "Cambio Aggressivo")
        self.assertEqual(relay_change_label(CONS), "Cambio Conservativo")


class TestDisqualificationChance(unittest.TestCase):
    def test_normal_is_the_old_formula_everywhere(self) -> None:
        for relay_name in RELAYS:
            for harmony in (-20, 0, 20, 45, 59, 60, 61, 90, 100):
                for substituted in (False, True):
                    expected = _old_formula(harmony, substituted, relay_name)
                    self.assertAlmostEqual(_relay_dq_chance(harmony, substituted, relay_name, NORM), expected)
                    # senza il quarto argomento (chiamate di prima di B.3) il valore è lo stesso
                    self.assertAlmostEqual(_relay_dq_chance(harmony, substituted, relay_name), expected)

    def test_aggressive_adds_ten_points_after_the_relay_multiplier(self) -> None:
        # 4x100m, affiatamento 20: base 0,24; 4x400m: 0,24 × 0,5 = 0,12 e poi + 0,10 (non 0,24 + 0,10 poi × 0,5)
        self.assertAlmostEqual(_relay_dq_chance(20, False, "4x100m", AGGR), 0.34)
        self.assertAlmostEqual(_relay_dq_chance(20, False, "4x400m", AGGR), 0.22)
        # con rischio di base zero, «Aggressivo» ha comunque un costo
        self.assertAlmostEqual(_relay_dq_chance(90, False, "4x100m", AGGR), 0.10)
        self.assertAlmostEqual(_relay_dq_chance(90, False, "4x400m", AGGR), 0.10)

    def test_conservative_subtracts_ten_points_and_never_goes_below_zero(self) -> None:
        self.assertAlmostEqual(_relay_dq_chance(20, False, "4x100m", CONS), 0.14)
        self.assertAlmostEqual(_relay_dq_chance(20, False, "4x400m", CONS), 0.02)
        self.assertEqual(_relay_dq_chance(60, False, "4x100m", CONS), 0.0)
        self.assertEqual(_relay_dq_chance(90, True, "4x400m", CONS), 0.0)

    def test_chance_stays_between_zero_and_one(self) -> None:
        self.assertEqual(_relay_dq_chance(-200, True, "4x100m", AGGR), 1.0)
        for relay_name in RELAYS:
            for change in RelayChange:
                for harmony in range(-50, 151, 5):
                    chance = _relay_dq_chance(harmony, False, relay_name, change)
                    self.assertTrue(0.0 <= chance <= 1.0, (relay_name, change, harmony, chance))

    def test_order_conservative_normal_aggressive(self) -> None:
        for relay_name in RELAYS:
            for harmony in (0, 20, 40, 60, 90):
                c, n, a = (_relay_dq_chance(harmony, False, relay_name, ch) for ch in (CONS, NORM, AGGR))
                self.assertLessEqual(c, n)
                self.assertLess(n, a)


def _meet_state(harmony: int = 100):
    """Stato in settimana di gara con tutte le staffette (M e F) complete e l'affiatamento fissato."""
    state = make_state(3)
    state.week = 4
    for gender in ("M", "F"):
        for relay in state.relays_for(gender).values():
            relay.harmony = harmony
    return state


def _relay_results(summary):
    return [r for r in summary.event_results if r.event_name in RELAYS]


def _player(result):
    return next(s for s in result.standings if s.is_player)


def _rivals(summary):
    return [
        (r.event_name, r.gender, s.athlete_name, s.mark_value)
        for r in _relay_results(summary)
        for s in r.standings
        if not s.is_player
    ]


class TestChangeInSimulation(unittest.TestCase):
    def run_meet(self, change: RelayChange | None, harmony: int = 100, seed: int = 11, only: str | None = None):
        state = _meet_state(harmony)
        if change is not None:
            for name in ([only] if only else RELAYS):
                state.race_strategy[name] = {"change": change.value}
        return simulate_competition(state, rng=random.Random(seed))

    def test_the_fixture_has_relay_results_for_both_relays_and_both_categories(self) -> None:
        """Il roster di prova non riesce a comporre la 4x100m femminile (poche atlete): i risultati sono 3, non 4."""
        results = _relay_results(self.run_meet(None))
        self.assertGreaterEqual(len(results), 3)
        self.assertEqual({r.event_name for r in results}, set(RELAYS))
        self.assertEqual({r.gender for r in results}, {"M", "F"})

    def test_normal_is_identical_to_no_choice(self) -> None:
        plain = self.run_meet(None, harmony=30)
        normal = self.run_meet(NORM, harmony=30)
        self.assertEqual([r.player_mark for r in plain.event_results], [r.player_mark for r in normal.event_results])
        self.assertEqual([r.attitude for r in plain.event_results], [r.attitude for r in normal.event_results])
        self.assertEqual(_rivals(plain), _rivals(normal))

    def test_individual_events_do_not_depend_on_the_relay_choice(self) -> None:
        plain = self.run_meet(None, harmony=30)
        for change in (CONS, AGGR):
            other = self.run_meet(change, harmony=30)
            individual = lambda s: [(r.event_name, r.gender, r.player_mark) for r in s.event_results if r.event_name not in RELAYS]
            self.assertTrue(individual(plain))
            self.assertEqual(individual(other), individual(plain), change)

    def test_score_bonus_is_the_only_effect_when_the_risk_does_not_change(self) -> None:
        """Con la variazione di rischio azzerata (forzata) «Aggressivo» dà solo +2 punti: stessa sequenza RNG, avversari
        identici, tempo della squadra migliore in ogni staffetta."""
        base = self.run_meet(NORM)
        with mock.patch.dict("models.simulation.RELAY_CHANGE_EFFECTS", {AGGR: (2.0, 0.0)}):
            risky = self.run_meet(AGGR)
        self.assertEqual(_rivals(risky), _rivals(base))
        for b, r in zip(_relay_results(base), _relay_results(risky)):
            self.assertLess(_player(r).mark_value, _player(b).mark_value, (b.event_name, b.gender))

    def test_conservative_score_malus_when_the_risk_does_not_change(self) -> None:
        base = self.run_meet(NORM)
        with mock.patch.dict("models.simulation.RELAY_CHANGE_EFFECTS", {CONS: (-1.0, 0.0)}):
            careful = self.run_meet(CONS)
        self.assertEqual(_rivals(careful), _rivals(base))
        for b, c in zip(_relay_results(base), _relay_results(careful)):
            self.assertGreater(_player(c).mark_value, _player(b).mark_value, (b.event_name, b.gender))

    def test_the_bonus_is_two_points_of_team_score(self) -> None:
        """+2 punti di punteggio = 0,02 di `norm` = 0,02 × `span_seconds` di tempo (nessun limite raggiunto a questo livello)."""
        base = self.run_meet(NORM)
        with mock.patch.dict("models.simulation.RELAY_CHANGE_EFFECTS", {AGGR: (2.0, 0.0)}):
            risky = self.run_meet(AGGR)
        for b, r in zip(_relay_results(base), _relay_results(risky)):
            rdef = RELAYS[b.event_name]
            span = rdef.span_seconds_f if b.gender == "F" else rdef.span_seconds
            self.assertAlmostEqual(_player(b).mark_value - _player(r).mark_value, 0.02 * span, places=6)

    def test_certain_risk_disqualifies_both_categories_and_shows_the_choice(self) -> None:
        with mock.patch.dict("models.simulation.RELAY_CHANGE_EFFECTS", {AGGR: (2.0, 1.0)}):
            summary = self.run_meet(AGGR)
        results = _relay_results(summary)
        self.assertEqual(len(results), len(_relay_results(self.run_meet(None))))  # tutte le squadre complete
        self.assertEqual({r.gender for r in results}, {"M", "F"})
        for result in results:
            self.assertTrue(result.disqualified)
            self.assertEqual(result.player_mark, RELAY_DQ_MARK)
            self.assertIn("Cambio Aggressivo", result.attitude)

    def test_conservative_with_certain_cut_never_disqualifies(self) -> None:
        """Affiatamento 0 (rischio base alto) e riduzione totale: nessuna squalifica, per più semi."""
        with mock.patch.dict("models.simulation.RELAY_CHANGE_EFFECTS", {CONS: (-1.0, -1.0)}):
            for seed in range(8):
                for result in _relay_results(self.run_meet(CONS, harmony=0, seed=seed)):
                    self.assertFalse(result.disqualified, (seed, result.event_name, result.gender))

    def test_choice_applies_only_to_the_chosen_relay(self) -> None:
        with mock.patch.dict("models.simulation.RELAY_CHANGE_EFFECTS", {AGGR: (2.0, 1.0)}):
            summary = self.run_meet(AGGR, only="4x100m")
        for result in _relay_results(summary):
            if result.event_name == "4x100m":
                self.assertTrue(result.disqualified)
            else:
                self.assertFalse(result.disqualified)
                self.assertNotIn("Cambio", result.attitude)

    def test_result_shows_the_choice_only_when_not_normal(self) -> None:
        for result in _relay_results(self.run_meet(NORM)):
            self.assertNotIn("·", result.attitude)
        for result in _relay_results(self.run_meet(CONS)):
            self.assertIn("Cambio Conservativo", result.attitude)

    def test_deterministic_with_the_same_seed(self) -> None:
        a = self.run_meet(AGGR, harmony=40, seed=5)
        b = self.run_meet(AGGR, harmony=40, seed=5)
        self.assertEqual([r.player_mark for r in a.event_results], [r.player_mark for r in b.event_results])


class TestChangeState(unittest.TestCase):
    def test_default_and_unknown_values_fall_back_to_normal(self) -> None:
        state = make_state(3)
        self.assertEqual(state.change_for("4x100m"), NORM)
        state.race_strategy["4x100m"] = {"change": "Boh"}
        self.assertEqual(state.change_for("4x100m"), NORM)
        state.race_strategy["4x100m"] = {"pace": "Veloce"}  # chiavi di un altro tipo di piano
        self.assertEqual(state.change_for("4x100m"), NORM)
        state.race_strategy["4x100m"] = {"change": "Aggressivo"}
        self.assertEqual(state.change_for("4x100m"), AGGR)
        self.assertEqual(state.change_for("4x400m"), NORM)

    def test_relay_choice_does_not_touch_the_other_plans(self) -> None:
        state = make_state(3)
        state.race_strategy = {"1500m": {"pace": "Lento", "kick": "Nessuno"}, "4x100m": {"change": "Conservativo"}}
        self.assertEqual(state.strategy_for("1500m")[0].value, "Lento")
        self.assertEqual(state.risk_for("Salto in Lungo").value, "Sicuro")
        self.assertEqual(state.change_for("4x100m"), CONS)

    def test_choice_roundtrips_through_the_database(self) -> None:
        state = make_state(3)
        state.race_strategy = {
            "800m": {"pace": "Lento", "kick": "Ultimi 200m"},
            "4x100m": {"change": "Aggressivo"},
            "4x400m": {"change": "Conservativo"},
        }
        with tempfile.TemporaryDirectory() as tmp:
            db = DatabaseManager(db_path=Path(tmp) / "s.db")
            db.save_game(state)
            loaded = db.load_game()
        self.assertEqual(loaded.race_strategy, state.race_strategy)
        self.assertEqual(loaded.change_for("4x100m"), AGGR)
        self.assertEqual(loaded.change_for("4x400m"), CONS)


if __name__ == "__main__":
    unittest.main()
