class_name ShotPutMotion
extends RefCounted
## MODEL (nessuna scena) - getto del peso: geometria della pedana, cronologia del tentativo, posa dell'atleta e volo
## del peso. Sono funzioni PURE del tempo del tentativo (come RaceMotion e TrackGeometry): chi le usa (RaceController,
## ShotPutRig, ShotPutView, BroadcastCameras, il costruttore della pista e i test) legge gli stessi numeri e non
## possono divergere. Non decide mai una misura: la misura arriva gia' calcolata dal motore Python.
##
## VINCOLO CHE DECIDE IL DISEGNO: il peso atterra ESATTAMENTE a `L = C + u * (misura + RAGGIO)`, dove C e' il centro
## della pedana, u il versore (orizzontale) verso il punto di caduta e RAGGIO = 1,0675 m (la misura si legge dal
## bordo interno del cerchio, con il nastro che passa per il centro). Il punto di rilascio R e' SCRITTO (ricavato dalla
## posa a t = T_REL e dall'altezza dell'atleta), mai riletto dallo scheletro; con angolo di rilascio fisso la velocita'
## iniziale si ricava in forma chiusa. Il volo e' una funzione del tempo fissata a tau >= T: esatto a 1x, a 8x e con
## «salta alla fine».
##
## Convenzioni: pista lungo +X (il settore va verso +X), su = +Y. Gli angoli di orientamento (`yaw`) sono antiorari
## visti dall'alto, 0 = guarda +X (il settore), PI = guarda indietro (+X e' davanti, -X e' la parte posteriore della
## pedana). L'atleta e' destrorso e usa la tecnica a rotazione (antioraria).

enum Phase { ENTER, SET, SPIN, FLIGHT, LAND, EXIT }
enum Mode { WALK, IDLE, RIG }

# --- pedana e settore (m) ----------------------------------------------------------------------------
const CENTER: Vector3 = Vector3(-42.0, 0.0, -36.0)
const CIRCLE_RADIUS: float = 1.0675       # diametro 2,135 m
const CIRCLE_TOP: float = 0.012           # quota del piano della pedana (i piedi stanno qui dentro il cerchio)
const STOPBOARD_CHORD: float = 1.22       # corda interna del fermapiedi
const STOPBOARD_WIDTH: float = 0.112
const STOPBOARD_HEIGHT: float = 0.10
const SECTOR_HALF_ANGLE: float = deg_to_rad(17.46)   # settore da 34,92 gradi
## Lunghezza disegnata del settore dal bordo della pedana. Il regolamento prevede 100 m, ma lungo l'asse la curva 1 sta a
## ~78 m dalla pedana: si disegnano 30 m (oltre il record del mondo, 23,56 m). Scelta confermata dall'utente.
const SECTOR_LENGTH: float = 30.0
const BALL_RADIUS_M: float = 0.0605       # peso maschile 7,26 kg: diametro ~121 mm
const BALL_RADIUS_F: float = 0.052        # peso femminile 4 kg: diametro ~104 mm
const GRAVITY: float = 9.81
const MAX_LAND_ANGLE: float = 0.13        # rad: scarto massimo del punto di caduta dall'asse del settore (il raggio non cambia)

# --- cronologia del tentativo animato (s dall'inizio del tentativo, a 1x) -------------------------------
const T_ENTER_END: float = 1.8            # fine dell'ingresso a piedi
const T_TURN_END: float = 2.4             # fine della rotazione sul posto (di spalle al settore)
const T_SET: float = 2.65                 # da qui lo scheletro e' comandato dal rig (gambe comprese)
const T_REL: float = 5.20                 # rilascio (coincide con l'ultimo tasto di KEY_T meno due)
const SPIN_AFTER_REL: float = 0.08          # la camera della rotazione resta sull'atleta solo un attimo dopo il rilascio: il peso esce subito dall'inquadratura
const LAND_HOLD: float = 1.3              # dopo l'atterraggio: misura, nastro, bandierina
const EXIT_TIME: float = 1.8
const END_HOLD: float = 0.15
const INSTANT_DURATION: float = 0.35      # tentativi non animati (gli altri concorrenti)
const ENTER_X0: float = -3.1              # x di partenza dell'ingresso (relativa al centro)
const SET_X: float = -0.74                # x della posizione iniziale, sul lato opposto al settore
const EXIT_X: float = -2.9
const ARM_ELEVATION: float = deg_to_rad(52.0)   # inclinazione del braccio teso al rilascio (il peso parte a ~37 gradi)

## Griglia dei tasti della posa a rotazione (stessi tempi per tutti i canali).
## 0 posizione iniziale, 1 fine dell'attesa, 2 caricamento, 3 appoggio sul sinistro, 4 volo (piede destro in giro),
## 5 piede destro al centro, 6 posizione di potenza, 7 RILASCIO, 8 e 9 inversione, 10 fermo.
const KEY_T: Array = [2.65, 3.50, 3.95, 4.25, 4.60, 4.85, 5.02, 5.20, 5.35, 5.50, 5.90]

# Proporzioni del modello (frazioni dell'altezza H, misurate sul rig Quaternius a riposo, vedi tests/verify_shotput.gd).
const ANKLE_H: float = 0.0475
const HIP_ABOVE_PELVIS: float = 0.0125
const LEG_LENGTH: float = 0.486
const SHOULDER_UP: float = 0.278          # osso del bacino -> spalla, lungo la schiena
const SHOULDER_SIDE: float = 0.116          # maschile; femminile SHOULDER_SIDE_F
const SHOULDER_SIDE_F: float = 0.085
const NECK_UP: float = 0.314
const ARM_LENGTH: float = 0.272           # spalla -> polso
const HAND_TO_BALL: float = 0.09          # polso -> centro del peso (m, a braccio teso)

static var _tables: Dictionary = {}


class Plan:
	extends RefCounted
	var instant: bool = false
	var foul: bool = false
	var mark: float = 0.0
	var height: float = 1.8
	var female: bool = false
	var ball_r: float = BALL_RADIUS_M
	var land_angle: float = 0.0
	var dir: Vector3 = Vector3.RIGHT      # versore orizzontale dal centro della pedana al punto di caduta
	var landing: Vector3 = Vector3.ZERO   # punto di caduta (a terra)
	var release: Vector3 = Vector3.ZERO   # centro del peso al rilascio
	var vdir: Vector3 = Vector3.RIGHT     # versore orizzontale rilascio -> caduta
	var theta: float = 0.0                # angolo di rilascio
	var speed: float = 0.0                # velocita' iniziale (m/s)
	var flight: float = 0.0               # durata del volo (s)
	var t_land: float = 0.0
	var t_exit: float = 0.0
	var duration: float = INSTANT_DURATION


class Pose:
	extends RefCounted
	var mode: int = Mode.WALK
	var arms_ik: bool = true              # false: le braccia le muove l'animazione (uscita)
	var ball_in_hand: bool = false
	var root: Vector3 = Vector3.ZERO      # posizione a terra del bacino (nodo dell'atleta)
	var yaw: float = 0.0
	var pelvis_y: float = 0.9             # quota (m) del bacino
	var lean: float = 0.0                 # inclinazione in avanti del busto
	var twist: float = 0.0                # rotazione delle spalle rispetto al bacino (antioraria +)
	var head_pitch: float = 0.0
	var walk_speed: float = 0.0
	var foot_l: Vector3 = Vector3.ZERO    # bersagli (caviglia) in coordinate di mondo
	var foot_r: Vector3 = Vector3.ZERO
	var knee_l: Vector3 = Vector3.ZERO    # poli dell'IK
	var knee_r: Vector3 = Vector3.ZERO
	var hand_r: Vector3 = Vector3.ZERO    # bersagli (polso)
	var hand_l: Vector3 = Vector3.ZERO
	var elbow_r: Vector3 = Vector3.ZERO
	var elbow_l: Vector3 = Vector3.ZERO
	var ball_off: Vector3 = Vector3.ZERO  # centro del peso - polso destro, mentre lo tiene in mano


# --- geometria ----------------------------------------------------------------------------------------

static func dir_at(angle: float) -> Vector3:
	return Vector3(cos(angle), 0.0, -sin(angle))


## Punto di caduta (a terra): a `mark` metri dal bordo del cerchio, misurati in linea retta dal centro.
static func landing_point(mark: float, land_angle: float) -> Vector3:
	return CENTER + dir_at(land_angle) * (mark + CIRCLE_RADIUS)


## Scarto deterministico del punto di caduta dall'asse del settore (stesso tentativo = stessa traiettoria).
static func landing_angle(visual_key: String, round_num: int) -> float:
	var h: int = absi(hash("%s#%d#caduta" % [visual_key, round_num])) % 2001
	return (float(h) / 1000.0 - 1.0) * MAX_LAND_ANGLE


static func release_angle(mark: float) -> float:
	return deg_to_rad(36.0 + 2.5 * clampf((mark - 8.0) / 14.0, 0.0, 1.0))


## Prepara un tentativo. `instant` = tentativo non animato (il peso e' gia' a terra).
static func make_plan(mark: float, foul: bool, height: float, female: bool, land_angle: float, instant: bool = false) -> Plan:
	var p: Plan = Plan.new()
	p.instant = instant
	p.foul = foul
	p.mark = mark
	p.height = height
	p.female = female
	p.ball_r = BALL_RADIUS_F if female else BALL_RADIUS_M
	p.land_angle = land_angle
	p.dir = dir_at(land_angle)
	p.landing = landing_point(mark, land_angle)
	if instant:
		p.duration = INSTANT_DURATION
		return p
	p.release = _release_point(p)
	var flat: Vector3 = Vector3(p.landing.x - p.release.x, 0.0, p.landing.z - p.release.z)
	var d: float = flat.length()
	p.vdir = flat / d if d > 0.0001 else p.dir
	p.theta = release_angle(mark)
	var h: float = p.release.y - p.ball_r          # quota del centro al rilascio sopra il centro a terra
	var c: float = cos(p.theta)
	# D = v cos(t) T ;  h + v sin(t) T - g T^2 / 2 = 0   =>   v^2 = g D^2 / (2 cos^2(t) (D tan(t) + h))
	p.speed = (d / c) * sqrt(GRAVITY / (2.0 * (d * tan(p.theta) + h)))
	p.flight = d / (p.speed * c)
	p.t_land = T_REL + p.flight
	p.t_exit = p.t_land + LAND_HOLD
	p.duration = p.t_exit + EXIT_TIME + END_HOLD
	return p


static func phase_at(plan: Plan, t: float) -> int:
	if plan.instant:
		return Phase.LAND
	if t < T_TURN_END:
		return Phase.ENTER
	if t < KEY_T[1]:
		return Phase.SET
	if t < T_REL + SPIN_AFTER_REL:
		return Phase.SPIN
	if t < plan.t_land:
		return Phase.FLIGHT
	if t < plan.t_exit:
		return Phase.LAND
	return Phase.EXIT


# --- volo del peso ------------------------------------------------------------------------------------

## Posizione del centro del peso a `tau` secondi dal rilascio. Da tau >= T il peso e' fermo nel punto di caduta.
static func flight_position(plan: Plan, tau: float) -> Vector3:
	if tau >= plan.flight:
		var sink: float = clampf((tau - plan.flight) * 8.0, 0.0, 1.0) * plan.ball_r * 0.4   # si assesta nel terreno
		return Vector3(plan.landing.x, plan.ball_r - sink, plan.landing.z)
	var horiz: float = plan.speed * cos(plan.theta) * tau
	var y: float = plan.release.y + plan.speed * sin(plan.theta) * tau - 0.5 * GRAVITY * tau * tau
	return Vector3(plan.release.x + plan.vdir.x * horiz, y, plan.release.z + plan.vdir.z * horiz)


## Stato del peso a `t`: {pos, visible, in_hand, landed}. Prima del rilascio sta in mano (lo disegna l'atleta).
static func ball_at(plan: Plan, t: float) -> Dictionary:
	if plan.instant:
		return {"pos": Vector3(plan.landing.x, plan.ball_r * 0.6, plan.landing.z), "visible": true, "in_hand": false, "landed": true}
	if t < T_REL:
		return {"pos": plan.release, "visible": false, "in_hand": true, "landed": false}
	var tau: float = t - T_REL
	return {"pos": flight_position(plan, tau), "visible": true, "in_hand": false, "landed": tau >= plan.flight}


# --- posa dell'atleta ---------------------------------------------------------------------------------

static func _table(foul: bool) -> Dictionary:
	if _tables.has(foul):
		return _tables[foul]
	var tb: Dictionary = {
		"px":     [-0.74, -0.74, -0.70, -0.62, -0.45, -0.15, 0.22, 0.60, 0.55, 0.52, 0.52],
		"pz":     [0.00, 0.00, 0.08, 0.14, 0.12, 0.08, 0.00, -0.12, -0.05, 0.02, 0.02],
		"a":      [0.00, 0.00, 0.00, 0.35, 1.50, 2.30, 2.95, 3.24, 3.50, 3.65, 3.80],
		"py":     [0.505, 0.500, 0.465, 0.440, 0.445, 0.440, 0.450, 0.505, 0.500, 0.470, 0.500],
		"lean":   [0.12, 0.12, 0.30, 0.28, 0.20, 0.25, 0.12, -0.10, 0.05, 0.16, 0.08],
		"twist":  [0.00, 0.00, -0.60, -0.75, -0.80, -0.85, -0.55, 0.12, 0.20, 0.20, 0.00],
		"hpitch": [0.25, 0.25, 0.10, 0.05, 0.00, 0.00, -0.05, -0.30, -0.15, 0.00, 0.00],
		"flx":    [-0.74, -0.74, -0.72, -0.66, -0.60, -0.10, 0.62, 0.80, 0.80, 0.20, 0.30],
		"flz":    [0.22, 0.22, 0.24, 0.22, 0.20, -0.18, -0.22, -0.22, -0.22, -0.30, -0.28],
		"fll":    [0.0, 0.0, 0.0, 0.03, 0.0, 0.18, 0.02, 0.0, 0.0, 0.10, 0.0],
		"frx":    [-0.74, -0.74, -0.80, -0.80, -0.35, -0.05, -0.02, 0.28, 0.38, 0.60, 0.60],
		"frz":    [-0.22, -0.22, -0.25, -0.30, 0.45, 0.10, 0.04, 0.14, 0.25, 0.30, 0.30],
		"frl":    [0.0, 0.0, 0.0, 0.05, 0.30, 0.0, 0.0, 0.10, 0.22, 0.0, 0.0],
		"armr":   [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.15, 1.0, 1.35, 1.8, 2.0],
		"lhf":    [0.28, 0.28, 0.25, 0.20, 0.10, 0.20, 0.38, 0.0, 0.05, 0.10, 0.10],
		"lhl":    [0.12, 0.12, 0.35, 0.40, 0.42, 0.42, 0.30, 0.26, 0.28, 0.30, 0.20],
		"lhu":    [-0.18, -0.18, -0.05, 0.0, 0.05, 0.02, 0.05, -0.20, -0.22, -0.25, -0.35],
	}
	if foul:
		# Nullo: dopo il rilascio il piede destro scavalca il fermapiedi e atterra oltre il cerchio.
		tb["px"] = [-0.74, -0.74, -0.70, -0.62, -0.45, -0.15, 0.22, 0.60, 0.74, 0.84, 0.84]
		tb["frx"] = [-0.74, -0.74, -0.80, -0.80, -0.35, -0.05, -0.02, 0.28, 0.80, 1.34, 1.34]
		tb["frz"] = [-0.22, -0.22, -0.25, -0.30, 0.45, 0.10, 0.04, 0.14, 0.22, 0.22, 0.22]
		tb["frl"] = [0.0, 0.0, 0.0, 0.05, 0.30, 0.0, 0.0, 0.10, 0.28, 0.0, 0.0]
		tb["flx"] = [-0.74, -0.74, -0.72, -0.66, -0.60, -0.10, 0.62, 0.80, 0.80, 0.62, 0.55]
	_tables[foul] = tb
	return tb


static func _tangent(vals: Array, i: int) -> float:
	var n: int = KEY_T.size()
	if i <= 0 or i >= n - 1:
		return 0.0
	return (float(vals[i + 1]) - float(vals[i - 1])) / (float(KEY_T[i + 1]) - float(KEY_T[i - 1]))


## Interpolazione cubica di Hermite (tangenti di Catmull-Rom, nulle agli estremi) sulla griglia KEY_T.
static func _sample(vals: Array, t: float) -> float:
	var n: int = KEY_T.size()
	if t <= float(KEY_T[0]):
		return float(vals[0])
	if t >= float(KEY_T[n - 1]):
		return float(vals[n - 1])
	var i: int = 0
	while t > float(KEY_T[i + 1]):
		i += 1
	var t0: float = float(KEY_T[i])
	var h: float = float(KEY_T[i + 1]) - t0
	var u: float = (t - t0) / h
	var u2: float = u * u
	var u3: float = u2 * u
	return (2.0 * u3 - 3.0 * u2 + 1.0) * float(vals[i]) + (u3 - 2.0 * u2 + u) * h * _tangent(vals, i) \
		+ (-2.0 * u3 + 3.0 * u2) * float(vals[i + 1]) + (u3 - u2) * h * _tangent(vals, i + 1)


## Valori del corpo a `t` (solo dai tasti, per t >= T_SET): bacino, orientamento, piedi, braccio destro.
static func _keyed(plan: Plan, t: float) -> Dictionary:
	var tb: Dictionary = _table(plan.foul)
	var w: float = smoothstep(float(KEY_T[5]), float(KEY_T[7]), t)    # il corpo si gira verso il punto di caduta
	return {
		"P": Vector3(CENTER.x + _sample(tb["px"], t), 0.0, CENTER.z + _sample(tb["pz"], t)),
		"psi": PI + _sample(tb["a"], t) + plan.land_angle * w,
		"py": _sample(tb["py"], t),
		"lean": _sample(tb["lean"], t),
		"twist": _sample(tb["twist"], t),
		"hpitch": _sample(tb["hpitch"], t),
		"fl": Vector3(CENTER.x + _sample(tb["flx"], t), maxf(_sample(tb["fll"], t), 0.0), CENTER.z + _sample(tb["flz"], t)),
		"fr": Vector3(CENTER.x + _sample(tb["frx"], t), maxf(_sample(tb["frl"], t), 0.0), CENTER.z + _sample(tb["frz"], t)),
		"armr": _sample(tb["armr"], t),
		"lh": Vector3(_sample(tb["lhf"], t), _sample(tb["lhl"], t), _sample(tb["lhu"], t)),
	}


## Punto di rilascio: centro del peso con il braccio destro teso, calcolato dalla posa a T_REL (mai dallo scheletro).
static func _release_point(plan: Plan) -> Vector3:
	var b: Dictionary = _keyed(plan, T_REL)
	var h: float = plan.height
	var chi: float = float(b["psi"]) + float(b["twist"])
	var fwd: Vector3 = dir_at(chi)
	var right: Vector3 = Vector3(sin(chi), 0.0, cos(chi))
	var lean: float = b["lean"]
	var p: Vector3 = b["P"]
	var hip: Vector3 = Vector3(p.x, _hip_height(plan, b), p.z)
	var shoulder: Vector3 = hip + Vector3.UP * (SHOULDER_UP * h * cos(lean)) + fwd * (SHOULDER_UP * h * sin(lean)) + right * (_shoulder_side(plan) * h)
	var arm_dir: Vector3 = plan.dir * cos(ARM_ELEVATION) + Vector3.UP * sin(ARM_ELEVATION)
	return shoulder + arm_dir * (ARM_LENGTH * h * 0.97 + HAND_TO_BALL)


## Quota del bacino: quella dei tasti, ma mai oltre cio' che le gambe (piedi a terra) permettono di raggiungere.
static func _hip_height(plan: Plan, b: Dictionary) -> float:
	var h: float = plan.height
	var leg: float = LEG_LENGTH * h * 0.985
	var p: Vector3 = b["P"]
	var best: float = INF
	for key: String in ["fl", "fr"]:
		var f: Vector3 = b[key]
		var dxz: float = Vector2(p.x - f.x, p.z - f.z).length()
		var ankle_y: float = CIRCLE_TOP + ANKLE_H * h + f.y
		best = minf(best, ankle_y + sqrt(maxf(leg * leg - dxz * dxz, 0.04)))
	return clampf(minf(float(b["py"]) * h, best - HIP_ABOVE_PELVIS * h), 0.38 * h, 0.56 * h)


static func pose_at(plan: Plan, t: float) -> Pose:
	var po: Pose = Pose.new()
	var h: float = plan.height
	if t >= T_SET:
		var tk: float = minf(t, float(KEY_T[KEY_T.size() - 1]))
		var b: Dictionary = _keyed(plan, tk)
		po.mode = Mode.RIG
		po.root = b["P"]
		po.yaw = b["psi"]
		po.pelvis_y = _hip_height(plan, b)
		po.lean = b["lean"]
		po.twist = b["twist"]
		po.head_pitch = b["hpitch"]
		var ankle: float = CIRCLE_TOP + ANKLE_H * h
		po.foot_l = Vector3(b["fl"].x, ankle + b["fl"].y, b["fl"].z)
		po.foot_r = Vector3(b["fr"].x, ankle + b["fr"].y, b["fr"].z)
		var fwd_p: Vector3 = dir_at(po.yaw)
		po.knee_l = po.foot_l + fwd_p * 0.55 + Vector3.UP * 0.40
		po.knee_r = po.foot_r + fwd_p * 0.55 + Vector3.UP * 0.40
		_arms(plan, po, float(b["armr"]), b["lh"], t < T_REL)
		if t > plan.t_exit and not plan.instant:
			_apply_exit(plan, po, t)
		return po
	# Ingresso a piedi, rotazione sul posto e attesa: le gambe le muove l'animazione, le braccia (peso al collo) l'IK.
	po.lean = 0.06
	po.pelvis_y = 0.52 * h
	if t < T_ENTER_END:
		var u: float = t / T_ENTER_END
		var e: float = smoothstep(0.0, 1.0, u)
		po.root = Vector3(CENTER.x + lerpf(ENTER_X0, SET_X, e), 0.0, CENTER.z + lerpf(0.6, 0.0, e))
		po.yaw = 0.0
		po.walk_speed = (SET_X - ENTER_X0) * 6.0 * u * (1.0 - u) / T_ENTER_END
		po.mode = Mode.WALK
	elif t < T_TURN_END:
		var e2: float = smoothstep(0.0, 1.0, (t - T_ENTER_END) / (T_TURN_END - T_ENTER_END))
		po.root = Vector3(CENTER.x + SET_X, 0.0, CENTER.z)
		po.yaw = PI * e2
		po.walk_speed = 0.9
		po.mode = Mode.WALK
	else:
		po.root = Vector3(CENTER.x + SET_X, 0.0, CENTER.z)
		po.yaw = PI
		po.mode = Mode.IDLE
	_arms(plan, po, 0.0, Vector3(0.28, 0.12, -0.18), true)
	return po


## Braccia: destra (peso al collo -> teso al rilascio -> rilassato) e sinistra (equilibrio, poi blocco). Tutto in
## coordinate di mondo, nel sistema del busto (orientato come bacino + torsione).
static func _arms(plan: Plan, po: Pose, arm_r: float, lh: Vector3, ball_in_hand: bool) -> void:
	var h: float = plan.height
	var s: float = h / 1.82
	var chi: float = po.yaw + po.twist
	var fwd: Vector3 = dir_at(chi)
	var left: Vector3 = Vector3(-sin(chi), 0.0, -cos(chi))
	var right: Vector3 = -left
	var hip: Vector3 = Vector3(po.root.x, po.pelvis_y, po.root.z)
	var up_s: Vector3 = Vector3.UP * (SHOULDER_UP * h * cos(po.lean)) + fwd * (SHOULDER_UP * h * sin(po.lean))
	var sh_r: Vector3 = hip + up_s + right * (_shoulder_side(plan) * h)
	var sh_l: Vector3 = hip + up_s + left * (_shoulder_side(plan) * h)
	var neck: Vector3 = hip + Vector3.UP * (NECK_UP * h * cos(po.lean)) + fwd * (NECK_UP * h * sin(po.lean))
	var ball_hold: Vector3 = neck + right * 0.075 + fwd * 0.09 + Vector3.UP * 0.02
	var wrist_hold: Vector3 = ball_hold - Vector3.UP * (0.10 * s) - fwd * 0.03 + right * 0.04
	var arm_dir: Vector3 = plan.dir * cos(ARM_ELEVATION) + Vector3.UP * sin(ARM_ELEVATION)
	var wrist_ext: Vector3 = plan.release - arm_dir * HAND_TO_BALL
	var wrist_relax: Vector3 = sh_r + fwd * 0.12 + right * 0.10 - Vector3.UP * (0.40 * s)
	var elbow_hold: Vector3 = sh_r + right * 0.45 + Vector3.UP * 0.12 - fwd * 0.05
	var elbow_ext: Vector3 = sh_r - plan.dir * 0.20 + right * 0.25 - Vector3.UP * 0.30
	var elbow_relax: Vector3 = sh_r + right * 0.35 - Vector3.UP * 0.10
	if plan.instant:
		wrist_ext = wrist_hold
		elbow_ext = elbow_hold
	var a: float = clampf(arm_r, 0.0, 1.0)
	if arm_r <= 1.0:
		po.hand_r = wrist_hold.lerp(wrist_ext, a)
		po.elbow_r = elbow_hold.lerp(elbow_ext, a)
		po.ball_off = (ball_hold - wrist_hold).lerp(plan.release - wrist_ext, a)
	else:
		var r: float = clampf(arm_r - 1.0, 0.0, 1.0)
		po.hand_r = wrist_ext.lerp(wrist_relax, r)
		po.elbow_r = elbow_ext.lerp(elbow_relax, r)
	po.ball_in_hand = ball_in_hand and arm_r <= 1.0
	po.hand_l = sh_l + fwd * (lh.x * s) + left * (lh.y * s) + Vector3.UP * (lh.z * s)
	po.elbow_l = sh_l + left * 0.40 - Vector3.UP * 0.20 - fwd * 0.10


## Uscita: dopo la misura l'atleta si gira e se ne va dalla parte posteriore della pedana (non dal davanti: sarebbe nullo).
static func _apply_exit(plan: Plan, po: Pose, t: float) -> void:
	var last: Pose = pose_at(plan, plan.t_exit - 0.0001)
	var u: float = clampf((t - plan.t_exit) / EXIT_TIME, 0.0, 1.0)
	var e: float = smoothstep(0.0, 1.0, u)
	po.mode = Mode.WALK
	po.arms_ik = false
	po.ball_in_hand = false
	po.root = Vector3(lerpf(last.root.x, CENTER.x + EXIT_X, e), 0.0, lerpf(last.root.z, CENTER.z + 0.3, e))
	po.yaw = lerpf(last.yaw, 3.0 * PI, smoothstep(0.0, 0.4, u))
	po.walk_speed = absf(CENTER.x + EXIT_X - last.root.x) * 6.0 * u * (1.0 - u) / EXIT_TIME
	po.pelvis_y = 0.52 * plan.height
	po.lean = 0.0
	po.twist = 0.0


static func _shoulder_side(plan: Plan) -> float:
	return SHOULDER_SIDE_F if plan.female else SHOULDER_SIDE
