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
	if wanted == RigMode.FULL:
		_targets["foot_l"].global_position = p.foot_l
		_targets["foot_r"].global_position = p.foot_r
		_targets["pole_leg_l"].global_position = p.knee_l
		_targets["pole_leg_r"].global_position = p.knee_r
		_foot_level.turn_l = p.foot_turn_l
		_foot_level.turn_r = p.foot_turn_r
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

	func _process_modification() -> void:
		var skel: Skeleton3D = get_skeleton()
		if skel == null:
			return
		_level(skel, "foot_l", turn_l)
		_level(skel, "foot_r", turn_r)

	static func _level(skel: Skeleton3D, bone_name: String, turn: float) -> void:
		var i: int = skel.find_bone(bone_name)
		var parent: int = skel.get_bone_parent(i)
		var desired: Basis = Basis(Vector3.UP, turn) * skel.get_bone_global_rest(i).basis
		var local_basis: Basis = skel.get_bone_global_pose(parent).basis.inverse() * desired
		skel.set_bone_pose_rotation(i, local_basis.orthonormalized().get_rotation_quaternion())
