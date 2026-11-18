"""SQLite persistence layer for Track & Field Manager (v2 schema)."""

from __future__ import annotations

from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta
import json
import re
import sqlite3
import random
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

from models.generator import generate_body, infer_gender
from models.entities import (
    Athlete,
    Coach,
    CompetitionSummary,
    CompetitionTier,
    EthicalDilemma,
    EventResult,
    EventStanding,
    GameState,
    PeriodizationPhase,
    Personality,
    Relay,
    RivalAthlete,
    RivalClub,
    SeasonEndResult,
    SeasonObjective,
    SeasonOutcome,
    SeasonPhase,
    Specialty,
    StaffMember,
    StaffRole,
    TrainingFocus,
    Transaction,
    WeatherCondition,
)

SCHEMA_VERSION = 9

# Columns added in v3 (youth academy, facilities, race attitude, fans, club league).
# Applied with ALTER TABLE so v2 saves survive the upgrade.
V3_COLUMNS: Dict[str, List[Tuple[str, str]]] = {
    "game_state": [
        ("event_attitude_json", "TEXT NOT NULL DEFAULT '{}'"),
        ("gym_level", "INTEGER NOT NULL DEFAULT 0"),
        ("stand_seats", "INTEGER NOT NULL DEFAULT 500"),
        ("fidelity", "INTEGER NOT NULL DEFAULT 100"),
        ("scouting_points_used", "INTEGER NOT NULL DEFAULT 0"),
        ("bankrupt", "INTEGER NOT NULL DEFAULT 0"),
        ("league_table_json", "TEXT NOT NULL DEFAULT '{}'"),
    ],
    "athletes": [
        ("in_youth_squad", "INTEGER NOT NULL DEFAULT 0"),
        ("fans", "INTEGER NOT NULL DEFAULT 0"),
    ],
    "competition_history": [
        ("is_home", "INTEGER NOT NULL DEFAULT 0"),
        ("spectators", "INTEGER NOT NULL DEFAULT 0"),
        ("ticket_income", "INTEGER NOT NULL DEFAULT 0"),
        ("team_standings_json", "TEXT NOT NULL DEFAULT '[]'"),
        ("player_team", "TEXT NOT NULL DEFAULT ''"),
    ],
}

# Columns added in v4 (coaches with their own skills, relays).
V4_COLUMNS: Dict[str, List[Tuple[str, str]]] = {
    "game_state": [
        ("relays_json", "TEXT NOT NULL DEFAULT '{}'"),
        ("coach_hired_week", "INTEGER NOT NULL DEFAULT 0"),
    ],
    "athletes": [
        ("coach_id", "INTEGER"),
    ],
}
# Columns added in v5 (persistent rival clubs that develop over time).
V5_COLUMNS: Dict[str, List[Tuple[str, str]]] = {
    "game_state": [("rivals_json", "TEXT NOT NULL DEFAULT '[]'")],
}
# Columns added in v6 (end-of-season promotion & relegation history).
V6_COLUMNS: Dict[str, List[Tuple[str, str]]] = {
    "game_state": [("season_history_json", "TEXT NOT NULL DEFAULT '[]'")],
}
# Columns added in v7 (nationality, height and weight of athletes).
V7_COLUMNS: Dict[str, List[Tuple[str, str]]] = {
    "athletes": [
        ("nationality", "TEXT NOT NULL DEFAULT 'Italia'"),
        ("height_cm", "INTEGER NOT NULL DEFAULT 0"),
        ("weight_kg", "INTEGER NOT NULL DEFAULT 0"),
    ],
}
# Columns added in v8 (athlete gender + separate women's lineup and records).
V8_COLUMNS: Dict[str, List[Tuple[str, str]]] = {
    "athletes": [("gender", "TEXT NOT NULL DEFAULT ''")],
    "game_state": [
        ("event_lineup_f_json", "TEXT NOT NULL DEFAULT '{}'"),
        ("club_records_f_json", "TEXT NOT NULL DEFAULT '{}'"),
    ],
}
# Columns added in v9 (separate women's relays).
V9_COLUMNS: Dict[str, List[Tuple[str, str]]] = {
    "game_state": [("relays_f_json", "TEXT NOT NULL DEFAULT '{}'")]
}
MIGRATIONS: Dict[int, Dict[str, List[Tuple[str, str]]]] = {
    2: V3_COLUMNS,
    3: V4_COLUMNS,
    4: V5_COLUMNS,
    5: V6_COLUMNS,
    6: V7_COLUMNS,
    7: V8_COLUMNS,
    8: V9_COLUMNS,
}


def _relays_to_json(relays: Dict[str, Relay]) -> str:
    return json.dumps(
        {
            name: {
                "member_ids": r.member_ids,
                "reserve_id": r.reserve_id,
                "harmony": r.harmony,
                "last_change_week": r.last_change_week,
            }
            for name, r in relays.items()
        }
    )


def _relays_from_json(raw: str) -> Dict[str, Relay]:
    return {
        name: Relay(
            event=name,
            member_ids=list(rj["member_ids"]),
            reserve_id=rj.get("reserve_id"),
            harmony=int(rj.get("harmony", 30)),
            last_change_week=int(rj.get("last_change_week", -100)),
        )
        for name, rj in json.loads(raw).items()
    }


def _backfill_bodies(athletes: List[Athlete]) -> List[Athlete]:
    """Old saves have no gender or height/weight: infer gender and generate stable builds."""
    for a in athletes:
        if a.gender not in ("M", "F"):
            a.gender = infer_gender(a.name)
        if not a.height_cm:
            a.height_cm, a.weight_kg = generate_body(
                a.specialty, random.Random(a.id or 0), a.age, a.gender
            )
    return athletes


def _season_history_to_json(history: List[SeasonEndResult]) -> str:
    return json.dumps(
        [
            {
                "season": h.season,
                "tier": h.tier.value,
                "placement": h.placement,
                "outcome": h.outcome.value,
                "final_table": [[t, p] for t, p in h.final_table],
                "new_tier": h.new_tier.value if h.new_tier else None,
            }
            for h in history
        ]
    )


def _season_history_from_json(raw: str) -> List[SeasonEndResult]:
    return [
        SeasonEndResult(
            season=int(h["season"]),
            tier=CompetitionTier(h["tier"]),
            placement=int(h["placement"]),
            outcome=SeasonOutcome(h["outcome"]),
            final_table=[(str(t), int(p)) for t, p in h["final_table"]],
            new_tier=CompetitionTier(h["new_tier"]) if h.get("new_tier") else None,
        )
        for h in json.loads(raw)
    ]


def _rivals_to_json(clubs: List[RivalClub]) -> str:
    def ser(pool: Dict[str, RivalAthlete]) -> List[dict]:
        return [
            {
                "name": a.name,
                "event": a.event,
                "age": a.age,
                "skill": a.skill,
                "pb": a.pb,
                "pb_display": a.pb_display,
                "gender": a.gender,
            }
            for a in pool.values()
        ]

    return json.dumps(
        [
            {
                "name": c.name,
                "tier": c.tier.value,
                "ambition": c.ambition,
                "offset": c.offset,
                "history": c.history,
                "athletes": ser(c.athletes),
                "female_athletes": ser(c.female_athletes),
            }
            for c in clubs
        ]
    )


def _rivals_from_json(raw: str) -> List[RivalClub]:
    clubs: List[RivalClub] = []
    for cj in json.loads(raw):
        club = RivalClub(
            name=cj["name"],
            tier=CompetitionTier(cj["tier"]),
            ambition=float(cj["ambition"]),
            offset=float(cj.get("offset", 0.0)),
            history=[float(h) for h in cj.get("history", [])],
        )
        for aj in cj.get("athletes", []):
            club.athletes[aj["event"]] = RivalAthlete(
                name=aj["name"],
                event=aj["event"],
                age=int(aj["age"]),
                skill=float(aj["skill"]),
                pb=aj.get("pb"),
                pb_display=aj.get("pb_display"),
                gender=str(aj.get("gender", "M")),
            )
        for aj in cj.get("female_athletes", []):
            club.female_athletes[aj["event"]] = RivalAthlete(
                name=aj["name"],
                event=aj["event"],
                age=int(aj["age"]),
                skill=float(aj["skill"]),
                pb=aj.get("pb"),
                pb_display=aj.get("pb_display"),
                gender=str(aj.get("gender", "F")),
            )
        clubs.append(club)
    return clubs


def get_default_save_path() -> Path:
    """Return a writable default SQLite database path for both dev and PyInstaller builds."""
    save_dir = Path.home() / ".track_field_manager"
    save_dir.mkdir(parents=True, exist_ok=True)
    return save_dir / "savegame.db"


def get_saves_dir() -> Path:
    """Return the directory holding multi-slot career/prototype save files."""
    saves_dir = get_default_save_path().parent / "saves"
    saves_dir.mkdir(parents=True, exist_ok=True)
    return saves_dir


def make_save_slot_path(team_name: str, saves_dir: Optional[Path] = None) -> Path:
    """Generate a unique SQLite save path from `team_name` inside `saves_dir`."""
    target_dir = Path(saves_dir) if saves_dir is not None else get_saves_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "_", team_name.strip().lower()).strip("_") or "societa"
    candidate = target_dir / f"{slug}.db"
    idx = 2
    while candidate.exists():
        candidate = target_dir / f"{slug}_{idx}.db"
        idx += 1
    return candidate


@dataclass
class SaveSlotInfo:
    """Lightweight metadata for a saved game shown in the start screen."""

    path: Path
    team_name: str
    game_mode: str
    tier: str
    season_number: int
    week: int
    season_phase: str
    in_game_date: date
    budget: int
    prestige: int
    bankrupt: bool
    updated_at: datetime

    @property
    def mode_label(self) -> str:
        return "Prototipo Outdoor" if self.game_mode == "vertical_slice" else "Carriera Completa"


def read_save_summary(db_path: Path) -> Optional[SaveSlotInfo]:
    """Read save metadata without mutating schema or loading full rosters."""
    path = Path(db_path)
    if not path.is_file():
        return None
    try:
        uri = f"{path.resolve().as_uri()}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as conn:
            conn.row_factory = sqlite3.Row
            has_table = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='game_state'"
            ).fetchone()
            if not has_table:
                return None
            cols = {r[1] for r in conn.execute("PRAGMA table_info(game_state)").fetchall()}
            bankrupt_expr = "bankrupt" if "bankrupt" in cols else "0 AS bankrupt"
            row = conn.execute(
                f"""
                SELECT team_name, game_mode, budget, week, season_number,
                       season_phase, start_date, prestige, tier, {bankrupt_expr}
                FROM game_state WHERE id = 1
                """
            ).fetchone()
            if row is None:
                return None
            week = int(row["week"])
            start_d = date.fromisoformat(row["start_date"])
            in_game = start_d + timedelta(weeks=max(0, week - 1))
            mtime = datetime.fromtimestamp(path.stat().st_mtime)
            return SaveSlotInfo(
                path=path,
                team_name=str(row["team_name"]),
                game_mode=str(row["game_mode"]),
                tier=str(row["tier"]),
                season_number=int(row["season_number"]),
                week=week,
                season_phase=str(row["season_phase"]),
                in_game_date=in_game,
                budget=int(row["budget"]),
                prestige=int(row["prestige"]),
                bankrupt=bool(row["bankrupt"]),
                updated_at=mtime,
            )
    except (sqlite3.Error, ValueError, OSError):
        return None


def list_save_slots(
    saves_dir: Optional[Path] = None, legacy_path: Optional[Path] = None
) -> List[SaveSlotInfo]:
    """Return available save slots sorted from most recently updated to oldest."""
    target_dir = Path(saves_dir) if saves_dir is not None else get_saves_dir()
    candidates: List[Path] = []
    if target_dir.is_dir():
        candidates.extend(sorted(target_dir.glob("*.db")))
    legacy = Path(legacy_path) if legacy_path is not None else get_default_save_path()
    if legacy.is_file() and legacy.resolve() not in {c.resolve() for c in candidates}:
        candidates.append(legacy)

    slots: List[SaveSlotInfo] = []
    for path in candidates:
        info = read_save_summary(path)
        if info is not None:
            slots.append(info)
    slots.sort(key=lambda s: s.updated_at, reverse=True)
    return slots


def delete_save_slot(db_path: Path) -> bool:
    """Delete a save file from disk if it exists."""
    path = Path(db_path)
    if not path.is_file():
        return False
    path.unlink()
    return True


class DatabaseManager:
    """Handles SQLite schema creation, saving, and loading of GameState."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = Path(db_path) if db_path is not None else get_default_save_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        with closing(sqlite3.connect(str(self.db_path))) as conn:
            conn.row_factory = sqlite3.Row
            with conn:
                yield conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            current_ver = conn.execute("PRAGMA user_version").fetchone()[0]
            if current_ver in MIGRATIONS:
                # Upgrade path: keep the save, add the newer columns step by step
                while current_ver in MIGRATIONS:
                    for table, columns in MIGRATIONS[current_ver].items():
                        for col_name, col_def in columns:
                            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}")
                    current_ver += 1
                conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            elif current_ver != SCHEMA_VERSION:
                conn.executescript(
                    """
                    DROP TABLE IF EXISTS game_state;
                    DROP TABLE IF EXISTS athletes;
                    DROP TABLE IF EXISTS staff;
                    DROP TABLE IF EXISTS transactions;
                    DROP TABLE IF EXISTS competition_history;
                    DROP TABLE IF EXISTS coaches;
                    """
                )
                conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS game_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    team_name TEXT NOT NULL,
                    game_mode TEXT NOT NULL,
                    budget INTEGER NOT NULL,
                    week INTEGER NOT NULL,
                    season_number INTEGER NOT NULL,
                    season_phase TEXT NOT NULL,
                    start_date TEXT NOT NULL,
                    prestige INTEGER NOT NULL,
                    reputation INTEGER NOT NULL,
                    tier TEXT NOT NULL,
                    track_condition INTEGER NOT NULL,
                    member_fees_weekly INTEGER NOT NULL,
                    event_lineup_json TEXT NOT NULL,
                    club_records_json TEXT NOT NULL,
                    objectives_json TEXT NOT NULL,
                    milestones_json TEXT NOT NULL,
                    news_log_json TEXT NOT NULL,
                    pending_dilemma_json TEXT,
                    event_attitude_json TEXT NOT NULL DEFAULT '{}',
                    gym_level INTEGER NOT NULL DEFAULT 0,
                    stand_seats INTEGER NOT NULL DEFAULT 500,
                    fidelity INTEGER NOT NULL DEFAULT 100,
                    scouting_points_used INTEGER NOT NULL DEFAULT 0,
                    bankrupt INTEGER NOT NULL DEFAULT 0,
                    league_table_json TEXT NOT NULL DEFAULT '{}',
                    relays_json TEXT NOT NULL DEFAULT '{}',
                    coach_hired_week INTEGER NOT NULL DEFAULT 0,
                    rivals_json TEXT NOT NULL DEFAULT '[]',
                    season_history_json TEXT NOT NULL DEFAULT '[]',
                    event_lineup_f_json TEXT NOT NULL DEFAULT '{}',
                    club_records_f_json TEXT NOT NULL DEFAULT '{}',
                    relays_f_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS athletes (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    age INTEGER NOT NULL,
                    specialty TEXT NOT NULL,
                    speed INTEGER NOT NULL,
                    stamina INTEGER NOT NULL,
                    strength INTEGER NOT NULL,
                    technique INTEGER NOT NULL,
                    resilience INTEGER NOT NULL,
                    form INTEGER NOT NULL,
                    fatigue INTEGER NOT NULL,
                    potential INTEGER NOT NULL,
                    personality TEXT NOT NULL,
                    training_focus TEXT NOT NULL,
                    periodization TEXT NOT NULL,
                    sleep_quality INTEGER NOT NULL,
                    nutrition INTEGER NOT NULL,
                    weekly_wage INTEGER NOT NULL,
                    injured_weeks INTEGER NOT NULL DEFAULT 0,
                    is_youth_prospect INTEGER NOT NULL DEFAULT 0,
                    personal_best REAL,
                    personal_best_display TEXT,
                    doping_boost_weeks INTEGER NOT NULL DEFAULT 0,
                    in_youth_squad INTEGER NOT NULL DEFAULT 0,
                    fans INTEGER NOT NULL DEFAULT 0,
                    coach_id INTEGER,
                    nationality TEXT NOT NULL DEFAULT 'Italia',
                    height_cm INTEGER NOT NULL DEFAULT 0,
                    weight_kg INTEGER NOT NULL DEFAULT 0,
                    gender TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS coaches (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    specialty TEXT,
                    skills_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS staff (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    role TEXT NOT NULL,
                    skill INTEGER NOT NULL,
                    weekly_cost INTEGER NOT NULL,
                    hired INTEGER NOT NULL,
                    description TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    week INTEGER NOT NULL,
                    description TEXT NOT NULL,
                    category TEXT NOT NULL,
                    amount INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS competition_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    week INTEGER NOT NULL,
                    tier TEXT NOT NULL,
                    season_phase TEXT NOT NULL,
                    meet_name TEXT NOT NULL,
                    weather TEXT NOT NULL,
                    track_surface TEXT NOT NULL,
                    total_prize_money INTEGER NOT NULL,
                    total_prestige_gained INTEGER NOT NULL,
                    travel_cost INTEGER NOT NULL,
                    promoted_to TEXT,
                    results_json TEXT NOT NULL,
                    is_home INTEGER NOT NULL DEFAULT 0,
                    spectators INTEGER NOT NULL DEFAULT 0,
                    ticket_income INTEGER NOT NULL DEFAULT 0,
                    team_standings_json TEXT NOT NULL DEFAULT '[]',
                    player_team TEXT NOT NULL DEFAULT ''
                );
                """
            )

    def has_saved_game(self) -> bool:
        with self._connect() as conn:
            row = conn.execute("SELECT 1 FROM game_state WHERE id = 1").fetchone()
            return row is not None

    def save_game(self, state: GameState) -> None:
        """Persist the complete GameState atomically into SQLite."""
        next_id = max((a.id or 0 for a in state.athletes), default=0) + 1
        for athlete in state.athletes:
            if athlete.id is None:
                athlete.id = next_id
                next_id += 1

        dilemma_json: Optional[str] = None
        if state.pending_dilemma is not None:
            d = state.pending_dilemma
            dilemma_json = json.dumps(
                {
                    "id": d.id,
                    "title": d.title,
                    "description": d.description,
                    "accept_label": d.accept_label,
                    "reject_label": d.reject_label,
                    "athlete_id": d.athlete_id,
                }
            )

        objectives_json = json.dumps(
            [
                {"key": o.key, "title": o.title, "completed": o.completed}
                for o in state.objectives
            ]
        )
        records_json = json.dumps(
            {k: [v[0], v[1], v[2]] for k, v in state.club_records.items()}
        )
        records_f_json = json.dumps(
            {k: [v[0], v[1], v[2]] for k, v in state.club_records_f.items()}
        )

        with self._connect() as conn:
            conn.execute("DELETE FROM game_state")
            conn.execute("DELETE FROM athletes")
            conn.execute("DELETE FROM staff")
            conn.execute("DELETE FROM transactions")
            conn.execute("DELETE FROM competition_history")
            conn.execute("DELETE FROM coaches")

            conn.execute(
                """
                INSERT INTO game_state (
                    id, team_name, game_mode, budget, week, season_number, season_phase,
                    start_date, prestige, reputation, tier, track_condition, member_fees_weekly,
                    event_lineup_json, club_records_json, objectives_json, milestones_json,
                    news_log_json, pending_dilemma_json, event_attitude_json, gym_level,
                    stand_seats, fidelity, scouting_points_used, bankrupt, league_table_json,
                    relays_json, coach_hired_week, rivals_json, season_history_json,
                    event_lineup_f_json, club_records_f_json, relays_f_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    1,
                    state.team_name,
                    state.game_mode,
                    state.budget,
                    state.week,
                    state.season_number,
                    state.season_phase.value,
                    state.start_date.isoformat(),
                    state.prestige,
                    state.reputation,
                    state.tier.value,
                    state.track_condition,
                    state.member_fees_weekly,
                    json.dumps(state.event_lineup),
                    records_json,
                    objectives_json,
                    json.dumps(state.milestones),
                    json.dumps(state.news_log),
                    dilemma_json,
                    json.dumps(state.event_attitude),
                    state.gym_level,
                    state.stand_seats,
                    state.fidelity,
                    state.scouting_points_used,
                    1 if state.bankrupt else 0,
                    json.dumps(state.league_table),
                    _relays_to_json(state.relays),
                    state.coach_hired_week,
                    _rivals_to_json(state.rival_clubs),
                    _season_history_to_json(state.season_history),
                    json.dumps(state.event_lineup_f),
                    records_f_json,
                    _relays_to_json(state.relays_f),
                ),
            )

            conn.executemany(
                """
                INSERT INTO athletes (
                    id, name, age, specialty, speed, stamina, strength, technique,
                    resilience, form, fatigue, potential, personality, training_focus,
                    periodization, sleep_quality, nutrition, weekly_wage, injured_weeks,
                    is_youth_prospect, personal_best, personal_best_display, doping_boost_weeks,
                    in_youth_squad, fans, coach_id, nationality, height_cm, weight_kg, gender
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        a.id,
                        a.name,
                        a.age,
                        a.specialty.value,
                        a.speed,
                        a.stamina,
                        a.strength,
                        a.technique,
                        a.resilience,
                        a.form,
                        a.fatigue,
                        a.potential,
                        a.personality.value,
                        a.training_focus.value,
                        a.periodization.value,
                        a.sleep_quality,
                        a.nutrition,
                        a.weekly_wage,
                        a.injured_weeks,
                        1 if a.is_youth_prospect else 0,
                        a.personal_best,
                        a.personal_best_display,
                        a.doping_boost_weeks,
                        1 if a.in_youth_squad else 0,
                        a.fans,
                        a.coach_id,
                        a.nationality,
                        a.height_cm,
                        a.weight_kg,
                        a.gender,
                    )
                    for a in state.athletes
                ],
            )

            conn.executemany(
                """
                INSERT INTO staff (id, name, role, skill, weekly_cost, hired, description)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        s.id,
                        s.name,
                        s.role.value,
                        s.skill,
                        s.weekly_cost,
                        1 if s.hired else 0,
                        s.description,
                    )
                    for s in state.staff
                ],
            )

            conn.executemany(
                "INSERT INTO coaches (id, name, specialty, skills_json) VALUES (?, ?, ?, ?)",
                [
                    (
                        c.id,
                        c.name,
                        c.specialty.value if c.specialty is not None else None,
                        json.dumps(c.skills),
                    )
                    for c in state.coaches
                ],
            )

            conn.executemany(
                """
                INSERT INTO transactions (week, description, category, amount)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (t.week, t.description, t.category, t.amount)
                    for t in state.transactions
                ],
            )

            conn.executemany(
                """
                INSERT INTO competition_history (
                    week, tier, season_phase, meet_name, weather, track_surface,
                    total_prize_money, total_prestige_gained, travel_cost, promoted_to, results_json,
                    is_home, spectators, ticket_income, team_standings_json, player_team
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        c.week,
                        c.tier.value,
                        c.season_phase.value,
                        c.meet_name,
                        c.weather.value,
                        c.track_surface,
                        c.total_prize_money,
                        c.total_prestige_gained,
                        c.travel_cost,
                        c.promoted_to.value if c.promoted_to else None,
                        json.dumps(
                            [
                                {
                                    "event_name": er.event_name,
                                    "player_athlete_name": er.player_athlete_name,
                                    "placement": er.placement,
                                    "total_competitors": er.total_competitors,
                                    "player_mark": er.player_mark,
                                    "prize_money": er.prize_money,
                                    "prestige_gained": er.prestige_gained,
                                    "wind_ms": er.wind_ms,
                                    "wind_illegal": er.wind_illegal,
                                    "is_pb": er.is_pb,
                                    "is_club_record": er.is_club_record,
                                    "attitude": er.attitude,
                                    "withdrew_injured": er.withdrew_injured,
                                    "disqualified": er.disqualified,
                                    "gender": er.gender,
                                    "standings": [
                                        {
                                            "athlete_name": s.athlete_name,
                                            "team_name": s.team_name,
                                            "is_player": s.is_player,
                                            "mark_value": s.mark_value,
                                            "mark_display": s.mark_display,
                                            "placement": s.placement,
                                            "wind_ms": s.wind_ms,
                                            "wind_illegal": s.wind_illegal,
                                        }
                                        for s in er.standings
                                    ],
                                }
                                for er in c.event_results
                            ]
                        ),
                        1 if c.is_home else 0,
                        c.spectators,
                        c.ticket_income,
                        json.dumps([[t, p] for t, p in c.team_standings]),
                        c.player_team,
                    )
                    for c in state.competition_history
                ],
            )

    def load_game(self) -> Optional[GameState]:
        """Load GameState from SQLite, returning None if no save exists."""
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM game_state WHERE id = 1").fetchone()
            if row is None:
                return None

            athletes: List[Athlete] = [
                Athlete(
                    id=r["id"],
                    name=r["name"],
                    age=r["age"],
                    specialty=Specialty(r["specialty"]),
                    speed=r["speed"],
                    stamina=r["stamina"],
                    strength=r["strength"],
                    technique=r["technique"],
                    resilience=r["resilience"],
                    form=r["form"],
                    fatigue=r["fatigue"],
                    potential=r["potential"],
                    personality=Personality(r["personality"]),
                    training_focus=TrainingFocus(r["training_focus"]),
                    periodization=PeriodizationPhase(r["periodization"]),
                    sleep_quality=r["sleep_quality"],
                    nutrition=r["nutrition"],
                    weekly_wage=r["weekly_wage"],
                    injured_weeks=r["injured_weeks"],
                    is_youth_prospect=bool(r["is_youth_prospect"]),
                    personal_best=r["personal_best"],
                    personal_best_display=r["personal_best_display"],
                    doping_boost_weeks=r["doping_boost_weeks"],
                    in_youth_squad=bool(r["in_youth_squad"]),
                    fans=r["fans"],
                    coach_id=r["coach_id"],
                    nationality=r["nationality"],
                    height_cm=r["height_cm"],
                    weight_kg=r["weight_kg"],
                    gender=r["gender"],
                )
                for r in conn.execute("SELECT * FROM athletes ORDER BY id ASC").fetchall()
            ]

            staff: List[StaffMember] = [
                StaffMember(
                    id=r["id"],
                    name=r["name"],
                    role=StaffRole(r["role"]),
                    skill=r["skill"],
                    weekly_cost=r["weekly_cost"],
                    hired=bool(r["hired"]),
                    description=r["description"],
                )
                for r in conn.execute("SELECT * FROM staff ORDER BY id ASC").fetchall()
            ]

            coaches: List[Coach] = [
                Coach(
                    id=r["id"],
                    name=r["name"],
                    specialty=Specialty(r["specialty"]) if r["specialty"] else None,
                    skills={str(k): int(v) for k, v in json.loads(r["skills_json"]).items()},
                )
                for r in conn.execute("SELECT * FROM coaches ORDER BY id ASC").fetchall()
            ]
            relays = _relays_from_json(row["relays_json"])
            relays_f = _relays_from_json(row["relays_f_json"])

            transactions: List[Transaction] = [
                Transaction(
                    id=r["id"],
                    week=r["week"],
                    description=r["description"],
                    category=r["category"],
                    amount=r["amount"],
                )
                for r in conn.execute("SELECT * FROM transactions ORDER BY id ASC").fetchall()
            ]

            history: List[CompetitionSummary] = []
            for r in conn.execute("SELECT * FROM competition_history ORDER BY id ASC").fetchall():
                raw_results = json.loads(r["results_json"])
                event_results: List[EventResult] = []
                for er in raw_results:
                    standings = [
                        EventStanding(
                            athlete_name=s["athlete_name"],
                            team_name=s["team_name"],
                            is_player=s["is_player"],
                            mark_value=s["mark_value"],
                            mark_display=s["mark_display"],
                            placement=s["placement"],
                            wind_ms=s.get("wind_ms"),
                            wind_illegal=s.get("wind_illegal", False),
                        )
                        for s in er.get("standings", [])
                    ]
                    event_results.append(
                        EventResult(
                            event_name=er["event_name"],
                            player_athlete_name=er["player_athlete_name"],
                            placement=er["placement"],
                            total_competitors=er["total_competitors"],
                            player_mark=er["player_mark"],
                            prize_money=er["prize_money"],
                            prestige_gained=er["prestige_gained"],
                            wind_ms=er.get("wind_ms"),
                            wind_illegal=er.get("wind_illegal", False),
                            is_pb=er.get("is_pb", False),
                            is_club_record=er.get("is_club_record", False),
                            standings=standings,
                            attitude=er.get("attitude", "Normale"),
                            withdrew_injured=er.get("withdrew_injured", False),
                            disqualified=er.get("disqualified", False),
                            gender=er.get("gender", ""),
                        )
                    )
                history.append(
                    CompetitionSummary(
                        week=r["week"],
                        tier=CompetitionTier(r["tier"]),
                        season_phase=SeasonPhase(r["season_phase"]),
                        meet_name=r["meet_name"],
                        weather=WeatherCondition(r["weather"]),
                        track_surface=r["track_surface"],
                        event_results=event_results,
                        total_prize_money=r["total_prize_money"],
                        total_prestige_gained=r["total_prestige_gained"],
                        travel_cost=r["travel_cost"],
                        promoted_to=(
                            CompetitionTier(r["promoted_to"])
                            if r["promoted_to"]
                            else None
                        ),
                        is_home=bool(r["is_home"]),
                        spectators=r["spectators"],
                        ticket_income=r["ticket_income"],
                        team_standings=[
                            (str(t), int(p)) for t, p in json.loads(r["team_standings_json"])
                        ],
                        player_team=r["player_team"],
                    )
                )

            raw_records = json.loads(row["club_records_json"])
            club_records: Dict[str, Tuple[float, str, str]] = {
                k: (float(v[0]), str(v[1]), str(v[2])) for k, v in raw_records.items()
            }
            raw_records_f = json.loads(row["club_records_f_json"])
            club_records_f: Dict[str, Tuple[float, str, str]] = {
                k: (float(v[0]), str(v[1]), str(v[2])) for k, v in raw_records_f.items()
            }
            objectives = [
                SeasonObjective(
                    key=o["key"], title=o["title"], completed=bool(o["completed"])
                )
                for o in json.loads(row["objectives_json"])
            ]

            pending_dilemma: Optional[EthicalDilemma] = None
            if row["pending_dilemma_json"]:
                dj = json.loads(row["pending_dilemma_json"])
                pending_dilemma = EthicalDilemma(
                    id=dj["id"],
                    title=dj["title"],
                    description=dj["description"],
                    accept_label=dj["accept_label"],
                    reject_label=dj["reject_label"],
                    athlete_id=dj.get("athlete_id"),
                )

            return GameState(
                team_name=row["team_name"],
                game_mode=row["game_mode"],
                budget=row["budget"],
                week=row["week"],
                season_number=row["season_number"],
                season_phase=SeasonPhase(row["season_phase"]),
                start_date=date.fromisoformat(row["start_date"]),
                prestige=row["prestige"],
                reputation=row["reputation"],
                tier=CompetitionTier(row["tier"]),
                track_condition=row["track_condition"],
                member_fees_weekly=row["member_fees_weekly"],
                athletes=_backfill_bodies(athletes),
                staff=staff,
                transactions=transactions,
                competition_history=history,
                event_lineup=json.loads(row["event_lineup_json"]),
                club_records=club_records,
                objectives=objectives,
                milestones=json.loads(row["milestones_json"]),
                news_log=json.loads(row["news_log_json"]),
                pending_dilemma=pending_dilemma,
                event_attitude=json.loads(row["event_attitude_json"]),
                gym_level=row["gym_level"],
                stand_seats=row["stand_seats"],
                fidelity=row["fidelity"],
                scouting_points_used=row["scouting_points_used"],
                bankrupt=bool(row["bankrupt"]),
                league_table={
                    str(k): int(v) for k, v in json.loads(row["league_table_json"]).items()
                },
                coaches=coaches,
                relays=relays,
                coach_hired_week=row["coach_hired_week"],
                rival_clubs=_rivals_from_json(row["rivals_json"]),
                season_history=_season_history_from_json(row["season_history_json"]),
                event_lineup_f=json.loads(row["event_lineup_f_json"]),
                club_records_f=club_records_f,
                relays_f=relays_f,
            )
