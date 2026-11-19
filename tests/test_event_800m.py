"""800 m (Q16): taratura, record del mondo, coerenza con il 1500 m e vecchi salvataggi senza la disciplina.

Senza Qt: `PYTHONPATH=. python3 -m unittest tests.test_event_800m`.
Le ancore dell'800 m sono STIME (nessun dato FIDAL a portata): le fasce sono larghe di proposito. Sostituirle
con dati veri (campionati regionali Lazio, Assoluti) appena disponibili, come già per lungo e peso.
"""

from __future__ import annotations

import random
import unittest

from models.entities import DNF_MARK, EVENTS, Specialty
from models.simulation import _score_to_mark, body_modifier, simulate_competition, upgrade_legacy_state
from tests.test_assignments import make_state

WR = {"M": 100.91, "F": 113.28}  # Rudisha 2012, Kratochvílová 1983 (verificati con ricerca web il 2026-11-19); indipendenti dalla costante


def mark(score: float, gender: str, event: str = "800m") -> float:
    return _score_to_mark(EVENTS[event], score, gender=gender)[0]


class TestEvent800mDefinition(unittest.TestCase):
    def test_is_a_middle_distance_event_between_400_and_1500(self) -> None:
        keys = list(EVENTS)
        self.assertEqual(EVENTS["800m"].specialty, Specialty.MIDDLE_DISTANCE)
        self.assertLess(keys.index("400m"), keys.index("800m"))
        self.assertLess(keys.index("800m"), keys.index("1500m"))
        self.assertTrue(EVENTS["800m"].lower_is_better)
        self.assertFalse(EVENTS["800m"].wind_affected)
        self.assertAlmostEqual(sum(EVENTS["800m"].weights.values()), 1.0)
        self.assertEqual(EVENTS["800m"].unit, EVENTS["1500m"].unit)  # stesso formato m:ss.cc

    def test_every_event_has_an_ideal_build(self) -> None:
        """Regola di CLAUDE.md: ogni gara ha un fisico ideale (qui anche per l'800m, per entrambi i sessi)."""
        from models.simulation import BODY_IDEALS, BODY_IDEALS_F

        for name in EVENTS:
            self.assertIn(name, BODY_IDEALS)
            self.assertIn(name, BODY_IDEALS_F)
        a = make_state(2).athletes[0]
        a.height_cm, a.weight_kg = 178, 66
        self.assertNotEqual(body_modifier(a, "800m"), 0.0)

    def test_historic_marks_correspond_to_comparable_scores(self) -> None:
        """Il traguardo storico dell'800m è raggiungibile ma non banale: score simile a quello del 1500m."""
        for gender, key in (("M", "historic_mark"), ("F", "historic_mark_f")):
            def score_of(event: str) -> float:
                target = getattr(EVENTS[event], key)
                lo, hi = 0.0, 150.0
                for _ in range(60):
                    mid = (lo + hi) / 2
                    if mark(mid, gender, event) > target:
                        lo = mid
                    else:
                        hi = mid
                return lo

            self.assertAlmostEqual(score_of("800m"), score_of("1500m"), delta=4.0, msg=gender)


class TestEvent800mCalibration(unittest.TestCase):
    def test_bands_at_the_game_anchors(self) -> None:
        # M: provinciale 42 ~2:05, regionale 56 ~1:58,5, vincitore regionale 66 ~1:54, nazionale 70 ~1:52, int. 84 ~1:45,5
        for score, lo, hi in ((42, 121.0, 129.0), (56, 115.0, 122.0), (66, 110.0, 118.0), (70, 108.0, 116.0), (84, 102.0, 109.0)):
            self.assertTrue(lo <= mark(score, "M") <= hi, (score, mark(score, "M")))
        # F: 42 ~2:21, 56 ~2:14,7, 66 ~2:10, 70 ~2:08,5, 84 ~2:02
        for score, lo, hi in ((42, 136.0, 146.0), (56, 130.0, 138.0), (66, 126.0, 134.0), (70, 124.0, 132.0), (84, 118.0, 126.0)):
            self.assertTrue(lo <= mark(score, "F") <= hi, (score, mark(score, "F")))

    def test_better_score_is_always_faster_and_capped_at_the_world_record(self) -> None:
        for gender in ("M", "F"):
            times = [mark(s, gender) for s in range(0, 120, 2)]
            self.assertTrue(all(a >= b for a, b in zip(times, times[1:])), gender)
            self.assertEqual(min(times), WR[gender], gender)  # raggiunge il tetto e non va oltre
            self.assertGreater(mark(84, gender), WR[gender])  # l'ancora internazionale è sotto il record

    def test_display_format_is_minutes_seconds_hundredths(self) -> None:
        seconds, text = _score_to_mark(EVENTS["800m"], 56.0, gender="M")
        m, s = divmod(seconds, 60)
        self.assertEqual(text, f"{int(m)}:{s:05.2f}")
        self.assertRegex(text, r"^\d:\d\d\.\d\d$")

    def test_consistent_with_the_1500m_at_every_anchor(self) -> None:
        """A parità di livello il rapporto 800m/1500m resta quasi costante (~0,47-0,49), non cambia da una ancora all'altra."""
        for gender in ("M", "F"):
            ratios = [mark(s, gender) / mark(s, gender, "1500m") for s in (42, 56, 66, 70, 84)]
            for r in ratios:
                self.assertTrue(0.46 <= r <= 0.52, (gender, ratios))
            self.assertLess(max(ratios) - min(ratios), 0.04, (gender, ratios))


class TestOldSaveWithout800m(unittest.TestCase):
    def test_upgrade_adds_rivals_and_lineup_and_the_meet_runs(self) -> None:
        state = make_state(6)
        for club in state.rival_clubs:  # com'era un salvataggio prima dell'800m
            club.athletes.pop("800m")
            club.female_athletes.pop("800m")
        state.event_lineup.pop("800m")
        state.event_lineup_f.pop("800m")
        upgrade_legacy_state(state, rng=random.Random(1))
        for club in state.rival_clubs:
            self.assertEqual(club.athletes["800m"].event, "800m")
            self.assertEqual(club.female_athletes["800m"].gender, "F")
        for gender in ("M", "F"):
            self.assertIn("800m", state.lineup_for(gender))
        self.assertIsNotNone(state.event_lineup["800m"])
        # nessun atleta oltre il tetto di gare, e il meeting si disputa con l'800m dentro
        for gender in ("M", "F"):
            counts: dict = {}
            for e in state.active_events:
                aid = state.lineup_for(gender).get(e)
                if aid is not None:
                    counts[aid] = counts.get(aid, 0) + 1
            self.assertLessEqual(max(counts.values()), 2)
        summary = simulate_competition(state, rng=random.Random(3))
        events = {(r.event_name, r.gender) for r in summary.event_results}
        self.assertIn(("800m", "M"), events)
        self.assertIn(("800m", "F"), events)
        for r in summary.event_results:
            if r.event_name == "800m":
                self.assertTrue(all(60.0 < s.mark_value < 400.0 for s in r.standings if s.mark_display != DNF_MARK), r.gender)

    def test_upgrade_is_idempotent_for_a_current_save(self) -> None:
        state = make_state(6)
        before = {(c.name, e): a.name for c in state.rival_clubs for e, a in c.athletes.items()}
        lineup = dict(state.event_lineup)
        upgrade_legacy_state(state, rng=random.Random(1))
        after = {(c.name, e): a.name for c in state.rival_clubs for e, a in c.athletes.items()}
        self.assertEqual(before, after)
        self.assertEqual(lineup, state.event_lineup)


if __name__ == "__main__":
    unittest.main()
