"""SQLite persistence layer for Track & Field Manager (v2 schema)."""

from __future__ import annotations

from contextlib import closing, contextmanager
import json
import sqlite3
from datetime import date
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

from models.entities import (
    Athlete,
    CompetitionSummary,
    CompetitionTier,
    EthicalDilemma,
    EventResult,
    EventStanding,
    GameState,
    PeriodizationPhase,
    Personality,
    SeasonObjective,
    SeasonPhase,
    Specialty,
    StaffMember,
    StaffRole,
    TrainingFocus,
    Transaction,
    WeatherCondition,
)

SCHEMA_VERSION = 2


def get_default_save_path() -> Path:
    """Return a writable default SQLite database path for both dev and PyInstaller builds."""
    save_dir = Path.home() / ".track_field_manager"
    save_dir.mkdir(parents=True, exist_ok=True)
    return save_dir / "savegame.db"


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
            if current_ver != SCHEMA_VERSION:
                conn.executescript(
                    """
                    DROP TABLE IF EXISTS game_state;
                    DROP TABLE IF EXISTS athletes;
                    DROP TABLE IF EXISTS staff;
                    DROP TABLE IF EXISTS transactions;
                    DROP TABLE IF EXISTS competition_history;
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
                    pending_dilemma_json TEXT
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
                    doping_boost_weeks INTEGER NOT NULL DEFAULT 0
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
                    results_json TEXT NOT NULL
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

        with self._connect() as conn:
            conn.execute("DELETE FROM game_state")
            conn.execute("DELETE FROM athletes")
            conn.execute("DELETE FROM staff")
            conn.execute("DELETE FROM transactions")
            conn.execute("DELETE FROM competition_history")

            conn.execute(
                """
                INSERT INTO game_state (
                    id, team_name, game_mode, budget, week, season_number, season_phase,
                    start_date, prestige, reputation, tier, track_condition, member_fees_weekly,
                    event_lineup_json, club_records_json, objectives_json, milestones_json,
                    news_log_json, pending_dilemma_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                ),
            )

            conn.executemany(
                """
                INSERT INTO athletes (
                    id, name, age, specialty, speed, stamina, strength, technique,
                    resilience, form, fatigue, potential, personality, training_focus,
                    periodization, sleep_quality, nutrition, weekly_wage, injured_weeks,
                    is_youth_prospect, personal_best, personal_best_display, doping_boost_weeks
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    total_prize_money, total_prestige_gained, travel_cost, promoted_to, results_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    )
                )

            raw_records = json.loads(row["club_records_json"])
            club_records: Dict[str, Tuple[float, str, str]] = {
                k: (float(v[0]), str(v[1]), str(v[2])) for k, v in raw_records.items()
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
                athletes=athletes,
                staff=staff,
                transactions=transactions,
                competition_history=history,
                event_lineup=json.loads(row["event_lineup_json"]),
                club_records=club_records,
                objectives=objectives,
                milestones=json.loads(row["milestones_json"]),
                news_log=json.loads(row["news_log_json"]),
                pending_dilemma=pending_dilemma,
            )
