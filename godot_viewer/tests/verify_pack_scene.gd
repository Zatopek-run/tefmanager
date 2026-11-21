extends SceneTree
## Verifica headless che la SCENA (RunnerView) metta davvero i corridori dove li vuole la formazione del gruppo:
##   godot --headless --path godot_viewer -s res://tests/verify_pack_scene.gd -- --race=13 --times=20,45
## Una gara per esecuzione (la sceglie lo Stadium dagli argomenti, come nel gioco). Ai tempi indicati (secondi di gara) la posizione di ogni RunnerView che ha il
## testimone deve coincidere con TrackGeometry.runner_pose(..., lateral). verify_pack.gd controlla il modello; questo controlla che la vista lo USI: uno scostamento
## calcolato e poi scartato non si vedrebbe altrimenti. Esce con codice 0 se tutto torna, 1 altrimenti.

const TOL: float = 1e-4
const MAX_SECONDS: float = 240.0  # tempo reale: oltre, la prova e' fallita

var _failures: int = 0
var _times: Array[float] = []
var _scene: Node = null
var _idx: int = 0
var _wait: int = 0
var _race_id: int = 1
var _started_at: int = 0
var _still: Dictionary = {}  # staffetta: frazione ferma -> (distanza propria, posizione) al controllo precedente


func _check(cond: bool, what: String) -> void:
	print(("OK    " if cond else "FAIL  ") + what)
	if not cond:
		_failures += 1


func _finish() -> bool:
	print("RISULTATO: " + ("TUTTO OK" if _failures == 0 else "%d FALLIMENTI" % _failures))
	quit(0 if _failures == 0 else 1)
	return true


func _process(_delta: float) -> bool:
	var rc: Node = root.get_node("RaceController")
	if _scene == null:
		for a: String in OS.get_cmdline_user_args():
			if a.begins_with("--race="):
				_race_id = int(a.get_slice("=", 1))
			if a.begins_with("--times="):
				for part: String in a.get_slice("=", 1).split(","):
					_times.append(float(part))
		rc.replay_enabled = false
		rc.time_scale = 8.0
		_scene = (load("res://scenes/Stadium.tscn") as PackedScene).instantiate()  # carica la gara (--race) e la fa partire da solo
		root.add_child(_scene)
		_started_at = Time.get_ticks_msec()
		return false
	if _idx >= _times.size():
		return _finish()
	if Time.get_ticks_msec() - _started_at > int(MAX_SECONDS * 1000.0) or rc.state == rc.State.FINISHED:
		_check(false, "gara %d: il tempo %.0f s non e' stato raggiunto (stato %d)" % [_race_id, _times[_idx], rc.state])
		return _finish()
	if rc.state != rc.State.RUNNING or rc.race_time < _times[_idx]:
		return false
	_wait += 1
	if _wait < 3:
		return false  # i RunnerView leggono il controller nel loro _process: si aspetta qualche fotogramma
	_wait = 0
	_compare(rc, _times[_idx])
	_idx += 1
	return false


func _compare(rc: Node, t: float) -> void:
	var kind: String = rc.event_kind
	var views: Array = []
	_collect(_scene, views)
	var worst: float = 0.0
	var checked: int = 0
	var spread: float = 0.0
	var still_checked: int = 0
	var still_worst: float = 0.0
	for v: Node in views:
		var d: RunnerData = v.data
		if d.lateral < 0.0:
			continue
		var st: Vector2 = v._leg_state()
		if v._relay_leg >= 0 and absf(st.x - d.distance) > 1e-6:
			# staffetta: frazione che non porta il testimone. Se e' ferma (stessa distanza propria del controllo precedente) non deve essere scivolata di lato
			if v.name in _still and absf(_still[v.name][0] - st.x) < 1e-6 and st.x > 400.0:
				still_checked += 1
				still_worst = maxf(still_worst, v.position.distance_to(_still[v.name][1]))
			_still[v.name] = [st.x, v.position]
			continue
		var want: Vector3 = TrackGeometry.runner_pose(kind, d.lane, st.x, d.lateral)["position"]
		worst = maxf(worst, v.position.distance_to(want))
		checked += 1
		spread = maxf(spread, absf(d.lateral - float(d.lane - 1) * TrackGeometry.LANE_WIDTH))
	_check(checked > 0, "gara %d (%s) t=%.0f: %d viste confrontate" % [_race_id, kind, t, checked])
	_check(worst < TOL, "gara %d (%s) t=%.0f: la scena usa la formazione (scarto massimo %.4f m, scostamento dalla corsia fino a %.2f m)" % [_race_id, kind, t, worst, spread])
	if still_checked > 0:
		_check(still_worst < TOL, "gara %d (%s) t=%.0f: %d frazioni ferme non scivolano di lato (scarto massimo %.4f m)" % [_race_id, kind, t, still_checked, still_worst])
	if _idx == _times.size() - 1:
		_check(spread > 0.3, "gara %d (%s) t=%.0f: i corridori sono davvero usciti dalla propria corsia (%.2f m)" % [_race_id, kind, t, spread])


func _collect(n: Node, out: Array) -> void:
	if n.name.begins_with("Runner_"):  # (non si cita la classe RunnerView: compilerebbe prima degli autoload)
		out.append(n)
	for c in n.get_children():
		_collect(c, out)
