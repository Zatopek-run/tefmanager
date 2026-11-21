"""Istantanea della Dashboard (PIANOLAVORO G.1, scelta C: Dashboard in QML). **Senza Qt.**

La vista QML disegna soltanto `dashboard_snapshot`: testi, soglie e gravità si decidono qui. Questo file raccoglie le asserzioni che
prima leggevano i widget della Dashboard (`squad_val`, `top_table`, `objectives_list`, `tier_progress`, `actions_box`…) e ora leggono
lo snapshot: dove sono finite è indicato in ogni test.
"""

from __future__ import annotations

import json
import random
import unittest

from models.dashboard import (
    TOP_ATHLETES,
    dashboard_snapshot,
    empty_dashboard_snapshot,
    short_event_name,
    weekly_action_items,
)
from models.entities import EthicalDilemma, HISTORY_WEEKS
from models.simulation import advance_week
from tests.test_assignments import make_state


def kpis(snap: dict) -> dict:
    return {k["key"]: k for k in snap["kpis"]}


def shape(value):
    """La «forma» di un dict: chiavi e tipi annidati, per confrontare lo scheletro con uno snapshot vero."""
    if isinstance(value, dict):
        return {k: shape(v) for k, v in value.items()}
    if isinstance(value, list):
        return [shape(value[0])] if value else []
    return type(value).__name__


class TestShape(unittest.TestCase):
    def test_plain_data_only(self) -> None:
        """Solo dict/liste/stringhe/numeri/booleani con chiavi stringa: passa da QVariantMap a QML senza perdite."""
        snap = dashboard_snapshot(make_state(3), [])
        json.dumps(snap)  # se fallisce, c'è un oggetto che QML non saprebbe leggere

    def test_the_empty_snapshot_has_every_key_of_a_real_one(self) -> None:
        real, empty = dashboard_snapshot(make_state(3), []), empty_dashboard_snapshot()
        self.assertEqual(set(real), set(empty))
        for key in ("pill", "trend", "season", "top"):
            self.assertEqual(set(real[key]), set(empty[key]), key)
        self.assertEqual(set(real["season"]["progress"]), set(empty["season"]["progress"]))
        self.assertEqual(len(empty["kpis"]), len(real["kpis"]))
        self.assertEqual(set(real["kpis"][0]), set(empty["kpis"][0]))

    def test_does_not_touch_the_state(self) -> None:
        state = make_state(3)
        before = (state.week, state.budget, [(a.form, a.fatigue) for a in state.athletes], list(state.news_log))
        dashboard_snapshot(state, [])
        self.assertEqual(before, (state.week, state.budget, [(a.form, a.fatigue) for a in state.athletes], list(state.news_log)))


class TestKpis(unittest.TestCase):
    def test_four_clickable_cards_with_valid_targets(self) -> None:
        cards = dashboard_snapshot(make_state(3), [])["kpis"]
        self.assertEqual([c["key"] for c in cards], ["budget", "prestige", "squad", "race"])
        self.assertEqual([c["target"] for c in cards], [7, 5, 1, 3])  # indici della barra laterale (finora fissi)

    def test_negative_budget_is_flagged_bad(self) -> None:
        state = make_state(3)
        state.budget = -500
        card = kpis(dashboard_snapshot(state, []))["budget"]
        self.assertEqual(card["tone"], "bad")
        self.assertIn("In rosso", card["sub"])
        state.budget = 5000
        self.assertEqual(kpis(dashboard_snapshot(state, []))["budget"]["tone"], "")

    def test_empty_squad_tells_what_to_do(self) -> None:
        """Era `squad_val`/`squad_sub` in test_empty_start_ui."""
        state = make_state(3)
        state.athletes = []
        card = kpis(dashboard_snapshot(state, []))["squad"]
        self.assertIn("Nessun atleta", card["value"])
        self.assertIn("Vivaio", card["sub"])

    def test_the_race_card_counts_down(self) -> None:
        state = make_state(3)
        state.week = 5
        card = kpis(dashboard_snapshot(state, []))["race"]
        self.assertEqual(card["value"], f"Tra {state.weeks_until_competition} sett.")
        state.week = 4
        self.assertEqual(kpis(dashboard_snapshot(state, []))["race"]["tone"], "warn")  # settimana di gara


class TestPill(unittest.TestCase):
    """Era il semaforo di `TestDashboard.test_the_traffic_light`."""

    def test_pending_dilemma_is_always_red(self) -> None:
        state = make_state(3)
        state.pending_dilemma = EthicalDilemma(id="d1", title="t", description="d", accept_label="Sì", reject_label="No")
        pill = dashboard_snapshot(state, [])["pill"]
        self.assertEqual(pill["level"], "danger")
        self.assertIn("Dilemma", pill["text"])

    def test_the_level_follows_the_worst_priority(self) -> None:
        state = make_state(3)
        state.pending_dilemma = None
        snap = dashboard_snapshot(state, [])
        severities = {a["severity"] for a in snap["actions"]}
        expected = "danger" if "danger" in severities else ("warn" if "warn" in severities else "ok")
        self.assertEqual(snap["pill"]["level"], expected)

    def test_nothing_to_do_is_green(self) -> None:
        state = make_state(3)
        state.pending_dilemma = None
        snap = dashboard_snapshot(state, [])
        snap2 = {**snap, "actions": [{"text": "x", "severity": "ok", "target": 0}]}
        from models.dashboard import _pill

        self.assertEqual(_pill(state, snap2["actions"]), {"level": "ok", "text": "Tutto ok"})


class TestTrend(unittest.TestCase):
    def test_empty_trend_says_why(self) -> None:
        """Era `test_the_empty_trend_says_why` (`trend_chart._empty_text`)."""
        state = make_state(3)
        for a in state.athletes:
            a.history = {}
        self.assertIn("avanza la prima settimana", dashboard_snapshot(state, [])["trend"]["emptyText"])
        state.athletes = []
        self.assertIn("Nessun atleta", dashboard_snapshot(state, [])["trend"]["emptyText"])

    def test_one_point_and_one_tip_per_week_played(self) -> None:
        state = make_state(3)
        rng = random.Random(3)
        for _ in range(3):
            advance_week(state, rng)
            state.pending_dilemma = None
        trend = dashboard_snapshot(state, [])["trend"]
        self.assertEqual(len(trend["form"]), 3)
        self.assertEqual(len(trend["fatigue"]), 3)
        self.assertEqual(len(trend["tips"]), 3)
        self.assertEqual(trend["weeks"], HISTORY_WEEKS)
        self.assertTrue(trend["tips"][-1].startswith("ultima settimana"))
        self.assertTrue(trend["tips"][0].startswith("2 sett. fa"))


class TestSeason(unittest.TestCase):
    def test_progress_and_lead_in_career(self) -> None:
        """Era `tier_progress.maximum()/format()` in test_empty_start_ui."""
        state = make_state(3)
        state.game_mode = "career"
        season = dashboard_snapshot(state, [])["season"]
        self.assertEqual(season["progress"]["max"], state.season_length)
        self.assertIn("mancano", season["progress"]["text"])
        self.assertTrue(season["showTimeline"])
        self.assertEqual(len(season["weeks"]), state.season_length)

    def test_the_prototype_has_no_timeline_and_no_contracts(self) -> None:
        """Era `test_the_prototype_has_no_season_timeline`."""
        state = make_state(3)
        state.game_mode = "vertical_slice"
        state.main_squad[0].contract_end_season = state.season_number
        season = dashboard_snapshot(state, [])["season"]
        self.assertFalse(season["showTimeline"])
        self.assertEqual(season["contracts"], "")
        self.assertEqual(season["progress"]["max"], 8)
        self.assertIn("Prototipo", season["progress"]["text"])

    def test_expiring_contracts_are_listed_in_career(self) -> None:
        state = make_state(3)
        state.game_mode = "career"
        for a in state.main_squad:
            a.contract_end_season = state.season_number + 3
        state.main_squad[0].contract_end_season = state.season_number
        self.assertIn(state.main_squad[0].name, dashboard_snapshot(state, [])["season"]["contracts"])
        state.main_squad[0].contract_end_season = state.season_number + 3
        self.assertEqual(dashboard_snapshot(state, [])["season"]["contracts"], "")

    def test_timeline_marks_exactly_one_current_week(self) -> None:
        state = make_state(3)
        state.game_mode = "career"
        weeks = dashboard_snapshot(state, [])["season"]["weeks"]
        self.assertEqual(sum(w["current"] for w in weeks), 1)
        self.assertTrue(all(w["tip"].startswith(f"Settimana {w['number']}") for w in weeks))


class TestObjectives(unittest.TestCase):
    def test_real_state_not_text_prefixes(self) -> None:
        """Era `objectives_list` con icone vere: lo stato fatto/non fatto è un booleano, non «[COMPLETATO]»/«[ ]» nel testo."""
        state = make_state(3)
        rows = dashboard_snapshot(state, [])["objectives"]
        self.assertEqual(len(rows), len(state.objectives))
        for row in rows:
            self.assertIsInstance(row["done"], bool)
            self.assertNotIn("[", row["text"])
            self.assertEqual(row["kind"], "objective")

    def test_failed_seasons_and_the_sacking_are_flagged(self) -> None:
        """Era test_board_ui: «Attenzione» e «ESONERATO» in coda all'elenco."""
        state = make_state(3)
        state.board_failed_streak = 1
        last = dashboard_snapshot(state, [])["objectives"][-1]
        self.assertIn("Attenzione", last["text"])
        self.assertEqual(last["kind"], "warn")
        state.fired = True
        last = dashboard_snapshot(state, [])["objectives"][-1]
        self.assertIn("ESONERATO", last["text"])
        self.assertEqual(last["kind"], "fired")


class TestHeatAndTop(unittest.TestCase):
    def test_heat_rows_cells_and_one_best_per_row(self) -> None:
        heat = dashboard_snapshot(make_state(3), [])["heat"]
        self.assertIsNotNone(heat)
        self.assertEqual(len(heat["events"]), len(heat["rows"][0]["cells"]))
        for row in heat["rows"]:
            self.assertEqual(sum(c["best"] for c in row["cells"]), 1)
            self.assertTrue(all(0.0 <= c["level"] <= 1.0 for c in row["cells"]))
        self.assertLessEqual(len(heat["rows"]), 8)

    def test_no_heat_without_athletes(self) -> None:
        state = make_state(3)
        state.athletes = []
        self.assertIsNone(dashboard_snapshot(state, [])["heat"])

    def test_short_event_names(self) -> None:
        self.assertEqual([short_event_name(n) for n in ("100m", "Salto in Lungo", "Getto del Peso")], ["100m", "Lungo", "Peso"])

    def test_top_rows_are_complete_and_leveled(self) -> None:
        """Era `top_table`: nomi interi, stato mai abbreviato, al più 8 righe, livello del badge."""
        top = dashboard_snapshot(make_state(3), [])["top"]
        self.assertLessEqual(len(top["rows"]), TOP_ATHLETES)
        self.assertEqual(top["emptyText"], "")
        ovrs = [r["ovr"] for r in top["rows"]]
        self.assertEqual(ovrs, sorted(ovrs, reverse=True))
        for r in top["rows"]:
            self.assertIn(r["level"], ("ok", "warn", "danger"))
            self.assertNotIn("...", r["status"])
            self.assertRegex(r["name"], r"\([MF]\)$")

    def test_empty_squad_placeholder(self) -> None:
        state = make_state(3)
        state.athletes = []
        top = dashboard_snapshot(state, [])["top"]
        self.assertEqual(top["rows"], [])
        self.assertIn("Nessun atleta in rosa", top["emptyText"])
        self.assertNotIn("&&", top["emptyText"])


class TestActionsAndNews(unittest.TestCase):
    def test_actions_are_the_weekly_priorities(self) -> None:
        state = make_state(3)
        snap = dashboard_snapshot(state, [])
        self.assertEqual([(a["text"], a["severity"], a["target"]) for a in snap["actions"]], weekly_action_items(state, []))

    def test_empty_squad_does_not_report_uncovered_events(self) -> None:
        state = make_state(3)
        state.athletes = []
        texts = [a["text"] for a in dashboard_snapshot(state, [])["actions"]]
        self.assertTrue(any("Nessun atleta in rosa" in t for t in texts))
        self.assertFalse(any("gare scoperte" in t for t in texts))

    def test_news_lists_milestones_first_and_is_capped(self) -> None:
        state = make_state(3)
        state.milestones = [f"m{i}" for i in range(10)]
        state.news_log = [f"n{i}" for i in range(30)]
        news = dashboard_snapshot(state, [])["news"]
        stars = [n for n in news if n["star"]]
        self.assertTrue(all(n["text"].startswith("★ ") for n in stars))
        self.assertEqual(news[: len(stars)], stars)
        self.assertLessEqual(len(news), 12)


if __name__ == "__main__":
    unittest.main()
