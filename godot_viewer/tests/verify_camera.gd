extends SceneTree
## Verifica delle inquadrature, misurata su una finestra VERA (1280x720: in --headless la finestra di default e' 64x64
## e qualunque tolleranza in pixel sarebbe vuota). A ogni fotogramma di gara proietta sullo schermo il primo in
## classifica (live_order[0]) e giudica la camera in uso:
##   - camere che PANORAMICANO (400m: start, rettilineo opposto, curva 2): primo quasi al centro (dx, dy entro PAN_*);
##   - carrello alto (100m, rettilineo d'arrivo dei 400m, corsa oltre il traguardo): il primo sta nella FASCIA di
##     progetto a destra del centro e TUTTI i corridori ancora in gara sono nell'inquadratura;
##   - ripresa larga dello start (100m): primo e corridori in inquadratura.
## Si saltano il conto alla rovescia e il traguardo (camera fissa).  godot --headless --path godot_viewer -s res://tests/verify_camera.gd
## Esce con 0 se almeno MIN_OK_FRACTION dei fotogrammi di ogni caso e' conforme.

const VIEW_SIZE: Vector2i = Vector2i(1280, 720)
const PAN_DX: float = 0.06          # frazione della larghezza: primo vicino al centro
const PAN_DY: float = 0.12
const BAND_DX_MIN: float = 0.05     # carrello: il primo sta a destra del centro, fra queste frazioni della larghezza
const BAND_DX_MAX: float = 0.32
const MIN_OK_FRACTION: float = 0.95
var CASES: Array[Vector2i] = [Vector2i(1, 1), Vector2i(1, 4), Vector2i(3, 1), Vector2i(3, 8), Vector2i(4, 4), Vector2i(5, 8), Vector2i(6, 8)]  # (gara, velocita'); --only=gara,velocita' per un caso solo

var _failures: int = 0
var _case: int = -1
var _stadium: Node = null
var _frames: int = 0
var _ok: int = 0
var _bad_example: String = ""
var _kinds: Dictionary = {}   # tipo di camera -> [frame, ok]
var _wait: int = 0
var _last_trace: int = -1


func _check(cond: bool, what: String) -> void:
	print(("OK    " if cond else "FAIL  ") + what)
	if not cond:
		_failures += 1


func _next_case() -> bool:
	_case += 1
	if _case >= CASES.size():
		return false
	if _stadium == null:
		root.size = VIEW_SIZE
		_stadium = (load("res://scenes/Stadium.tscn") as PackedScene).instantiate()
		root.add_child(_stadium)
	_wait = 3
	_frames = 0
	_ok = 0
	_bad_example = ""
	_kinds.clear()
	return true


func _process(_delta: float) -> bool:
	var rc: Node = root.get_node("RaceController")
	if _case < 0:
		for a: String in OS.get_cmdline_user_args():
			if a.begins_with("--only="):
				var parts: PackedStringArray = a.get_slice("=", 1).split(",")
				CASES = [Vector2i(int(parts[0]), int(parts[1]))]
		return not _next_case() and _finish()
	if _wait > 0:
		_wait -= 1
		if _wait == 0:
			rc.time_scale = float(CASES[_case].y)
			rc.load_race(CASES[_case].x)
			rc.start()
		return false
	if rc.state == rc.State.FINISHED:
		var frac: float = float(_ok) / maxf(1.0, float(_frames))
		var detail: Array[String] = []
		for k: String in _kinds:
			detail.append("%s %d/%d" % [k, _kinds[k][1], _kinds[k][0]])
		_check(_frames > 20 and frac >= MIN_OK_FRACTION, "gara %d a %dx (finestra %s): %.1f%% di %d fotogrammi conformi [%s]%s" % [
			CASES[_case].x, CASES[_case].y, str(root.get_visible_rect().size), frac * 100.0, _frames, ", ".join(detail),
			("" if _bad_example.is_empty() else "  es. non conforme: " + _bad_example)])
		return not _next_case() and _finish()
	if rc.state != rc.State.RUNNING or rc.race_time < 1.0 or rc.live_order.is_empty():
		return false
	var cam: Camera3D = root.get_viewport().get_camera_3d()
	var cams: Node = _stadium.get_node("Cameras")
	if cam == null or cam == cams.get_node("FinishCam"):
		return false
	var lead: RunnerData = rc.live_order[0]
	if lead.finished and cam != cams.get("_side_cam"):
		return false
	var size: Vector2 = root.get_visible_rect().size
	var kind: String = _cam_kind(cam, cams)
	var p: Vector2 = cam.unproject_position(_world_of(lead))
	var dx: float = (p.x - size.x * 0.5) / size.x
	var dy: float = (p.y - size.y * 0.5) / size.y
	var good: bool = not cam.is_position_behind(_world_of(lead))
	match kind:
		"pan":
			good = good and absf(dx) <= PAN_DX and absf(dy) <= PAN_DY
		"carrello":
			good = good and dx >= BAND_DX_MIN and dx <= BAND_DX_MAX and absf(dy) <= 0.45
			for r: RunnerData in rc.runners:  # tutti quelli ancora in gara devono essere nell'inquadratura (non nella corsa dopo il traguardo del primo)
				if lead.finished or r.finished or r.dnf:
					continue
				var q: Vector2 = cam.unproject_position(_world_of(r))
				if q.x < 0.0 or q.x > size.x or q.y < 0.0 or q.y > size.y or cam.is_position_behind(_world_of(r)):
					good = false
					if _bad_example.is_empty():
						_bad_example = "fuori quadro: %s a (%.0f, %.0f) px, spread %.1f m, fov %.1f (goal scala %.2f), pos cam %s, primo dx %.2f" % [r.surname(), q.x, q.y, rc.leader_distance() - r.distance, cam.fov, cams.get("_frame_scale"), str(cam.position), dx]
		_:  # start largo
			good = good and p.x >= 0.0 and p.x <= size.x and p.y >= 0.0 and p.y <= size.y
	if OS.get_cmdline_user_args().has("--trace") and kind == "carrello" and int(rc.race_time * 4.0) != _last_trace:
		_last_trace = int(rc.race_time * 4.0)
		var outs: Array[String] = []
		for r2: RunnerData in rc.runners:
			var q2: Vector2 = cam.unproject_position(_world_of(r2))
			if q2.x < 0.0 or q2.x > size.x:
				outs.append("%s(%.0f%s)" % [r2.surname(), q2.x, "F" if r2.finished else ""])
		print("t=%.2f primo dx=%.2f scala=%.2f fov=%.1f spread=%.1f fuori=%s lead.fin=%s" % [rc.race_time, dx, cams.get("_frame_scale"), cam.fov, cams.call("_racing_spread"), str(outs), str(lead.finished)])
	_frames += 1
	if not _kinds.has(kind):
		_kinds[kind] = [0, 0]
	_kinds[kind][0] += 1
	if good:
		_ok += 1
		_kinds[kind][1] += 1
	elif _bad_example.is_empty():
		_bad_example = "%s t=%.1f primo a (%.2f, %.2f) della larghezza/altezza dal centro" % [kind, rc.race_time, dx, dy]
	return false


func _cam_kind(cam: Camera3D, cams: Node) -> String:
	if cam == cams.get("_side_cam"):
		return "carrello"
	if cam == cams.get("_o_start") or cam == cams.get("_o_far") or cam == cams.get("_o_curve"):
		return "pan"
	return "start"


func _world_of(r: RunnerData) -> Vector3:
	var rc: Node = root.get_node("RaceController")
	return TrackGeometry.runner_pose(rc.event_kind, r.lane, r.distance)["position"] + Vector3(0.0, 0.9, 0.0)


func _finish() -> bool:
	print("RISULTATO: %s" % ("TUTTO OK" if _failures == 0 else "%d FALLIMENTI" % _failures))
	quit(0 if _failures == 0 else 1)
	return true
