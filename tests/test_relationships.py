"""Relazioni tra atleti (PIANOLAVORO F.3): amicizie, rivalità, chimica di squadra e affiatamento di staffetta. Senza Qt.

Garanzie: (1) la relazione di una coppia è deterministica e simmetrica; (2) un'amicizia tra le frazioni dà +10 di affiatamento
a una staffetta, una rivalità −10; (3) la chimica sposta la forma di tutti entro ±3; (4) nessun RNG.
"""

from __future__ import annotations

import random
import unittest
from itertools import combinations

from models.entities import (
    CHEMISTRY_FORM_MAX,
    RELATION_BOND_PER_RELAY,
    RELATION_FRIEND_MIN,
    RELATION_RIVAL_MAX,
    RELATION_STRENGTH_MAX,
    RELATION_STRENGTH_MIN,
    RELAY_FRIEND_HARMONY,
    RELAY_RIVAL_HARMONY,
    PeriodizationPhase,
    Personality,
    TrainingFocus,
)
from models.generator import generate_initial_roster
from models.relationships import (
    bond_relay_teammates,
    ensure_relationships,
    initial_value,
    is_friend,
    is_rival,
    net_pairs,
    relation_between,
    relation_label,
    relations_of,
    relationships_from_json,
    relationships_to_json,
    relay_chemistry_bonus,
    set_relation,
    team_chemistry_form_bonus,
)
from models.simulation import _recalculate_form, advance_week
from tests.test_assignments import make_state


def squad(n: int = 16):
    state = make_state(3)
    state.athletes = state.athletes[:n]
    for a in state.athletes:
        a.relationships = {}
    return state


def calm(state):
    """Tutte le coppie a zero: nessuna amicizia né rivalità."""
    for a, b in combinations(state.main_squad, 2):
        set_relation(a, b, 0)


class TestInitialValue(unittest.TestCase):
    def test_symmetric_and_deterministic(self) -> None:
        for a in range(1, 30):
            for b in range(a + 1, 31):
                self.assertEqual(initial_value(a, b), initial_value(b, a))
                self.assertEqual(initial_value(a, b), initial_value(a, b))

    def test_values_are_nothing_or_a_friendship_or_a_rivalry_in_range(self) -> None:
        for a, b in combinations(range(1, 80), 2):
            v = initial_value(a, b)
            if v:
                self.assertTrue(RELATION_STRENGTH_MIN <= abs(v) <= RELATION_STRENGTH_MAX, v)
                self.assertTrue(is_friend(v) or is_rival(v))

    def test_the_shares_of_friends_and_rivals_are_close_to_the_configured_ones(self) -> None:
        values = [initial_value(a, b) for a, b in combinations(range(1, 120), 2)]
        friends = sum(1 for v in values if v > 0) / len(values)
        rivals = sum(1 for v in values if v < 0) / len(values)
        self.assertAlmostEqual(friends, 0.12, delta=0.03)
        self.assertAlmostEqual(rivals, 0.06, delta=0.03)

    def test_it_never_uses_the_random_generators(self) -> None:
        random.seed(2)
        before = random.getstate()
        initial_value(3, 9)
        self.assertEqual(random.getstate(), before)


class TestEnsure(unittest.TestCase):
    def test_every_pair_of_the_main_squad_gets_an_entry_in_both_athletes(self) -> None:
        state = squad(12)
        created = ensure_relationships(state)
        self.assertEqual(created, 12 * 11 // 2)
        for a, b in combinations(state.main_squad, 2):
            self.assertEqual(a.relationships[b.id], b.relationships[a.id])
            self.assertEqual(a.relationships[b.id], initial_value(a.id, b.id))

    def test_it_is_idempotent_and_keeps_changed_values(self) -> None:
        state = squad(8)
        ensure_relationships(state)
        a, b = state.main_squad[:2]
        set_relation(a, b, -77)
        self.assertEqual(ensure_relationships(state), 0)
        self.assertEqual(relation_between(a, b), -77)
        self.assertEqual(relation_between(b, a), -77)

    def test_a_pair_that_reached_zero_is_not_rerolled(self) -> None:
        state = squad(8)
        ensure_relationships(state)
        a, b = state.main_squad[:2]
        set_relation(a, b, 0)
        ensure_relationships(state)
        self.assertEqual(relation_between(a, b), 0)

    def test_the_youth_squad_is_left_out_and_a_newcomer_gets_new_pairs_only(self) -> None:
        state = squad(8)
        state.athletes[0].in_youth_squad = True
        ensure_relationships(state)
        self.assertEqual(state.athletes[0].relationships, {})
        state.athletes[0].in_youth_squad = False  # promosso
        created = ensure_relationships(state)
        self.assertEqual(created, 7)

    def test_entries_towards_athletes_that_left_are_dropped(self) -> None:
        state = squad(6)
        ensure_relationships(state)
        gone = state.athletes.pop()
        self.assertTrue(any(gone.id in a.relationships for a in state.athletes))
        ensure_relationships(state)
        self.assertFalse(any(gone.id in a.relationships for a in state.athletes))

    def test_an_asymmetric_old_entry_is_made_symmetric(self) -> None:
        state = squad(4)
        a, b = state.main_squad[:2]
        a.relationships[b.id] = 50
        ensure_relationships(state)
        self.assertEqual((relation_between(a, b), relation_between(b, a)), (50, 50))


class TestRelayChemistry(unittest.TestCase):
    def legs(self, values):
        """Quattro frazioni; `values` = relazioni (a,b) in ordine di combinazioni (6 coppie)."""
        state = squad(4)
        calm(state)
        for (a, b), v in zip(combinations(state.main_squad, 2), values):
            set_relation(a, b, v)
        return state.main_squad

    def test_no_relationship_no_bonus(self) -> None:
        self.assertEqual(relay_chemistry_bonus(self.legs([0] * 6)), 0)

    def test_a_friendship_gives_plus_ten(self) -> None:
        self.assertEqual(relay_chemistry_bonus(self.legs([60, 0, 0, 0, 0, 0])), RELAY_FRIEND_HARMONY)
        self.assertEqual(RELAY_FRIEND_HARMONY, 10)

    def test_a_rivalry_gives_minus_ten(self) -> None:
        self.assertEqual(relay_chemistry_bonus(self.legs([0, 0, 0, -45, 0, 0])), RELAY_RIVAL_HARMONY)
        self.assertEqual(RELAY_RIVAL_HARMONY, -10)

    def test_several_pairs_of_the_same_kind_do_not_stack(self) -> None:
        self.assertEqual(relay_chemistry_bonus(self.legs([60, 70, 80, 0, 0, 0])), RELAY_FRIEND_HARMONY)

    def test_friend_and_rival_in_the_same_team_cancel_out(self) -> None:
        self.assertEqual(relay_chemistry_bonus(self.legs([60, 0, 0, 0, 0, -60])), 0)

    def test_acquaintances_below_the_threshold_do_not_count(self) -> None:
        low = RELATION_FRIEND_MIN - 1
        self.assertEqual(relay_chemistry_bonus(self.legs([low, 0, 0, 0, 0, RELATION_RIVAL_MAX + 1])), 0)

    def test_friends_who_do_not_run_together_do_not_help(self) -> None:
        state = squad(6)
        calm(state)
        a, b, c, d, e, f = state.main_squad
        set_relation(e, f, 80)
        self.assertEqual(relay_chemistry_bonus([a, b, c, d]), 0)


class TestTeamChemistry(unittest.TestCase):
    def test_neutral_without_relationships(self) -> None:
        state = squad(10)
        calm(state)
        self.assertEqual((net_pairs(state), team_chemistry_form_bonus(state)), (0, 0))

    def test_friendships_raise_and_rivalries_lower_the_bonus_within_the_cap(self) -> None:
        state = squad(16)
        calm(state)
        pairs = list(combinations(state.main_squad, 2))
        for a, b in pairs[:8]:
            set_relation(a, b, 60)
        self.assertEqual(net_pairs(state), 8)
        self.assertEqual(team_chemistry_form_bonus(state), 2)
        for a, b in pairs[8:40]:
            set_relation(a, b, 60)
        self.assertEqual(team_chemistry_form_bonus(state), CHEMISTRY_FORM_MAX)
        for a, b in pairs:
            set_relation(a, b, -60)
        self.assertEqual(team_chemistry_form_bonus(state), -CHEMISTRY_FORM_MAX)

    def test_the_bonus_moves_everybody_s_form_target(self) -> None:
        athlete = generate_initial_roster(rng=random.Random(1))[0]
        athlete.personality = Personality.LEADER
        athlete.training_focus = TrainingFocus.EXPLOSIVE_POWER
        athlete.periodization = PeriodizationPhase.PREP_SPECIFICA
        athlete.fatigue, athlete.form, athlete.injured_weeks = 10, 70, 0
        base = _recalculate_form(athlete, False, False, False, False)
        better = _recalculate_form(athlete, False, False, False, False, chemistry_bonus=3)
        worse = _recalculate_form(athlete, False, False, False, False, chemistry_bonus=-3)
        self.assertGreater(better, base)
        self.assertLess(worse, base)
        self.assertEqual(_recalculate_form(athlete, False, False, False, False, chemistry_bonus=0), base)


class TestBond(unittest.TestCase):
    def test_running_together_brings_teammates_closer_once_per_pair(self) -> None:
        state = squad(6)
        calm(state)
        ids = [a.id for a in state.main_squad[:4]]
        done: set = set()
        self.assertEqual(bond_relay_teammates(state, [ids], done), 6)
        self.assertEqual(bond_relay_teammates(state, [ids], done), 0)  # la stessa coppia in un'altra staffetta: non due volte
        a, b = state.main_squad[:2]
        self.assertEqual(relation_between(a, b), RELATION_BOND_PER_RELAY)
        self.assertEqual(relation_between(b, a), RELATION_BOND_PER_RELAY)
        c = state.main_squad[5]
        self.assertEqual(relation_between(a, c), 0)

    def test_it_is_capped_at_one_hundred(self) -> None:
        state = squad(4)
        a, b = state.main_squad[:2]
        set_relation(a, b, 99)
        bond_relay_teammates(state, [[a.id, b.id]])
        self.assertEqual(relation_between(a, b), 100)


class TestReading(unittest.TestCase):
    def test_relations_of_lists_nonzero_ones_best_first(self) -> None:
        state = squad(5)
        calm(state)
        me, x, y, z, _ = state.main_squad
        set_relation(me, x, -50)
        set_relation(me, y, 70)
        set_relation(me, z, 40)
        self.assertEqual([(o.name, v) for o, v in relations_of(state, me)], [(y.name, 70), (z.name, 40), (x.name, -50)])

    def test_labels(self) -> None:
        self.assertEqual(relation_label(60), "Amicizia")
        self.assertEqual(relation_label(-60), "Rivalità")
        self.assertEqual(relation_label(10), "Conoscenza")
        self.assertEqual(relation_label(-10), "Attrito")

    def test_json_roundtrip_keeps_zeros_and_clamps(self) -> None:
        self.assertEqual(relationships_from_json(relationships_to_json({3: 50, 5: 0, 7: -20})), {3: 50, 5: 0, 7: -20})
        self.assertEqual(relationships_from_json('{"1": 250, "2": -250}'), {1: 100, 2: -100})
        for raw in (None, "", "x", "[1]", "7"):
            self.assertEqual(relationships_from_json(raw), {})


class TestTick(unittest.TestCase):
    def test_the_first_tick_creates_the_relationships_and_later_ticks_keep_them(self) -> None:
        state = make_state(3)
        state.week = 1
        for a in state.athletes:
            a.relationships = {}
        state.pending_dilemma = None
        advance_week(state, rng=random.Random(1))
        pairs = len(state.main_squad) * (len(state.main_squad) - 1) // 2
        self.assertEqual(sum(len(a.relationships) for a in state.main_squad), 2 * pairs)
        snapshot = {a.id: dict(a.relationships) for a in state.athletes}
        state.pending_dilemma = None
        advance_week(state, rng=random.Random(2))
        for a in state.athletes:  # solo i legami di staffetta possono essere cambiati (+2), mai creati o tolti
            self.assertEqual(set(a.relationships), set(snapshot[a.id]))

    def test_ensure_and_the_bonuses_never_touch_the_random_generators(self) -> None:
        state = squad(10)
        random.seed(4)
        before = random.getstate()
        ensure_relationships(state)
        team_chemistry_form_bonus(state)
        relay_chemistry_bonus(state.main_squad[:4])
        self.assertEqual(random.getstate(), before)


class TestRelayRace(unittest.TestCase):
    """L'affiatamento in gara cambia davvero il tempo della staffetta: a parità di estrazioni, amici più veloci di rivali."""

    def relay_marks(self, value: int, seed: int):
        from models.simulation import simulate_competition

        state = make_state(3)
        state.week = 4
        ensure_relationships(state)
        for a, b in combinations(state.main_squad, 2):
            set_relation(a, b, value)
        rng = random.Random(seed)
        summary = simulate_competition(state, rng=rng)
        marks = {}
        for res in summary.event_results:
            if res.event_name.startswith("4x") and not res.disqualified:
                player = next(s for s in res.standings if s.is_player)
                marks[(res.event_name, res.gender)] = player.mark_value
        return marks

    def test_the_relay_harmony_alone_is_enough_to_make_the_difference(self) -> None:
        """Con la chimica di squadra spenta resta solo il ±10 di affiatamento della staffetta."""
        from unittest import mock

        with mock.patch("models.simulation.team_chemistry_form_bonus", return_value=0):
            totals = {"friends": {}, "rivals": {}}
            for seed in range(40):
                for label, value in (("friends", 80), ("rivals", -80)):
                    for key, mark in self.relay_marks(value, seed).items():
                        totals[label].setdefault(key, []).append(mark)
        for key in set(totals["friends"]) & set(totals["rivals"]):
            f, r = totals["friends"][key], totals["rivals"][key]
            self.assertLess(sum(f) / len(f), sum(r) / len(r), key)

    def test_friends_run_faster_than_rivals_on_average(self) -> None:
        """Statistico su 40 semi (le gare individuali prima delle staffette non consumano sempre le stesse estrazioni)."""
        totals = {"friends": {}, "rivals": {}}
        for seed in range(40):
            for label, value in (("friends", 80), ("rivals", -80)):
                for key, mark in self.relay_marks(value, seed).items():
                    totals[label].setdefault(key, []).append(mark)
        keys = set(totals["friends"]) & set(totals["rivals"])
        self.assertTrue(keys)
        for key in keys:
            f, r = totals["friends"][key], totals["rivals"][key]
            self.assertLess(sum(f) / len(f), sum(r) / len(r), key)  # tempo più basso = più veloce


if __name__ == "__main__":
    unittest.main()
