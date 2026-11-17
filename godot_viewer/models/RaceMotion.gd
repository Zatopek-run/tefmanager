class_name RaceMotion
extends RefCounted
## Modello di movimento dei 100m: funzioni pure, nessuno stato di scena.
##
## E' la trascrizione GDScript di `_velocity` / `curve_progress` di views/race_viewer.py:
## una curva di velocita' (forte accelerazione fino a ~60 m, poi leggero calo) viene
## integrata e normalizzata in modo che lo spazio percorso valga ESATTAMENTE 1 a u = 1.
## Per questo ogni corridore taglia il traguardo al suo `final_time`, qualunque sia la curva.

const RACE_DISTANCE: float = 100.0
const STEPS: int = 600
const RUNOUT_TAU: float = 1.1  # costante di tempo della decelerazione dopo il traguardo (s)
const DNF_STOP_DISTANCE: float = 42.0  # un ritirato smette di correre qui (come DNF_PROGRESS = 0,42 in Python)
const DNF_TAU: float = 0.7     # ...e rallenta con questa costante di tempo (s)

static var _table: PackedFloat64Array = PackedFloat64Array()


## Velocita' relativa (sempre > 0) al tempo normalizzato u in [0, 1].
static func _velocity(u: float) -> float:
	return (1.0 - exp(-u / 0.14)) * (1.0 - 0.07 * maxf(0.0, (u - 0.6) / 0.4)) + 0.02


## Tabella dello spazio normalizzato 0..1 a passi uniformi di tempo.
static func _get_table() -> PackedFloat64Array:
	if _table.is_empty():
		var cum: PackedFloat64Array = PackedFloat64Array([0.0])
		for i in range(1, STEPS + 1):
			var u0: float = float(i - 1) / STEPS
			var u1: float = float(i) / STEPS
			cum.append(cum[i - 1] + 0.5 * (_velocity(u0) + _velocity(u1)) / STEPS)
		var total: float = cum[STEPS]
		for i in range(cum.size()):
			cum[i] = cum[i] / total
		_table = cum
	return _table


## Frazione di percorso (0..1) al tempo normalizzato u. Monotona; 0 a u=0, 1 a u=1.
static func progress(u: float) -> float:
	var table: PackedFloat64Array = _get_table()
	var x: float = clampf(u, 0.0, 1.0) * STEPS
	var i: int = mini(STEPS - 1, int(x))
	return lerpf(table[i], table[i + 1], x - float(i))


## Derivata di progress() rispetto a u (spazio normalizzato per unita' di tempo normalizzato).
static func slope(u: float) -> float:
	var table: PackedFloat64Array = _get_table()
	var i: int = mini(STEPS - 1, int(clampf(u, 0.0, 1.0) * STEPS))
	return (table[i + 1] - table[i]) * STEPS


## Stato di un corridore al tempo di gara `race_t` (secondi dallo sparo).
## Ritorna Vector2(distanza_m, velocita_m_s).
## - prima di `reaction`: fermo ai blocchi
## - fino a `final_time`: corre sulla curva, arrivando a 100.0 m esatti a `final_time`
## - dopo: continua e rallenta (lancio oltre il traguardo)
static func state_at(race_t: float, reaction: float, final_time: float) -> Vector2:
	if race_t <= reaction:
		return Vector2.ZERO
	var run_duration: float = final_time - reaction
	if race_t < final_time:
		var u: float = (race_t - reaction) / run_duration
		return Vector2(RACE_DISTANCE * progress(u), RACE_DISTANCE * slope(u) / run_duration)
	var finish_speed: float = RACE_DISTANCE * slope(1.0) / run_duration
	var dt: float = race_t - final_time
	var decay: float = exp(-dt / RUNOUT_TAU)
	return Vector2(RACE_DISTANCE + finish_speed * RUNOUT_TAU * (1.0 - decay), finish_speed * decay)


## Tempo di gara (s dallo sparo) a cui un corridore ha percorso `distance` m, sulla stessa curva di state_at().
static func time_at_distance(distance: float, reaction: float, final_time: float) -> float:
	var target: float = clampf(distance / RACE_DISTANCE, 0.0, 1.0)
	var lo: float = 0.0
	var hi: float = 1.0
	for i in range(40):
		var mid: float = (lo + hi) * 0.5
		if progress(mid) < target:
			lo = mid
		else:
			hi = mid
	return reaction + hi * (final_time - reaction)


## Come state_at(), ma per un ritirato: corre sulla stessa curva fino a DNF_STOP_DISTANCE, poi rallenta e si ferma.
static func state_at_dnf(race_t: float, reaction: float, final_time: float) -> Vector2:
	var t_stop: float = time_at_distance(DNF_STOP_DISTANCE, reaction, final_time)
	if race_t < t_stop:
		return state_at(race_t, reaction, final_time)
	var at_stop: Vector2 = state_at(t_stop, reaction, final_time)
	var dt: float = race_t - t_stop
	var decay: float = exp(-dt / DNF_TAU)
	return Vector2(at_stop.x + at_stop.y * DNF_TAU * (1.0 - decay), at_stop.y * decay)
