extends SceneTree
## Salva screenshot della scena reale (serve una finestra, NON --headless):
##   godot --path godot_viewer -s res://tests/screenshots.gd -- out_dir [close]
## Scatta ai tempi di gara in SHOTS (secondi dallo sparo; -1 = ai blocchi prima dello sparo).

## 100m: preparazione (apertura larga, primo piano blocchi, set, ripresa larga), start, carrello alto, arrivo, oltre il traguardo
const SHOTS_100M: Array[float] = [-8.6, -5.0, -1.0, -0.2, 0.8, 4.0, 8.4, 9.5, 11.5, 14.0]
## 400m: partenza, curva 1, rettilineo opposto, curva 2, rettilineo d'arrivo, fotofinish, dopo l'arrivo
const SHOTS_400M: Array[float] = [-6.6, -4.0, -1.5, 3.0, 12.0, 25.0, 36.0, 42.0, 44.3, 47.0, 50.0]

## 800m (~105 s): preparazione, curva 1, rettilineo opposto, curva 2, rettilineo d'arrivo (passaggio), 2o giro, volata, arrivo
const SHOTS_800M: Array[float] = [-3.8, -1.5, 3.0, 18.0, 33.0, 46.0, 62.0, 80.0, 96.0, 102.5, 105.2, 107.0, 110.0]

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
		rc.replay_enabled = false  # gli scatti sono ai tempi di gara dal vivo (state RUNNING)
		_scene = (load("res://scenes/Stadium.tscn") as PackedScene).instantiate()
		root.add_child(_scene)
		if args.size() > 1 and args[1] == "close":  # primo piano per giudicare il modello dei corridori
			(_scene.get_node("Cameras/BroadcastPath/CameraDolly/SideCam") as Camera3D).fov = 9.0
		return false
	if rc.state == rc.State.LOADED:
		rc.start()  # la scena parte da sola dopo 1.5 s: qui forziamo l'avvio subito
		return false
	var shots: Array[float] = SHOTS_400M if rc.event_kind == "400m" else (SHOTS_800M if rc.event_kind == "800m" else SHOTS_100M)
	if _stage >= shots.size():
		quit(0)
		return true
	var want: float = shots[_stage]
	# want < 0: secondi PRIMA dello sparo (clock); want >= 0: secondi di gara dopo lo sparo
	var ready: bool = (rc.state == rc.State.COUNTDOWN and rc.clock >= rc.gun_at + want) if want < 0.0 else (rc.state == rc.State.RUNNING and rc.race_time >= want)
	if ready:
		var img: Image = root.get_texture().get_image()
		var path: String = "%s/shot_%d_t%s.png" % [_out_dir, _stage, "pre%.1f" % absf(want) if want < 0.0 else str(want)]
		img.save_png(path)
		print("salvato ", path)
		_stage += 1
	return false
