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
## Altezza dell'osso "hand" (il polso): le dita arrivano ~0,17 m piu' in basso, quindi sfiorano la pista.
## (Con 0,04 le dita sprofondavano nella pista, ammesso che il braccio ci arrivasse.)
const HAND_Y: float = 0.20
const HAND_SPREAD: float = 0.24          # semi-larghezza fra le mani
const FRONT_FOOT := Vector3(-0.50, 0.15, 0.10)   # caviglia del piede anteriore (gamba "sinistra", z negativo)
const REAR_FOOT := Vector3(-0.88, 0.15, -0.10)
# Altezza del bacino per i due estremi. La x del bacino e l'inclinazione del busto NON sono costanti: si risolvono
# (`_solve_torso`) in modo che le spalle stiano sopra le mani a distanza di braccio.
const PELVIS_Y_PRONTI: float = 0.47
const PELVIS_Y_SET: float = 0.82
## Frazione della lunghezza del braccio fra spalla e polso (< 1: gomito appena piegato, l'IK non va a braccio teso).
const ARM_REACH: float = 0.95
## Quanto stanno avanti le spalle rispetto alle mani (m): in "set" il peso e' sulle mani.
const SHOULDER_AHEAD_PRONTI: float = -0.02
const SHOULDER_AHEAD_SET: float = 0.08
const PITCH_MIN: float = 0.4
const PITCH_MAX: float = 2.9
const HEAD_MAX_PITCH: float = 1.6                # la testa non segue il busto oltre questo angolo: guarda la pista davanti
const HEAD_DROP: float = 0.05

var skeleton: Skeleton3D
var _ik: TwoBoneIK3D
var _targets: Dictionary = {}                    # nome -> Node3D (bersagli IK e poli)
var _model: Node3D                               # nodo del modello (per passare da spazio locale a spazio scheletro)
var amount: float = 0.0
var enabled: bool = false
const CONTROLLED_BONES: Array[String] = [
	"pelvis", "spine_01", "spine_02", "spine_03", "neck_01", "Head",
	"upperarm_l", "lowerarm_l", "hand_l", "upperarm_r", "lowerarm_r", "hand_r",
	"thigh_l", "calf_l", "foot_l", "thigh_r", "calf_r", "foot_r"]
var _free_bones: Array[int] = []
var _arm_length: float = -1.0                   # spalla -> gomito -> polso, in metri di mondo (misurata al primo uso)
var _solved_a: float = -1.0                      # dove e' stato risolto il busto l'ultima volta (cache)
var _solved_pitch: float = 1.0
var _solved_pelvis_x: float = -0.6


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
	if on and not enabled and skeleton != null:
		# Le ossa che la posa non comanda (clavicole, dita, rotazioni residue) tornano a riposo: altrimenti restano
		# nell'ultimo fotogramma dell'animazione fermata e le due braccia partono da basi diverse.
		skeleton.reset_bone_poses()
		_solved_a = -1.0
	enabled = on
	if _ik != null:
		_ik.active = on
		_ik.influence = 1.0 if on else 0.0


## Aggiorna la posa (da chiamare a ogni fotogramma finche' e' attiva, DOPO l'AnimationPlayer o con esso fermo).
func update(new_amount: float) -> void:
	amount = clampf(new_amount, 0.0, 1.0)
	var a: float = smoothstep(0.0, 1.0, amount)
	if _arm_length < 0.0:
		_arm_length = _measure_arm_length()
	_reset_free_bones()

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

	# Bacino e busto: l'altezza del bacino viene da `amount`, inclinazione e x dal vincolo "le spalle stanno a
	# distanza di braccio dalle mani". Si risolve solo quando `amount` cambia (cache).
	var pelvis_y: float = lerpf(PELVIS_Y_PRONTI, PELVIS_Y_SET, a)
	if absf(a - _solved_a) > 0.0005:
		_solve_torso(pelvis_y, HAND_X + lerpf(SHOULDER_AHEAD_PRONTI, SHOULDER_AHEAD_SET, a))
		_solved_a = a
	_apply_torso(Vector3(_solved_pelvis_x, pelvis_y, 0.0), _solved_pitch)


## Ossa che la posa non comanda (clavicole, dita, punta dei piedi...): a riposo, uguali a destra e a sinistra.
## Con l'animazione fermata restano nell'ultimo fotogramma di corsa (clavicole 0,2 rad fuori riposo e diverse fra loro),
## e un `reset_bone_poses()` una tantum non basta: va rifatto a ogni aggiornamento.
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


## Lunghezza del braccio (spalla -> gomito -> polso) in metri di mondo: dipende dalla scala del singolo corridore.
func _measure_arm_length() -> float:
	var s: Vector3 = _bone_world_rest("upperarm_l")
	var e: Vector3 = _bone_world_rest("lowerarm_l")
	var h: Vector3 = _bone_world_rest("hand_l")
	return (e - s).length() + (h - e).length()


func _bone_world_rest(bone_name: String) -> Vector3:
	return (skeleton.global_transform * skeleton.get_bone_global_rest(skeleton.find_bone(bone_name))).origin


## Posizione di un osso nello spazio locale del corridore (quello dei bersagli IK).
func _bone_local(bone_name: String) -> Vector3:
	var world: Vector3 = (skeleton.global_transform * skeleton.get_bone_global_pose(skeleton.find_bone(bone_name))).origin
	return global_transform.affine_inverse() * world


## Applica bacino (posizione locale al corridore) e catena busto-testa per un dato angolo di inclinazione.
func _apply_torso(pelvis_local: Vector3, pitch: float) -> void:
	var to_skel: Transform3D = skeleton.global_transform.affine_inverse() * global_transform
	# Rotazione = pitch attorno all'asse laterale dello scheletro (X) applicato alla rotazione a riposo.
	# Pesi vicini a 1: la schiena resta quasi dritta (una curvatura forte fa risalire le spalle oltre i 90 gradi).
	_set_global_pelvis(to_skel * pelvis_local, pitch * 0.75)
	_set_global_rotation("spine_01", pitch * 0.85)
	_set_global_rotation("spine_02", pitch * 0.93)
	_set_global_rotation("spine_03", pitch * 1.0)
	var head_pitch: float = minf(pitch, HEAD_MAX_PITCH) + HEAD_DROP
	_set_global_rotation("neck_01", head_pitch - HEAD_DROP * 0.6)
	_set_global_rotation("Head", head_pitch)


## Trova inclinazione del busto e x del bacino per cui le spalle stanno sopra le mani a `ARM_REACH` * braccio.
## Il vettore bacino -> spalle dipende solo dall'inclinazione, non dalla posizione del bacino: si cerca l'angolo
## per l'altezza giusta (bisezione: piu' inclinato = spalle piu' basse) e poi si sposta il bacino in x.
func _solve_torso(pelvis_y: float, shoulder_x: float) -> void:
	var reach: float = ARM_REACH * _arm_length
	var dx: float = shoulder_x - HAND_X
	var shoulder_y: float = HAND_Y + sqrt(maxf(reach * reach - dx * dx, 0.0004))
	var lo: float = PITCH_MIN
	var hi: float = PITCH_MAX
	for i in range(14):
		var mid: float = 0.5 * (lo + hi)
		_apply_torso(Vector3(0.0, pelvis_y, 0.0), mid)
		var shoulders: Vector3 = 0.5 * (_bone_local("upperarm_l") + _bone_local("upperarm_r"))
		if shoulders.y > shoulder_y:
			lo = mid     # spalle ancora troppo alte: piu' inclinazione
		else:
			hi = mid
	_solved_pitch = hi
	_apply_torso(Vector3(0.0, pelvis_y, 0.0), _solved_pitch)
	var s: Vector3 = 0.5 * (_bone_local("upperarm_l") + _bone_local("upperarm_r"))
	_solved_pelvis_x = shoulder_x - s.x


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
