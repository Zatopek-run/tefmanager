extends SceneTree
## Verifica headless del modello e del controller (nessuna scena):
##   godot --headless --path godot_viewer -s res://tests/verify_race.gd
## Gara 1: tutti arrivano; gara 2: un ritirato (DNF) che si ferma e non entra nell'ordine d'arrivo.
## Esce con codice 0 se tutto torna, 1 altrimenti.

var _failures: int = 0
var _race_id: int = 1
var _phase: int = 0              # 0 = da avviare, 1 = in corso
var _finish_order: Array[String] = []
var _announced: bool = false
var _connected: bool = false
var _dnf_max_distance: float = 0.0
var _dnf_ever_finished: bool = false


func _check(cond: bool, what: String) -> void:
	print(("OK    " if cond else "FAIL  ") + what)
	if not cond:
		_failures += 1


func _start_race(race_id: int) -> bool:
	var rc: Node = root.get_node("RaceController")
	_finish_order.clear()
	_announced = false
	_dnf_max_distance = 0.0
	_dnf_ever_finished = false
	if not rc.load_race(race_id):
		_check(false, "gara %d caricata" % race_id)
		return false
	print("--- gara %d (%d corridori)" % [race_id, rc.runners.size()])
	for r: RunnerData in rc.runners:
		if r.dnf:
			continue
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
	if not _connected:  # i segnali si collegano una volta sola: lo stesso controller serve entrambe le gare
		_connected = true
		rc.runner_finished.connect(func(r: RunnerData) -> void: _finish_order.append(r.athlete_name))
		rc.race_finished.connect(func(_res: Array[RunnerData]) -> void: _announced = true)
	rc.time_scale = 4.0
	rc.start()
	return true


func _process(_delta: float) -> bool:
	var rc: Node = root.get_node("RaceController")
	if _phase == 0:
		_phase = 1
		_check(root.get_node("DatabaseManager").is_open(), "database aperto")
		if not _start_race(_race_id):
			return _finish()
		return false
	for r: RunnerData in rc.runners:
		if r.dnf:
			_dnf_max_distance = maxf(_dnf_max_distance, r.distance)
			_dnf_ever_finished = _dnf_ever_finished or r.finished
	if rc.state != rc.State.FINISHED:
		return false

	var expected: Array[RunnerData] = []
	for r: RunnerData in rc.runners:
		if not r.dnf:
			expected.append(r)
	expected.sort_custom(func(a: RunnerData, b: RunnerData) -> bool: return a.final_time < b.final_time)
	var expected_names: Array[String] = []
	for r: RunnerData in expected:
		expected_names.append(r.athlete_name)
	_check(_announced, "race_finished emesso")
	_check(_finish_order == expected_names, "ordine d'arrivo = ordine dei tempi (%s)" % str(_finish_order))
	_check(is_equal_approx(rc.display_time, expected[0].final_time),
		"cronometro bloccato sul vincitore (%.2f)" % rc.display_time)
	_check(rc.live_order[0] == expected[0], "classifica live: primo = vincitore")
	var dnf_runners: Array[RunnerData] = []
	for r: RunnerData in rc.runners:
		if r.dnf:
			dnf_runners.append(r)
	if not dnf_runners.is_empty():
		_check(not _dnf_ever_finished, "il ritirato non taglia il traguardo")
		_check(_dnf_max_distance > RaceMotion.DNF_STOP_DISTANCE and _dnf_max_distance < 60.0,
			"il ritirato si ferma poco oltre %.0f m (%.1f m)" % [RaceMotion.DNF_STOP_DISTANCE, _dnf_max_distance])
		_check(rc.live_order[rc.live_order.size() - 1].dnf, "il ritirato e' ultimo in classifica")
		_check(dnf_runners[0].place == rc.runners.size(), "il ritirato ha l'ultimo posto")

	if _race_id < 2:
		_race_id += 1
		_phase = 0
		return false
	return _finish()


func _finish() -> bool:
	print("RISULTATO: %s" % ("TUTTO OK" if _failures == 0 else "%d FALLIMENTI" % _failures))
	quit(0 if _failures == 0 else 1)
	return true
