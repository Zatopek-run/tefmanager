extends SceneTree
## Verifica la posa ai blocchi (pronti -> set) di tutti e 8 i corridori, leggendo le ossa DOPO l'IK.
##   godot --headless --path godot_viewer -s res://tests/verify_pose.gd      (esce con 0 = ok, 1 = errori)
## Perche' dopo l'IK: dal 4.3 lo scheletro ripristina la posa "pre-modificatori" quando i modificatori finiscono, quindi
## leggere un osso da _process dice dove NON e'. Qui si legge dentro `skeleton_updated`.
##
## Controlli (a pronti, mezzo, set):
##   - le punte delle dita (middle_04_leaf) toccano la pista: y fra TIP_MIN e TIP_MAX (ne' sollevate ne' dentro);
##   - il braccio non e' a bracci tesi: spalla-polso < 99% della lunghezza (l'IK raggiunge davvero il bersaglio);
##   - le caviglie arrivano ai blocchi (errore < FOOT_TOL);
##   - le due mani sono alla stessa altezza (differenza < SYM_TOL).

const AMOUNTS: Array = [0.0, 0.5, 1.0]
const TIP_MIN: float = -0.02
const TIP_MAX: float = 0.05
const FOOT_TOL: float = 0.04
const SYM_TOL: float = 0.03
const FULL_ARM: float = 0.99

var _scene: Node = null
var _views: Array = []
var _post: Dictionary = {}     # indice corridore -> posizioni mondo delle ossa, scritte dentro skeleton_updated
var _stage: int = 0
var _frames: int = 0
var _errors: int = 0


func _on_updated(sk: Skeleton3D, key: int) -> void:
	var d: Dictionary = {}
	for n: String in ["upperarm_l", "upperarm_r", "lowerarm_l", "lowerarm_r", "hand_l", "hand_r", "middle_04_leaf_l", "middle_04_leaf_r", "foot_l", "foot_r"]:
		d[n] = (sk.global_transform * sk.get_bone_global_pose(sk.find_bone(n))).origin
	_post[key] = d


func _fail(msg: String) -> void:
	_errors += 1
	print("ERRORE: ", msg)


func _process(_d: float) -> bool:
	var rc: Node = root.get_node("RaceController")
	if _scene == null:
		_scene = (load("res://scenes/Stadium.tscn") as PackedScene).instantiate()
		root.add_child(_scene)
		return false
	if rc.state == rc.State.LOADED:
		rc.start()
		return false
	if rc.state != rc.State.COUNTDOWN:
		return false
	if _views.is_empty():
		_views = _scene.find_children("*", "Node3D", true, false).filter(func(n): return n.get_script() != null and n.get_script().resource_path.ends_with("RunnerView.gd"))
		if _views.size() != 8:
			print("ERRORE: attesi 8 corridori, trovati ", _views.size())
			quit(1)
			return true
		for i in range(_views.size()):
			var sk: Skeleton3D = _views[i]._skeleton
			sk.skeleton_updated.connect(_on_updated.bind(sk, i))
	_frames += 1
	if _frames == 1:
		for v in _views:
			v.set_amount_override = AMOUNTS[_stage]
		return false
	if _frames < 8:
		return false
	_check(AMOUNTS[_stage])
	_stage += 1
	_frames = 0
	if _stage >= AMOUNTS.size():
		print("posa ai blocchi: ", "OK" if _errors == 0 else "%d errori" % _errors)
		quit(0 if _errors == 0 else 1)
		return true
	return false


func _check(amount: float) -> void:
	var worst_tip_lo: float = 9.0
	var worst_tip_hi: float = -9.0
	var worst_foot: float = 0.0
	var worst_arm: float = 0.0
	var worst_sym: float = 0.0
	for i in range(_views.size()):
		var v = _views[i]
		var p: Dictionary = _post[i]
		var tag: String = "amount %.1f corsia %d" % [amount, v.data.lane]
		for side in ["l", "r"]:
			var tip_y: float = p["middle_04_leaf_" + side].y
			worst_tip_lo = minf(worst_tip_lo, tip_y)
			worst_tip_hi = maxf(worst_tip_hi, tip_y)
			if tip_y < TIP_MIN or tip_y > TIP_MAX:
				_fail("%s dita %s a y=%.3f (attese fra %.2f e %.2f)" % [tag, side, tip_y, TIP_MIN, TIP_MAX])
			var arm_len: float = (p["lowerarm_" + side] - p["upperarm_" + side]).length() + (p["hand_" + side] - p["lowerarm_" + side]).length()
			var chord: float = (p["hand_" + side] - p["upperarm_" + side]).length()
			worst_arm = maxf(worst_arm, chord / arm_len)
			if chord / arm_len > FULL_ARM:
				_fail("%s braccio %s teso (%.1f%%): non arriva al bersaglio" % [tag, side, 100.0 * chord / arm_len])
			var foot_target: Vector3 = v._rig._targets["foot_" + side].global_position
			var err: float = (p["foot_" + side] - foot_target).length()
			worst_foot = maxf(worst_foot, err)
			if err > FOOT_TOL:
				_fail("%s caviglia %s a %.3f m dal blocco" % [tag, side, err])
		var sym: float = absf(p["middle_04_leaf_l"].y - p["middle_04_leaf_r"].y)
		worst_sym = maxf(worst_sym, sym)
		if sym > SYM_TOL:
			_fail("%s mani a quote diverse (%.3f m)" % [tag, sym])
	print("amount %.1f  dita y [%.3f .. %.3f]  braccio max %.0f%%  caviglia max %.3f  asimmetria mani max %.3f" % [amount, worst_tip_lo, worst_tip_hi, worst_arm * 100.0, worst_foot, worst_sym])
