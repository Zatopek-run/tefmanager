class_name BroadcastCameras
extends Node3D
## VIEW 3D - regia broadcast. Due modi, scelti in base alla gara caricata:
##  - 100m: telecamera laterale a scorrimento su Path3D, poi stacco sul fotofinish;
##  - gare sull'ovale (400m): telecamera "chase" sul lato esterno, poi stacco sul fotofinish.
## In entrambi i casi la MIRA e' sempre esattamente sul primo in classifica (live_order[0]): resta al centro
## dell'inquadratura, senza ritardo di inseguimento, anche a 4x/8x. Solo quando il primo cambia la mira scivola
## dal vecchio al nuovo (con la partenza sfalsata dei 400m due primi possono distare decine di metri in pista);
## fino allo sparo si inquadra tutto il gruppo. La camera sta sul lato esterno e guarda verso l'interno:
## i corridori vanno da sinistra a destra.
##
## Nodi attesi (definiti in Stadium.tscn):
##   Cameras (questo script)
##   |- BroadcastPath (Path3D)  -> la curva viene scritta qui in _ready()
##   |  \- CameraDolly (PathFollow3D)
##   |     \- SideCam (Camera3D)        (100m)
##   |- ChaseCam (Camera3D)             (ovale)
##   \- FinishCam (Camera3D)

const TRACK_Z_CENTER: float = 4.27        # centro delle 8 corsie sul rettilineo d'arrivo
const PATH_Z: float = 17.0                # 100m: il carrello corre sul lato esterno
const PATH_Y: float = 2.3
const PATH_START_X: float = -12.0
const PATH_END_X: float = 118.0
const SIDE_CAM_BEHIND: float = 3.0        # 100m: il carrello sta 3 m dietro il primo (angolo piu' dinamico)
const AIM_BLEND: float = 4.0              # 1/s: velocita' con cui la mira scivola sul nuovo primo quando cambia
const HEADING_FOLLOW: float = 5.0         # 1/s: morbidezza della direzione di marcia (curve)
const CUT_BEFORE_FINISH: float = 10.0     # stacco sul fotofinish quando al traguardo mancano meno di questi metri
const FINISH_CAM_Z: float = 16.0

const CHASE_DISTANCE: float = 10.0        # ovale: distanza base dal centro del gruppo, verso l'esterno
const CHASE_START_EXTRA_MAX: float = 38.0 # ...e alla partenza (corsie sfalsate su ~46 m) si inquadra tutto il gruppo
const CHASE_EXTRA_MAX: float = 12.0       # ...piu' quanto serve per inquadrare un gruppo sparpagliato
const CHASE_HEIGHT: float = 4.5          # piu' alta del 100m: si vede meglio la pista dall'alto
const CHASE_FOV: float = 30.0

@onready var _path: Path3D = $BroadcastPath
@onready var _dolly: PathFollow3D = $BroadcastPath/CameraDolly
@onready var _side_cam: Camera3D = $BroadcastPath/CameraDolly/SideCam
@onready var _chase_cam: Camera3D = $ChaseCam
@onready var _finish_cam: Camera3D = $FinishCam

var _oval: bool = false
var _finish_x: float = 100.0
var _race_distance: float = 100.0
var _follow_x: float = 0.0
var _aim_offset: Vector3 = Vector3.ZERO   # scarto fra la mira e il primo: si smorza a zero (vedi _update_chase_cam)
var _focus_lane: int = -1                 # corsia del corridore inquadrato (-1 = gruppo)
var _on_finish_cam: bool = false

var _chase_target: Vector3 = Vector3.ZERO
var _chase_heading: Vector2 = Vector2(1.0, 0.0)
var _chase_extra: float = 0.0
var _chase_lens: CameraAttributesPractical = null


func _ready() -> void:
	var curve: Curve3D = Curve3D.new()
	curve.add_point(Vector3(PATH_START_X, PATH_Y, PATH_Z))
	curve.add_point(Vector3(PATH_END_X, PATH_Y, PATH_Z))
	_path.curve = curve
	_dolly.loop = false
	_dolly.rotation_mode = PathFollow3D.ROTATION_NONE  # l'orientamento lo decide look_at(), non la curva

	# Una lente per camera: la sfocatura sullo sfondo parte oltre il soggetto, non sui corridori.
	_side_cam.fov = 28.0                  # teleobiettivo: schiaccia la prospettiva come in TV
	_side_cam.attributes = _make_lens(22.0)
	_finish_cam.fov = 22.0
	_finish_cam.attributes = _make_lens(24.0)
	_chase_lens = _make_lens(CHASE_DISTANCE + 14.0)
	_chase_cam.fov = CHASE_FOV
	_chase_cam.attributes = _chase_lens

	RaceController.race_loaded.connect(func(_r: Array[RunnerData], _i: Dictionary) -> void: reset())
	reset()


func _make_lens(far_distance: float) -> CameraAttributesPractical:
	var lens: CameraAttributesPractical = CameraAttributesPractical.new()
	lens.dof_blur_far_enabled = true      # sfoca tribune e sfondo, tiene a fuoco le corsie
	lens.dof_blur_far_distance = far_distance
	lens.dof_blur_far_transition = 25.0
	lens.dof_blur_amount = 0.06
	return lens


## Riconfigura per la gara caricata (100m rettilineo oppure ovale) e riporta le camere alla partenza.
func reset() -> void:
	_oval = RaceController.event_kind != "100m"
	_race_distance = RaceMotion.race_distance(RaceController.event_kind)
	_finish_x = TrackGeometry.FINISH_X if _oval else 100.0
	# Fotofinish: sul piano del traguardo, guarda trasversalmente tutte le corsie.
	_finish_cam.position = Vector3(_finish_x + 0.15, 0.9, FINISH_CAM_Z)
	_finish_cam.look_at_from_position(_finish_cam.position, Vector3(_finish_x, 0.8, TRACK_Z_CENTER), Vector3.UP)

	_on_finish_cam = false
	if _oval:
		_chase_extra = 0.0
		var pack: Dictionary = _pack()
		_chase_target = pack["center"]
		_chase_heading = pack["heading"]
		_update_chase_cam(0.0, true)
		_chase_cam.make_current()
	else:
		_follow_x = 0.0
		_update_side_cam(0.0, true)
		_side_cam.make_current()


func _process(delta: float) -> void:
	if RaceController.state == RaceController.State.IDLE or RaceController.state == RaceController.State.LOADED:
		return
	if not _on_finish_cam and RaceController.leader_distance() >= _race_distance - CUT_BEFORE_FINISH:
		_on_finish_cam = true
		_finish_cam.make_current()
	if _on_finish_cam:
		return
	if _oval:
		_update_chase_cam(delta, false)
	else:
		_update_side_cam(delta, false)


# --- 100m ---------------------------------------------------------------------------------------

func _update_side_cam(_delta: float, _snap: bool) -> void:
	var aim: Vector3 = _leader_world_position_100m()
	_follow_x = aim.x - SIDE_CAM_BEHIND            # il carrello segue il primo senza ritardo
	_dolly.progress = clampf(_follow_x - PATH_START_X, 0.0, PATH_END_X - PATH_START_X)
	_side_cam.look_at(aim + Vector3(0.0, 1.0, 0.0), Vector3.UP)  # mira esatta sul primo


## Posizione del primo in classifica sul rettilineo dei 100m. Prima dello sparo: centro delle corsie alla partenza.
func _leader_world_position_100m() -> Vector3:
	var live: Array[RunnerData] = RaceController.live_order
	if live.is_empty() or RaceController.state == RaceController.State.LOADED or RaceController.state == RaceController.State.COUNTDOWN:
		return Vector3(0.0, 0.0, TRACK_Z_CENTER)
	return Vector3(live[0].distance, 0.0, (live[0].lane - 1) * TrackGeometry.LANE_WIDTH)


# --- ovale --------------------------------------------------------------------------------------

## Centro, direzione media di marcia e sparpagliamento (m) dei corridori ancora in gara (tutti se sono arrivati).
func _pack() -> Dictionary:
	var positions: Array[Vector3] = []
	var heading_sum: Vector2 = Vector2.ZERO
	for pass_all: bool in [false, true]:
		for r: RunnerData in RaceController.runners:
			if r.dnf or (not pass_all and r.finished):
				continue  # un ritirato fermo non deve trascinare il centro del gruppo
			var pose: Dictionary = TrackGeometry.pose(r.lane, r.distance)
			positions.append(pose["position"])
			heading_sum += pose["heading"]
		if not positions.is_empty():
			break
	if positions.is_empty():
		return {"center": _chase_target, "heading": _chase_heading, "spread": 0.0}
	var center: Vector3 = Vector3.ZERO
	for p: Vector3 in positions:
		center += p
	center /= maxf(1.0, float(positions.size()))
	var spread: float = 0.0
	for a: Vector3 in positions:
		for b: Vector3 in positions:
			spread = maxf(spread, a.distance_to(b))
	var heading: Vector2 = heading_sum.normalized() if heading_sum.length() > 0.2 else _chase_heading
	return {"center": center, "heading": heading, "spread": spread}


func _update_chase_cam(delta: float, snap: bool) -> void:
	var pack: Dictionary = _pack()
	var at_start: bool = RaceController.state == RaceController.State.LOADED or RaceController.state == RaceController.State.COUNTDOWN
	var live: Array[RunnerData] = RaceController.live_order

	# Soggetto: il primo in classifica; fino allo sparo, il centro del gruppo (inquadratura larga).
	var focus: Vector3 = pack["center"]
	var heading: Vector2 = pack["heading"]
	var focus_lane: int = -1
	if not at_start and not live.is_empty():
		var pose: Dictionary = TrackGeometry.pose(live[0].lane, live[0].distance)
		focus = pose["position"]
		heading = pose["heading"]
		focus_lane = live[0].lane

	# Mira = soggetto + scarto. Lo scarto e' zero in regime (mira esatta, nessun ritardo); se il soggetto cambia
	# (nuovo primo, o sparo) parte dalla vecchia mira e decade a zero: la camera scivola, non salta.
	if snap:
		_aim_offset = Vector3.ZERO
		_focus_lane = focus_lane
	elif focus_lane != _focus_lane:
		_aim_offset = _chase_target - focus
		_focus_lane = focus_lane
	_aim_offset *= exp(-AIM_BLEND * delta * RaceController.time_scale)
	_chase_target = focus + _aim_offset

	var weight: float = 1.0 if snap else 1.0 - exp(-HEADING_FOLLOW * delta * RaceController.time_scale)
	_chase_heading = _chase_heading.lerp(heading, weight).normalized()
	var extra_goal: float = clampf(float(pack["spread"]) * 0.8, 0.0, CHASE_START_EXTRA_MAX) if at_start 		else clampf(float(pack["spread"]) * 0.45, 0.0, CHASE_EXTRA_MAX)
	_chase_extra = lerpf(_chase_extra, extra_goal, weight)

	# "Destra" della direzione di marcia = lato esterno della pista (si gira a sinistra).
	var right: Vector3 = Vector3(-_chase_heading.y, 0.0, _chase_heading.x)
	var distance: float = CHASE_DISTANCE + _chase_extra
	_chase_cam.position = _chase_target + right * distance + Vector3(0.0, CHASE_HEIGHT + 0.05 * _chase_extra, 0.0)
	_chase_cam.look_at(_chase_target + Vector3(0.0, 0.9, 0.0), Vector3.UP)
	_chase_cam.fov = CHASE_FOV + 0.45 * _chase_extra
	_chase_lens.dof_blur_far_distance = distance + 14.0
