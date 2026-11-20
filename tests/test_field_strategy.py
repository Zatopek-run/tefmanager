"""Lotto B.2: rischio nei concorsi (lungo e peso): bonus di tecnica contro probabilità di tentativo nullo.

Senza Qt (`PYTHONPATH=. python3 -m unittest tests.test_field_strategy`). Il modello non simula i singoli tentativi: un nullo
fa perdere la quota `FIELD_FOUL_LOSS` della misura (si ripiega sul secondo tentativo). I test fissano la struttura
(monotonia, una sola estrazione RNG solo se il rischio non è «Sicuro», salvataggio), non il bilanciamento.
"""

from __future__ import annotations

import random
import tempfile
import unittest
from pathlib import Path

from models.database import DatabaseManager
from models.entities import (
    EVENTS,
    FIELD_FOUL_LOSS,
    FIELD_RISK_EFFECTS,
    FIELD_STRATEGY_EVENTS,
    FieldRisk,
)
from models.simulation import field_risk_effect, field_risk_label, simulate_competition
from tests.test_assignments import make_state

LONG, SHOT = EVENTS["Salto in Lungo"], EVENTS["Getto del Peso"]


class TestRiskEffect(unittest.TestCase):
    def test_safe_has_no_effect(self) -> None:
        for event in (LONG, SHOT):
            self.assertEqual(field_risk_effect(event, FieldRisk.SICURO), (0.0, 0.0))

    def test_plan_figures_balanced_and_aggressive(self) -> None:
        """+1 / +3 punti di tecnica con 5% / 15% di nullo (piano B.2); i punti valgono il peso della tecnica nell'evento."""
        for event in (LONG, SHOT):
            weight = event.weights["technique"]
            self.assertAlmostEqual(field_risk_effect(event, FieldRisk.BILANCIATO)[0], 1 * weight)
            self.assertAlmostEqual(field_risk_effect(event, FieldRisk.AGGRESSIVO)[0], 3 * weight)
            self.assertEqual(field_risk_effect(event, FieldRisk.BILANCIATO)[1], 0.05)
            self.assertEqual(field_risk_effect(event, FieldRisk.AGGRESSIVO)[1], 0.15)

    def test_more_risk_means_more_score_and_more_fouls(self) -> None:
        effects = [field_risk_effect(LONG, r) for r in (FieldRisk.SICURO, FieldRisk.BILANCIATO, FieldRisk.AGGRESSIVO)]
        self.assertEqual(sorted(effects), effects)
        self.assertEqual(len({e[0] for e in effects}), 3)
        self.assertEqual(len({e[1] for e in effects}), 3)

    def test_foul_loss_is_a_small_fraction(self) -> None:
        self.assertGreater(FIELD_FOUL_LOSS, 0)
        self.assertLess(FIELD_FOUL_LOSS, 0.10)

    def test_label(self) -> None:
        self.assertEqual(field_risk_label(FieldRisk.SICURO), "")
        self.assertEqual(field_risk_label(FieldRisk.AGGRESSIVO), "Rischio Aggressivo")
        self.assertIn("nullo", field_risk_label(FieldRisk.BILANCIATO, fouled=True))

    def test_field_events_are_long_jump_and_shot_put(self) -> None:
        self.assertEqual(set(FIELD_STRATEGY_EVENTS), {"Salto in Lungo", "Getto del Peso"})
        self.assertEqual(set(FIELD_RISK_EFFECTS), set(FieldRisk))


def _meet_state(seed: int = 3):
    state = make_state(seed)
    state.week = 4
    return state


def _player(summary, event: str, gender: str = "M"):
    result = next(r for r in summary.event_results if r.event_name == event and r.gender == gender)
    standing = next(s for s in result.standings if s.is_player)
    return result, standing


class TestRiskInSimulation(unittest.TestCase):
    def run_meet(self, risk: FieldRisk, event: str = "Salto in Lungo", seed: int = 11):
        state = _meet_state()
        state.race_strategy[event] = {"risk": risk.value}
        return simulate_competition(state, rng=random.Random(seed))

    def test_safe_is_identical_to_no_strategy(self) -> None:
        plain = simulate_competition(_meet_state(), rng=random.Random(11))
        safe = self.run_meet(FieldRisk.SICURO)
        self.assertEqual([r.player_mark for r in plain.event_results], [r.player_mark for r in safe.event_results])
        self.assertEqual([r.attitude for r in plain.event_results], [r.attitude for r in safe.event_results])

    def test_the_risk_draw_is_the_only_extra_rng_call(self) -> None:
        """Se il nullo non può capitare (probabilità 0) non si estrae nulla: tutti gli avversari, in ogni gara, restano identici."""
        from unittest import mock

        for event in FIELD_STRATEGY_EVENTS:
            base = self.run_meet(FieldRisk.SICURO, event)
            with mock.patch.dict("models.simulation.FIELD_RISK_EFFECTS", {FieldRisk.AGGRESSIVO: (3, 0.0)}):
                risky = self.run_meet(FieldRisk.AGGRESSIVO, event)
            rivals = lambda s: [
                (r.event_name, r.gender, st.athlete_name, st.mark_value)
                for r in s.event_results
                for st in r.standings
                if not st.is_player
            ]
            self.assertTrue(rivals(base))
            self.assertEqual(rivals(risky), rivals(base), event)

    def test_without_a_foul_the_player_gains_the_technique_bonus(self) -> None:
        """Con una probabilità di nullo nulla (forzata) il rischio dà solo il bonus: misura migliore."""
        from unittest import mock

        base = self.run_meet(FieldRisk.SICURO)
        with mock.patch.dict("models.simulation.FIELD_RISK_EFFECTS", {FieldRisk.AGGRESSIVO: (3, 0.0)}):
            risky = self.run_meet(FieldRisk.AGGRESSIVO)
        self.assertGreater(_player(risky, "Salto in Lungo")[1].mark_value, _player(base, "Salto in Lungo")[1].mark_value)

    def test_certain_foul_costs_the_fixed_share_and_is_shown(self) -> None:
        from unittest import mock

        with mock.patch.dict("models.simulation.FIELD_RISK_EFFECTS", {FieldRisk.AGGRESSIVO: (0, 1.0)}):
            fouled = self.run_meet(FieldRisk.AGGRESSIVO)
        base = self.run_meet(FieldRisk.SICURO)
        result, standing = _player(fouled, "Salto in Lungo")
        _res, base_standing = _player(base, "Salto in Lungo")
        self.assertAlmostEqual(standing.mark_value, base_standing.mark_value * (1 - FIELD_FOUL_LOSS), places=6)
        self.assertEqual(standing.mark_display, f"{standing.mark_value:.2f}m")
        self.assertIn("tentativo nullo", result.attitude)

    def test_risk_is_ignored_by_other_events(self) -> None:
        state = _meet_state()
        state.race_strategy["100m"] = {"risk": "Aggressivo"}
        a = simulate_competition(state, rng=random.Random(11))
        b = simulate_competition(_meet_state(), rng=random.Random(11))
        self.assertEqual([r.player_mark for r in a.event_results], [r.player_mark for r in b.event_results])

    def test_deterministic_with_the_same_seed(self) -> None:
        a = _player(self.run_meet(FieldRisk.AGGRESSIVO), "Getto del Peso")[1].mark_value
        b = _player(self.run_meet(FieldRisk.AGGRESSIVO), "Getto del Peso")[1].mark_value
        self.assertEqual(a, b)

    def test_fouls_happen_at_about_the_stated_rate(self) -> None:
        fouls = sum(
            "tentativo nullo" in _player(self.run_meet(FieldRisk.AGGRESSIVO, seed=s), "Salto in Lungo")[0].attitude
            for s in range(200)
        )
        self.assertGreater(fouls, 200 * 0.15 * 0.5)
        self.assertLess(fouls, 200 * 0.15 * 1.6)


class TestRiskState(unittest.TestCase):
    def test_default_and_unknown_values_are_safe(self) -> None:
        state = make_state(3)
        self.assertEqual(state.risk_for("Salto in Lungo"), FieldRisk.SICURO)
        state.race_strategy["Salto in Lungo"] = {"risk": "Boh"}
        self.assertEqual(state.risk_for("Salto in Lungo"), FieldRisk.SICURO)
        state.race_strategy["Getto del Peso"] = {"pace": "Veloce"}  # chiavi di un altro tipo di piano
        self.assertEqual(state.risk_for("Getto del Peso"), FieldRisk.SICURO)

    def test_risk_roundtrips_through_the_database_without_a_new_schema_version(self) -> None:
        state = make_state(3)
        state.race_strategy = {"Salto in Lungo": {"risk": "Aggressivo"}, "1500m": {"pace": "Lento", "kick": "Nessuno"}}
        with tempfile.TemporaryDirectory() as tmp:
            db = DatabaseManager(db_path=Path(tmp) / "r.db")
            db.save_game(state)
            loaded = db.load_game()
        self.assertEqual(loaded.race_strategy, state.race_strategy)
        self.assertEqual(loaded.risk_for("Salto in Lungo"), FieldRisk.AGGRESSIVO)
        self.assertEqual(loaded.risk_for("Getto del Peso"), FieldRisk.SICURO)


if __name__ == "__main__":
    unittest.main()
