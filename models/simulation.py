"""Simulation engine for periodization, recovery, wind-aware meets, economy, and seasons."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from models.entities import (
    ATTITUDE_EFFECTS,
    COACH_BASE_SKILL,
    COACH_COMFORT_LOAD,
    COACH_NO_COACH_MULT,
    RELAY_DQ_MARK,
    RIVAL_RACE_SIGMA,
    RIVAL_RETIREMENT_AGE,
    RIVAL_TREND_SNAPSHOTS,
    PROMOTION_SPOTS,
    RELEGATION_SPOTS,
    SeasonEndResult,
    SeasonOutcome,
    RivalClub,
    RELAY_LEG_WEIGHTS,
    RELAYS,
    Coach,
    Relay,
    RelayDefinition,
    harmony_grade,
    BANKRUPTCY_THRESHOLD,
    DEBT_WEEKLY_INTEREST,
    DNF_MARK,
    EVENTS,
    GYM_TRAINING_BONUS_PER_LEVEL,
    GYM_UPKEEP_PER_LEVEL,
    TEAM_POINTS,
    TICKET_PRICE,
    TIER_CONFIG,
    YOUTH_TRAINING_MULT,
    RaceAttitude,
    Athlete,
    CompetitionSummary,
    CompetitionTier,
    EthicalDilemma,
    EventDefinition,
    EventResult,
    EventStanding,
    GameState,
    PeriodizationPhase,
    Personality,
    SeasonPhase,
    Specialty,
    StaffRole,
    TrainingFocus,
    Transaction,
    WeatherCondition,
)
from models.generator import (
    build_default_lineup,
    clamp_stat,
    get_meet_name,
    SPECIALTY_COACH_FOCUS,
    create_rival_clubs,
    generate_coach,
    generate_rival_athlete,
    maybe_generate_dilemma,
    senior_wage,
)


@dataclass
class WeekAdvanceReport:
    """Outcome summary returned after advancing one in-game week."""

    completed_week: int
    new_week: int
    weekly_income: int
    weekly_wages: int
    staff_cost: int
    travel_cost: int
    injuries: List[str]
    recoveries: List[str]
    stat_gains: List[str]
    doping_scandals: List[str]
    competition_summary: Optional[CompetitionSummary] = None
    triggered_dilemma: Optional[EthicalDilemma] = None
    season_end: Optional[SeasonEndResult] = None


def _hired_roles(state: GameState) -> Set[StaffRole]:
    return {s.role for s in state.staff if s.hired}


def coach_load_multiplier(load: int) -> float:
    """A coach follows up to COACH_COMFORT_LOAD athletes well; beyond that attention is diluted."""
    if load <= COACH_COMFORT_LOAD:
        return 1.0
    return max(0.5, 1.0 - 0.08 * (load - COACH_COMFORT_LOAD))


def auto_assign_coach(state: GameState, athlete: Athlete) -> Optional[Coach]:
    """Give the athlete the least-busy suitable coach, unless they already have one."""
    current = state.coach_of(athlete)
    if current is not None:
        return current
    candidates = [c for c in state.coaches if c.can_train(athlete)]
    if not candidates:
        athlete.coach_id = None
        return None
    best = min(candidates, key=lambda c: (state.coach_load(c), -max(c.skills.values())))
    athlete.coach_id = best.id
    return best


# ---------------------------------------------------------------- body build
# Ideal build per event: (height cm, height mode, BMI, BMI mode).
# Modes: "near" = best at the ideal, penalised on both sides; "min" = more is never worse.
BODY_IDEALS: Dict[str, Tuple[int, str, float, str]] = {
    "100m": (183, "near", 22.8, "near"),
    "400m": (181, "near", 21.6, "near"),
    "1500m": (176, "near", 20.4, "near"),
    "Salto in Lungo": (184, "min", 21.6, "near"),
    "Getto del Peso": (189, "min", 27.5, "min"),
}
BODY_IDEALS_F: Dict[str, Tuple[int, str, float, str]] = {
    "100m": (172, "near", 21.3, "near"),
    "400m": (171, "near", 20.3, "near"),
    "1500m": (166, "near", 19.2, "near"),
    "Salto in Lungo": (174, "min", 20.4, "near"),
    "Getto del Peso": (178, "min", 26.0, "min"),
}
BODY_MOD_MAX = 1.2  # best possible bonus (race-score points)
BODY_MOD_MIN = -4.0  # worst possible penalty


def body_modifier(athlete: Athlete, event_name: str) -> float:
    """Race-score bonus/penalty for how well height and weight suit the event."""
    ideals = BODY_IDEALS_F if getattr(athlete, "gender", "M") == "F" else BODY_IDEALS
    ideal = ideals.get(event_name)
    if ideal is None or not athlete.height_cm or not athlete.weight_kg:
        return 0.0
    ideal_h, h_mode, ideal_bmi, b_mode = ideal
    bmi = athlete.weight_kg / (athlete.height_cm / 100) ** 2
    dh = (athlete.height_cm - ideal_h) / 6.0  # ~1 standard deviation of the generator
    db = (bmi - ideal_bmi) / 1.0
    if h_mode == "min":
        dh = min(0.0, dh)
    if b_mode == "min":
        db = min(0.0, db)
    penalty = 0.7 * (abs(dh) + abs(db))
    return max(BODY_MOD_MIN, min(BODY_MOD_MAX, 1.2 - penalty))


def body_fit_score(athlete: Athlete) -> int:
    """0-100 rating of how well the build suits the athlete's own discipline (best event)."""
    mods = [
        body_modifier(athlete, name)
        for name, ev in EVENTS.items()
        if ev.specialty == athlete.specialty
    ]
    if not mods:
        return 50
    best = max(mods)
    return round((best - BODY_MOD_MIN) / (BODY_MOD_MAX - BODY_MOD_MIN) * 100)


# ---------------------------------------------------------------- relays
def relay_leg_score(athlete: Athlete, rdef: RelayDefinition) -> float:
    """How good an athlete is as a relay leg (attributes, form, fatigue and, a bit, build)."""
    base = sum(getattr(athlete, attr) * w for attr, w in rdef.leg_weights.items())
    build = body_modifier(athlete, rdef.requires_event) * 0.5
    return base + (athlete.form - 60) * 0.15 - max(0, athlete.fatigue - 62) * 0.2 + build


def auto_build_relay(
    state: GameState, event: str, with_reserve: bool = True, gender: str = "M"
) -> Relay:
    """Pick the 4 best available legs of a division (best runner on anchor) plus a reserve."""
    rdef = RELAYS[event]
    relays = state.relays_for(gender)
    relay = relays.get(event) or Relay(event=event)
    taken = {aid for name, r in relays.items() if name != event for aid in r.all_ids()}
    pool = [
        a for a in state.main_squad
        if a.gender == gender and a.id is not None and not a.is_injured and a.id not in taken
    ]
    pool.sort(key=lambda a: relay_leg_score(a, rdef), reverse=True)
    best = pool[:5] if with_reserve else pool[:4]
    legs: List[Optional[int]] = [a.id for a in best[:4]]
    if len(legs) == 4:
        legs = [legs[1], legs[2], legs[3], legs[0]]  # strongest runner anchors
    legs += [None] * (4 - len(legs))
    old = set(relay.all_ids())
    new_ids = [a.id for a in best]
    relay.member_ids = legs
    relay.reserve_id = best[4].id if len(best) > 4 else None
    if old and set(new_ids) != old:
        relay.harmony = int(relay.harmony * 0.75)
        relay.last_change_week = state.week
    relays[event] = relay
    return relay


def auto_build_all_relays(state: GameState, gender: Optional[str] = None) -> None:
    """Compose active relays (M and F unless gender is specified): legs first, then reserves."""
    genders = (gender,) if gender in ("M", "F") else ("M", "F")
    for g in genders:
        relays = state.relays_for(g)
        for name in state.active_relays:
            auto_build_relay(state, name, with_reserve=False, gender=g)
        for name in state.active_relays:
            relay = relays[name]
            taken = {aid for r in relays.values() for aid in r.all_ids()}
            rdef = RELAYS[name]
            spare = [
                a for a in state.main_squad
                if a.gender == g and a.id is not None and not a.is_injured and a.id not in taken
            ]
            if spare:
                relay.reserve_id = max(spare, key=lambda a: relay_leg_score(a, rdef)).id


def _relay_dq_chance(harmony: int, substituted: bool) -> float:
    return max(0.0, (60 - harmony) * 0.006) + (0.03 if substituted else 0.0)


def _relay_mark(rdef: RelayDefinition, score: float, gender: str = "M") -> Tuple[float, str]:
    norm = max(0.15, min(1.18, score / 100.0))
    if gender == "F" and rdef.base_seconds_f > 0:
        base_s, span_s, min_s = rdef.base_seconds_f, rdef.span_seconds_f, rdef.min_seconds_f
    else:
        base_s, span_s, min_s = rdef.base_seconds, rdef.span_seconds, rdef.min_seconds
    seconds = max(min_s, base_s - norm * span_s)
    if seconds >= 60:
        mins = int(seconds // 60)
        return seconds, f"{mins}:{seconds % 60:05.2f}"
    return seconds, f"{seconds:.2f}s"


def _update_relay_harmony(state: GameState, raced: Set) -> None:
    """Relay teams gel by training together; incomplete or injured teams lose harmony."""
    by_id = {a.id: a for a in state.athletes}

    def fit(aid: Optional[int]) -> bool:
        a = by_id.get(aid) if aid is not None else None
        return a is not None and not a.is_injured and not a.in_youth_squad

    for gender in ("M", "F"):
        for name, relay in state.relays_for(gender).items():
            did_race = (name, gender) in raced or (gender == "M" and name in raced)
            missing = sum(1 for mid in relay.member_ids if not fit(mid))
            if missing == 0:
                relay.harmony += 4 + (6 if did_race else 0)
            elif missing == 1 and fit(relay.reserve_id):
                relay.harmony += 2 + (6 if did_race else 0)  # the reserve fills in at practice
            else:
                relay.harmony -= 2
            relay.harmony = max(0, min(100, relay.harmony))


def _recalculate_form(
    athlete: Athlete,
    rested: bool,
    tapering: bool,
    has_mental_coach: bool,
    leader_present: bool,
) -> int:
    """Recalculate athlete Form (1-100) from fatigue, sleep, nutrition, and tapering."""
    lifestyle_bonus = ((athlete.sleep_quality + athlete.nutrition) / 2.0 - 70.0) * 0.18
    if athlete.is_injured:
        target_form = max(15, 42 - athlete.fatigue * 0.3)
    elif athlete.fatigue >= 80:
        target_form = 48 - (athlete.fatigue - 70) * 1.25
    elif athlete.fatigue >= 58:
        target_form = 74 - (athlete.fatigue - 52) * 0.75
    else:
        target_form = 86 - athlete.fatigue * 0.32

    if rested and not athlete.is_injured:
        target_form += 6
    if tapering and not athlete.is_injured:
        target_form += 9
    if has_mental_coach:
        target_form += 4
    if leader_present:
        target_form += 2
    if athlete.doping_boost_weeks > 0:
        target_form += 10

    target_form += lifestyle_bonus
    blended = athlete.form * 0.35 + target_form * 0.65
    return clamp_stat(blended, 5, 100)


def apply_weekly_training(
    athlete: Athlete,
    hired_roles: Optional[Set[StaffRole]] = None,
    leader_present: bool = False,
    rng: Optional[random.Random] = None,
    gym_level: int = 0,
    coach: Optional[Coach] = None,
    coach_load: int = 1,
) -> Tuple[List[str], Optional[str], Optional[str], Optional[str]]:
    """
    Update a single athlete's stats, fatigue, form, and injury status for one week.

    Skill gains depend on the assigned coach's skill in the trained attribute and on how
    many athletes that coach is following; without a suitable coach growth is much slower.

    Returns:
        (stat_gains, injury_note, recovery_note, doping_scandal_note)
    """
    r = rng or random.Random()
    roles = hired_roles or set()
    gains: List[str] = []
    injury_note: Optional[str] = None
    recovery_note: Optional[str] = None
    scandal_note: Optional[str] = None

    has_physio = StaffRole.PHYSIO in roles
    has_doctor = StaffRole.DOCTOR in roles
    has_mental = StaffRole.MENTAL_COACH in roles

    # Anti-doping check if pharmacological shortcut active
    if athlete.doping_boost_weeks > 0:
        athlete.doping_boost_weeks -= 1
        if r.random() < 0.24:
            athlete.injured_weeks = 4
            athlete.doping_boost_weeks = 0
            athlete.form = 25
            scandal_note = (
                f"SCANDALO DOPING: {athlete.name} è risultato positivo al controllo! "
                "Squalifica di 4 settimane e grave danno d'immagine."
            )
            return gains, injury_note, recovery_note, scandal_note

    if athlete.is_injured:
        heal_step = 2 if (has_physio and athlete.injured_weeks > 1 and r.random() < 0.55) else 1
        athlete.injured_weeks = max(0, athlete.injured_weeks - heal_step)
        rec_amt = r.randint(22, 30) + (8 if has_physio else 0)
        athlete.fatigue = clamp_stat(athlete.fatigue - rec_amt, 0, 100)
        athlete.form = _recalculate_form(athlete, True, False, has_mental, leader_present)
        if athlete.injured_weeks == 0:
            recovery_note = f"{athlete.name} ha recuperato dall'infortunio ed è tornato in pista."
        return gains, injury_note, recovery_note, scandal_note

    focus = athlete.training_focus
    period = athlete.periodization
    low_peak, high_peak = athlete.specialty.peak_age_range

    # Age growth factor: young athletes develop rapidly toward potential
    if athlete.age < low_peak:
        age_factor = 1.30
    elif athlete.age <= high_peak:
        age_factor = 1.00
    else:
        age_factor = 0.65

    load_mult = coach_load_multiplier(coach_load)

    def coach_bonus(stat_name: str) -> float:
        if coach is None or not coach.can_train(athlete):
            return COACH_NO_COACH_MULT
        return (0.6 + coach.skill_for(stat_name) / 100.0 * 0.8) * load_mult

    personality_growth = 1.15 if athlete.personality == Personality.PERFEZIONISTA else 1.0
    facility_growth = 1.0 + gym_level * GYM_TRAINING_BONUS_PER_LEVEL
    if athlete.in_youth_squad:
        facility_growth *= YOUTH_TRAINING_MULT
    period_growth = {
        PeriodizationPhase.PREP_GENERALE: 1.05,
        PeriodizationPhase.PREP_SPECIFICA: 1.25,
        PeriodizationPhase.GARA: 0.90,
        PeriodizationPhase.SCARICO: 0.45,
    }[period]

    def try_improve(stat_name: str, base_chance: float, max_gain: int = 2) -> None:
        current = getattr(athlete, stat_name)
        cap = min(99, max(current, athlete.potential))
        if current >= cap:
            return
        headroom = max(0.20, (cap - current) / 45.0)
        chance = min(
            0.95,
            base_chance * age_factor * coach_bonus(stat_name) * personality_growth * period_growth * facility_growth * headroom
        )
        if r.random() < chance:
            delta = 2 if (max_gain >= 2 and r.random() < 0.25 and current < cap - 3) else 1
            setattr(athlete, stat_name, clamp_stat(current + delta, 1, cap))
            gains.append(f"{athlete.name}: +{delta} {stat_name.capitalize()}")

    rested = focus == TrainingFocus.REST
    tapering = period == PeriodizationPhase.SCARICO

    if focus == TrainingFocus.ENDURANCE:
        try_improve("stamina", 0.70, max_gain=2)
        try_improve("resilience", 0.28, max_gain=1)
        if athlete.specialty == Specialty.MIDDLE_DISTANCE:
            try_improve("speed", 0.25, max_gain=1)
        fatigue_add = r.randint(11, 16)
    elif focus == TrainingFocus.EXPLOSIVE_POWER:
        try_improve("speed", 0.56, max_gain=2)
        try_improve("strength", 0.56, max_gain=2)
        fatigue_add = r.randint(13, 19)
    elif focus == TrainingFocus.TECHNIQUE:
        try_improve("technique", 0.72, max_gain=2)
        try_improve("speed", 0.22, max_gain=1)
        fatigue_add = r.randint(9, 14)
    else:  # TrainingFocus.REST
        fatigue_add = -r.randint(24, 32)

    # Periodization load modulation
    if period == PeriodizationPhase.PREP_SPECIFICA and not rested:
        fatigue_add += 4
    elif period == PeriodizationPhase.GARA and not rested:
        fatigue_add += 2
    elif tapering:
        fatigue_add = min(fatigue_add - 14, -10)

    # Perfectionists push harder; sleep, nutrition & physio aid recovery
    if athlete.personality == Personality.PERFEZIONISTA and not rested and not tapering:
        fatigue_add += 2
    if has_physio:
        fatigue_add -= 7
    recovery_lifestyle = int(((athlete.sleep_quality + athlete.nutrition) / 2.0 - 70.0) * 0.12)
    fatigue_add -= recovery_lifestyle

    athlete.fatigue = clamp_stat(athlete.fatigue + fatigue_add, 0, 100)
    athlete.form = _recalculate_form(athlete, rested, tapering, has_mental, leader_present)

    # Veterans past their peak window slowly lose physical qualities
    years_past_peak = athlete.age - (high_peak + 1)
    if years_past_peak > 0 and r.random() < min(0.5, 0.10 * years_past_peak):
        stat_name = r.choice(["speed", "stamina", "strength"])
        current = getattr(athlete, stat_name)
        if current > 1:
            setattr(athlete, stat_name, current - 1)
            gains.append(f"{athlete.name}: -1 {stat_name.capitalize()} (età)")

    # Injury risk check when overloaded
    if not rested and not tapering and athlete.fatigue >= 68:
        resilience_factor = max(0.35, 1.35 - athlete.resilience / 100.0)
        impulsive_mult = 1.25 if (athlete.personality == Personality.IMPULSIVO and not has_mental) else 1.0
        doctor_mult = 0.55 if has_doctor else 1.0
        youth_mult = 1.25 if athlete.age <= 17 else 1.0
        injury_prob = min(
            0.50,
            (athlete.fatigue - 64) * 0.011 * resilience_factor * impulsive_mult * doctor_mult * youth_mult,
        )
        if r.random() < injury_prob:
            base_weeks = r.randint(1, 3)
            if has_physio and base_weeks > 1:
                base_weeks -= 1
            athlete.injured_weeks = base_weeks
            athlete.form = clamp_stat(athlete.form - 18, 5, 100)
            injury_note = (
                f"{athlete.name} ha subito uno stiramento muscolare (Fatica {athlete.fatigue}) "
                f"— stop di {athlete.injured_weeks} sett."
            )

    return gains, injury_note, recovery_note, scandal_note


def _score_to_mark(
    event_def: EventDefinition,
    performance_score: float,
    wind_ms: Optional[float] = None,
    gender: str = "M",
) -> Tuple[float, str]:
    """Convert a composite performance score + wind into realistic athletics marks."""
    norm = max(0.15, min(1.18, performance_score / 100.0))

    if event_def.name == "100m":
        if gender == "F":
            seconds = 14.15 - norm * 3.25
            if wind_ms is not None:
                seconds -= wind_ms * 0.055
            seconds = max(10.49, seconds)
        else:
            seconds = 12.95 - norm * 3.16
            if wind_ms is not None:
                # Tailwind helps (~0.05s per 1.0 m/s), headwind slows
                seconds -= wind_ms * 0.055
            seconds = max(9.58, seconds)
        return seconds, f"{seconds:.2f}s"

    if event_def.name == "400m":
        seconds = (
            max(47.60, 68.50 - norm * 20.60)
            if gender == "F"
            else max(43.10, 60.60 - norm * 17.60)
        )
        return seconds, f"{seconds:.2f}s"

    if event_def.name == "1500m":
        total_seconds = (
            max(229.0, 362.0 - norm * 142.0)
            if gender == "F"
            else max(206.0, 312.0 - norm * 114.0)
        )
        mins = int(total_seconds // 60)
        secs = total_seconds % 60
        return total_seconds, f"{mins}:{secs:05.2f}"

    if event_def.name == "Salto in Lungo":
        meters = (4.60 + norm * 2.65) if gender == "F" else (5.30 + norm * 3.10)
        if wind_ms is not None:
            meters += wind_ms * 0.08
        return meters, f"{meters:.2f}m"

    meters = (10.20 + norm * 9.80) if gender == "F" else (11.40 + norm * 10.60)
    return meters, f"{meters:.2f}m"


def _compute_athlete_event_score(
    athlete: Athlete,
    event_def: EventDefinition,
    weather: WeatherCondition,
    track_condition: int,
    has_mental_coach: bool,
    rng: random.Random,
) -> float:
    """Calculate simulated performance score from attributes, form, personality, weather & track."""
    weather_mod = -1.8 if weather == WeatherCondition.PIOGGIA else (-0.8 if weather == WeatherCondition.CALDO else 0.0)
    doping_mod = 6.5 if athlete.doping_boost_weeks > 0 else 0.0

    # Impulsive athletes have wilder swings unless coached mentally
    sigma = 5.6 if (athlete.personality == Personality.IMPULSIVO and not has_mental_coach) else 3.8
    if athlete.personality == Personality.PERFEZIONISTA:
        sigma = 3.0
    variance = rng.gauss(0.0, sigma)

    expected = expected_event_score(athlete, event_def, track_condition)
    return expected + weather_mod + doping_mod + variance


def expected_event_score(athlete: Athlete, event_def: EventDefinition, track_condition: int = 75) -> float:
    """Race score an athlete would post on an average day (same scale as rival levels)."""
    base_skill = sum(getattr(athlete, k) * w for k, w in event_def.weights.items())
    specialty_bonus = 4.0 if athlete.specialty == event_def.specialty else -3.5
    form_modifier = (athlete.form - 60) * 0.24
    fatigue_penalty = max(0, athlete.fatigue - 62) * 0.26
    track_mod = (track_condition - 75) * 0.06
    build_mod = body_modifier(athlete, event_def.name)
    return base_skill + specialty_bonus + form_modifier - fatigue_penalty + track_mod + build_mod


def _roll_meet_wind(weather: WeatherCondition, season_phase: SeasonPhase, rng: random.Random) -> float:
    """Roll realistic wind speed in m/s (Indoor = 0.0)."""
    if season_phase == SeasonPhase.INDOOR:
        return 0.0
    if weather == WeatherCondition.VENTOSO:
        return round(rng.uniform(0.6, 3.3), 1)
    if weather == WeatherCondition.PIOGGIA:
        return round(rng.uniform(-1.4, 1.5), 1)
    return round(rng.uniform(-0.8, 2.5), 1)


def _evaluate_objectives(state: GameState, summary: Optional[CompetitionSummary] = None) -> None:
    """Update completion state of seasonal objectives."""
    for obj in state.objectives:
        if obj.key == "positive_budget":
            threshold = 8000 if state.game_mode == "vertical_slice" else 10000
            obj.completed = state.budget >= threshold
        elif obj.key == "win_event" and summary is not None:
            if any(er.placement == 1 for er in summary.event_results):
                obj.completed = True
        elif obj.key == "club_record" and summary is not None:
            if any(er.is_club_record for er in summary.event_results):
                obj.completed = True
        elif obj.key == "promote":
            if state.tier != CompetitionTier.PROVINCIALE:
                obj.completed = True
        elif obj.key == "historic_mark" and summary is not None:
            for er in summary.event_results:
                ev = EVENTS.get(er.event_name)
                if ev is None:  # relays have no historic benchmark
                    continue
                player_st = next((s for s in er.standings if s.is_player), None)
                if player_st and not er.wind_illegal:
                    if (ev.lower_is_better and player_st.mark_value < ev.historic_mark) or (
                        not ev.lower_is_better and player_st.mark_value > ev.historic_mark
                    ):
                        obj.completed = True


def _is_better(event_def: EventDefinition, new: float, old: float) -> bool:
    return new < old if event_def.lower_is_better else new > old


def _compute_ticket_income(
    state: GameState, weather: WeatherCondition, rng: random.Random
) -> Tuple[int, int]:
    """Spectators & ticket income for a home meet (capped by stand capacity)."""
    demand = (300 + state.prestige * 4 + state.tier.order * 900) * (0.6 + state.reputation / 250.0)
    if weather == WeatherCondition.PIOGGIA and state.season_phase != SeasonPhase.INDOOR:
        demand *= 0.7
    demand *= rng.uniform(0.85, 1.15)
    spectators = int(min(state.stand_seats, max(0.0, demand)))
    return spectators, spectators * TICKET_PRICE[state.tier.value]


def _rival_only_points(
    clubs: List[RivalClub],
    event: str,
    team_points: Dict[str, int],
    rng: random.Random,
    gender: str = "M",
) -> None:
    """When the club enters nobody in an event, the rivals still score among themselves."""
    def day_score(club: RivalClub) -> float:
        athlete = club.athlete_for(event, gender)
        return rng.gauss(athlete.skill if athlete else 0.0, RIVAL_RACE_SIGMA)

    order = sorted(clubs, key=day_score, reverse=True)
    for place, club in enumerate(order, start=1):
        team_points[club.name] = team_points.get(club.name, 0) + TEAM_POINTS.get(place, 0)


# ---------------------------------------------------------------- rival development
def _weekly_rival_drift(age: int) -> float:
    """Typical weekly change of a rival's level by age: youngsters grow, veterans fade."""
    if age <= 23:
        return 0.13
    if age <= 27:
        return 0.05
    if age <= 29:
        return 0.0
    return -min(0.3, 0.08 * (age - 29))


def progress_rivals(state: GameState, rng: random.Random) -> None:
    """Every rival club in every category trains too; ambitious clubs improve faster."""
    for club in state.rival_clubs:
        for pool in (club.athletes, club.female_athletes):
            for athlete in pool.values():
                drift = _weekly_rival_drift(athlete.age)
                if drift > 0:
                    drift *= club.ambition
                athlete.skill = round(athlete.skill + drift + rng.gauss(0.0, 0.15), 2)
        if state.week % 4 == 0:
            club.history.append(round(club.level(), 2))
            club.history = club.history[-RIVAL_TREND_SNAPSHOTS:]


def renew_rivals_for_season(state: GameState, rng: random.Random) -> List[str]:
    """New season: rivals age, veterans retire and clubs sign replacements.

    Ambitious clubs raise their recruiting level, complacent ones lose ground; every
    season's recruits are slightly stronger than the last (the sport moves forward).
    Returns news lines about the player's current category.
    """
    news: List[str] = []
    for club in state.rival_clubs:
        club.offset = round(club.offset + (club.ambition - 1.0) * 1.5, 2)
        club.ambition = round(club.ambition + (1.0 - club.ambition) * 0.2, 2)  # drifts back to normal
        for gender, pool in (("M", club.athletes), ("F", club.female_athletes)):
            for event, athlete in list(pool.items()):
                athlete.age += 1
                retiring = athlete.age >= RIVAL_RETIREMENT_AGE or (athlete.age >= 31 and rng.random() < 0.3)
                if not retiring:
                    continue
                newcomer = generate_rival_athlete(
                    event, club.tier, club.offset, season=state.season_number, rng=rng, age_range=(18, 22), gender=gender
                )
                pool[event] = newcomer
                if club.tier == state.tier and len(news) < 4:
                    news.append(
                        f"Sett. {state.week}: {club.name} — si ritira {athlete.name} ({event} {gender}), "
                        f"arriva il giovane {newcomer.name}."
                    )
    return news


def _adapt_rival_ambition(state: GameState, team_points: Dict[str, int]) -> None:
    """Clubs beaten by the player invest more; clubs comfortably ahead relax a little."""
    mine = team_points.get(state.team_name, 0)
    for club in state.rivals_in():
        pts = team_points.get(club.name, 0)
        if pts < mine:
            club.ambition = min(1.6, round(club.ambition + 0.04, 2))
        elif pts > mine + 8:
            club.ambition = max(0.6, round(club.ambition - 0.02, 2))


def simulate_competition(
    state: GameState,
    rng: Optional[random.Random] = None,
) -> CompetitionSummary:
    """Simulate the current week's meet: wind, weather, race attitude, team scoring & home gate."""
    r = rng or random.Random()
    tier_cfg = TIER_CONFIG[state.tier]
    clubs = state.rivals_in()
    rivals = [c.name for c in clubs]
    roles = _hired_roles(state)
    has_mental = StaffRole.MENTAL_COACH in roles
    has_doctor = StaffRole.DOCTOR in roles
    leader_present = any(
        a.personality == Personality.LEADER and not a.is_injured for a in state.main_squad
    )
    is_home = state.next_meet_is_home

    weather = (
        WeatherCondition.SERENO
        if state.season_phase == SeasonPhase.INDOOR
        else r.choice(list(WeatherCondition))
    )
    track_surface = (
        "Tartan Ottimale"
        if state.track_condition >= 80
        else ("Tartan Standard" if state.track_condition >= 55 else "Tartan Usurato")
    )

    athlete_by_id: Dict[int, Athlete] = {
        a.id: a for a in state.main_squad if a.id is not None
    }
    fan_mult = {0: 3, 1: 6, 2: 12, 3: 25}[state.tier.order]

    event_results: List[EventResult] = []
    team_points: Dict[str, int] = {state.team_name: 0}
    for team in rivals:
        team_points.setdefault(team, 0)
    total_prize = 0
    total_prestige = 0

    for gender in ("M", "F"):
        lineup = state.lineup_for(gender)
        records = state.records_for(gender)
        for event_name in state.active_events:
            event_def = EVENTS[event_name]
            selected_id = lineup.get(event_name)
            player_athlete = athlete_by_id.get(selected_id) if selected_id is not None else None

            if player_athlete is None or player_athlete.is_injured:
                _rival_only_points(clubs, event_name, team_points, r, gender=gender)
                continue

            attitude = state.attitude_for(event_name)
            att = ATTITUDE_EFFECTS[attitude]

            wind_ms: Optional[float] = (
                _roll_meet_wind(weather, state.season_phase, r) if event_def.wind_affected else None
            )
            wind_illegal = bool(wind_ms is not None and wind_ms > 2.0)

            standings: List[EventStanding] = []

            # In-race injury check: attitude & accumulated fatigue drive the risk
            injury_chance = att["injury"] + max(0, player_athlete.fatigue - 60) * 0.004
            if has_doctor:
                injury_chance *= 0.55
            withdrew = r.random() < injury_chance

            if withdrew:
                p_val = 9999.0 if event_def.lower_is_better else 0.0
                p_disp = DNF_MARK
                weeks_out = r.randint(1, 3) + (1 if attitude == RaceAttitude.AGGRESSIVO else 0)
                player_athlete.injured_weeks = max(player_athlete.injured_weeks, weeks_out)
                player_athlete.form = clamp_stat(player_athlete.form - 15, 5, 100)
                state.news_log.insert(
                    0,
                    f"Sett. {state.week}: {player_athlete.name} si ritira nei {event_name} ({gender}) per un "
                    f"problema muscolare (atteggiamento {attitude.value}) — stop di {weeks_out} sett.",
                )
            else:
                p_score = _compute_athlete_event_score(
                    player_athlete, event_def, weather, state.track_condition, has_mental, r
                )
                p_score += att["score"]
                if att["sigma"] > 0:
                    p_score += r.gauss(0.0, att["sigma"])  # all-out efforts are less predictable
                if is_home:
                    p_score += 1.0  # home crowd
                p_val, p_disp = _score_to_mark(event_def, p_score, wind_ms, gender=gender)

            standings.append(
                EventStanding(
                    athlete_name=player_athlete.name,
                    team_name=state.team_name,
                    is_player=True,
                    mark_value=p_val,
                    mark_display=p_disp,
                    wind_ms=wind_ms,
                    wind_illegal=wind_illegal,
                )
            )

            # Match fatigue scales with attitude
            player_athlete.fatigue = clamp_stat(player_athlete.fatigue + int(att["fatigue"]), 0, 100)
            player_athlete.form = _recalculate_form(player_athlete, False, False, has_mental, leader_present)

            # One athlete per rival club in the same gender division
            for club in clubs:
                opp = club.athlete_for(event_name, gender)
                if opp is None:
                    continue
                opp_score = r.gauss(opp.skill, RIVAL_RACE_SIGMA)
                o_val, o_disp = _score_to_mark(event_def, opp_score, wind_ms, gender=gender)
                if not wind_illegal and (opp.pb is None or _is_better(event_def, o_val, opp.pb)):
                    opp.pb, opp.pb_display = o_val, o_disp
                standings.append(
                    EventStanding(
                        athlete_name=opp.name,
                        team_name=club.name,
                        is_player=False,
                        mark_value=o_val,
                        mark_display=o_disp,
                        wind_ms=wind_ms,
                        wind_illegal=wind_illegal,
                    )
                )

            standings.sort(key=lambda s: s.mark_value, reverse=not event_def.lower_is_better)
            if withdrew:
                # A withdrawn athlete is always classified last
                standings.sort(key=lambda s: s.is_player)
            player_place = 1
            for idx, standing in enumerate(standings, start=1):
                standing.placement = idx
                if standing.is_player:
                    player_place = idx
                if not (standing.is_player and withdrew):
                    team_points[standing.team_name] = team_points.get(standing.team_name, 0) + TEAM_POINTS.get(idx, 0)

            # Check PB, Club Record, and Historic Milestone (only when wind <= 2.0 m/s!)
            is_pb = False
            is_club_rec = False
            if not wind_illegal and not withdrew:
                if player_athlete.personal_best is None or _is_better(
                    event_def, p_val, player_athlete.personal_best
                ):
                    player_athlete.personal_best = p_val
                    player_athlete.personal_best_display = p_disp
                    is_pb = True

                existing_rec = records.get(event_name)
                if existing_rec is None or _is_better(event_def, p_val, existing_rec[0]):
                    records[event_name] = (p_val, p_disp, player_athlete.name)
                    is_club_rec = True
                    state.milestones.insert(
                        0,
                        f"Sett. {state.week}: Nuovo Record Sociale ({gender}) nei {event_name}! {player_athlete.name} segna {p_disp}.",
                    )

                # Historic benchmark check
                h_mark = (
                    event_def.historic_mark_f
                    if (gender == "F" and event_def.historic_mark_f is not None)
                    else event_def.historic_mark
                )
                h_label = (
                    event_def.historic_label_f
                    if (gender == "F" and event_def.historic_label_f)
                    else event_def.historic_label
                )
                if _is_better(event_def, p_val, h_mark):
                    milestone_msg = (
                        f"Sett. {state.week}: MOMENTO STORICO! {player_athlete.name} abbatte il muro "
                        f"{h_label} ({gender}) ({p_disp})!"
                    )
                    if milestone_msg not in state.milestones:
                        state.milestones.insert(0, milestone_msg)
            elif not withdrew and (
                player_athlete.personal_best is None
                or _is_better(event_def, p_val, player_athlete.personal_best)
            ):
                state.news_log.insert(
                    0,
                    f"Sett. {state.week}: {player_athlete.name} ha corso/saltato {p_disp} nei {event_name} ({gender}), "
                    f"ma con vento +{wind_ms:.1f} m/s (>2.0 m/s): non valido per il record!",
                )

            prize_multipliers = {1: 1.0, 2: 0.60, 3: 0.35, 4: 0.15}
            prestige_table = {1: 35, 2: 22, 3: 14, 4: 7, 5: 3}

            if withdrew:
                prize = 0
                prestige_gain = 0
            else:
                prize = int(tier_cfg["prize_base"] * prize_multipliers.get(player_place, 0.0))
                prestige_gain = prestige_table.get(player_place, 1) + (5 if is_club_rec else 0)
                # Fans follow athletes who place well, set PBs and break records
                fan_gain = max(0, 9 - player_place) * fan_mult + (5 if is_pb else 0) + (10 if is_club_rec else 0)
                player_athlete.fans += fan_gain

            total_prize += prize
            total_prestige += prestige_gain

            event_results.append(
                EventResult(
                    event_name=event_name,
                    player_athlete_name=player_athlete.name,
                    placement=player_place,
                    total_competitors=len(standings),
                    player_mark=p_disp,
                    prize_money=prize,
                    prestige_gained=prestige_gain,
                    wind_ms=wind_ms,
                    wind_illegal=wind_illegal,
                    is_pb=is_pb,
                    is_club_record=is_club_rec,
                    standings=standings,
                    attitude=attitude.value,
                    withdrew_injured=withdrew,
                    gender=gender,
                )
            )

    # ---- Relays: harmony, legs and baton changes (M & F); no effect on individual form or fans
    for relay_name in state.active_relays:
        rdef = RELAYS[relay_name]
        for gender in ("M", "F"):
            relay = state.relays_for(gender).get(relay_name)
            legs: List[Athlete] = []
            substituted = False
            if relay is not None:
                reserve = athlete_by_id.get(relay.reserve_id) if relay.reserve_id is not None else None
                for mid in relay.member_ids:
                    runner = athlete_by_id.get(mid) if mid is not None else None
                    if (runner is None or runner.is_injured) and reserve is not None and not reserve.is_injured:
                        runner, reserve, substituted = reserve, None, True
                    if runner is not None and not runner.is_injured:
                        legs.append(runner)
            if relay is None or len(legs) < 4:
                _rival_only_points(clubs, rdef.requires_event, team_points, r, gender=gender)
                continue

            harmony = relay.harmony - (15 if substituted else 0)
            disqualified = r.random() < _relay_dq_chance(harmony, substituted)
            if disqualified:
                p_val, p_disp = 9999.0, RELAY_DQ_MARK
            else:
                leg_scores = [relay_leg_score(a, rdef) for a in legs]
                p_score = sum(sc * w for sc, w in zip(leg_scores, RELAY_LEG_WEIGHTS))
                p_score += (harmony - 50) * 0.08 + r.gauss(0.0, 2.5)
                if is_home:
                    p_score += 1.0
                p_val, p_disp = _relay_mark(rdef, p_score, gender=gender)
            team_label = " / ".join(f"{a.name[0]}. {a.name.split(' ', 1)[-1]}" for a in legs)
            standings = [
                EventStanding(
                    athlete_name=team_label,
                    team_name=state.team_name,
                    is_player=True,
                    mark_value=p_val,
                    mark_display=p_disp,
                )
            ]
            for club in clubs:
                # A club's relay is as fast as its division sprinters in that distance
                opp_ref = club.athlete_for(rdef.requires_event, gender)
                opp_skill = opp_ref.skill if opp_ref is not None else 50.0
                o_val, o_disp = _relay_mark(rdef, r.gauss(opp_skill, 4.0), gender=gender)
                standings.append(
                    EventStanding(
                        athlete_name=f"Staffetta {club.name}",
                        team_name=club.name,
                        is_player=False,
                        mark_value=o_val,
                        mark_display=o_disp,
                    )
                )
            standings.sort(key=lambda st: st.mark_value)
            if disqualified:
                standings.sort(key=lambda st: st.is_player)
            player_place = 1
            for idx, st in enumerate(standings, start=1):
                st.placement = idx
                if st.is_player:
                    player_place = idx
                if not (st.is_player and disqualified):
                    team_points[st.team_name] = team_points.get(st.team_name, 0) + TEAM_POINTS.get(idx, 0)

            is_club_rec = False
            records = state.records_for(gender)
            if disqualified:
                prize, prestige_gain = 0, 0
                state.news_log.insert(
                    0,
                    f"Sett. {state.week}: Staffetta {relay_name} ({gender}) squalificata per cambio fuori zona "
                    f"(affiatamento {harmony_grade(max(0, harmony))}).",
                )
            else:
                existing_rec = records.get(relay_name)
                if existing_rec is None or p_val < existing_rec[0]:
                    records[relay_name] = (p_val, p_disp, team_label)
                    is_club_rec = True
                    state.milestones.insert(
                        0,
                        f"Sett. {state.week}: Nuovo Record Sociale ({gender}) nella {relay_name} "
                        f"({team_label}): {p_disp}.",
                    )
                prize = int(tier_cfg["prize_base"] * {1: 1.0, 2: 0.60, 3: 0.35, 4: 0.15}.get(player_place, 0.0))
                prestige_gain = {1: 35, 2: 22, 3: 14, 4: 7, 5: 3}.get(player_place, 1) + (5 if is_club_rec else 0)
            total_prize += prize
            total_prestige += prestige_gain
            event_results.append(
                EventResult(
                    event_name=relay_name,
                    player_athlete_name=team_label,
                    placement=player_place,
                    total_competitors=len(standings),
                    player_mark=p_disp,
                    prize_money=prize,
                    prestige_gained=prestige_gain,
                    is_club_record=is_club_rec,
                    standings=standings,
                    attitude=f"Affiatamento {harmony_grade(max(0, harmony))}",
                    withdrew_injured=False,
                    disqualified=disqualified,
                    gender=gender,
                )
            )

    _adapt_rival_ambition(state, team_points)
    team_standings = sorted(team_points.items(), key=lambda kv: kv[1], reverse=True)
    team_place = next(
        (i for i, (t, _p) in enumerate(team_standings, start=1) if t == state.team_name),
        len(team_standings),
    )
    team_bonus = {1: 10, 2: 6, 3: 3}.get(team_place, 0)
    total_prestige += team_bonus
    for team, pts in team_points.items():
        state.league_table[team] = state.league_table.get(team, 0) + pts

    # Home meets: no bus trip, but the gate brings ticket income and wears the track
    spectators, ticket_income = (0, 0)
    if is_home:
        spectators, ticket_income = _compute_ticket_income(state, weather, r)
        travel_cost = 0
        state.track_condition = clamp_stat(state.track_condition - 3, 25, 100)
    else:
        travel_cost = tier_cfg["travel_cost"]
    state.budget += total_prize + ticket_income - travel_cost
    state.prestige += total_prestige

    meet_name = get_meet_name(state.week, state.tier, state.season_phase.value)
    if total_prize > 0:
        state.transactions.insert(
            0,
            Transaction(
                id=None,
                week=state.week,
                description=f"Premi {meet_name}",
                category="Premi Gara",
                amount=total_prize,
            ),
        )
    if is_home:
        state.transactions.insert(
            0,
            Transaction(
                id=None,
                week=state.week,
                description=f"Biglietteria meeting in casa ({spectators:,} spettatori)",
                category="Biglietti",
                amount=ticket_income,
            ),
        )
    else:
        state.transactions.insert(
            0,
            Transaction(
                id=None,
                week=state.week,
                description=f"Trasferta in pullman ({state.tier.value})",
                category="Trasferte",
                amount=-travel_cost,
            ),
        )

    meet_tier = state.tier
    promoted_to: Optional[CompetitionTier] = None  # promotion now happens at season end

    summary = CompetitionSummary(
        week=state.week,
        tier=meet_tier,
        season_phase=state.season_phase,
        meet_name=meet_name,
        weather=weather,
        track_surface=track_surface,
        event_results=event_results,
        total_prize_money=total_prize,
        total_prestige_gained=total_prestige,
        travel_cost=travel_cost,
        promoted_to=promoted_to,
        is_home=is_home,
        spectators=spectators,
        ticket_income=ticket_income,
        team_standings=team_standings,
        player_team=state.team_name,
    )
    state.competition_history.insert(0, summary)
    venue = f"in casa, {spectators:,} spettatori" if is_home else "in trasferta"
    state.news_log.insert(
        0,
        f"Sett. {state.week}: Completato {summary.meet_name} ({weather.value}, {venue}) — "
        f"società {team_place}ª con {team_points[state.team_name]} pt, "
        f"+${total_prize:,} premi, +{total_prestige} prestigio.",
    )
    _evaluate_objectives(state, summary)
    return summary


LEGACY_COACH_ROLES: Dict[StaffRole, Specialty] = {
    StaffRole.COACH_SPRINTS: Specialty.SPRINTS,
    StaffRole.COACH_JUMPS: Specialty.JUMPS,
    StaffRole.COACH_DISTANCE: Specialty.MIDDLE_DISTANCE,
}


def upgrade_legacy_state(state: GameState, rng: Optional[random.Random] = None) -> None:
    """Bring older saves up to date: coach 'roles' become real coaches, relays get composed."""
    r = rng or random.Random()
    legacy = [s for s in state.staff if s.role in LEGACY_COACH_ROLES]
    if legacy and not state.coaches:
        for member in legacy:
            if not member.hired:
                continue
            spec = LEGACY_COACH_ROLES[member.role]
            primary, secondary = SPECIALTY_COACH_FOCUS[spec]
            coach = generate_coach(spec, primary, secondary, tier=member.skill, rng=r)
            coach.name = member.name.replace("Coach ", "")
            coach.id = len(state.coaches) + 1
            state.coaches.append(coach)
    if legacy:
        state.staff = [s for s in state.staff if s.role not in LEGACY_COACH_ROLES]
        for athlete in state.athletes:
            auto_assign_coach(state, athlete)
    if any(name not in state.relays for name in state.active_relays):
        auto_build_all_relays(state, gender="M")
    if any(name not in state.relays_f for name in state.active_relays) and any(
        a.gender == "F" for a in state.main_squad
    ):
        auto_build_all_relays(state, gender="F")
    if not state.rival_clubs:
        state.rival_clubs = create_rival_clubs(rng=r)
    for club in state.rival_clubs:
        if not club.female_athletes:
            for event in club.athletes:
                club.female_athletes[event] = generate_rival_athlete(
                    event, club.tier, club.offset, season=state.season_number, rng=r, gender="F"
                )
    if not state.event_lineup_f and any(a.gender == "F" for a in state.main_squad):
        state.event_lineup_f = build_default_lineup(
            state.athletes, event_names=state.active_events, gender="F"
        )


def close_season(state: GameState) -> SeasonEndResult:
    """Final league table: the top 2 go up, the last club goes down a category."""
    table = state.league_standings()
    placement = state.league_position
    tier = state.tier
    up, down = tier.next_tier, tier.previous_tier
    outcome = SeasonOutcome.STAYED
    new_tier: Optional[CompetitionTier] = None
    week = state.week - 1  # the week that just ended

    if placement <= PROMOTION_SPOTS and up is not None:
        outcome, new_tier = SeasonOutcome.PROMOTED, up
        msg = (
            f"Sett. {week}: PROMOZIONE! {state.team_name} chiude {placement}ª in "
            f"{tier.value} e sale in categoria {up.value}!"
        )
    elif placement == 1 and up is None:
        outcome = SeasonOutcome.CHAMPION
        msg = f"Sett. {week}: CAMPIONI! {state.team_name} vince la lega {tier.value}!"
    elif placement > len(table) - RELEGATION_SPOTS and down is not None:
        outcome, new_tier = SeasonOutcome.RELEGATED, down
        msg = (
            f"Sett. {week}: RETROCESSIONE. {state.team_name} chiude ultima in "
            f"{tier.value} e scende in categoria {down.value}."
        )
    else:
        msg = f"Sett. {week}: Stagione chiusa al {placement}° posto in {tier.value}: categoria confermata."

    if new_tier is not None:
        state.tier = new_tier
    state.news_log.insert(0, msg)
    if outcome != SeasonOutcome.STAYED:
        state.milestones.insert(0, msg)

    result = SeasonEndResult(
        season=state.season_number,
        tier=tier,
        placement=placement,
        outcome=outcome,
        final_table=table,
        new_tier=new_tier,
    )
    state.season_history.insert(0, result)
    return result


def comp_summary_relays(summary: Optional[CompetitionSummary]) -> List[Tuple[str, str]]:
    """Relays `(event_name, gender)` that finished (not disqualified) in a meet."""
    if summary is None:
        return []
    return [
        (er.event_name, er.gender or "M")
        for er in summary.event_results
        if er.event_name in RELAYS and not er.disqualified
    ]


def weekly_finances(state: GameState) -> Dict[str, int]:
    """Projected recurring weekly income & expenses (excluding meets and one-off costs)."""
    tier_cfg = TIER_CONFIG[state.tier]
    rep_mult = 0.65 + (state.reputation / 100.0) * 0.55
    fidelity_mult = 0.8 + 0.2 * (state.fidelity / 100.0)
    sponsor = round(tier_cfg["weekly_sponsor"] * rep_mult * fidelity_mult)
    individual = sum(a.fans // 4 for a in state.main_squad if a.age >= 18)
    athlete_wages = sum(a.weekly_wage for a in state.main_squad)
    staff_cost = sum(s.weekly_cost for s in state.staff if s.hired)
    coach_cost = sum(c.weekly_wage for c in state.coaches)
    gym_upkeep = state.gym_level * GYM_UPKEEP_PER_LEVEL
    income = sponsor + individual + state.member_fees_weekly
    expenses = athlete_wages + staff_cost + coach_cost + gym_upkeep
    return {
        "sponsor": sponsor,
        "individual_sponsors": individual,
        "member_fees": state.member_fees_weekly,
        "income": income,
        "athlete_wages": athlete_wages,
        "staff_cost": staff_cost,
        "coach_cost": coach_cost,
        "gym_upkeep": gym_upkeep,
        "expenses": expenses,
        "net": income - expenses,
    }


def promote_youth_athlete(state: GameState, athlete: Athlete) -> None:
    """Move an academy kid to the main squad: starts being paid, form capped like a debut."""
    athlete.in_youth_squad = False
    athlete.weekly_wage = senior_wage(athlete)
    athlete.form = min(athlete.form, 75)
    auto_assign_coach(state, athlete)  # youth coaches can't follow main-squad athletes


def advance_week(
    state: GameState,
    rng: Optional[random.Random] = None,
) -> WeekAdvanceReport:
    """Advance simulation by 1 week, handling meets, training, economy, seasons, and dilemmas."""
    r = rng or random.Random()
    completed_week = state.week
    comp_summary: Optional[CompetitionSummary] = None
    travel_cost = 0
    season_end: Optional[SeasonEndResult] = None

    if state.is_competition_week:
        comp_summary = simulate_competition(state, rng=r)
        travel_cost = comp_summary.travel_cost

    roles = _hired_roles(state)
    leader_present = any(
        a.personality == Personality.LEADER and not a.is_injured for a in state.main_squad
    )

    injuries: List[str] = []
    recoveries: List[str] = []
    stat_gains: List[str] = []
    doping_scandals: List[str] = []

    loads = {c.id: state.coach_load(c) for c in state.coaches}
    for athlete in state.athletes:
        coach = state.coach_of(athlete)
        gains, injury_note, recovery_note, scandal_note = apply_weekly_training(
            athlete,
            hired_roles=roles,
            leader_present=leader_present,
            rng=r,
            gym_level=state.gym_level,
            coach=coach,
            coach_load=loads.get(coach.id, 1) if coach is not None else 1,
        )
        stat_gains.extend(gains)
        if injury_note:
            injuries.append(injury_note)
            state.news_log.insert(0, f"Sett. {completed_week}: {injury_note}")
        if recovery_note:
            recoveries.append(recovery_note)
            state.news_log.insert(0, f"Sett. {completed_week}: {recovery_note}")
        if scandal_note:
            doping_scandals.append(scandal_note)
            state.reputation = clamp_stat(state.reputation - 25, 0, 100)
            state.prestige = max(0, state.prestige - 45)
            state.news_log.insert(0, f"Sett. {completed_week}: {scandal_note}")
            state.milestones.insert(0, f"Sett. {completed_week}: {scandal_note}")

    # Weekly finances: club sponsor (reputation & fidelity), personal sponsors, fees vs wages & upkeep
    fin = weekly_finances(state)
    state.budget += fin["net"]

    def ledger(description: str, category: str, amount: int) -> None:
        state.transactions.insert(
            0,
            Transaction(id=None, week=completed_week, description=description, category=category, amount=amount),
        )

    ledger(
        f"Sponsor Società ({state.tier.value}, Rep {state.reputation}%, Fedeltà {state.fidelity}%)",
        "Sponsor",
        fin["sponsor"],
    )
    if fin["individual_sponsors"] > 0:
        ledger("Sponsor Individuali Atleti (in base ai fan)", "Sponsor", fin["individual_sponsors"])
    ledger("Quote Tesserati & Contributi", "Quote Sociali", fin["member_fees"])
    ledger(f"Stipendi Atleti ({len(state.main_squad)})", "Stipendi Atleti", -fin["athlete_wages"])
    if fin["staff_cost"] > 0:
        hired_count = sum(1 for s in state.staff if s.hired)
        ledger(f"Compensi Staff ({hired_count} specialisti)", "Staff", -fin["staff_cost"])
    if fin["coach_cost"] > 0:
        ledger(f"Stipendi Allenatori ({len(state.coaches)})", "Allenatori", -fin["coach_cost"])
    if fin["gym_upkeep"] > 0:
        ledger(f"Gestione Palestra (livello {state.gym_level})", "Impianto", -fin["gym_upkeep"])

    # Debt: interest on the negative balance, bankruptcy below the threshold
    if state.budget < 0:
        interest = int(math.ceil(-state.budget * DEBT_WEEKLY_INTEREST))
        state.budget -= interest
        ledger("Interessi passivi sul debito (5%)", "Interessi", -interest)
        state.news_log.insert(
            0, f"Sett. {completed_week}: Conto in rosso! Pagati ${interest:,} di interessi."
        )
        if state.budget < BANKRUPTCY_THRESHOLD and not state.bankrupt:
            state.bankrupt = True
            msg = (
                f"Sett. {completed_week}: FALLIMENTO! Il debito ha superato "
                f"${-BANKRUPTCY_THRESHOLD:,}: la società viene messa in liquidazione."
            )
            state.news_log.insert(0, msg)
            state.milestones.insert(0, msg)

    # Coaches' skills slowly fade: sooner or later they need replacing
    for coach in state.coaches:
        if r.random() < 0.10:
            decayable = [k for k, v in coach.skills.items() if v > COACH_BASE_SKILL]
            if decayable:
                stat = r.choice(decayable)
                coach.skills[stat] -= 1

    _update_relay_harmony(state, set(comp_summary_relays(comp_summary)))
    progress_rivals(state, r)

    # Gradual tartan track wear
    state.track_condition = clamp_stat(state.track_condition - r.randint(1, 3), 25, 100)

    # Sponsors slowly regain trust in a stable squad; scouting budget resets
    state.fidelity = min(100, state.fidelity + 2)
    state.scouting_points_used = 0

    state.week += 1

    # Season progression in Career mode (every 12 weeks: Outdoor -> Cross -> Indoor -> Outdoor)
    if state.game_mode == "career" and (state.week - 1) % 12 == 0:
        cycle = [SeasonPhase.OUTDOOR, SeasonPhase.CROSS, SeasonPhase.INDOOR]
        next_idx = (cycle.index(state.season_phase) + 1) % len(cycle)
        state.season_phase = cycle[next_idx]
        if state.season_phase == SeasonPhase.OUTDOOR:
            season_end = close_season(state)
            state.season_number += 1
            state.league_table = {}
            for a in state.athletes:
                a.age += 1
            for line in renew_rivals_for_season(state, r):
                state.news_log.insert(0, line)
        state.news_log.insert(
            0,
            f"Sett. {state.week}: Inizia la stagione {state.season_phase.value}!",
        )

    # Academy kids turning 18 join the main squad automatically
    for a in state.youth_squad:
        if a.age >= 18:
            promote_youth_athlete(state, a)
            state.news_log.insert(
                0, f"Sett. {state.week}: {a.name} compie 18 anni e passa in Prima Squadra dal vivaio."
            )

    if state.is_competition_week:
        venue = "IN CASA" if state.next_meet_is_home else "in trasferta"
        state.news_log.insert(
            0,
            f"Sett. {state.week}: Settimana di Gara ({venue})! Verifica formazione, atteggiamento e Scarico.",
        )

    _evaluate_objectives(state, comp_summary)
    dilemma = maybe_generate_dilemma(state, rng=r)
    if dilemma is not None:
        state.pending_dilemma = dilemma

    state.news_log = state.news_log[:70]
    state.milestones = state.milestones[:40]
    state.transactions = state.transactions[:400]

    return WeekAdvanceReport(
        completed_week=completed_week,
        new_week=state.week,
        weekly_income=fin["income"],
        weekly_wages=fin["athlete_wages"],
        staff_cost=fin["staff_cost"],
        travel_cost=travel_cost,
        injuries=injuries,
        recoveries=recoveries,
        stat_gains=stat_gains,
        doping_scandals=doping_scandals,
        competition_summary=comp_summary,
        triggered_dilemma=dilemma,
        season_end=season_end,
    )
