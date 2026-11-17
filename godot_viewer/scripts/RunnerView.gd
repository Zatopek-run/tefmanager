class_name RunnerView
extends Node3D
## VIEW 3D - atleta mid-poly costruito da primitive (nessun asset esterno).
## Legge `RunnerData` (distanza, velocita') e si limita a rappresentarlo: posizione = distanza,
## frequenza della falcata = velocita' / lunghezza del passo. Non influenza mai il risultato.
##
## Convenzione assi: pista lungo +X, su = +Y, corsie lungo +Z. Una rotazione positiva attorno a Z
## porta un arto che pende verso il basso in avanti (+X).
##
## Anatomia: arti rastremati (cilindri con raggio diverso alle estremita'), articolazioni sferiche,
## busto e testa ellissoidali, canotta + pantaloncini nei colori della squadra, pettorale con numero
## di corsia, scarpette bianche, capelli. Non e' un modello scolpito: per un realismo vero serve un
## personaggio con scheletro (glTF) e animazioni.

const LANE_WIDTH: float = 1.22
const BODY_SCALE: float = 0.92     # il modello costruito e' ~1,97 m: scala a ~1,81 m
const TOP_SPEED: float = 11.5      # m/s oltre cui l'ampiezza della falcata e' massima
const STRIDE_MIN: float = 2.0      # lunghezza del ciclo completo (2 passi) in partenza, m
const STRIDE_MAX: float = 4.4      # ...e a regime
const HIP_HEIGHT: float = 1.0
const CROUCH_HIP_HEIGHT: float = 0.66
const CROUCH_DISTANCE: float = 2.5 # a questa distanza dai blocchi il corridore e' gia' in piedi

var data: RunnerData = null

var _hips: Node3D
var _torso: Node3D
var _head: Node3D
var _legs: Array[Dictionary] = []  # {thigh, shin, foot, side}
var _arms: Array[Dictionary] = []  # {upper, fore, side}
var _phase: float = 0.0


func setup(runner: RunnerData) -> void:
	data = runner
	position = Vector3(0.0, 0.0, (runner.lane - 1) * LANE_WIDTH)
	scale = Vector3.ONE * BODY_SCALE
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
	var skin_color: Color = _skin_color(data.athlete_name)
	var skin: StandardMaterial3D = _material(skin_color, 0.55)
	var kit_color: Color = _team_color(data.team_name)
	var kit: StandardMaterial3D = _material(kit_color, 0.8)
	var shorts: StandardMaterial3D = _material(kit_color.darkened(0.5), 0.8)
	var hair: StandardMaterial3D = _material(_hair_color(data.athlete_name), 0.9)
	var shoe: StandardMaterial3D = _material(Color(0.96, 0.96, 0.96), 0.6)
	var sole: StandardMaterial3D = _material(kit_color.darkened(0.2), 0.7)
	var bib: StandardMaterial3D = _material(Color(0.97, 0.97, 0.94), 0.9)

	_hips = Node3D.new()
	_hips.position = Vector3(0.0, HIP_HEIGHT, 0.0)
	add_child(_hips)
	_ellipsoid(_hips, Vector3(0.11, 0.1, 0.175), shorts, Vector3(0.0, 0.0, 0.0))  # bacino

	_torso = Node3D.new()
	_torso.position = Vector3(0.0, 0.06, 0.0)
	_hips.add_child(_torso)
	_ellipsoid(_torso, Vector3(0.115, 0.17, 0.165), kit, Vector3(0.0, 0.14, 0.0))   # addome
	_ellipsoid(_torso, Vector3(0.14, 0.22, 0.2), kit, Vector3(0.0, 0.4, 0.0))       # torace
	for side: float in [1.0, -1.0]:  # pettorale: placca sottile sul fianco del torace + numero di corsia
		_ellipsoid(_torso, Vector3(0.1, 0.075, 0.012), bib, Vector3(0.0, 0.4, 0.2 * side))
		var number: Label3D = Label3D.new()
		number.text = str(data.lane)
		number.font_size = 72
		number.pixel_size = 0.0014
		number.modulate = Color(0.05, 0.05, 0.05)
		number.outline_size = 0
		number.position = Vector3(0.0, 0.4, 0.214 * side)
		if side < 0.0:
			number.rotation.y = PI
		_torso.add_child(number)

	# Collo, testa, capelli, naso, orecchie.
	_head = Node3D.new()
	_head.position = Vector3(0.0, 0.58, 0.0)
	_torso.add_child(_head)
	_segment(_head, 0.05, 0.055, -0.1, skin, Vector3.ZERO)                         # collo (cresce verso l'alto)
	_ellipsoid(_head, Vector3(0.105, 0.125, 0.095), skin, Vector3(0.025, 0.2, 0.0))  # testa
	_ellipsoid(_head, Vector3(0.11, 0.1, 0.1), hair, Vector3(0.0, 0.245, 0.0))      # capelli
	_ellipsoid(_head, Vector3(0.025, 0.03, 0.02), skin, Vector3(0.125, 0.19, 0.0))  # naso
	for side: float in [1.0, -1.0]:
		_ellipsoid(_head, Vector3(0.015, 0.03, 0.02), skin, Vector3(0.0, 0.2, 0.095 * side))  # orecchie

	for side: float in [1.0, -1.0]:
		# Braccio: spalla -> gomito -> mano.
		var shoulder: Node3D = Node3D.new()
		shoulder.position = Vector3(0.0, 0.54, 0.225 * side)
		_torso.add_child(shoulder)
		_ellipsoid(shoulder, Vector3(0.065, 0.065, 0.065), skin, Vector3.ZERO)                 # deltoide
		_segment(shoulder, 0.052, 0.042, 0.29, skin, Vector3.ZERO)                            # braccio
		var elbow: Node3D = Node3D.new()
		elbow.position = Vector3(0.0, -0.29, 0.0)
		shoulder.add_child(elbow)
		_ellipsoid(elbow, Vector3(0.042, 0.042, 0.042), skin, Vector3.ZERO)                   # gomito
		_segment(elbow, 0.045, 0.03, 0.26, skin, Vector3.ZERO)                                # avambraccio
		_ellipsoid(elbow, Vector3(0.035, 0.055, 0.025), skin, Vector3(0.0, -0.3, 0.0))        # mano
		_arms.append({"upper": shoulder, "fore": elbow, "side": side})

		# Gamba: anca -> ginocchio -> caviglia -> piede.
		var thigh: Node3D = Node3D.new()
		thigh.position = Vector3(0.0, -0.04, 0.1 * side)
		_hips.add_child(thigh)
		_segment(thigh, 0.098, 0.062, 0.46, skin, Vector3.ZERO)                               # coscia
		_segment(thigh, 0.108, 0.1, 0.2, shorts, Vector3.ZERO)                                # gamba del pantaloncino
		var knee: Node3D = Node3D.new()
		knee.position = Vector3(0.0, -0.46, 0.0)
		thigh.add_child(knee)
		_ellipsoid(knee, Vector3(0.058, 0.058, 0.058), skin, Vector3.ZERO)                    # ginocchio
		_segment(knee, 0.06, 0.036, 0.43, skin, Vector3.ZERO)                                 # stinco
		_ellipsoid(knee, Vector3(0.065, 0.11, 0.06), skin, Vector3(-0.02, -0.13, 0.0))        # polpaccio
		var ankle: Node3D = Node3D.new()
		ankle.position = Vector3(0.0, -0.43, 0.0)
		knee.add_child(ankle)
		_ellipsoid(ankle, Vector3(0.14, 0.05, 0.055), shoe, Vector3(0.055, -0.035, 0.0))      # scarpetta
		_ellipsoid(ankle, Vector3(0.14, 0.012, 0.058), sole, Vector3(0.06, -0.075, 0.0))      # suola
		_legs.append({"thigh": thigh, "shin": knee, "foot": ankle, "side": side})


## Cilindro rastremato appeso a `parent` con il punto alto in `pos`: `top_r` in alto, `bottom_r` in basso.
## `length` negativo = cresce verso l'alto (collo).
func _segment(parent: Node3D, top_r: float, bottom_r: float, length: float, mat: Material, pos: Vector3) -> MeshInstance3D:
	var m: CylinderMesh = CylinderMesh.new()
	m.top_radius = top_r
	m.bottom_radius = bottom_r
	m.height = absf(length)
	m.radial_segments = 14
	m.rings = 1
	var mi: MeshInstance3D = MeshInstance3D.new()
	mi.mesh = m
	mi.material_override = mat
	mi.position = pos + Vector3(0.0, -length * 0.5, 0.0)
	parent.add_child(mi)
	return mi


func _ellipsoid(parent: Node3D, radii: Vector3, mat: Material, pos: Vector3) -> MeshInstance3D:
	var m: SphereMesh = SphereMesh.new()
	m.radius = 1.0
	m.height = 2.0
	m.radial_segments = 20
	m.rings = 10
	var mi: MeshInstance3D = MeshInstance3D.new()
	mi.mesh = m
	mi.material_override = mat
	mi.scale = radii
	mi.position = pos
	parent.add_child(mi)
	return mi


func _material(color: Color, roughness: float) -> StandardMaterial3D:
	var m: StandardMaterial3D = StandardMaterial3D.new()
	m.albedo_color = color
	m.roughness = roughness
	return m


## Colori deterministici dal nome: la stessa gara si rivede sempre uguale.
func _team_color(team: String) -> Color:
	return Color.from_hsv(float(absi(hash(team)) % 360) / 360.0, 0.75, 0.9)


func _skin_color(athlete: String) -> Color:
	var tones: Array[Color] = [
		Color(0.94, 0.76, 0.64), Color(0.82, 0.6, 0.45), Color(0.62, 0.42, 0.3), Color(0.38, 0.25, 0.17)]
	return tones[absi(hash(athlete)) % tones.size()]


func _hair_color(athlete: String) -> Color:
	var tones: Array[Color] = [
		Color(0.06, 0.05, 0.04), Color(0.2, 0.12, 0.07), Color(0.4, 0.27, 0.13), Color(0.72, 0.58, 0.32)]
	return tones[absi(hash(athlete + "h")) % tones.size()]


# --- posa ---------------------------------------------------------------------------------------

## `crouch` = 1 ai blocchi (posizione "set"), 0 in corsa. Tutti gli angoli sono interpolati.
func _apply_pose(distance: float, amp: float) -> void:
	var crouch: float = clampf(1.0 - distance / CROUCH_DISTANCE, 0.0, 1.0)
	_hips.position.y = lerpf(HIP_HEIGHT + 0.045 * absf(sin(_phase)) * amp, CROUCH_HIP_HEIGHT, crouch)
	_hips.rotation.y = lerpf(-0.12 * amp * sin(_phase), 0.0, crouch)    # il bacino ruota...
	_torso.rotation.y = lerpf(0.2 * amp * sin(_phase), 0.0, crouch)      # ...e le spalle controruotano
	var lean: float = lerpf(-(0.1 + 0.22 * amp), -0.95, crouch)
	_torso.rotation.z = lean
	_head.rotation.z = -lean * lerpf(0.85, 0.55, crouch)                 # lo sguardo resta in avanti

	for leg: Dictionary in _legs:
		var side: float = leg["side"]
		var a: float = _phase + (0.0 if side > 0.0 else PI)
		var thigh_run: float = 0.95 * amp * sin(a) + 0.2 * amp
		var knee_run: float = -(0.12 + amp * 1.7 * maxf(0.0, cos(a + 0.5)))
		var foot_run: float = -0.45 * amp * sin(a + 0.9) - 0.1 * amp
		var thigh_set: float = 1.1 if side > 0.0 else -0.35
		var knee_set: float = -1.7 if side > 0.0 else -1.0
		var foot_set: float = 0.0 if side > 0.0 else -0.7
		(leg["thigh"] as Node3D).rotation.z = lerpf(thigh_run, thigh_set, crouch)
		(leg["shin"] as Node3D).rotation.z = lerpf(knee_run, knee_set, crouch)
		(leg["foot"] as Node3D).rotation.z = lerpf(foot_run, foot_set, crouch)

	for arm: Dictionary in _arms:
		var side: float = arm["side"]
		var a: float = _phase + (PI if side > 0.0 else 0.0)  # braccio opposto alla gamba dello stesso lato
		var arm_run: float = 1.15 * amp * sin(a) - 0.1 * amp
		var elbow_run: float = lerpf(0.35, 1.5, amp) + 0.25 * amp * sin(a + 0.6)
		(arm["upper"] as Node3D).rotation.z = lerpf(arm_run, 0.95, crouch)  # in "set" le braccia restano verticali
		(arm["fore"] as Node3D).rotation.z = lerpf(elbow_run, 0.0, crouch)
