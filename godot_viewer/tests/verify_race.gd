extends SceneTree
## Verifica headless del modello e del controller (nessuna scena):
##   godot --headless --path godot_viewer -s res://tests/verify_race.gd
## Esce con codice 0 se tutto torna, 1 altrimenti.

var _failures: int = 0
var _started: bool = false
var _finish_order: Array[String] = []
var _announced: bool = false


func _check(cond: bool, what: String) -> void:
	print(("OK    " if cond else "FAIL  ") + what)
	if not cond:
		_failures += 1


func _setup() -> void:
	var rc: Node = root.get_node("RaceController")
	var db: Node = root.get_node("DatabaseManager")
	_check(db.is_open(), "database aperto")
	_check(rc.load_race(1), "gara 1 caricata")
	var runners: Array[RunnerData] = rc.runners
	_check(runners.size() == 8, "8 corridori (trovati %d)" % runners.size())

	# Modello puro: arrivo esatto a 100 m al tempo ufficiale, curva monotona.
	for r: RunnerData in runners:
		var s: Vector2 = RaceMotion.state_at(r.final_time, r.reaction_time, r.final_time)
		_check(is_equal_approx(s.x, 100.0), "%s: %.6f m a %.2f s" % [r.athlete_name, s.x, r.final_time])
		_check(RaceMotion.state_at(r.reaction_time - 0.01, r.reaction_time, r.final_time).x == 0.0,
			"%s: fermo fino alla reazione" % r.athlete_name)
		var prev: float = -1.0
		var monotone: bool = true
		for i in range(0, 1101):
			var d: float = RaceMotion.state_at(i * 0.01, r.reaction_time, r.final_time).x
			if d < prev:
				monotone = false
			prev = d
		_check(monotone, "%s: distanza monotona" % r.athlete_name)

	rc.runner_finished.connect(func(r: RunnerData) -> void: _finish_order.append(r.athlete_name))
	rc.race_finished.connect(func(_res: Array[RunnerData]) -> void: _announced = true)
	rc.time_scale = 4.0
	rc.start()


func _process(_delta: float) -> bool:
	if not _started:
		_started = true  # gli Autoload sono pronti solo dal primo fotogramma
		_setup()
		if root.get_node("RaceController").state == 0:  # IDLE: caricamento fallito
			print("RISULTATO: %d FALLIMENTI" % _failures)
			quit(1)
		return false
	var rc: Node = root.get_node("RaceController")
	if rc.state != rc.State.FINISHED:
		return false
	var expected: Array[RunnerData] = rc.runners.duplicate()
	expected.sort_custom(func(a: RunnerData, b: RunnerData) -> bool: return a.final_time < b.final_time)
	var expected_names: Array[String] = []
	for r: RunnerData in expected:
		expected_names.append(r.athlete_name)
	_check(_announced, "race_finished emesso")
	_check(_finish_order == expected_names, "ordine d'arrivo = ordine dei tempi (%s)" % str(_finish_order))
	_check(is_equal_approx(rc.display_time, expected[0].final_time),
		"cronometro bloccato sul vincitore (%.2f)" % rc.display_time)
	_check(rc.live_order[0] == expected[0], "classifica live: primo = vincitore")
	print("RISULTATO: %s" % ("TUTTO OK" if _failures == 0 else "%d FALLIMENTI" % _failures))
	quit(0 if _failures == 0 else 1)
	return true
