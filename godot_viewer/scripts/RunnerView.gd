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
const CHARACTER_PATH_F: String = "res://assets/athlete/Superhero_Female_FullBody.gltf"
const ANIMATION_PATH: String = "res://assets/athlete/UAL1_Standard.glb"
const SKIN_LIGHT_PATH: String = "res://assets/athlete/T_Superhero_Male_Light.png"
const SKIN_DARK_PATH: String = "res://assets/athlete/T_Superhero_Male_Dark.png"
const SKIN_LIGHT_PATH_F: String = "res://assets/athlete/T_Superhero_Female_Light_BaseColor.png"
const SKIN_DARK_PATH_F: String = "res://assets/athlete/T_Superhero_Female_Dark_BaseColor.png"
const HAIR_PATHS: Array[String] = [
	"res://assets/athlete/Hair_Buzzed.gltf",
	"res://assets/athlete/Hair_SimpleParted.gltf",
]
const HAIR_PATHS_F: Array[String] = [
	"res://assets/athlete/Hair_Long.gltf",
	"res://assets/athlete/Hair_Buns.gltf",
]

## Il modello guarda verso +Z (convenzione glTF): lo giriamo di 90 gradi per farlo correre verso +X.
const FACING_Y: float = PI * 0.5

## Metri percorsi per ciclo completo (2 passi) di ogni animazione: ricava la cadenza dalla velocita'.
## La corsa (Sprint) non ha piu' una costante: la cadenza viene da StrideModel (evento, fase di gara, altezza).
const STRIDE_JOG: float = 3.2
const STRIDE_WALK: float = 1.5
const SPRINT_FROM: float = 7.0   # m/s: da qui in su "Sprint"
const SPRINT_BACK_TO_JOG: float = 6.0  # isteresi per evitare lo sfarfallio tra due animazioni
const WALK_BELOW: float = 2.5
const BLEND_TIME: float = 0.25
const BLOCK_START_BLEND: float = 0.06
const DRIVE_LEAN_MAX: float = deg_to_rad(26.0)   # inclinazione in avanti in uscita dai blocchi
const DRIVE_RISE_METERS: float = 16.0            # metri su cui il busto si raddrizza gradualmente

static var _animation_library: AnimationLibrary = null
static var _cloth_shader_cache: Shader = null
const PLAYER_MARKER_COLOR: Color = Color(1.0, 0.86, 0.12)

var data: RunnerData = null

var _model: Node3D
var _skeleton: Skeleton3D
var _player: AnimationPlayer
var _current_anim: StringName = &""
var _rig: SetPoseRig = null           # posizione ai blocchi (pronti/set), attiva prima della partenza
var _posture_mod: SprintPostureModifier = null
var _baton: MeshInstance3D = null
var _player_marker: MeshInstance3D = null
var _head_bone_idx: int = -1
var _relay_leg: int = -1               # -1 = gara individuale; 0..3 = frazione della staffetta
var _relay_leg_len: float = 100.0
var _visual_key: String = ""
var _height_m: float = StrideModel.REF_HEIGHT   # altezza visiva del modello: regola la cadenza (StrideModel)
var set_amount_override: float = -1.0  # solo per prove: forza pronti(0)..set(1); -1 = la decide RaceController


func setup(runner: RunnerData, relay_leg: int = -1, leg_len: float = 100.0, visual_name: String = "") -> void:
	data = runner
	_relay_leg = relay_leg
	_relay_leg_len = leg_len
	_visual_key = visual_name if not visual_name.is_empty() else runner.athlete_name
	_apply_transform()

	var is_female: bool = runner.gender == "F"
	var char_path: String = CHARACTER_PATH_F if is_female else CHARACTER_PATH
	_model = (load(char_path) as PackedScene).instantiate() as Node3D
	_model.rotation.y = FACING_Y
	add_child(_model)
	_skeleton = _model.find_child("Skeleton3D", true, false) as Skeleton3D

	var body: MeshInstance3D = _find_body_mesh()
	var height: float = _dress(body)
	_attach_hair()
	if runner.is_player:
		_head_bone_idx = _skeleton.find_bone("Head")
		_attach_player_marker()
	if _relay_leg >= 0:
		_attach_baton()
	var base_h: float = 1.63 if is_female else 1.72
	var target_height: float = base_h + float(absi(hash(_visual_key + "height")) % 15) / 100.0
	_model.scale = Vector3.ONE * (target_height / height)
	_height_m = target_height

	_setup_animation()
	_posture_mod = SprintPostureModifier.new()
	_skeleton.add_child(_posture_mod)
	_rig = SetPoseRig.new()
	add_child(_rig)
	_rig.setup(_model, _skeleton)
	_play(&"Idle" if (_relay_leg > 0 or not RaceController.uses_blocks(RaceController.event_kind)) else &"Crouch_Idle")


func _process(_delta: float) -> void:
	if data == null:
		return
	if RaceController.is_field(RaceController.event_kind):
		visible = (data == RaceController.active_jumper)
		if visible:
			_rig.set_enabled(false)
			position = RaceController.jumper_pos
			rotation.y = RaceController.jumper_yaw
			_model.rotation.x = 0.0
			_model.position = Vector3.ZERO
			_play(RaceController.jumper_anim, 0.12)
			if _posture_mod != null:
				_posture_mod.active_weight = 1.0 if _current_anim == &"Sprint" else 0.0
			_player.speed_scale = RaceController.jumper_speed_scale * RaceController.time_scale
			_update_player_marker()
		return
	visible = true
	var st: Vector2 = _leg_state()
	_apply_transform(st.x)
	_update_animation(st.x, st.y)
	_update_player_marker()


func _leg_state() -> Vector2:
	if _relay_leg < 0:
		return Vector2(data.distance, data.speed)
	var td: float = data.distance
	var ts: float = data.speed
	var leg_start: float = float(_relay_leg) * _relay_leg_len
	var leg_end: float = leg_start + _relay_leg_len
	var accel_zone: float = minf(8.0, _relay_leg_len * 0.08)
	var has_baton: bool = (_relay_leg == 0 or td >= leg_start) and (_relay_leg == 3 or td < leg_end)
	if data.dq and td >= RaceMotion.dnf_stop_distance(RaceController.event_kind):
		has_baton = false
	if _baton != null:
		_baton.visible = has_baton
	if _relay_leg > 0 and td < leg_start - accel_zone:
		return Vector2(leg_start - accel_zone, 0.0)
	if _relay_leg > 0 and td < leg_start:
		var p: float = (td - (leg_start - accel_zone)) / accel_zone
		var dist: float = lerpf(leg_start - accel_zone, leg_start, smoothstep(0.0, 1.0, p))
		return Vector2(dist, ts * (0.35 + 0.65 * p))
	if _relay_leg < 3 and td > leg_end:
		var over: float = td - leg_end
		var dec: float = exp(-over / 5.0)
		return Vector2(leg_end + 8.0 * (1.0 - dec), 7.5 * dec)
	return Vector2(td, ts)


## Posizione e orientamento in pista: rettilineo dei 100m, oppure anello da 400 m con partenza sfalsata.
func _apply_transform(leg_dist: float = -1.0) -> void:
	var d: float = data.distance if leg_dist < 0.0 else leg_dist
	var pose: Dictionary = TrackGeometry.runner_pose(RaceController.event_kind, data.lane, d)
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


func _update_animation(leg_dist: float = -1.0, leg_speed: float = -1.0) -> void:
	var d: float = data.distance if leg_dist < 0.0 else leg_dist
	var s: float = data.speed if leg_speed < 0.0 else leg_speed
	var want: StringName
	var standing: bool = (not RaceController.uses_blocks(RaceController.event_kind)) or _relay_leg > 0
	var at_blocks: bool = (not standing) and s < 0.01 and d < 0.01
	var just_left_blocks: bool = false
	if at_blocks != _rig.enabled:
		_rig.set_enabled(at_blocks)
		if at_blocks:
			_player.stop()         # le ossa le comanda SetPoseRig finche' si e' ai blocchi
		else:
			_current_anim = &""    # alla partenza riparte subito la corsa in spinta
			just_left_blocks = true
	if at_blocks:
		_model.rotation.x = 0.0
		_model.position = Vector3.ZERO
		if _posture_mod != null:
			_posture_mod.active_weight = 0.0
		_rig.update(set_amount_override if set_amount_override >= 0.0 else RaceController.set_amount())
		return
	if standing and s < 0.05:
		_model.rotation.x = 0.0
		_model.position = Vector3.ZERO
		if _posture_mod != null:
			_posture_mod.active_weight = 0.0
		_play(&"Idle")
		_player.speed_scale = RaceController.play_speed()
		return

	# Inclinazione in avanti nella fase di spinta fuori dai blocchi: si raddrizza gradualmente sui primi ~16 m.
	var drive: float = 0.0 if (standing or data.finished) else (1.0 - smoothstep(0.0, DRIVE_RISE_METERS, d))
	if data.dnf and s < SPRINT_FROM:
		drive *= clampf(s / SPRINT_FROM, 0.0, 1.0)
	_model.rotation.x = DRIVE_LEAN_MAX * drive
	_model.position = Vector3(0.0, 0.08 * drive, 0.0)

	# In uscita dai blocchi si parte direttamente in Sprint (mai Walk/Jog); Walk/Jog restano solo in rallentamento.
	var handed_off: bool = _relay_leg >= 0 and _relay_leg < 3 and data.distance > float(_relay_leg + 1) * _relay_leg_len
	var slowing: bool = data.finished or handed_off or (data.dnf and d > 10.0)
	if slowing and s < 0.3 and d > 1.0:
		want = &"Idle"  # fermo dopo il traguardo o dopo il ritiro
	elif not slowing or s >= SPRINT_FROM or (_current_anim == &"Sprint" and s >= SPRINT_BACK_TO_JOG):
		want = &"Sprint"
	elif s < WALK_BELOW:
		want = &"Walk"
	else:
		want = &"Jog_Fwd"
	_play(want, BLOCK_START_BLEND if just_left_blocks else BLEND_TIME)
	if _posture_mod != null:
		_posture_mod.active_weight = 1.0 if _current_anim == &"Sprint" else 0.0

	var stride: float = 1.0
	match _current_anim:
		&"Sprint": stride = _sprint_cycle_length(d, s)
		&"Jog_Fwd": stride = STRIDE_JOG
		&"Walk": stride = STRIDE_WALK
	if _current_anim == &"Crouch_Idle" or _current_anim == &"Idle":
		_player.speed_scale = RaceController.play_speed()
	else:
		var length: float = _player.get_animation(_current_anim).length
		_player.speed_scale = clampf(s / stride * length * RaceController.play_speed(), 0.25, 8.0)


## Metri per ciclo della corsa: cadenza e ampiezza da StrideModel (evento, punto della gara, altezza). Nelle staffette la
## frazione e' un tratto di 100/400 m: le frazioni dalla 2a in poi hanno gia' il testimone in corsa (partenza lanciata).
func _sprint_cycle_length(d: float, speed: float) -> float:
	var kind: String = RaceController.event_kind
	var local: float = d
	if _relay_leg >= 0:
		local = maxf(0.0, d - float(_relay_leg) * _relay_leg_len) + (StrideModel.FLYING_START_OFFSET if _relay_leg > 0 else 0.0)
	if not StrideModel.is_supported(kind):
		return 4.6   # evento senza curva (non dovrebbe succedere: le gare in pista sono tutte coperte)
	return StrideModel.cycle_length(kind, local, speed, _height_m)


func _play(anim: StringName, blend: float = BLEND_TIME) -> void:
	if anim == _current_anim:
		return
	_current_anim = anim
	_player.play(anim, blend)


# --- vestiti e capelli --------------------------------------------------------------------------

func _find_body_mesh() -> MeshInstance3D:
	for name_try: String in ["Superhero_Female", "SuperHero_Male"]:
		var n: Node = _skeleton.get_node_or_null(name_try)
		if n is MeshInstance3D:
			return n as MeshInstance3D
	for child: Node in _skeleton.get_children():
		if child is MeshInstance3D and not child.name in ["Eyebrows", "Eyes"]:
			return child as MeshInstance3D
	return null


## Colora la pelle, aggiunge canotta/pantaloncini/scarpette. Ritorna l'altezza del modello a riposo (m).
func _dress(body: MeshInstance3D) -> float:
	var skin: StandardMaterial3D = body.get_active_material(0).duplicate() as StandardMaterial3D
	var tone: int = absi(hash(_visual_key)) % 4
	var light_tex: String = SKIN_LIGHT_PATH_F if data.gender == "F" else SKIN_LIGHT_PATH
	var dark_tex: String = SKIN_DARK_PATH_F if data.gender == "F" else SKIN_DARK_PATH
	skin.albedo_texture = load(light_tex if tone < 2 else dark_tex) as Texture2D
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
	for ci: int in [Mesh.ARRAY_CUSTOM0, Mesh.ARRAY_CUSTOM1, Mesh.ARRAY_CUSTOM2, Mesh.ARRAY_CUSTOM3]:
		arrays[ci] = null
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


func _update_player_marker() -> void:
	if _player_marker == null or _skeleton == null or _head_bone_idx < 0:
		return
	var head_world: Vector3 = _skeleton.to_global(_skeleton.get_bone_global_pose(_head_bone_idx).origin)
	_player_marker.global_position = head_world + Vector3(0.0, 0.45, 0.0)


func _attach_player_marker() -> void:
	var mesh: ArrayMesh = ArrayMesh.new()
	var add_tri := func(half_w: float, half_h: float, z: float, col: Color) -> void:
		var arr: Array = []
		arr.resize(Mesh.ARRAY_MAX)
		arr[Mesh.ARRAY_VERTEX] = PackedVector3Array([
			Vector3(-half_w, half_h, z),
			Vector3(half_w, half_h, z),
			Vector3(0.0, -half_h, z),
		])
		arr[Mesh.ARRAY_INDEX] = PackedInt32Array([0, 1, 2])
		var surf_idx: int = mesh.get_surface_count()
		mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arr)
		var mat: StandardMaterial3D = StandardMaterial3D.new()
		mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		mat.billboard_mode = BaseMaterial3D.BILLBOARD_ENABLED
		mat.cull_mode = BaseMaterial3D.CULL_DISABLED
		mat.albedo_color = col
		mesh.surface_set_material(surf_idx, mat)

	add_tri.call(0.18, 0.16, -0.005, Color(0.06, 0.09, 0.16))
	add_tri.call(0.15, 0.135, 0.005, PLAYER_MARKER_COLOR)

	_player_marker = MeshInstance3D.new()
	_player_marker.mesh = mesh
	_player_marker.position = Vector3(0.0, 2.15, 0.0)
	_player_marker.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(_player_marker)


func _attach_hair() -> void:
	var pool: Array[String] = HAIR_PATHS_F if data.gender == "F" else HAIR_PATHS
	var path: String = pool[absi(hash(_visual_key + "hair")) % pool.size()]
	var scene: Node = (load(path) as PackedScene).instantiate()
	var hair: MeshInstance3D = scene.find_children("*", "MeshInstance3D", true, false)[0] as MeshInstance3D
	hair.get_parent().remove_child(hair)
	scene.free()
	_skeleton.add_child(hair)  # stesse 65 ossa del corpo: la skin si lega per nome
	var mat: StandardMaterial3D = hair.get_active_material(0).duplicate() as StandardMaterial3D
	var tones: Array[Color] = [
		Color(0.05, 0.04, 0.035), Color(0.2, 0.11, 0.06), Color(0.42, 0.27, 0.12), Color(0.8, 0.62, 0.3)]
	mat.albedo_color = tones[absi(hash(_visual_key + "shade")) % tones.size()]
	hair.set_surface_override_material(0, mat)


func _attach_baton() -> void:
	var attach: BoneAttachment3D = BoneAttachment3D.new()
	attach.bone_name = &"hand_r"
	_skeleton.add_child(attach)
	var mesh: CylinderMesh = CylinderMesh.new()
	mesh.top_radius = 0.018
	mesh.bottom_radius = 0.018
	mesh.height = 0.30
	var mat: StandardMaterial3D = StandardMaterial3D.new()
	mat.albedo_color = Color(0.98, 0.80, 0.15)
	mat.metallic = 0.7
	mat.roughness = 0.25
	mesh.material = mat
	_baton = MeshInstance3D.new()
	_baton.mesh = mesh
	_baton.rotation_degrees = Vector3(90.0, 0.0, 0.0)
	_baton.visible = (_relay_leg == 0)
	attach.add_child(_baton)


## Colori deterministici dal nome: la stessa gara si rivede sempre uguale.
func _team_color(team: String) -> Color:
	return Color.from_hsv(float(absi(hash(team)) % 360) / 360.0, 0.75, 0.9)


## Raddrizza la parte alta della schiena nell'animazione Sprint (che altrimenti curva spine_02/03 a ~49°).
class SprintPostureModifier:
	extends SkeletonModifier3D

	var active_weight: float = 0.0

	func _process_modification() -> void:
		if active_weight <= 0.001:
			return
		var skel: Skeleton3D = get_skeleton()
		if skel == null:
			return
		_pitch_bone(skel, "spine_01", deg_to_rad(-6.0) * active_weight)
		_pitch_bone(skel, "spine_02", deg_to_rad(-9.0) * active_weight)
		_pitch_bone(skel, "spine_03", deg_to_rad(-10.0) * active_weight)
		_pitch_bone(skel, "neck_01", deg_to_rad(-4.0) * active_weight)
		_pitch_bone(skel, "Head", deg_to_rad(12.0) * active_weight)

	static func _pitch_bone(skel: Skeleton3D, bone_name: String, delta_rad: float) -> void:
		var idx: int = skel.find_bone(bone_name)
		if idx < 0:
			return
		var parent: int = skel.get_bone_parent(idx)
		var parent_basis: Basis = skel.get_bone_global_pose(parent).basis if parent >= 0 else Basis.IDENTITY
		var desired_basis: Basis = Basis(Vector3.RIGHT, delta_rad) * skel.get_bone_global_pose(idx).basis
		var local_basis: Basis = parent_basis.inverse() * desired_basis
		skel.set_bone_pose_rotation(idx, local_basis.get_rotation_quaternion())
