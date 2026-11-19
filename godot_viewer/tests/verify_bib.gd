extends SceneTree
## Verifica headless dei pettorali: lettura da un DB con e senza la colonna `bib` e proporzioni della stampa.
##   godot --headless --path godot_viewer -s res://tests/verify_bib.gd
## Esce con codice 0 se tutto torna, 1 altrimenti.

var _failures: int = 0


func _check(cond: bool, what: String) -> void:
	print(("OK    " if cond else "FAIL  ") + what)
	if not cond:
		_failures += 1


func _make_db(path: String, with_bib: bool) -> void:
	DirAccess.remove_absolute(path)
	var w: SQLite = SQLite.new()
	w.path = path
	if not w.open_db():
		_check(false, "creato %s" % path)
		return
	w.query("CREATE TABLE races (race_id INTEGER PRIMARY KEY, event_name TEXT NOT NULL, meet_name TEXT NOT NULL, distance_m REAL NOT NULL DEFAULT 100, wind_ms REAL NOT NULL DEFAULT 0);")
	var bib_col: String = ", bib INTEGER NOT NULL DEFAULT 0" if with_bib else ""
	w.query("CREATE TABLE race_results (race_id INTEGER NOT NULL, lane INTEGER NOT NULL, athlete_name TEXT NOT NULL, team_name TEXT NOT NULL DEFAULT '', gender TEXT NOT NULL DEFAULT 'M', is_player INTEGER NOT NULL DEFAULT 0, reaction_time REAL NOT NULL, final_time REAL NOT NULL, status TEXT NOT NULL DEFAULT 'OK'%s, PRIMARY KEY (race_id, lane));" % bib_col)
	w.query("INSERT INTO races (race_id, event_name, meet_name) VALUES (1, '100m', 'Prova');")
	for lane in range(1, 4):
		if with_bib:
			w.query("INSERT INTO race_results (race_id, lane, athlete_name, team_name, reaction_time, final_time, bib) VALUES (1, %d, 'Atleta %d', 'Club', 0.15, %.2f, %d);" % [lane, lane, 9.9 + lane * 0.1, 100 + lane * 111])
		else:
			w.query("INSERT INTO race_results (race_id, lane, athlete_name, team_name, reaction_time, final_time) VALUES (1, %d, 'Atleta %d', 'Club', 0.15, %.2f);" % [lane, lane, 9.9 + lane * 0.1])
	w.close_db()


func _process(_delta: float) -> bool:
	var dm: Node = root.get_node("DatabaseManager")
	var dir: String = ProjectSettings.globalize_path("user://")
	var legacy: String = dir.path_join("bib_test_legacy.db")
	var fresh: String = dir.path_join("bib_test_fresh.db")
	_make_db(legacy, false)
	_make_db(fresh, true)

	_check(dm.open_database(fresh), "DB con la colonna bib aperto")
	var with_bib: Array[RunnerData] = dm.get_race_runners(1)
	_check(with_bib.size() == 3, "3 corridori letti")
	_check(with_bib.map(func(r: RunnerData) -> int: return r.bib) == [211, 322, 433], "pettorali letti dal DB: %s" % str(with_bib.map(func(r: RunnerData) -> int: return r.bib)))
	_check(with_bib.all(func(r: RunnerData) -> bool: return r.is_valid()), "corridori validi")

	_check(dm.open_database(legacy), "DB vecchio (senza colonna bib) aperto")
	var without: Array[RunnerData] = dm.get_race_runners(1)
	_check(without.size() == 3 and without.all(func(r: RunnerData) -> bool: return r.bib == 0 and r.is_valid()),
		"DB vecchio: letto senza errori, pettorale 0 (= nessuno)")

	# La stampa: foglio entro ±0,06 altezze corporee (oltre il busto gira di lato e il disegno si taglia), nella fascia della canotta.
	var rect: Vector4 = BibPrint.rect()
	_check(rect.z <= 0.12 + 1e-6 and rect.z > 0.05, "foglio largo %.3f altezze corporee (<= 0,12)" % rect.z)
	_check(rect.y - rect.w * 0.5 >= 0.60 and rect.y + rect.w * 0.5 <= 0.82, "foglio dentro la fascia della canotta (0,60-0,82)")
	_check(is_equal_approx(rect.z / rect.w, float(BibPrint.SIZE.x) / float(BibPrint.SIZE.y)), "proporzioni del foglio = proporzioni della texture")

	DirAccess.remove_absolute(legacy)
	DirAccess.remove_absolute(fresh)
	print("RISULTATO: " + ("TUTTO OK" if _failures == 0 else "%d FALLIMENTI" % _failures))
	quit(0 if _failures == 0 else 1)
	return true
