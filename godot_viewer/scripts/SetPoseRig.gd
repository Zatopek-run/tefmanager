class_name SetPoseRig
extends Node3D
## VIEW 3D - posizione ai blocchi ("pronti" -> "set") per lo scheletro del corridore, ottenuta senza animazioni:
## bacino e schiena sono posati a mano, braccia e gambe con TwoBoneIK3D (mani sulla linea, piedi nei blocchi).
## Il nodo va messo come figlio del RunnerView: le coordinate dei punti sono "locali al corridore":
## +X = direzione di corsa, +Y = su, Z = laterale (0 = centro corsia), linea di partenza a x = 0.
##
## `amount` 0 = pronti (ginocchio posteriore a terra, bacino basso), 1 = set (bacino alto, ginocchia sollevate).

# Punti fissi (m): mani appena dietro la linea, piedi nei due blocchi.
const HAND_X: float = -0.03
const HAND_Y: float = 0.04
const HAND_SPREAD: float = 0.24          # semi-larghezza fra le mani
const FRONT_FOOT := Vector3(-0.50, 0.15, 0.10)   # caviglia del piede anteriore (gamba "sinistra", z negativo)
const REAR_FOOT := Vector3(-0.88, 0.15, -0.10)
# Bacino e inclinazione del busto per i due estremi.
const PELVIS_PRONTI := Vector2(-0.70, 0.47)      # (x, y)
const PELVIS_SET := Vector2(-0.60, 0.88)
const TORSO_PITCH_PRONTI: float = 0.85
const TORSO_PITCH_SET: float = 1.42
const HEAD_DROP: float = 0.05

var skeleton: Skeleton3D
var _ik: TwoBoneIK3D
var _targets: Dictionary = {}                    # nome -> Node3D (bersagli IK e poli)
var _model: Node3D                               # nodo del modello (per passare da spazio locale a spazio scheletro)
var amount: float = 0.0
var enabled: bool = false


func setup(model: Node3D, skel: Skeleton3D) -> void:
	_model = model
	skeleton = skel
	for n: String in ["hand_l", "hand_r", "foot_l", "foot_r", "pole_arm_l", "pole_arm_r", "pole_leg_l", "pole_leg_r"]:
		var t: Node3D = Node3D.new()
		t.name = "T_" + n
		add_child(t)
		_targets[n] = t
	_ik = TwoBoneIK3D.new()
	_ik.name = "SetPoseIK"
	skeleton.add_child(_ik)
	_ik.setting_count = 4
	var chains: Array = [
		["upperarm_l", "lowerarm_l", "hand_l", "hand_l", "pole_arm_l"],
		["upperarm_r", "lowerarm_r", "hand_r", "hand_r", "pole_arm_r"],
		["thigh_l", "calf_l", "foot_l", "foot_l", "pole_leg_l"],
		["thigh_r", "calf_r", "foot_r", "foot_r", "pole_leg_r"]]
	for i in range(chains.size()):
		var c: Array = chains[i]
		_ik.set_root_bone_name(i, c[0])
		_ik.set_middle_bone_name(i, c[1])
		_ik.set_end_bone_name(i, c[2])
		_ik.set_target_node(i, _ik.get_path_to(_targets[c[3]]))
		_ik.set_pole_node(i, _ik.get_path_to(_targets[c[4]]))
	set_enabled(false)


func set_enabled(on: bool) -> void:
	enabled = on
	if _ik != null:
		_ik.active = on
		_ik.influence = 1.0 if on else 0.0


## Aggiorna la posa (da chiamare a ogni fotogramma finche' e' attiva, DOPO l'AnimationPlayer o con esso fermo).
func update(new_amount: float) -> void:
	amount = clampf(new_amount, 0.0, 1.0)
	var a: float = smoothstep(0.0, 1.0, amount)
	var pelvis_xy: Vector2 = PELVIS_PRONTI.lerp(PELVIS_SET, a)
	var pitch: float = lerpf(TORSO_PITCH_PRONTI, TORSO_PITCH_SET, a)

	# Bersagli IK (spazio locale del corridore). Il ginocchio posteriore scende a terra in "pronti".
	var rear_foot: Vector3 = REAR_FOOT
	_targets["hand_l"].position = Vector3(HAND_X, HAND_Y, -HAND_SPREAD)
	_targets["hand_r"].position = Vector3(HAND_X, HAND_Y, HAND_SPREAD)
	_targets["foot_l"].position = FRONT_FOOT * Vector3(1.0, 1.0, -1.0)
	_targets["foot_r"].position = rear_foot * Vector3(1.0, 1.0, -1.0)
	# Poli: i gomiti vanno indietro/fuori, le ginocchia avanti.
	_targets["pole_arm_l"].position = Vector3(-0.55, 0.45, -0.55)
	_targets["pole_arm_r"].position = Vector3(-0.55, 0.45, 0.55)
	_targets["pole_leg_l"].position = Vector3(0.10, 0.60 + 0.15 * a, -0.35)
	_targets["pole_leg_r"].position = Vector3(-0.10 + 0.20 * a, 0.08 + 0.50 * a, 0.35)

	# Bacino: posizione (in spazio scheletro) e inclinazione.
	var pelvis_local: Vector3 = Vector3(pelvis_xy.x, pelvis_xy.y, 0.0)
	var to_skel: Transform3D = skeleton.global_transform.affine_inverse() * global_transform
	var pelvis_skel: Vector3 = to_skel * pelvis_local
	# Rotazione = pitch attorno all'asse laterale dello scheletro (X) applicato alla rotazione a riposo.
	_set_global_pelvis(pelvis_skel, pitch * 0.35)
	_set_global_rotation("spine_01", pitch * 0.60)
	_set_global_rotation("spine_02", pitch * 0.82)
	_set_global_rotation("spine_03", pitch * 0.97)
	_set_global_rotation("neck_01", pitch * 0.97 + HEAD_DROP * 0.4)
	_set_global_rotation("Head", pitch * 0.97 + HEAD_DROP)


func _rest_global(bone: int) -> Transform3D:
	return skeleton.get_bone_global_rest(bone)


func _set_global_pelvis(pos_skel: Vector3, pitch: float) -> void:
	var i: int = skeleton.find_bone("pelvis")
	var parent: int = skeleton.get_bone_parent(i)
	var parent_global: Transform3D = skeleton.get_bone_global_pose(parent) if parent >= 0 else Transform3D.IDENTITY
	var desired: Transform3D = Transform3D(Basis(Vector3.RIGHT, pitch) * _rest_global(i).basis, pos_skel)
	var local: Transform3D = parent_global.affine_inverse() * desired
	skeleton.set_bone_pose_position(i, local.origin)
	skeleton.set_bone_pose_rotation(i, local.basis.get_rotation_quaternion())


func _set_global_rotation(bone_name: String, pitch: float) -> void:
	var i: int = skeleton.find_bone(bone_name)
	var parent: int = skeleton.get_bone_parent(i)
	var parent_global: Transform3D = skeleton.get_bone_global_pose(parent)
	var desired_basis: Basis = Basis(Vector3.RIGHT, pitch) * _rest_global(i).basis
	var local_basis: Basis = parent_global.basis.inverse() * desired_basis
	skeleton.set_bone_pose_rotation(i, local_basis.get_rotation_quaternion())
	skeleton.set_bone_pose_position(i, skeleton.get_bone_rest(i).origin)
