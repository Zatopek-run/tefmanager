extends SceneTree
## Screenshot del gruppo nei 800m e 1500m (serve una finestra, NON --headless):
##   godot --path godot_viewer -s res://tests/screenshots_pack.gd -- out_dir --race=13 --times=5,17,30,60 [--speed=4]
## Per ogni istante (secondi di gara dallo sparo) salva DUE immagini: la regia normale e una vista DALL'ALTO sulla testa della corsa, che fa vedere chi sta
## sulla corda, chi sorpassa all'esterno e dove ognuno rientra. Con flatpak /tmp e' privato: usa una cartella della home.

var _out_dir: String = "user://shots"
var _times: Array[float] = []
var _stage: int = 0
var _scene: Node = null
var _top: Camera3D = null
var _phase: int = 0  # 0 = in attesa del tempo, 1 = camera dall'alto attiva (si scatta al fotogramma dopo)


func _process(_delta: float) -> bool:
	var rc: Node = root.get_node("RaceController")
	if _scene == null:
		var args: PackedStringArray = OS.get_cmdline_user_args()
		if args.size() > 0:
			_out_dir = args[0]
		for a: String in args:
			if a.begins_with("--speed="):
				rc.time_scale = float(a.get_slice("=", 1))
			if a.begins_with("--times="):
				for part: String in a.get_slice("=", 1).split(","):
					_times.append(float(part))
		DirAccess.make_dir_recursive_absolute(_out_dir)
		rc.replay_enabled = false
		_scene = (load("res://scenes/Stadium.tscn") as PackedScene).instantiate()
		root.add_child(_scene)
		_top = Camera3D.new()
		_top.fov = 38.0
		_scene.add_child(_top)
		return false
	if rc.state == rc.State.LOADED:
		rc.start()
		return false
	if _stage >= _times.size():
		quit(0)
		return true
	if _phase == 0:
		if rc.state == rc.State.RUNNING and rc.race_time >= _times[_stage]:
			_save("%s/pack_%02d_t%.0f_tv.png" % [_out_dir, _stage, _times[_stage]])
			# vista dall'alto sulla testa: centro fra il primo e l'ultimo ancora in gara
			var lo: float = INF
			var hi: float = -INF
			for r: RunnerData in rc.runners:
				if r.dnf or r.finished:
					continue
				lo = minf(lo, r.distance)
				hi = maxf(hi, r.distance)
			var lead: RunnerData = rc.live_order[0]
			var mid_d: float = (lo + hi) * 0.5 if hi >= lo else lead.distance
			var center: Vector3 = TrackGeometry.runner_pose(rc.event_kind, lead.lane, mid_d, 1.0)["position"]
			var span: float = maxf(14.0, hi - lo + 8.0)
			_top.position = center + Vector3(0.0, span * 1.45, 0.001)
			_top.look_at(center, Vector3.UP)
			_top.make_current()
			_phase = 1
		return false
	# fotogramma dopo: la camera dall'alto e' quella disegnata
	_save("%s/pack_%02d_t%.0f_top.png" % [_out_dir, _stage, _times[_stage]])
	_stage += 1
	_phase = 0
	return false


func _save(path: String) -> void:
	var img: Image = root.get_texture().get_image()
	img.save_png(path)
	print("salvato ", path)
