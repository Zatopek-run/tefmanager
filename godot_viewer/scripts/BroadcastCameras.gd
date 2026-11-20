class_name BroadcastCameras
extends Node3D
## VIEW 3D - regia broadcast, ricavata dalle dirette di riferimento (100m di Roma, 400m di Parigi 2024).
## I cambi di ripresa dipendono dallo STATO della gara (clock prima dello sparo, tratto dell'anello dopo), non dal
## tempo reale: valgono quindi a 1x come a 8x. In gara la MIRA e' sempre esattamente sul primo in classifica.
##
## 100m (vedi _direct_100m): apertura larga dall'alto dietro i blocchi -> primo piano basso sui blocchi (teleobiettivo,
##   sfondo sfocato) -> ripresa larga dello start -> carrello alto su Path3D che segue il gruppo (il primo a destra
##   del centro) -> ripresa dall'alto sul traguardo -> corsa oltre il traguardo, sulla curva.
## Ovale (vedi _direct_oval, 400m): apertura larga sulla partenza sfalsata -> primo piano sui blocchi -> ripresa larga dello
##   start (resta finche' il primo e' in curva 1) -> dal lato opposto dell'interno con teleobiettivo (rettilineo opposto)
##   -> dall'alto sulla curva 2 -> carrello alto sul rettilineo d'arrivo -> traguardo -> oltre il traguardo.
##
## Nodi attesi (definiti in Stadium.tscn):
##   Cameras (questo script)
##   |- BroadcastPath (Path3D)  -> la curva viene scritta qui in _ready()
##   |  \- CameraDolly (PathFollow3D)
##   |     \- SideCam (Camera3D)        (carrello alto)
##   \- FinishCam (Camera3D)

const TRACK_Z_CENTER: float = 4.27        # centro delle 8 corsie sul rettilineo d'arrivo
const PATH_Z: float = 20.7                # carrello alto sul lato esterno: ~30 gradi di inclinazione sul centro pista
const PATH_Y: float = 9.5
const PATH_START_X: float = -112.0
const PATH_END_X: float = 70.0
const TRACK_FOV: float = 24.0             # il gruppo occupa circa meta' inquadratura
const LEAD_IN_FRAME: float = 3.0          # il primo sta 3 m a destra del centro dell'inquadratura (~70% della larghezza)
const CUT_BEFORE_FINISH: float = 10.0     # stacco sul traguardo quando mancano meno di questi metri
# Dopo l'arrivo del primo si torna al carrello alto sulla corsa oltre il traguardo: il ritardo non e'
# piu' fisso, vedi RaceController.finish_hold() (si allunga sui fotofinish piu' combattuti).
# Preparazione (secondi di clock prima dello sparo):
const OPEN_WIDE_TIME: float = 0.8         # apertura larga
const WIDE_CUT_BEFORE_GUN_100M: float = 0.4
const WIDE_CUT_BEFORE_GUN_OVAL: float = 2.2   # nei 400m lo start largo si vede piu' a lungo
const START_WIDE_HOLD: float = 1.7        # 100m: la ripresa larga resta fino a questo tempo di gara
const FINISH_CAM_Z: float = 16.0
const REPLAY_CAM_AHEAD: float = 7.0      # ralenti: la camera sta cosi' oltre la linea del traguardo
const REPLAY_CAM_Y: float = 3.0       # alta abbastanza da guardare sopra fotografi e giudici (z 12-17, alti ~1,7 m)
const REPLAY_CAM_Z: float = 19.0
const REPLAY_FOV: float = 22.0
# Inquadratura adattiva del carrello alto:
const FRAME_WIDTH_BASE: float = 14.4      # larghezza (m) inquadrata dal carrello con fov TRACK_FOV a distanza base
const FRAME_MARGIN: float = 8.0      # margine: la corsia piu' vicina alla camera appare piu' larga (prospettiva)
const FRAME_PULLBACK_MAX: float = 1.6     # oltre z = 47 il carrello finirebbe nelle tribune
const FRAME_FOV_MAX: float = 50.0

@onready var _path: Path3D = $BroadcastPath
@onready var _dolly: PathFollow3D = $BroadcastPath/CameraDolly
@onready var _side_cam: Camera3D = $BroadcastPath/CameraDolly/SideCam
@onready var _finish_cam: Camera3D = $FinishCam

var _oval: bool = false
var _field: bool = false
var _race_distance: float = 100.0
var _current_cam: Camera3D = null
var _frame_scale: float = 1.0             # allontanamento attuale del carrello alto
var _frame_fov: float = TRACK_FOV

# 100m
var _open_cam: Camera3D
var _close_cam: Camera3D
var _start_cam: Camera3D
# ovale
var _o_open: Camera3D
var _o_close: Camera3D
var _o_start: Camera3D
var _o_far: Camera3D
var _o_curve: Camera3D
# concorsi (Salto in Lungo)
var _field_cam: Camera3D
# getto del peso (regia guidata dalla fase del tentativo, vedi _direct_shot)
var _sp_sector: Camera3D   # panoramica sul settore (prima dei tentativi e per i tentativi non animati)
var _sp_wide: Camera3D     # ingresso, posizione iniziale e uscita: larga, dal lato del settore
var _sp_spin: Camera3D     # rotazione: teleobiettivo laterale (lato del braccio che lancia)
var _sp_fly: Camera3D      # volo: teleobiettivo laterale che segue il peso
var _sp_land: Camera3D     # atterraggio: sul cratere, poi nastro e bandierina
# ralenti dell'arrivo (corse)
var _replay_cam: Camera3D


func _ready() -> void:
	var curve: Curve3D = Curve3D.new()
	curve.add_point(Vector3(PATH_START_X, PATH_Y, PATH_Z))
	curve.add_point(Vector3(PATH_END_X, PATH_Y, PATH_Z))
	_path.curve = curve
	_dolly.loop = false
	_dolly.rotation_mode = PathFollow3D.ROTATION_NONE  # l'orientamento lo decide look_at(), non la curva

	# Una lente per camera: la sfocatura sullo sfondo parte oltre il soggetto, non sui corridori.
	_side_cam.fov = TRACK_FOV             # teleobiettivo: schiaccia la prospettiva come in TV
	_side_cam.attributes = _make_lens(60.0)
	_finish_cam.attributes = _make_lens(60.0)

	var sx: float = TrackGeometry.START_100M_X
	_open_cam = _make_static_cam(Vector3(sx - 15.0, 9.0, 4.4), Vector3(sx + 12.0, 0.3, 4.4), 40.0, 60.0)
	# Primo piano basso con teleobiettivo: lo sfondo e' sfocato; angolo e distanza vengono dal confronto con il video.
	_close_cam = _make_static_cam(Vector3(sx + 1.4, 0.75, 12.5), Vector3(sx - 0.5, 0.55, 5.0), 42.0, 9.0)
	_start_cam = _make_static_cam(Vector3(sx + 9.0, 11.0, 19.0), Vector3(sx + 3.0, 0.3, 3.6), 42.0, 40.0)

	var s: float = TrackGeometry.STRAIGHT
	_o_open = _make_static_cam(Vector3(-14.0, 17.0, -20.0), Vector3(20.0, 0.0, -12.0), 50.0, 80.0)
	_o_close = _make_static_cam(Vector3(0.0, 1.0, 5.0), Vector3(0.0, 0.5, 0.0), 38.0, 7.0)   # riposizionata in reset()
	_o_start = _make_static_cam(Vector3(-14.0, 12.0, -26.0), Vector3(15.0, 0.0, -8.0), 42.0, 120.0)   # inquadra tutte le 8 corsie sfalsate
	_o_far = _make_static_cam(Vector3(-s * 0.5, 5.0, 34.0), Vector3(-s * 0.5, 0.8, -78.0), 9.0, 600.0)   # teleobiettivo dall'altro lato
	_o_curve = _make_static_cam(Vector3(-s - 72.0, 18.0, -36.8), Vector3(-s - 30.0, 0.8, -36.8), 30.0, 150.0)
	_field_cam = _make_static_cam(Vector3(-12.0, 3.4, -3.5), Vector3(-12.0, 0.9, -14.0), 34.0, 80.0)
	var sp_c: Vector3 = ShotPutMotion.CENTER
	_sp_sector = _make_static_cam(sp_c + Vector3(-7.0, 7.5, 17.0), sp_c + Vector3(11.0, 0.0, -1.0), 50.0, 300.0)
	_sp_wide = _make_static_cam(sp_c + Vector3(-3.4, 1.9, 6.6), sp_c + Vector3(-0.9, 1.0, 0.0), 30.0, 90.0)
	_sp_spin = _make_static_cam(sp_c + Vector3(0.8, 1.55, 6.8), sp_c + Vector3(0.0, 1.2, 0.0), 24.0, 60.0)
	_sp_fly = _make_static_cam(sp_c + Vector3(8.0, 2.4, 16.0), sp_c + Vector3(8.0, 3.0, 0.0), 22.0, 400.0)
	_sp_land = _make_static_cam(sp_c + Vector3(10.0, 1.1, 4.0), sp_c + Vector3(12.0, 0.2, 0.0), 30.0, 120.0)
	# Ralenti: teleobiettivo basso a bordo pista oltre il traguardo, guarda i corridori che arrivano (3/4 frontale).
	_replay_cam = _make_static_cam(Vector3(TrackGeometry.FINISH_X + REPLAY_CAM_AHEAD, REPLAY_CAM_Y, REPLAY_CAM_Z),
		Vector3(TrackGeometry.FINISH_X - 20.0, 1.0, TRACK_Z_CENTER), REPLAY_FOV, 120.0)

	RaceController.race_loaded.connect(func(_r: Array[RunnerData], _i: Dictionary) -> void: reset())
	reset()


func _make_static_cam(pos: Vector3, target: Vector3, fov_deg: float, dof_far: float) -> Camera3D:
	var cam: Camera3D = Camera3D.new()
	add_child(cam)
	cam.fov = fov_deg
	cam.attributes = _make_lens(dof_far)
	cam.look_at_from_position(pos, target, Vector3.UP)
	return cam


func _make_lens(far_distance: float) -> CameraAttributesPractical:
	var lens: CameraAttributesPractical = CameraAttributesPractical.new()
	lens.dof_blur_far_enabled = true      # sfoca tribune e sfondo, tiene a fuoco le corsie
	lens.dof_blur_far_distance = far_distance
	lens.dof_blur_far_transition = 25.0
	lens.dof_blur_amount = 0.08
	return lens


## Riconfigura per la gara caricata (100m oppure ovale) e riporta le camere alla preparazione.
func reset() -> void:
	_field = RaceController.is_field(RaceController.event_kind)
	_oval = (not _field) and RaceController.event_kind != "100m"
	_race_distance = RaceMotion.race_distance(RaceController.event_kind)
	var fx: float = TrackGeometry.FINISH_X
	if _field:
		if RaceController.event_kind == "Getto del Peso":
			_field_cam.look_at_from_position(Vector3(-34.0, 4.2, -22.0), Vector3(-36.0, 1.3, -36.0), Vector3.UP)
		else:
			_field_cam.look_at_from_position(Vector3(-12.0, 3.4, -3.5), Vector3(-12.0, 0.9, -14.0), Vector3.UP)
	elif _oval:
		var s: float = TrackGeometry.STRAIGHT
		# Traguardo ovale: dall'alto, appena oltre la linea, sul lato esterno (si vede tutto il gruppo).
		_finish_cam.fov = 38.0
		_finish_cam.look_at_from_position(Vector3(fx + 3.0, 11.0, 22.0), Vector3(fx - 9.0, 0.4, TRACK_Z_CENTER), Vector3.UP)
		if RaceController.event_kind == "1500m" or RaceController.event_kind == "800m":
			var wp: Dictionary = TrackGeometry.runner_pose(RaceController.event_kind, 4, 0.0)
			var wpos: Vector3 = wp["position"]
			var wh: Vector2 = wp["heading"]
			var wright: Vector3 = Vector3(-wh.y, 0.0, wh.x)
			_o_open.look_at_from_position(wpos + wright * 18.0 + Vector3(0.0, 11.0, 0.0), wpos + Vector3(0.0, 0.6, 0.0), Vector3.UP)
			_o_close.look_at_from_position(wpos + wright * 5.0 + Vector3(wh.x, 0.0, wh.y) * 2.5 + Vector3(0.0, 1.3, 0.0), wpos + Vector3(0.0, 0.9, 0.0), Vector3.UP)
			_o_start.look_at_from_position(Vector3(-14.0, 12.0, -26.0), wpos + Vector3(0.0, 0.6, 0.0), Vector3.UP)
		else:
			_o_open.look_at_from_position(Vector3(-14.0, 17.0, -20.0), Vector3(20.0, 0.0, -12.0), Vector3.UP)
			_o_start.look_at_from_position(Vector3(-14.0, 12.0, -26.0), Vector3(15.0, 0.0, -8.0), Vector3.UP)
			# Primo piano sui blocchi della corsia 6 (al centro dello schieramento), dal lato esterno.
			var pose: Dictionary = TrackGeometry.pose(6, 0.0)
			var h: Vector2 = pose["heading"]
			var right: Vector3 = Vector3(-h.y, 0.0, h.x)
			var p: Vector3 = pose["position"]
			_o_close.look_at_from_position(p + right * 3.4 + Vector3(0.0, 0.75, 0.0),
				p + Vector3(h.x, 0.0, h.y) * -0.3 + Vector3(0.0, 0.5, 0.0), Vector3.UP)
			_o_start.position = Vector3(-14.0, 12.0, -26.0)
			_o_open.position = Vector3(-14.0, 17.0, -20.0)
			_o_far.position = Vector3(-s * 0.5, 5.0, 34.0)
	else:
		# 100m: dall'alto, appena oltre la linea, sul lato esterno; i corridori arrivano da sinistra.
		_finish_cam.fov = 30.0
		_finish_cam.look_at_from_position(Vector3(fx + 3.0, 10.0, 20.0), Vector3(fx - 5.0, 0.4, TRACK_Z_CENTER), Vector3.UP)
	_current_cam = null
	_direct()


func _process(_delta: float) -> void:
	_direct()


func _direct() -> void:
	if RaceController.state == RaceController.State.REPLAY and not _field:
		_direct_replay()
	elif _field:
		_direct_field()
	elif _oval:
		_direct_oval()
	else:
		_direct_100m()


func _direct_field() -> void:
	if RaceController.event_kind == "Getto del Peso":
		_direct_shot()
	else:
		_apply(_field_cam)


## Regia del getto del peso, legata alla FASE del tentativo (ShotPutMotion.phase_at), non al tempo reale: vale a 1x come a 8x.
## ingresso/posizione iniziale = larga di lato e un po' da dietro (si vede il volto dell'atleta, di spalle al settore) ->
## rotazione e rilascio = teleobiettivo dal lato del braccio che lancia -> volo = teleobiettivo laterale che segue il peso ->
## atterraggio = sul cratere (poi nastro e bandierina) -> uscita = di nuovo larga. Senza tentativo animato: panoramica del settore.
func _direct_shot() -> void:
	var rc: Node = RaceController
	var plan: ShotPutMotion.Plan = rc.shot_plan
	var cam: Camera3D = _sp_sector
	if plan != null and not plan.instant and rc.state == rc.State.RUNNING:
		var t: float = rc.shot_t
		var pose: ShotPutMotion.Pose = rc.shot_pose
		var focus: Vector3 = (pose.root if pose != null else ShotPutMotion.CENTER) + Vector3(0.0, 1.0, 0.0)
		match rc.shot_phase:
			ShotPutMotion.Phase.ENTER, ShotPutMotion.Phase.SET, ShotPutMotion.Phase.EXIT:
				cam = _sp_wide
				cam.look_at(focus, Vector3.UP)
			ShotPutMotion.Phase.SPIN:
				cam = _sp_spin
				var u: float = clampf((t - float(ShotPutMotion.KEY_T[1])) / (ShotPutMotion.T_REL + ShotPutMotion.SPIN_AFTER_REL - float(ShotPutMotion.KEY_T[1])), 0.0, 1.0)
				cam.position = ShotPutMotion.CENTER + Vector3(lerpf(-0.6, 1.4, u), 1.55, 6.8 - 1.0 * u)   # lento avvicinamento
				cam.look_at(focus + Vector3(0.0, 0.2, 0.0), Vector3.UP)
			ShotPutMotion.Phase.FLIGHT:
				cam = _sp_fly
				var mid: Vector3 = (plan.release + plan.landing) * 0.5
				cam.position = Vector3(mid.x, 4.5, mid.z + 11.0 + 0.5 * plan.mark)
				cam.look_at(rc.shot_pos, Vector3.UP)
			ShotPutMotion.Phase.LAND:
				cam = _sp_land
				cam.position = plan.landing + Vector3(-2.6, 1.1, 3.6)
				cam.look_at(plan.landing + Vector3(0.0, 0.15, 0.0), Vector3.UP)
	_apply(cam)


## Ralenti: camera fissa bassa vicino al traguardo, mira esatta sul primo (come le altre camere che seguono la gara).
func _direct_replay() -> void:
	_replay_cam.look_at(_leader_world_position() + Vector3(0.0, 0.9, 0.0), Vector3.UP)
	_apply(_replay_cam)


## Regia dei 100m, scelta in base allo stato della gara.
func _direct_100m() -> void:
	var rc: Node = RaceController
	var cam: Camera3D = _side_cam
	match rc.state:
		rc.State.IDLE, rc.State.LOADED:
			cam = _open_cam
		rc.State.COUNTDOWN:
			if rc.clock < OPEN_WIDE_TIME:
				cam = _open_cam
			elif rc.clock < rc.gun_at - WIDE_CUT_BEFORE_GUN_100M:
				cam = _close_cam
			else:
				cam = _start_cam
		_:
			var live: Array[RunnerData] = rc.live_order
			var leader_done: bool = not live.is_empty() and live[0].finished
			if rc.race_time < START_WIDE_HOLD:
				cam = _start_cam
			elif leader_done and rc.race_time > live[0].final_time + rc.finish_hold():
				cam = _side_cam  # corsa oltre il traguardo, di nuovo dall'alto
			elif rc.leader_distance() >= _race_distance - CUT_BEFORE_FINISH:
				cam = _finish_cam
	_apply(cam)


## Regia sull'ovale (400m): una ripresa per tratto dell'anello in cui si trova il primo in classifica.
func _direct_oval() -> void:
	var rc: Node = RaceController
	var cam: Camera3D = _o_start
	match rc.state:
		rc.State.IDLE, rc.State.LOADED:
			cam = _o_open
		rc.State.COUNTDOWN:
			if rc.clock < OPEN_WIDE_TIME:
				cam = _o_open
			elif rc.clock < rc.gun_at - WIDE_CUT_BEFORE_GUN_OVAL:
				cam = _o_close
			else:
				cam = _o_start
		_:
			var live: Array[RunnerData] = rc.live_order
			if not live.is_empty():
				var lead: RunnerData = live[0]
				if lead.finished and rc.race_time > lead.final_time + rc.finish_hold():
					cam = _side_cam
				elif lead.distance >= _race_distance - CUT_BEFORE_FINISH:
					cam = _finish_cam
				else:
					match TrackGeometry.region_for(RaceController.event_kind, lead.lane, lead.distance):
						TrackGeometry.Region.ARC1: cam = _o_start
						TrackGeometry.Region.BACK: cam = _o_far
						TrackGeometry.Region.ARC2: cam = _o_curve
						_: cam = _side_cam
	_apply(cam)


func _apply(cam: Camera3D) -> void:
	if cam != _current_cam:
		_current_cam = cam
		cam.make_current()
	# Mira esatta sul primo in classifica per le camere che seguono la gara (nessun ritardo di inseguimento).
	if cam == _side_cam:
		_update_side_cam()
	elif cam == _field_cam:
		if RaceController.event_kind == "Getto del Peso":
			var focus: Vector3 = RaceController.shot_pos if RaceController.shot_visible else RaceController.jumper_pos
			_field_cam.fov = 40.0
			_field_cam.position = Vector3(clampf(focus.x + 0.5, -42.0, -22.0), 4.6, -16.0)
			_field_cam.look_at(Vector3(lerpf(RaceController.jumper_pos.x, focus.x, 0.65), clampf(focus.y * 0.60, 1.2, 3.0), focus.z), Vector3.UP)
		else:
			var jp: Vector3 = RaceController.jumper_pos
			_field_cam.fov = 34.0
			_field_cam.position = Vector3(clampf(jp.x + 6.0, -34.0, 2.0), 3.4, -3.5)
			_field_cam.look_at(jp + Vector3(1.5, 0.9, 0.0), Vector3.UP)
	elif cam == _o_start or cam == _o_far or cam == _o_curve:
		if RaceController.state == RaceController.State.RUNNING or RaceController.state == RaceController.State.FINISHED:
			cam.look_at(_leader_world_position() + Vector3(0.0, 0.9, 0.0), Vector3.UP)


## Carrello alto su Path3D: il primo sta a destra del centro (ripresa TV) e TUTTI i corridori ancora in gara restano
## in inquadratura: se il gruppo si sparpaglia (400m sul rettilineo d'arrivo) la camera si allontana e apre l'obiettivo.
func _update_side_cam() -> void:
	var leader: Vector3 = _leader_world_position()
	var spread: float = _racing_spread()
	var a: float = maxf(LEAD_IN_FRAME, spread * 0.28)   # distanza del primo dal centro dell'inquadratura
	var width_needed: float = 2.0 * maxf(a, spread - a) + FRAME_MARGIN
	var s_goal: float = clampf(sqrt(width_needed / FRAME_WIDTH_BASE), 1.0, FRAME_PULLBACK_MAX)
	var fov_goal: float = clampf(TRACK_FOV * width_needed / (FRAME_WIDTH_BASE * s_goal), TRACK_FOV, FRAME_FOV_MAX)
	var weight: float = 1.0 - exp(-3.0 * get_process_delta_time() * RaceController.play_speed())
	_frame_scale = lerpf(_frame_scale, s_goal, weight)
	_frame_fov = lerpf(_frame_fov, fov_goal, weight)
	var aim: Vector3 = leader
	aim.x -= a
	aim.z = TRACK_Z_CENTER                       # si guarda il centro pista, non la corsia del primo
	_dolly.progress = clampf(aim.x - PATH_START_X, 0.0, PATH_END_X - PATH_START_X)
	# Allontanamento: il vettore camera -> centro pista cresce di _frame_scale (la camera e' figlia del carrello).
	_side_cam.position = Vector3(0.0, PATH_Y * (_frame_scale - 1.0), (PATH_Z - TRACK_Z_CENTER) * (_frame_scale - 1.0))
	_side_cam.fov = _frame_fov
	_side_cam.look_at(aim + Vector3(0.0, 0.4, 0.0), Vector3.UP)


## Distanza (m) fra il primo e l'ultimo dei corridori ancora in gara (esclusi arrivati e ritirati).
func _racing_spread() -> float:
	var lo: float = INF
	var hi: float = -INF
	for r: RunnerData in RaceController.runners:
		if r.finished or r.dnf:
			continue
		lo = minf(lo, r.distance)
		hi = maxf(hi, r.distance)
	return maxf(0.0, hi - lo) if hi >= lo else 0.0


## Posizione del primo in classifica. Prima dello sparo: centro delle corsie alla linea di partenza.
func _leader_world_position() -> Vector3:
	var live: Array[RunnerData] = RaceController.live_order
	if live.is_empty() or RaceController.state == RaceController.State.LOADED or RaceController.state == RaceController.State.COUNTDOWN:
		return TrackGeometry.runner_pose(RaceController.event_kind, 4, 0.0)["position"]
	return TrackGeometry.runner_pose(RaceController.event_kind, live[0].lane, live[0].distance)["position"]
