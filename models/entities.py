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
