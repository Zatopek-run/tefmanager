extends SceneTree
## Verifica headless del getto del peso: modello (ShotPutMotion) e controller (RaceController), senza finestra.
##   godot --headless --path godot_viewer -s res://tests/verify_shotput.gd
## Controlla soprattutto che il peso atterri ESATTAMENTE alla misura decisa dal motore Python (0,5 mm di tolleranza),
## che l'angolo di rilascio stia fra 35 e 40 gradi, che il peso non vada mai sotto terra prima dell'atterraggio, che la
## posa dell'atleta sia continua (niente salti da un fotogramma all'altro) e che i piedi restino dentro la pedana fino al
## rilascio. Esce con codice 0 se tutto torna, 1 altrimenti.

var _failures: int = 0
const FPS: float = 60.0


func _check(cond: bool, what: String) -> void:
	if not cond:
		print("FAIL  " + what)
		_failures += 1
	elif OS.get_cmdline_user_args().has("--verbose"):
		print("OK    " + what)


func _init() -> void:
	_check_proportions()
	_check_flight_exactness()
	_check_release_and_pose()


## Gli autoload (RaceController) esistono solo dopo _init: il controllo del controller gira al primo fotogramma.
func _process(_delta: float) -> bool:
	_check_controller()
	print("RISULTATO: %s" % ("TUTTO OK" if _failures == 0 else "%d FALLIMENTI" % _failures))
	quit(0 if _failures == 0 else 1)
	return true


## Le proporzioni usate da ShotPutMotion (frazioni dell'altezza) devono coincidere con quelle del modello 3D.
func _check_proportions() -> void:
	for path: String in ["res://assets/athlete/Superhero_Male_FullBody.gltf", "res://assets/athlete/Superhero_Female_FullBody.gltf"]:
		var m: Node3D = (load(path) as PackedScene).instantiate()
		root.add_child(m)
		var sk: Skeleton3D = m.find_child("Skeleton3D", true, false)
		var h: float = CharacterDress.body_extent(CharacterDress.find_body_mesh(sk)).y
		var pos: Callable = func(n: String) -> Vector3: return sk.get_bone_global_rest(sk.find_bone(n)).origin
		var up: Vector3 = pos.call("upperarm_r")
		var pel: Vector3 = pos.call("pelvis")
		_check(absf((up.y - pel.y) / h - ShotPutMotion.SHOULDER_UP) < 0.01, "%s: spalla sopra il bacino %.3f H" % [path.get_file(), (up.y - pel.y) / h])
		_check(absf(absf(up.x) / h - (ShotPutMotion.SHOULDER_SIDE_F if path.contains("Female") else ShotPutMotion.SHOULDER_SIDE)) < 0.01, "%s: semi-larghezza spalle %.3f H" % [path.get_file(), absf(up.x) / h])
		var arm: float = (pos.call("lowerarm_r") - up).length() + (pos.call("hand_r") - pos.call("lowerarm_r")).length()
		_check(absf(arm / h - ShotPutMotion.ARM_LENGTH) < 0.012, "%s: braccio %.3f H" % [path.get_file(), arm / h])
		var thigh: Vector3 = pos.call("thigh_r")
		var leg: float = (pos.call("calf_r") - thigh).length() + (pos.call("foot_r") - pos.call("calf_r")).length()
		_check(absf(leg / h - ShotPutMotion.LEG_LENGTH) < 0.012, "%s: gamba %.3f H" % [path.get_file(), leg / h])
		_check(absf((pos.call("neck_01") as Vector3).y - pel.y) / h - ShotPutMotion.NECK_UP < 0.01, "%s: collo" % path.get_file())
		m.free()


func _check_flight_exactness() -> void:
	_check(is_equal_approx(float(ShotPutMotion.KEY_T[7]), ShotPutMotion.T_REL), "il tasto 7 e' il rilascio")
	var n: int = 0
	for female: bool in [false, true]:
		var heights: Array = [1.63, 1.70, 1.77] if female else [1.72, 1.79, 1.86]
		for mark: float in [3.0, 6.5, 9.2, 12.0, 15.42, 17.64, 19.42, 20.15, 22.0, 23.56]:
			for ang: float in [-ShotPutMotion.MAX_LAND_ANGLE, 0.0, 0.07, ShotPutMotion.MAX_LAND_ANGLE]:
				for h: float in heights:
					for foul: bool in [false, true]:
						n += 1
						var p: ShotPutMotion.Plan = ShotPutMotion.make_plan(mark, foul, h, female, ang)
						var tag: String = "%s %.2f m ang %.2f h %.2f%s" % ["F" if female else "M", mark, ang, h, " nullo" if foul else ""]
						# a) atterraggio: raggio dal centro - raggio della pedana = misura
						var end: Vector3 = ShotPutMotion.flight_position(p, p.flight)
						var radial: float = Vector2(end.x - ShotPutMotion.CENTER.x, end.z - ShotPutMotion.CENTER.z).length() - ShotPutMotion.CIRCLE_RADIUS
						_check(absf(radial - mark) < 0.0005, "%s: atterra a %.5f m" % [tag, radial])
						_check(absf(end.y - p.ball_r) < 0.0005, "%s: a terra al tempo T" % tag)
						var late: Vector3 = ShotPutMotion.flight_position(p, p.flight + 5.0)
						_check(Vector2(late.x - end.x, late.z - end.z).length() < 1e-6, "%s: fermo dopo T" % tag)
						# b) angolo e velocita'
						_check(rad_to_deg(p.theta) >= 35.0 and rad_to_deg(p.theta) <= 40.0, "%s: angolo %.1f" % [tag, rad_to_deg(p.theta)])
						_check(p.speed > 4.0 and p.speed < 16.0, "%s: v0 %.2f m/s" % [tag, p.speed])
						_check(p.flight > 0.7 and p.flight < 2.4, "%s: volo %.2f s" % [tag, p.flight])
						# c) il peso non va sotto terra prima di T e sale prima di scendere
						var min_y: float = INF
						var max_y: float = -INF
						var steps: int = int(p.flight * 200.0)
						var smooth: bool = true
						var prev: Vector3 = ShotPutMotion.flight_position(p, 0.0)
						for i in range(steps + 1):
							var q: Vector3 = ShotPutMotion.flight_position(p, minf(float(i) / 200.0, p.flight))
							min_y = minf(min_y, q.y)
							max_y = maxf(max_y, q.y)
							smooth = smooth and q.distance_to(prev) < 0.4
							prev = q
						_check(min_y >= p.ball_r - 0.0005, "%s: sempre sopra il suolo (min %.4f)" % [tag, min_y])
						_check(max_y > p.release.y, "%s: sale oltre il rilascio" % tag)
						_check(smooth, "%s: nessun salto lungo la traiettoria" % tag)
						# d) il rilascio e' dentro la pedana e a un'altezza plausibile per quell'atleta
						var r_xz: float = Vector2(p.release.x - ShotPutMotion.CENTER.x, p.release.z - ShotPutMotion.CENTER.z).length()
						_check(r_xz < ShotPutMotion.CIRCLE_RADIUS, "%s: rilascio dentro la pedana (%.2f m dal centro)" % [tag, r_xz])
						_check(p.release.y > 1.0 * h and p.release.y < 1.17 * h, "%s: rilascio a %.2f m (%.2f H)" % [tag, p.release.y, p.release.y / h])
	print("peso: %d tentativi teorici verificati" % n)


func _check_release_and_pose() -> void:
	for foul: bool in [false, true]:
		for female: bool in [false, true]:
			var p: ShotPutMotion.Plan = ShotPutMotion.make_plan(18.0, foul, 1.65 if female else 1.80, female, 0.05)
			var tag: String = "%s%s" % ["F" if female else "M", " nullo" if foul else ""]
			var prev: ShotPutMotion.Pose = ShotPutMotion.pose_at(p, 0.0)
			var max_root: float = 0.0
			var max_foot: float = 0.0
			var max_hand: float = 0.0
			var max_yaw: float = 0.0
			var inside: bool = true
			var worst_r: float = 0.0
			var t: float = 1.0 / FPS
			while t <= p.duration + 0.01:
				var q: ShotPutMotion.Pose = ShotPutMotion.pose_at(p, t)
				var exiting: bool = t > p.t_exit - 0.02 and t < p.t_exit + 0.02
				if not exiting:
					max_root = maxf(max_root, q.root.distance_to(prev.root))
					max_yaw = maxf(max_yaw, absf(q.yaw - prev.yaw))
					if q.mode == ShotPutMotion.Mode.RIG and prev.mode == ShotPutMotion.Mode.RIG:
						max_foot = maxf(max_foot, maxf(q.foot_l.distance_to(prev.foot_l), q.foot_r.distance_to(prev.foot_r)))
						max_hand = maxf(max_hand, q.hand_l.distance_to(prev.hand_l))
						if q.arms_ik and prev.arms_ik:
							max_hand = maxf(max_hand, q.hand_r.distance_to(prev.hand_r))
				# prima del rilascio i piedi stanno dentro la pedana (altrimenti sarebbe nullo)
				if t >= ShotPutMotion.T_SET and t <= ShotPutMotion.T_REL:
					for f: Vector3 in [q.foot_l, q.foot_r]:
						var r: float = Vector2(f.x - ShotPutMotion.CENTER.x, f.z - ShotPutMotion.CENTER.z).length()
						worst_r = maxf(worst_r, r)
						if r > ShotPutMotion.CIRCLE_RADIUS - 0.05:
							inside = false
				prev = q
				t += 1.0 / FPS
			_check(max_root < 0.12, "%s: bacino continuo (max %.3f m a fotogramma)" % [tag, max_root])
			_check(max_yaw < 0.30, "%s: orientamento continuo (max %.3f rad a fotogramma)" % [tag, max_yaw])
			_check(max_foot < 0.14, "%s: piedi continui (max %.3f m a fotogramma)" % [tag, max_foot])
			_check(max_hand < 0.22, "%s: mani continue (max %.3f m a fotogramma)" % [tag, max_hand])
			_check(inside, "%s: piedi dentro la pedana fino al rilascio (max %.2f m dal centro)" % [tag, worst_r])
			# dopo il rilascio: valido = piedi ancora dentro, nullo = un piede oltre il fermapiedi
			var after: ShotPutMotion.Pose = ShotPutMotion.pose_at(p, ShotPutMotion.KEY_T[10] + 0.1)
			var rr: float = Vector2(after.foot_r.x - ShotPutMotion.CENTER.x, after.foot_r.z - ShotPutMotion.CENTER.z).length()
			var rl: float = Vector2(after.foot_l.x - ShotPutMotion.CENTER.x, after.foot_l.z - ShotPutMotion.CENTER.z).length()
			if foul:
				_check(rr > ShotPutMotion.CIRCLE_RADIUS + ShotPutMotion.STOPBOARD_WIDTH, "%s: piede oltre il fermapiedi (%.2f m)" % [tag, rr])
			else:
				_check(rr < ShotPutMotion.CIRCLE_RADIUS - 0.05 and rl < ShotPutMotion.CIRCLE_RADIUS - 0.05, "%s: dopo il lancio resta nella pedana" % tag)
			# uscita dalla parte posteriore
			var gone: ShotPutMotion.Pose = ShotPutMotion.pose_at(p, p.duration)
			_check(gone.root.x < ShotPutMotion.CENTER.x - ShotPutMotion.CIRCLE_RADIUS - 1.0, "%s: esce dal lato posteriore (x %.2f)" % [tag, gone.root.x])
			# all'inizio dell'attesa il peso e' in mano e la mano e' vicina al collo; al rilascio la mano e' al bersaglio
			_check(ShotPutMotion.pose_at(p, 3.0).ball_in_hand, "%s: peso in mano all'attesa" % tag)
			_check(not ShotPutMotion.pose_at(p, ShotPutMotion.T_REL + 0.05).ball_in_hand, "%s: peso non piu' in mano dopo il rilascio" % tag)
			var at_rel: ShotPutMotion.Pose = ShotPutMotion.pose_at(p, ShotPutMotion.T_REL)
			_check((at_rel.hand_r + at_rel.ball_off).distance_to(p.release) < 0.001, "%s: al rilascio il peso e' in R" % tag)
			# raggiungibilita': le gambe arrivano ai piedi (distanza anca-caviglia <= lunghezza della gamba)
			var worst_reach: float = 0.0
			t = ShotPutMotion.T_SET
			while t <= ShotPutMotion.KEY_T[10]:
				var z: ShotPutMotion.Pose = ShotPutMotion.pose_at(p, t)
				for f2: Vector3 in [z.foot_l, z.foot_r]:
					var hip: Vector3 = Vector3(z.root.x, z.pelvis_y + ShotPutMotion.HIP_ABOVE_PELVIS * p.height, z.root.z)
					worst_reach = maxf(worst_reach, hip.distance_to(f2) / (ShotPutMotion.LEG_LENGTH * p.height))
				t += 0.02
			_check(worst_reach < 1.06, "%s: gambe raggiungono i piedi (massimo %.2f della lunghezza)" % [tag, worst_reach])


## Controller: avanza i tentativi con passi fissi di tempo e controlla che ogni peso animato finisca esattamente dove dice il DB.
func _check_controller() -> void:
	var rc: Node = root.get_node("RaceController")
	for race_id: int in [11, 12]:
		_check(rc.load_race(race_id), "gara %d caricata" % race_id)
		var steps: Array[Dictionary] = []
		for st: Dictionary in rc.field_queue:
			steps.append(st)
		var animated: int = 0
		var landed: Dictionary = {}     # indice del passo -> posizione finale del peso
		rc.replay_enabled = false
		rc.start()
		var guard: int = 0
		var last_idx: int = -1
		var last_pos: Vector3 = Vector3.ZERO
		var last_landed: bool = false
		var last_foul: bool = false
		while rc.state != rc.State.FINISHED and guard < 200000:
			guard += 1
			var idx: int = rc.field_idx
			if idx != last_idx:
				if last_idx >= 0 and last_idx < steps.size() and bool(steps[last_idx]["animate"]):
					landed[last_idx] = {"pos": last_pos, "landed": last_landed}
				last_idx = idx
			rc._process(0.05)
			if rc.shot_visible:
				last_pos = rc.shot_pos
				last_landed = rc.shot_plan != null and rc.shot_plan.flight > 0.0 and rc.shot_t >= rc.shot_plan.t_land
			last_foul = rc.field_landed_foul
		_check(rc.state == rc.State.FINISHED, "gara %d: finisce" % race_id)
		for i in range(steps.size()):
			if not bool(steps[i]["animate"]):
				continue
			animated += 1
			_check(landed.has(i), "gara %d, prova %d animata: arrivata fino all'atterraggio" % [race_id, i])
			if not landed.has(i):
				continue
			var plan: ShotPutMotion.Plan = steps[i]["plan"]
			var pos: Vector3 = landed[i]["pos"]
			var radial: float = Vector2(pos.x - ShotPutMotion.CENTER.x, pos.z - ShotPutMotion.CENTER.z).length() - ShotPutMotion.CIRCLE_RADIUS
			_check(absf(radial - float(steps[i]["mark"])) < 0.0005, "gara %d, prova %d: il peso finisce a %.4f m (DB %.2f m)" % [race_id, i, radial, float(steps[i]["mark"])])
		var expected_steps: int = 0
		for st2: Dictionary in steps:
			expected_steps += 1
		_check(animated == expected_steps and expected_steps >= 24, "gara %d: tutti i %d lanci sono animati (%d)" % [race_id, expected_steps, animated])
		var best: float = 0.0
		for r: RunnerData in rc.runners:
			best = maxf(best, r.best_mark)
		_check(is_equal_approx(rc.live_order[0].best_mark, best), "gara %d: il primo in classifica ha la misura migliore" % race_id)
