class_name ShotPutRig
extends Node3D
## VIEW 3D - posa dell'atleta nel getto del peso, senza animazioni (la libreria Quaternius non ha un gesto di lancio).
## Stesso schema di SetPoseRig: bacino e schiena sono posati a mano (rotazioni globali in spazio scheletro), braccia e gambe
## con TwoBoneIK3D (mani sul peso, piedi piantati). Tutti i bersagli arrivano GIA' risolti in coordinate di mondo da
## `ShotPutMotion.pose_at` (modello puro): il rig non legge mai lo scheletro per decidere dove mettere le cose.
##
## Due modi (vedi `ShotPutMotion.Mode`): in WALK/IDLE le gambe le muove l'AnimationPlayer e l'IK comanda solo le braccia
## (peso al collo); in RIG lo scheletro e' tutto del rig (l'AnimationPlayer e' fermo). Con `arms_ik = false` (uscita) il rig e'
## spento e tutto torna all'animazione.
##
## Spazio scheletro: il modello guarda +Z, +Y e' su, +X e' la SINISTRA del personaggio. Una rotazione positiva attorno a Y gira
## verso la sinistra (antioraria vista dall'alto), come `yaw` in ShotPutMotion.

enum RigMode { OFF, ARMS, FULL }

const CONTROLLED_BONES: Array[String] = [
	"pelvis", "spine_01", "spine_02", "spine_03", "neck_01", "Head",
	"upperarm_l", "lowerarm_l", "hand_l", "upperarm_r", "lowerarm_r", "hand_r",
	"thigh_l", "calf_l", "foot_l", "thigh_r", "calf_r", "foot_r"]
## Quanto ogni osso della schiena segue l'inclinazione e la torsione (rotazioni globali: 1 = come il busto).
const PITCH_PELVIS: float = 0.5
const PITCH_SPINE: Array[float] = [0.75, 0.9, 1.0]
const TWIST_SPINE: Array[float] = [0.30, 0.65, 1.0]

var skeleton: Skeleton3D
var rig_mode: int = RigMode.OFF
var _ik_arms: TwoBoneIK3D
var _ik_legs: TwoBoneIK3D
var _foot_level: FootLevel
var _hand_aim: HandAim
var _fingers: FingerGrip
var _targets: Dictionary = {}                    # nome -> Node3D (bersagli IK e poli)
var _free_bones: Array[int] = []


func setup(skel: Skeleton3D) -> void:
	skeleton = skel
	for n: String in ["hand_l", "hand_r", "foot_l", "foot_r", "pole_arm_l", "pole_arm_r", "pole_leg_l", "pole_leg_r"]:
		var t: Node3D = Node3D.new()
		t.name = "T_" + n
		add_child(t)
		_targets[n] = t
	_ik_arms = _make_ik("ShotArmsIK", [
		["upperarm_l", "lowerarm_l", "hand_l", "hand_l", "pole_arm_l"],
		["upperarm_r", "lowerarm_r", "hand_r", "hand_r", "pole_arm_r"]])
	_ik_legs = _make_ik("ShotLegsIK", [
		["thigh_l", "calf_l", "foot_l", "foot_l", "pole_leg_l"],
		["thigh_r", "calf_r", "foot_r", "foot_r", "pole_leg_r"]])
	# Dopo l'IK: l'IK posiziona solo la caviglia e il piede seguirebbe l'inclinazione dello stinco (punta in giu', suola dentro la
	# pedana). Questo modificatore, creato DOPO i due IK (i modificatori girano nell'ordine dei figli), lo rimette orizzontale.
	_foot_level = FootLevel.new()
	_foot_level.name = "ShotFootLevel"
	skeleton.add_child(_foot_level)
	_hand_aim = HandAim.new()
	_hand_aim.name = "ShotHandAim"
	skeleton.add_child(_hand_aim)
	_hand_aim.active = false
	_fingers = FingerGrip.new()
	_fingers.name = "ShotFingerGrip"
	skeleton.add_child(_fingers)
	_fingers.active = false
	set_rig_mode(RigMode.OFF)


func _make_ik(node_name: String, chains: Array) -> TwoBoneIK3D:
	var ik: TwoBoneIK3D = TwoBoneIK3D.new()
	ik.name = node_name
	skeleton.add_child(ik)
	ik.setting_count = chains.size()
	for i in range(chains.size()):
		var c: Array = chains[i]
		ik.set_root_bone_name(i, c[0])
		ik.set_middle_bone_name(i, c[1])
		ik.set_end_bone_name(i, c[2])
		ik.set_target_node(i, ik.get_path_to(_targets[c[3]]))
		ik.set_pole_node(i, ik.get_path_to(_targets[c[4]]))
	return ik


func set_rig_mode(new_mode: int) -> void:
	if new_mode == rig_mode or skeleton == null:
		return
	# Le ossa che il nuovo modo non comanda tornano a riposo (l'animazione le riscrive, il rig le riposa a ogni fotogramma).
	skeleton.reset_bone_poses()
	rig_mode = new_mode
	_ik_arms.active = new_mode != RigMode.OFF
	_ik_arms.influence = 1.0 if new_mode != RigMode.OFF else 0.0
	_ik_legs.active = new_mode == RigMode.FULL
	_ik_legs.influence = 1.0 if new_mode == RigMode.FULL else 0.0
	_foot_level.active = new_mode == RigMode.FULL
	_hand_aim.active = new_mode != RigMode.OFF
	_fingers.active = new_mode != RigMode.OFF
	_fingers.use_left = new_mode == RigMode.FULL


## Applica la posa. Ritorna il modo del rig scelto (il chiamante ferma o riavvia l'AnimationPlayer di conseguenza).
func apply(p: ShotPutMotion.Pose) -> int:
	var wanted: int = RigMode.OFF
	if p.arms_ik:
		wanted = RigMode.FULL if p.mode == ShotPutMotion.Mode.RIG else RigMode.ARMS
	set_rig_mode(wanted)
	if wanted == RigMode.OFF:
		return wanted
	_targets["hand_r"].global_position = p.hand_r
	_targets["hand_l"].global_position = p.hand_l
	_targets["pole_arm_r"].global_position = p.elbow_r
	_targets["pole_arm_l"].global_position = p.elbow_l
	_hand_aim.ball_off = p.ball_off
	_hand_aim.ball_r = p.ball_radius
	_hand_aim.weight = p.hand_aim
	_fingers.ball_r = p.ball_radius
	_fingers.grip_r = p.grip_r
	_fingers.grip_l = p.grip_l
	if wanted == RigMode.FULL:
		_targets["foot_l"].global_position = p.foot_l
		_targets["foot_r"].global_position = p.foot_r
		_targets["pole_leg_l"].global_position = p.knee_l
		_targets["pole_leg_r"].global_position = p.knee_r
		_foot_level.turn_l = p.foot_turn_l
		_foot_level.turn_r = p.foot_turn_r
		_foot_level.pitch_l = p.foot_pitch_l
		_foot_level.pitch_r = p.foot_pitch_r
		_reset_free_bones()
		_apply_torso(p)
	return wanted


## Ossa che la posa non comanda (clavicole, dita, punta dei piedi...): a riposo a ogni aggiornamento.
func _reset_free_bones() -> void:
	if _free_bones.is_empty():
		for i in range(skeleton.get_bone_count()):
			if not CONTROLLED_BONES.has(skeleton.get_bone_name(i)):
				_free_bones.append(i)
	for i: int in _free_bones:
		var rest: Transform3D = skeleton.get_bone_rest(i)
		skeleton.set_bone_pose_position(i, rest.origin)
		skeleton.set_bone_pose_rotation(i, rest.basis.get_rotation_quaternion())
		skeleton.set_bone_pose_scale(i, rest.basis.get_scale())


## Bacino (posizione di mondo), schiena (inclinazione + torsione) e testa. L'orientamento di tutto il corpo (yaw) e' quello
## del nodo dell'atleta: qui si aggiungono solo inclinazione, torsione delle spalle e sguardo.
func _apply_torso(p: ShotPutMotion.Pose) -> void:
	var to_skel: Transform3D = skeleton.global_transform.affine_inverse()
	_set_pelvis(to_skel * Vector3(p.root.x, p.pelvis_y, p.root.z), p.lean * PITCH_PELVIS)
	var spine: Array[String] = ["spine_01", "spine_02", "spine_03"]
	for i in range(3):
		_set_global_basis(spine[i], Basis(Vector3.UP, p.twist * TWIST_SPINE[i]) * Basis(Vector3.RIGHT, p.lean * PITCH_SPINE[i]))
	_set_global_basis("neck_01", Basis(Vector3.UP, p.twist) * Basis(Vector3.RIGHT, p.lean * 0.7 + p.head_pitch * 0.4))
	_set_global_basis("Head", Basis(Vector3.UP, p.twist * 0.9) * Basis(Vector3.RIGHT, p.lean * 0.4 + p.head_pitch))


func _set_pelvis(pos_skel: Vector3, pitch: float) -> void:
	var i: int = skeleton.find_bone("pelvis")
	var parent: int = skeleton.get_bone_parent(i)
	var parent_global: Transform3D = skeleton.get_bone_global_pose(parent) if parent >= 0 else Transform3D.IDENTITY
	var desired: Transform3D = Transform3D(Basis(Vector3.RIGHT, pitch) * skeleton.get_bone_global_rest(i).basis, pos_skel)
	var local: Transform3D = parent_global.affine_inverse() * desired
	skeleton.set_bone_pose_position(i, local.origin)
	skeleton.set_bone_pose_rotation(i, local.basis.get_rotation_quaternion())


## Orientamento globale = `delta` (in spazio scheletro) applicato all'orientamento a riposo dell'osso.
func _set_global_basis(bone_name: String, delta: Basis) -> void:
	var i: int = skeleton.find_bone(bone_name)
	var parent: int = skeleton.get_bone_parent(i)
	var parent_global: Transform3D = skeleton.get_bone_global_pose(parent)
	var local_basis: Basis = parent_global.basis.inverse() * (delta * skeleton.get_bone_global_rest(i).basis)
	skeleton.set_bone_pose_rotation(i, local_basis.orthonormalized().get_rotation_quaternion())
	skeleton.set_bone_pose_position(i, skeleton.get_bone_rest(i).origin)


## Piedi orizzontali: orientamento globale = orientamento a riposo (suola piatta) ruotato di `turn` attorno alla verticale
## (positivo = verso la sinistra del corpo). Gira DOPO l'IK delle gambe e legge la posa gia' aggiornata del polpaccio.
class FootLevel:
	extends SkeletonModifier3D

	var turn_l: float = 0.12
	var turn_r: float = -0.12
	## Tallone sollevato (rad): rotazione attorno all'asse laterale del piede, la punta si abbassa. Le posizioni (caviglia) le
	## calcola ShotPutMotion in modo che la punta della scarpa resti a terra mentre il piede gira attorno ad essa.
	var pitch_l: float = 0.0
	var pitch_r: float = 0.0

	func _process_modification() -> void:
		var skel: Skeleton3D = get_skeleton()
		if skel == null:
			return
		_level(skel, "foot_l", turn_l, pitch_l)
		_level(skel, "foot_r", turn_r, pitch_r)

	static func _level(skel: Skeleton3D, bone_name: String, turn: float, pitch: float) -> void:
		var i: int = skel.find_bone(bone_name)
		var parent: int = skel.get_bone_parent(i)
		var desired: Basis = Basis(Vector3.UP, turn) * Basis(Vector3.RIGHT, pitch) * skel.get_bone_global_rest(i).basis
		var local_basis: Basis = skel.get_bone_global_pose(parent).basis.inverse() * desired
		skel.set_bone_pose_rotation(i, local_basis.orthonormalized().get_rotation_quaternion())


## Orienta la mano destra con il palmo verso il peso. Gira DOPO l'IK (che posiziona il polso ma lascia alla mano l'orientamento del
## braccio: il peso, a ~11 cm dal polso, restava lontano dal palmo e dalle dita). Il centro del peso sta a `ball_off` dal polso: la mano
## si orienta in modo che il peso poggi sul palmo, cioe' a `ball_r + PALM_GAP` dal piano delle dita; fra le due soluzioni possibili si
## sceglie quella piu' vicina alla direzione dell'avambraccio (il polso si piega il meno possibile). Il polso non si sposta.
class HandAim:
	extends SkeletonModifier3D

	var ball_off: Vector3 = Vector3.ZERO     # polso -> centro del peso, coordinate di mondo
	var ball_r: float = 0.0605
	var weight: float = 0.0

	func _process_modification() -> void:
		var skel: Skeleton3D = get_skeleton()
		if skel != null:
			apply_to(skel)

	func apply_to(skel: Skeleton3D) -> void:
		var k: float = ball_off.length()
		if weight <= 0.001 or k < 0.02:
			return
		var ih: int = skel.find_bone("hand_r")
		var il: int = skel.find_bone("lowerarm_r")
		var g_arm: Transform3D = skel.get_bone_global_pose(il)
		var g_hand: Transform3D = skel.get_bone_global_pose(ih)
		var to_skel: Basis = skel.global_transform.basis.orthonormalized().inverse()
		var u: Vector3 = (to_skel * ball_off).normalized()
		var f: Vector3 = (g_hand.origin - g_arm.origin).normalized()
		var fp: Vector3 = f - u * f.dot(u)                       # parte dell'avambraccio perpendicolare alla direzione del peso
		var down: Vector3 = -(to_skel * Vector3.UP).normalized()
		var g: Vector3 = down - u * down.dot(u)
		var m: Vector3 = (fp + 0.35 * (g.normalized() if g.length() > 0.001 else Vector3.RIGHT)).normalized()
		var sin_phi: float = clampf((ball_r + ShotPutMotion.PALM_GAP) / k, 0.35, 0.92)
		var cos_phi: float = sqrt(1.0 - sin_phi * sin_phi)
		var d: Vector3 = cos_phi * u + sin_phi * m                # direzione delle dita
		var n: Vector3 = sin_phi * u - cos_phi * m                # normale del palmo (verso il peso)
		var c: Vector3 = d.cross(n)
		# Asse y locale della mano = dita, -x = normale del palmo, z = asse di chiusura (misurato sul rig a riposo).
		var ref: Basis = Basis(Vector3(0.0, 1.0, 0.0), Vector3(-1.0, 0.0, 0.0), Vector3(0.0, 0.0, 1.0))
		var rest: Basis = skel.get_bone_global_rest(ih).basis.orthonormalized()
		var desired: Basis = Basis(-n, d, c) * ref.inverse() * rest
		var local_aimed: Quaternion = (g_arm.basis.orthonormalized().inverse() * desired).orthonormalized().get_rotation_quaternion()
		var current: Quaternion = skel.get_bone_pose_rotation(ih)
		skel.set_bone_pose_rotation(ih, current.slerp(local_aimed, clampf(weight, 0.0, 1.0)))


## Dita: ogni falange ruota attorno al proprio asse X locale (misurato sul rig: con +X le dita si chiudono verso il palmo, in entrambe le mani).
## `grip` 0 = come a riposo, 1 = chiuse attorno al peso, negativo = distese. Gira DOPO l'IK e l'animazione e parte sempre dalla posa a
## riposo, quindi non si accumula nulla da un fotogramma all'altro. Il pollice si chiude verso le altre dita (X) e si piega verso il
## palmo (Z, di segno opposto nelle due mani).
class FingerGrip:
	extends SkeletonModifier3D

	## Piegatura (rad) delle tre falangi con presa = 1: avvolgono una sfera di ~12 cm.
	const CURL: Dictionary = {
		"index": [0.45, 0.70, 0.45], "middle": [0.40, 0.60, 0.40], "ring": [0.40, 0.55, 0.35], "pinky": [0.35, 0.55, 0.40]}
	const THUMB_X: float = 0.20
	const THUMB_Z: Array[float] = [0.12, 0.20, 0.16]
	const OVEREXTEND: float = 0.5    # le dita distese (presa < 0) si piegano all'indietro di meno di quanto si chiudono

	## Il peso maschile (raggio 60,5 mm) e' piu' grande del femminile (52 mm): le dita devono chiudersi di piu' per arrivare alla sua superficie
	## (misurato sulla scena vera: con la presa tarata sul femminile le punte restavano ~2 cm fuori).
	const CURL_PER_RADIUS: float = 41.0
	const BALL_R_REF: float = 0.052

	var grip_r: float = 0.0
	var grip_l: float = 0.0
	var ball_r: float = 0.052
	var use_left: bool = false
	var _bones: Dictionary = {}     # "index_01_r" -> indice dell'osso, e rotazione a riposo

	func _process_modification() -> void:
		var skel: Skeleton3D = get_skeleton()
		if skel != null:
			apply_to(skel)

	## Applica la presa a uno scheletro (separata dal modificatore perche' i test la chiamano senza il ciclo di aggiornamento).
	func apply_to(skel: Skeleton3D) -> void:
		var size: float = maxf(1.0 + CURL_PER_RADIUS * (ball_r - BALL_R_REF), 0.8)
		_curl(skel, "r", grip_r * size if grip_r > 0.0 else grip_r)
		if use_left:
			_curl(skel, "l", grip_l)

	func _curl(skel: Skeleton3D, side: String, grip: float) -> void:
		var g: float = grip if grip >= 0.0 else grip * OVEREXTEND
		for finger: String in CURL:
			for k in range(3):
				_rotate(skel, "%s_0%d_%s" % [finger, k + 1, side], Quaternion(Vector3.RIGHT, g * float((CURL[finger] as Array)[k])))
		var thumb_sign: float = -1.0 if side == "r" else 1.0
		_rotate(skel, "thumb_01_" + side, Quaternion(Vector3.RIGHT, g * THUMB_X) * Quaternion(Vector3.BACK, thumb_sign * g * THUMB_Z[0]))
		_rotate(skel, "thumb_02_" + side, Quaternion(Vector3.BACK, thumb_sign * g * THUMB_Z[1]))
		_rotate(skel, "thumb_03_" + side, Quaternion(Vector3.BACK, thumb_sign * g * THUMB_Z[2]))

	func _rotate(skel: Skeleton3D, bone_name: String, local_turn: Quaternion) -> void:
		if not _bones.has(bone_name):
			var i: int = skel.find_bone(bone_name)
			_bones[bone_name] = [i, skel.get_bone_rest(i).basis.get_rotation_quaternion()] if i >= 0 else [-1, Quaternion.IDENTITY]
		var entry: Array = _bones[bone_name]
		if int(entry[0]) >= 0:
			skel.set_bone_pose_rotation(int(entry[0]), (entry[1] as Quaternion) * local_turn)
