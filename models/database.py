"""SQLite persistence layer for Track & Field Manager (v2 schema)."""

from __future__ import annotations

from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from functools import lru_cache
import json
import re
import sqlite3
import random
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

from models.generator import generate_body, infer_gender
from models.entities import (
    AGENT_RELATION_START,
    Agent,
    AgentPersonality,
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
    RetiredAthlete,
    RivalAthlete,
    RivalClub,
    SyntheticAthlete,
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

SCHEMA_VERSION = 19

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
# Columns added in v10 (athlete contracts: last season of the contract, 0 = none yet).
V10_COLUMNS: Dict[str, List[Tuple[str, str]]] = {
    "athletes": [("contract_end_season", "INTEGER NOT NULL DEFAULT 0")],
}
# Columns added in v11 (athlete contract: 1 = do not renew at expiry, the athlete leaves the club).
V11_COLUMNS: Dict[str, List[Tuple[str, str]]] = {
    "athletes": [("contract_no_renew", "INTEGER NOT NULL DEFAULT 0")],
}
# Columns added in v12 (A.2: quanti 1°, 2°, ... posti ha ottenuto ogni club in stagione, per lo spareggio).
V12_COLUMNS: Dict[str, List[Tuple[str, str]]] = {
    "game_state": [("league_places_json", "TEXT NOT NULL DEFAULT '{}'")],
}
# Columns added in v13 (A.3: stato dell'RNG della partita, `[]` = salvataggio vecchio, si semina dal seed di ripiego).
V13_COLUMNS: Dict[str, List[Tuple[str, str]]] = {
    "game_state": [("rng_state_json", "TEXT NOT NULL DEFAULT '[]'")],
}
# Columns added in v14 (B.1: piano gara per evento, `{}` = ritmo Medio e nessuno scatto).
V14_COLUMNS: Dict[str, List[Tuple[str, str]]] = {
    "game_state": [("race_strategy_json", "TEXT NOT NULL DEFAULT '{}'")],
}
# Columns added in v15 (C.1: punti ranking per evento di ogni atleta e campo mondiale di atleti sintetici;
# `{}` / `[]` = salvataggio vecchio, il campo sintetico si genera al caricamento con l'RNG della partita).
V15_COLUMNS: Dict[str, List[Tuple[str, str]]] = {
    "athletes": [("ranking_json", "TEXT NOT NULL DEFAULT '{}'")],
    "game_state": [("ranking_pool_json", "TEXT NOT NULL DEFAULT '[]'")],
}
# Columns added in v16 (C.2: Board, `{}` = nessuna stagione fallita e non esonerato; gli obiettivi con soglia e avanzamento
# stanno in `objectives_json`, il verdetto di ogni stagione in `season_history_json`).
V16_COLUMNS: Dict[str, List[Tuple[str, str]]] = {
    "game_state": [("board_json", "TEXT NOT NULL DEFAULT '{}'")],
}
# Columns added in v17 (C.3: infortuni dell'atleta nella stagione in corso e ex atleti della società; `[]` = nessun ritiro).
V17_COLUMNS: Dict[str, List[Tuple[str, str]]] = {
    "athletes": [("season_injuries", "INTEGER NOT NULL DEFAULT 0")],
    "game_state": [("retired_json", "TEXT NOT NULL DEFAULT '[]'")],
}
# Columns added in v18 (D.1: agente dell'atleta, `NULL` = ancora da assegnare, e agenti della società; `[]` = nessuno).
V18_COLUMNS: Dict[str, List[Tuple[str, str]]] = {
    "athletes": [("agent_id", "INTEGER")],
    "game_state": [("agents_json", "TEXT NOT NULL DEFAULT '[]'")],
}
# Columns added in v19 (D.2: bonus per record sociale pattuito in trattativa, € per record; 0 = nessuno).
V19_COLUMNS: Dict[str, List[Tuple[str, str]]] = {
    "athletes": [("record_bonus", "INTEGER NOT NULL DEFAULT 0")],
}
MIGRATIONS: Dict[int, Dict[str, List[Tuple[str, str]]]] = {
    2: V3_COLUMNS,
    3: V4_COLUMNS,
    4: V5_COLUMNS,
    5: V6_COLUMNS,
    6: V7_COLUMNS,
    7: V8_COLUMNS,
    8: V9_COLUMNS,
    9: V10_COLUMNS,
    10: V11_COLUMNS,
    11: V12_COLUMNS,
    12: V13_COLUMNS,
    13: V14_COLUMNS,
    14: V15_COLUMNS,
    15: V16_COLUMNS,
    16: V17_COLUMNS,
    17: V18_COLUMNS,
    18: V19_COLUMNS,
}

# Backup scritti prima di ogni migrazione: sottocartella `backups/` accanto allo slot, estensione
# `.db.bak`, così `glob("*.db")` degli slot non li vede mai.
BACKUPS_DIRNAME = "backups"
MAX_BACKUPS_PER_SLOT = 3
_BACKUP_STAMP_FORMAT = "%Y%m%d-%H%M%S-%f"  # microsecondi: due backup non collidono


class UnsupportedSaveVersion(Exception):
    """Il file ha una `user_version` che questo gioco non sa aprire né migrare.

    Sollevata PRIMA di qualsiasi scrittura: il file resta intatto.
    """

    def __init__(
        self, versione_trovata: int, versione_attesa: int, path: Optional[Path] = None
    ) -> None:
        self.versione_trovata = versione_trovata
        self.versione_attesa = versione_attesa
        self.path = path
        super().__init__(self.message)

    @property
    def is_newer(self) -> bool:
        return self.versione_trovata > self.versione_attesa

    @property
    def message(self) -> str:
        if self.is_newer:
            return (
                f"Salvataggio di una versione più recente (v{self.versione_trovata}, "
                f"questo gioco arriva alla v{self.versione_attesa}): aggiorna il gioco."
            )
        return f"Salvataggio non riconosciuto o non migrabile (versione v{self.versione_trovata})."


class SaveMigrationError(RuntimeError):
    """Backup o migrazione non riusciti: il salvataggio è rimasto com'era.

    `backup_path` è il backup verificato creato prima del tentativo (None se non si è arrivati lì).
    """

    def __init__(self, message: str, backup_path: Optional[Path] = None) -> None:
        super().__init__(message)
        self.backup_path = backup_path


def _migration_reaches_current(version: int) -> bool:
    """True se `MIGRATIONS` porta senza buchi da `version` a `SCHEMA_VERSION`."""
    if version not in MIGRATIONS:
        return False
    v = version
    while v in MIGRATIONS:
        v += 1
    return v == SCHEMA_VERSION


def _is_supported_version(version: int) -> bool:
    return version == SCHEMA_VERSION or _migration_reaches_current(version)


def _ro_uri(path: Path) -> str:
    return f"{Path(path).resolve().as_uri()}?mode=ro"


def _inspect(conn: sqlite3.Connection) -> Tuple[int, int]:
    """(`user_version`, numero di tabelle utente): sola lettura, nessuna scrittura."""
    version = int(conn.execute("PRAGMA user_version").fetchone()[0])
    tables = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master "
        "WHERE type = 'table' AND name NOT LIKE 'sqlite\\_%' ESCAPE '\\'"
    ).fetchone()[0]
    return version, int(tables)


@lru_cache(maxsize=1)
def _schema_statements() -> Tuple[str, ...]:
    """Gli statement di `_CREATE_TABLES_SQL`, uno per uno (niente `executescript`: farebbe COMMIT)."""
    return tuple(part.strip() for part in _CREATE_TABLES_SQL.split(";") if part.strip())


def _schema_table_names() -> set:
    return set(re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", _CREATE_TABLES_SQL))


def _backup_dir(db_path: Path) -> Path:
    return Path(db_path).parent / BACKUPS_DIRNAME


def _backup_name_pattern(db_path: Path) -> "re.Pattern[str]":
    stem = re.escape(Path(db_path).stem)
    return re.compile(rf"^{stem}\.v(\d+)\.(\d{{8}}-\d{{6}}-\d{{6}})\.db\.bak$")


def list_backups(db_path: Path) -> List[Path]:
    """I backup di QUESTO slot (pattern esatto), dal più vecchio al più recente."""
    directory = _backup_dir(db_path)
    if not directory.is_dir():
        return []
    pattern = _backup_name_pattern(db_path)
    found = []
    for entry in directory.iterdir():
        m = pattern.match(entry.name)
        if m and entry.is_file():
            found.append((m.group(2), entry.name, entry))
    found.sort(key=lambda t: (t[0], t[1]))
    return [t[2] for t in found]


def _verify_backup(path: Path, version: int) -> None:
    """Il backup deve aprirsi, passare `integrity_check` ed essere alla versione di partenza."""
    with closing(sqlite3.connect(_ro_uri(path), uri=True)) as conn:
        result = conn.execute("PRAGMA integrity_check").fetchall()
        if result != [("ok",)]:
            raise SaveMigrationError(f"Il backup non supera integrity_check: {result[:3]}")
        found = conn.execute("PRAGMA user_version").fetchone()[0]
        if found != version:
            raise SaveMigrationError(
                f"Il backup è alla versione v{found}, attesa v{version}"
            )


def _create_backup(source: sqlite3.Connection, db_path: Path, version: int) -> Path:
    """Copia coerente via `Connection.backup()` (mai `shutil.copy` su un DB aperto), sempre nuova.

    Si scrive in `.tmp`, si verifica, poi si rinomina: un backup parziale non ha mai il nome finale.
    """
    directory = _backup_dir(db_path)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime(_BACKUP_STAMP_FORMAT)
    final = directory / f"{Path(db_path).stem}.v{version}.{stamp}.db.bak"
    tmp = final.with_name(final.name + ".tmp")
    if final.exists():
        raise SaveMigrationError(f"Il backup {final.name} esiste già: non lo sovrascrivo.")
    try:
        with closing(sqlite3.connect(str(tmp))) as dest:
            source.backup(dest)
        _verify_backup(tmp, version)
        tmp.rename(final)
    except BaseException as exc:
        tmp.unlink(missing_ok=True)  # solo il nostro temporaneo, mai un backup precedente
        if isinstance(exc, SaveMigrationError) or not isinstance(exc, Exception):
            raise
        raise SaveMigrationError(f"Backup non riuscito: {exc}") from exc
    return final


def _prune_backups(db_path: Path) -> None:
    """Tiene i `MAX_BACKUPS_PER_SLOT` più recenti di questo slot. Solo dopo una migrazione riuscita."""
    for old in list_backups(db_path)[:-MAX_BACKUPS_PER_SLOT]:
        try:
            old.unlink()
        except OSError:
            pass  # la pulizia è facoltativa: meglio un backup in più che un errore


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
                "board_results": [[t, bool(ok)] for t, ok in h.board_results],
                "board_failed": h.board_failed,
                "board_streak": h.board_streak,
                "fired": h.fired,
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
            board_results=[(str(t), bool(ok)) for t, ok in h.get("board_results", [])],
            board_failed=h.get("board_failed"),
            board_streak=int(h.get("board_streak", 0)),
            fired=bool(h.get("fired", False)),
        )
        for h in json.loads(raw)
    ]


def _retired_to_json(retired: List[RetiredAthlete]) -> str:
    return json.dumps(
        [
            {
                "name": r.name,
                "gender": r.gender,
                "specialty": r.specialty.value,
                "age": r.age,
                "season": r.season,
                "reason": r.reason,
                "nationality": r.nationality,
                "overall": r.overall,
                "pb": r.personal_best_display,
                "coach_skills": r.coach_skills,
                "coach_offer": r.coach_offer,
                "became_coach": r.became_coach,
            }
            for r in retired
        ]
    )


def _retired_from_json(raw: str) -> List[RetiredAthlete]:
    return [
        RetiredAthlete(
            name=str(r["name"]),
            gender=str(r.get("gender", "M")),
            specialty=Specialty(r["specialty"]),
            age=int(r["age"]),
            season=int(r["season"]),
            reason=str(r.get("reason", "")),
            nationality=str(r.get("nationality", "Italia")),
            overall=int(r.get("overall", 0)),
            personal_best_display=r.get("pb"),
            coach_skills={str(k): int(v) for k, v in r.get("coach_skills", {}).items()},
            coach_offer=bool(r.get("coach_offer", False)),
            became_coach=bool(r.get("became_coach", False)),
        )
        for r in json.loads(raw)
    ]


def _agents_to_json(agents: List[Agent]) -> str:
    return json.dumps([{"id": a.id, "name": a.name, "personality": a.personality.value, "relation": a.relation} for a in agents])


def _agents_from_json(raw: str) -> List[Agent]:
    return [
        Agent(
            id=int(a["id"]),
            name=str(a["name"]),
            personality=AgentPersonality(a["personality"]),
            relation=int(a.get("relation", AGENT_RELATION_START)),
        )
        for a in json.loads(raw)
    ]


def _synthetic_to_json(pool: List[SyntheticAthlete]) -> str:
    return json.dumps([[s.name, s.nationality, s.event, s.gender, s.skill, s.points] for s in pool])


def _synthetic_from_json(raw: str) -> List[SyntheticAthlete]:
    return [
        SyntheticAthlete(
            name=str(n), nationality=str(nat), event=str(ev), gender=str(g), skill=float(sk), points=float(pt)
        )
        for n, nat, ev, g, sk, pt in json.loads(raw)
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
                "rank": a.ranking_points,
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
                ranking_points={str(k): float(v) for k, v in aj.get("rank", {}).items()},
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
                ranking_points={str(k): float(v) for k, v in aj.get("rank", {}).items()},
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
    schema_version: int = SCHEMA_VERSION
    # "ok" | "newer" (versione più recente) | "unsupported" (non migrabile) | "corrupt" (non SQLite)
    status: str = "ok"
    size_bytes: int = 0

    @property
    def is_supported(self) -> bool:
        return self.status == "ok"

    @property
    def mode_label(self) -> str:
        if not self.is_supported:
            return "—"
        return "Prototipo Outdoor" if self.game_mode == "vertical_slice" else "Carriera Completa"


def _unsupported_slot(
    path: Path, status: str, version: int, size: int, mtime: datetime
) -> SaveSlotInfo:
    """Slot non apribile: solo i metadati affidabili (file, mtime, dimensione, `user_version`)."""
    labels = {
        "newer": f"Salvataggio di versione più recente (v{version})",
        "unsupported": f"Salvataggio non compatibile (v{version})",
        "corrupt": "Salvataggio danneggiato",
    }
    return SaveSlotInfo(
        path=path,
        team_name=labels[status],
        game_mode="",
        tier="—",
        season_number=0,
        week=0,
        season_phase="",
        in_game_date=mtime.date(),
        budget=0,
        prestige=0,
        bankrupt=False,
        updated_at=mtime,
        schema_version=version,
        status=status,
        size_bytes=size,
    )


def read_save_summary(db_path: Path) -> Optional[SaveSlotInfo]:
    """Read save metadata without mutating schema or loading full rosters.

    Uno slot che il gioco non sa aprire (versione più recente, non migrabile, non SQLite) viene
    elencato lo stesso, marcato in `status`, con i soli metadati affidabili: così l'utente vede la
    partita e capisce perché non si apre. Un file di 0 byte (DB nuovo) non è uno slot.
    """
    path = Path(db_path)
    if not path.is_file():
        return None
    try:
        stat = path.stat()
        mtime = datetime.fromtimestamp(stat.st_mtime)
        size = stat.st_size
    except OSError:
        return None
    if size == 0:
        return None
    try:
        with closing(sqlite3.connect(_ro_uri(path), uri=True)) as conn:
            conn.row_factory = sqlite3.Row
            version, tables = _inspect(conn)
            if tables == 0 or not _is_supported_version(version):
                status = "newer" if version > SCHEMA_VERSION else "unsupported"
                return _unsupported_slot(path, status, version, size, mtime)
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
                schema_version=version,
                size_bytes=size,
            )
    except sqlite3.OperationalError:
        return None  # file bloccato o non apribile: non è un salvataggio «danneggiato»
    except sqlite3.DatabaseError:
        return _unsupported_slot(path, "corrupt", 0, size, mtime)  # non SQLite / malformato
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


_CREATE_TABLES_SQL = """
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
    relays_f_json TEXT NOT NULL DEFAULT '{}',
    league_places_json TEXT NOT NULL DEFAULT '{}',
    rng_state_json TEXT NOT NULL DEFAULT '[]',
    race_strategy_json TEXT NOT NULL DEFAULT '{}',
    ranking_pool_json TEXT NOT NULL DEFAULT '[]',
    board_json TEXT NOT NULL DEFAULT '{}',
    retired_json TEXT NOT NULL DEFAULT '[]',
    agents_json TEXT NOT NULL DEFAULT '[]'
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
    gender TEXT NOT NULL DEFAULT '',
    contract_end_season INTEGER NOT NULL DEFAULT 0,
    contract_no_renew INTEGER NOT NULL DEFAULT 0,
    ranking_json TEXT NOT NULL DEFAULT '{}',
    season_injuries INTEGER NOT NULL DEFAULT 0,
    agent_id INTEGER,
    record_bonus INTEGER NOT NULL DEFAULT 0
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
        """Apre o crea il file. Regole (CLAUDE.md, convenzione 4):

        - file assente o di 0 byte: DB nuovo, creato in una sola transazione;
        - versione non riconosciuta (più recente, v0/v1 con dati, nessuna tabella utente):
          `UnsupportedSaveVersion` PRIMA di qualsiasi scrittura;
        - versione migrabile: backup verificato, poi migrazione in un'unica transazione;
        - versione corrente: nessuna scrittura (si completano solo eventuali tabelle mancanti).
        """
        self.last_backup_path: Optional[Path] = None
        path = self.db_path
        if not path.exists() or path.stat().st_size == 0:
            self._write_transaction(expected_version=0)
            return

        with closing(sqlite3.connect(_ro_uri(path), uri=True)) as ro:
            version, tables = _inspect(ro)
            if tables == 0 or not _is_supported_version(version):
                raise UnsupportedSaveVersion(version, SCHEMA_VERSION, path)
            if version == SCHEMA_VERSION:
                present = {
                    r[0]
                    for r in ro.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
                }
                needs_write = not _schema_table_names() <= present
            else:
                needs_write = True
                # Sorgente del backup: la stessa connessione in sola lettura dell'ispezione
                self.last_backup_path = _create_backup(ro, path, version)

        if not needs_write:
            return
        try:
            self._write_transaction(expected_version=version)
        except SaveMigrationError as exc:
            if exc.backup_path is None:
                exc.backup_path = self.last_backup_path
            raise
        except Exception as exc:
            raise SaveMigrationError(
                f"Migrazione dalla v{version} non riuscita ({exc}): il salvataggio è rimasto com'era.",
                self.last_backup_path,
            ) from exc
        if self.last_backup_path is not None:
            _prune_backups(path)  # solo a migrazione riuscita

    def _write_transaction(self, expected_version: int) -> None:
        """Migrazione e creazione tabelle in UNA transazione esplicita (`BEGIN IMMEDIATE`).

        `isolation_level=None`: il modulo `sqlite3` non apre né chiude transazioni da solo e
        non fa COMMIT impliciti. Gli ALTER, le CREATE e `PRAGMA user_version` stanno nella
        stessa transazione: o c'è tutto o non cambia niente.
        """
        conn = sqlite3.connect(str(self.db_path), isolation_level=None)
        try:
            conn.execute("BEGIN IMMEDIATE")
            # Riletta con il lock di scrittura: un altro processo può aver migrato nel frattempo
            current = int(conn.execute("PRAGMA user_version").fetchone()[0])
            if current != expected_version and current != SCHEMA_VERSION:
                raise SaveMigrationError(
                    f"La versione del file è cambiata durante l'apertura (v{expected_version} -> v{current})."
                )
            v = current
            while v in MIGRATIONS and current != SCHEMA_VERSION:
                for table, columns in MIGRATIONS[v].items():
                    for col_name, col_def in columns:
                        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}")
                v += 1
            for statement in _schema_statements():
                conn.execute(statement)
            # PRAGMA non accetta parametri: intero costante, mai input esterno
            conn.execute(f"PRAGMA user_version = {int(SCHEMA_VERSION)}")
            conn.execute("COMMIT")
        except BaseException:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

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
                {"key": o.key, "title": o.title, "completed": o.completed, "target": o.target, "value": o.value}
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
                    event_lineup_f_json, club_records_f_json, relays_f_json, league_places_json, rng_state_json, race_strategy_json, ranking_pool_json, board_json, retired_json, agents_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    json.dumps(state.league_places),
                    json.dumps(state.rng_state),
                    json.dumps(state.race_strategy),
                    _synthetic_to_json(state.ranking_pool),
                    json.dumps({"failed_streak": state.board_failed_streak, "fired": state.fired}),
                    _retired_to_json(state.retired),
                    _agents_to_json(state.agents),
                ),
            )

            conn.executemany(
                """
                INSERT INTO athletes (
                    id, name, age, specialty, speed, stamina, strength, technique,
                    resilience, form, fatigue, potential, personality, training_focus,
                    periodization, sleep_quality, nutrition, weekly_wage, injured_weeks,
                    is_youth_prospect, personal_best, personal_best_display, doping_boost_weeks,
                    in_youth_squad, fans, coach_id, nationality, height_cm, weight_kg, gender,
                    contract_end_season, contract_no_renew, ranking_json, season_injuries, agent_id, record_bonus
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        a.contract_end_season,
                        1 if a.contract_no_renew else 0,
                        json.dumps(a.ranking_points),
                        a.season_injuries,
                        a.agent_id,
                        a.record_bonus,
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
                    contract_end_season=r["contract_end_season"],
                    contract_no_renew=bool(r["contract_no_renew"]),
                    ranking_points={str(k): float(v) for k, v in json.loads(r["ranking_json"]).items()},
                    season_injuries=int(r["season_injuries"]),
                    agent_id=(int(r["agent_id"]) if r["agent_id"] is not None else None),
                    record_bonus=int(r["record_bonus"]),
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
                    key=o["key"],
                    title=o["title"],
                    completed=bool(o["completed"]),
                    target=int(o.get("target", 0)),
                    value=int(o.get("value", 0)),
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
                league_places={
                    str(k): [int(n) for n in v] for k, v in json.loads(row["league_places_json"]).items()
                },
                rng_state=json.loads(row["rng_state_json"]),
                race_strategy={
                    str(k): {str(a): str(b) for a, b in v.items()}
                    for k, v in json.loads(row["race_strategy_json"]).items()
                },
                coaches=coaches,
                retired=_retired_from_json(row["retired_json"]),
                agents=_agents_from_json(row["agents_json"]),
                relays=relays,
                coach_hired_week=row["coach_hired_week"],
                rival_clubs=_rivals_from_json(row["rivals_json"]),
                ranking_pool=_synthetic_from_json(row["ranking_pool_json"]),
                board_failed_streak=int(json.loads(row["board_json"]).get("failed_streak", 0)),
                fired=bool(json.loads(row["board_json"]).get("fired", False)),
                season_history=_season_history_from_json(row["season_history_json"]),
                event_lineup_f=json.loads(row["event_lineup_f_json"]),
                club_records_f=club_records_f,
                relays_f=relays_f,
            )
