extends Node
## CONTROLLER - orchestra la gara. Legge dal Model (DatabaseManager) e aggiorna lo stato dei corridori;
## le View (Stadium, HUD) leggono questo stato e si collegano ai segnali. Non decide mai un risultato.
##
## Tempo: `clock` e' il tempo di animazione (include il conto alla rovescia, lo sparo e' a GUN_AT);
## `race_time` e' il tempo di gara dallo sparo. Ogni corridore corre per (final_time - reaction_time)
## secondi dopo la reazione, quindi taglia il traguardo esattamente a `final_time` (vedi RaceMotion).
## Il tempo scorre in tempo reale (nessuna compressione, anche per le gare lunghe): e' l'utente a poter
## accelerare con `time_scale` (tasti 1/2/4/8 in Stadium).

signal race_loaded(runners: Array[RunnerData], info: Dictionary)
signal countdown_started()
signal gun_fired()
signal runner_finished(runner: RunnerData)
signal race_finished(results: Array[RunnerData])

enum State { IDLE, LOADED, COUNTDOWN, RUNNING, REPLAY, FINISHED }

## Ralenti dell'arrivo (solo corse): finita la gara rivede gli ultimi secondi del vincitore a velocita' ridotta, da
## un'altra inquadratura. E' solo regia: i risultati sono gia' calcolati, il tempo di gara viene riavvolto e le
## posizioni si rileggono dalla stessa curva (RaceMotion); `finished` e i segnali non vengono toccati durante il replay.
## Valori allineati al replay della vista PyQt (`REPLAY_LOOKBACK`, `REPLAY_SPEED` in race_viewer.py).
const REPLAY_SPEED: float = 0.35
const REPLAY_LOOKBACK: float = 3.0   # secondi di gara prima del traguardo del vincitore da cui riparte
const REPLAY_AFTER: float = 1.8      # secondi dopo il traguardo del vincitore a cui si ferma

const GUN_AT: float = 2.4          # secondi tra "via" al conto alla rovescia e lo sparo (default)
## Preparazione piu' lunga per i 100m, come nella diretta TV: apertura larga, lungo primo piano sui blocchi, sparo.
const GUN_AT_BY_KIND: Dictionary = {"100m": 9.0, "400m": 7.0, "800m": 4.6, "1500m": 4.2, "4x100m": 6.5, "4x400m": 5.0, "Salto in Lungo": 1.6, "Getto del Peso": 1.6}


static func is_relay(kind: String) -> bool:
	return kind == "4x100m" or kind == "4x400m"


static func is_field(kind: String) -> bool:
	return kind == "Salto in Lungo" or kind == "Getto del Peso"


static func uses_blocks(kind: String) -> bool:
	return kind != "1500m" and kind != "800m" and not is_field(kind)


var field_queue: Array[Dictionary] = []
## Prove per atleta nei concorsi (3 + 3 con 8 partecipanti o meno). Si ricava dalle prove lette dal DB; senza dati vale
## FIELD_ROUNDS_DEFAULT, che deve coincidere con `FIELD_ROUNDS` di views/race_viewer.py.
const FIELD_ROUNDS_DEFAULT := 6
var field_rounds: int = FIELD_ROUNDS_DEFAULT
var field_idx: int = 0
var field_step_t: float = 0.0
var active_jumper: RunnerData = null
var jumper_pos: Vector3 = Vector3(-36.0, 0.0, -14.0)
var jumper_yaw: float = 0.0
var jumper_anim: StringName = &"Idle"
var jumper_speed_scale: float = 1.0
## Getto del peso (vedi models/ShotPutMotion.gd): il tentativo in corso, il suo tempo, la fase (per la regia), la posa
## dell'atleta (null = tentativo non animato) e il peso in volo. `shot_pos` e `shot_visible` descrivono il peso in volo o a
## terra; prima del rilascio sta in mano all'atleta (lo disegna RunnerView) e `shot_visible` e' falso.
var shot_plan: ShotPutMotion.Plan = null
var shot_t: float = 0.0
var shot_phase: int = ShotPutMotion.Phase.ENTER
var shot_pose: ShotPutMotion.Pose = null
var shot_pos: Vector3 = Vector3(-41.0, 1.5, -36.0)
var shot_visible: bool = false
var field_caption: String = ""
var field_value_text: String = ""
var field_landed_mark: float = -1.0
var field_landed_foul: bool = false
const SET_CALL_AT: float = 1.5          # "set": questi secondi prima dello sparo il corridore comincia a salire
const SET_RISE_TIME: float = 0.75
const AFTER_FINISH_SECONDS: float = 4.0  # quanto resta in RUNNING dopo l'ultimo arrivo (lancio oltre il traguardo)

var state: State = State.IDLE
var info: Dictionary = {}
var gun_at: float = GUN_AT            # secondi di preparazione prima dello sparo per l'evento caricato
var event_kind: String = "100m"       # nome dell'evento: sceglie curva, distanza e geometria della pista
var runners: Array[RunnerData] = []
var live_order: Array[RunnerData] = []  # ordine di classifica aggiornato a ogni fotogramma
var clock: float = 0.0
var race_time: float = 0.0
var display_time: float = 0.0           # cronometro: si blocca sul tempo del vincitore
var time_scale: float = 1.0
var replay_enabled: bool = true       # false: niente ralenti (test, o chi vuole andare dritto al finale)
var _skip_replay: bool = false        # "Salta alla fine" salta anche il ralenti
var _replay_start: float = 0.0
var _replay_end: float = 0.0

var _finished_count: int = 0
var _finisher_count: int = 0       # corridori che arrivano al traguardo (esclusi i ritirati)
var _announced: bool = false
var _winner_time: float = 0.0
var _last_finish_time: float = 0.0
var finish_margin: float = INF     # distacco 1°-2° (noto subito, il modello ha gia' calcolato il risultato)


## Carica la gara dal DB. Ritorna false se non ci sono corridori validi.
func load_race(race_id: int) -> bool:
	var loaded: Array[RunnerData] = DatabaseManager.get_race_runners(race_id)
	if loaded.is_empty():
		push_error("RaceController: nessun corridore per la gara %d." % race_id)
		return false
	if loaded.all(func(r: RunnerData) -> bool: return r.dnf):
		push_error("RaceController: gara %d senza classificati (tutti ritirati)." % race_id)
		return false
	var loaded_info: Dictionary = DatabaseManager.get_race_info(race_id)
	var kind: String = str(loaded_info.get("event_name", "100m"))
	if not RaceMotion.is_supported(kind) and not is_field(kind):
		push_error("RaceController: evento '%s' non supportato dal visualizzatore." % kind)
		return false
	runners = loaded
	info = loaded_info
	event_kind = kind
	gun_at = float(GUN_AT_BY_KIND.get(kind, GUN_AT))
	_assign_places()
	_finisher_count = 0
	_winner_time = INF
	_last_finish_time = 0.0
	var finish_times: Array[float] = []
	for r: RunnerData in runners:
		if not r.dnf:
			_finisher_count += 1
			_winner_time = minf(_winner_time, r.final_time)
			_last_finish_time = maxf(_last_finish_time, r.final_time)
			finish_times.append(r.final_time)
		r.distance = 0.0
		r.speed = 0.0
		r.finished = false
		r.attempts = []
		r.best_mark = 0.0
		r.revealed_rounds = 0
	finish_times.sort()
	finish_margin = finish_times[1] - finish_times[0] if finish_times.size() >= 2 else INF
	live_order = runners.duplicate()
	field_queue.clear()
	field_idx = 0
	field_step_t = 0.0
	active_jumper = null
	jumper_pos = _shot_wait_position() if kind == "Getto del Peso" else Vector3(-36.0, 0.0, -14.0)
	jumper_yaw = PI if kind == "Getto del Peso" else 0.0
	jumper_anim = &"Idle"
	jumper_speed_scale = 1.0
	shot_plan = null
	shot_t = 0.0
	shot_phase = ShotPutMotion.Phase.ENTER
	shot_pose = null
	shot_pos = Vector3(-41.0, 1.5, -36.0)
	shot_visible = false
	field_caption = ""
	field_value_text = ""
	field_landed_mark = -1.0
	field_landed_foul = false
	if is_field(kind):
		_init_field_queue(race_id)
	clock = 0.0
	race_time = 0.0
	display_time = 0.0
	_finished_count = 0
	_announced = false
	_skip_replay = false
	state = State.LOADED
	race_loaded.emit(runners, info)
	return true


func start() -> void:
	if state != State.LOADED:
		return
	state = State.COUNTDOWN
	countdown_started.emit()


## Salta alla fine: porta il tempo oltre l'ultimo arrivo (i risultati non cambiano).
func skip_to_end() -> void:
	if state == State.REPLAY:
		_end_replay()
		return
	_skip_replay = true   # "Salta alla fine" porta dritti al finale, senza ralenti
	if state == State.COUNTDOWN:
		state = State.RUNNING
		gun_fired.emit()
	if state == State.RUNNING:
		if is_field(event_kind):
			while field_idx < field_queue.size():
				_commit_field_step(field_queue[field_idx])
				field_idx += 1
			_sort_field_order()
			for r: RunnerData in runners:
				r.finished = true
			active_jumper = live_order[0] if not live_order.is_empty() else null
			jumper_anim = &"Idle"
			if event_kind == "Getto del Peso":
				shot_plan = null
				shot_pose = null
				shot_visible = false
				shot_phase = ShotPutMotion.Phase.EXIT
				jumper_pos = _shot_wait_position()
				jumper_yaw = PI
			field_caption = "CLASSIFICA FINALE"
			field_value_text = "%.2f m" % live_order[0].best_mark if not live_order.is_empty() else ""
			field_landed_foul = false
			_announced = true
			state = State.FINISHED
			race_finished.emit(_sorted_by_place())
			return
		race_time = _last_finish_time + AFTER_FINISH_SECONDS
		clock = gun_at + race_time


## Posizione ai blocchi prima dello sparo: 0 = "pronti" (ginocchio a terra), 1 = "set" (bacino alto).
## "Pronti" fino a SET_CALL_AT secondi prima dello sparo, poi sale in SET_RISE_TIME e resta fermo fino al via.
func set_amount() -> float:
	if state == State.LOADED or state == State.IDLE:
		return 0.0
	if state == State.COUNTDOWN:
		return clampf((clock - (gun_at - SET_CALL_AT)) / SET_RISE_TIME, 0.0, 1.0)
	return 1.0


func leader_distance() -> float:
	return live_order[0].distance if not live_order.is_empty() else 0.0


## Quanto indugiare sulla finish-cam prima di tagliare sul carrello/runout: il distacco 1°-2° e'
## gia' noto (il modello ha calcolato il risultato prima della messa in scena), quindi la regia
## puo' decidere in anticipo invece di reagire a un arrivo che non vede ancora. Soglie allineate a
## `Track3DWidget._finish_hold` in race_3d.py.
func finish_hold() -> float:
	if finish_margin < 0.12:
		return 1.7
	if finish_margin < 0.4:
		return 1.0
	return 0.55


func _process(delta: float) -> void:
	if state == State.REPLAY:
		_process_replay(delta)
		return
	if state != State.COUNTDOWN and state != State.RUNNING:
		return
	if state == State.COUNTDOWN:
		clock += delta * time_scale
		if clock >= gun_at:
			state = State.RUNNING
			gun_fired.emit()
	else:
		race_time += delta * time_scale
		clock = gun_at + race_time
	if is_field(event_kind):
		if state == State.RUNNING:
			_process_field(delta * time_scale)
		return
	_update_runners()
	_update_order()
	display_time = minf(race_time, _winner_time) if _finished_count > 0 else race_time
	if state == State.RUNNING and race_time >= _last_finish_time + AFTER_FINISH_SECONDS:
		if replay_enabled and not _skip_replay:
			_begin_replay()
		else:
			state = State.FINISHED


## Posizione e velocita' di ogni corridore a `race_time` (funzione pura del tempo: si puo' anche riavvolgere).
func _apply_motion() -> void:
	for r: RunnerData in runners:
		var s: Vector2
		if r.dnf:
			s = RaceMotion.state_at_dnf(race_time, r.reaction_time, r.final_time, event_kind)
		else:
			s = RaceMotion.state_at(race_time, r.reaction_time, r.final_time, event_kind)
		r.distance = s.x
		r.speed = s.y


func _update_runners() -> void:
	_apply_motion()
	for r: RunnerData in runners:
		if not r.dnf and not r.finished and race_time >= r.final_time:
			r.finished = true
			_finished_count += 1
			runner_finished.emit(r)
	if not _announced and _finished_count == _finisher_count:
		_announced = true
		race_finished.emit(_sorted_by_place())


## Velocita' di riproduzione effettiva: quella scelta dall'utente (1x-8x), oppure REPLAY_SPEED nel ralenti.
## Anche le animazioni dei corridori la usano, altrimenti le gambe andrebbero a ritmo pieno al rallentatore.
func play_speed() -> float:
	return REPLAY_SPEED if state == State.REPLAY else time_scale


func _begin_replay() -> void:
	state = State.REPLAY
	_replay_start = maxf(_winner_time - REPLAY_LOOKBACK, 0.0)
	_replay_end = _winner_time + REPLAY_AFTER
	race_time = _replay_start
	clock = gun_at + race_time
	_update_replay_frame()


func _process_replay(delta: float) -> void:
	race_time += delta * REPLAY_SPEED
	clock = gun_at + race_time
	if race_time >= _replay_end:
		_end_replay()
		return
	_update_replay_frame()


## Durante il ralenti `finished` e' solo un riflesso del tempo riavvolto: nessun segnale, nessun contatore.
func _update_replay_frame() -> void:
	_apply_motion()
	for r: RunnerData in runners:
		r.finished = (not r.dnf) and race_time >= r.final_time
	_update_order()
	display_time = minf(race_time, _winner_time) if live_order[0].finished else race_time


## Fine del ralenti (naturale o con "Salta alla fine"): si ripristina lo stato definitivo della gara.
func _end_replay() -> void:
	race_time = _last_finish_time + AFTER_FINISH_SECONDS
	clock = gun_at + race_time
	_apply_motion()
	for r: RunnerData in runners:
		r.finished = not r.dnf
	_update_order()
	display_time = _winner_time
	state = State.FINISHED


## Classifica live: chi ha gia' tagliato il traguardo per ordine di arrivo, poi gli altri per distanza.
func _update_order() -> void:
	live_order.sort_custom(func(a: RunnerData, b: RunnerData) -> bool:
		if a.finished != b.finished:
			return a.finished
		if a.finished:
			return a.place < b.place
		return a.distance > b.distance)


## Assegna l'ordine d'arrivo: tempo minore nelle corse, misura maggiore nei concorsi. I ritirati vengono dopo.
func _assign_places() -> void:
	var ordered: Array[RunnerData] = runners.duplicate()
	var higher_wins: bool = is_field(event_kind)
	ordered.sort_custom(func(a: RunnerData, b: RunnerData) -> bool:
		if a.dnf != b.dnf:
			return b.dnf
		if is_equal_approx(a.final_time, b.final_time):
			return a.lane < b.lane
		return a.final_time > b.final_time if higher_wins else a.final_time < b.final_time)
	for i in range(ordered.size()):
		ordered[i].place = i + 1


func _init_field_queue(race_id: int) -> void:
	var by_lane: Dictionary = DatabaseManager.get_field_attempts(race_id)
	for r: RunnerData in runners:
		if by_lane.has(r.lane) and not (by_lane[r.lane] as Array).is_empty():
			r.attempts = by_lane[r.lane]
		elif not r.dnf:
			r.attempts = [
				{"round": 1, "mark": snappedf(r.final_time * 0.96, 0.01), "foul": false},
				{"round": 2, "mark": snappedf(r.final_time * 0.98, 0.01), "foul": false},
				{"round": 3, "mark": r.final_time, "foul": false},
				{"round": 4, "mark": snappedf(r.final_time * 0.97, 0.01), "foul": false},
				{"round": 5, "mark": snappedf(r.final_time * 0.985, 0.01), "foul": false},
				{"round": 6, "mark": snappedf(r.final_time * 0.975, 0.01), "foul": false},
			]
	field_rounds = 0
	for r: RunnerData in runners:
		for att: Dictionary in r.attempts:
			field_rounds = maxi(field_rounds, int(att.get("round", 0)))
	if field_rounds == 0:
		field_rounds = FIELD_ROUNDS_DEFAULT
	for rnd in range(1, field_rounds + 1):
		for r: RunnerData in runners:
			if r.dnf:
				continue
			for att: Dictionary in r.attempts:
				if int(att.get("round", 0)) == rnd:
					var anim_jump: bool = r.is_player or event_kind == "Getto del Peso"   # peso: si vedono TUTTI i lanci
					var step: Dictionary = {
						"runner": r,
						"round": rnd,
						"mark": float(att.get("mark", 0.0)),
						"foul": bool(att.get("foul", false)),
						"animate": anim_jump,
						"dur": 4.2 if anim_jump else 0.35,
					}
					if event_kind == "Getto del Peso":
						# Piano del tentativo (rilascio, velocita', volo): decide solo la geometria, la misura e' quella del DB.
						var plan: ShotPutMotion.Plan = ShotPutMotion.make_plan(
							float(step["mark"]), bool(step["foul"]), RunnerData.visual_height(r.athlete_name, r.gender),
							r.gender == "F", ShotPutMotion.landing_angle(r.athlete_name, rnd), not anim_jump)
						step["plan"] = plan
						step["dur"] = plan.duration
					field_queue.append(step)
	if not field_queue.is_empty():
		active_jumper = field_queue[0]["runner"]
		field_caption = "PROVA 1/%d · %s" % [field_rounds, active_jumper.surname()]
		field_value_text = "IN PEDANA"


func _commit_field_step(step: Dictionary) -> void:
	var r: RunnerData = step["runner"]
	r.revealed_rounds = maxi(r.revealed_rounds, int(step["round"]))
	if not bool(step["foul"]):
		r.best_mark = maxf(r.best_mark, float(step["mark"]))


func _sort_field_order() -> void:
	live_order.sort_custom(func(a: RunnerData, b: RunnerData) -> bool:
		if a.dnf != b.dnf:
			return b.dnf
		if is_equal_approx(a.best_mark, b.best_mark):
			return a.lane < b.lane
		return a.best_mark > b.best_mark)


func _process_field(dt: float) -> void:
	if field_idx >= field_queue.size():
		if state == State.RUNNING:
			for r: RunnerData in runners:
				r.finished = true
			_sort_field_order()
			if not _announced:
				_announced = true
				race_finished.emit(_sorted_by_place())
			state = State.FINISHED
		return
	var step: Dictionary = field_queue[field_idx]
	var r: RunnerData = step["runner"]
	var rnd: int = int(step["round"])
	var mark: float = float(step["mark"])
	var foul: bool = bool(step["foul"])
	var dur: float = float(step["dur"])
	active_jumper = r
	field_caption = "PROVA %d/%d · %s" % [rnd, field_rounds, r.surname()]

	if field_step_t == 0.0:
		field_landed_foul = false
		if bool(step["animate"]):
			field_landed_mark = -100.0
		shot_visible = false
	field_step_t += dt

	if event_kind == "Getto del Peso":
		_update_shot(step)
	elif bool(step["animate"]):
		var t: float = field_step_t
		var run_end: float = 2.15
		var fly_end: float = 2.95
		jumper_yaw = 0.0
		if t < run_end:
			var u: float = clampf(t / run_end, 0.0, 1.0)
			var start_x: float = -36.0
			var board_x: float = -9.72 if foul else -10.0
			var x: float = lerpf(start_x, board_x, u * u * 0.35 + u * 0.65)
			jumper_pos = Vector3(x, 0.0, -14.0)
			jumper_anim = &"Sprint"
			jumper_speed_scale = lerpf(0.75, 1.35, u)
			field_value_text = "RINCORSA"
		elif t < fly_end:
			var s: float = clampf((t - run_end) / (fly_end - run_end), 0.0, 1.0)
			var takeoff_x: float = -9.72 if foul else -10.0
			var x: float = takeoff_x + mark * s
			var apex: float = 0.95 + 0.08 * mark
			var y: float = 4.0 * apex * s * (1.0 - s)
			jumper_pos = Vector3(x, y, -14.0)
			jumper_anim = &"Jump_Start" if s < 0.25 else (&"Jump" if s < 0.85 else &"Jump_Land")
			jumper_speed_scale = 1.0
			field_value_text = "IN VOLO"
		else:
			jumper_pos = Vector3((-9.72 if foul else -10.0) + mark, 0.0, -14.0)
			jumper_anim = &"Jump_Land" if t < fly_end + 0.35 else &"Idle"
			jumper_speed_scale = 1.0
			_commit_field_step(step)
			_sort_field_order()
			field_landed_mark = (-9.72 if foul else -10.0) + mark
			field_landed_foul = foul
			field_value_text = "NULLO" if foul else "%.2f m" % mark
	else:
		jumper_yaw = 0.0
		jumper_pos = Vector3(-10.0 + mark, 0.0, -14.0)
		field_landed_mark = -10.0 + mark
		jumper_anim = &"Idle"
		jumper_speed_scale = 1.0
		_commit_field_step(step)
		_sort_field_order()
		field_landed_foul = foul
		field_value_text = "NULLO" if foul else "%.2f m" % mark

	if field_step_t >= dur:
		_commit_field_step(step)
		_sort_field_order()
		field_step_t = 0.0
		field_idx += 1


## Dove sta l'atleta quando non lancia (tentativi non animati e fine gara): dietro la pedana, di spalle al settore.
func _shot_wait_position() -> Vector3:
	return ShotPutMotion.CENTER + Vector3(-2.2, 0.0, 0.5)


## Un passo del getto del peso: il tempo del tentativo decide fase, posa dell'atleta e peso (funzioni pure di
## ShotPutMotion). Il peso atterra alla misura del DB per costruzione; qui si aggiornano solo lo stato e i testi.
func _update_shot(step: Dictionary) -> void:
	var plan: ShotPutMotion.Plan = step["plan"]
	var t: float = field_step_t
	shot_plan = plan
	shot_t = t
	shot_phase = ShotPutMotion.phase_at(plan, t)
	var ball: Dictionary = ShotPutMotion.ball_at(plan, t)
	shot_visible = bool(ball["visible"])
	shot_pos = ball["pos"]
	if plan.instant:
		shot_pose = null
		jumper_pos = _shot_wait_position()
		jumper_yaw = PI
		jumper_anim = &"Idle"
		jumper_speed_scale = 1.0
	else:
		shot_pose = ShotPutMotion.pose_at(plan, t)
		jumper_pos = shot_pose.root
		jumper_yaw = shot_pose.yaw
	if bool(ball["landed"]):
		_commit_field_step(step)
		_sort_field_order()
		field_landed_mark = plan.landing.x
		field_landed_foul = plan.foul
		field_value_text = "NULLO" if plan.foul else "%.2f m" % plan.mark
	elif t >= ShotPutMotion.T_REL:
		field_value_text = "IN VOLO"
	else:
		field_value_text = "IN PEDANA"


func _sorted_by_place() -> Array[RunnerData]:
	var ordered: Array[RunnerData] = runners.duplicate()
	ordered.sort_custom(func(a: RunnerData, b: RunnerData) -> bool: return a.place < b.place)
	return ordered


static func format_time(seconds: float) -> String:
	if seconds >= 60.0:
		var mins: int = int(seconds / 60.0)
		var rem: float = seconds - float(mins) * 60.0
		return "%d:%05.2f" % [mins, rem]
	return "%.2f" % seconds
