class_name TrackSideCrew
extends RefCounted
## VIEW 3D - personale a bordo pista: fotografi vicino al traguardo e giudici d'arrivo. Figure STATICHE a forme semplici
## (scatole e sfere): servono a dare vita alla scena, non a essere guardate da vicino.
##
## Posti scelti per NON coprire gli atleti: i giudici stanno a z >= 14 (la camera del traguardo e il carrello guardano la
## corsia 8 da fuori: una figura piu' vicina la nasconderebbe); i fotografi dentro il campo stanno dietro i cartelloni (z = -3.4).
## Solo per le corse in pista: nei concorsi la camera del salto in lungo sta proprio li' (-12; 3,4; -3,5).

const SKINS: Array[Color] = [Color(0.94, 0.76, 0.64), Color(0.82, 0.6, 0.45), Color(0.62, 0.42, 0.3), Color(0.38, 0.25, 0.17)]
const SHIRTS: Array[Color] = [Color(0.12, 0.12, 0.15), Color(0.2, 0.25, 0.4), Color(0.55, 0.12, 0.12), Color(0.85, 0.85, 0.82)]
const VEST: Color = Color(0.95, 0.55, 0.08)      # pettorina arancione dei giudici
const TROUSERS: Color = Color(0.13, 0.14, 0.2)


static func build(parent: Node3D) -> void:
	var rng: RandomNumberGenerator = RandomNumberGenerator.new()
	rng.seed = 2024   # deterministico: stessa scena a ogni gara
	# Fotografi inginocchiati dietro i cartelloni del campo, nel tratto d'arrivo.
	for x: float in [-16.0, -11.0, -6.5, -2.5]:
		_photographer(parent, Vector3(x + rng.randf_range(-0.6, 0.6), 0.0, -3.5), PI * 0.5 * 0.0, true, rng)
	# Fotografi in piedi appena oltre il traguardo, fuori dalla pista (la curva si allontana da z = 9,15).
	for p: Vector2 in [Vector2(4.5, 12.5), Vector2(7.0, 13.5), Vector2(9.5, 12.8)]:
		_photographer(parent, Vector3(p.x, 0.0, p.y), PI, false, rng)
	# Giudici d'arrivo dietro un tavolo, fuori dalla pista.
	_judge_table(parent, Vector3(-4.5, 0.0, 15.2))
	for x: float in [-7.0, -5.0, -3.0, -1.0]:
		_person(parent, Vector3(x, 0.0, 16.4), PI, VEST, rng.randi() % SKINS.size(), false)


static func _judge_table(parent: Node3D, pos: Vector3) -> void:
	var top: MeshInstance3D = _box(parent, Vector3(8.0, 0.08, 1.0), pos + Vector3(0.0, 0.78, 0.0), Color(0.75, 0.75, 0.78))
	top.name = "JudgeTable"
	for dx: float in [-3.8, 3.8]:
		_box(parent, Vector3(0.08, 0.78, 0.9), pos + Vector3(dx, 0.39, 0.0), Color(0.45, 0.45, 0.5))


static func _photographer(parent: Node3D, pos: Vector3, yaw: float, kneeling: bool, rng: RandomNumberGenerator) -> void:
	var skin: int = rng.randi() % SKINS.size()
	_person(parent, pos, yaw, SHIRTS[rng.randi() % SHIRTS.size()], skin, kneeling)
	# Macchina con obiettivo davanti al viso, verso la pista (+Z locale = verso z positivi con yaw 0).
	var pivot: Node3D = Node3D.new()
	pivot.position = pos
	pivot.rotation.y = yaw
	parent.add_child(pivot)
	var h: float = 0.95 if kneeling else 1.5
	_box(pivot, Vector3(0.2, 0.14, 0.12), Vector3(0.0, h, 0.28), Color(0.06, 0.06, 0.07))
	_box(pivot, Vector3(0.1, 0.1, 0.3), Vector3(0.0, h, 0.48), Color(0.1, 0.1, 0.12))


## Persona stilizzata: gambe, busto colorato, testa. In ginocchio le gambe sono piu' corte.
static func _person(parent: Node3D, pos: Vector3, yaw: float, shirt: Color, skin_idx: int, kneeling: bool) -> void:
	var pivot: Node3D = Node3D.new()
	pivot.position = pos
	pivot.rotation.y = yaw
	parent.add_child(pivot)
	var leg_h: float = 0.45 if kneeling else 0.85
	_box(pivot, Vector3(0.34, leg_h, 0.24), Vector3(0.0, leg_h * 0.5, 0.0), TROUSERS)
	var torso_h: float = 0.6
	_box(pivot, Vector3(0.44, torso_h, 0.26), Vector3(0.0, leg_h + torso_h * 0.5, 0.0), shirt)
	var head: MeshInstance3D = MeshInstance3D.new()
	var sphere: SphereMesh = SphereMesh.new()
	sphere.radius = 0.11
	sphere.height = 0.22
	head.mesh = sphere
	head.material_override = _mat(SKINS[skin_idx])
	head.position = Vector3(0.0, leg_h + torso_h + 0.13, 0.0)
	head.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	pivot.add_child(head)


static func _box(parent: Node3D, size: Vector3, pos: Vector3, color: Color) -> MeshInstance3D:
	var mesh: BoxMesh = BoxMesh.new()
	mesh.size = size
	var mi: MeshInstance3D = MeshInstance3D.new()
	mi.mesh = mesh
	mi.material_override = _mat(color)
	mi.position = pos
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	parent.add_child(mi)
	return mi


static func _mat(color: Color) -> StandardMaterial3D:
	var m: StandardMaterial3D = StandardMaterial3D.new()
	m.albedo_color = color
	m.roughness = 0.9
	return m
