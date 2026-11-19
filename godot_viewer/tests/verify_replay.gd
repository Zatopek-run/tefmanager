extends SceneTree
## Verifica headless del ralenti dell'arrivo (RaceController, stato REPLAY). Guida il controller a passi fissi
## (`set_process(false)` + `_process(dt)`), quindi non dipende dal tempo reale:
##   godot --headless --path godot_viewer -s res://tests/verify_replay.gd
## Controlla: sequenza RUNNING -> REPLAY -> FINISHED, tempo riavvolto, nessun segnale doppio, stato finale identico a
## quello senza ralenti, Esc durante il ralenti e durante la gara, nessun ralenti nei concorsi.
## Esce con codice 0 se tutto torna, 1 altrimenti.

const DT: float = 0.05
const MAX_STEPS: int = 20000
## 1-2 = 100m (2 con un ritirato), 3 = 400m, 5 = 1500m, 7 = 4x100m, 8 = 4x400m con squadra squalificata, 9 = lungo
const RACES: Array[int] = [1, 2, 3, 5, 7, 8]

var _failures: int = 0
var _done: bool = false
var _runner_finished_count: int = 0
var _race_finished_count: int = 0


func _check(cond: bool, what: String) -> void:
	print(("OK    " if cond else "FAIL  ") + what)
	if not cond:
		_failures += 1


func _process(_delta: float) -> bool:
	if _done:
		return true
	_done = true
	var rc: Node = root.get_node("RaceController")
	rc.set_process(false)
	rc.runner_finished.connect(func(_r: RunnerData) -> void: _runner_finished_count += 1)
	rc.race_finished.connect(func(_res: Array[RunnerData]) -> void: _race_finished_count += 1)
	for id: int in RACES:
		_full_race(rc, id)
	_skip_during_replay(rc, 1)
	_skip_during_run(rc, 1)
	_field_has_no_replay(rc, 9)
	_disabled_has_no_replay(rc, 1)
	print("RISULTATO: " + ("TUTTO OK" if _failures == 0 else "%d FALLIMENTI" % _failures))
	quit(0 if _failures == 0 else 1)
	return true


func _load(rc: Node, id: int) -> bool:
	_runner_finished_count = 0
	_race_finished_count = 0
	rc.replay_enabled = true
	rc.time_scale = 1.0
	if not rc.load_race(id):
		_check(false, "gara %d caricata" % id)
		return false
	rc.start()
	return true


func _names(rc: Node) -> Array[String]:
	var out: Array[String] = []
	for r: RunnerData in rc.live_order:
		out.append(r.athlete_name if not rc.is_relay(rc.event_kind) else r.team_name)
	return out


func _winner_time(rc: Node) -> float:
	var best: float = INF
	for r: RunnerData in rc.runners:
		if not r.dnf:
			best = minf(best, r.final_time)
	return best


func _check_final_state(rc: Node, label: String) -> void:
	var finishers: int = rc.runners.filter(func(r: RunnerData) -> bool: return not r.dnf).size()
	_check(rc.state == rc.State.FINISHED, "%s: stato finale FINISHED" % label)
	_check(_runner_finished_count == finishers, "%s: runner_finished emesso una volta per arrivato (%d/%d)" % [label, _runner_finished_count, finishers])
	_check(_race_finished_count == 1, "%s: race_finished emesso una volta sola (%d)" % [label, _race_finished_count])
	_check(is_equal_approx(rc.display_time, _winner_time(rc)), "%s: cronometro sul tempo del vincitore (%.2f)" % [label, rc.display_time])
	_check(rc.live_order[0].place == 1, "%s: primo in classifica = vincitore" % label)
	_check(rc.runners.all(func(r: RunnerData) -> bool: return r.finished == (not r.dnf)), "%s: arrivati tutti, ritirati no" % label)
	var places_ok: bool = true
	for i in range(rc.live_order.size() - 1):
		var a: RunnerData = rc.live_order[i]
		var b: RunnerData = rc.live_order[i + 1]
		if a.dnf == b.dnf and a.place > b.place:
			places_ok = false
	_check(places_ok, "%s: classifica nell'ordine d'arrivo" % label)


func _full_race(rc: Node, id: int) -> void:
	if not _load(rc, id):
		return
	var kind: String = rc.event_kind
	var label: String = "gara %d (%s)" % [id, kind]
	var winner: float = _winner_time(rc)
	var seq: Array[int] = []
	var live_snapshot: Array[String] = []
	var replay_min: float = INF
	var replay_max: float = -INF
	var replay_monotone: bool = true
	var replay_prev: float = -1.0
	var speed_ok: bool = true
	var no_leader_before_line: bool = true
	var leader_after_line: bool = false
	var steps: int = 0
	while rc.state != rc.State.FINISHED and steps < MAX_STEPS:
		var before: int = rc.state
		if before == rc.State.RUNNING:
			live_snapshot = _names(rc)
		rc._process(DT)
		steps += 1
		if seq.is_empty() or seq[seq.size() - 1] != rc.state:
			seq.append(rc.state)
		if rc.state == rc.State.REPLAY:
			replay_min = minf(replay_min, rc.race_time)
			replay_max = maxf(replay_max, rc.race_time)
			if rc.race_time < replay_prev:
				replay_monotone = false
			replay_prev = rc.race_time
			speed_ok = speed_ok and is_equal_approx(rc.play_speed(), rc.REPLAY_SPEED)
			var lead_done: bool = rc.live_order[0].finished
			if rc.race_time < winner - 1e-6 and lead_done:
				no_leader_before_line = false
			if rc.race_time >= winner and lead_done:
				leader_after_line = true
	_check(steps < MAX_STEPS, "%s: arriva a FINISHED (%d passi)" % [label, steps])
	_check(seq == [rc.State.COUNTDOWN, rc.State.RUNNING, rc.State.REPLAY, rc.State.FINISHED] or seq == [rc.State.RUNNING, rc.State.REPLAY, rc.State.FINISHED],
		"%s: sequenza COUNTDOWN/RUNNING -> REPLAY -> FINISHED %s" % [label, str(seq)])
	_check(replay_min < winner - 1.0, "%s: il tempo viene riavvolto prima del traguardo (%.2f < %.2f)" % [label, replay_min, winner])
	_check(replay_max >= winner + 1.0, "%s: il ralenti passa il traguardo e prosegue (%.2f)" % [label, replay_max])
	_check(replay_monotone, "%s: nel ralenti il tempo avanza sempre" % label)
	_check(speed_ok, "%s: velocita' di riproduzione = REPLAY_SPEED" % label)
	_check(no_leader_before_line, "%s: nel ralenti nessuno e' 'arrivato' prima del traguardo" % label)
	_check(leader_after_line, "%s: nel ralenti il vincitore taglia il traguardo" % label)
	_check_final_state(rc, label)
	_check(_names(rc) == live_snapshot, "%s: classifica finale uguale a quella prima del ralenti" % label)


func _skip_during_replay(rc: Node, id: int) -> void:
	if not _load(rc, id):
		return
	var steps: int = 0
	while rc.state != rc.State.REPLAY and steps < MAX_STEPS:
		rc._process(DT)
		steps += 1
	_check(rc.state == rc.State.REPLAY, "Esc nel ralenti: stato REPLAY raggiunto")
	for i in range(10):
		rc._process(DT)
	rc.skip_to_end()
	_check_final_state(rc, "Esc nel ralenti")


func _skip_during_run(rc: Node, id: int) -> void:
	if not _load(rc, id):
		return
	for i in range(40):
		rc._process(DT)
	var seen_replay: bool = false
	rc.skip_to_end()
	var steps: int = 0
	while rc.state != rc.State.FINISHED and steps < MAX_STEPS:
		rc._process(DT)
		steps += 1
		seen_replay = seen_replay or rc.state == rc.State.REPLAY
	_check(not seen_replay, "Esc in gara: salta anche il ralenti")
	_check_final_state(rc, "Esc in gara")


func _field_has_no_replay(rc: Node, id: int) -> void:
	if not _load(rc, id):
		return
	rc.time_scale = 8.0
	var seen_replay: bool = false
	var steps: int = 0
	while rc.state != rc.State.FINISHED and steps < MAX_STEPS:
		rc._process(DT)
		steps += 1
		seen_replay = seen_replay or rc.state == rc.State.REPLAY
	_check(rc.state == rc.State.FINISHED and not seen_replay, "concorso (%s): nessun ralenti" % rc.event_kind)


func _disabled_has_no_replay(rc: Node, id: int) -> void:
	if not _load(rc, id):
		return
	rc.replay_enabled = false
	var seen_replay: bool = false
	var steps: int = 0
	while rc.state != rc.State.FINISHED and steps < MAX_STEPS:
		rc._process(DT)
		steps += 1
		seen_replay = seen_replay or rc.state == rc.State.REPLAY
	_check(not seen_replay, "replay_enabled = false: nessun ralenti")
	_check_final_state(rc, "senza ralenti")
