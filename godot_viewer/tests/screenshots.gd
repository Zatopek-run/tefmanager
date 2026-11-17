extends SceneTree
## Salva screenshot della scena reale (serve una finestra, NON --headless):
##   godot --path godot_viewer -s res://tests/screenshots.gd -- out_dir [close]
## Scatta ai tempi di gara in SHOTS (secondi dallo sparo; -1 = ai blocchi prima dello sparo).

const SHOTS: Array[float] = [-1.0, 4.0, 9.5, 9.85, 10.4]

var _out_dir: String = "user://shots"
var _stage: int = 0
var _scene: Node = null


func _process(_delta: float) -> bool:
	var rc: Node = root.get_node("RaceController")
	if _scene == null:
		var args: PackedStringArray = OS.get_cmdline_user_args()
		if args.size() > 0:
			_out_dir = args[0]
		DirAccess.make_dir_recursive_absolute(_out_dir)
		_scene = (load("res://scenes/Stadium.tscn") as PackedScene).instantiate()
		root.add_child(_scene)
		if args.size() > 1 and args[1] == "close":  # primo piano per giudicare il modello dei corridori
			(_scene.get_node("Cameras/BroadcastPath/CameraDolly/SideCam") as Camera3D).fov = 9.0
		return false
	if rc.state == rc.State.LOADED:
		rc.start()  # la scena parte da sola dopo 1.5 s: qui forziamo l'avvio subito
		return false
	if _stage >= SHOTS.size():
		quit(0)
		return true
	var want: float = SHOTS[_stage]
	var ready: bool = (rc.state == rc.State.COUNTDOWN and rc.clock > 1.8) if want < 0.0 else rc.race_time >= want
	if ready:
		var img: Image = root.get_texture().get_image()
		var path: String = "%s/shot_%d_t%s.png" % [_out_dir, _stage, "pre" if want < 0.0 else str(want)]
		img.save_png(path)
		print("salvato ", path)
		_stage += 1
	return false
