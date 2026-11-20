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
    def display_name(self) -> str:
        """Nome mostrato in interfaccia (il `value` resta quello salvato nel DB e usato come chiave)."""
        return TIER_DISPLAY_NAMES[self]

    @property
    def order(self) -> int:
        return TIER_ORDER.index(self)

    @property
    def next_tier(self) -> Optional["CompetitionTier"]:
        idx = self.order
        if idx + 1 < len(TIER_ORDER):
            return TIER_ORDER[idx + 1]
        return None

    @property
    def previous_tier(self) -> Optional["CompetitionTier"]:
        idx = self.order
        return TIER_ORDER[idx - 1] if idx > 0 else None


TIER_ORDER: List[CompetitionTier] = [
    CompetitionTier.PROVINCIALE,
    CompetitionTier.REGIONALE,
    CompetitionTier.NAZIONALE,
    CompetitionTier.INTERNAZIONALE,
]

# Nomi dei livelli come gli vede il giocatore (Q18: slot dei Campionati di Società). Solo testo: il `value`
# dell'enum NON si cambia, perché è scritto nei salvataggi e usato come chiave (es. TICKET_PRICE).
TIER_DISPLAY_NAMES: Dict[CompetitionTier, str] = {
    CompetitionTier.PROVINCIALE: "Fase regionale CdS",
    CompetitionTier.REGIONALE: "Finale Bronzo",
    CompetitionTier.NAZIONALE: "Finale Argento",
    CompetitionTier.INTERNAZIONALE: "Finale Oro / Coppa Europa",
}

# Economia (PIANOLAVORO A.1, 2026-11-20). Sponsor società +40% e montepremi +25% rispetto ai valori precedenti
# (600/1250/2500/4800 e 1200/2800/6000/12500). I rimborsi spese degli atleti sono scesi del 45% (non del 20% del
# piano: con -20% il flusso restava a -3.237 €/sett.): vedi WAGE_* sotto e docs/BALANCE.md §A.
TIER_CONFIG: Dict[CompetitionTier, Dict[str, int]] = {
    CompetitionTier.PROVINCIALE: {
        "weekly_sponsor": 840,
        "prize_base": 1500,
        "opponent_skill": 42,
        "travel_cost": 350,
    },
    CompetitionTier.REGIONALE: {
        "weekly_sponsor": 1750,
        "prize_base": 3500,
        "opponent_skill": 56,
        "travel_cost": 750,
    },
    CompetitionTier.NAZIONALE: {
        "weekly_sponsor": 3500,
        "prize_base": 7500,
        "opponent_skill": 70,
        "travel_cost": 1500,
    },
    CompetitionTier.INTERNAZIONALE: {
        "weekly_sponsor": 6720,
        "prize_base": 15625,
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
    RESILIENTE = "Resiliente"


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

# Bonus al bersaglio di forma per la fase «Gara (Picco)», solo nel tick che precede una settimana di gara
# (la forma usata in gara è quella calcolata nel tick precedente). Minore del +9 dello Scarico: il picco
# non toglie la fatica, quindi è più debole del tapering vero e proprio.
PEAK_FORM_BONUS = 6

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
# Rimborso spese settimanale di un atleta di Prima Squadra: base + overall × WAGE_PER_OVERALL, tra WAGE_MIN e WAGE_MAX.
# (prima 100|80 + overall × 4,2, tra 95 e 950: -45%). Vale per gli atleti creati o promossi da ora: i salvataggi
# esistenti tengono i rimborsi già scritti (mai rivisti dopo la creazione, vedi AUDIT R14).
WAGE_BASE_ADULT = 55
WAGE_BASE_PROSPECT = 45  # giovani promettenti (`is_youth_prospect`)
WAGE_PER_OVERALL = 2.3
WAGE_MIN = 52
WAGE_MAX = 520
# Bonus una tantum per la promozione di categoria, a fine stagione (PIANOLAVORO A.1).
PROMOTION_BONUS = 5000
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


# Fasce d'età FIDAL (Q17): (età massima inclusa, nome). Si calcolano da `Athlete.age`, non si salvano: il gioco non ha
# l'anno di nascita e l'età cresce di 1 a ogni cambio stagione. Sotto i 14 anni vale la prima fascia.
AGE_CATEGORIES: List[Tuple[int, str]] = [
    (15, "Cadetti"),
    (17, "Allievi"),
    (19, "Juniores"),
    (22, "Promesse"),
]
AGE_CATEGORY_SENIOR = "Seniores"  # 23 anni e oltre
# Convocazioni (regolamento FIDAL art. 3.3 e 5.7): al massimo 2 gare individuali + 1 staffetta per atleta e meeting.
# La staffetta è già unica per atleta (vedi `GameState.relay_of`); qui il tetto delle gare individuali.
MAX_INDIVIDUAL_EVENTS = 2
# Q17: sotto questa età non si gareggia nel livello «Internazionale» (Finale Oro / Coppa Europa).
INTERNATIONAL_MIN_AGE = 20
# Contratti (Q22): durata di 1-3 stagioni, rinnovo automatico alla scadenza; per annullarlo si svincola l'atleta.
CONTRACT_MAX_SEASONS = 3


def age_category(age: int) -> str:
    """Fascia d'età FIDAL: Cadetti 14-15, Allievi 16-17, Juniores 18-19, Promesse 20-22, Seniores 23+."""
    for max_age, name in AGE_CATEGORIES:
        if age <= max_age:
            return name
    return AGE_CATEGORY_SENIOR


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
    base_seconds_f: float = 0.0
    span_seconds_f: float = 0.0
    min_seconds_f: float = 0.0


RELAYS: Dict[str, RelayDefinition] = {
    "4x100m": RelayDefinition(
        name="4x100m",
        leg_weights={"speed": 0.70, "technique": 0.20, "strength": 0.10},
        base_seconds=50.4,
        span_seconds=11.2,
        min_seconds=36.8,
        indoor=False,
        requires_event="100m",
        base_seconds_f=55.0,
        span_seconds_f=11.8,
        min_seconds_f=40.8,
    ),
    "4x400m": RelayDefinition(
        name="4x400m",
        leg_weights={"speed": 0.50, "stamina": 0.40, "technique": 0.10},
        base_seconds=229.0,
        span_seconds=50.0,
        min_seconds=174.0,
        indoor=True,
        requires_event="400m",
        base_seconds_f=250.0,
        span_seconds_f=53.0,
        min_seconds_f=195.0,
    ),
}
RELAY_LEG_WEIGHTS: List[float] = [0.24, 0.24, 0.24, 0.28]  # the anchor leg counts a bit more
RELAY_CHANGE_COOLDOWN_WEEKS = 4
# Moltiplicatore della probabilità di squalifica per staffetta (Q20). Nella 4x400 il cambio non è lanciato e
# i frazionisti sono più lenti: il cambio fuori zona è più raro. Valore confermato dall'utente (2026-11-19).
RELAY_DQ_MULT: Dict[str, float] = {"4x100m": 1.0, "4x400m": 0.5}
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
    historic_mark_f: Optional[float] = None
    historic_label_f: str = ""


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
        historic_mark_f=11.80,
        historic_label_f="sub-11.80s nei 100m",
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
        historic_mark_f=52.00,
        historic_label_f="sub-52.00s nei 400m",
    ),
    "800m": EventDefinition(
        name="800m",
        specialty=Specialty.MIDDLE_DISTANCE,
        unit="min",
        lower_is_better=True,
        wind_affected=False,
        historic_mark=113.0,  # 1:53.00 (stima: stesso score storico del 1500m)
        historic_label="sub-1:53.00 negli 800m",
        weights={"stamina": 0.40, "speed": 0.38, "technique": 0.15, "strength": 0.07},
        historic_mark_f=128.0,  # 2:08.00
        historic_label_f="sub-2:08.00 negli 800m",
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
        historic_mark_f=260.0,  # 4:20.00
        historic_label_f="sub-4:20.00 nei 1500m",
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
        historic_mark_f=6.60,
        historic_label_f="oltre 6.60m nel Lungo",
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
        historic_mark_f=16.50,
        historic_label_f="oltre 16.50m nel Peso",
    ),
}

# Curva punteggio -> tempo dell'800m (Q16): secondi = a - norm * b, minimo = record del mondo (M Rudisha 2012,
# F Kratochvilova 1983). Le ancore (score 42/56/84: M 2:05 / 1:58,5 / 1:45,5, F 2:21 / 2:14,7 / 2:02) sono STIME.
MIDDLE_800M_CURVE: Dict[str, Tuple[float, float, float]] = {  # sesso -> (a, b, minimo)
    "M": (144.5, 46.4, 100.91),
    "F": (160.0, 45.2, 113.28),
}

VERTICAL_SLICE_EVENTS: List[str] = ["100m", "Salto in Lungo", "1500m"]


# Nationality name -> flag emoji. Most of the pool is Italian; the rest are foreign athletes.
NATIONALITIES: Dict[str, str] = {
    "Italia": "🇮🇹",
    "Francia": "🇫🇷",
    "Spagna": "🇪🇸",
    "Germania": "🇩🇪",
    "Regno Unito": "🇬🇧",
    "Stati Uniti": "🇺🇸",
    "Canada": "🇨🇦",
    "Giamaica": "🇯🇲",
    "Kenya": "🇰🇪",
    "Etiopia": "🇪🇹",
    "Nigeria": "🇳🇬",
    "Brasile": "🇧🇷",
    "Giappone": "🇯🇵",
    "Australia": "🇦🇺",
}


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
    nationality: str = "Italia"
    contract_end_season: int = 0  # ultima stagione di contratto (inclusa); 0 = nessuno (vivaio) o ancora da assegnare
    height_cm: int = 0  # 0 = not yet generated (old saves)
    weight_kg: int = 0
    gender: str = "M"
    contract_no_renew: bool = False  # il giocatore non vuole rinnovarlo: alla scadenza lascia la società

    @property
    def gender_label(self) -> str:
        return "Donna" if self.gender == "F" else "Uomo"

    @property
    def flag(self) -> str:
        return NATIONALITIES.get(self.nationality, "🏳")

    @property
    def height_display(self) -> str:
        return f"{self.height_cm / 100:.2f} m" if self.height_cm else "—"

    @property
    def weight_display(self) -> str:
        return f"{self.weight_kg} kg" if self.weight_kg else "—"

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
    def age_category(self) -> str:
        return age_category(self.age)

    def can_race_in(self, tier: "CompetitionTier") -> bool:
        """Gli under 20 non gareggiano nel livello Internazionale (Q17)."""
        return tier != CompetitionTier.INTERNAZIONALE or self.age >= INTERNATIONAL_MIN_AGE

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


# ---------------------------------------------------------------- rival clubs
RIVAL_RACE_SIGMA = 4.5  # day-to-day variance of a rival's performance
RIVAL_RETIREMENT_AGE = 33
RIVAL_SEASON_INFLATION = 0.8  # each season new rival recruits are a bit stronger
RIVAL_TREND_SNAPSHOTS = 13  # one every 4 weeks: about a year of history


@dataclass
class RivalAthlete:
    """A named athlete of a rival club. Their level uses the same scale as race scores."""

    name: str
    event: str
    age: int
    skill: float
    pb: Optional[float] = None
    pb_display: Optional[str] = None
    gender: str = "M"


@dataclass
class RivalClub:
    """A rival club that develops over time: young athletes grow, veterans decline and retire.

    Ambition (0.6-1.6) scales how much the club invests in progress; it rises when
    the club keeps finishing behind the player and drops when it is comfortably ahead.
    """

    name: str
    tier: CompetitionTier
    ambition: float
    offset: float = 0.0  # club quality vs the category average (drives its recruits)
    athletes: Dict[str, RivalAthlete] = field(default_factory=dict)
    female_athletes: Dict[str, RivalAthlete] = field(default_factory=dict)
    history: List[float] = field(default_factory=list)  # average level, one snapshot every 4 weeks

    def athletes_for(self, gender: str = "M") -> Dict[str, RivalAthlete]:
        return self.female_athletes if gender == "F" else self.athletes

    def athlete_for(self, event: str, gender: str = "M") -> Optional[RivalAthlete]:
        pool = self.female_athletes if gender == "F" else self.athletes
        return pool.get(event) or self.athletes.get(event)

    def level(self, events: Optional[List[str]] = None, gender: Optional[str] = None) -> float:
        pools: List[Dict[str, RivalAthlete]] = []
        if gender in (None, "M"):
            pools.append(self.athletes)
        if gender in (None, "F") and self.female_athletes:
            pools.append(self.female_athletes)
        vals = [a.skill for p in pools for e, a in p.items() if events is None or e in events]
        return sum(vals) / len(vals) if vals else 0.0

    @property
    def trend(self) -> float:
        """Change in average level over the stored history (about the last year)."""
        if len(self.history) < 2:
            return 0.0
        return self.history[-1] - self.history[0]

    @property
    def ambition_label(self) -> str:
        if self.ambition >= 1.2:
            return "Ambiziosa"
        if self.ambition <= 0.85:
            return "Appagata"
        return "Stabile"

    def star(self, events: Optional[List[str]] = None, gender: Optional[str] = None) -> Optional[RivalAthlete]:
        pools: List[Dict[str, RivalAthlete]] = []
        if gender in (None, "M"):
            pools.append(self.athletes)
        if gender in (None, "F") and self.female_athletes:
            pools.append(self.female_athletes)
        pool = [a for p in pools for e, a in p.items() if events is None or e in events]
        return max(pool, key=lambda a: a.skill) if pool else None


# ---------------------------------------------------------------- league promotion & relegation
PROMOTION_SPOTS = 2  # top 2 of the final league table move up
RELEGATION_SPOTS = 1  # last club moves down


class SeasonOutcome(str, Enum):
    PROMOTED = "Promossa"
    STAYED = "Salvezza"
    RELEGATED = "Retrocessa"
    CHAMPION = "Campione"


@dataclass
class SeasonEndResult:
    """Final league table of a season and what it meant for the club."""

    season: int
    tier: CompetitionTier
    placement: int
    outcome: SeasonOutcome
    final_table: List[Tuple[str, int]] = field(default_factory=list)
    new_tier: Optional[CompetitionTier] = None


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
    gender: str = ""

    @property
    def display_event_name(self) -> str:
        if self.gender in ("M", "F"):
            return f"{self.event_name} ({self.gender})"
        return self.event_name


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


# Stessa lista (valore, etichetta), stesso ordine, per i due punti di ingresso di "nuova partita"
# (StartScreen e NewGameDialog): prima erano in ordine opposto con default diversi.
GAME_MODE_OPTIONS: List[Tuple[str, str]] = [
    ("career", "Carriera Completa (Outdoor, Cross, Indoor, Promozioni)"),
    ("vertical_slice", "Prototipo Outdoor (10 atleti, 3 discipline, 2 gare)"),
]


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
    rival_clubs: List[RivalClub] = field(default_factory=list)
    season_history: List[SeasonEndResult] = field(default_factory=list)  # newest first
    event_lineup_f: Dict[str, Optional[int]] = field(default_factory=dict)
    club_records_f: Dict[str, Tuple[float, str, str]] = field(default_factory=dict)
    relays_f: Dict[str, Relay] = field(default_factory=dict)

    def lineup_for(self, gender: str = "M") -> Dict[str, Optional[int]]:
        return self.event_lineup_f if gender == "F" else self.event_lineup

    def records_for(self, gender: str = "M") -> Dict[str, Tuple[float, str, str]]:
        return self.club_records_f if gender == "F" else self.club_records

    def relays_for(self, gender: str = "M") -> Dict[str, Relay]:
        return self.relays_f if gender == "F" else self.relays

    def league_standings(self) -> List[Tuple[str, int]]:
        """Current league table with every club of the category (0 points if not scored yet).

        Ties are broken alphabetically so the order is stable.
        """
        table = {self.team_name: 0}
        table.update({c.name: 0 for c in self.rivals_in()})
        table.update({k: v for k, v in self.league_table.items() if k in table})
        return sorted(table.items(), key=lambda kv: (-kv[1], kv[0]))

    @property
    def league_position(self) -> int:
        for idx, (team, _pts) in enumerate(self.league_standings(), start=1):
            if team == self.team_name:
                return idx
        return 0

    @property
    def weeks_to_season_end(self) -> Optional[int]:
        """Weeks left before the final league table is drawn up (career mode only)."""
        if self.game_mode != "career":
            return None
        return 36 - ((self.week - 1) % 36)

    def rivals_in(self, tier: Optional[CompetitionTier] = None) -> List[RivalClub]:
        t = tier or self.tier
        return [c for c in self.rival_clubs if c.tier == t]

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

    def lineup_problem(self, athlete: Athlete, event_name: str, gender: str) -> Optional[str]:
        """Motivo (in italiano) per cui `athlete` non può essere convocato in `event_name`, o None se può.

        Regole: stessa divisione, Prima Squadra, età minima del livello (Q17) e al massimo
        `MAX_INDIVIDUAL_EVENTS` gare individuali tra quelle attive (le altre non si disputano).
        """
        if athlete.gender != gender:
            return f"{athlete.name} non può gareggiare nella divisione {gender}."
        if athlete.in_youth_squad:
            return f"{athlete.name} è nel vivaio e non gareggia."
        if not athlete.can_race_in(self.tier):
            return (
                f"{athlete.name} ha {athlete.age} anni: in {self.tier.display_name} "
                f"gareggiano solo atleti dai {INTERNATIONAL_MIN_AGE} anni."
            )
        lineup = self.lineup_for(gender)
        others = [e for e in self.active_events if e != event_name and lineup.get(e) == athlete.id]
        if len(others) >= MAX_INDIVIDUAL_EVENTS:
            return (
                f"{athlete.name} è già iscritto a {len(others)} gare individuali "
                f"({', '.join(others)}): il massimo è {MAX_INDIVIDUAL_EVENTS} più una staffetta."
            )
        return None

    def relay_of(self, athlete_id: Optional[int], gender: Optional[str] = None) -> Optional[str]:
        if athlete_id is None:
            return None
        pools = (
            [self.relays_for(gender)]
            if gender in ("M", "F")
            else [self.relays, self.relays_f]
        )
        for pool in pools:
            for name, relay in pool.items():
                if athlete_id in relay.all_ids():
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
