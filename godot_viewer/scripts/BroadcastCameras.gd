class_name BroadcastCameras
extends Node3D
## VIEW 3D - regia broadcast: telecamera laterale a scorrimento su Path3D, poi stacco sul fotofinish.
##
## Nodi attesi (definiti in Stadium.tscn):
##   Cameras (questo script)
##   |- BroadcastPath (Path3D)  -> la curva viene scritta qui in _ready()
##   |  \- CameraDolly (PathFollow3D)
##   |     \- SideCam (Camera3D)
##   \- FinishCam (Camera3D)

const TRACK_Z_CENTER: float = 4.27        # centro delle 8 corsie
const PATH_Z: float = 17.0                # il carrello corre sul lato esterno: guardando verso -Z, +X e' a destra
const PATH_Y: float = 2.3
const PATH_START_X: float = -12.0
const PATH_END_X: float = 118.0
const LEAD_OFFSET: float = -1.0           # il punto guardato sta poco dietro il leader: il gruppo resta visibile a sinistra
const FOLLOW_SPEED: float = 3.5           # 1/s: morbidezza dell'inseguimento
const CUT_TO_FINISH_AT: float = 90.0      # stacco sul fotofinish quando il leader supera questa distanza
const FINISH_X: float = 100.0

@onready var _path: Path3D = $BroadcastPath
@onready var _dolly: PathFollow3D = $BroadcastPath/CameraDolly
@onready var _side_cam: Camera3D = $BroadcastPath/CameraDolly/SideCam
@onready var _finish_cam: Camera3D = $FinishCam

var _follow_x: float = 0.0
var _on_finish_cam: bool = false


func _ready() -> void:
	var curve: Curve3D = Curve3D.new()
	curve.add_point(Vector3(PATH_START_X, PATH_Y, PATH_Z))
	curve.add_point(Vector3(PATH_END_X, PATH_Y, PATH_Z))
	_path.curve = curve
	_dolly.loop = false
	_dolly.rotation_mode = PathFollow3D.ROTATION_NONE  # l'orientamento lo decide look_at(), non la curva

	var lens: CameraAttributesPractical = CameraAttributesPractical.new()
	lens.dof_blur_far_enabled = true      # sfoca tribune e sfondo, tiene a fuoco le corsie
	lens.dof_blur_far_distance = 22.0
	lens.dof_blur_far_transition = 25.0
	lens.dof_blur_amount = 0.06

	_side_cam.fov = 28.0                  # teleobiettivo: schiaccia la prospettiva come in TV
	_side_cam.attributes = lens
	_finish_cam.fov = 22.0
	_finish_cam.attributes = lens
	# Fotofinish: sul piano del traguardo, guarda trasversalmente tutte le corsie.
	_finish_cam.position = Vector3(FINISH_X + 0.15, 0.9, 16.0)
	_finish_cam.look_at_from_position(_finish_cam.position, Vector3(FINISH_X, 0.8, TRACK_Z_CENTER), Vector3.UP)

	RaceController.race_loaded.connect(func(_r: Array[RunnerData], _i: Dictionary) -> void: reset())
	reset()


func reset() -> void:
	_on_finish_cam = false
	_follow_x = 0.0
	_update_side_cam(0.0, true)
	_side_cam.make_current()


func _process(delta: float) -> void:
	if RaceController.state == RaceController.State.IDLE or RaceController.state == RaceController.State.LOADED:
		return
	var lead: float = RaceController.leader_distance()
	if not _on_finish_cam and lead >= CUT_TO_FINISH_AT:
		_on_finish_cam = true
		_finish_cam.make_current()
	if not _on_finish_cam:
		_update_side_cam(delta, false)


func _update_side_cam(delta: float, snap: bool) -> void:
	var target_x: float = RaceController.leader_distance() + LEAD_OFFSET
	var weight: float = 1.0 if snap else 1.0 - exp(-FOLLOW_SPEED * delta)
	_follow_x = lerpf(_follow_x, target_x, weight)
	_dolly.progress = clampf(_follow_x - PATH_START_X, 0.0, PATH_END_X - PATH_START_X)
	_side_cam.look_at(Vector3(_follow_x, 1.0, TRACK_Z_CENTER), Vector3.UP)
