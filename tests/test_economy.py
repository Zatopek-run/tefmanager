"""Lotto A.1: sostenibilità economica dell'avvio (sponsor +40%, premi +25%, rimborsi -45%, bonus promozione).

Misura una Carriera «in autopilota» (il giocatore non spende nulla: niente staff, palestra, ingaggi) su più seed.
I numeri attesi vengono dalla scansione del 2026-11-20 su 8 seed (12 sett.: da +4.727 a +15.349; 36 sett.: da +286 a +23.775);
le soglie qui sotto hanno margine. Se cambiano le cifre di bilanciamento, rifare la misura e aggiornare `docs/BALANCE.md`.

Serve PyQt6 (offscreen) solo perché la partita nuova si crea dal controller; la logica provata sta in `models/`.
"""

from __future__ import annotations

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
from models.entities import (
    PROMOTION_BONUS,
    WAGE_MAX,
    WAGE_MIN,
    SeasonOutcome,
    TIER_CONFIG,
    CompetitionTier,
)
from models.generator import senior_wage
from models.simulation import advance_week, close_season

_app = QApplication.instance() or QApplication([])

SEEDS = (1, 2, 3, 4, 5)
# Per la stagione intera i cinque semi non bastano: una partita su sei o sette chiude in deficit (AUDIT R21), e con
# cinque semi il test passava o falliva a seconda di come cadevano le estrazioni. Si guarda la distribuzione.
SEASON_SEEDS = tuple(range(1, 31))
SEASON_DEFICIT = -1000  # sotto questo saldo dopo 36 settimane la partita è «in deficit»
SEASON_DEFICIT_MAX_SHARE = 0.30  # quota massima di partite in deficit (misurato il 2026-11-20: 15% su 40 semi)


def _new_game(tmpdir: str, seed: int, mode: str) -> GameController:
    ctrl = GameController(
        db_manager=DatabaseManager(db_path=Path(tmpdir) / f"e{seed}.db"), rng=random.Random(seed), auto_create=False
    )
    ctrl.start_new_game(team_name="CUS Test", game_mode=mode)
    return ctrl


def _autopilot_runs(mode: str, weeks: int, seeds: tuple[int, ...] = SEEDS) -> list[tuple[int, bool]]:
    """(variazione del bilancio, fallita) dopo `weeks` settimane senza alcuna azione del giocatore, per ogni seed."""
    runs = []
    for seed in seeds:
        with tempfile.TemporaryDirectory() as tmpdir:
            ctrl = _new_game(tmpdir, seed, mode)
            start = ctrl.state.budget
            for _ in range(weeks):
                ctrl.dismiss_dilemma()
                advance_week(ctrl.state, rng=ctrl.rng)
            runs.append((ctrl.state.budget - start, ctrl.state.bankrupt))
    return runs


def _autopilot_deltas(mode: str, weeks: int, seeds: tuple[int, ...] = SEEDS) -> list[int]:
    """Variazione del bilancio dopo `weeks` settimane senza alcuna azione del giocatore, per ogni seed."""
    return [delta for delta, _bankrupt in _autopilot_runs(mode, weeks, seeds)]


class TestStartingEconomy(unittest.TestCase):
    def test_career_is_not_losing_money_after_12_weeks(self) -> None:
        deltas = _autopilot_deltas("career", 12)
        self.assertGreaterEqual(min(deltas), 0, f"Carriera in perdita dopo 12 settimane: {deltas}")

    def test_career_season_is_sustainable_in_most_games_and_never_bankrupt(self) -> None:
        """Sulla distribuzione di 30 partite in autopilota: la mediana chiude in attivo, poche vanno in deficit e
        nessuna arriva al fallimento; l'economia non è una macchina per soldi."""
        runs = _autopilot_runs("career", 36, SEASON_SEEDS)
        deltas = [delta for delta, _bankrupt in runs]
        ordered = sorted(deltas)
        median = ordered[len(ordered) // 2]
        in_deficit = sum(1 for d in deltas if d < SEASON_DEFICIT)
        self.assertGreater(median, 0, f"la mediana chiude in perdita: {ordered}")
        self.assertLessEqual(
            in_deficit / len(deltas), SEASON_DEFICIT_MAX_SHARE, f"troppe partite in deficit ({in_deficit}): {ordered}"
        )
        self.assertFalse(any(bankrupt for _delta, bankrupt in runs), f"una partita arriva al fallimento: {ordered}")
        self.assertLessEqual(sum(deltas) / len(deltas), 40_000, f"economia troppo generosa: {ordered}")

    def test_prototype_is_sustainable_over_its_two_meets(self) -> None:
        deltas = _autopilot_deltas("vertical_slice", 8)
        self.assertGreaterEqual(min(deltas), 0, f"Prototipo in perdita dopo 8 settimane: {deltas}")

    def test_weekly_flow_is_much_closer_to_zero_than_before(self) -> None:
        """Prima delle cifre nuove il flusso strutturale della Carriera era -4.497 €/sett. (R3)."""
        from models.simulation import weekly_finances

        with tempfile.TemporaryDirectory() as tmpdir:
            net = weekly_finances(_new_game(tmpdir, 1, "career").state)["net"]
        self.assertGreater(net, -2500)
        self.assertLess(net, 0, "i rimborsi non devono azzerare da soli i costi: restano le gare a pareggiare")


class TestWageFormula(unittest.TestCase):
    def test_starting_wages_are_within_bounds_and_lower_than_the_old_formula(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            squad = _new_game(tmpdir, 3, "career").state.main_squad
        self.assertTrue(squad)
        for a in squad:
            self.assertGreaterEqual(a.weekly_wage, WAGE_MIN)
            self.assertLessEqual(a.weekly_wage, WAGE_MAX)
            old = max(95, min(950, round((80 if a.is_youth_prospect else 100) + a.overall * 4.2)))
            self.assertLess(a.weekly_wage, old)
            self.assertEqual(a.weekly_wage, senior_wage(a))

    def test_wage_grows_with_overall(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            a = _new_game(tmpdir, 3, "career").state.main_squad[0]
        low = senior_wage(a)
        a.speed = a.stamina = a.strength = a.technique = 95
        self.assertGreater(senior_wage(a), low)


class TestTierConfig(unittest.TestCase):
    def test_sponsors_and_prizes_grow_with_the_tier(self) -> None:
        tiers = [CompetitionTier.PROVINCIALE, CompetitionTier.REGIONALE, CompetitionTier.NAZIONALE, CompetitionTier.INTERNAZIONALE]
        for key in ("weekly_sponsor", "prize_base"):
            values = [TIER_CONFIG[t][key] for t in tiers]
            self.assertEqual(values, sorted(values))
        self.assertEqual(TIER_CONFIG[CompetitionTier.PROVINCIALE]["weekly_sponsor"], 840)
        self.assertEqual(TIER_CONFIG[CompetitionTier.PROVINCIALE]["prize_base"], 1500)


class TestPromotionBonus(unittest.TestCase):
    @staticmethod
    def _force_position(state, position: int) -> None:
        names = [c.name for c in state.rivals_in()]
        table, points = {}, 1000
        for pos in range(1, len(names) + 2):
            team = state.team_name if pos == position else names.pop(0)
            table[team] = points
            points -= 100
        state.league_table = table

    def _close(self, position: int):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _new_game(tmpdir, 1, "career").state
        state.week = 37  # la stagione è appena finita
        self._force_position(state, position)
        before, n_tx = state.budget, len(state.transactions)
        result = close_season(state)
        return state, result, state.budget - before, len(state.transactions) - n_tx

    def test_promotion_pays_the_bonus_once_and_records_it(self) -> None:
        state, result, delta, new_tx = self._close(2)
        self.assertEqual(result.outcome, SeasonOutcome.PROMOTED)
        self.assertEqual(delta, PROMOTION_BONUS)
        self.assertEqual(new_tx, 1)
        self.assertEqual(state.transactions[0].amount, PROMOTION_BONUS)
        self.assertEqual(state.transactions[0].week, 36)
        self.assertIn("Bonus promozione", state.news_log[0])

    def test_no_bonus_when_staying_or_relegated(self) -> None:
        for position in (4, 8):
            _state, result, delta, new_tx = self._close(position)
            self.assertNotEqual(result.outcome, SeasonOutcome.PROMOTED)
            self.assertEqual((delta, new_tx), (0, 0), f"posizione {position}")


if __name__ == "__main__":
    unittest.main()
