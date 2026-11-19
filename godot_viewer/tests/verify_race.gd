extends SceneTree
## Verifica headless del modello e del controller (nessuna scena):
##   godot --headless --path godot_viewer -s res://tests/verify_race.gd
## Gara 1: tutti arrivano; gara 2: un ritirato (DNF) che si ferma e non entra nell'ordine d'arrivo.
## Esce con codice 0 se tutto torna, 1 altrimenti.

const LAST_RACE: int = 14         # 1-2 = 100m, 3-4 = 400m, 5-6 = 1500m, 7 = 4x100m, 8 = 4x400m DQ, 9-10 = Salto in Lungo, 11-12 = Getto del Peso, 13-14 = 800m

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
	print("--- gara %d: %s (%d corridori)" % [race_id, rc.event_kind, rc.runners.size()])
	if rc.event_kind == "400m":
		_check_oval_geometry()
	elif rc.event_kind == "1500m":
		_check_1500m_geometry(rc)
	elif rc.event_kind == "800m":
		_check_800m_geometry(rc)
	if rc.is_field(rc.event_kind):
		_check(not rc.field_queue.is_empty(), "concorso con %d salti in coda" % rc.field_queue.size())
		_check(rc.runners.all(func(r: RunnerData) -> bool: return r.dnf or r.attempts.size() == rc.field_rounds), "%d prove per concorrente" % rc.field_rounds)
		_check(rc.field_rounds == 6, "6 prove (3 + 3) come FIELD_ROUNDS di views/race_viewer.py")
	else:
		for r: RunnerData in rc.runners:
			if r.dnf:
				continue
			var s: Vector2 = RaceMotion.state_at(r.final_time, r.reaction_time, r.final_time, rc.event_kind)
			_check(is_equal_approx(s.x, RaceMotion.race_distance(rc.event_kind)), "%s: %.6f m a %.2f s" % [r.athlete_name, s.x, r.final_time])
			_check(RaceMotion.state_at(r.reaction_time - 0.01, r.reaction_time, r.final_time, rc.event_kind).x == 0.0,
				"%s: fermo fino alla reazione" % r.athlete_name)
			var prev: float = -1.0
			var monotone: bool = true
			for i in range(0, int(r.final_time * 100.0) + 101):
				var d: float = RaceMotion.state_at(i * 0.01, r.reaction_time, r.final_time, rc.event_kind).x
				if d < prev:
					monotone = false
				prev = d
			_check(monotone, "%s: distanza monotona" % r.athlete_name)
	var seen_bibs: Dictionary = {}
	for r: RunnerData in rc.runners:
		seen_bibs[r.bib] = true
	_check(rc.runners.all(func(r: RunnerData) -> bool: return r.bib > 0) and seen_bibs.size() == rc.runners.size(),
		"pettorali presenti e tutti diversi (%d corridori)" % rc.runners.size())
	if not _connected:  # i segnali si collegano una volta sola: lo stesso controller serve entrambe le gare
		_connected = true
		rc.runner_finished.connect(func(r: RunnerData) -> void: _finish_order.append(r.athlete_name))
		rc.race_finished.connect(func(_res: Array[RunnerData]) -> void: _announced = true)
	rc.replay_enabled = false   # il ralenti ha il suo test (verify_replay.gd): qui si verifica la gara dal vivo, piu' in fretta
	rc.time_scale = 8.0 if rc.is_field(rc.event_kind) else 4.0
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
	var higher_wins: bool = rc.is_field(rc.event_kind)
	expected.sort_custom(func(a: RunnerData, b: RunnerData) -> bool: return a.final_time > b.final_time if higher_wins else a.final_time < b.final_time)
	var expected_names: Array[String] = []
	for r: RunnerData in expected:
		expected_names.append(r.athlete_name)
	_check(_announced, "race_finished emesso")
	if not higher_wins:
		_check(_finish_order == expected_names, "ordine d'arrivo = ordine dei tempi (%s)" % str(_finish_order))
		_check(is_equal_approx(rc.display_time, expected[0].final_time),
			"cronometro bloccato sul vincitore (%.2f)" % rc.display_time)
	else:
		_check(is_equal_approx(rc.live_order[0].best_mark, expected[0].final_time),
			"miglior salto vincitore (%.2f m)" % rc.live_order[0].best_mark)
	_check(rc.live_order[0] == expected[0], "classifica live: primo = vincitore")
	var dnf_runners: Array[RunnerData] = []
	for r: RunnerData in rc.runners:
		if r.dnf:
			dnf_runners.append(r)
	if not dnf_runners.is_empty():
		_check(not _dnf_ever_finished, "il ritirato non taglia il traguardo")
		var stop: float = RaceMotion.dnf_stop_distance(rc.event_kind)
		_check(_dnf_max_distance > stop and _dnf_max_distance < stop * 1.25,
			"il ritirato si ferma poco oltre %.0f m (%.1f m)" % [stop, _dnf_max_distance])
		_check(rc.live_order[rc.live_order.size() - 1].dnf, "il ritirato e' ultimo in classifica")
		_check(dnf_runners[0].place == rc.runners.size(), "il ritirato ha l'ultimo posto")

	if _race_id < LAST_RACE:
		_race_id += 1
		_phase = 0
		return false
	return _finish()


func _finish() -> bool:
	print("RISULTATO: %s" % ("TUTTO OK" if _failures == 0 else "%d FALLIMENTI" % _failures))
	quit(0 if _failures == 0 else 1)
	return true


## Pista ovale: ogni corsia chiude l'anello, la partenza sfalsata fa correre esattamente 400 m e tutti arrivano a x = 0.
func _check_oval_geometry() -> void:
	for lane in range(1, TrackGeometry.LANES + 1):
		var length: float = 0.0
		var prev: Vector3 = TrackGeometry.pose(lane, 0.0)["position"]
		for step in range(1, 4001):
			var p: Vector3 = TrackGeometry.pose(lane, step * 0.1)["position"]
			length += p.distance_to(prev)
			prev = p
		_check(absf(length - 400.0) < 0.5, "corsia %d: percorso di 400 m (%.2f m)" % [lane, length])
		var end: Vector3 = TrackGeometry.pose(lane, 400.0)["position"]
		_check(absf(end.x - TrackGeometry.FINISH_X) < 0.01 and absf(end.z - (lane - 1) * TrackGeometry.LANE_WIDTH) < 0.01,
			"corsia %d: arriva sulla linea del traguardo (%.3f, %.3f)" % [lane, end.x, end.z])


func _check_800m_geometry(rc: Node) -> void:
	_check(not rc.uses_blocks("800m"), "800m senza blocchi (partenza in piedi)")
	_check(rc.format_time(105.92) == "1:45.92", "format_time 800m (%s)" % rc.format_time(105.92))
	for lane in range(1, TrackGeometry.LANES + 1):
		var start: Vector3 = TrackGeometry.runner_pose("800m", lane, 0.0)["position"]
		_check(absf(start.x - TrackGeometry.FINISH_X) < 0.05 and absf(start.z - (lane - 1) * TrackGeometry.LANE_WIDTH) < 0.01,
			"800m corsia %d: parte sulla linea d'arrivo nella sua corsia (%.3f, %.3f)" % [lane, start.x, start.z])
		var end: Vector3 = TrackGeometry.runner_pose("800m", lane, 800.0)["position"]
		_check(absf(end.x - TrackGeometry.FINISH_X) < 0.02 and end.z >= -0.01 and end.z <= 2.2,
			"800m corsia %d: arriva al traguardo alla corda (%.3f, %.3f)" % [lane, end.x, end.z])
		var mid: Vector3 = TrackGeometry.runner_pose("800m", lane, 400.0)["position"]
		_check(absf(mid.x - TrackGeometry.FINISH_X) < 0.05 and mid.z >= -0.01 and mid.z <= 2.2,
			"800m corsia %d: a 400 m e' al passaggio sulla linea (%.3f, %.3f)" % [lane, mid.x, mid.z])
	# la regia non deve vedere il rettilineo d'arrivo nei primi metri (la partenza e' sulla linea)
	_check(TrackGeometry.region_for("800m", 4, 0.0) == TrackGeometry.Region.ARC1, "800m: allo sparo il primo e' in curva 1")
	_check(TrackGeometry.region_for("800m", 4, 150.0) == TrackGeometry.Region.BACK, "800m: a 150 m e' sul rettilineo opposto")
	_check(TrackGeometry.region_for("800m", 4, 700.0) == TrackGeometry.Region.HOME or TrackGeometry.region_for("800m", 4, 700.0) == TrackGeometry.Region.ARC2,
		"800m: a 700 m e' nel secondo giro")


func _check_1500m_geometry(rc: Node) -> void:
	_check(rc.format_time(232.15) == "3:52.15", "format_time >= 60s (%s)" % rc.format_time(232.15))
	_check(not rc.uses_blocks("1500m"), "1500m senza blocchi (partenza in piedi)")
	for lane in range(1, TrackGeometry.LANES + 1):
		var end: Vector3 = TrackGeometry.runner_pose("1500m", lane, 1500.0)["position"]
		_check(absf(end.x - TrackGeometry.FINISH_X) < 0.02 and end.z >= -0.01 and end.z <= 2.2,
			"1500m corsia %d: arriva al traguardo alla corda (%.3f, %.3f)" % [lane, end.x, end.z])
