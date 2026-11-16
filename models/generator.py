"""Procedural athlete, staff, scouting, and dilemma generation for Track & Field Manager."""

from __future__ import annotations

import random
from typing import Dict, List, Optional

from models.entities import (
    COACH_BASE_SKILL,
    COACH_STATS,
    EVENTS,
    VERTICAL_SLICE_EVENTS,
    Athlete,
    Coach,
    CompetitionTier,
    EthicalDilemma,
    GameState,
    PeriodizationPhase,
    Personality,
    SeasonObjective,
    Specialty,
    StaffMember,
    StaffRole,
    TrainingFocus,
    coach_hire_skills,
)

FIRST_NAMES: List[str] = [
    "Lorenzo", "Marco", "Giulia", "Sofia", "Alessandro", "Elena", "Matteo", "Chiara",
    "Luca", "Francesca", "Davide", "Alice", "Federico", "Martina", "Gabriele", "Sara",
    "Tommaso", "Giorgia", "Samuele", "Beatrice", "Edoardo", "Camilla", "Nicolò", "Viola",
    "Kofi", "Amara", "Kenji", "Soren", "Nadia", "Mateo", "Freya", "Tariq",
]

LAST_NAMES: List[str] = [
    "Rossi", "Bianchi", "Esposito", "Conti", "Moretti", "Greco", "Galli", "Ferri",
    "Rinaldi", "Lombardi", "De Luca", "Marchetti", "Barbieri", "Fontana", "Sartori", "Rizzo",
    "Bellini", "Caruso", "Mancini", "Leone", "Colombo", "Ricci", "Neri", "Villa",
    "Okafor", "Tanaka", "Lindqvist", "Silva", "Kowalski", "Alvarez",
]

RIVAL_TEAMS: Dict[CompetitionTier, List[str]] = {
    CompetitionTier.PROVINCIALE: [
        "GS Val d'Arno", "Polisportiva Nord", "Atletica Borgo", "CUS Collina",
        "Virtus Piana", "Runners San Marco", "Olympia Distretto",
    ],
    CompetitionTier.REGIONALE: [
        "Atletica Lombardia", "CUS Emilia", "Fiamme del Tirreno", "Pro Sport Veneto",
        "Libertas Piemonte", "Veloce Liguria", "Sport Club Toscana",
    ],
    CompetitionTier.NAZIONALE: [
        "Aeronautica Club", "Fiamme Azzurre Pro", "CUS Milano Elite", "Atletica Capitale",
        "Pro Patria Nazionale", "Gruppo Sportivo Nord", "Team Tricolore",
    ],
    CompetitionTier.INTERNAZIONALE: [
        "London Track Club", "Berlin Adler AC", "Paris Stade 92", "Madrid Atletismo",
        "Zurich Lions TF", "Tokyo Striders", "Stockholm Nordic AC",
    ],
}


def clamp_stat(value: float, low: int = 1, high: int = 100) -> int:
    """Clamp a numeric stat cleanly into [low, high]."""
    return max(low, min(high, int(round(value))))


def generate_athlete(
    tier: CompetitionTier = CompetitionTier.PROVINCIALE,
    specialty: Optional[Specialty] = None,
    rng: Optional[random.Random] = None,
    existing_names: Optional[set[str]] = None,
    youth_prospect: bool = False,
    age_range: Optional[tuple[int, int]] = None,
    base_offset: int = 0,
) -> Athlete:
    """Procedurally generate an athlete with discipline age curve, resilience, and personality."""
    r = rng or random.Random()
    used = existing_names or set()

    name = f"{r.choice(FIRST_NAMES)} {r.choice(LAST_NAMES)}"
    for _ in range(15):
        if name not in used:
            break
        name = f"{r.choice(FIRST_NAMES)} {r.choice(LAST_NAMES)}"

    chosen_specialty = specialty or r.choice(list(Specialty))
    if age_range is not None:
        age = r.randint(*age_range)
    elif youth_prospect:
        age = r.randint(15, 17)
    else:
        low_peak, high_peak = chosen_specialty.peak_age_range
        age = r.randint(max(18, low_peak - 2), high_peak + 2)

    base_map = {
        CompetitionTier.PROVINCIALE: 42,
        CompetitionTier.REGIONALE: 54,
        CompetitionTier.NAZIONALE: 67,
        CompetitionTier.INTERNAZIONALE: 79,
    }
    base = base_map[tier] - (10 if youth_prospect else 0) + base_offset

    def roll(bias: int = 0) -> int:
        return clamp_stat(r.gauss(base + bias, 7))

    if chosen_specialty == Specialty.SPRINTS:
        speed, stamina, strength, technique = roll(12), roll(-6), roll(3), roll(6)
    elif chosen_specialty == Specialty.MIDDLE_DISTANCE:
        speed, stamina, strength, technique = roll(2), roll(14), roll(-8), roll(4)
    elif chosen_specialty == Specialty.JUMPS:
        speed, stamina, strength, technique = roll(9), roll(-6), roll(4), roll(12)
    else:
        speed, stamina, strength, technique = roll(-8), roll(-6), roll(15), roll(10)

    resilience = clamp_stat(r.gauss(62 if not youth_prospect else 56, 12), 25, 96)
    potential = (
        r.randint(80, 96)
        if youth_prospect
        else clamp_stat(max(speed, stamina, strength, technique) + r.randint(4, 18), 55, 98)
    )
    personality = r.choice(list(Personality))
    fatigue = r.randint(6, 20)
    sleep_quality = r.randint(65, 90)
    nutrition = r.randint(65, 90)
    form = clamp_stat(70 - fatigue * 0.35 + r.randint(-4, 7))

    athlete = Athlete(
        id=None,
        name=name,
        age=age,
        specialty=chosen_specialty,
        speed=speed,
        stamina=stamina,
        strength=strength,
        technique=technique,
        resilience=resilience,
        form=form,
        fatigue=fatigue,
        potential=potential,
        personality=personality,
        training_focus=(
            TrainingFocus.EXPLOSIVE_POWER
            if chosen_specialty in (Specialty.SPRINTS, Specialty.JUMPS, Specialty.THROWS)
            else TrainingFocus.ENDURANCE
        ),
        periodization=PeriodizationPhase.PREP_GENERALE,
        sleep_quality=sleep_quality,
        nutrition=nutrition,
        weekly_wage=120,
        injured_weeks=0,
        is_youth_prospect=youth_prospect,
    )
    athlete.weekly_wage = senior_wage(athlete)
    return athlete


def generate_vertical_slice_roster(rng: Optional[random.Random] = None) -> List[Athlete]:
    """Generate 10 athletes across the 3 vertical-slice disciplines (Sprints, Jumps, Middle-distance)."""
    r = rng or random.Random()
    specialties = [
        Specialty.SPRINTS,
        Specialty.SPRINTS,
        Specialty.SPRINTS,
        Specialty.SPRINTS,
        Specialty.JUMPS,
        Specialty.JUMPS,
        Specialty.JUMPS,
        Specialty.MIDDLE_DISTANCE,
        Specialty.MIDDLE_DISTANCE,
        Specialty.MIDDLE_DISTANCE,
    ]
    roster: List[Athlete] = []
    used_names: set[str] = set()
    for idx, spec in enumerate(specialties, start=1):
        # Include 2 promising youth prospects from school meets
        is_youth = idx in (4, 10)
        athlete = generate_athlete(
            tier=CompetitionTier.PROVINCIALE,
            specialty=spec,
            rng=r,
            existing_names=used_names,
            youth_prospect=is_youth,
        )
        athlete.id = idx
        if idx == 1:
            athlete.personality = Personality.LEADER
        used_names.add(athlete.name)
        roster.append(athlete)
    return roster


def generate_initial_roster(rng: Optional[random.Random] = None) -> List[Athlete]:
    """Generate a balanced 8-athlete starting career roster covering all 4 specialties."""
    r = rng or random.Random()
    specialties = [
        Specialty.SPRINTS,
        Specialty.SPRINTS,
        Specialty.MIDDLE_DISTANCE,
        Specialty.MIDDLE_DISTANCE,
        Specialty.JUMPS,
        Specialty.JUMPS,
        Specialty.THROWS,
        Specialty.THROWS,
    ]
    roster: List[Athlete] = []
    used_names: set[str] = set()
    for idx, spec in enumerate(specialties, start=1):
        athlete = generate_athlete(
            tier=CompetitionTier.PROVINCIALE,
            specialty=spec,
            rng=r,
            existing_names=used_names,
            youth_prospect=(idx == 2),
        )
        athlete.id = idx
        if idx == 1:
            athlete.personality = Personality.LEADER
        used_names.add(athlete.name)
        roster.append(athlete)
    return roster


def generate_school_scouting_pool(
    tier: CompetitionTier,
    count: int = 4,
    rng: Optional[random.Random] = None,
    existing_names: Optional[set[str]] = None,
    vertical_slice_only: bool = False,
) -> List[Athlete]:
    """Generate young talents discovered at Campionati Studenteschi (ages 15-17)."""
    r = rng or random.Random()
    used = set(existing_names or set())
    allowed_specs = (
        [Specialty.SPRINTS, Specialty.JUMPS, Specialty.MIDDLE_DISTANCE]
        if vertical_slice_only
        else list(Specialty)
    )
    pool: List[Athlete] = []
    for i in range(count):
        prospect = generate_athlete(
            tier=tier,
            specialty=r.choice(allowed_specs),
            rng=r,
            existing_names=used,
            youth_prospect=(i < count - 1),  # mostly school kids, plus 1 senior free agent
        )
        used.add(prospect.name)
        pool.append(prospect)
    return pool


def generate_academy_prospects(
    count: int,
    rng: Optional[random.Random] = None,
    specialty: Optional[Specialty] = None,
    high_potential: bool = False,
    existing_names: Optional[set[str]] = None,
    allowed_specialties: Optional[List[Specialty]] = None,
) -> List[Athlete]:
    """Generate 14-17 year-old kids for the youth academy (vivaio).

    They are raw (low current stats) but can carry high potential; a
    "high potential" search guarantees Potential >= 85.
    """
    r = rng or random.Random()
    used = set(existing_names or set())
    pool_specs = allowed_specialties or list(Specialty)
    kids: List[Athlete] = []
    for _ in range(count):
        kid = generate_athlete(
            tier=CompetitionTier.PROVINCIALE,
            specialty=specialty or r.choice(pool_specs),
            rng=r,
            existing_names=used,
            youth_prospect=True,
            age_range=(14, 17),
            base_offset=-6,
        )
        kid.potential = r.randint(85, 97) if high_potential else r.randint(68, 95)
        kid.in_youth_squad = True
        kid.weekly_wage = 0
        used.add(kid.name)
        kids.append(kid)
    return kids


def senior_wage(athlete: Athlete) -> int:
    """Weekly wage for a main-squad athlete (academy kids are unpaid)."""
    wage_base = 80 if athlete.is_youth_prospect else 100
    return clamp_stat(wage_base + athlete.overall * 4.2, 95, 950)


# Main and secondary skill a coach of each specialty is usually hired for
SPECIALTY_COACH_FOCUS: Dict[Specialty, tuple[str, str]] = {
    Specialty.SPRINTS: ("speed", "technique"),
    Specialty.MIDDLE_DISTANCE: ("stamina", "speed"),
    Specialty.JUMPS: ("technique", "speed"),
    Specialty.THROWS: ("strength", "technique"),
}


def generate_coach(
    specialty: Optional[Specialty],
    primary: str,
    secondary: Optional[str],
    tier: int,
    rng: Optional[random.Random] = None,
    existing_names: Optional[set[str]] = None,
) -> Coach:
    """Create a coach: the chosen skills depend on the recruitment tier, the rest stay low."""
    r = rng or random.Random()
    used = existing_names or set()
    name = f"{r.choice(FIRST_NAMES)} {r.choice(LAST_NAMES)}"
    for _ in range(15):
        if name not in used:
            break
        name = f"{r.choice(FIRST_NAMES)} {r.choice(LAST_NAMES)}"
    prim_val, sec_val = coach_hire_skills(tier)
    skills = {stat: COACH_BASE_SKILL for stat in COACH_STATS}
    skills[primary] = prim_val
    if secondary is not None and secondary != primary:
        skills[secondary] = sec_val
    return Coach(id=None, name=name, specialty=specialty, skills=skills)


def create_initial_coaches(
    roster: List[Athlete], rng: Optional[random.Random] = None
) -> List[Coach]:
    """One entry-level coach for each specialty in the starting roster, athletes pre-assigned."""
    r = rng or random.Random()
    coaches: List[Coach] = []
    used: set[str] = set()
    for spec in Specialty:
        if not any(a.specialty == spec for a in roster):
            continue
        primary, secondary = SPECIALTY_COACH_FOCUS[spec]
        coach = generate_coach(spec, primary, secondary, tier=1, rng=r, existing_names=used)
        coach.id = len(coaches) + 1
        used.add(coach.name)
        coaches.append(coach)
        for a in roster:
            if a.specialty == spec:
                a.coach_id = coach.id
    return coaches


def create_initial_staff() -> List[StaffMember]:
    """Create the 3 medical & mental support staff candidates (coaches are separate)."""
    return [
        StaffMember(
            id=4,
            name="Dott.ssa Chiara Neri",
            role=StaffRole.PHYSIO,
            skill=4,
            weekly_cost=300,
            hired=False,
            description="Accelera recupero fatica (+8/sett) e dimezza durata infortuni.",
        ),
        StaffMember(
            id=5,
            name="Dott. Marco Conti",
            role=StaffRole.DOCTOR,
            skill=4,
            weekly_cost=340,
            hired=False,
            description="Riduce del 45% il rischio di infortuni da sovraccarico.",
        ),
        StaffMember(
            id=6,
            name="Dott. Luca Ferretti",
            role=StaffRole.MENTAL_COACH,
            skill=3,
            weekly_cost=220,
            hired=False,
            description="Stabilizza forma in gara e migliora la resa degli Impulsivi.",
        ),
    ]


def create_season_objectives(game_mode: str, tier: CompetitionTier) -> List[SeasonObjective]:
    """Create season goals for the club."""
    if game_mode == "vertical_slice":
        return [
            SeasonObjective("positive_budget", "Chiudi la stagione con bilancio sopra $8.000"),
            SeasonObjective("win_event", "Vinci almeno una gara ufficiale"),
            SeasonObjective("club_record", "Stabilisci un nuovo Record Sociale omologato (vento <= 2.0 m/s)"),
        ]
    return [
        SeasonObjective("positive_budget", "Mantieni il bilancio sopra $10.000"),
        SeasonObjective(
            "promote",
            f"Ottieni la promozione dalla categoria {tier.value}",
        ),
        SeasonObjective("historic_mark", "Abbatti un traguardo storico (es. sub-11.00s nei 100m)"),
    ]


def build_default_lineup(
    athletes: List[Athlete],
    event_names: Optional[List[str]] = None,
) -> Dict[str, Optional[int]]:
    """Auto-assign the strongest available athlete to each active event."""
    targets = event_names or list(EVENTS.keys())
    lineup: Dict[str, Optional[int]] = {}
    used_ids: set[int] = set()
    for event_name in targets:
        event_def = EVENTS[event_name]
        candidates = [
            a for a in athletes if not a.is_injured and not a.in_youth_squad and a.id is not None
        ]
        if not candidates:
            lineup[event_name] = None
            continue

        def event_score(a: Athlete) -> float:
            specialty_bonus = 12.0 if a.specialty == event_def.specialty else 0.0
            unused_bonus = 8.0 if a.id not in used_ids else 0.0
            weighted = (
                a.speed * event_def.weights["speed"]
                + a.stamina * event_def.weights["stamina"]
                + a.strength * event_def.weights["strength"]
                + a.technique * event_def.weights["technique"]
            )
            return weighted + specialty_bonus + unused_bonus + a.form * 0.15

        best = max(candidates, key=event_score)
        lineup[event_name] = best.id
        if best.id is not None:
            used_ids.add(best.id)
    return lineup


def get_meet_name(week: int, tier: CompetitionTier, season_phase_label: str = "Outdoor") -> str:
    """Return a realistic meet title for a given week and tier."""
    meet_num = max(1, week // 4)
    phase_short = season_phase_label.split(" ")[0]
    return f"Meeting {tier.value} {phase_short} #{meet_num}"


def get_rival_teams(tier: CompetitionTier) -> List[str]:
    return RIVAL_TEAMS.get(tier, RIVAL_TEAMS[CompetitionTier.PROVINCIALE])


def get_recruitment_fee(athlete: Athlete) -> int:
    if athlete.is_youth_prospect:
        return max(300, athlete.potential * 9)
    return max(500, athlete.overall * 30)


def maybe_generate_dilemma(
    state: GameState,
    rng: Optional[random.Random] = None,
) -> Optional[EthicalDilemma]:
    """Occasionally present a dramatic ethical dilemma tied to sponsors or shortcuts."""
    if state.pending_dilemma is not None or not state.athletes:
        return None
    r = rng or random.Random()
    # Trigger around weeks 3, 6, 10... with 55% chance on week 3/7 for vertical slice playability
    if state.week not in (3, 7) and r.random() > 0.22:
        return None

    star = max(state.athletes, key=lambda a: a.overall)
    if state.week % 2 == 1:
        return EthicalDilemma(
            id=f"doping_w{state.week}",
            title="Scorciatoia Farmacologica?",
            description=(
                f"Uno sponsor ambizioso ti offre un integratore 'sperimentale' non ancora "
                f"tracciato per {star.name} in vista della prossima gara, insieme a un bonus di $1.800.\n\n"
                "Accettare garantisce prestazioni immediate, ma espone il club a squalifiche e crollo "
                "della reputazione. Rifiutare protegge l'etica del club ma fa perdere lo sponsor."
            ),
            accept_label="Accetta scorciatoia (+Forma & +$1.800, alto rischio squalifica)",
            reject_label="Rifiuta con fermezza (+Reputazione, perdi $600 di sponsor)",
            athlete_id=star.id,
        )
    return EthicalDilemma(
        id=f"youth_push_w{state.week}",
        title="Forzare il Giovane Talento?",
        description=(
            f"La stampa locale vuole vedere subito in gara il tuo atleta {star.name} al massimo carico, "
            "anche se il medico suggerisce prudenza per proteggere la sua crescita a lungo termine."
        ),
        accept_label="Spremi l'atleta per visibilità (+$1.000 sponsor, +22 Fatica)",
        reject_label="Proteggi la crescita (+8 Resilienza & Forma, -$300 incasso)",
        athlete_id=star.id,
    )
