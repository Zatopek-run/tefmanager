extends SceneTree
## Verifica che la camera tenga il primo in classifica al centro dell'inquadratura (a ogni velocita'):
##   godot --headless --path godot_viewer -s res://tests/verify_camera.gd
## A ogni fotogramma proietta il primo (live_order[0]) sullo schermo e misura lo scarto dal centro. Si escludono
## il conto alla rovescia (inquadratura larga sul gruppo) e lo stacco sul fotofinish (camera fissa).
## Esce con codice 0 se almeno MIN_OK_FRACTION dei fotogrammi sta entro TOLERANCE_PX dal centro.

const TOLERANCE_PX: float = 90.0
const MIN_OK_FRACTION: float = 0.95
const CASES: Array[Vector2i] = [Vector2i(3, 1), Vector2i(3, 8), Vector2i(1, 4), Vector2i(4, 4)]  # (gara, velocita')

var _failures: int = 0
var _case: int = -1
var _stadium: Node = null
var _frames: int = 0
var _ok: int = 0
var _max_dx: float = 0.0
var _max_dy: float = 0.0
var _wait: int = 0


func _check(cond: bool, what: String) -> void:
	print(("OK    " if cond else "FAIL  ") + what)
	if not cond:
		_failures += 1


func _next_case() -> bool:
	_case += 1
	if _case >= CASES.size():
		return false
	if _stadium == null:  # una sola scena per tutte le prove: la gara si cambia dal controller
		_stadium = (load("res://scenes/Stadium.tscn") as PackedScene).instantiate()
		root.add_child(_stadium)
	_wait = 3
	_frames = 0
	_ok = 0
	_max_dx = 0.0
	_max_dy = 0.0
	return true


func _process(_delta: float) -> bool:
	var rc: Node = root.get_node("RaceController")
	if _case < 0:
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
		_check(_frames > 20 and frac >= MIN_OK_FRACTION,
			"gara %d a %dx: primo entro %.0f px dal centro nel %.1f%% dei %d fotogrammi (max dx %.0f, dy %.0f)" % [
				CASES[_case].x, CASES[_case].y, TOLERANCE_PX, frac * 100.0, _frames, _max_dx, _max_dy])
		return not _next_case() and _finish()
	if rc.state != rc.State.RUNNING or rc.race_time < 1.0 or rc.live_order.is_empty():
		return false
	var cam: Camera3D = root.get_viewport().get_camera_3d()
	var cams: Node = _stadium.get_node("Cameras")
	if cam == null or cam == cams.get_node("FinishCam"):
		return false  # stacco sul fotofinish: camera fissa
	var lead: RunnerData = rc.live_order[0]
	if lead.finished:
		return false
	var view: Node3D = null
	for child: Node in _stadium.get_node("Runners").get_children():  # per dato, non per nome: dopo un riavvio i nomi cambiano
		if not child.is_queued_for_deletion() and child.get("data") == lead:
			view = child as Node3D
	if view == null:
		return false
	var world: Vector3 = view.global_position + Vector3(0.0, 0.9, 0.0)
	var size: Vector2 = root.get_visible_rect().size
	var p: Vector2 = cam.unproject_position(world)
	var behind: bool = cam.is_position_behind(world)
	var dx: float = absf(p.x - size.x * 0.5)
	var dy: float = absf(p.y - size.y * 0.5)
	_frames += 1
	_max_dx = maxf(_max_dx, dx)
	_max_dy = maxf(_max_dy, dy)
	if not behind and dx <= TOLERANCE_PX and dy <= TOLERANCE_PX:
		_ok += 1
	return false


func _finish() -> bool:
	print("RISULTATO: %s" % ("TUTTO OK" if _failures == 0 else "%d FALLIMENTI" % _failures))
	quit(0 if _failures == 0 else 1)
	return true
