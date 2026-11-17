extends Node
## MODEL - accesso in sola lettura ai risultati pre-calcolati (SQLite via godot-sqlite).
##
## Richiede il plugin GDExtension "godot-sqlite" (classe globale `SQLite`) in res://addons/godot-sqlite/.
## Percorso del DB: variabile d'ambiente TEF_RACE_DB, altrimenti user://race_results.db.
## Se il file non esiste viene creato con schema.sql + demo_seed.sql (solo per sviluppo).

const DEFAULT_DB_PATH: String = "user://race_results.db"
const SCHEMA_PATH: String = "res://data/schema.sql"
const DEMO_SEED_PATH: String = "res://data/demo_seed.sql"

var _db: SQLite = null
var db_path: String = DEFAULT_DB_PATH


func _ready() -> void:
	var env_path: String = OS.get_environment("TEF_RACE_DB")
	if not env_path.is_empty():
		db_path = env_path
	if not FileAccess.file_exists(db_path):
		push_warning("DatabaseManager: %s non esiste, creo il DB dimostrativo." % db_path)
		_create_demo_database()
	open_database(db_path)


func _exit_tree() -> void:
	close_database()


func open_database(path: String) -> bool:
	close_database()
	_db = SQLite.new()
	_db.path = path
	_db.read_only = true
	_db.foreign_keys = true
	if not _db.open_db():
		push_error("DatabaseManager: impossibile aprire %s (%s)" % [path, _db.error_message])
		_db = null
		return false
	db_path = path
	return true


func close_database() -> void:
	if _db != null:
		_db.close_db()
		_db = null


func is_open() -> bool:
	return _db != null


## Metadati della gara (evento, meeting, vento). Dizionario vuoto se non esiste.
func get_race_info(race_id: int) -> Dictionary:
	var rows: Array[Dictionary] = _select(
		"SELECT race_id, event_name, meet_name, distance_m, wind_ms FROM races WHERE race_id = ?;",
		[race_id])
	return rows[0] if rows.size() > 0 else {}


## Corridori della gara ordinati per corsia. Righe con dati incoerenti vengono scartate.
func get_race_runners(race_id: int) -> Array[RunnerData]:
	var result: Array[RunnerData] = []
	var rows: Array[Dictionary] = _select(
		"SELECT lane, athlete_name, team_name, is_player, reaction_time, final_time, status "
		+ "FROM race_results WHERE race_id = ? ORDER BY lane;", [race_id])
	for row: Dictionary in rows:
		var runner: RunnerData = RunnerData.from_row(row)
		if runner.is_valid():
			result.append(runner)
		else:
			push_warning("DatabaseManager: riga scartata (corsia %s): tempi incoerenti." % str(row.get("lane")))
	return result


func _select(sql: String, bindings: Array) -> Array[Dictionary]:
	var rows: Array[Dictionary] = []
	if _db == null:
		push_error("DatabaseManager: database non aperto.")
		return rows
	if not _db.query_with_bindings(sql, bindings):
		push_error("DatabaseManager: query fallita (%s)" % _db.error_message)
		return rows
	for row: Variant in _db.query_result:
		rows.append(row as Dictionary)
	return rows


# --- solo sviluppo: DB dimostrativo -------------------------------------------------------------

func _create_demo_database() -> void:
	var writer: SQLite = SQLite.new()
	writer.path = db_path
	if not writer.open_db():
		push_error("DatabaseManager: impossibile creare %s" % db_path)
		return
	for script_path: String in [SCHEMA_PATH, DEMO_SEED_PATH]:
		var text: String = FileAccess.get_file_as_string(script_path)
		for statement: String in text.split(";", false):
			var sql: String = statement.strip_edges()
			if sql.is_empty() or _only_comments(sql):
				continue
			if not writer.query(sql + ";"):
				push_error("DatabaseManager: %s -> %s" % [script_path, writer.error_message])
	writer.close_db()


func _only_comments(sql: String) -> bool:
	for line: String in sql.split("\n", false):
		var stripped: String = line.strip_edges()
		if not stripped.is_empty() and not stripped.begins_with("--"):
			return false
	return true
