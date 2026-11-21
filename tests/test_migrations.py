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


# --------------------------------------------------------------------------- lotto 1.2


class TestUnsupportedVersions(_TmpCase):
    def assert_refused(self, path: Path, found: int) -> dbm.UnsupportedSaveVersion:
        before = sha(path)
        with self.assertRaises(dbm.UnsupportedSaveVersion) as cm:
            DatabaseManager(db_path=path)
        self.assertEqual(sha(path), before, "nessuna scrittura: hash identico")
        self.assertEqual(cm.exception.versione_trovata, found)
        self.assertEqual(cm.exception.versione_attesa, SCHEMA_VERSION)
        self.assertFalse((path.parent / dbm.BACKUPS_DIRNAME).exists(), "nessun backup per un rifiuto")
        return cm.exception

    def test_e2_unknown_versions_are_refused_not_wiped(self) -> None:
        """E2 (AUDIT R2): più recente, v0 e v1 con dati non vengono mai azzerati."""
        for version in (SCHEMA_VERSION + 1, SCHEMA_VERSION + 50, 0, 1):
            with self.subTest(versione=version):
                path = make_save(self.slot(f"x{version}"), SCHEMA_VERSION)
                with closing(sqlite3.connect(path)) as conn:
                    conn.execute(f"PRAGMA user_version = {version}")
                    conn.commit()
                self.assert_refused(path, version)
                with closing(sqlite3.connect(path)) as conn:  # nessun DROP: i dati ci sono ancora
                    self.assertEqual(
                        conn.execute("SELECT team_name FROM game_state").fetchone()[0],
                        f"SENTINELLA-v{SCHEMA_VERSION}",
                    )
                    self.assertEqual(conn.execute("SELECT COUNT(*) FROM athletes").fetchone()[0], 1)

    def test_messages_distinguish_newer_from_unrecognised(self) -> None:
        newer = dbm.UnsupportedSaveVersion(SCHEMA_VERSION + 1, SCHEMA_VERSION)
        old = dbm.UnsupportedSaveVersion(1, SCHEMA_VERSION)
        self.assertTrue(newer.is_newer)
        self.assertFalse(old.is_newer)
        self.assertIn("più recente", newer.message)
        self.assertIn("aggiorna il gioco", newer.message)
        self.assertIn("non riconosciuto o non migrabile", old.message)
        self.assertNotIn("più recente", old.message)

    def test_a_gap_in_the_migration_chain_is_refused(self) -> None:
        path = make_save(self.slot(), 7)
        chain = {k: v for k, v in MIGRATIONS.items() if k != 8}  # 7 -> 8 -> (manca) -> 9
        with mock.patch.dict(dbm.__dict__, {"MIGRATIONS": chain}):
            self.assert_refused(path, 7)

    def test_non_empty_file_without_user_tables_is_refused(self) -> None:
        # zero tabelle utente (sqlite_sequence non conta): non è un DB nuovo
        only_header = self.slot("intestazione")
        with closing(sqlite3.connect(only_header)) as conn:
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            conn.commit()
        self.assertGreater(only_header.stat().st_size, 0)
        self.assert_refused(only_header, SCHEMA_VERSION)
        dropped = self.slot("droppato")
        with closing(sqlite3.connect(dropped)) as conn:
            conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY AUTOINCREMENT)")
            conn.execute("INSERT INTO t DEFAULT VALUES")
            conn.execute("DROP TABLE t")  # resta sqlite_sequence
            conn.execute("PRAGMA user_version = 5")
            conn.commit()
        with closing(sqlite3.connect(dropped)) as conn:
            self.assertEqual(dbm._inspect(conn), (5, 0))
        self.assert_refused(dropped, 5)

    def test_a_non_sqlite_file_is_not_touched(self) -> None:
        path = self.slot("testo")
        path.write_bytes(b"questo non e' un database sqlite " * 40)
        before = sha(path)
        with self.assertRaises(sqlite3.DatabaseError):
            DatabaseManager(db_path=path)
        self.assertEqual(sha(path), before)

    def test_read_save_summary_lists_unsupported_slots_read_only(self) -> None:
        cases = {"nuovo": SCHEMA_VERSION + 3, "vecchio": 1, "zero": 0}
        for name, version in cases.items():
            with self.subTest(name):
                path = make_save(self.slot(name), SCHEMA_VERSION)
                with closing(sqlite3.connect(path)) as conn:
                    conn.execute(f"PRAGMA user_version = {version}")
                    conn.commit()
                before, mtime = sha(path), path.stat().st_mtime_ns
                info = dbm.read_save_summary(path)
                assert info is not None
                self.assertFalse(info.is_supported)
                self.assertEqual(info.status, "newer" if version > SCHEMA_VERSION else "unsupported")
                self.assertEqual(info.schema_version, version)
                self.assertEqual(info.size_bytes, path.stat().st_size)
                self.assertIn(f"(v{version})", info.team_name)
                self.assertAlmostEqual(info.updated_at.timestamp(), path.stat().st_mtime, places=3)
                self.assertEqual(sha(path), before)
                self.assertEqual(path.stat().st_mtime_ns, mtime)

    def test_corrupt_and_empty_files_in_the_slot_list(self) -> None:
        good = make_save(self.slot("buono"), SCHEMA_VERSION)
        newer = make_save(self.slot("piu_recente"), SCHEMA_VERSION)
        with closing(sqlite3.connect(newer)) as conn:
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
            conn.commit()
        garbage = self.slot("danneggiato")
        garbage.write_bytes(b"\x00\x01 non sqlite " * 100)
        self.slot("vuoto").touch()
        # un backup vero nella sottocartella: non deve comparire
        make_save(self.slot("vecchio"), 7)
        DatabaseManager(db_path=self.slot("vecchio"))
        self.assertTrue(self.backups("vecchio"))
        slots = dbm.list_save_slots(self.dir, legacy_path=self.dir / "inesistente.db")
        by_name = {s.path.name: s for s in slots}
        self.assertEqual(
            set(by_name), {"buono.db", "piu_recente.db", "danneggiato.db", "vecchio.db"},
            "il file di 0 byte non è uno slot; i backup non compaiono",
        )
        self.assertEqual(by_name["buono.db"].status, "ok")
        self.assertEqual(by_name["piu_recente.db"].status, "newer")
        self.assertEqual(by_name["danneggiato.db"].status, "corrupt")
        self.assertEqual(by_name["danneggiato.db"].team_name, "Salvataggio danneggiato")
        self.assertEqual(good, by_name["buono.db"].path)


class TestMigrationV10Contracts(_TmpCase):
    """v9 → v10 (Q22): colonna `contract_end_season` negli atleti, con 0 = «da assegnare»."""

    def test_v9_save_gets_the_column_with_default_zero_and_a_verified_backup(self) -> None:
        self.assertGreaterEqual(SCHEMA_VERSION, 10)
        self.assertIn(9, MIGRATIONS)
        path = make_save(self.slot("v9"), 9)
        with closing(sqlite3.connect(path)) as conn:
            self.assertNotIn("contract_end_season", column_names(conn, "athletes"))  # la fixture è davvero v9
        db = DatabaseManager(db_path=path)
        self.assertEqual(user_version(path), SCHEMA_VERSION)
        with closing(sqlite3.connect(path)) as conn:
            self.assertEqual(conn.execute("SELECT contract_end_season FROM athletes WHERE id = 1").fetchone(), (0,))
            self.assertIn(
                ("contract_end_season", "INTEGER", 1, "0", 0), columns(conn, "athletes"),
            )
        sentinel_ok(self, path, 9)
        backup = self.backups("v9")[0]
        self.assertEqual(db.last_backup_path, backup)
        self.assertEqual(user_version(backup), 9)
        with closing(sqlite3.connect(backup)) as conn:
            self.assertNotIn("contract_end_season", column_names(conn, "athletes"))
        sentinel_ok(self, backup, 9)

    def test_failed_v9_migration_leaves_the_save_untouched(self) -> None:
        path = make_save(self.slot("v9"), 9)
        before = sha(path)
        broken = {"athletes": [("contract_end_season", "INTEGER NOT NULL DEFAULT 0"), ("rotta", "SYNTAX ((")]}
        with mock.patch.dict(MIGRATIONS, {9: broken}):
            with self.assertRaises(dbm.SaveMigrationError):
                DatabaseManager(db_path=path)
        self.assertEqual(sha(path), before)
        self.assertEqual(user_version(path), 9)


class TestMigrationV11NoRenew(_TmpCase):
    """v10 → v11: colonna `contract_no_renew` («non rinnovare»), con 0 = rinnovo automatico."""

    def test_v10_save_gets_the_column_with_default_zero_and_a_verified_backup(self) -> None:
        self.assertGreaterEqual(SCHEMA_VERSION, 11)
        self.assertIn(10, MIGRATIONS)
        path = make_save(self.slot("v10"), 10)
        with closing(sqlite3.connect(path)) as conn:
            self.assertNotIn("contract_no_renew", column_names(conn, "athletes"))  # la fixture è davvero v10
            self.assertIn("contract_end_season", column_names(conn, "athletes"))
        db = DatabaseManager(db_path=path)
        self.assertEqual(user_version(path), SCHEMA_VERSION)
        with closing(sqlite3.connect(path)) as conn:
            self.assertEqual(conn.execute("SELECT contract_no_renew FROM athletes WHERE id = 1").fetchone(), (0,))
            self.assertIn(("contract_no_renew", "INTEGER", 1, "0", 0), columns(conn, "athletes"))
        sentinel_ok(self, path, 10)
        backup = self.backups("v10")[0]
        self.assertEqual(db.last_backup_path, backup)
        self.assertEqual(user_version(backup), 10)
        with closing(sqlite3.connect(backup)) as conn:
            self.assertNotIn("contract_no_renew", column_names(conn, "athletes"))
        sentinel_ok(self, backup, 10)

    def test_failed_v10_migration_leaves_the_save_untouched(self) -> None:
        path = make_save(self.slot("v10"), 10)
        before = sha(path)
        broken = {"athletes": [("contract_no_renew", "INTEGER NOT NULL DEFAULT 0"), ("rotta", "SYNTAX ((")]}
        with mock.patch.dict(MIGRATIONS, {10: broken}):
            with self.assertRaises(dbm.SaveMigrationError):
                DatabaseManager(db_path=path)
        self.assertEqual(sha(path), before)
        self.assertEqual(user_version(path), 10)


class TestMigrationV12LeaguePlaces(_TmpCase):
    """v11 → v12 (A.2): colonna `league_places_json` (piazzamenti per club, per lo spareggio), default `'{}'`."""

    def test_v11_save_gets_the_column_with_default_and_a_verified_backup(self) -> None:
        self.assertGreaterEqual(SCHEMA_VERSION, 12)
        self.assertIn(11, MIGRATIONS)
        path = make_save(self.slot("v11"), 11)
        with closing(sqlite3.connect(path)) as conn:
            self.assertNotIn("league_places_json", column_names(conn, "game_state"))  # la fixture è davvero v11
            self.assertIn("contract_no_renew", column_names(conn, "athletes"))
        db = DatabaseManager(db_path=path)
        self.assertEqual(user_version(path), SCHEMA_VERSION)
        with closing(sqlite3.connect(path)) as conn:
            self.assertEqual(conn.execute("SELECT league_places_json FROM game_state WHERE id = 1").fetchone(), ("{}",))
            self.assertIn(("league_places_json", "TEXT", 1, "'{}'", 0), columns(conn, "game_state"))
        sentinel_ok(self, path, 11)
        backup = self.backups("v11")[0]
        self.assertEqual(db.last_backup_path, backup)
        self.assertEqual(user_version(backup), 11)
        with closing(sqlite3.connect(backup)) as conn:
            self.assertNotIn("league_places_json", column_names(conn, "game_state"))
        sentinel_ok(self, backup, 11)

    def test_failed_v11_migration_leaves_the_save_untouched(self) -> None:
        path = make_save(self.slot("v11"), 11)
        before = sha(path)
        broken = {"game_state": [("league_places_json", "TEXT NOT NULL DEFAULT '{}'"), ("rotta", "SYNTAX ((")]}
        with mock.patch.dict(MIGRATIONS, {11: broken}):
            with self.assertRaises(dbm.SaveMigrationError):
                DatabaseManager(db_path=path)
        self.assertEqual(sha(path), before)
        self.assertEqual(user_version(path), 11)


class TestMigrationV13RngState(_TmpCase):
    """v12 → v13 (A.3): colonna `rng_state_json` (stato dell'RNG della partita), default `'[]'` = salvataggio vecchio."""

    def test_v12_save_gets_the_column_with_default_and_a_verified_backup(self) -> None:
        self.assertGreaterEqual(SCHEMA_VERSION, 13)
        self.assertIn(12, MIGRATIONS)
        path = make_save(self.slot("v12"), 12)
        with closing(sqlite3.connect(path)) as conn:
            self.assertNotIn("rng_state_json", column_names(conn, "game_state"))  # la fixture è davvero v12
            self.assertIn("league_places_json", column_names(conn, "game_state"))
        db = DatabaseManager(db_path=path)
        self.assertEqual(user_version(path), SCHEMA_VERSION)
        with closing(sqlite3.connect(path)) as conn:
            self.assertEqual(conn.execute("SELECT rng_state_json FROM game_state WHERE id = 1").fetchone(), ("[]",))
            self.assertIn(("rng_state_json", "TEXT", 1, "'[]'", 0), columns(conn, "game_state"))
        sentinel_ok(self, path, 12)
        backup = self.backups("v12")[0]
        self.assertEqual(db.last_backup_path, backup)
        self.assertEqual(user_version(backup), 12)
        with closing(sqlite3.connect(backup)) as conn:
            self.assertNotIn("rng_state_json", column_names(conn, "game_state"))
        sentinel_ok(self, backup, 12)

    def test_failed_v12_migration_leaves_the_save_untouched(self) -> None:
        path = make_save(self.slot("v12"), 12)
        before = sha(path)
        broken = {"game_state": [("rng_state_json", "TEXT NOT NULL DEFAULT '[]'"), ("rotta", "SYNTAX ((")]}
        with mock.patch.dict(MIGRATIONS, {12: broken}):
            with self.assertRaises(dbm.SaveMigrationError):
                DatabaseManager(db_path=path)
        self.assertEqual(sha(path), before)
        self.assertEqual(user_version(path), 12)


class TestMigrationV14RaceStrategy(_TmpCase):
    """v13 → v14 (B.1): colonna `race_strategy_json` (piano gara per evento), default `'{}'` = ritmo Medio, nessuno scatto."""

    def test_v13_save_gets_the_column_with_default_and_a_verified_backup(self) -> None:
        self.assertGreaterEqual(SCHEMA_VERSION, 14)
        self.assertIn(13, MIGRATIONS)
        path = make_save(self.slot("v13"), 13)
        with closing(sqlite3.connect(path)) as conn:
            self.assertNotIn("race_strategy_json", column_names(conn, "game_state"))  # la fixture è davvero v13
            self.assertIn("rng_state_json", column_names(conn, "game_state"))
        db = DatabaseManager(db_path=path)
        self.assertEqual(user_version(path), SCHEMA_VERSION)
        with closing(sqlite3.connect(path)) as conn:
            self.assertEqual(conn.execute("SELECT race_strategy_json FROM game_state WHERE id = 1").fetchone(), ("{}",))
            self.assertIn(("race_strategy_json", "TEXT", 1, "'{}'", 0), columns(conn, "game_state"))
        sentinel_ok(self, path, 13)
        backup = self.backups("v13")[0]
        self.assertEqual(db.last_backup_path, backup)
        self.assertEqual(user_version(backup), 13)
        with closing(sqlite3.connect(backup)) as conn:
            self.assertNotIn("race_strategy_json", column_names(conn, "game_state"))
        sentinel_ok(self, backup, 13)

    def test_failed_v13_migration_leaves_the_save_untouched(self) -> None:
        path = make_save(self.slot("v13"), 13)
        before = sha(path)
        broken = {"game_state": [("race_strategy_json", "TEXT NOT NULL DEFAULT '{}'"), ("rotta", "SYNTAX ((")]}
        with mock.patch.dict(MIGRATIONS, {13: broken}):
            with self.assertRaises(dbm.SaveMigrationError):
                DatabaseManager(db_path=path)
        self.assertEqual(sha(path), before)
        self.assertEqual(user_version(path), 13)


class TestMigrationV15Ranking(_TmpCase):
    """v14 → v15 (C.1): `athletes.ranking_json` (punti per evento) e `game_state.ranking_pool_json` (campo sintetico)."""

    def test_v14_save_gets_both_columns_with_defaults_and_a_verified_backup(self) -> None:
        self.assertGreaterEqual(SCHEMA_VERSION, 15)
        self.assertIn(14, MIGRATIONS)
        path = make_save(self.slot("v14"), 14)
        with closing(sqlite3.connect(path)) as conn:
            self.assertNotIn("ranking_json", column_names(conn, "athletes"))  # la fixture è davvero v14
            self.assertNotIn("ranking_pool_json", column_names(conn, "game_state"))
            self.assertIn("race_strategy_json", column_names(conn, "game_state"))
        db = DatabaseManager(db_path=path)
        self.assertEqual(user_version(path), SCHEMA_VERSION)
        with closing(sqlite3.connect(path)) as conn:
            self.assertEqual(conn.execute("SELECT ranking_pool_json FROM game_state WHERE id = 1").fetchone(), ("[]",))
            self.assertIn(("ranking_pool_json", "TEXT", 1, "'[]'", 0), columns(conn, "game_state"))
            self.assertIn(("ranking_json", "TEXT", 1, "'{}'", 0), columns(conn, "athletes"))
            values = {r[0] for r in conn.execute("SELECT ranking_json FROM athletes")}
            self.assertLessEqual(values, {"{}"})
        sentinel_ok(self, path, 14)
        backup = self.backups("v14")[0]
        self.assertEqual(db.last_backup_path, backup)
        self.assertEqual(user_version(backup), 14)
        with closing(sqlite3.connect(backup)) as conn:
            self.assertNotIn("ranking_pool_json", column_names(conn, "game_state"))
            self.assertNotIn("ranking_json", column_names(conn, "athletes"))
        sentinel_ok(self, backup, 14)

    def test_failed_v14_migration_leaves_the_save_untouched(self) -> None:
        path = make_save(self.slot("v14"), 14)
        before = sha(path)
        broken = {
            "athletes": [("ranking_json", "TEXT NOT NULL DEFAULT '{}'")],
            "game_state": [("ranking_pool_json", "TEXT NOT NULL DEFAULT '[]'"), ("rotta", "SYNTAX ((")],
        }
        with mock.patch.dict(MIGRATIONS, {14: broken}):
            with self.assertRaises(dbm.SaveMigrationError):
                DatabaseManager(db_path=path)
        self.assertEqual(sha(path), before)
        self.assertEqual(user_version(path), 14)
        with closing(sqlite3.connect(path)) as conn:  # la prima colonna è stata annullata insieme alla seconda
            self.assertNotIn("ranking_json", column_names(conn, "athletes"))


class TestMigrationV16Board(_TmpCase):
    """v15 → v16 (C.2): colonna `game_state.board_json` (stagioni fallite di fila ed esonero), default `'{}'`."""

    def test_v15_save_gets_the_column_with_default_and_a_verified_backup(self) -> None:
        self.assertGreaterEqual(SCHEMA_VERSION, 16)
        self.assertIn(15, MIGRATIONS)
        path = make_save(self.slot("v15"), 15)
        with closing(sqlite3.connect(path)) as conn:
            self.assertNotIn("board_json", column_names(conn, "game_state"))  # la fixture è davvero v15
            self.assertIn("ranking_pool_json", column_names(conn, "game_state"))
        db = DatabaseManager(db_path=path)
        self.assertEqual(user_version(path), SCHEMA_VERSION)
        with closing(sqlite3.connect(path)) as conn:
            self.assertEqual(conn.execute("SELECT board_json FROM game_state WHERE id = 1").fetchone(), ("{}",))
            self.assertIn(("board_json", "TEXT", 1, "'{}'", 0), columns(conn, "game_state"))
        sentinel_ok(self, path, 15)
        backup = self.backups("v15")[0]
        self.assertEqual(db.last_backup_path, backup)
        self.assertEqual(user_version(backup), 15)
        with closing(sqlite3.connect(backup)) as conn:
            self.assertNotIn("board_json", column_names(conn, "game_state"))
        sentinel_ok(self, backup, 15)

    def test_a_migrated_save_loads_with_no_failed_season_and_not_fired(self) -> None:
        from tests.test_assignments import make_state

        path = self.slot("v16")
        state = make_state(3)
        state.board_failed_streak, state.fired = 1, True
        DatabaseManager(db_path=path).save_game(state)
        with closing(sqlite3.connect(path)) as conn:  # come dopo la migrazione: la colonna ha il valore di default
            conn.execute("UPDATE game_state SET board_json = '{}'")
            conn.commit()
        loaded = DatabaseManager(db_path=path).load_game()
        self.assertEqual((loaded.board_failed_streak, loaded.fired), (0, False))

    def test_failed_v15_migration_leaves_the_save_untouched(self) -> None:
        path = make_save(self.slot("v15"), 15)
        before = sha(path)
        broken = {"game_state": [("board_json", "TEXT NOT NULL DEFAULT '{}'"), ("rotta", "SYNTAX ((")]}
        with mock.patch.dict(MIGRATIONS, {15: broken}):
            with self.assertRaises(dbm.SaveMigrationError):
                DatabaseManager(db_path=path)
        self.assertEqual(sha(path), before)
        self.assertEqual(user_version(path), 15)


class TestMigrationV17Retirement(_TmpCase):
    """v16 → v17 (C.3): `athletes.season_injuries` (default 0) e `game_state.retired_json` (default `'[]'`)."""

    def test_v16_save_gets_the_columns_with_default_and_a_verified_backup(self) -> None:
        self.assertGreaterEqual(SCHEMA_VERSION, 17)
        self.assertIn(16, MIGRATIONS)
        path = make_save(self.slot("v16"), 16)
        with closing(sqlite3.connect(path)) as conn:
            self.assertNotIn("retired_json", column_names(conn, "game_state"))  # la fixture è davvero v16
            self.assertNotIn("season_injuries", column_names(conn, "athletes"))
            self.assertIn("board_json", column_names(conn, "game_state"))
        db = DatabaseManager(db_path=path)
        self.assertEqual(user_version(path), SCHEMA_VERSION)
        with closing(sqlite3.connect(path)) as conn:
            self.assertEqual(conn.execute("SELECT retired_json FROM game_state WHERE id = 1").fetchone(), ("[]",))
            self.assertEqual(conn.execute("SELECT season_injuries FROM athletes WHERE id = 1").fetchone(), (0,))
            self.assertIn(("retired_json", "TEXT", 1, "'[]'", 0), columns(conn, "game_state"))
            self.assertIn(("season_injuries", "INTEGER", 1, "0", 0), columns(conn, "athletes"))
        sentinel_ok(self, path, 16)
        backup = self.backups("v16")[0]
        self.assertEqual(db.last_backup_path, backup)
        self.assertEqual(user_version(backup), 16)
        with closing(sqlite3.connect(backup)) as conn:
            self.assertNotIn("retired_json", column_names(conn, "game_state"))
        sentinel_ok(self, backup, 16)

    def test_a_migrated_save_loads_with_no_retired_and_no_injuries(self) -> None:
        from tests.test_assignments import make_state

        path = self.slot("v17")
        state = make_state(3)
        state.athletes[0].season_injuries = 3
        DatabaseManager(db_path=path).save_game(state)
        with closing(sqlite3.connect(path)) as conn:  # come dopo la migrazione: le colonne hanno il valore di default
            conn.execute("UPDATE game_state SET retired_json = '[]'")
            conn.execute("UPDATE athletes SET season_injuries = 0")
            conn.commit()
        loaded = DatabaseManager(db_path=path).load_game()
        self.assertEqual(loaded.retired, [])
        self.assertTrue(all(a.season_injuries == 0 for a in loaded.athletes))

    def test_failed_v16_migration_leaves_the_save_untouched(self) -> None:
        path = make_save(self.slot("v16"), 16)
        before = sha(path)
        broken = {"game_state": [("retired_json", "TEXT NOT NULL DEFAULT '[]'"), ("rotta", "SYNTAX ((")]}
        with mock.patch.dict(MIGRATIONS, {16: broken}):
            with self.assertRaises(dbm.SaveMigrationError):
                DatabaseManager(db_path=path)
        self.assertEqual(sha(path), before)
        self.assertEqual(user_version(path), 16)


class TestMigrationV18Agents(_TmpCase):
    """v17 → v18 (D.1): `athletes.agent_id` (NULL = nessun agente) e `game_state.agents_json` (default `'[]'`)."""

    def test_v17_save_gets_the_columns_with_default_and_a_verified_backup(self) -> None:
        self.assertGreaterEqual(SCHEMA_VERSION, 18)
        self.assertIn(17, MIGRATIONS)
        path = make_save(self.slot("v17"), 17)
        with closing(sqlite3.connect(path)) as conn:
            self.assertNotIn("agents_json", column_names(conn, "game_state"))  # la fixture è davvero v17
            self.assertNotIn("agent_id", column_names(conn, "athletes"))
            self.assertIn("retired_json", column_names(conn, "game_state"))
        db = DatabaseManager(db_path=path)
        self.assertEqual(user_version(path), SCHEMA_VERSION)
        with closing(sqlite3.connect(path)) as conn:
            self.assertEqual(conn.execute("SELECT agents_json FROM game_state WHERE id = 1").fetchone(), ("[]",))
            self.assertEqual(conn.execute("SELECT agent_id FROM athletes WHERE id = 1").fetchone(), (None,))
            self.assertIn(("agents_json", "TEXT", 1, "'[]'", 0), columns(conn, "game_state"))
            self.assertIn(("agent_id", "INTEGER", 0, None, 0), columns(conn, "athletes"))
        sentinel_ok(self, path, 17)
        backup = self.backups("v17")[0]
        self.assertEqual(db.last_backup_path, backup)
        self.assertEqual(user_version(backup), 17)
        with closing(sqlite3.connect(backup)) as conn:
            self.assertNotIn("agents_json", column_names(conn, "game_state"))
        sentinel_ok(self, backup, 17)

    def test_a_migrated_save_loads_without_agents_and_the_game_assigns_them(self) -> None:
        from models.agents import agent_of, ensure_agents
        from tests.test_assignments import make_state

        path = self.slot("v18")
        state = make_state(3)
        DatabaseManager(db_path=path).save_game(state)
        loaded = DatabaseManager(db_path=path).load_game()
        self.assertEqual(loaded.agents, [])
        self.assertTrue(all(a.agent_id is None for a in loaded.athletes))
        self.assertEqual(ensure_agents(loaded), len(loaded.athletes))  # come fa `upgrade_legacy_state` al caricamento
        self.assertTrue(all(agent_of(loaded, a) is not None for a in loaded.athletes))

    def test_failed_v17_migration_leaves_the_save_untouched(self) -> None:
        path = make_save(self.slot("v17"), 17)
        before = sha(path)
        broken = {"game_state": [("agents_json", "TEXT NOT NULL DEFAULT '[]'"), ("rotta", "SYNTAX ((")]}
        with mock.patch.dict(MIGRATIONS, {17: broken}):
            with self.assertRaises(dbm.SaveMigrationError):
                DatabaseManager(db_path=path)
        self.assertEqual(sha(path), before)
        self.assertEqual(user_version(path), 17)


class TestMigrationV19RecordBonus(_TmpCase):
    """v18 → v19 (D.2): `athletes.record_bonus` (default 0, nessun bonus)."""

    def test_v18_save_gets_the_column_with_default_and_a_verified_backup(self) -> None:
        self.assertGreaterEqual(SCHEMA_VERSION, 19)
        self.assertIn(18, MIGRATIONS)
        path = make_save(self.slot("v18"), 18)
        with closing(sqlite3.connect(path)) as conn:
            self.assertNotIn("record_bonus", column_names(conn, "athletes"))  # la fixture è davvero v18
            self.assertIn("agent_id", column_names(conn, "athletes"))
        db = DatabaseManager(db_path=path)
        self.assertEqual(user_version(path), SCHEMA_VERSION)
        with closing(sqlite3.connect(path)) as conn:
            self.assertEqual(conn.execute("SELECT record_bonus FROM athletes WHERE id = 1").fetchone(), (0,))
            self.assertIn(("record_bonus", "INTEGER", 1, "0", 0), columns(conn, "athletes"))
        sentinel_ok(self, path, 18)
        backup = self.backups("v18")[0]
        self.assertEqual(db.last_backup_path, backup)
        self.assertEqual(user_version(backup), 18)
        with closing(sqlite3.connect(backup)) as conn:
            self.assertNotIn("record_bonus", column_names(conn, "athletes"))
        sentinel_ok(self, backup, 18)

    def test_a_migrated_save_loads_with_no_bonus(self) -> None:
        from tests.test_assignments import make_state

        path = self.slot("v19")
        state = make_state(3)
        state.athletes[0].record_bonus = 600
        DatabaseManager(db_path=path).save_game(state)
        with closing(sqlite3.connect(path)) as conn:  # come dopo la migrazione: la colonna ha il valore di default
            conn.execute("UPDATE athletes SET record_bonus = 0")
            conn.commit()
        loaded = DatabaseManager(db_path=path).load_game()
        self.assertTrue(all(a.record_bonus == 0 for a in loaded.athletes))

    def test_failed_v18_migration_leaves_the_save_untouched(self) -> None:
        path = make_save(self.slot("v18"), 18)
        before = sha(path)
        broken = {"athletes": [("record_bonus", "INTEGER NOT NULL DEFAULT 0"), ("rotta", "SYNTAX ((")]}
        with mock.patch.dict(MIGRATIONS, {18: broken}):
            with self.assertRaises(dbm.SaveMigrationError):
                DatabaseManager(db_path=path)
        self.assertEqual(sha(path), before)
        self.assertEqual(user_version(path), 18)


class TestMigrationV20MonthlyReports(_TmpCase):
    """v19 → v20 (D.3): `game_state.monthly_report_json` (default `'[]'`, nessun bilancio mensile)."""

    def test_v19_save_gets_the_column_with_default_and_a_verified_backup(self) -> None:
        self.assertGreaterEqual(SCHEMA_VERSION, 20)
        self.assertIn(19, MIGRATIONS)
        path = make_save(self.slot("v19"), 19)
        with closing(sqlite3.connect(path)) as conn:
            self.assertNotIn("monthly_report_json", column_names(conn, "game_state"))  # la fixture è davvero v19
            self.assertIn("agents_json", column_names(conn, "game_state"))
        db = DatabaseManager(db_path=path)
        self.assertEqual(user_version(path), SCHEMA_VERSION)
        with closing(sqlite3.connect(path)) as conn:
            self.assertEqual(conn.execute("SELECT monthly_report_json FROM game_state WHERE id = 1").fetchone(), ("[]",))
            self.assertIn(("monthly_report_json", "TEXT", 1, "'[]'", 0), columns(conn, "game_state"))
        sentinel_ok(self, path, 19)
        backup = self.backups("v19")[0]
        self.assertEqual(db.last_backup_path, backup)
        self.assertEqual(user_version(backup), 19)
        with closing(sqlite3.connect(backup)) as conn:
            self.assertNotIn("monthly_report_json", column_names(conn, "game_state"))
        sentinel_ok(self, backup, 19)

    def test_a_migrated_save_loads_with_no_monthly_reports(self) -> None:
        from tests.test_assignments import make_state

        path = self.slot("v20")
        DatabaseManager(db_path=path).save_game(make_state(3))
        loaded = DatabaseManager(db_path=path).load_game()
        self.assertEqual(loaded.monthly_reports, [])

    def test_failed_v19_migration_leaves_the_save_untouched(self) -> None:
        path = make_save(self.slot("v19"), 19)
        before = sha(path)
        broken = {"game_state": [("monthly_report_json", "TEXT NOT NULL DEFAULT '[]'"), ("rotta", "SYNTAX ((")]}
        with mock.patch.dict(MIGRATIONS, {19: broken}):
            with self.assertRaises(dbm.SaveMigrationError):
                DatabaseManager(db_path=path)
        self.assertEqual(sha(path), before)
        self.assertEqual(user_version(path), 19)


class TestMigrationV21PrepWeeks(_TmpCase):
    """v20 → v21 (avvio senza atleti, Q32): `game_state.prep_weeks` (default 0 = calendario di sempre, senza Preparazione)."""

    def test_v20_save_gets_the_column_with_default_and_a_verified_backup(self) -> None:
        self.assertGreaterEqual(SCHEMA_VERSION, 21)
        self.assertIn(20, MIGRATIONS)
        path = make_save(self.slot("v20"), 20)
        with closing(sqlite3.connect(path)) as conn:
            self.assertNotIn("prep_weeks", column_names(conn, "game_state"))  # la fixture è davvero v20
            self.assertIn("monthly_report_json", column_names(conn, "game_state"))
        db = DatabaseManager(db_path=path)
        self.assertEqual(user_version(path), SCHEMA_VERSION)
        with closing(sqlite3.connect(path)) as conn:
            self.assertEqual(conn.execute("SELECT prep_weeks FROM game_state WHERE id = 1").fetchone(), (0,))
            self.assertIn(("prep_weeks", "INTEGER", 1, "0", 0), columns(conn, "game_state"))
        sentinel_ok(self, path, 20)
        backup = self.backups("v20")[0]
        self.assertEqual(db.last_backup_path, backup)
        self.assertEqual(user_version(backup), 20)
        with closing(sqlite3.connect(backup)) as conn:
            self.assertNotIn("prep_weeks", column_names(conn, "game_state"))
        sentinel_ok(self, backup, 20)

    def test_a_migrated_save_keeps_the_old_calendar(self) -> None:
        from tests.test_assignments import make_state

        path = self.slot("v21")
        DatabaseManager(db_path=path).save_game(make_state(3))
        loaded = DatabaseManager(db_path=path).load_game()
        self.assertEqual(loaded.prep_weeks, 0)
        self.assertEqual(loaded.season_length, 36)

    def test_prep_weeks_and_the_empty_squad_roundtrip(self) -> None:
        from models.entities import GameState, SeasonPhase

        path = self.slot("empty")
        state = GameState(game_mode="career", prep_weeks=8, season_phase=SeasonPhase.PREPARAZIONE)
        DatabaseManager(db_path=path).save_game(state)
        loaded = DatabaseManager(db_path=path).load_game()
        self.assertEqual((loaded.prep_weeks, loaded.season_phase), (8, SeasonPhase.PREPARAZIONE))
        self.assertEqual((loaded.athletes, loaded.coaches), ([], []))

    def test_failed_v20_migration_leaves_the_save_untouched(self) -> None:
        path = make_save(self.slot("v20"), 20)
        before = sha(path)
        broken = {"game_state": [("prep_weeks", "INTEGER NOT NULL DEFAULT 0"), ("rotta", "SYNTAX ((")]}
        with mock.patch.dict(MIGRATIONS, {20: broken}):
            with self.assertRaises(dbm.SaveMigrationError):
                DatabaseManager(db_path=path)
        self.assertEqual(sha(path), before)
        self.assertEqual(user_version(path), 20)


class TestMigrationV22StaffAttributes(_TmpCase):
    """v21 → v22 (E.1): `staff.attributes_json` (default `'{}'` = tutti gli attributi al riferimento, l'effetto di prima)."""

    def test_v21_save_gets_the_column_with_default_and_a_verified_backup(self) -> None:
        self.assertGreaterEqual(SCHEMA_VERSION, 22)
        self.assertIn(21, MIGRATIONS)
        path = make_save(self.slot("v21"), 21)
        with closing(sqlite3.connect(path)) as conn:
            self.assertNotIn("attributes_json", column_names(conn, "staff"))  # la fixture è davvero v21
            self.assertIn("prep_weeks", column_names(conn, "game_state"))
            _insert(conn, "staff", id=4, name="Dott.ssa Vecchia", role="Fisioterapista", skill=4, weekly_cost=300,
                    hired=1, description="d")
            conn.commit()
        db = DatabaseManager(db_path=path)
        self.assertEqual(user_version(path), SCHEMA_VERSION)
        with closing(sqlite3.connect(path)) as conn:
            self.assertEqual(conn.execute("SELECT attributes_json FROM staff WHERE id = 4").fetchone(), ("{}",))
            self.assertIn(("attributes_json", "TEXT", 1, "'{}'", 0), columns(conn, "staff"))
        sentinel_ok(self, path, 21)
        backup = self.backups("v21")[0]
        self.assertEqual(db.last_backup_path, backup)
        self.assertEqual(user_version(backup), 21)
        with closing(sqlite3.connect(backup)) as conn:
            self.assertNotIn("attributes_json", column_names(conn, "staff"))
        sentinel_ok(self, backup, 21)

    def test_old_staff_row_loads_with_every_attribute_at_reference(self) -> None:
        from models.entities import STAFF_ATTR_REF, StaffRole
        from models.generator import create_initial_staff
        from tests.test_assignments import make_state

        path = self.slot("v21")
        state = make_state(3)
        state.staff = create_initial_staff()
        next(m for m in state.staff if m.id == 5).hired = True  # il dottor Conti, il medico originale
        DatabaseManager(db_path=path).save_game(state)
        with closing(sqlite3.connect(path)) as conn:  # lo riporta a com'era un salvataggio v21: senza la colonna
            conn.execute("ALTER TABLE staff DROP COLUMN attributes_json")
            conn.execute("ALTER TABLE game_state DROP COLUMN facilities_json")  # v23, successiva
            conn.execute("ALTER TABLE game_state DROP COLUMN academy_level")  # v24, successiva
            conn.execute("ALTER TABLE game_state DROP COLUMN scout_json")  # v24, successiva
            conn.execute("ALTER TABLE athletes DROP COLUMN relationships_json")  # v25, successiva
            conn.execute("ALTER TABLE athletes DROP COLUMN history_json")  # v26, successiva
            conn.execute("ALTER TABLE athletes DROP COLUMN pb_json")  # v27, successiva
            conn.execute("PRAGMA user_version = 21")
            conn.commit()
        loaded = DatabaseManager(db_path=path).load_game()  # migra v21 → v22
        self.assertEqual(user_version(path), SCHEMA_VERSION)
        doctor = next(s for s in loaded.staff if s.id == 5)
        self.assertEqual(doctor.role, StaffRole.DOCTOR)
        self.assertTrue(doctor.hired)
        self.assertEqual(doctor.attributes, {"diagnosi": STAFF_ATTR_REF, "prevenzione": STAFF_ATTR_REF})

    def test_attributes_roundtrip_and_corrupt_json_falls_back_to_reference(self) -> None:
        from models.entities import STAFF_ATTR_REF
        from tests.test_assignments import make_state
        from models.generator import create_initial_staff

        path = self.slot("v22")
        state = make_state(3)
        state.staff = create_initial_staff()
        state.staff[0].attributes = {"competenza": 18, "recupero": 6}
        DatabaseManager(db_path=path).save_game(state)
        loaded = DatabaseManager(db_path=path).load_game()
        self.assertEqual(loaded.staff[0].attributes, {"competenza": 18, "recupero": 6})
        self.assertEqual(loaded.staff[1].attributes, {"diagnosi": STAFF_ATTR_REF, "prevenzione": STAFF_ATTR_REF})
        with closing(sqlite3.connect(path)) as conn:
            conn.execute("UPDATE staff SET attributes_json = 'non json' WHERE id = ?", (state.staff[2].id,))
            conn.commit()
        again = DatabaseManager(db_path=path).load_game()
        self.assertEqual(again.staff[2].attributes, {"motivazione": STAFF_ATTR_REF, "pressione": STAFF_ATTR_REF})

    def test_a_save_from_before_the_staff_market_gets_the_other_candidates(self) -> None:
        from models.generator import create_initial_staff
        from tests.test_assignments import make_state

        path = self.slot("v21")
        state = make_state(3)
        state.staff = [m for m in create_initial_staff() if m.id in (4, 5, 6)]  # i soli 3 candidati di prima
        state.staff[0].hired = True
        DatabaseManager(db_path=path).save_game(state)
        loaded = DatabaseManager(db_path=path).load_game()
        self.assertEqual(len(loaded.staff), 9)
        self.assertEqual([m.id for m in loaded.staff if m.hired], [4])  # la scelta fatta resta
        DatabaseManager(db_path=path).save_game(loaded)  # e il mercato completo si salva e ricarica uguale
        again = DatabaseManager(db_path=path).load_game()
        self.assertEqual([m.id for m in again.staff], [m.id for m in loaded.staff])

    def test_failed_v21_migration_leaves_the_save_untouched(self) -> None:
        path = make_save(self.slot("v21"), 21)
        before = sha(path)
        broken = {"staff": [("attributes_json", "TEXT NOT NULL DEFAULT '{}'"), ("rotta", "SYNTAX ((")]}
        with mock.patch.dict(MIGRATIONS, {21: broken}):
            with self.assertRaises(dbm.SaveMigrationError):
                DatabaseManager(db_path=path)
        self.assertEqual(sha(path), before)
        self.assertEqual(user_version(path), 21)


class TestMigrationV27PersonalBests(_TmpCase):
    """v26 → v27 (Q43): `athletes.pb_json` (default `'{}'` = nessun primato per gara). Le colonne `personal_best*` restano, inutilizzate."""

    def test_v26_save_gets_the_column_with_default_and_a_verified_backup(self) -> None:
        self.assertGreaterEqual(SCHEMA_VERSION, 27)
        self.assertIn(26, MIGRATIONS)
        path = make_save(self.slot("v26"), 26)
        with closing(sqlite3.connect(path)) as conn:
            self.assertNotIn("pb_json", column_names(conn, "athletes"))  # la fixture è davvero v26
            self.assertIn("history_json", column_names(conn, "athletes"))
        db = DatabaseManager(db_path=path)
        self.assertEqual(user_version(path), SCHEMA_VERSION)
        with closing(sqlite3.connect(path)) as conn:
            self.assertIn(("pb_json", "TEXT", 1, "'{}'", 0), columns(conn, "athletes"))
            self.assertIn("personal_best", column_names(conn, "athletes"))  # nessun DROP di dati
        sentinel_ok(self, path, 26)
        backup = self.backups("v26")[0]
        self.assertEqual(db.last_backup_path, backup)
        self.assertEqual(user_version(backup), 26)
        with closing(sqlite3.connect(backup)) as conn:
            self.assertNotIn("pb_json", column_names(conn, "athletes"))
        sentinel_ok(self, backup, 26)

    def test_old_save_loads_without_personal_bests_and_they_roundtrip(self) -> None:
        from models.personal_bests import record_best
        from tests.test_assignments import make_state

        path = self.slot("v26")
        state = make_state(2)
        DatabaseManager(db_path=path).save_game(state)
        with closing(sqlite3.connect(path)) as conn:  # lo riporta a com'era un salvataggio v26: senza la colonna
            conn.execute("ALTER TABLE athletes DROP COLUMN pb_json")
            conn.execute("PRAGMA user_version = 26")
            conn.commit()
        loaded = DatabaseManager(db_path=path).load_game()  # migra v26 → v27
        self.assertEqual(user_version(path), SCHEMA_VERSION)
        self.assertTrue(all(a.pb_log == {} for a in loaded.athletes))  # nessun primato inventato: si fissano con le prime gare
        record_best(loaded.athletes[0], "100m", 11.2, "11.20s", 1, 4, "Meeting A")
        record_best(loaded.athletes[0], "100m", 11.0, "11.00s", 1, 8, "Meeting B")
        DatabaseManager(db_path=path).save_game(loaded)
        again = DatabaseManager(db_path=path).load_game()
        self.assertEqual(again.athletes[0].pb_log, loaded.athletes[0].pb_log)
        self.assertEqual(again.athletes[1].pb_log, {})

    def test_failed_v26_migration_leaves_the_save_untouched(self) -> None:
        path = make_save(self.slot("v26"), 26)
        before = sha(path)
        broken = {"athletes": [("pb_json", "TEXT NOT NULL DEFAULT '{}'"), ("rotta", "SYNTAX ((")]}
        with mock.patch.dict(MIGRATIONS, {26: broken}):
            with self.assertRaises(dbm.SaveMigrationError):
                DatabaseManager(db_path=path)
        self.assertEqual(sha(path), before)


if __name__ == "__main__":
    unittest.main()


class TestMigrationV23Facilities(_TmpCase):
    """v22 → v23 (E.2): `game_state.facilities_json` (default `'{}'` = nessun impianto avanzato, l'effetto di prima)."""

    def test_v22_save_gets_the_column_with_default_and_a_verified_backup(self) -> None:
        self.assertGreaterEqual(SCHEMA_VERSION, 23)
        self.assertIn(22, MIGRATIONS)
        path = make_save(self.slot("v22"), 22)
        with closing(sqlite3.connect(path)) as conn:
            self.assertNotIn("facilities_json", column_names(conn, "game_state"))  # la fixture è davvero v22
            self.assertIn("attributes_json", column_names(conn, "staff"))
        db = DatabaseManager(db_path=path)
        self.assertEqual(user_version(path), SCHEMA_VERSION)
        with closing(sqlite3.connect(path)) as conn:
            self.assertIn(("facilities_json", "TEXT", 1, "'{}'", 0), columns(conn, "game_state"))
        sentinel_ok(self, path, 22)
        backup = self.backups("v22")[0]
        self.assertEqual(db.last_backup_path, backup)
        self.assertEqual(user_version(backup), 22)
        with closing(sqlite3.connect(backup)) as conn:
            self.assertNotIn("facilities_json", column_names(conn, "game_state"))
        sentinel_ok(self, backup, 22)

    def test_old_save_loads_without_facilities_and_they_roundtrip_once_bought(self) -> None:
        from models.entities import FACILITY_MEDICAL, FACILITY_VIDEO
        from tests.test_assignments import make_state

        path = self.slot("v22")
        state = make_state(3)
        DatabaseManager(db_path=path).save_game(state)
        with closing(sqlite3.connect(path)) as conn:  # lo riporta a com'era un salvataggio v22: senza la colonna
            conn.execute("ALTER TABLE game_state DROP COLUMN facilities_json")
            conn.execute("ALTER TABLE game_state DROP COLUMN academy_level")  # v24, successiva
            conn.execute("ALTER TABLE game_state DROP COLUMN scout_json")  # v24, successiva
            conn.execute("ALTER TABLE athletes DROP COLUMN relationships_json")  # v25, successiva
            conn.execute("ALTER TABLE athletes DROP COLUMN history_json")  # v26, successiva
            conn.execute("ALTER TABLE athletes DROP COLUMN pb_json")  # v27, successiva
            conn.execute("PRAGMA user_version = 22")
            conn.commit()
        loaded = DatabaseManager(db_path=path).load_game()  # migra v22 → v23
        self.assertEqual(user_version(path), SCHEMA_VERSION)
        self.assertEqual(loaded.facilities, {})
        loaded.facilities = {FACILITY_MEDICAL: 1, FACILITY_VIDEO: 1}
        DatabaseManager(db_path=path).save_game(loaded)
        self.assertEqual(DatabaseManager(db_path=path).load_game().facilities, {FACILITY_MEDICAL: 1, FACILITY_VIDEO: 1})

    def test_corrupt_or_unknown_facilities_load_as_the_safe_value(self) -> None:
        from models.entities import FACILITY_WEIGHTS
        from tests.test_assignments import make_state

        path = self.slot("v23")
        DatabaseManager(db_path=path).save_game(make_state(3))
        with closing(sqlite3.connect(path)) as conn:
            conn.execute("UPDATE game_state SET facilities_json = 'non json'")
            conn.commit()
        self.assertEqual(DatabaseManager(db_path=path).load_game().facilities, {})
        with closing(sqlite3.connect(path)) as conn:
            conn.execute("UPDATE game_state SET facilities_json = ?", ('{"palestra_pesi": 1, "ignoto": 1}',))
            conn.commit()
        self.assertEqual(DatabaseManager(db_path=path).load_game().facilities, {FACILITY_WEIGHTS: 1})

    def test_failed_v22_migration_leaves_the_save_untouched(self) -> None:
        path = make_save(self.slot("v22"), 22)
        before = sha(path)
        broken = {"game_state": [("facilities_json", "TEXT NOT NULL DEFAULT '{}'"), ("rotta", "SYNTAX ((")]}
        with mock.patch.dict(MIGRATIONS, {22: broken}):
            with self.assertRaises(dbm.SaveMigrationError):
                DatabaseManager(db_path=path)
        self.assertEqual(sha(path), before)


class TestMigrationV24Giovanili(_TmpCase):
    """v23 → v24 (E.3): `game_state.academy_level` (0 = il vivaio di prima) e `scout_json` (`'{}'` = nessuno scout)."""

    def test_v23_save_gets_both_columns_with_defaults_and_a_verified_backup(self) -> None:
        self.assertGreaterEqual(SCHEMA_VERSION, 24)
        self.assertIn(23, MIGRATIONS)
        path = make_save(self.slot("v23"), 23)
        with closing(sqlite3.connect(path)) as conn:
            self.assertNotIn("academy_level", column_names(conn, "game_state"))  # la fixture è davvero v23
            self.assertIn("facilities_json", column_names(conn, "game_state"))
        db = DatabaseManager(db_path=path)
        self.assertEqual(user_version(path), SCHEMA_VERSION)
        with closing(sqlite3.connect(path)) as conn:
            self.assertIn(("academy_level", "INTEGER", 1, "0", 0), columns(conn, "game_state"))
            self.assertIn(("scout_json", "TEXT", 1, "'{}'", 0), columns(conn, "game_state"))
        sentinel_ok(self, path, 23)
        backup = self.backups("v23")[0]
        self.assertEqual(db.last_backup_path, backup)
        self.assertEqual(user_version(backup), 23)
        with closing(sqlite3.connect(backup)) as conn:
            self.assertNotIn("scout_json", column_names(conn, "game_state"))
        sentinel_ok(self, backup, 23)

    def test_old_save_loads_without_academy_or_scout_and_both_roundtrip(self) -> None:
        from models.scouting import scout_candidates
        from tests.test_assignments import make_state

        path = self.slot("v23")
        DatabaseManager(db_path=path).save_game(make_state(3))
        with closing(sqlite3.connect(path)) as conn:  # lo riporta a com'era un salvataggio v23: senza le colonne
            conn.execute("ALTER TABLE game_state DROP COLUMN academy_level")
            conn.execute("ALTER TABLE game_state DROP COLUMN scout_json")
            conn.execute("ALTER TABLE athletes DROP COLUMN relationships_json")  # v25, successiva
            conn.execute("ALTER TABLE athletes DROP COLUMN history_json")  # v26, successiva
            conn.execute("ALTER TABLE athletes DROP COLUMN pb_json")  # v27, successiva
            conn.execute("PRAGMA user_version = 23")
            conn.commit()
        loaded = DatabaseManager(db_path=path).load_game()  # migra v23 → v24
        self.assertEqual(user_version(path), SCHEMA_VERSION)
        self.assertEqual((loaded.academy_level, loaded.scout), (0, None))
        loaded.academy_level = 3
        loaded.scout = scout_candidates()[2]
        DatabaseManager(db_path=path).save_game(loaded)
        again = DatabaseManager(db_path=path).load_game()
        self.assertEqual((again.academy_level, again.scout), (3, scout_candidates()[2]))

    def test_corrupt_scout_and_out_of_range_academy_load_as_safe_values(self) -> None:
        from tests.test_assignments import make_state

        path = self.slot("v24")
        DatabaseManager(db_path=path).save_game(make_state(3))
        for raw in ("non json", "[1]", '{"id": "x"}', '{"id": 1}'):
            with closing(sqlite3.connect(path)) as conn:
                conn.execute("UPDATE game_state SET scout_json = ?, academy_level = 99", (raw,))
                conn.commit()
            loaded = DatabaseManager(db_path=path).load_game()
            self.assertIsNone(loaded.scout, raw)
            self.assertEqual(loaded.academy_level, 5)  # fuori scala: portato al massimo, mai oltre

    def test_failed_v23_migration_leaves_the_save_untouched(self) -> None:
        path = make_save(self.slot("v23"), 23)
        before = sha(path)
        broken = {"game_state": [("academy_level", "INTEGER NOT NULL DEFAULT 0"), ("rotta", "SYNTAX ((")]}
        with mock.patch.dict(MIGRATIONS, {23: broken}):
            with self.assertRaises(dbm.SaveMigrationError):
                DatabaseManager(db_path=path)
        self.assertEqual(sha(path), before)


class TestMigrationV25Relationships(_TmpCase):
    """v24 → v25 (F.3): `athletes.relationships_json` (default `'{}'` = nessuna relazione, si generano al primo tick)."""

    def test_v24_save_gets_the_column_with_default_and_a_verified_backup(self) -> None:
        self.assertGreaterEqual(SCHEMA_VERSION, 25)
        self.assertIn(24, MIGRATIONS)
        path = make_save(self.slot("v24"), 24)
        with closing(sqlite3.connect(path)) as conn:
            self.assertNotIn("relationships_json", column_names(conn, "athletes"))  # la fixture è davvero v24
            self.assertIn("scout_json", column_names(conn, "game_state"))
        db = DatabaseManager(db_path=path)
        self.assertEqual(user_version(path), SCHEMA_VERSION)
        with closing(sqlite3.connect(path)) as conn:
            self.assertIn(("relationships_json", "TEXT", 1, "'{}'", 0), columns(conn, "athletes"))
        sentinel_ok(self, path, 24)
        backup = self.backups("v24")[0]
        self.assertEqual(db.last_backup_path, backup)
        self.assertEqual(user_version(backup), 24)
        with closing(sqlite3.connect(backup)) as conn:
            self.assertNotIn("relationships_json", column_names(conn, "athletes"))
        sentinel_ok(self, backup, 24)

    def test_old_save_loads_without_relationships_and_they_roundtrip(self) -> None:
        from tests.test_assignments import make_state

        path = self.slot("v24")
        state = make_state(3)
        DatabaseManager(db_path=path).save_game(state)
        with closing(sqlite3.connect(path)) as conn:  # lo riporta a com'era un salvataggio v24: senza la colonna
            conn.execute("ALTER TABLE athletes DROP COLUMN relationships_json")
            conn.execute("ALTER TABLE athletes DROP COLUMN history_json")  # v26, successiva
            conn.execute("ALTER TABLE athletes DROP COLUMN pb_json")  # v27, successiva
            conn.execute("PRAGMA user_version = 24")
            conn.commit()
        loaded = DatabaseManager(db_path=path).load_game()  # migra v24 → v25
        self.assertEqual(user_version(path), SCHEMA_VERSION)
        self.assertTrue(all(a.relationships == {} for a in loaded.athletes))
        a, b = loaded.athletes[0], loaded.athletes[1]
        a.relationships = {b.id: 55, 999: -40}
        b.relationships = {a.id: 55, 999: 0}
        DatabaseManager(db_path=path).save_game(loaded)
        again = DatabaseManager(db_path=path).load_game()
        self.assertEqual(again.athletes[0].relationships, {b.id: 55, 999: -40})
        self.assertEqual(again.athletes[1].relationships, {a.id: 55, 999: 0})  # lo zero resta: «già incontrati»

    def test_corrupt_relationships_load_as_none_and_bad_entries_are_dropped(self) -> None:
        from tests.test_assignments import make_state

        path = self.slot("v25")
        DatabaseManager(db_path=path).save_game(make_state(3))
        with closing(sqlite3.connect(path)) as conn:
            conn.execute("UPDATE athletes SET relationships_json = 'non json'")
            conn.commit()
        self.assertTrue(all(a.relationships == {} for a in DatabaseManager(db_path=path).load_game().athletes))
        with closing(sqlite3.connect(path)) as conn:
            conn.execute("UPDATE athletes SET relationships_json = ?", ('{"2": 500, "x": 5, "3": "boh", "4": -999}',))
            conn.commit()
        for a in DatabaseManager(db_path=path).load_game().athletes:
            self.assertEqual(a.relationships, {2: 100, 4: -100})

    def test_failed_v24_migration_leaves_the_save_untouched(self) -> None:
        path = make_save(self.slot("v24"), 24)
        before = sha(path)
        broken = {"athletes": [("relationships_json", "TEXT NOT NULL DEFAULT '{}'"), ("rotta", "SYNTAX ((")]}
        with mock.patch.dict(MIGRATIONS, {24: broken}):
            with self.assertRaises(dbm.SaveMigrationError):
                DatabaseManager(db_path=path)
        self.assertEqual(sha(path), before)


class TestMigrationV26History(_TmpCase):
    """v25 → v26 (G.1/G.2): `athletes.history_json` (default `'{}'` = nessuno storico, si riempie giocando)."""

    def test_v25_save_gets_the_column_with_default_and_a_verified_backup(self) -> None:
        self.assertGreaterEqual(SCHEMA_VERSION, 26)
        self.assertIn(25, MIGRATIONS)
        path = make_save(self.slot("v25"), 25)
        with closing(sqlite3.connect(path)) as conn:
            self.assertNotIn("history_json", column_names(conn, "athletes"))  # la fixture è davvero v25
            self.assertIn("relationships_json", column_names(conn, "athletes"))
        db = DatabaseManager(db_path=path)
        self.assertEqual(user_version(path), SCHEMA_VERSION)
        with closing(sqlite3.connect(path)) as conn:
            self.assertIn(("history_json", "TEXT", 1, "'{}'", 0), columns(conn, "athletes"))
        sentinel_ok(self, path, 25)
        backup = self.backups("v25")[0]
        self.assertEqual(db.last_backup_path, backup)
        self.assertEqual(user_version(backup), 25)
        with closing(sqlite3.connect(backup)) as conn:
            self.assertNotIn("history_json", column_names(conn, "athletes"))
        sentinel_ok(self, backup, 25)

    def test_old_save_loads_without_history_and_it_roundtrips(self) -> None:
        from tests.test_assignments import make_state

        path = self.slot("v25")
        state = make_state(2)
        DatabaseManager(db_path=path).save_game(state)
        with closing(sqlite3.connect(path)) as conn:  # lo riporta a com'era un salvataggio v25: senza la colonna
            conn.execute("ALTER TABLE athletes DROP COLUMN history_json")
            conn.execute("ALTER TABLE athletes DROP COLUMN pb_json")  # v27, successiva
            conn.execute("PRAGMA user_version = 25")
            conn.commit()
        loaded = DatabaseManager(db_path=path).load_game()  # migra v25 → v26
        self.assertEqual(user_version(path), SCHEMA_VERSION)
        self.assertTrue(all(a.history == {} for a in loaded.athletes))
        loaded.athletes[0].history = {
            "weekly": [[60, 20, 0], [62, 25, 1]],
            "results": [{"season": 1, "week": 4, "event": "100m", "gender": "M", "place": 2, "of": 8, "mark": "11.20", "pb": True, "out": False}],
        }
        DatabaseManager(db_path=path).save_game(loaded)
        again = DatabaseManager(db_path=path).load_game()
        self.assertEqual(again.athletes[0].history, loaded.athletes[0].history)
        self.assertEqual(again.athletes[1].history, {})

    def test_failed_v25_migration_leaves_the_save_untouched(self) -> None:
        path = make_save(self.slot("v25"), 25)
        before = sha(path)
        broken = {"athletes": [("history_json", "TEXT NOT NULL DEFAULT '{}'"), ("rotta", "SYNTAX ((")]}
        with mock.patch.dict(MIGRATIONS, {25: broken}):
            with self.assertRaises(dbm.SaveMigrationError):
                DatabaseManager(db_path=path)
        self.assertEqual(sha(path), before)
