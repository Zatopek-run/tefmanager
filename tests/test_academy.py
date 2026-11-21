"""Giovanili avanzate (PIANOLAVORO E.3): Academy a stelle, osservatore con attributi, rete regionale. Senza Qt.

Garanzie: (1) senza Academy, scout e regione ogni cosa è identica a prima di E.3; (2) 5 stelle = +50% di crescita del
vivaio (e solo del vivaio); (3) le fasce d'incertezza contengono sempre il valore vero e si stringono con gli attributi.
"""

from __future__ import annotations

import random
import unittest
from copy import deepcopy

from models.entities import (
    ACADEMY_MAX_LEVEL,
    SCOUT_CURRENT_BAND,
    SCOUT_POTENTIAL_BAND,
    SCOUT_REGION_STAR_CHANCE,
    SCOUT_REGION_STAR_STAT_MAX,
    SCOUT_REGION_STAR_STAT_MIN,
    SCOUT_REGIONS,
    STAFF_ATTR_MAX,
    PeriodizationPhase,
    Personality,
    Scout,
    Specialty,
    TrainingFocus,
)
from models.generator import generate_academy_prospects, generate_initial_roster
from models.scouting import (
    SCOUT_CATALOGUE,
    academy_growth_multiplier,
    academy_upgrade_cost,
    apply_region_talent,
    band_half_width,
    current_band_text,
    current_half_width,
    estimate_band,
    potential_band_text,
    potential_half_width,
    region_search_extras,
    scout_candidates,
    scout_from_json,
    scout_severance,
    scout_to_json,
)
from models.simulation import apply_weekly_training


def scout_with(potenziale: int, attuale: int) -> Scout:
    return Scout(9, "Prova", 100, potenziale, attuale)


def youth(seed: int = 1, in_youth: bool = True):
    a = generate_initial_roster(rng=random.Random(seed))[0]
    a.in_youth_squad = in_youth
    a.personality = Personality.LEADER
    a.training_focus = TrainingFocus.EXPLOSIVE_POWER
    a.periodization = PeriodizationPhase.PREP_SPECIFICA
    a.age = 16
    a.speed = a.stamina = a.strength = a.technique = 30
    a.potential = 45  # poco margine: la probabilità resta sotto il tetto di 0,95 anche con cinque stelle
    a.fatigue = 10
    a.injured_weeks = 0
    a.doping_boost_weeks = 0
    return a


def growth(level: int, in_youth: bool = True, seeds: int = 600) -> int:
    base = youth(in_youth=in_youth)
    total = 0
    for seed in range(seeds):
        a = deepcopy(base)
        apply_weekly_training(a, rng=random.Random(seed), academy_level=level)
        total += a.strength - 30
    return total


class TestAcademy(unittest.TestCase):
    def test_multiplier_is_one_at_zero_stars_and_one_and_a_half_at_five(self) -> None:
        self.assertEqual(academy_growth_multiplier(0), 1.0)
        self.assertAlmostEqual(academy_growth_multiplier(5), 1.5)
        steps = [academy_growth_multiplier(n) for n in range(ACADEMY_MAX_LEVEL + 1)]
        self.assertEqual(steps, sorted(steps))
        self.assertAlmostEqual(academy_growth_multiplier(99), 1.5)  # mai oltre cinque stelle

    def test_upgrade_cost_rises_with_the_star(self) -> None:
        costs = [academy_upgrade_cost(n) for n in range(ACADEMY_MAX_LEVEL)]
        self.assertEqual(costs, [4000, 8000, 12000, 16000, 20000])

    def test_five_stars_make_youth_grow_clearly_more(self) -> None:
        self.assertGreater(growth(5), growth(0) * 1.25)  # +50% sulla probabilità: il guadagno cresce di quasi altrettanto
        self.assertGreater(growth(3), growth(1))

    def test_zero_stars_is_exactly_the_old_behaviour_rng_included(self) -> None:
        for seed in range(30):
            a, b = youth(), youth()
            r1, r2 = random.Random(seed), random.Random(seed)
            apply_weekly_training(a, rng=r1)
            apply_weekly_training(b, rng=r2, academy_level=0)
            self.assertEqual(a, b)
            self.assertEqual(r1.getstate(), r2.getstate())

    def test_the_academy_does_not_touch_the_main_squad(self) -> None:
        for seed in range(30):
            a, b = youth(in_youth=False), youth(in_youth=False)
            r1, r2 = random.Random(seed), random.Random(seed)
            apply_weekly_training(a, rng=r1, academy_level=5)
            apply_weekly_training(b, rng=r2, academy_level=0)
            self.assertEqual(a, b)
            self.assertEqual(r1.getstate(), r2.getstate())


class TestBands(unittest.TestCase):
    def kids(self, n: int = 40):
        return generate_academy_prospects(count=n, rng=random.Random(5))

    def test_no_scout_means_the_old_widths(self) -> None:
        self.assertEqual(potential_half_width(None), SCOUT_POTENTIAL_BAND)
        self.assertEqual(current_half_width(None), SCOUT_CURRENT_BAND)
        self.assertEqual(SCOUT_POTENTIAL_BAND, 8)  # la fascia di `potential_band_display` prima di E.3

    def test_attribute_one_is_the_same_as_no_scout(self) -> None:
        for kid in self.kids():
            self.assertEqual(potential_band_text(kid, scout_with(1, 1)), potential_band_text(kid, None))
            self.assertEqual(current_band_text(kid, scout_with(1, 1)), current_band_text(kid, None))

    def test_width_shrinks_with_the_attribute_down_to_the_minimum(self) -> None:
        widths = [band_half_width(a, 8, 2) for a in range(1, STAFF_ATTR_MAX + 1)]
        self.assertEqual(widths, sorted(widths, reverse=True))
        self.assertEqual((widths[0], widths[-1]), (8, 2))
        self.assertEqual(band_half_width(STAFF_ATTR_MAX, 5, 0), 0)

    def test_the_band_always_contains_the_true_value(self) -> None:
        for kid in self.kids():
            for attr in range(1, STAFF_ATTR_MAX + 1):
                scout = scout_with(attr, attr)
                lo, hi = (int(x) for x in potential_band_text(kid, scout).split("-"))
                self.assertLessEqual(lo, kid.potential)
                self.assertGreaterEqual(hi, kid.potential)
                text = current_band_text(kid, scout)
                if "-" in text:
                    lo, hi = (int(x) for x in text.split("-"))
                    self.assertLessEqual(lo, kid.overall)
                    self.assertGreaterEqual(hi, kid.overall)
                else:
                    self.assertEqual(int(text), kid.overall)

    def test_a_perfect_current_judgement_sees_the_exact_overall(self) -> None:
        for kid in self.kids():
            self.assertEqual(current_band_text(kid, scout_with(1, STAFF_ATTR_MAX)), str(kid.overall))

    def test_a_better_scout_narrows_the_band(self) -> None:
        for kid in self.kids(10):
            def width(scout) -> int:
                lo, hi = (int(x) for x in potential_band_text(kid, scout).split("-"))
                return hi - lo

            self.assertLess(width(scout_with(20, 1)), width(None))

    def test_the_band_is_deterministic_and_independent_of_the_rng(self) -> None:
        kid = self.kids(1)[0]
        random.seed(1)
        first = potential_band_text(kid, scout_with(10, 10))
        random.seed(999)
        self.assertEqual(potential_band_text(kid, scout_with(10, 10)), first)
        self.assertEqual(estimate_band(70, "x", 6), estimate_band(70, "x", 6))

    def test_the_potential_band_matches_the_one_the_game_always_showed(self) -> None:
        """Con la fascia di prima (±8, scarto ±3) la stessa formula: lo stesso numero di sempre per lo stesso ragazzo."""
        for kid in self.kids():
            lo, hi = estimate_band(
                kid.potential, f"{kid.name}|{kid.age}|{kid.specialty.value}|{kid.gender}", SCOUT_POTENTIAL_BAND
            )
            self.assertEqual(potential_band_text(kid, None), f"{lo}-{hi}")


class TestScoutPersistence(unittest.TestCase):
    def test_catalogue_has_three_candidates_with_attributes_in_range(self) -> None:
        cands = scout_candidates()
        self.assertEqual(len(cands), len(SCOUT_CATALOGUE))
        self.assertEqual(len(cands), 3)
        self.assertEqual(len({c.scout_id for c in cands}), 3)
        for c in cands:
            self.assertTrue(1 <= c.potenziale <= 20 and 1 <= c.attuale <= 20 and c.weekly_cost > 0)

    def test_roundtrip_and_corrupt_values(self) -> None:
        for c in scout_candidates():
            self.assertEqual(scout_from_json(scout_to_json(c)), c)
        self.assertEqual(scout_to_json(None), "{}")
        for raw in (None, "", "{}", "non json", "[1]", "42", '{"id": "x"}', '{"id": 1, "name": "a"}'):
            self.assertIsNone(scout_from_json(raw), raw)

    def test_out_of_range_attributes_are_clamped(self) -> None:
        got = scout_from_json('{"id": 1, "name": "a", "cost": 10, "potenziale": 99, "attuale": -5}')
        self.assertEqual((got.potenziale, got.attuale), (20, 1))

    def test_severance_is_six_weeks_of_pay(self) -> None:
        self.assertEqual(scout_severance(scout_with(10, 10)), 600)


class TestRegions(unittest.TestCase):
    def test_no_region_means_no_extra_cost(self) -> None:
        self.assertEqual(region_search_extras(None), (0, 0))
        self.assertEqual(region_search_extras("giamaica"), (1, 800))

    def test_a_region_marks_the_nationality_and_about_a_fifth_are_stars(self) -> None:
        for key, (_label, spec, stat, nationality) in SCOUT_REGIONS.items():
            rng = random.Random(7)
            kids = generate_academy_prospects(count=2000, rng=rng, specialty=spec)
            stars = 0
            for kid in kids:
                before = getattr(kid, stat)
                stars += 1 if apply_region_talent(kid, key, rng) else 0
                self.assertEqual(kid.nationality, nationality)
                self.assertGreaterEqual(kid.potential, getattr(kid, stat))
                if getattr(kid, stat) != before:
                    self.assertGreater(getattr(kid, stat), 80)
            self.assertAlmostEqual(stars / len(kids), SCOUT_REGION_STAR_CHANCE, delta=0.03, msg=key)
            self.assertEqual(sum(1 for k in kids if getattr(k, stat) > 80), stars, key)  # i non-talenti non superano 80

    def test_jamaica_makes_sprinters_with_speed_above_80(self) -> None:
        rng = random.Random(3)
        kids = generate_academy_prospects(count=1000, rng=rng, specialty=Specialty.SPRINTS)
        for kid in kids:
            apply_region_talent(kid, "giamaica", rng)
        share = sum(1 for k in kids if k.speed > 80) / len(kids)
        self.assertAlmostEqual(share, 0.20, delta=0.04)

    def test_draw_count_is_one_per_kid_plus_one_for_each_star(self) -> None:
        for seed in range(40):
            rng, ref = random.Random(seed), random.Random(seed)
            kid = generate_academy_prospects(count=1, rng=random.Random(2), specialty=Specialty.SPRINTS)[0]
            star = apply_region_talent(kid, "giamaica", rng)
            ref.random()
            if star:
                ref.randint(SCOUT_REGION_STAR_STAT_MIN, SCOUT_REGION_STAR_STAT_MAX)
            self.assertEqual(rng.getstate(), ref.getstate(), seed)

    def test_every_region_matches_a_nationality_the_game_knows(self) -> None:
        from models.entities import NATIONALITIES

        for _label, _spec, _stat, nationality in SCOUT_REGIONS.values():
            self.assertIn(nationality, NATIONALITIES)


if __name__ == "__main__":
    unittest.main()
