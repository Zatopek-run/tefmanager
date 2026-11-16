"""Simulation engine for periodization, recovery, wind-aware meets, economy, and seasons."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from models.entities import (
    EVENTS,
    TIER_CONFIG,
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
    FIRST_NAMES,
    LAST_NAMES,
    clamp_stat,
    get_meet_name,
    get_rival_teams,
    maybe_generate_dilemma,
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


def _hired_roles(state: GameState) -> Set[StaffRole]:
    return {s.role for s in state.staff if s.hired}


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
) -> Tuple[List[str], Optional[str], Optional[str], Optional[str]]:
    """
    Update a single athlete's stats, fatigue, form, and injury status for one week.

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

    # Coach specialty bonus
    coach_bonus = 1.0
    if athlete.specialty == Specialty.SPRINTS and StaffRole.COACH_SPRINTS in roles:
        coach_bonus = 1.25
    elif athlete.specialty == Specialty.JUMPS and StaffRole.COACH_JUMPS in roles:
        coach_bonus = 1.25
    elif athlete.specialty == Specialty.MIDDLE_DISTANCE and StaffRole.COACH_DISTANCE in roles:
        coach_bonus = 1.25

    personality_growth = 1.15 if athlete.personality == Personality.PERFEZIONISTA else 1.0
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
        chance = min(0.95, base_chance * age_factor * coach_bonus * personality_growth * period_growth * headroom)
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
) -> Tuple[float, str]:
    """Convert a composite performance score + wind into realistic athletics marks."""
    norm = max(0.15, min(1.18, performance_score / 100.0))

    if event_def.name == "100m":
        seconds = 12.60 - norm * 2.75
        if wind_ms is not None:
            # Tailwind helps (~0.05s per 1.0 m/s), headwind slows
            seconds -= wind_ms * 0.055
        seconds = max(9.58, seconds)
        return seconds, f"{seconds:.2f}s"

    if event_def.name == "400m":
        seconds = max(43.10, 57.40 - norm * 12.90)
        return seconds, f"{seconds:.2f}s"

    if event_def.name == "1500m":
        total_seconds = max(206.0, 282.0 - norm * 68.0)
        mins = int(total_seconds // 60)
        secs = total_seconds % 60
        return total_seconds, f"{mins}:{secs:05.2f}"

    if event_def.name == "Salto in Lungo":
        meters = 5.30 + norm * 3.10
        if wind_ms is not None:
            meters += wind_ms * 0.08
        return meters, f"{meters:.2f}m"

    meters = 11.40 + norm * 10.60
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
    base_skill = (
        athlete.speed * event_def.weights["speed"]
        + athlete.stamina * event_def.weights["stamina"]
        + athlete.strength * event_def.weights["strength"]
        + athlete.technique * event_def.weights["technique"]
    )
    specialty_bonus = 4.0 if athlete.specialty == event_def.specialty else -3.5
    form_modifier = (athlete.form - 60) * 0.24
    fatigue_penalty = max(0, athlete.fatigue - 62) * 0.26
    track_mod = (track_condition - 75) * 0.06
    weather_mod = -1.8 if weather == WeatherCondition.PIOGGIA else (-0.8 if weather == WeatherCondition.CALDO else 0.0)
    doping_mod = 6.5 if athlete.doping_boost_weeks > 0 else 0.0

    # Impulsive athletes have wilder swings unless coached mentally
    sigma = 5.6 if (athlete.personality == Personality.IMPULSIVO and not has_mental_coach) else 3.8
    if athlete.personality == Personality.PERFEZIONISTA:
        sigma = 3.0
    variance = rng.gauss(0.0, sigma)

    return base_skill + specialty_bonus + form_modifier - fatigue_penalty + track_mod + weather_mod + doping_mod + variance


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
                ev = EVENTS[er.event_name]
                player_st = next((s for s in er.standings if s.is_player), None)
                if player_st and not er.wind_illegal:
                    if (ev.lower_is_better and player_st.mark_value < ev.historic_mark) or (
                        not ev.lower_is_better and player_st.mark_value > ev.historic_mark
                    ):
                        obj.completed = True


def simulate_competition(
    state: GameState,
    rng: Optional[random.Random] = None,
) -> CompetitionSummary:
    """Simulate the current week's competition across active events with wind, weather & records."""
    r = rng or random.Random()
    tier_cfg = TIER_CONFIG[state.tier]
    rivals = get_rival_teams(state.tier)
    roles = _hired_roles(state)
    has_mental = StaffRole.MENTAL_COACH in roles
    leader_present = any(a.personality == Personality.LEADER and not a.is_injured for a in state.athletes)

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

    athlete_by_id: Dict[int, Athlete] = {a.id: a for a in state.athletes if a.id is not None}

    event_results: List[EventResult] = []
    total_prize = 0
    total_prestige = 0

    for event_name in state.active_events:
        event_def = EVENTS[event_name]
        selected_id = state.event_lineup.get(event_name)
        player_athlete = athlete_by_id.get(selected_id) if selected_id is not None else None

        if player_athlete is None or player_athlete.is_injured:
            continue

        wind_ms: Optional[float] = (
            _roll_meet_wind(weather, state.season_phase, r) if event_def.wind_affected else None
        )
        wind_illegal = bool(wind_ms is not None and wind_ms > 2.0)

        standings: List[EventStanding] = []

        p_score = _compute_athlete_event_score(
            player_athlete, event_def, weather, state.track_condition, has_mental, r
        )
        p_val, p_disp = _score_to_mark(event_def, p_score, wind_ms)
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

        # Match fatigue
        player_athlete.fatigue = clamp_stat(player_athlete.fatigue + 7, 0, 100)
        player_athlete.form = _recalculate_form(player_athlete, False, False, has_mental, leader_present)

        # 7 AI opponents
        opp_base = tier_cfg["opponent_skill"]
        for i in range(7):
            opp_name = f"{r.choice(FIRST_NAMES)} {r.choice(LAST_NAMES)}"
            opp_team = rivals[i % len(rivals)]
            opp_score = r.gauss(opp_base, 7.5)
            o_val, o_disp = _score_to_mark(event_def, opp_score, wind_ms)
            standings.append(
                EventStanding(
                    athlete_name=opp_name,
                    team_name=opp_team,
                    is_player=False,
                    mark_value=o_val,
                    mark_display=o_disp,
                    wind_ms=wind_ms,
                    wind_illegal=wind_illegal,
                )
            )

        standings.sort(key=lambda s: s.mark_value, reverse=not event_def.lower_is_better)
        player_place = 1
        for idx, standing in enumerate(standings, start=1):
            standing.placement = idx
            if standing.is_player:
                player_place = idx

        # Check PB, Club Record, and Historic Milestone (only when wind <= 2.0 m/s!)
        is_pb = False
        is_club_rec = False
        if not wind_illegal:
            if player_athlete.personal_best is None or (
                (event_def.lower_is_better and p_val < player_athlete.personal_best)
                or (not event_def.lower_is_better and p_val > player_athlete.personal_best)
            ):
                player_athlete.personal_best = p_val
                player_athlete.personal_best_display = p_disp
                is_pb = True

            existing_rec = state.club_records.get(event_name)
            if existing_rec is None or (
                (event_def.lower_is_better and p_val < existing_rec[0])
                or (not event_def.lower_is_better and p_val > existing_rec[0])
            ):
                state.club_records[event_name] = (p_val, p_disp, player_athlete.name)
                is_club_rec = True
                state.milestones.insert(
                    0,
                    f"Sett. {state.week}: Nuovo Record Sociale nei {event_name}! {player_athlete.name} segna {p_disp}.",
                )

            # Historic benchmark check
            if (event_def.lower_is_better and p_val < event_def.historic_mark) or (
                not event_def.lower_is_better and p_val > event_def.historic_mark
            ):
                milestone_msg = (
                    f"Sett. {state.week}: MOMENTO STORICO! {player_athlete.name} abbatte il muro "
                    f"{event_def.historic_label} ({p_disp})!"
                )
                if milestone_msg not in state.milestones:
                    state.milestones.insert(0, milestone_msg)
        elif player_athlete.personal_best is None or (
            (event_def.lower_is_better and p_val < player_athlete.personal_best)
            or (not event_def.lower_is_better and p_val > player_athlete.personal_best)
        ):
            state.news_log.insert(
                0,
                f"Sett. {state.week}: {player_athlete.name} ha corso/saltato {p_disp} nei {event_name}, "
                f"ma con vento +{wind_ms:.1f} m/s (>2.0 m/s): non valido per il record!",
            )

        prize_multipliers = {1: 1.0, 2: 0.60, 3: 0.35, 4: 0.15}
        prestige_table = {1: 35, 2: 22, 3: 14, 4: 7, 5: 3}

        prize = int(tier_cfg["prize_base"] * prize_multipliers.get(player_place, 0.0))
        prestige_gain = prestige_table.get(player_place, 1) + (5 if is_club_rec else 0)

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
            )
        )

    travel_cost = tier_cfg["travel_cost"]
    state.budget += total_prize - travel_cost
    state.prestige += total_prestige

    if total_prize > 0:
        state.transactions.insert(
            0,
            Transaction(
                id=None,
                week=state.week,
                description=f"Premi {get_meet_name(state.week, state.tier, state.season_phase.value)}",
                category="Premi Gara",
                amount=total_prize,
            ),
        )
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
    promoted_to: Optional[CompetitionTier] = None
    next_tier = state.tier.next_tier
    if next_tier is not None:
        required = TIER_CONFIG[next_tier]["prestige_required"]
        if state.prestige >= required:
            state.tier = next_tier
            promoted_to = next_tier
            promo_msg = f"Sett. {state.week}: PROMOZIONE! {state.team_name} sale in categoria {next_tier.value}!"
            state.news_log.insert(0, promo_msg)
            state.milestones.insert(0, promo_msg)

    summary = CompetitionSummary(
        week=state.week,
        tier=meet_tier,
        season_phase=state.season_phase,
        meet_name=get_meet_name(state.week, meet_tier, state.season_phase.value),
        weather=weather,
        track_surface=track_surface,
        event_results=event_results,
        total_prize_money=total_prize,
        total_prestige_gained=total_prestige,
        travel_cost=travel_cost,
        promoted_to=promoted_to,
    )
    state.competition_history.insert(0, summary)
    state.news_log.insert(
        0,
        f"Sett. {state.week}: Completato {summary.meet_name} ({weather.value}) — "
        f"+${total_prize:,} premi, -{travel_cost:,}$ trasferta, +{total_prestige} prestigio.",
    )
    _evaluate_objectives(state, summary)
    return summary


def advance_week(
    state: GameState,
    rng: Optional[random.Random] = None,
) -> WeekAdvanceReport:
    """Advance simulation by 1 week, handling meets, training, economy, seasons, and dilemmas."""
    r = rng or random.Random()
    completed_week = state.week
    comp_summary: Optional[CompetitionSummary] = None
    travel_cost = 0

    if state.is_competition_week:
        comp_summary = simulate_competition(state, rng=r)
        travel_cost = comp_summary.travel_cost

    roles = _hired_roles(state)
    leader_present = any(a.personality == Personality.LEADER and not a.is_injured for a in state.athletes)

    injuries: List[str] = []
    recoveries: List[str] = []
    stat_gains: List[str] = []
    doping_scandals: List[str] = []

    for athlete in state.athletes:
        gains, injury_note, recovery_note, scandal_note = apply_weekly_training(
            athlete, hired_roles=roles, leader_present=leader_present, rng=r
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

    # Weekly finances: sponsor scaled by ethical reputation + member fees vs athlete & staff wages
    tier_cfg = TIER_CONFIG[state.tier]
    rep_mult = 0.65 + (state.reputation / 100.0) * 0.55
    sponsor_income = round(tier_cfg["weekly_sponsor"] * rep_mult)
    member_fees = state.member_fees_weekly
    total_income = sponsor_income + member_fees

    athlete_wages = sum(a.weekly_wage for a in state.athletes)
    staff_cost = sum(s.weekly_cost for s in state.staff if s.hired)

    state.budget += total_income - athlete_wages - staff_cost
    state.transactions.insert(
        0,
        Transaction(
            id=None,
            week=completed_week,
            description=f"Sponsor Locali ({state.tier.value}, Rep {state.reputation}%)",
            category="Sponsor",
            amount=sponsor_income,
        ),
    )
    state.transactions.insert(
        0,
        Transaction(
            id=None,
            week=completed_week,
            description="Quote Tesserati & Contributi",
            category="Quote Sociali",
            amount=member_fees,
        ),
    )
    state.transactions.insert(
        0,
        Transaction(
            id=None,
            week=completed_week,
            description=f"Stipendi Atleti ({len(state.athletes)})",
            category="Stipendi Atleti",
            amount=-athlete_wages,
        ),
    )
    if staff_cost > 0:
        hired_count = sum(1 for s in state.staff if s.hired)
        state.transactions.insert(
            0,
            Transaction(
                id=None,
                week=completed_week,
                description=f"Compensi Staff ({hired_count} specialisti)",
                category="Staff",
                amount=-staff_cost,
            ),
        )

    # Gradual tartan track wear
    state.track_condition = clamp_stat(state.track_condition - r.randint(1, 3), 25, 100)

    state.week += 1

    # Season progression in Career mode (every 12 weeks: Outdoor -> Cross -> Indoor -> Outdoor)
    if state.game_mode == "career" and (state.week - 1) % 12 == 0:
        cycle = [SeasonPhase.OUTDOOR, SeasonPhase.CROSS, SeasonPhase.INDOOR]
        next_idx = (cycle.index(state.season_phase) + 1) % len(cycle)
        state.season_phase = cycle[next_idx]
        if state.season_phase == SeasonPhase.OUTDOOR:
            state.season_number += 1
            for a in state.athletes:
                a.age += 1
        state.news_log.insert(
            0,
            f"Sett. {state.week}: Inizia la stagione {state.season_phase.value}!",
        )

    if state.is_competition_week:
        state.news_log.insert(
            0,
            f"Sett. {state.week}: Settimana di Gara! Verifica la formazione e valuta lo Scarico (Tapering).",
        )

    _evaluate_objectives(state, comp_summary)
    dilemma = maybe_generate_dilemma(state, rng=r)
    if dilemma is not None:
        state.pending_dilemma = dilemma

    state.news_log = state.news_log[:70]
    state.milestones = state.milestones[:40]

    return WeekAdvanceReport(
        completed_week=completed_week,
        new_week=state.week,
        weekly_income=total_income,
        weekly_wages=athlete_wages,
        staff_cost=staff_cost,
        travel_cost=travel_cost,
        injuries=injuries,
        recoveries=recoveries,
        stat_gains=stat_gains,
        doping_scandals=doping_scandals,
        competition_summary=comp_summary,
        triggered_dilemma=dilemma,
    )
