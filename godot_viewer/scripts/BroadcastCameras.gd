class_name BroadcastCameras
extends Node3D
## VIEW 3D - regia broadcast, ricavata dalle dirette di riferimento (100m di Roma, 400m di Parigi 2024).
## I cambi di ripresa dipendono dallo STATO della gara (clock prima dello sparo, tratto dell'anello dopo), non dal
## tempo reale: valgono quindi a 1x come a 8x. In gara la MIRA e' sempre esattamente sul primo in classifica.
##
## 100m (vedi _direct_100m): apertura larga dall'alto dietro i blocchi -> primo piano basso sui blocchi (teleobiettivo,
##   sfondo sfocato) -> ripresa larga dello start -> carrello alto su Path3D che segue il gruppo (il primo a destra
##   del centro) -> ripresa dall'alto sul traguardo -> corsa oltre il traguardo, sulla curva.
## Ovale (vedi _direct_oval, 400m): apertura larga sulla partenza sfalsata -> primo piano sui blocchi -> ripresa larga dello
##   start (resta finche' il primo e' in curva 1) -> dal lato opposto dell'interno con teleobiettivo (rettilineo opposto)
##   -> dall'alto sulla curva 2 -> carrello alto sul rettilineo d'arrivo -> traguardo -> oltre il traguardo.
##
## Nodi attesi (definiti in Stadium.tscn):
##   Cameras (questo script)
##   |- BroadcastPath (Path3D)  -> la curva viene scritta qui in _ready()
##   |  \- CameraDolly (PathFollow3D)
##   |     \- SideCam (Camera3D)        (carrello alto)
##   \- FinishCam (Camera3D)

const TRACK_Z_CENTER: float = 4.27        # centro delle 8 corsie sul rettilineo d'arrivo
const PATH_Z: float = 20.7                # carrello alto sul lato esterno: ~30 gradi di inclinazione sul centro pista
const PATH_Y: float = 9.5
const PATH_START_X: float = -112.0
const PATH_END_X: float = 70.0
const TRACK_FOV: float = 24.0             # il gruppo occupa circa meta' inquadratura
const LEAD_IN_FRAME: float = 3.0          # il primo sta 3 m a destra del centro dell'inquadratura (~70% della larghezza)
const CUT_BEFORE_FINISH: float = 10.0     # stacco sul traguardo quando mancano meno di questi metri
const RUNOUT_CUT_DELAY: float = 1.2       # dopo l'arrivo del primo si torna al carrello alto sulla corsa oltre il traguardo
# Preparazione (secondi di clock prima dello sparo):
const OPEN_WIDE_TIME: float = 0.8         # apertura larga
const WIDE_CUT_BEFORE_GUN_100M: float = 0.4
const WIDE_CUT_BEFORE_GUN_OVAL: float = 2.2   # nei 400m lo start largo si vede piu' a lungo
const START_WIDE_HOLD: float = 2.2        # 100m: la ripresa larga resta fino a questo tempo di gara
const FINISH_CAM_Z: float = 16.0

@onready var _path: Path3D = $BroadcastPath
@onready var _dolly: PathFollow3D = $BroadcastPath/CameraDolly
@onready var _side_cam: Camera3D = $BroadcastPath/CameraDolly/SideCam
@onready var _finish_cam: Camera3D = $FinishCam

var _oval: bool = false
var _race_distance: float = 100.0
var _current_cam: Camera3D = null

# 100m
var _open_cam: Camera3D
var _close_cam: Camera3D
var _start_cam: Camera3D
# ovale
var _o_open: Camera3D
var _o_close: Camera3D
var _o_start: Camera3D
var _o_far: Camera3D
var _o_curve: Camera3D


func _ready() -> void:
	var curve: Curve3D = Curve3D.new()
	curve.add_point(Vector3(PATH_START_X, PATH_Y, PATH_Z))
	curve.add_point(Vector3(PATH_END_X, PATH_Y, PATH_Z))
	_path.curve = curve
	_dolly.loop = false
	_dolly.rotation_mode = PathFollow3D.ROTATION_NONE  # l'orientamento lo decide look_at(), non la curva

	# Una lente per camera: la sfocatura sullo sfondo parte oltre il soggetto, non sui corridori.
	_side_cam.fov = TRACK_FOV             # teleobiettivo: schiaccia la prospettiva come in TV
	_side_cam.attributes = _make_lens(60.0)
	_finish_cam.attributes = _make_lens(60.0)

	var sx: float = TrackGeometry.START_100M_X
	_open_cam = _make_static_cam(Vector3(sx - 15.0, 9.0, 4.4), Vector3(sx + 12.0, 0.3, 4.4), 40.0, 60.0)
	# Primo piano basso con teleobiettivo: lo sfondo e' sfocato; angolo e distanza vengono dal confronto con il video.
	_close_cam = _make_static_cam(Vector3(sx + 1.4, 0.75, 12.5), Vector3(sx - 0.5, 0.55, 5.0), 42.0, 9.0)
	_start_cam = _make_static_cam(Vector3(sx + 9.0, 11.0, 19.0), Vector3(sx + 3.0, 0.3, 3.6), 42.0, 40.0)

	var s: float = TrackGeometry.STRAIGHT
	_o_open = _make_static_cam(Vector3(-14.0, 17.0, -20.0), Vector3(20.0, 0.0, -12.0), 50.0, 80.0)
	_o_close = _make_static_cam(Vector3(0.0, 1.0, 5.0), Vector3(0.0, 0.5, 0.0), 38.0, 7.0)   # riposizionata in reset()
	_o_start = _make_static_cam(Vector3(-4.0, 8.0, -14.0), Vector3(24.0, 0.0, -14.0), 28.0, 120.0)
	_o_far = _make_static_cam(Vector3(-s * 0.5, 5.0, 34.0), Vector3(-s * 0.5, 0.8, -78.0), 9.0, 600.0)   # teleobiettivo dall'altro lato
	_o_curve = _make_static_cam(Vector3(-s - 72.0, 18.0, -36.8), Vector3(-s - 30.0, 0.8, -36.8), 30.0, 150.0)

	RaceController.race_loaded.connect(func(_r: Array[RunnerData], _i: Dictionary) -> void: reset())
	reset()


func _make_static_cam(pos: Vector3, target: Vector3, fov_deg: float, dof_far: float) -> Camera3D:
	var cam: Camera3D = Camera3D.new()
	add_child(cam)
	cam.fov = fov_deg
	cam.attributes = _make_lens(dof_far)
	cam.look_at_from_position(pos, target, Vector3.UP)
	return cam


func _make_lens(far_distance: float) -> CameraAttributesPractical:
	var lens: CameraAttributesPractical = CameraAttributesPractical.new()
	lens.dof_blur_far_enabled = true      # sfoca tribune e sfondo, tiene a fuoco le corsie
	lens.dof_blur_far_distance = far_distance
	lens.dof_blur_far_transition = 25.0
	lens.dof_blur_amount = 0.08
	return lens


## Riconfigura per la gara caricata (100m oppure ovale) e riporta le camere alla preparazione.
func reset() -> void:
	_oval = RaceController.event_kind != "100m"
	_race_distance = RaceMotion.race_distance(RaceController.event_kind)
	var fx: float = TrackGeometry.FINISH_X
	if _oval:
		# Traguardo dei 400m: sul piano della linea, guarda trasversalmente tutte le corsie.
		_finish_cam.fov = 22.0
		_finish_cam.look_at_from_position(Vector3(fx + 0.15, 0.9, FINISH_CAM_Z), Vector3(fx, 0.8, TRACK_Z_CENTER), Vector3.UP)
		# Primo piano sui blocchi della corsia 6 (al centro dello schieramento), dal lato esterno.
		var pose: Dictionary = TrackGeometry.pose(6, 0.0)
		var h: Vector2 = pose["heading"]
		var right: Vector3 = Vector3(-h.y, 0.0, h.x)
		var p: Vector3 = pose["position"]
		_o_close.look_at_from_position(p + right * 3.4 + Vector3(0.0, 0.75, 0.0),
			p + Vector3(h.x, 0.0, h.y) * -0.3 + Vector3(0.0, 0.5, 0.0), Vector3.UP)
	else:
		# 100m: dall'alto, appena oltre la linea, sul lato esterno; i corridori arrivano da sinistra.
		_finish_cam.fov = 30.0
		_finish_cam.look_at_from_position(Vector3(fx + 3.0, 10.0, 20.0), Vector3(fx - 5.0, 0.4, TRACK_Z_CENTER), Vector3.UP)
	_current_cam = null
	_direct()


func _process(_delta: float) -> void:
	_direct()


func _direct() -> void:
	if _oval:
		_direct_oval()
	else:
		_direct_100m()


## Regia dei 100m, scelta in base allo stato della gara.
func _direct_100m() -> void:
	var rc: Node = RaceController
	var cam: Camera3D = _side_cam
	match rc.state:
		rc.State.IDLE, rc.State.LOADED:
			cam = _open_cam
		rc.State.COUNTDOWN:
			if rc.clock < OPEN_WIDE_TIME:
				cam = _open_cam
			elif rc.clock < rc.gun_at - WIDE_CUT_BEFORE_GUN_100M:
				cam = _close_cam
			else:
				cam = _start_cam
		_:
			var live: Array[RunnerData] = rc.live_order
			var leader_done: bool = not live.is_empty() and live[0].finished
			if rc.race_time < START_WIDE_HOLD:
				cam = _start_cam
			elif leader_done and rc.race_time > live[0].final_time + RUNOUT_CUT_DELAY:
				cam = _side_cam  # corsa oltre il traguardo, di nuovo dall'alto
			elif rc.leader_distance() >= _race_distance - CUT_BEFORE_FINISH:
				cam = _finish_cam
	_apply(cam)


## Regia sull'ovale (400m): una ripresa per tratto dell'anello in cui si trova il primo in classifica.
func _direct_oval() -> void:
	var rc: Node = RaceController
	var cam: Camera3D = _o_start
	match rc.state:
		rc.State.IDLE, rc.State.LOADED:
			cam = _o_open
		rc.State.COUNTDOWN:
			if rc.clock < OPEN_WIDE_TIME:
				cam = _o_open
			elif rc.clock < rc.gun_at - WIDE_CUT_BEFORE_GUN_OVAL:
				cam = _o_close
			else:
				cam = _o_start
		_:
			var live: Array[RunnerData] = rc.live_order
			if not live.is_empty():
				var lead: RunnerData = live[0]
				if lead.finished and rc.race_time > lead.final_time + RUNOUT_CUT_DELAY:
					cam = _side_cam
				elif lead.distance >= _race_distance - CUT_BEFORE_FINISH:
					cam = _finish_cam
				else:
					match TrackGeometry.region(lead.lane, lead.distance):
						TrackGeometry.Region.ARC1: cam = _o_start
						TrackGeometry.Region.BACK: cam = _o_far
						TrackGeometry.Region.ARC2: cam = _o_curve
						_: cam = _side_cam
	_apply(cam)


func _apply(cam: Camera3D) -> void:
	if cam != _current_cam:
		_current_cam = cam
		cam.make_current()
	# Mira esatta sul primo in classifica per le camere che seguono la gara (nessun ritardo di inseguimento).
	if cam == _side_cam:
		_update_side_cam()
	elif cam == _o_start or cam == _o_far or cam == _o_curve:
		if RaceController.state == RaceController.State.RUNNING or RaceController.state == RaceController.State.FINISHED:
			cam.look_at(_leader_world_position() + Vector3(0.0, 0.9, 0.0), Vector3.UP)


## Carrello alto su Path3D: segue il gruppo con il primo poco a destra del centro.
func _update_side_cam() -> void:
	var aim: Vector3 = _leader_world_position()
	aim.x -= LEAD_IN_FRAME                       # il primo cade a destra del centro (ripresa TV)
	aim.z = TRACK_Z_CENTER                       # si guarda il centro pista, non la corsia del primo
	_dolly.progress = clampf(aim.x - PATH_START_X, 0.0, PATH_END_X - PATH_START_X)
	_side_cam.look_at(aim + Vector3(0.0, 0.4, 0.0), Vector3.UP)


## Posizione del primo in classifica. Prima dello sparo: centro delle corsie alla linea di partenza.
func _leader_world_position() -> Vector3:
	var live: Array[RunnerData] = RaceController.live_order
	var start_x: float = TrackGeometry.START_100M_X if RaceController.event_kind == "100m" else 0.0
	if live.is_empty() or RaceController.state == RaceController.State.LOADED or RaceController.state == RaceController.State.COUNTDOWN:
		return Vector3(start_x, 0.0, TRACK_Z_CENTER)
	return TrackGeometry.runner_pose(RaceController.event_kind, live[0].lane, live[0].distance)["position"]
