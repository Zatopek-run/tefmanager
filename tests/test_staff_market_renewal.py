"""Rinnovo del mercato dello staff a fine stagione (PIANOLAVORO E.1, Q33). Senza Qt.

Garanzie: l'assunto resta, i non assunti cambiano, 3 persone per ruolo, ids nuovi e unici, **una sola estrazione dell'RNG
della partita**, esito deterministico, e il caricamento di un salvataggio non riporta indietro i candidati del catalogo.
"""

from __future__ import annotations

import random
import tempfile
import unittest
from pathlib import Path

from models.database import DatabaseManager
from models.entities import (
    STAFF_ATTR_REF,
    STAFF_ATTRIBUTES,
    STAFF_CATALOGUE_LAST_ID,
    STAFF_POOL_PER_ROLE,
    STAFF_TIERS,
    StaffRole,
)
from models.generator import (
    create_initial_staff,
    ensure_staff_market,
    renew_staff_market,
    staff_weekly_cost,
)
from models.simulation import advance_week
from tests.test_assignments import make_state

ROLES = list(STAFF_ATTRIBUTES)


def state_with_market(hire_ids=(5,)):
    state = make_state(3)
    state.staff = create_initial_staff()
    for m in state.staff:
        m.hired = m.id in hire_ids
    state.season_number = 2
    return state


def per_role(state, role):
    return [m for m in state.staff if m.role == role]


class TestRenewal(unittest.TestCase):
    def test_hired_stays_and_the_others_are_replaced_by_new_people(self) -> None:
        state = state_with_market((5,))
        old_ids = {m.id for m in state.staff}
        renew_staff_market(state, random.Random(1))
        hired = [m for m in state.staff if m.hired]
        self.assertEqual([m.id for m in hired], [5])
        new = [m for m in state.staff if m.id not in old_ids]
        self.assertEqual(len(new), 8)  # 9 − 1 assunto, poi 3 + 3 + 2 nuovi: 8 al posto degli 8 non assunti
        self.assertFalse(any(m.hired for m in new))
        self.assertTrue(all(m.id > STAFF_CATALOGUE_LAST_ID for m in new))
        self.assertEqual(len({m.id for m in state.staff}), len(state.staff))

    def test_always_three_per_role_with_or_without_a_hired_one(self) -> None:
        for hire in ((), (4,), (5, 6), (4, 5, 6)):
            state = state_with_market(hire)
            renew_staff_market(state, random.Random(2))
            for role in ROLES:
                self.assertEqual(len(per_role(state, role)), STAFF_POOL_PER_ROLE, (hire, role))
            self.assertEqual(len(state.staff), 9)

    def test_new_candidates_differ_in_profile_and_names_are_unique(self) -> None:
        state = state_with_market(())
        renew_staff_market(state, random.Random(3))
        self.assertEqual(len({m.name for m in state.staff}), 9)
        for role in ROLES:
            group = per_role(state, role)
            self.assertEqual(len({m.skill for m in group}), 3, role)  # un junior, un esperto, un senior
            for m in group:
                self.assertEqual(set(m.attributes), {k for k, _l in STAFF_ATTRIBUTES[role]})
                self.assertTrue(m.name.startswith("Dott."))

    def test_attributes_stay_inside_the_tier_bands(self) -> None:
        lows = {stars: band for _n, band, stars in STAFF_TIERS}
        for seed in range(40):
            state = state_with_market(())
            renew_staff_market(state, random.Random(seed))
            for m in state.staff:
                low, high = lows[m.skill]
                for value in m.attributes.values():
                    self.assertTrue(low <= value <= high, (m.skill, m.attributes))

    def test_consumes_exactly_one_draw_of_the_game_rng(self) -> None:
        state = state_with_market()
        rng, mirror = random.Random(99), random.Random(99)
        renew_staff_market(state, rng)
        mirror.getrandbits(32)
        self.assertEqual(rng.getstate(), mirror.getstate())
        # anche senza mercato (fixture di test) la stessa estrazione, così il flusso non dipende dallo stato dello staff
        empty = make_state(3)
        rng2, mirror2 = random.Random(99), random.Random(99)
        self.assertEqual(renew_staff_market(empty, rng2), [])
        mirror2.getrandbits(32)
        self.assertEqual(rng2.getstate(), mirror2.getstate())

    def test_deterministic_for_a_seed_and_different_across_seeds(self) -> None:
        def snapshot(seed):
            state = state_with_market()
            renew_staff_market(state, random.Random(seed))
            return [(m.id, m.name, m.skill, m.weekly_cost, tuple(sorted(m.attributes.items()))) for m in state.staff]

        self.assertEqual(snapshot(7), snapshot(7))
        self.assertNotEqual(snapshot(7), snapshot(8))

    def test_ids_never_repeat_over_several_seasons(self) -> None:
        state = state_with_market((4,))
        seen = {m.id for m in state.staff}
        rng = random.Random(5)
        for _ in range(5):
            before = {m.id for m in state.staff}
            renew_staff_market(state, rng)
            fresh = {m.id for m in state.staff} - before
            self.assertFalse(fresh & seen)
            seen |= {m.id for m in state.staff}
        self.assertEqual([m.id for m in state.staff if m.hired], [4])  # l'assunto attraversa tutte le stagioni

    def test_the_news_line_names_the_season_and_count(self) -> None:
        state = state_with_market((5,))
        news = renew_staff_market(state, random.Random(1))
        self.assertEqual(len(news), 1)
        self.assertIn("rinnova", news[0])
        self.assertIn("8", news[0])


class TestCost(unittest.TestCase):
    def test_reference_attributes_cost_the_base_of_the_role(self) -> None:
        for role, base in ((StaffRole.PHYSIO, 300), (StaffRole.DOCTOR, 340), (StaffRole.MENTAL_COACH, 220)):
            attrs = {k: STAFF_ATTR_REF for k, _l in STAFF_ATTRIBUTES[role]}
            self.assertEqual(staff_weekly_cost(role, attrs), base)

    def test_cost_grows_with_attributes_and_is_in_euro_tens(self) -> None:
        keys = [k for k, _l in STAFF_ATTRIBUTES[StaffRole.PHYSIO]]
        costs = [staff_weekly_cost(StaffRole.PHYSIO, {k: v for k in keys}) for v in range(1, 21)]
        self.assertEqual(costs, sorted(costs))
        self.assertTrue(all(c % 10 == 0 and c >= 100 for c in costs))
        self.assertAlmostEqual(staff_weekly_cost(StaffRole.PHYSIO, {k: 10 for k in keys}) / 300, 0.6, delta=0.05)
        self.assertAlmostEqual(staff_weekly_cost(StaffRole.PHYSIO, {k: 16 for k in keys}) / 300, 1.5, delta=0.1)


class TestTickAndReload(unittest.TestCase):
    def play_until_season_end(self, state, rng):
        season = state.season_number
        guard = 0
        while state.season_number == season and guard < 120:
            state.pending_dilemma = None
            advance_week(state, rng=rng)
            guard += 1
        return guard

    def test_the_season_end_of_the_tick_renews_the_market_once(self) -> None:
        state = make_state(3)
        state.staff = create_initial_staff()
        state.staff[1].hired = True  # Greco
        hired_id = state.staff[1].id
        before = {m.id for m in state.staff}
        self.play_until_season_end(state, random.Random(7))
        self.assertEqual(len(state.staff), 9)
        self.assertEqual([m.id for m in state.staff if m.hired], [hired_id])
        self.assertEqual(len({m.id for m in state.staff} - before), 8)
        self.assertTrue(any("mercato dello staff" in n for n in state.news_log))

    def test_reload_after_a_renewal_does_not_bring_the_catalogue_back(self) -> None:
        state = make_state(3)
        state.staff = create_initial_staff()
        state.staff[1].hired = True
        hired_id = state.staff[1].id
        self.play_until_season_end(state, random.Random(7))
        ids = [m.id for m in state.staff]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "s.db"
            DatabaseManager(db_path=path).save_game(state)
            loaded = DatabaseManager(db_path=path).load_game()
            self.assertEqual([m.id for m in loaded.staff], ids)
            self.assertEqual(len(loaded.staff), 9)
            self.assertEqual([m.id for m in loaded.staff if m.hired], [hired_id])
            for a, b in zip(state.staff, loaded.staff):
                self.assertEqual((a.name, a.weekly_cost, a.attributes), (b.name, b.weekly_cost, b.attributes))
            DatabaseManager(db_path=path).save_game(loaded)
            self.assertEqual([m.id for m in DatabaseManager(db_path=path).load_game().staff], ids)

    def test_ensure_market_only_completes_saves_from_before_the_market(self) -> None:
        state = state_with_market(())
        renew_staff_market(state, random.Random(4))
        ids = [m.id for m in state.staff]
        self.assertEqual(ensure_staff_market(state.staff), 0)
        self.assertEqual([m.id for m in state.staff], ids)
        # un salvataggio con un solo originale assunto e gli altri già rinnovati non è «precedente al mercato»
        mixed = [m for m in create_initial_staff() if m.id == 4] + [m for m in state.staff if m.id > STAFF_CATALOGUE_LAST_ID][:2]
        self.assertEqual(ensure_staff_market(mixed), 0)
        self.assertEqual(len(mixed), 3)


if __name__ == "__main__":
    unittest.main()
