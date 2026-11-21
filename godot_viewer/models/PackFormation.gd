class_name PackFormation
extends RefCounted
## Formazione del gruppo nelle gare con rientro alla corda (800m, 1500m): posizione laterale di ogni corridore in ogni istante.
##
## E' la trascrizione GDScript di `models/pack_formation.py` (il RIFERIMENTO, con i test): stesse costanti, stesso algoritmo, chiavi di
## ordinamento totali (l'indice e' l'ultimo criterio) cosi' Python e Godot danno lo stesso ordine. Se cambi qualcosa la', cambialo anche qui
## (tests/verify_pack.gd confronta valori fissi calcolati da Python).
## SOLO MESSA IN SCENA: non cambia tempi, ordine o misure. E' una funzione pura del tempo di gara (il ralenti riavvolge e rilegge); l'isteresi
## si calcola a passi dalla partenza e si tiene in cache (solo un'ottimizzazione).

const SLOT_W: float = 0.95
const MAX_SLOT: int = 7
const GAP_AHEAD: float = 1.6
const GAP_BEHIND: float = 3.0
const STEP: float = 0.2
const WINDOW_STEPS: int = 10
const SEP_LAT: float = 0.75
const SEP_ALONG: float = 2.4
const SEP_FULL: float = 0.5
const SEP_PASSES: int = 3
const OUTER_LAT: float = 7.6
const EXIT_STEP: float = 0.9
const EXIT_MIN: float = 0.9
const PUSH_HALF: int = 3
const AVG_HALF: int = 3
const LEAVE_SECONDS: float = 5.0
## (inizio, fine) del rientro alla corda in metri dalla partenza. 800m: fine della prima curva = PI * R1 = 115,6 m.
const BREAK_WINDOWS: Dictionary = {"800m": Vector2(115.6, 145.0), "1500m": Vector2(10.0, 90.0)}

var kind: String = ""
var n: int = 0
var start_lats: PackedFloat64Array = PackedFloat64Array()
var dist_fn: Callable            # (corridore: int, t: float) -> metri dalla sua partenza
var stops: PackedFloat64Array = PackedFloat64Array()   # istante di arresto di un ritirato, INF = corre fino in fondo
var _hist: Array = []            # Array[PackedInt32Array]: file a ogni passo
var _phys: Array = []            # Array[PackedFloat64Array]: posizione laterale fisica a ogni passo
var _push: Array = []            # Array[PackedFloat64Array]: spinta di distanza minima richiesta a ogni passo
var _lane_rank: PackedInt32Array = PackedInt32Array()
var _last_present: PackedInt32Array = PackedInt32Array()   # ultimo passo in cui il corridore e' presente
var _exit_order: PackedInt32Array = PackedInt32Array()      # ordine di arresto (0 = il primo), -1 = non si ferma
var exit_lats: PackedFloat64Array = PackedFloat64Array()   # dove si ferma ognuno di quelli che si fermano


static func applies_to(event_kind: String) -> bool:
	return BREAK_WINDOWS.has(event_kind)


static func _smooth(a: float, b: float, x: float) -> float:
	if b <= a:
		return 1.0 if x >= a else 0.0
	var t: float = clampf((x - a) / (b - a), 0.0, 1.0)
	return t * t * (3.0 - 2.0 * t)


func _init(p_kind: String, p_start_lats: PackedFloat64Array, p_dist_fn: Callable, p_stops: PackedFloat64Array = PackedFloat64Array()) -> void:
	kind = p_kind
	start_lats = p_start_lats
	n = p_start_lats.size()
	dist_fn = p_dist_fn
	if p_stops.size() == n:
		stops = p_stops
	else:
		stops = PackedFloat64Array()
		stops.resize(n)
		stops.fill(INF)
	var order: Array = range(n)
	order.sort_custom(func(a: int, b: int) -> bool:
		if start_lats[a] != start_lats[b]:
			return start_lats[a] < start_lats[b]
		return a < b)
	_lane_rank.resize(n)
	for rank in range(n):
		_lane_rank[order[rank]] = rank
	_last_present.resize(n)
	for i in range(n):
		_last_present[i] = int(ceil(stops[i] / STEP)) - 1 if stops[i] < INF else 1000000000
	# chi si ferma (ritirato, oppure arrivato che ha tagliato il traguardo) va verso l'esterno, ognuno in una fila diversa: il primo a fermarsi e' il piu' esterno
	var stoppers: Array = []
	for i in range(n):
		if stops[i] < INF:
			stoppers.append(i)
	stoppers.sort_custom(func(a: int, b: int) -> bool:
		if stops[a] != stops[b]:
			return stops[a] < stops[b]
		return a < b)
	_exit_order.resize(n)
	_exit_order.fill(-1)
	exit_lats = PackedFloat64Array()
	exit_lats.resize(n)
	exit_lats.fill(OUTER_LAT)
	for k in range(stoppers.size()):
		_exit_order[stoppers[k]] = k
		exit_lats[stoppers[k]] = maxf(EXIT_MIN, OUTER_LAT - EXIT_STEP * k)


## Le file (0 = corda) di ogni corridore presente al passo successivo. Ordine: posizione laterale fisica del passo prima (chi e' piu' dentro
## tiene il posto), poi piu' avanti, poi corsia interna, poi indice. Un assente (ritirato fermo): -1.
static func assign_slots(dists: PackedFloat64Array, prev_lats: PackedFloat64Array, p_start_lats: PackedFloat64Array, present: Array) -> PackedInt32Array:
	var count: int = dists.size()
	var order: Array = []
	for i in range(count):
		if present[i]:
			order.append(i)
	order.sort_custom(func(a: int, b: int) -> bool:
		if prev_lats[a] != prev_lats[b]:
			return prev_lats[a] < prev_lats[b]
		if dists[a] != dists[b]:
			return dists[a] > dists[b]
		if p_start_lats[a] != p_start_lats[b]:
			return p_start_lats[a] < p_start_lats[b]
		return a < b)
	var slots: PackedInt32Array = PackedInt32Array()
	slots.resize(count)
	slots.fill(-1)
	var placed: Array = []
	for i: int in order:
		var chosen: int = MAX_SLOT
		for s in range(MAX_SLOT + 1):
			var free: bool = true
			for k: int in placed:
				var delta: float = dists[k] - dists[i]
				if slots[k] == s and delta > -GAP_BEHIND and delta < GAP_AHEAD:
					free = false
					break
			if free:
				chosen = s
				break
		slots[i] = chosen
		placed.append(i)
	return slots


func _present(i: int, t: float) -> bool:
	return t < stops[i]


func _slots_at_step(k: int) -> PackedInt32Array:
	while _hist.size() <= k:
		var j: int = _hist.size()
		var t: float = j * STEP
		var dists: PackedFloat64Array = PackedFloat64Array()
		dists.resize(n)
		var present: Array = []
		for i in range(n):
			dists[i] = float(dist_fn.call(i, t))
			present.append(_present(i, t))
		var prev: PackedFloat64Array = start_lats if j == 0 else (_phys[j - 1] as PackedFloat64Array)
		_hist.append(assign_slots(dists, prev, start_lats, present))
		var phys: PackedFloat64Array = PackedFloat64Array()
		phys.resize(n)
		for i in range(n):
			phys[i] = _lat(i, t)  # usa le file fino a questo passo (la finestra guarda indietro)
		_phys.append(phys)
	return _hist[k]


func _averaged_slot_lat(i: int, step_pos: float) -> float:
	var k0: int = int(step_pos)
	var frac: float = step_pos - k0
	if frac <= 1e-12:
		return _avg_at(i, k0)
	return _avg_at(i, k0) * (1.0 - frac) + _avg_at(i, k0 + 1) * frac


func _avg_at(i: int, k: int) -> float:
	var total: float = 0.0
	for j in range(WINDOW_STEPS):
		var kk: int = mini(maxi(0, k - j), maxi(0, _last_present[i]))
		var s: int = (_slots_at_step(kk) as PackedInt32Array)[i]
		total += (s if s >= 0 else MAX_SLOT) * SLOT_W
	return total / WINDOW_STEPS


func _lat(i: int, t: float) -> float:
	var win: Vector2 = BREAK_WINDOWS[kind]
	var w: float = _smooth(win.x, win.y, float(dist_fn.call(i, t)))
	if w <= 0.0:
		return start_lats[i]  # prima della linea di rientro: nella propria corsia, esattamente
	var slot_lat: float = _averaged_slot_lat(i, t / STEP)
	return start_lats[i] + (slot_lat - start_lats[i]) * w


## Posizioni laterali prima della verifica di distanza minima: file mediate, rientro e uscita di chi si ferma.
func _base(t: float) -> PackedFloat64Array:
	var out: PackedFloat64Array = PackedFloat64Array()
	out.resize(n)
	for i in range(n):
		if t >= stops[i]:
			var at_stop: float = _lat(i, stops[i] - 1e-3)  # appena prima dell'arresto: ancora presente
			out[i] = at_stop + (exit_lats[i] - at_stop) * _smooth(0.0, LEAVE_SECONDS, t - stops[i])
		else:
			out[i] = _lat(i, t)
	return out


## Spinta di distanza minima richiesta al passo `k` (>= 0 per ognuno), in cache.
func _grid_push(k: int) -> PackedFloat64Array:
	while _push.size() <= k:
		var j: int = _push.size()
		var t: float = j * STEP
		var base: PackedFloat64Array = _base(t)
		var sep: PackedFloat64Array = _separate(base, t)
		var row: PackedFloat64Array = PackedFloat64Array()
		row.resize(n)
		for i in range(n):
			row[i] = sep[i] - base[i]
		_push.append(row)
	return _push[k]


## Spinta estesa nel tempo: il massimo della richiesta entro +-PUSH_HALF passi (ci si sposta PRIMA di incontrarsi e si resta spostati un attimo dopo).
func _grid_env(k: int) -> PackedFloat64Array:
	var out: PackedFloat64Array = PackedFloat64Array()
	out.resize(n)
	out.fill(0.0)
	for m in range(-PUSH_HALF, PUSH_HALF + 1):
		var row: PackedFloat64Array = _grid_push(maxi(0, k + m))
		for i in range(n):
			out[i] = maxf(out[i], row[i])
	return out


## Spinta addolcita: media dell'estesa entro +-AVG_HALF passi. Resta >= della richiesta nell'istante (l'estesa la copre per tutta la finestra).
func _grid_avg(k: int) -> PackedFloat64Array:
	var out: PackedFloat64Array = PackedFloat64Array()
	out.resize(n)
	out.fill(0.0)
	var count: float = float(2 * AVG_HALF + 1)
	for m in range(-AVG_HALF, AVG_HALF + 1):
		var row: PackedFloat64Array = _grid_env(maxi(0, k + m))
		for i in range(n):
			out[i] += row[i] / count
	return out


## Posizione laterale (m dalla corda, >= 0) di ogni corridore al tempo di gara `t`. Gare senza rientro: le corsie di partenza.
func lateral_offsets(t: float) -> PackedFloat64Array:
	if not applies_to(kind):
		return start_lats.duplicate()
	t = maxf(0.0, t)
	var base: PackedFloat64Array = _base(t)
	var pos: float = t / STEP
	var k0: int = int(pos)
	var frac: float = pos - k0
	var a0: PackedFloat64Array = _grid_avg(k0)
	var a1: PackedFloat64Array = a0 if frac <= 1e-12 else _grid_avg(k0 + 1)
	var out: PackedFloat64Array = PackedFloat64Array()
	out.resize(n)
	for i in range(n):
		out[i] = base[i] + (a0[i] if frac <= 1e-12 else a0[i] * (1.0 - frac) + a1[i] * frac)
	return out


## Chi ha la chiave piu' alta sta piu' fuori quando due si sfiorano: la corsia di partenza (statica: nessun salto) e, per chi si ferma, una chiave che passa
## gradualmente (in LEAVE_SECONDS) a quella dell'ordine d'uscita (il primo a fermarsi e' il piu' alto).
func _priority(i: int, t: float) -> float:
	var key: float = float(_lane_rank[i])
	if stops[i] < INF and t > stops[i]:
		var w: float = _smooth(0.0, LEAVE_SECONDS, t - stops[i])
		key = key * (1.0 - w) + (2.0 * float(n) - float(_exit_order[i])) * w
	return key


## Distanza minima fra due corridori a fianco. Chi ha la chiave di precedenza piu' alta si sposta fuori.
func _separate(lats: PackedFloat64Array, t: float) -> PackedFloat64Array:
	var d: PackedFloat64Array = PackedFloat64Array()
	d.resize(n)
	var keys: PackedFloat64Array = PackedFloat64Array()
	keys.resize(n)
	for i in range(n):
		d[i] = float(dist_fn.call(i, t))
		keys[i] = _priority(i, t)
	var out: PackedFloat64Array = lats.duplicate()
	for _pass in range(SEP_PASSES):
		for i in range(n):
			for j in range(i + 1, n):
				var along: float = absf(d[i] - d[j])
				if along >= SEP_ALONG:
					continue
				var i_inner: bool = keys[i] < keys[j] or (keys[i] == keys[j] and i < j)
				var inner: int = i if i_inner else j
				var outer: int = j if i_inner else i
				var need: float = SEP_LAT - (out[outer] - out[inner])
				if need > 0.0:
					out[outer] += need * (1.0 - _smooth(SEP_FULL, SEP_ALONG, along))
	return out
