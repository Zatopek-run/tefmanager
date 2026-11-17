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

enum State { IDLE, LOADED, COUNTDOWN, RUNNING, FINISHED }

const GUN_AT: float = 2.4          # secondi tra "via" al conto alla rovescia e lo sparo (default)
## Preparazione piu' lunga per i 100m, come nella diretta TV: apertura larga, lungo primo piano sui blocchi, sparo.
const GUN_AT_BY_KIND: Dictionary = {"100m": 9.0, "400m": 7.0, "1500m": 4.2}


static func uses_blocks(kind: String) -> bool:
	return kind == "100m" or kind == "400m"
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

var _finished_count: int = 0
var _finisher_count: int = 0       # corridori che arrivano al traguardo (esclusi i ritirati)
var _announced: bool = false
var _winner_time: float = 0.0
var _last_finish_time: float = 0.0


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
	if not RaceMotion.is_supported(kind):
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
	for r: RunnerData in runners:
		if not r.dnf:
			_finisher_count += 1
			_winner_time = minf(_winner_time, r.final_time)
			_last_finish_time = maxf(_last_finish_time, r.final_time)
		r.distance = 0.0
		r.speed = 0.0
		r.finished = false
	live_order = runners.duplicate()
	clock = 0.0
	race_time = 0.0
	display_time = 0.0
	_finished_count = 0
	_announced = false
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
	if state == State.COUNTDOWN:
		state = State.RUNNING
		gun_fired.emit()
	if state == State.RUNNING:
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


func _process(delta: float) -> void:
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
	_update_runners()
	_update_order()
	display_time = minf(race_time, _winner_time) if _finished_count > 0 else race_time
	if state == State.RUNNING and race_time >= _last_finish_time + AFTER_FINISH_SECONDS:
		state = State.FINISHED


func _update_runners() -> void:
	for r: RunnerData in runners:
		var s: Vector2 = RaceMotion.state_at_dnf(race_time, r.reaction_time, r.final_time, event_kind) if r.dnf 			else RaceMotion.state_at(race_time, r.reaction_time, r.final_time, event_kind)
		r.distance = s.x
		r.speed = s.y
		if not r.dnf and not r.finished and race_time >= r.final_time:
			r.finished = true
			_finished_count += 1
			runner_finished.emit(r)
	if not _announced and _finished_count == _finisher_count:
		_announced = true
		race_finished.emit(_sorted_by_place())


## Classifica live: chi ha gia' tagliato il traguardo per ordine di arrivo, poi gli altri per distanza.
func _update_order() -> void:
	live_order.sort_custom(func(a: RunnerData, b: RunnerData) -> bool:
		if a.finished != b.finished:
			return a.finished
		if a.finished:
			return a.place < b.place
		return a.distance > b.distance)


## Assegna l'ordine d'arrivo dal solo `final_time` (parita': corsia piu' bassa). I ritirati vengono dopo i classificati.
func _assign_places() -> void:
	var ordered: Array[RunnerData] = runners.duplicate()
	ordered.sort_custom(func(a: RunnerData, b: RunnerData) -> bool:
		if a.dnf != b.dnf:
			return b.dnf
		if is_equal_approx(a.final_time, b.final_time):
			return a.lane < b.lane
		return a.final_time < b.final_time)
	for i in range(ordered.size()):
		ordered[i].place = i + 1


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
