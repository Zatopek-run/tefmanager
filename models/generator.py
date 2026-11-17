"""Procedural athlete, staff, scouting, and dilemma generation for Track & Field Manager."""

from __future__ import annotations

import csv
from pathlib import Path
import random
import re
from typing import Dict, List, Optional

from models.entities import (
    COACH_BASE_SKILL,
    COACH_STATS,
    EVENTS,
    VERTICAL_SLICE_EVENTS,
    RIVAL_SEASON_INFLATION,
    TIER_CONFIG,
    Athlete,
    Coach,
    CompetitionTier,
    EthicalDilemma,
    GameState,
    NATIONALITIES,
    PeriodizationPhase,
    Personality,
    RivalAthlete,
    RivalClub,
    SeasonObjective,
    Specialty,
    StaffMember,
    StaffRole,
    TrainingFocus,
    coach_hire_skills,
)

MALE_FIRST_NAMES: List[str] = [
    "Lorenzo", "Marco", "Alessandro", "Matteo", "Luca", "Davide", "Federico", "Gabriele",
    "Tommaso", "Samuele", "Edoardo", "Nicolò", "Kofi", "Kenji", "Soren", "Mateo", "Tariq",
]

FEMALE_NAME_LIST: List[str] = [
    "Giulia", "Sofia", "Elena", "Chiara", "Francesca", "Alice", "Martina", "Sara",
    "Giorgia", "Beatrice", "Camilla", "Viola", "Amara", "Nadia", "Freya", "Yuki", "Amina",
]

FIRST_NAMES: List[str] = [
    "Lorenzo", "Marco", "Giulia", "Sofia", "Alessandro", "Elena", "Matteo", "Chiara",
    "Luca", "Francesca", "Davide", "Alice", "Federico", "Martina", "Gabriele", "Sara",
    "Tommaso", "Giorgia", "Samuele", "Beatrice", "Edoardo", "Camilla", "Nicolò", "Viola",
    "Kofi", "Amara", "Kenji", "Soren", "Nadia", "Mateo", "Freya", "Tariq",
]

FEMALE_FIRST_NAMES: frozenset[str] = frozenset(FEMALE_NAME_LIST)


def infer_gender(athlete_name: str) -> str:
    """Infer 'F' or 'M' from an athlete's first name (defaults to 'M')."""
    first = athlete_name.strip().split(" ", 1)[0] if athlete_name else ""
    return "F" if first in FEMALE_FIRST_NAMES else "M"

LAST_NAMES: List[str] = [
    "Rossi", "Bianchi", "Esposito", "Conti", "Moretti", "Greco", "Galli", "Ferri",
    "Rinaldi", "Lombardi", "De Luca", "Marchetti", "Barbieri", "Fontana", "Sartori", "Rizzo",
    "Bellini", "Caruso", "Mancini", "Leone", "Colombo", "Ricci", "Neri", "Villa",
    "Okafor", "Tanaka", "Lindqvist", "Silva", "Kowalski", "Alvarez",
]

RIVAL_TEAMS: Dict[CompetitionTier, List[str]] = {
    CompetitionTier.PROVINCIALE: [
        "Atletica Frascati", "Atletica Tivoli", "Tirreno Atl. Civitavecchia", "CUS Cassino",
        "Atletica Viterbo", "Atletica Sora", "Olimpia Terracina",
    ],
    CompetitionTier.REGIONALE: [
        "Atl. Stud. Rieti A. Milardi", "Nissolino Intesatletica Latina", "S.S. Lazio Atletica",
        "Atl. Roma Acquacetosa", "ACSI Atl. Campidoglio", "Atl. Villa Gordiani", "Atl. Villa Guglielmi",
    ],
    CompetitionTier.NAZIONALE: [
        "G.A. Fiamme Gialle", "C.S. Esercito", "G.S. Fiamme Azzurre", "C.S. Aeronautica Militare",
        "Nissolino Sport Roma", "Circolo Canottieri Aniene", "Fiamme Gialle G. Simoni",
    ],
    CompetitionTier.INTERNAZIONALE: [
        "London Track Club", "Berlin Adler AC", "Paris Stade 92", "Madrid Atletismo",
        "Zurich Lions TF", "Tokyo Striders", "Stockholm Nordic AC",
    ],
}

LAZIO_PROVINCES: Tuple[str, ...] = ("Roma", "Latina", "Frosinone", "Rieti", "Viterbo")
LAZIO_CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "societa_atletica_lazio.csv"
_LEGAL_PREFIX = re.compile(r"^(?:A\.?S\.?D\.?|S\.?S\.?D\.?|A\.?P\.?D\.?|U\.?S\.?)\s+", re.IGNORECASE)
_LEGAL_SUFFIX = re.compile(
    r"(?:\s+(?:S\.?S\.?D\.?|A\.?S\.?D\.?|S\.?R\.?L\.?|A\s*R\.?L\.?|A\.?P\.?S\.?|A\.?S\.?U\.?|S\.?P\.?A\.?|SSDRL|ARL))+$",
    re.IGNORECASE,
)
_KEEP_UPPER = {"ASD", "CUS", "GS", "CS", "GA", "SS", "US", "GSBR", "LUISS", "LBM", "ACSI", "CBS", "EUR", "ASI", "AL.PA."}


def _format_lazio_club_name(raw: str) -> str:
    name = " ".join(raw.strip().split())
    for _ in range(3):
        cleaned = _LEGAL_PREFIX.sub("", name)
        cleaned = _LEGAL_SUFFIX.sub("", cleaned).strip(" -.,")
        if cleaned == name:
            break
        name = cleaned
    name = re.sub(r"\bATL\.", "Atl. ", name, flags=re.IGNORECASE)
    name = " ".join(name.split())
    words: List[str] = []
    for tok in name.split(" "):
        up = tok.upper()
        if up in _KEEP_UPPER or re.fullmatch(r"[A-Z]\.(?:[A-Z]\.)+", up):
            words.append(up)
        elif "'" in tok:
            head, tail = tok.split("'", 1)
            words.append(head.capitalize() + "'" + tail.capitalize())
        else:
            words.append(tok.capitalize())
    return " ".join(words)


def load_lazio_clubs(csv_path: Optional[Path] = None) -> Dict[str, List[str]]:
    """Load real Lazio athletics clubs grouped by province from CSV."""
    path = csv_path or LAZIO_CSV_PATH
    grouped: Dict[str, List[str]] = {p: [] for p in LAZIO_PROVINCES}
    if not path.is_file():
        return grouped
    seen: set[str] = set()
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            prov = (row.get("Provincia") or "").strip()
            raw_name = (row.get("Denominazione_Societa") or "").strip()
            if prov not in grouped or not raw_name:
                continue
            pretty = _format_lazio_club_name(raw_name)
            key = pretty.casefold()
            if not pretty or key in seen:
                continue
            seen.add(key)
            grouped[prov].append(pretty)
    return grouped


def clamp_stat(value: float, low: int = 1, high: int = 100) -> int:
    """Clamp a numeric stat cleanly into [low, high]."""
    return max(low, min(high, int(round(value))))


def generate_nationality(r: random.Random) -> str:
    """About 70% of athletes are Italian, the rest come from the other countries."""
    if r.random() < 0.7:
        return "Italia"
    return r.choice([n for n in NATIONALITIES if n != "Italia"])


# (mean height cm, height sd, mean BMI) per discipline: throwers are heavy, distance runners lean.
_BODY_PROFILE = {
    Specialty.SPRINTS: (182, 6, 22.6),
    Specialty.MIDDLE_DISTANCE: (176, 6, 20.4),
    Specialty.JUMPS: (183, 6, 21.4),
    Specialty.THROWS: (189, 6, 27.5),
}


def generate_body(
    specialty: Specialty, r: random.Random, age: int = 24, gender: str = "M"
) -> tuple[int, int]:
    """Height (cm) and weight (kg) consistent with the discipline and gender."""
    mean_h, sd, bmi_mean = _BODY_PROFILE[specialty]
    if gender == "F":
        mean_h -= 11
        bmi_mean -= 1.4 if specialty != Specialty.THROWS else 1.8
    growth = 0 if age >= 18 else (18 - age) * 2.5
    height = int(round(max(148, min(205, r.gauss(mean_h - growth, sd)))))
    bmi = max(17.0, r.gauss(bmi_mean, 1.0))
    weight = int(round(bmi * (height / 100) ** 2))
    return height, weight


def generate_athlete(
    tier: CompetitionTier = CompetitionTier.PROVINCIALE,
    specialty: Optional[Specialty] = None,
    rng: Optional[random.Random] = None,
    existing_names: Optional[set[str]] = None,
    youth_prospect: bool = False,
    age_range: Optional[tuple[int, int]] = None,
    base_offset: int = 0,
    gender: Optional[str] = None,
) -> Athlete:
    """Procedurally generate an athlete with discipline age curve, resilience, and personality."""
    r = rng or random.Random()
    used = existing_names or set()
    chosen_gender = gender if gender in ("M", "F") else r.choice(("M", "F"))
    first_pool = FEMALE_NAME_LIST if chosen_gender == "F" else MALE_FIRST_NAMES

    name = f"{r.choice(first_pool)} {r.choice(LAST_NAMES)}"
    for _ in range(15):
        if name not in used:
            break
        name = f"{r.choice(first_pool)} {r.choice(LAST_NAMES)}"

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

    height_cm, weight_kg = generate_body(chosen_specialty, r, age, chosen_gender)
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
        nationality=generate_nationality(r),
        height_cm=height_cm,
        weight_kg=weight_kg,
        gender=chosen_gender,
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
        # Include 2 promising youth prospects from school meets; balance M & F in each discipline
        is_youth = idx in (4, 10)
        athlete = generate_athlete(
            tier=CompetitionTier.PROVINCIALE,
            specialty=spec,
            rng=r,
            existing_names=used_names,
            youth_prospect=is_youth,
            gender="M" if idx % 2 == 1 else "F",
        )
        athlete.id = idx
        if idx == 1:
            athlete.personality = Personality.LEADER
        used_names.add(athlete.name)
        roster.append(athlete)
    return roster


def generate_initial_roster(rng: Optional[random.Random] = None) -> List[Athlete]:
    """Generate a balanced 16-athlete starting career roster (8 M + 8 F across all 4 specialties)."""
    r = rng or random.Random()
    specialties = [
        Specialty.SPRINTS,
        Specialty.MIDDLE_DISTANCE,
        Specialty.JUMPS,
        Specialty.THROWS,
    ]
    slots = [
        (spec, gender)
        for _cycle in range(2)
        for spec in specialties
        for gender in ("M", "F")
    ]
    roster: List[Athlete] = []
    used_names: set[str] = set()
    for idx, (spec, gender) in enumerate(slots, start=1):
        athlete = generate_athlete(
            tier=CompetitionTier.PROVINCIALE,
            specialty=spec,
            rng=r,
            existing_names=used_names,
            youth_prospect=(idx == 2),
            gender=gender,
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
    gender: Optional[str] = None,
) -> Dict[str, Optional[int]]:
    """Auto-assign the strongest available athlete (optionally filtered by gender) to each active event."""
    targets = event_names or list(EVENTS.keys())
    lineup: Dict[str, Optional[int]] = {}
    used_ids: set[int] = set()
    for event_name in targets:
        event_def = EVENTS[event_name]
        candidates = [
            a
            for a in athletes
            if not a.is_injured
            and not a.in_youth_squad
            and a.id is not None
            and (gender is None or a.gender == gender)
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


def generate_rival_athlete(
    event: str,
    tier: CompetitionTier,
    club_offset: float,
    season: int = 1,
    rng: Optional[random.Random] = None,
    age_range: tuple[int, int] = (19, 32),
    gender: str = "M",
) -> RivalAthlete:
    """A rival club athlete; later seasons produce slightly stronger recruits."""
    r = rng or random.Random()
    base = TIER_CONFIG[tier]["opponent_skill"] + club_offset + RIVAL_SEASON_INFLATION * (season - 1)
    first_pool = FEMALE_NAME_LIST if gender == "F" else MALE_FIRST_NAMES
    return RivalAthlete(
        name=f"{r.choice(first_pool)} {r.choice(LAST_NAMES)}",
        event=event,
        age=r.randint(*age_range),
        skill=round(r.gauss(base, 5.5), 2),
        gender=gender,
    )


def _rival_tier_names(
    r: random.Random,
    province: Optional[str],
    team_name: Optional[str],
) -> Dict[CompetitionTier, List[str]]:
    tier_names = {tier: list(names) for tier, names in RIVAL_TEAMS.items()}
    if not province or province not in LAZIO_PROVINCES:
        return tier_names
    by_prov = load_lazio_clubs()
    reserved = {n.casefold() for n in tier_names[CompetitionTier.NAZIONALE]}
    if team_name:
        reserved.add(team_name.strip().casefold())
    prov_pool = [n for n in by_prov.get(province, []) if n.casefold() not in reserved]
    all_lazio = [n for p in LAZIO_PROVINCES for n in by_prov.get(p, []) if n.casefold() not in reserved]
    if not all_lazio:
        return tier_names
    r.shuffle(prov_pool)
    prov_picked = prov_pool[:7]
    if len(prov_picked) < 7:
        used = {n.casefold() for n in prov_picked}
        extra = [n for n in all_lazio if n.casefold() not in used]
        r.shuffle(extra)
        prov_picked.extend(extra[: 7 - len(prov_picked)])
    used_all = reserved | {n.casefold() for n in prov_picked}
    reg_pool = [n for n in all_lazio if n.casefold() not in used_all]
    r.shuffle(reg_pool)
    if len(prov_picked) == 7:
        tier_names[CompetitionTier.PROVINCIALE] = prov_picked
    if len(reg_pool) >= 7:
        tier_names[CompetitionTier.REGIONALE] = reg_pool[:7]
    return tier_names


def create_rival_clubs(
    rng: Optional[random.Random] = None,
    province: Optional[str] = None,
    team_name: Optional[str] = None,
) -> List[RivalClub]:
    """Seven persistent rival clubs per category, each with one male and one female athlete per discipline."""
    r = rng or random.Random()
    clubs: List[RivalClub] = []
    for tier, names in _rival_tier_names(r, province, team_name).items():
        for name in names:
            club = RivalClub(
                name=name,
                tier=tier,
                ambition=round(r.uniform(0.8, 1.25), 2),
                offset=round(r.gauss(0.0, 3.0), 2),
            )
            for event in EVENTS:
                club.athletes[event] = generate_rival_athlete(
                    event, tier, club.offset, rng=r, gender="M"
                )
                club.female_athletes[event] = generate_rival_athlete(
                    event, tier, club.offset, rng=r, gender="F"
                )
            club.history.append(round(club.level(), 2))
            clubs.append(club)
    return clubs


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
