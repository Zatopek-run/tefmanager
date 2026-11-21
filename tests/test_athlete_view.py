"""Dati della scheda atleta (PIANOLAVORO G.2): radar, potenziale, condizione, storico gare, confronto. Senza Qt.

Garanzie: (1) i livelli seguono le soglie 80/65/45 e la fatica si legge al contrario; (2) il radar ha i 5 assi del piano con la media dei compagni
di disciplina; (3) la barra del potenziale è OVR/potenziale; (4) lo storico gare è l'ultimo `HISTORY_RESULTS` e il percentile è confrontabile;
(5) il confronto mette l'atleta nella classifica della sua disciplina anche se fuori dai primi; (6) solo dati semplici, nessuna scrittura.
"""

from __future__ import annotations

import json
import random
import unittest

from models.athlete_view import COMPARISON_ROWS, athlete_snapshot, empty_athlete_snapshot, stat_level
from models.entities import HISTORY_RESULTS, EventResult, Specialty
from models.history import record_result
from models.simulation import advance_week
from tests.test_assignments import make_state


def pick(state, specialty=None):
    squad = [a for a in state.main_squad if specialty is None or a.specialty == specialty]
    return squad[0]


class TestLevels(unittest.TestCase):
    def test_thresholds(self) -> None:
        self.assertEqual([stat_level(v) for v in (100, 80, 79, 65, 64, 45, 44, 0)], ["great", "great", "good", "good", "mid", "mid", "low", "low"])

    def test_fatigue_is_read_the_other_way_round(self) -> None:
        self.assertEqual(stat_level(10, invert=True), "great")  # poca fatica = bene
        self.assertEqual(stat_level(95, invert=True), "low")


class TestSnapshot(unittest.TestCase):
    def test_plain_data_and_same_keys_as_the_empty_one(self) -> None:
        state = make_state(3)
        snap = athlete_snapshot(state, pick(state))
        json.dumps(snap)
        empty = empty_athlete_snapshot()
        self.assertEqual(set(snap), set(empty))
        for key in ("radar", "potential", "performance", "comparison"):
            self.assertEqual(set(snap[key]), set(empty[key]), key)

    def test_does_not_touch_the_state(self) -> None:
        state = make_state(3)
        a = pick(state)
        before = (a.form, a.fatigue, dict(a.history), state.week)
        athlete_snapshot(state, a)
        self.assertEqual(before, (a.form, a.fatigue, dict(a.history), state.week))

    def test_radar_has_the_five_axes_of_the_plan(self) -> None:
        state = make_state(3)
        a = pick(state)
        radar = athlete_snapshot(state, a)["radar"]
        self.assertEqual([x["label"] for x in radar["axes"]], ["Velocità", "Resistenza", "Forza", "Tecnica", "Resilienza"])
        self.assertEqual([x["value"] for x in radar["axes"]], [a.speed, a.stamina, a.strength, a.technique, a.resilience])

    def test_radar_average_is_the_one_of_the_discipline_mates(self) -> None:
        state = make_state(3)
        a = pick(state)
        mates = [p for p in state.main_squad if p.specialty == a.specialty and p.id != a.id]
        radar = athlete_snapshot(state, a)["radar"]
        if mates:
            self.assertTrue(radar["hasAvg"])
            self.assertEqual(radar["axes"][0]["avg"], round(sum(p.speed for p in mates) / len(mates)))
        for p in mates:  # nessun compagno: niente media
            p.in_youth_squad = True
        lone = athlete_snapshot(state, a)["radar"]
        self.assertFalse(lone["hasAvg"])
        self.assertTrue(all(x["avg"] is None for x in lone["axes"]))

    def test_potential_bar(self) -> None:
        state = make_state(3)
        a = pick(state)
        a.potential = 80
        pot = athlete_snapshot(state, a)["potential"]
        self.assertEqual(pot["pct"], round(100 * a.overall / 80))
        self.assertIn(str(80 - a.overall), pot["text"])
        a.potential = a.overall  # al massimo
        self.assertEqual(athlete_snapshot(state, a)["potential"]["text"], "Ha raggiunto il potenziale")
        a.potential = 0  # dato mancante: nessuna divisione per zero
        self.assertEqual(athlete_snapshot(state, a)["potential"]["pct"], 100)

    def test_condition_marks_fatigue_inverted(self) -> None:
        state = make_state(3)
        a = pick(state)
        a.fatigue, a.form = 95, 90
        cond = {r["label"]: r for r in athlete_snapshot(state, a)["condition"]}
        self.assertEqual(cond["Fatica"]["level"], "low")
        self.assertEqual(cond["Forma"]["level"], "great")
        self.assertEqual(cond["Fatica"]["value"], 95)  # il valore resta quello vero


class TestPerformance(unittest.TestCase):
    def test_empty_history(self) -> None:
        state = make_state(3)
        a = pick(state)
        a.history = {}
        perf = athlete_snapshot(state, a)["performance"]
        self.assertEqual(perf["points"], [])
        self.assertEqual(perf["summary"], "")
        self.assertTrue(perf["emptyText"])

    def test_points_summary_and_cap(self) -> None:
        state = make_state(3)
        a = pick(state)
        a.history = {}
        for i in range(HISTORY_RESULTS + 3):
            record_result(state, a, EventResult("100m", a.name, 1 + i % 4, 8, "11.0", 0, 0, is_pb=(i == 12), gender="M"))
        perf = athlete_snapshot(state, a)["performance"]
        self.assertEqual(len(perf["points"]), HISTORY_RESULTS)
        self.assertIn(f"{HISTORY_RESULTS} gare", perf["summary"])
        self.assertTrue(any(p["pb"] for p in perf["points"]))
        self.assertTrue(all(0.0 <= p["percentile"] <= 100.0 for p in perf["points"]))
        self.assertTrue(all(p["tip"] for p in perf["points"]))

    def test_withdrawn_counts_as_zero_and_not_as_a_win(self) -> None:
        state = make_state(3)
        a = pick(state)
        a.history = {}
        record_result(state, a, EventResult("100m", a.name, 1, 8, "—", 0, 0, withdrew_injured=True, gender="M"))
        perf = athlete_snapshot(state, a)["performance"]
        self.assertEqual(perf["points"][0]["percentile"], 0.0)
        self.assertIn("0 vittorie", perf["summary"])
        self.assertIn("ritirato", perf["points"][0]["tip"])

    def test_a_played_game_fills_it(self) -> None:
        state = make_state(3)
        rng = random.Random(3)
        for _ in range(8):
            advance_week(state, rng)
            state.pending_dilemma = None
        total = sum(len(athlete_snapshot(state, a)["performance"]["points"]) for a in state.main_squad)
        self.assertGreater(total, 0)


class TestComparison(unittest.TestCase):
    def test_rank_and_rows(self) -> None:
        state = make_state(3)
        a = pick(state)
        comp = athlete_snapshot(state, a)["comparison"]
        peers = [p for p in state.main_squad if p.specialty == a.specialty]
        better = sum(1 for p in peers if (-p.overall, p.name) < (-a.overall, a.name))
        self.assertEqual(comp["rank"], better + 1)
        self.assertEqual(comp["of"], len(peers))
        self.assertEqual(sum(r["me"] for r in comp["rows"]), 1)
        ovrs = [r["ovr"] for r in comp["rows"] if not r["me"]]
        self.assertEqual(ovrs, sorted(ovrs, reverse=True))
        self.assertLessEqual(len(comp["rows"]), COMPARISON_ROWS)

    def test_the_athlete_is_shown_even_when_far_down_the_ranking(self) -> None:
        state = make_state(3)
        template = pick(state)
        import copy

        state.athletes = [a for a in state.athletes if a.specialty != template.specialty]
        crowd = []
        for i in range(COMPARISON_ROWS + 4):
            c = copy.deepcopy(template)
            c.id, c.name, c.specialty, c.in_youth_squad = 900 + i, f"Atleta {i:02d}", Specialty.SPRINTS, False
            c.speed = c.stamina = c.strength = c.technique = c.resilience = 90 - i
            crowd.append(c)
        state.athletes += crowd
        last = crowd[-1]
        comp = athlete_snapshot(state, last)["comparison"]
        self.assertEqual(comp["rank"], len(crowd))
        self.assertTrue(any(r["me"] for r in comp["rows"]))
        self.assertEqual(len(comp["rows"]), COMPARISON_ROWS)

    def test_a_lone_athlete_ranks_first_of_one(self) -> None:
        state = make_state(3)
        a = pick(state)
        for p in state.main_squad:
            if p.id != a.id:
                p.in_youth_squad = True
        comp = athlete_snapshot(state, a)["comparison"]
        self.assertEqual((comp["rank"], comp["of"]), (1, 1))


if __name__ == "__main__":
    unittest.main()
