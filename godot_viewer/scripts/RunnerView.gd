class_name RunnerView
extends Node3D
## VIEW 3D - atleta con scheletro (65 ossa) animato dalla Universal Animation Library di Quaternius (CC0).
## Legge `RunnerData` (distanza, velocita') e si limita a rappresentarlo: la posizione e' la distanza,
## l'animazione (accovacciato -> corsa -> camminata) e la sua cadenza dipendono dalla velocita'.
## Non influenza mai il risultato della gara.
##
## Il modello base e' quasi nudo: canotta e pantaloncini si ricavano dalla mesh del corpo (le scarpe sono mesh a parte, vedi CharacterDress.add_shoes)
## (triangoli selezionati per altezza, stessi pesi/scheletro, leggermente gonfiati) e si colorano con la squadra.
## Convenzione assi: pista lungo +X, su = +Y, corsie lungo +Z.

const LANE_WIDTH: float = 1.22

const CHARACTER_PATH: String = "res://assets/athlete/Superhero_Male_FullBody.gltf"
const CHARACTER_PATH_F: String = "res://assets/athlete/Superhero_Female_FullBody.gltf"
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

const PLAYER_MARKER_COLOR: Color = Color(1.0, 0.86, 0.12)

var data: RunnerData = null

var _model: Node3D
var _skeleton: Skeleton3D
var _player: AnimationPlayer
var _current_anim: StringName = &""
var _rig: SetPoseRig = null           # posizione ai blocchi (pronti/set), attiva prima della partenza
var _posture_mod: SprintPostureModifier = null
var _baton: MeshInstance3D = null
var _shot_rig: ShotPutRig = null        # getto del peso: posa a mano dello scheletro (vedi ShotPutRig)
var _shot_ball: MeshInstance3D = null    # il peso in mano all'atleta, finche' non lo rilascia
var _shot_pose: ShotPutMotion.Pose = null
var _player_marker: MeshInstance3D = null
var _head_bone_idx: int = -1
var _relay_leg: int = -1               # -1 = gara individuale; 0..3 = frazione della staffetta
var _relay_leg_len: float = 100.0
var _wait_lat: float = -2.0            # staffetta: scostamento a cui aspetta il cambio (calcolato una volta, vedi _lateral_for)
var _done_lat: float = -2.0            # staffetta: scostamento a cui si ferma dopo aver passato il testimone
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

	var body: MeshInstance3D = CharacterDress.find_body_mesh(_skeleton)
	var height: float = _dress(body)
	_attach_hair()
	if runner.is_player:
		_head_bone_idx = _skeleton.find_bone("Head")
		_attach_player_marker()
	if _relay_leg >= 0:
		_attach_baton()
	var target_height: float = RunnerData.visual_height(_visual_key, runner.gender)
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
		if visible and RaceController.event_kind == "Getto del Peso" and RaceController.shot_pose != null:
			_update_shot_pose(RaceController.shot_pose)
			return
		if visible:
			_stop_shot_rig()
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


# --- getto del peso -----------------------------------------------------------------------------

## Tentativo animato: la posa arriva da ShotPutMotion (modello puro) ed e' applicata da ShotPutRig. Ingresso e uscita a
## piedi usano la camminata della libreria con il peso al collo (IK delle sole braccia); dalla posizione iniziale in poi lo
## scheletro e' tutto del rig e l'AnimationPlayer e' fermo.
func _update_shot_pose(p: ShotPutMotion.Pose) -> void:
	if _shot_rig == null:
		_shot_rig = ShotPutRig.new()
		add_child(_shot_rig)
		_shot_rig.setup(_skeleton)
		_make_shot_ball()
		_skeleton.skeleton_updated.connect(_place_shot_ball)
	_rig.set_enabled(false)
	_shot_pose = p
	position = p.root
	rotation.y = p.yaw
	_model.rotation.x = 0.0
	_model.position = Vector3.ZERO
	if _posture_mod != null:
		_posture_mod.active_weight = 0.0
	var rig_mode: int = _shot_rig.apply(p)
	if rig_mode == ShotPutRig.RigMode.FULL:
		if _player.is_playing():
			_player.stop()
		_current_anim = &""
	elif p.mode == ShotPutMotion.Mode.IDLE:
		_play(&"Idle", 0.2)
		_player.speed_scale = RaceController.play_speed()
	else:
		_play(&"Walk", 0.2)
		var length: float = _player.get_animation(&"Walk").length
		_player.speed_scale = clampf(p.walk_speed / STRIDE_WALK * length * RaceController.play_speed(), 0.25, 8.0)
	_update_player_marker()


## Il peso e' un nodo "top level" (coordinate di mondo): lo posiziona _place_shot_ball sul polso destro dopo l'IK.
func _make_shot_ball() -> void:
	var plan: ShotPutMotion.Plan = RaceController.shot_plan
	var radius: float = plan.ball_r if plan != null else ShotPutMotion.BALL_RADIUS_M
	var ball: SphereMesh = SphereMesh.new()
	ball.radius = radius
	ball.height = radius * 2.0
	ball.radial_segments = 24
	ball.rings = 12
	var mat: StandardMaterial3D = StandardMaterial3D.new()
	mat.albedo_color = Color(0.86, 0.89, 0.94)
	mat.metallic = 0.45
	mat.roughness = 0.22
	ball.material = mat
	_shot_ball = MeshInstance3D.new()
	_shot_ball.mesh = ball
	_shot_ball.top_level = true
	_shot_ball.visible = false
	add_child(_shot_ball)


## Dopo lo scheletro aggiornato (`skeleton_updated`: la posa finale, IK compreso) il peso segue il polso destro: centro del
## peso = polso reale + scarto voluto dal modello (collo -> rilascio). Al rilascio il polso e' sul bersaglio, quindi il peso
## parte da R (a meno dell'errore dell'IK).
func _place_shot_ball() -> void:
	if _shot_ball == null:
		return
	var show: bool = visible and _shot_pose != null and _shot_pose.ball_in_hand and RaceController.event_kind == "Getto del Peso"
	_shot_ball.visible = show
	if show:
		var wrist: Vector3 = _skeleton.global_transform * _skeleton.get_bone_global_pose(_skeleton.find_bone("hand_r")).origin
		_shot_ball.global_position = wrist + _shot_pose.ball_off


## Torna all'animazione normale (nei tentativi non animati e quando cambia l'atleta in pedana).
func _stop_shot_rig() -> void:
	_shot_pose = null
	if _shot_rig != null and _shot_rig.rig_mode != ShotPutRig.RigMode.OFF:
		_shot_rig.set_rig_mode(ShotPutRig.RigMode.OFF)
		_current_anim = &""
	if _shot_ball != null:
		_shot_ball.visible = false


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
	var pose: Dictionary = TrackGeometry.runner_pose(RaceController.event_kind, data.lane, d, _lateral_for())
	position = pose["position"]
	rotation.y = pose["yaw"]


## Scostamento laterale dalla corda (-1 = nessuna formazione). Una frazione di staffetta che NON corre (aspetta il cambio, o ha gia' passato il testimone) sta ferma:
## lo scostamento della squadra continua a cambiare (sorpassi, rientro), quindi la si ferma a quello che la squadra ha nell'istante in cui il portatore arriva a lei
## (aspetta) o in cui lascia la sua zona (ha passato). E' una funzione pura del tempo (si calcola una volta) e coincide con quello della squadra nel momento in cui parte.
func _lateral_for() -> float:
	if _relay_leg < 0 or data.lateral < 0.0:
		return data.lateral
	var leg_start: float = float(_relay_leg) * _relay_leg_len
	var leg_end: float = leg_start + _relay_leg_len
	var td: float = data.distance
	if _relay_leg > 0 and td < leg_start - minf(8.0, _relay_leg_len * 0.08):
		if _wait_lat < -1.0:
			_wait_lat = RaceController.lateral_when_reaching(data, leg_start - minf(8.0, _relay_leg_len * 0.08))
		return _wait_lat
	if _relay_leg < 3 and td > leg_end + 8.0:
		if _done_lat < -1.0:
			_done_lat = RaceController.lateral_when_reaching(data, leg_end + 8.0)
		return _done_lat
	return data.lateral


# --- animazione ---------------------------------------------------------------------------------

func _setup_animation() -> void:
	_player = AnimationPlayer.new()
	_model.add_child(_player)  # root_node di default = ".." = _model: le tracce "Armature/Skeleton3D:..." combaciano
	_player.add_animation_library(&"", CharacterDress.animation_library())


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

## Colora la pelle, aggiunge canotta, pantaloncini e scarpe. Ritorna l'altezza del modello a riposo (m).
func _dress(body: MeshInstance3D) -> float:
	CharacterDress.apply_skin(body, data.gender, absi(hash(_visual_key)) % 4)
	var ext: Vector2 = CharacterDress.body_extent(body)
	var min_y: float = ext.x
	var h: float = ext.y

	var team: Color = _team_color(data.team_name)
	# Bounds = (|x| max, y min, y max) in altezze corporee (y: 0 piedi .. 1 cima della testa), a riposo.
	# Pettorale davanti e dietro, stampato sulla canotta (0 = nessuno: canotta liscia come prima, es. DB esportati senza numeri).
	var bib_print: Dictionary = {}
	if data.bib > 0:
		var bib_rect: Vector4 = BibPrint.rect()
		bib_print = {"tex": BibPrint.make_texture(self, data.bib), "back": bib_rect, "front": bib_rect, "tex_color": true}
	CharacterDress.add_cloth(_skeleton, body, min_y, h, Vector3(0.115, 0.60, 0.82), team, 0.006, 0.8, bib_print)           # canotta
	CharacterDress.add_cloth(_skeleton, body, min_y, h, Vector3(0.115, 0.43, 0.60), team.darkened(0.55), 0.007)           # pantaloncini
	# Scarpe vere (non piu' uno strato bianco sulla pelle del piede): tomaia bianca, scura o grigia a scelta dal nome, striscia della squadra.
	var shoe_pick: int = absi(hash(_visual_key + "scarpe")) % 3
	var shoe_upper: Color = [Color(0.96, 0.96, 0.96), Color(0.10, 0.10, 0.12), Color(0.78, 0.80, 0.84)][shoe_pick]
	var shoe_sole: Color = Color(0.93, 0.93, 0.93) if shoe_pick == 1 else Color(0.13, 0.13, 0.15)
	CharacterDress.add_shoes(_skeleton, body, shoe_upper, team, shoe_sole)
	return h


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
	CharacterDress.attach_hair(_skeleton, data.gender, _visual_key)


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
