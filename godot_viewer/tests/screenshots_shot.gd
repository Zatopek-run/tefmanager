extends SceneTree
## Screenshot del getto del peso sulla scena reale (serve una finestra, NON --headless):
##   godot --path godot_viewer -s res://tests/screenshots_shot.gd -- cartella_uscita [--race=11] [--debug] [--round=2]
## Scatta ai tempi del tentativo animato (secondi dall'ingresso dell'atleta del club). Senza --debug usa la regia vera
## (BroadcastCameras); con --debug la regia e' spenta e una camera fissa guarda l'atleta da vicino, per giudicare la posa.
## Dopo l'atterraggio scatta anche a +0.2 s (cratere), +1.0 s (nastro e bandierina).

const SHOTS: Array[float] = [0.8, 2.0, 3.0, 3.8, 4.2, 4.55, 4.8, 5.0, 5.15, 5.3, 5.55, 5.9]
const SHOTS_DEBUG: Array[float] = [3.0, 3.8, 4.1, 4.4, 4.65, 4.85, 5.0, 5.1, 5.25, 5.5, 6.0, 7.5]

var _out_dir: String = "user://shots"
var _stage: int = 0
var _scene: Node = null
var _debug: bool = false
var _round: int = 1
var _debug_cam: Camera3D = null
var _after: Array[float] = [0.2, 1.0]
var _after_stage: int = 0
var _attempt_plan: ShotPutMotion.Plan = null
var _gap_printed: bool = false


func _process(_delta: float) -> bool:
	var rc: Node = root.get_node("RaceController")
	if _scene == null:
		var args: PackedStringArray = OS.get_cmdline_user_args()
		for a: String in args:
			if a == "--debug":
				_debug = true
			elif a.begins_with("--round="):
				_round = int(a.get_slice("=", 1))
		if args.size() > 0 and not args[0].begins_with("--"):
			_out_dir = args[0]
		DirAccess.make_dir_recursive_absolute(_out_dir)
		rc.replay_enabled = false
		_scene = (load("res://scenes/Stadium.tscn") as PackedScene).instantiate()
		root.add_child(_scene)
		return false
	if rc.state == rc.State.LOADED:
		rc.start()
		return false
	if rc.state == rc.State.FINISHED:
		quit(0)
		return true
	var plan: ShotPutMotion.Plan = rc.shot_plan
	if plan != null and plan.instant and rc.state == rc.State.RUNNING and OS.get_cmdline_user_args().has("--instant"):
		# tentativo non animato (un altro concorrente): panoramica sul settore con il peso gia' a terra
		var istep: Dictionary = rc.field_queue[rc.field_idx]
		if int(istep["round"]) == _round and rc.shot_t >= 0.3:
			_save("instant")
			quit(0)
			return true
		return false
	if plan == null or plan.instant or rc.state != rc.State.RUNNING:
		return false
	var step: Dictionary = rc.field_queue[rc.field_idx]
	if int(step["round"]) != _round:
		if int(step["round"]) > _round:
			quit(0)
			return true
		return false
	if plan != _attempt_plan:
		_attempt_plan = plan
		_stage = 0
		_gap_printed = false
		_after_stage = 0
		print("tentativo: %.2f m, nullo=%s, rilascio %s, v0 %.2f m/s, volo %.2f s" % [plan.mark, str(plan.foul), str(plan.release), plan.speed, plan.flight])
		if _debug:
			(_scene.get_node("Cameras") as Node).set_process(false)
			_debug_cam = Camera3D.new()
			_scene.add_child(_debug_cam)
			_debug_cam.fov = 38.0
			_debug_cam.make_current()
	if _debug and _debug_cam != null and rc.shot_pose != null:
		var p: ShotPutMotion.Pose = rc.shot_pose
		var side: Vector3 = Vector3(2.4, 1.5, 4.2)       # dal lato destro dell'atleta (lato del braccio che lancia)
		_debug_cam.look_at_from_position(ShotPutMotion.CENTER + side, p.root + Vector3(0.0, 1.0, 0.0), Vector3.UP)
	var t: float = rc.shot_t
	if not _gap_printed and t >= ShotPutMotion.T_REL - 0.08 and t < ShotPutMotion.T_REL:
		# scarto fra il peso in mano (polso reale dopo l'IK + scarto voluto) e il punto R da cui parte il volo
		for c: Node in _scene.get_node("Runners").get_children():
			if c.get("data") == rc.active_jumper:
				var ball: MeshInstance3D = c.get("_shot_ball")
				if ball != null and ball.visible:
					print("scarto peso in mano - R al rilascio: %.1f cm" % (ball.global_position.distance_to(plan.release) * 100.0))
					_gap_printed = true
	var list: Array[float] = SHOTS_DEBUG if _debug else SHOTS
	if _stage < list.size() and t >= list[_stage]:
		_save("t%.2f" % list[_stage])
		_stage += 1
	elif _stage >= list.size() and _after_stage < _after.size() and t >= plan.t_land + _after[_after_stage]:
		_save("land+%.1f" % _after[_after_stage])
		_after_stage += 1
	elif _stage >= list.size() and _after_stage >= _after.size():
		quit(0)
		return true
	return false


func _save(tag: String) -> void:
	var img: Image = root.get_texture().get_image()
	var path: String = "%s/shot%s_%s.png" % [_out_dir, "_dbg" if _debug else "", tag]
	img.save_png(path)
	print("salvato ", path)
