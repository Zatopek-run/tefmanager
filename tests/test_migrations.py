"""Migrazioni e apertura dei salvataggi (lotti 1.1 e 1.2 di docs/PLAN.md).

SENZA Qt: non importa `views/` né `controllers/`, gira anche con il python3 di sistema:

    PYTHONPATH=. python3 -m unittest tests.test_migrations -v

Le fixture sono generate da codice: un DB corrente con dati «sentinella» riconoscibili, riportato
al layout di una versione precedente togliendo le colonne di `MIGRATIONS`.
E1 ed E2 sono gli esperimenti di docs/AUDIT.md (R1, R2) riscritti come test.
"""

from __future__ import annotations

import hashlib
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock

import models.database as dbm
from models.database import MIGRATIONS, SCHEMA_VERSION, DatabaseManager


# --------------------------------------------------------------------------- helper


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def columns(conn: sqlite3.Connection, table: str) -> set:
    """(nome, tipo, notnull, default, pk) di ogni colonna, senza l'ordine."""
    return {(r[1], r[2], r[3], r[4], r[5]) for r in conn.execute(f"PRAGMA table_info({table})")}


def column_names(conn: sqlite3.Connection, table: str) -> list:
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]


def user_version(path: Path) -> int:
    with closing(sqlite3.connect(f"{Path(path).resolve().as_uri()}?mode=ro", uri=True)) as conn:
        return conn.execute("PRAGMA user_version").fetchone()[0]


def _insert(conn: sqlite3.Connection, table: str, **given) -> None:
    """Inserisce una riga riempiendo con valori neutri le colonne NOT NULL senza default."""
    values = dict(given)
    for _cid, name, ctype, notnull, default, _pk in conn.execute(f"PRAGMA table_info({table})").fetchall():
        if name in values or default is not None or not notnull:
            continue
        values[name] = 0 if ctype.upper().startswith(("INT", "REAL")) else ""
    names = ", ".join(values)
    marks = ", ".join("?" for _ in values)
    conn.execute(f"INSERT INTO {table} ({names}) VALUES ({marks})", list(values.values()))


def make_save(path: Path, version: int) -> Path:
    """Crea uno slot alla `version` indicata con dati sentinella (game_state, athletes, transactions)."""
    DatabaseManager(db_path=path)  # DB corrente e vuoto
    with closing(sqlite3.connect(path)) as conn:
        _insert(
            conn, "game_state", id=1, team_name=f"SENTINELLA-v{version}", game_mode="vertical_slice",
            budget=7000 + version, week=3, season_number=1, season_phase="regular",
            start_date="2026-01-05", prestige=10, tier="Provinciale",
        )
        _insert(conn, "athletes", id=1, name=f"Atleta Sentinella {version}", age=20)
        _insert(conn, "transactions", week=1, description=f"sentinella-{version}", category="test", amount=version)
        for from_version, tables in MIGRATIONS.items():
            if from_version >= version:
                for table, cols in tables.items():
                    for col, _def in cols:
                        conn.execute(f"ALTER TABLE {table} DROP COLUMN {col}")
        if version <= 3:
            conn.execute("DROP TABLE coaches")  # il layout v2/v3 non l'aveva
        conn.execute(f"PRAGMA user_version = {version}")
        conn.commit()
    return path


def sentinel_ok(test: unittest.TestCase, path: Path, version: int) -> None:
    """I dati sentinella di `version` sono presenti e intatti in `path` (aperto in sola lettura)."""
    with closing(sqlite3.connect(f"{Path(path).resolve().as_uri()}?mode=ro", uri=True)) as conn:
        test.assertEqual(
            conn.execute("SELECT team_name, budget FROM game_state WHERE id = 1").fetchone(),
            (f"SENTINELLA-v{version}", 7000 + version),
        )
        test.assertEqual(conn.execute("SELECT name FROM athletes WHERE id = 1").fetchone()[0],
                         f"Atleta Sentinella {version}")
        test.assertEqual(
            conn.execute("SELECT description, amount FROM transactions").fetchall(),
            [(f"sentinella-{version}", version)],
        )


class _TmpCase(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name) / "saves"
        self.dir.mkdir()

    def slot(self, name: str = "partita") -> Path:
        return self.dir / f"{name}.db"

    def backups(self, name: str = "partita") -> list:
        return dbm.list_backups(self.slot(name))


def failing_migration(version: int, *, broken: bool) -> dict:
    """`MIGRATIONS[version]` con una colonna in testa e, se `broken`, uno statement rotto al 2° posto."""
    real = MIGRATIONS[version]
    first = ("e1_prima", "INTEGER NOT NULL DEFAULT 0")
    second = ("e1_seconda", "SYNTAX ERRATA ((") if broken else ("e1_seconda", "INTEGER NOT NULL DEFAULT 0")
    return {**real, "game_state": [first, second, *real.get("game_state", [])]}


# --------------------------------------------------------------------------- lotto 1.1


class TestMigrationSafety(_TmpCase):
    def test_schema_statements_are_single(self) -> None:
        # La migrazione esegue gli statement uno per uno: niente ';' dentro un literal
        statements = dbm._schema_statements()
        self.assertEqual(len(statements), dbm._CREATE_TABLES_SQL.count("CREATE TABLE"))
        for st in statements:
            self.assertTrue(sqlite3.complete_statement(st + ";"), st[:60])
        for version, tables in MIGRATIONS.items():
            for table, cols in tables.items():
                for col, definition in cols:
                    self.assertNotIn(";", f"{table}{col}{definition}")

    def test_sqlite_transaction_semantics_on_this_python(self) -> None:
        # Non si assume il default del modulo sqlite3: lo si misura.
        db = self.dir / "sem.db"
        with closing(sqlite3.connect(db)) as conn:  # modalità di default
            conn.execute("CREATE TABLE t (a)")
            conn.commit()
            conn.execute("ALTER TABLE t ADD COLUMN b")
            conn.rollback()
            self.assertEqual(column_names(conn, "t"), ["a", "b"], "il default NON protegge gli ALTER")
        with closing(sqlite3.connect(db, isolation_level=None)) as conn:  # esplicito
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("ALTER TABLE t ADD COLUMN c")
            conn.execute("PRAGMA user_version = 5")
            self.assertTrue(conn.in_transaction)
            conn.execute("ROLLBACK")
            self.assertEqual(column_names(conn, "t"), ["a", "b"])
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 0)

    def test_fixtures_use_rollback_journal(self) -> None:
        # Premessa del confronto per hash: niente WAL, quindi nessun file -wal da considerare
        path = make_save(self.slot(), 7)
        with closing(sqlite3.connect(path)) as conn:
            self.assertEqual(conn.execute("PRAGMA journal_mode").fetchone()[0], "delete")

    def test_every_old_version_migrates_with_data_and_backup(self) -> None:
        fresh = self.dir / "fresh.db"
        DatabaseManager(db_path=fresh)
        with closing(sqlite3.connect(fresh)) as conn:
            expected = {
                t: columns(conn, t)
                for (t,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
                if not t.startswith("sqlite_")
            }
        for version in range(2, SCHEMA_VERSION):
            with self.subTest(partenza=version):
                path = make_save(self.slot(f"v{version}"), version)
                db = DatabaseManager(db_path=path)
                self.assertEqual(user_version(path), SCHEMA_VERSION)
                sentinel_ok(self, path, version)
                with closing(sqlite3.connect(path)) as conn:
                    for table, cols in expected.items():
                        self.assertEqual(columns(conn, table), cols, table)
                # il backup esiste, è alla versione di partenza e contiene i dati sentinella
                found = self.backups(f"v{version}")
                self.assertEqual(len(found), 1)
                self.assertEqual(db.last_backup_path, found[0])
                self.assertEqual(user_version(found[0]), version)
                sentinel_ok(self, found[0], version)
                self.assertTrue(found[0].name.endswith(".db.bak"))

    def test_e1_failed_migration_leaves_original_untouched(self) -> None:
        """E1 (AUDIT R1): un ALTER che fallisce a metà non deve lasciare tracce."""
        path = make_save(self.slot(), 7)
        before = sha(path)
        with mock.patch.dict(MIGRATIONS, {7: failing_migration(7, broken=True)}):
            with self.assertRaises(Exception):
                DatabaseManager(db_path=path)
        self.assertEqual(sha(path), before, "il file originale deve essere identico byte per byte")
        self.assertEqual(user_version(path), 7)
        with closing(sqlite3.connect(path)) as conn:
            self.assertNotIn("e1_prima", column_names(conn, "game_state"), "nessuna colonna parziale")
        # Il file si riapre: con lo stesso statement corretto la migrazione riesce, senza
        # «duplicate column name» (prima del fix la colonna e1_prima era rimasta).
        with mock.patch.dict(MIGRATIONS, {7: failing_migration(7, broken=False)}):
            DatabaseManager(db_path=path)
        self.assertEqual(user_version(path), SCHEMA_VERSION)
        sentinel_ok(self, path, 7)

    def test_failure_is_typed_and_reports_the_backup(self) -> None:
        path = make_save(self.slot(), 7)
        with mock.patch.dict(MIGRATIONS, {7: failing_migration(7, broken=True)}):
            with self.assertRaises(dbm.SaveMigrationError) as cm:
                DatabaseManager(db_path=path)
        self.assertIsInstance(cm.exception.__cause__, sqlite3.OperationalError)
        self.assertEqual(cm.exception.backup_path, self.backups()[0])
        self.assertEqual(user_version(cm.exception.backup_path), 7)

    def test_failed_then_retried_keeps_two_valid_backups(self) -> None:
        path = make_save(self.slot(), 7)
        with mock.patch.dict(MIGRATIONS, {7: failing_migration(7, broken=True)}):
            with self.assertRaises(dbm.SaveMigrationError):
                DatabaseManager(db_path=path)
        self.assertEqual(len(self.backups()), 1)
        first = self.backups()[0]
        with mock.patch.dict(MIGRATIONS, {7: failing_migration(7, broken=False)}):
            DatabaseManager(db_path=path)
        found = self.backups()
        self.assertEqual(len(found), 2)
        self.assertIn(first, found, "il backup del tentativo fallito non va cancellato")
        for backup in found:  # entrambi validi e alla versione di partenza, con i dati
            self.assertEqual(user_version(backup), 7)
            sentinel_ok(self, backup, 7)
            with closing(sqlite3.connect(backup)) as conn:
                self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_retention_keeps_three_per_slot_and_only_after_success(self) -> None:
        other = make_save(self.slot("partita_2"), 5)  # slot con nome che inizia uguale
        DatabaseManager(db_path=other)
        other_backups = self.backups("partita_2")
        for _ in range(4):
            path = self.slot()
            path.unlink(missing_ok=True)
            make_save(path, 7)
            DatabaseManager(db_path=path)
        self.assertEqual(len(self.backups()), 3, "al massimo 3 per slot")
        # un tentativo FALLITO aggiunge un backup e non ne cancella nessuno
        path = self.slot()
        path.unlink()
        make_save(path, 7)
        kept = self.backups()
        with mock.patch.dict(MIGRATIONS, {7: failing_migration(7, broken=True)}):
            with self.assertRaises(dbm.SaveMigrationError):
                DatabaseManager(db_path=path)
        after_failure = self.backups()
        self.assertEqual(len(after_failure), 4)
        self.assertTrue(set(kept) <= set(after_failure))
        # a migrazione riuscita si torna a 3, restano i più recenti
        with mock.patch.dict(MIGRATIONS, {7: failing_migration(7, broken=False)}):
            DatabaseManager(db_path=path)
        final = self.backups()
        self.assertEqual(len(final), 3)
        self.assertEqual(final[:2], after_failure[-2:], "restano i più recenti")
        self.assertNotIn(final[2], after_failure)
        self.assertEqual(self.backups("partita_2"), other_backups, "l'altro slot non si tocca")

    def test_current_version_opens_without_writing_or_backup(self) -> None:
        path = make_save(self.slot(), SCHEMA_VERSION)
        before, mtime = sha(path), path.stat().st_mtime_ns
        DatabaseManager(db_path=path)
        DatabaseManager(db_path=path)
        self.assertEqual(sha(path), before)
        self.assertEqual(path.stat().st_mtime_ns, mtime)
        self.assertEqual(self.backups(), [])
        self.assertFalse((self.dir / dbm.BACKUPS_DIRNAME).exists())
        self.assertIsNone(DatabaseManager(db_path=path).last_backup_path)

    def test_backup_verification_failure_blocks_the_migration(self) -> None:
        path = make_save(self.slot(), 7)
        before = sha(path)
        with mock.patch.object(dbm, "_verify_backup", side_effect=dbm.SaveMigrationError("rotto")):
            with self.assertRaises(dbm.SaveMigrationError):
                DatabaseManager(db_path=path)
        self.assertEqual(sha(path), before)
        self.assertEqual(user_version(path), 7)
        self.assertEqual(list((self.dir / dbm.BACKUPS_DIRNAME).iterdir()), [], "né backup né .tmp")

    def test_version_changed_by_another_process_is_reread_inside_the_transaction(self) -> None:
        real = dbm._create_backup

        def other_process(version_set: int, record: dict):
            def sneaky(source, db_path, version):
                out = real(source, db_path, version)
                with closing(sqlite3.connect(db_path)) as conn:
                    conn.execute(f"PRAGMA user_version = {version_set}")
                    conn.commit()
                record["hash"] = sha(db_path)
                return out
            return sneaky

        # A: l'altro processo ha già portato il file alla versione corrente: niente ALTER
        path = make_save(self.slot("a"), 7)
        record: dict = {}
        with mock.patch.object(dbm, "_create_backup", other_process(SCHEMA_VERSION, record)):
            DatabaseManager(db_path=path)
        with closing(sqlite3.connect(path)) as conn:
            self.assertNotIn("relays_f_json", column_names(conn, "game_state"))
        self.assertEqual(user_version(path), SCHEMA_VERSION)
        # B: versione diversa da quella ispezionata e da quella corrente: errore, file com'era
        path = make_save(self.slot("b"), 7)
        record = {}
        with mock.patch.object(dbm, "_create_backup", other_process(6, record)):
            with self.assertRaises(dbm.SaveMigrationError):
                DatabaseManager(db_path=path)
        self.assertEqual(sha(path), record["hash"])
        self.assertEqual(user_version(path), 6)

    def test_new_database_is_created_in_one_transaction(self) -> None:
        for kind in ("assente", "zero byte"):
            with self.subTest(kind):
                path = self.slot(kind.replace(" ", "_"))
                if kind == "zero byte":
                    path.touch()
                DatabaseManager(db_path=path)
                self.assertEqual(user_version(path), SCHEMA_VERSION)
                self.assertEqual(self.backups(kind.replace(" ", "_")), [])
        # se la creazione fallisce a metà non resta un file v0 con tabelle (verrebbe rifiutato)
        path = self.slot("nuovo")
        broken = list(dbm._schema_statements())
        broken.insert(2, "CREATE TABLE ((")
        with mock.patch.object(dbm, "_schema_statements", return_value=tuple(broken)):
            with self.assertRaises(sqlite3.Error):
                DatabaseManager(db_path=path)
        self.assertEqual(path.stat().st_size, 0)
        DatabaseManager(db_path=path)
        self.assertEqual(user_version(path), SCHEMA_VERSION)

    def test_missing_table_in_a_current_save_is_completed(self) -> None:
        path = make_save(self.slot(), SCHEMA_VERSION)
        with closing(sqlite3.connect(path)) as conn:
            conn.execute("DROP TABLE coaches")
            conn.commit()
        DatabaseManager(db_path=path)
        with closing(sqlite3.connect(path)) as conn:
            self.assertEqual(len(column_names(conn, "coaches")), 4)
        sentinel_ok(self, path, SCHEMA_VERSION)
        self.assertEqual(self.backups(), [])

    def test_backups_are_not_listed_as_save_slots(self) -> None:
        path = make_save(self.slot(), 7)
        DatabaseManager(db_path=path)
        self.assertEqual(len(self.backups()), 1)
        slots = dbm.list_save_slots(self.dir, legacy_path=self.dir / "inesistente.db")
        self.assertEqual([s.path for s in slots], [path])  # glob reale, non un filtro sui nomi
        self.assertEqual(slots[0].team_name, "SENTINELLA-v7")


if __name__ == "__main__":
    unittest.main()
