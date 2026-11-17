class_name RunnerView
extends Node3D
## VIEW 3D - corridore mid-poly costruito da primitive (nessun asset esterno).
## Legge `RunnerData` (distanza, velocita') e si limita a rappresentarlo: posizione = distanza,
## frequenza della falcata = velocita' / lunghezza del passo. Non influenza mai il risultato.
##
## Convenzione assi: pista lungo +X, su = +Y, corsie lungo +Z. Una rotazione positiva attorno a Z
## porta un arto che pende verso il basso in avanti (+X).

const LANE_WIDTH: float = 1.22
const TOP_SPEED: float = 11.5      # m/s oltre cui l'ampiezza della falcata e' massima
const STRIDE_MIN: float = 2.0      # lunghezza del ciclo completo (2 passi) in partenza, m
const STRIDE_MAX: float = 4.4      # ...e a regime
const HIP_HEIGHT: float = 0.95
const CROUCH_HIP_HEIGHT: float = 0.62
const CROUCH_DISTANCE: float = 2.5 # a questa distanza dai blocchi il corridore e' gia' in piedi

var data: RunnerData = null

var _hips: Node3D
var _torso: Node3D
var _legs: Array[Dictionary] = []  # {thigh, shin, side}
var _arms: Array[Dictionary] = []  # {upper, fore, side}
var _phase: float = 0.0


func setup(runner: RunnerData) -> void:
	data = runner
	position = Vector3(0.0, 0.0, (runner.lane - 1) * LANE_WIDTH)
	_build_body()
	_apply_pose(0.0, 0.0)


func _process(delta: float) -> void:
	if data == null:
		return
	position.x = data.distance
	var amp: float = clampf(data.speed / TOP_SPEED, 0.0, 1.0)
	var stride: float = lerpf(STRIDE_MIN, STRIDE_MAX, amp)
	_phase = fmod(_phase + data.speed / stride * TAU * delta * RaceController.time_scale, TAU)
	_apply_pose(data.distance, amp)


# --- costruzione --------------------------------------------------------------------------------

func _build_body() -> void:
	var skin: StandardMaterial3D = _material(_skin_color(data.athlete_name))
	var kit: StandardMaterial3D = _material(_team_color(data.team_name))
	var shorts: StandardMaterial3D = _material(_team_color(data.team_name).darkened(0.45))
	var shoe: StandardMaterial3D = _material(Color(0.95, 0.95, 0.95))

	_hips = Node3D.new()
	_hips.position = Vector3(0.0, HIP_HEIGHT, 0.0)
	add_child(_hips)
	_add_mesh(_hips, _box(0.2, 0.18, 0.36), shorts, Vector3(0.0, 0.0, 0.0))

	_torso = Node3D.new()
	_hips.add_child(_torso)
	_add_mesh(_torso, _capsule(0.15, 0.58), kit, Vector3(0.0, 0.3, 0.0))
	_add_mesh(_torso, _sphere(0.11), skin, Vector3(0.02, 0.72, 0.0))  # testa

	for side: float in [1.0, -1.0]:
		var shoulder: Node3D = Node3D.new()
		shoulder.position = Vector3(0.0, 0.55, 0.2 * side)
		_torso.add_child(shoulder)
		_add_mesh(shoulder, _capsule(0.045, 0.3), skin, Vector3(0.0, -0.15, 0.0))
		var elbow: Node3D = Node3D.new()
		elbow.position = Vector3(0.0, -0.3, 0.0)
		shoulder.add_child(elbow)
		_add_mesh(elbow, _capsule(0.04, 0.28), skin, Vector3(0.0, -0.14, 0.0))
		_arms.append({"upper": shoulder, "fore": elbow, "side": side})

		var thigh: Node3D = Node3D.new()
		thigh.position = Vector3(0.0, -0.05, 0.1 * side)
		_hips.add_child(thigh)
		_add_mesh(thigh, _capsule(0.075, 0.46), skin, Vector3(0.0, -0.23, 0.0))
		var knee: Node3D = Node3D.new()
		knee.position = Vector3(0.0, -0.46, 0.0)
		thigh.add_child(knee)
		_add_mesh(knee, _capsule(0.055, 0.44), skin, Vector3(0.0, -0.22, 0.0))
		_add_mesh(knee, _box(0.26, 0.07, 0.1), shoe, Vector3(0.07, -0.46, 0.0))
		_legs.append({"thigh": thigh, "shin": knee, "side": side})


func _add_mesh(parent: Node3D, mesh: Mesh, mat: Material, pos: Vector3) -> void:
	var mi: MeshInstance3D = MeshInstance3D.new()
	mi.mesh = mesh
	mi.material_override = mat
	mi.position = pos
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
	parent.add_child(mi)


func _capsule(radius: float, height: float) -> CapsuleMesh:
	var m: CapsuleMesh = CapsuleMesh.new()
	m.radius = radius
	m.height = maxf(height, radius * 2.0)
	m.radial_segments = 12
	m.rings = 4
	return m


func _sphere(radius: float) -> SphereMesh:
	var m: SphereMesh = SphereMesh.new()
	m.radius = radius
	m.height = radius * 2.0
	m.radial_segments = 16
	m.rings = 8
	return m


func _box(x: float, y: float, z: float) -> BoxMesh:
	var m: BoxMesh = BoxMesh.new()
	m.size = Vector3(x, y, z)
	return m


func _material(color: Color) -> StandardMaterial3D:
	var m: StandardMaterial3D = StandardMaterial3D.new()
	m.albedo_color = color
	m.roughness = 0.65
	return m


## Colori deterministici dal nome: la stessa gara si rivede sempre uguale.
func _team_color(team: String) -> Color:
	return Color.from_hsv(float(absi(hash(team)) % 360) / 360.0, 0.75, 0.9)


func _skin_color(athlete: String) -> Color:
	var tones: Array[Color] = [
		Color(0.96, 0.8, 0.69), Color(0.85, 0.65, 0.5), Color(0.66, 0.46, 0.33), Color(0.42, 0.29, 0.2)]
	return tones[absi(hash(athlete)) % tones.size()]


# --- posa ---------------------------------------------------------------------------------------

## `crouch` = 1 ai blocchi (posizione "set"), 0 in corsa. Tutti gli angoli sono interpolati.
func _apply_pose(distance: float, amp: float) -> void:
	var crouch: float = clampf(1.0 - distance / CROUCH_DISTANCE, 0.0, 1.0)
	_hips.position.y = lerpf(HIP_HEIGHT + 0.04 * absf(sin(_phase)) * amp, CROUCH_HIP_HEIGHT, crouch)
	_torso.rotation.z = lerpf(-(0.12 + 0.25 * amp), -0.95, crouch)

	for leg: Dictionary in _legs:
		var side: float = leg["side"]
		var a: float = _phase + (0.0 if side > 0.0 else PI)
		var thigh_run: float = 0.85 * amp * sin(a) + 0.15 * amp
		var knee_run: float = -(0.1 + amp * 1.5 * maxf(0.0, cos(a + 0.4)))
		var thigh_set: float = 1.1 if side > 0.0 else -0.35
		var knee_set: float = -1.7 if side > 0.0 else -1.0
		(leg["thigh"] as Node3D).rotation.z = lerpf(thigh_run, thigh_set, crouch)
		(leg["shin"] as Node3D).rotation.z = lerpf(knee_run, knee_set, crouch)

	for arm: Dictionary in _arms:
		var side: float = arm["side"]
		var a: float = _phase + (PI if side > 0.0 else 0.0)  # braccio opposto alla gamba dello stesso lato
		var arm_run: float = 1.0 * amp * sin(a)
		var elbow_run: float = 1.4 * (0.6 + 0.4 * amp)
		(arm["upper"] as Node3D).rotation.z = lerpf(arm_run, 0.95, crouch)  # in "set" le braccia restano verticali
		(arm["fore"] as Node3D).rotation.z = lerpf(elbow_run, 0.0, crouch)
