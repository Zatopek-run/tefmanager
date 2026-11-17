class_name RunnerView
extends Node3D
## VIEW 3D - atleta con scheletro (65 ossa) animato dalla Universal Animation Library di Quaternius (CC0).
## Legge `RunnerData` (distanza, velocita') e si limita a rappresentarlo: la posizione e' la distanza,
## l'animazione (accovacciato -> corsa -> camminata) e la sua cadenza dipendono dalla velocita'.
## Non influenza mai il risultato della gara.
##
## Il modello base e' quasi nudo: canotta, pantaloncini e scarpette si ricavano dalla mesh del corpo
## (triangoli selezionati per altezza, stessi pesi/scheletro, leggermente gonfiati) e si colorano con la squadra.
## Convenzione assi: pista lungo +X, su = +Y, corsie lungo +Z.

const LANE_WIDTH: float = 1.22

const CHARACTER_PATH: String = "res://assets/athlete/Superhero_Male_FullBody.gltf"
const ANIMATION_PATH: String = "res://assets/athlete/UAL1_Standard.glb"
const SKIN_LIGHT_PATH: String = "res://assets/athlete/T_Superhero_Male_Light.png"
const SKIN_DARK_PATH: String = "res://assets/athlete/T_Superhero_Male_Dark.png"
const HAIR_PATHS: Array[String] = [
	"res://assets/athlete/Hair_Buzzed.gltf",
	"res://assets/athlete/Hair_SimpleParted.gltf",
]

## Il modello guarda verso +Z (convenzione glTF): lo giriamo di 90 gradi per farlo correre verso +X.
const FACING_Y: float = PI * 0.5

## Metri percorsi per ciclo completo (2 passi) di ogni animazione: ricava la cadenza dalla velocita'.
const STRIDE_SPRINT: float = 4.6
const STRIDE_JOG: float = 3.2
const STRIDE_WALK: float = 1.5
const SPRINT_FROM: float = 7.0   # m/s: da qui in su "Sprint"
const SPRINT_BACK_TO_JOG: float = 6.0  # isteresi per evitare lo sfarfallio tra due animazioni
const WALK_BELOW: float = 2.5
const BLEND_TIME: float = 0.25

static var _animation_library: AnimationLibrary = null
static var _cloth_shader_cache: Shader = null

var data: RunnerData = null

var _model: Node3D
var _skeleton: Skeleton3D
var _player: AnimationPlayer
var _current_anim: StringName = &""


func setup(runner: RunnerData) -> void:
	data = runner
	_apply_transform()

	_model = (load(CHARACTER_PATH) as PackedScene).instantiate() as Node3D
	_model.rotation.y = FACING_Y
	add_child(_model)
	_skeleton = _model.find_child("Skeleton3D", true, false) as Skeleton3D

	var body: MeshInstance3D = _skeleton.get_node("SuperHero_Male") as MeshInstance3D
	var height: float = _dress(body)
	_attach_hair()
	var target_height: float = 1.72 + float(absi(hash(runner.athlete_name + "height")) % 17) / 100.0
	_model.scale = Vector3.ONE * (target_height / height)

	_setup_animation()
	_play(&"Crouch_Idle")


func _process(_delta: float) -> void:
	if data == null:
		return
	_apply_transform()
	_update_animation()


## Posizione e orientamento in pista: rettilineo dei 100m, oppure anello da 400 m con partenza sfalsata.
func _apply_transform() -> void:
	if RaceController.event_kind == "100m":
		position = Vector3(data.distance, 0.0, (data.lane - 1) * LANE_WIDTH)
		rotation.y = 0.0
	else:
		var pose: Dictionary = TrackGeometry.pose(data.lane, data.distance)
		position = pose["position"]
		rotation.y = pose["yaw"]


# --- animazione ---------------------------------------------------------------------------------

func _setup_animation() -> void:
	if _animation_library == null:
		var ual: Node = (load(ANIMATION_PATH) as PackedScene).instantiate()
		var source: AnimationPlayer = ual.find_child("AnimationPlayer", true, false) as AnimationPlayer
		_animation_library = source.get_animation_library(&"")
		ual.free()
	_player = AnimationPlayer.new()
	_model.add_child(_player)  # root_node di default = ".." = _model: le tracce "Armature/Skeleton3D:..." combaciano
	_player.add_animation_library(&"", _animation_library)


func _update_animation() -> void:
	var s: float = data.speed
	var want: StringName
	if s < 0.01 and data.distance < 0.01:
		want = &"Crouch_Idle"
	elif s < 0.3 and data.distance > 1.0:
		want = &"Idle"  # fermo dopo il traguardo o dopo il ritiro
	elif s >= SPRINT_FROM or (_current_anim == &"Sprint" and s >= SPRINT_BACK_TO_JOG):
		want = &"Sprint"
	elif s < WALK_BELOW:
		want = &"Walk"
	else:
		want = &"Jog_Fwd"
	_play(want)

	var stride: float = 1.0
	match _current_anim:
		&"Sprint": stride = STRIDE_SPRINT
		&"Jog_Fwd": stride = STRIDE_JOG
		&"Walk": stride = STRIDE_WALK
	if _current_anim == &"Crouch_Idle" or _current_anim == &"Idle":
		_player.speed_scale = RaceController.time_scale
	else:
		var length: float = _player.get_animation(_current_anim).length
		_player.speed_scale = clampf(s / stride * length * RaceController.time_scale, 0.25, 8.0)


func _play(anim: StringName) -> void:
	if anim == _current_anim:
		return
	_current_anim = anim
	_player.play(anim, BLEND_TIME)


# --- vestiti e capelli --------------------------------------------------------------------------

## Colora la pelle, aggiunge canotta/pantaloncini/scarpette. Ritorna l'altezza del modello a riposo (m).
func _dress(body: MeshInstance3D) -> float:
	var skin: StandardMaterial3D = body.get_active_material(0).duplicate() as StandardMaterial3D
	var tone: int = absi(hash(data.athlete_name)) % 4
	skin.albedo_texture = load(SKIN_LIGHT_PATH if tone < 2 else SKIN_DARK_PATH) as Texture2D
	skin.albedo_color = [Color(1, 1, 1), Color(0.82, 0.68, 0.56), Color(1, 1, 1), Color(0.8, 0.72, 0.68)][tone]
	body.set_surface_override_material(0, skin)

	var verts: PackedVector3Array = body.mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
	var min_y: float = INF
	var max_y: float = -INF
	for v: Vector3 in verts:
		min_y = minf(min_y, v.y)
		max_y = maxf(max_y, v.y)
	var h: float = max_y - min_y

	var team: Color = _team_color(data.team_name)
	# Bounds = (|x| max, y min, y max) in altezze corporee (y: 0 piedi .. 1 cima della testa), a riposo.
	_add_cloth(body, min_y, h, Vector3(0.115, 0.60, 0.82), team, 0.006)                          # canotta
	_add_cloth(body, min_y, h, Vector3(0.115, 0.43, 0.60), team.darkened(0.55), 0.007)           # pantaloncini
	_add_cloth(body, min_y, h, Vector3(1.0, -1.0, 0.045), Color(0.96, 0.96, 0.96), 0.012)        # scarpette
	return h


## Aggiunge un capo ricavato dalla mesh del corpo: stessi vertici/pesi (quindi stesse ossa), gonfiati lungo
## la normale. Ogni vertice porta in UV2 la sua posizione a riposo (x, y in altezze corporee) e lo shader
## scarta i pixel fuori da `bounds`: il bordo e' netto anche se la mesh ha pochi triangoli.
func _add_cloth(body: MeshInstance3D, base_y: float, height: float, bounds: Vector3, color: Color, inflate: float) -> void:
	var src: Mesh = body.mesh
	var arrays: Array = src.surface_get_arrays(0)
	var verts: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var normals: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL]
	var index: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]

	var grown: PackedVector3Array = verts.duplicate()
	var rel: PackedVector2Array = PackedVector2Array()
	rel.resize(verts.size())
	for i in range(verts.size()):
		grown[i] = verts[i] + normals[i] * inflate
		rel[i] = Vector2(verts[i].x / height, (verts[i].y - base_y) / height)

	var kept: PackedInt32Array = PackedInt32Array()
	for t in range(0, index.size(), 3):
		var y0: float = rel[index[t]].y
		var y1: float = rel[index[t + 1]].y
		var y2: float = rel[index[t + 2]].y
		if minf(y0, minf(y1, y2)) <= bounds.z and maxf(y0, maxf(y1, y2)) >= bounds.y:
			kept.append(index[t])
			kept.append(index[t + 1])
			kept.append(index[t + 2])
	if kept.is_empty():
		push_warning("RunnerView: nessun triangolo per il capo %s" % str(color))
		return

	arrays[Mesh.ARRAY_VERTEX] = grown
	arrays[Mesh.ARRAY_INDEX] = kept
	arrays[Mesh.ARRAY_TEX_UV2] = rel
	var mesh: ArrayMesh = ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays, [], {},
		src.surface_get_format(0) & Mesh.ARRAY_FLAG_USE_8_BONE_WEIGHTS)

	var mat: ShaderMaterial = ShaderMaterial.new()
	mat.shader = _cloth_shader()
	mat.set_shader_parameter("color", color)
	mat.set_shader_parameter("bounds", bounds)
	mesh.surface_set_material(0, mat)

	var mi: MeshInstance3D = MeshInstance3D.new()
	mi.mesh = mesh
	mi.skin = body.skin
	_skeleton.add_child(mi)  # figlio dello scheletro: segue le stesse ossa del corpo


static func _cloth_shader() -> Shader:
	if _cloth_shader_cache == null:
		_cloth_shader_cache = Shader.new()
		_cloth_shader_cache.code = """
shader_type spatial;
uniform vec4 color : source_color = vec4(1.0);
uniform vec3 bounds = vec3(0.115, 0.6, 0.82); // |x| max, y min, y max (altezze corporee)
varying vec2 rel;
void vertex() { rel = UV2; }
void fragment() {
	if (abs(rel.x) > bounds.x || rel.y < bounds.y || rel.y > bounds.z) { discard; }
	ALBEDO = color.rgb;
	ROUGHNESS = 0.8;
}
"""
	return _cloth_shader_cache


func _attach_hair() -> void:
	var path: String = HAIR_PATHS[absi(hash(data.athlete_name + "hair")) % HAIR_PATHS.size()]
	var scene: Node = (load(path) as PackedScene).instantiate()
	var hair: MeshInstance3D = scene.find_children("*", "MeshInstance3D", true, false)[0] as MeshInstance3D
	hair.get_parent().remove_child(hair)
	scene.free()
	_skeleton.add_child(hair)  # stesse 65 ossa del corpo: la skin si lega per nome
	var mat: StandardMaterial3D = hair.get_active_material(0).duplicate() as StandardMaterial3D
	var tones: Array[Color] = [
		Color(0.05, 0.04, 0.035), Color(0.2, 0.11, 0.06), Color(0.42, 0.27, 0.12), Color(0.8, 0.62, 0.3)]
	mat.albedo_color = tones[absi(hash(data.athlete_name + "shade")) % tones.size()]
	hair.set_surface_override_material(0, mat)


## Colori deterministici dal nome: la stessa gara si rivede sempre uguale.
func _team_color(team: String) -> Color:
	return Color.from_hsv(float(absi(hash(team)) % 360) / 360.0, 0.75, 0.9)
