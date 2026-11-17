extends SceneTree
## Salva screenshot della scena reale (serve una finestra, NON --headless):
##   godot --path godot_viewer -s res://tests/screenshots.gd -- out_dir [close]
## Scatta ai tempi di gara in SHOTS (secondi dallo sparo; -1 = ai blocchi prima dello sparo).

const SHOTS_100M: Array[float] = [-1.0, 4.0, 9.5, 9.85, 10.4]
## 400m: partenza, curva 1, rettilineo opposto, curva 2, rettilineo d'arrivo, fotofinish, dopo l'arrivo
const SHOTS_400M: Array[float] = [-1.0, 6.0, 15.0, 25.0, 33.0, 40.0, 44.8, 46.5]

var _out_dir: String = "user://shots"
var _stage: int = 0
var _scene: Node = null


func _process(_delta: float) -> bool:
	var rc: Node = root.get_node("RaceController")
	if _scene == null:
		var args: PackedStringArray = OS.get_cmdline_user_args()
		for a: String in args:
			if a.begins_with("--speed="):
				rc.time_scale = float(a.get_slice("=", 1))  # per provare le camere a 2x/4x/8x
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
	var shots: Array[float] = SHOTS_400M if rc.event_kind == "400m" else SHOTS_100M
	if _stage >= shots.size():
		quit(0)
		return true
	var want: float = shots[_stage]
	var ready: bool = (rc.state == rc.State.COUNTDOWN and rc.clock > 1.8) if want < 0.0 else rc.race_time >= want
	if ready:
		var img: Image = root.get_texture().get_image()
		var path: String = "%s/shot_%d_t%s.png" % [_out_dir, _stage, "pre" if want < 0.0 else str(want)]
		img.save_png(path)
		print("salvato ", path)
		_stage += 1
	return false
