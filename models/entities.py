"""Core domain entities and enums for Track & Field Manager."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum
from typing import Dict, List, Optional, Tuple


class CompetitionTier(str, Enum):
    """League tiers from local to international level."""

    PROVINCIALE = "Provinciale"
    REGIONALE = "Regionale"
    NAZIONALE = "Nazionale"
    INTERNAZIONALE = "Internazionale"

    @property
    def order(self) -> int:
        return TIER_ORDER.index(self)

    @property
    def next_tier(self) -> Optional["CompetitionTier"]:
        idx = self.order
        if idx + 1 < len(TIER_ORDER):
            return TIER_ORDER[idx + 1]
        return None


TIER_ORDER: List[CompetitionTier] = [
    CompetitionTier.PROVINCIALE,
    CompetitionTier.REGIONALE,
    CompetitionTier.NAZIONALE,
    CompetitionTier.INTERNAZIONALE,
]

TIER_CONFIG: Dict[CompetitionTier, Dict[str, int]] = {
    CompetitionTier.PROVINCIALE: {
        "prestige_required": 0,
        "weekly_sponsor": 600,
        "prize_base": 1200,
        "opponent_skill": 42,
        "travel_cost": 350,
    },
    CompetitionTier.REGIONALE: {
        "prestige_required": 100,
        "weekly_sponsor": 1250,
        "prize_base": 2800,
        "opponent_skill": 56,
        "travel_cost": 750,
    },
    CompetitionTier.NAZIONALE: {
        "prestige_required": 280,
        "weekly_sponsor": 2500,
        "prize_base": 6000,
        "opponent_skill": 70,
        "travel_cost": 1500,
    },
    CompetitionTier.INTERNAZIONALE: {
        "prestige_required": 600,
        "weekly_sponsor": 4800,
        "prize_base": 12500,
        "opponent_skill": 84,
        "travel_cost": 3000,
    },
}


class SeasonPhase(str, Enum):
    """Real athletics seasonal cycle."""

    OUTDOOR = "Outdoor (Primavera/Estate)"
    CROSS = "Cross (Autunno)"
    INDOOR = "Indoor (Inverno)"


class Specialty(str, Enum):
    """Athlete primary track & field discipline group."""

    SPRINTS = "Velocità"
    MIDDLE_DISTANCE = "Mezzofondo"
    JUMPS = "Salti"
    THROWS = "Lanci"

    @property
    def peak_age_range(self) -> Tuple[int, int]:
        """Typical peak age window per discipline."""
        if self == Specialty.SPRINTS:
            return (20, 27)
        if self == Specialty.JUMPS:
            return (20, 28)
        if self == Specialty.MIDDLE_DISTANCE:
            return (21, 30)
        return (23, 32)  # Throws peak later


class TrainingFocus(str, Enum):
    """Weekly training regimens assignable per athlete."""

    ENDURANCE = "Resistenza"
    EXPLOSIVE_POWER = "Potenza Esplosiva"
    TECHNIQUE = "Tecnica"
    REST = "Riposo & Recupero"


class PeriodizationPhase(str, Enum):
    """Training periodization block for load & tapering strategy."""

    PREP_GENERALE = "Prep. Generale"
    PREP_SPECIFICA = "Prep. Specifica"
    GARA = "Gara (Picco)"
    SCARICO = "Scarico (Tapering)"


class Personality(str, Enum):
    """Athlete psychological profile affecting load response and consistency."""

    PERFEZIONISTA = "Perfezionista"
    IMPULSIVO = "Impulsivo"
    LEADER = "Leader"


class WeatherCondition(str, Enum):
    """Meet weather conditions affecting wind and performance."""

    SERENO = "Sereno"
    VENTOSO = "Ventoso"
    PIOGGIA = "Pioggia"
    CALDO = "Caldo"


class RaceAttitude(str, Enum):
    """How hard an athlete pushes in a race: trades performance for fatigue & injury risk."""

    PRUDENTE = "Prudente"
    NORMALE = "Normale"
    AGGRESSIVO = "Aggressivo"


# score bonus, post-race fatigue, base in-race injury chance, extra result variance (std dev)
ATTITUDE_EFFECTS: Dict[RaceAttitude, Dict[str, float]] = {
    RaceAttitude.PRUDENTE: {"score": -2.0, "fatigue": 4, "injury": 0.005, "sigma": 0.0},
    RaceAttitude.NORMALE: {"score": 0.0, "fatigue": 7, "injury": 0.02, "sigma": 0.0},
    RaceAttitude.AGGRESSIVO: {"score": 2.5, "fatigue": 11, "injury": 0.05, "sigma": 2.0},
}

# Club facilities & youth academy tuning
YOUTH_SQUAD_MAX = 8
YOUTH_TRAINING_MULT = 1.5
WEEKLY_SCOUTING_POINTS = 8
SCOUTING_SEARCH_POINTS = 2
# Cumulative weekly scouting fee by total points used (each search pays the difference)
SCOUTING_FEES: Dict[int, int] = {0: 0, 1: 0, 2: 150, 3: 350, 4: 600, 5: 1000, 6: 1500, 7: 2200, 8: 3000}
GYM_MAX_LEVEL = 5
GYM_TRAINING_BONUS_PER_LEVEL = 0.06
GYM_UPKEEP_PER_LEVEL = 40
STAND_EXPANSION_SEATS = 500
STAND_MAX_SEATS = 20000
TICKET_PRICE: Dict[str, int] = {
    "Provinciale": 4,
    "Regionale": 6,
    "Nazionale": 9,
    "Internazionale": 14,
}
DEBT_WEEKLY_INTEREST = 0.05
BANKRUPTCY_THRESHOLD = -20000
# Team points per finishing place (1st..8th) for the club league table
TEAM_POINTS: Dict[int, int] = {1: 8, 2: 7, 3: 6, 4: 5, 5: 4, 6: 3, 7: 2, 8: 1}
DNF_MARK = "Ritirato"


def gym_upgrade_cost(current_level: int) -> int:
    return (current_level + 1) * 2500


def stand_expansion_cost(current_seats: int) -> int:
    """Seats get pricier as the stand grows (like real stadium expansions)."""
    per_seat = 3 if current_seats < 5000 else (4 if current_seats < 10000 else 6)
    return STAND_EXPANSION_SEATS * per_seat + 500


# ---------------------------------------------------------------- coaches
COACH_STATS: List[str] = ["speed", "stamina", "strength", "technique"]
COACH_STAT_LABELS: Dict[str, str] = {
    "speed": "Velocità",
    "stamina": "Resistenza",
    "strength": "Forza",
    "technique": "Tecnica",
}
MAX_SPECIALIZED_COACHES = 6
MAX_YOUTH_COACHES = 2
COACH_COMFORT_LOAD = 6  # beyond this many athletes, each one gets less attention
COACH_BASE_SKILL = 25  # level of the skills the coach was not hired for
COACH_MAX_TIER = 5
COACH_NO_COACH_MULT = 0.6  # athletes without a (suitable) coach still train, but slowly


def coach_hire_skills(tier: int) -> Tuple[int, int]:
    """(primary, secondary) skill values for a recruitment tier 1-5."""
    primary = 60 + 7 * tier
    return primary, primary - 10


def coach_hire_cost(tier: int) -> int:
    return 1500 * tier


def coach_weekly_wage(skills: Dict[str, int]) -> int:
    return 40 + round(sum(max(0, v - 40) for v in skills.values()) * 2.2)


# ---------------------------------------------------------------- relays
@dataclass(frozen=True)
class RelayDefinition:
    name: str
    leg_weights: Dict[str, float]  # athlete attributes that matter for each leg
    base_seconds: float  # time for a very weak team
    span_seconds: float  # how much a strong team gains
    min_seconds: float
    indoor: bool  # also run during the indoor season
    requires_event: str  # only run when this individual event is in the programme


RELAYS: Dict[str, RelayDefinition] = {
    "4x100m": RelayDefinition(
        name="4x100m",
        leg_weights={"speed": 0.70, "technique": 0.20, "strength": 0.10},
        base_seconds=50.4,
        span_seconds=11.2,
        min_seconds=36.8,
        indoor=False,
        requires_event="100m",
    ),
    "4x400m": RelayDefinition(
        name="4x400m",
        leg_weights={"speed": 0.50, "stamina": 0.40, "technique": 0.10},
        base_seconds=229.0,
        span_seconds=50.0,
        min_seconds=174.0,
        indoor=True,
        requires_event="400m",
    ),
}
RELAY_LEG_WEIGHTS: List[float] = [0.24, 0.24, 0.24, 0.28]  # the anchor leg counts a bit more
RELAY_CHANGE_COOLDOWN_WEEKS = 4
RELAY_DQ_MARK = "Squalificata"


def harmony_grade(harmony: int) -> str:
    """Letter grade for relay harmony (E .. A++)."""
    grades = ["E", "D", "C-", "C", "C+", "B-", "B", "B+", "A", "A+", "A++"]
    return grades[max(0, min(10, harmony // 10))]


class StaffRole(str, Enum):
    """Specialized club staff roles."""

    COACH_SPRINTS = "Coach Velocità"
    COACH_JUMPS = "Coach Salti"
    COACH_DISTANCE = "Coach Mezzofondo"
    PHYSIO = "Fisioterapista"
    DOCTOR = "Medico Sportivo"
    MENTAL_COACH = "Preparatore Mentale"


@dataclass(frozen=True)
class EventDefinition:
    """Definition of an individual track & field event."""

    name: str
    specialty: Specialty
    unit: str
    lower_is_better: bool
    wind_affected: bool
    historic_mark: float
    historic_label: str
    weights: Dict[str, float]


EVENTS: Dict[str, EventDefinition] = {
    "100m": EventDefinition(
        name="100m",
        specialty=Specialty.SPRINTS,
        unit="s",
        lower_is_better=True,
        wind_affected=True,
        historic_mark=11.00,
        historic_label="sub-11.00s nei 100m",
        weights={"speed": 0.55, "technique": 0.25, "strength": 0.15, "stamina": 0.05},
    ),
    "400m": EventDefinition(
        name="400m",
        specialty=Specialty.SPRINTS,
        unit="s",
        lower_is_better=True,
        wind_affected=False,
        historic_mark=48.00,
        historic_label="sub-48.00s nei 400m",
        weights={"speed": 0.45, "stamina": 0.30, "technique": 0.15, "strength": 0.10},
    ),
    "1500m": EventDefinition(
        name="1500m",
        specialty=Specialty.MIDDLE_DISTANCE,
        unit="min",
        lower_is_better=True,
        wind_affected=False,
        historic_mark=235.0,  # 3:55.00
        historic_label="sub-3:55.00 nei 1500m",
        weights={"stamina": 0.55, "speed": 0.25, "technique": 0.15, "strength": 0.05},
    ),
    "Salto in Lungo": EventDefinition(
        name="Salto in Lungo",
        specialty=Specialty.JUMPS,
        unit="m",
        lower_is_better=False,
        wind_affected=True,
        historic_mark=7.50,
        historic_label="oltre 7.50m nel Lungo",
        weights={"speed": 0.40, "technique": 0.35, "strength": 0.20, "stamina": 0.05},
    ),
    "Getto del Peso": EventDefinition(
        name="Getto del Peso",
        specialty=Specialty.THROWS,
        unit="m",
        lower_is_better=False,
        wind_affected=False,
        historic_mark=18.00,
        historic_label="oltre 18.00m nel Peso",
        weights={"strength": 0.55, "technique": 0.35, "speed": 0.05, "stamina": 0.05},
    ),
}

VERTICAL_SLICE_EVENTS: List[str] = ["100m", "Salto in Lungo", "1500m"]


@dataclass
class Athlete:
    """Represents a single track & field athlete on the team."""

    id: Optional[int]
    name: str
    age: int
    specialty: Specialty
    speed: int
    stamina: int
    strength: int
    technique: int
    resilience: int
    form: int
    fatigue: int
    potential: int = 75
    personality: Personality = Personality.PERFEZIONISTA
    training_focus: TrainingFocus = TrainingFocus.ENDURANCE
    periodization: PeriodizationPhase = PeriodizationPhase.PREP_GENERALE
    sleep_quality: int = 75
    nutrition: int = 75
    weekly_wage: int = 200
    injured_weeks: int = 0
    is_youth_prospect: bool = False
    personal_best: Optional[float] = None
    personal_best_display: Optional[str] = None
    doping_boost_weeks: int = 0
    in_youth_squad: bool = False
    fans: int = 0
    coach_id: Optional[int] = None

    @property
    def power(self) -> int:
        """Composite power attribute combining speed and strength."""
        return round(self.speed * 0.55 + self.strength * 0.45)

    @property
    def overall(self) -> int:
        """Weighted overall rating based on specialty."""
        if self.specialty == Specialty.SPRINTS:
            score = (
                self.speed * 0.42
                + self.technique * 0.23
                + self.strength * 0.15
                + self.stamina * 0.12
                + self.resilience * 0.08
            )
        elif self.specialty == Specialty.MIDDLE_DISTANCE:
            score = (
                self.stamina * 0.46
                + self.speed * 0.22
                + self.technique * 0.14
                + self.resilience * 0.12
                + self.strength * 0.06
            )
        elif self.specialty == Specialty.JUMPS:
            score = (
                self.speed * 0.33
                + self.technique * 0.33
                + self.strength * 0.18
                + self.resilience * 0.08
                + self.stamina * 0.08
            )
        else:  # Throws
            score = (
                self.strength * 0.46
                + self.technique * 0.30
                + self.resilience * 0.10
                + self.speed * 0.08
                + self.stamina * 0.06
            )
        return max(1, min(100, round(score)))

    @property
    def is_injured(self) -> bool:
        return self.injured_weeks > 0

    @property
    def status_label(self) -> str:
        if self.injured_weeks > 0:
            return f"Infortunato ({self.injured_weeks}s)"
        if self.doping_boost_weeks > 0:
            return "Sospetto"
        if self.fatigue >= 80:
            return "Esausto"
        if self.fatigue >= 60:
            return "Affaticato"
        if self.form >= 78:
            return "Al Picco"
        return "In Forma"


@dataclass
class Coach:
    """A coach with their own skills. Specialized coaches train one specialty;
    youth coaches (specialty None) only train the youth academy, any discipline."""

    id: Optional[int]
    name: str
    specialty: Optional[Specialty]
    skills: Dict[str, int]  # speed / stamina / strength / technique, 1-100

    @property
    def is_youth_coach(self) -> bool:
        return self.specialty is None

    @property
    def weekly_wage(self) -> int:
        return coach_weekly_wage(self.skills)

    @property
    def kind_label(self) -> str:
        return "Vivaio" if self.specialty is None else self.specialty.value

    def skill_for(self, stat_name: str) -> int:
        if stat_name == "resilience":  # resilience is built through endurance work
            return self.skills.get("stamina", COACH_BASE_SKILL)
        return self.skills.get(stat_name, COACH_BASE_SKILL)

    def can_train(self, athlete: "Athlete") -> bool:
        if self.specialty is None:
            return athlete.in_youth_squad
        return self.specialty == athlete.specialty


@dataclass
class Relay:
    """A relay team: 4 ordered legs plus a reserve. Harmony grows by training together."""

    event: str
    member_ids: List[Optional[int]] = field(default_factory=lambda: [None, None, None, None])
    reserve_id: Optional[int] = None
    harmony: int = 30  # 0-100
    last_change_week: int = -100

    @property
    def is_complete(self) -> bool:
        return all(mid is not None for mid in self.member_ids)

    def all_ids(self) -> List[int]:
        ids = [mid for mid in self.member_ids if mid is not None]
        if self.reserve_id is not None:
            ids.append(self.reserve_id)
        return ids


@dataclass
class StaffMember:
    """Club staff specialist providing bonuses at a weekly salary."""

    id: Optional[int]
    name: str
    role: StaffRole
    skill: int  # 1-5 stars
    weekly_cost: int
    hired: bool = False
    description: str = ""


@dataclass
class SeasonObjective:
    """Trackable seasonal club milestone/objective."""

    key: str
    title: str
    completed: bool = False


@dataclass
class EthicalDilemma:
    """Narrative moral choice with short-term vs long-term consequences."""

    id: str
    title: str
    description: str
    accept_label: str
    reject_label: str
    athlete_id: Optional[int] = None


@dataclass
class Transaction:
    """Financial ledger entry."""

    id: Optional[int]
    week: int
    description: str
    category: str
    amount: int


@dataclass
class EventStanding:
    """A single competitor's performance in an event."""

    athlete_name: str
    team_name: str
    is_player: bool
    mark_value: float
    mark_display: str
    placement: int = 0
    wind_ms: Optional[float] = None
    wind_illegal: bool = False


@dataclass
class EventResult:
    """Full results of a single simulated event."""

    event_name: str
    player_athlete_name: str
    placement: int
    total_competitors: int
    player_mark: str
    prize_money: int
    prestige_gained: int
    wind_ms: Optional[float] = None
    wind_illegal: bool = False
    is_pb: bool = False
    is_club_record: bool = False
    standings: List[EventStanding] = field(default_factory=list)
    attitude: str = RaceAttitude.NORMALE.value
    withdrew_injured: bool = False
    disqualified: bool = False


@dataclass
class CompetitionSummary:
    """Summary of an entire competition meet."""

    week: int
    tier: CompetitionTier
    season_phase: SeasonPhase
    meet_name: str
    weather: WeatherCondition
    track_surface: str
    event_results: List[EventResult]
    total_prize_money: int
    total_prestige_gained: int
    travel_cost: int = 0
    promoted_to: Optional[CompetitionTier] = None
    is_home: bool = False
    spectators: int = 0
    ticket_income: int = 0
    team_standings: List[Tuple[str, int]] = field(default_factory=list)
    player_team: str = ""

    @property
    def team_placement(self) -> int:
        for idx, (team, _pts) in enumerate(self.team_standings, start=1):
            if team == self.player_team:
                return idx
        return 0


@dataclass
class GameState:
    """Root state object for the management simulation."""

    team_name: str = "Atletica Aurora"
    game_mode: str = "vertical_slice"  # "vertical_slice" or "career"
    budget: int = 12000
    week: int = 1
    season_number: int = 1
    season_phase: SeasonPhase = SeasonPhase.OUTDOOR
    start_date: date = field(default_factory=lambda: date(2026, 4, 6))
    prestige: int = 0
    reputation: int = 70  # 0-100 ethical standing affecting sponsors
    tier: CompetitionTier = CompetitionTier.PROVINCIALE
    track_condition: int = 82  # 1-100 tartan track condition
    member_fees_weekly: int = 450
    athletes: List[Athlete] = field(default_factory=list)
    staff: List[StaffMember] = field(default_factory=list)
    transactions: List[Transaction] = field(default_factory=list)
    competition_history: List[CompetitionSummary] = field(default_factory=list)
    event_lineup: Dict[str, Optional[int]] = field(default_factory=dict)
    club_records: Dict[str, Tuple[float, str, str]] = field(default_factory=dict)
    objectives: List[SeasonObjective] = field(default_factory=list)
    milestones: List[str] = field(default_factory=list)
    news_log: List[str] = field(default_factory=list)
    pending_dilemma: Optional[EthicalDilemma] = None
    event_attitude: Dict[str, str] = field(default_factory=dict)
    gym_level: int = 0
    stand_seats: int = 500
    fidelity: int = 100  # 0-100: drops with transfers, sponsors value stable squads
    scouting_points_used: int = 0
    bankrupt: bool = False
    league_table: Dict[str, int] = field(default_factory=dict)
    coaches: List[Coach] = field(default_factory=list)
    relays: Dict[str, Relay] = field(default_factory=dict)
    coach_hired_week: int = 0  # one new coach per week

    def coach_of(self, athlete: Athlete) -> Optional[Coach]:
        """The athlete's coach, if assigned and allowed to train them."""
        if athlete.coach_id is None:
            return None
        coach = next((c for c in self.coaches if c.id == athlete.coach_id), None)
        return coach if coach is not None and coach.can_train(athlete) else None

    def coach_load(self, coach: Coach) -> int:
        return sum(1 for a in self.athletes if a.coach_id == coach.id and coach.can_train(a))

    @property
    def active_relays(self) -> List[str]:
        """Relays run this season: they need their sprint event in the programme; no 4x100 indoors."""
        out: List[str] = []
        if self.season_phase == SeasonPhase.CROSS:
            return out
        for name, rdef in RELAYS.items():
            if rdef.requires_event not in self.active_events:
                continue
            if self.season_phase == SeasonPhase.INDOOR and not rdef.indoor:
                continue
            out.append(name)
        return out

    def relay_of(self, athlete_id: Optional[int]) -> Optional[str]:
        for name, relay in self.relays.items():
            if athlete_id is not None and athlete_id in relay.all_ids():
                return name
        return None

    @property
    def main_squad(self) -> List[Athlete]:
        return [a for a in self.athletes if not a.in_youth_squad]

    @property
    def youth_squad(self) -> List[Athlete]:
        return [a for a in self.athletes if a.in_youth_squad]

    @property
    def scouting_points_left(self) -> int:
        return max(0, WEEKLY_SCOUTING_POINTS - self.scouting_points_used)

    def attitude_for(self, event_name: str) -> RaceAttitude:
        raw = self.event_attitude.get(event_name, RaceAttitude.NORMALE.value)
        try:
            return RaceAttitude(raw)
        except ValueError:
            return RaceAttitude.NORMALE

    @property
    def next_meet_is_home(self) -> bool:
        """Meets alternate home/away: odd-numbered meets are hosted in the club's own stadium."""
        next_meet_week = self.week if self.is_competition_week else self.week + self.weeks_until_competition
        return (next_meet_week // 4) % 2 == 1

    @property
    def active_events(self) -> List[str]:
        """Events active in the current mode."""
        if self.game_mode == "vertical_slice":
            return list(VERTICAL_SLICE_EVENTS)
        return list(EVENTS.keys())

    @property
    def current_date(self) -> date:
        return self.start_date + timedelta(days=(self.week - 1) * 7)

    @property
    def is_competition_week(self) -> bool:
        """Competitions occur every 4 in-game weeks."""
        return self.week % 4 == 0

    @property
    def weeks_until_competition(self) -> int:
        rem = 4 - (self.week % 4)
        return 0 if self.is_competition_week else rem

    @property
    def is_vertical_slice_complete(self) -> bool:
        """In the 8-week outdoor prototype, two meets take place (Week 4 & Week 8)."""
        return self.game_mode == "vertical_slice" and self.week > 8
