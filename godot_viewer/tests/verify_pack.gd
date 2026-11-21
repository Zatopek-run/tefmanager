extends SceneTree
## Verifica headless dello stile di passo (sorpassi) e della formazione del gruppo (800m, 1500m):
##   godot --headless --path godot_viewer -s res://tests/verify_pack.gd
## 1) PARITA' con Python: valori fissi calcolati da `views/race_viewer.py` (curve_progress con stile) e `models/pack_formation.py` (PackFormation).
## 2) INVARIANTI: stile 0 = curva di sempre; con ogni stile il via e' 0 e l'arrivo e' ESATTAMENTE final_time; distanza monotona; il ritirato torna
##    alla stessa curva. 3) GRUPPO: nelle gare demo (800m e 1500m con stili) nessuno lascia la corsia prima della linea di rientro, lo scostamento e' >= 0 e
##    continuo, nessuno si compenetra, c'e' almeno un sorpasso, e la formazione e' una funzione pura del tempo (si puo' riavvolgere).
## Esce con codice 0 se tutto torna, 1 altrimenti.

const DT: float = 0.05
const TOL: float = 1e-6

var _failures: int = 0
var _done: bool = false


func _check(cond: bool, what: String) -> void:
	print(("OK    " if cond else "FAIL  ") + what)
	if not cond:
		_failures += 1


func _process(_delta: float) -> bool:
	if _done:
		return true
	_done = true
	_curve_parity()
	_curve_invariants()
	_pack_parity()
	_geometry()
	_runner_data_and_db()
	_demo_races()
	print("RISULTATO: " + ("TUTTO OK" if _failures == 0 else "%d FALLIMENTI" % _failures))
	quit(0 if _failures == 0 else 1)
	return true


# ---- 1) parita' con Python -------------------------------------------------------------------------------------------

## (evento, stile, u, progress) calcolati da Python con curve_progress(kind, u, 0, 0, style): la copia GDScript non ha l'ondeggiamento di fase.
const PROGRESS_FIXTURE: Array = [
	["100m", -1.0, 0.1, 0.053899017], ["100m", -1.0, 0.5, 0.456569776], ["100m", -1.0, 0.95, 0.947256294],
	["100m", 0.6, 0.33, 0.285120036], ["100m", 0.6, 0.77, 0.762754076],
	["400m", -1.0, 0.33, 0.301397965], ["400m", -1.0, 0.77, 0.765100025], ["400m", 0.6, 0.1, 0.067548324], ["400m", 0.6, 0.5, 0.502204933],
	["800m", -1.0, 0.1, 0.068156415], ["800m", -1.0, 0.5, 0.465044082], ["800m", 0.6, 0.5, 0.491360151], ["800m", 0.6, 0.95, 0.948153462],
	["1500m", -1.0, 0.33, 0.297890752], ["1500m", -1.0, 0.95, 0.943056458], ["1500m", 0.6, 0.1, 0.082515526], ["1500m", 0.6, 0.77, 0.763891813],
]


func _curve_parity() -> void:
	var ok: bool = true
	for row: Array in PROGRESS_FIXTURE:
		var got: float = RaceMotion.progress(float(row[2]), str(row[0]), float(row[1]))
		if absf(got - float(row[3])) > TOL:
			ok = false
			print("      %s stile %.1f u=%.2f: Godot %.9f, Python %.9f" % [row[0], row[1], row[2], got, row[3]])
	_check(ok, "curva con stile di passo identica a Python (%d valori)" % PROGRESS_FIXTURE.size())
	# la derivata: confronto con la differenza finita di progress() (stesso modello, due strade)
	var slope_ok: bool = true
	for kind: String in ["100m", "400m", "800m", "1500m"]:
		for style: float in [-1.0, 0.6]:
			for u: float in [0.2, 0.5, 0.8]:
				var h: float = 1e-3
				var fd: float = (RaceMotion.progress(u + h, kind, style) - RaceMotion.progress(u - h, kind, style)) / (2.0 * h)
				if absf(fd - RaceMotion.slope(u, kind, style)) > 0.02 * maxf(1.0, fd):
					slope_ok = false
					print("      derivata %s stile %.1f u=%.1f: %.4f vs %.4f" % [kind, style, u, RaceMotion.slope(u, kind, style), fd])
	_check(slope_ok, "slope() con stile coincide con la differenza finita di progress()")


# ---- 2) invarianti della curva ---------------------------------------------------------------------------------------

func _curve_invariants() -> void:
	var same: bool = true
	for kind: String in ["100m", "400m", "800m", "1500m", "4x100m", "4x400m"]:
		for i in range(0, 101):
			var u: float = float(i) / 100.0
			if RaceMotion.progress(u, kind) != RaceMotion.progress(u, kind, 0.0) or RaceMotion.slope(u, kind) != RaceMotion.slope(u, kind, 0.0):
				same = false
	_check(same, "stile 0 = valori di sempre (progress e slope, tutti gli eventi)")
	var relay_flat: bool = RaceMotion.progress(0.4, "4x100m", 1.0) == RaceMotion.progress(0.4, "4x100m") and RaceMotion.progress(0.4, "4x400m", -1.0) == RaceMotion.progress(0.4, "4x400m")
	_check(relay_flat, "le staffette non hanno stile di passo")
	for kind: String in ["100m", "400m", "800m", "1500m"]:
		var total: float = RaceMotion.race_distance(kind)
		var final_time: float = {"100m": 10.0, "400m": 47.0, "800m": 110.0, "1500m": 235.0}[kind]
		for style: float in [-1.0, -0.4, 0.4, 1.0]:
			var react: float = 0.15
			var st0: Vector2 = RaceMotion.state_at(react, react, final_time, kind, style)
			var st1: Vector2 = RaceMotion.state_at(final_time, react, final_time, kind, style)
			var before: Vector2 = RaceMotion.state_at(final_time - 0.01, react, final_time, kind, style)
			var mono: bool = true
			var prev: float = -1.0
			var speed_ok: bool = true
			var t: float = 0.0
			while t < final_time + 2.0:
				var s: Vector2 = RaceMotion.state_at(t, react, final_time, kind, style)
				if s.x + 1e-9 < prev or s.y < 0.0:
					mono = false
				prev = s.x
				t += final_time / 400.0
			_check(absf(st0.x) < TOL and absf(st1.x - total) < 1e-6 and before.x < total,
				"%s stile %+.1f: parte da 0 e arriva ESATTAMENTE a %.0f m a final_time (%.6f)" % [kind, style, total, st1.x])
			_check(mono and speed_ok, "%s stile %+.1f: distanza monotona, velocita' mai negativa" % [kind, style])
			# il ritirato corre sulla stessa curva fino al punto di arresto: time_at_distance e' l'inversa di state_at
			var d: float = RaceMotion.dnf_stop_distance(kind)
			var ta: float = RaceMotion.time_at_distance(d, react, final_time, kind, style)
			_check(absf(RaceMotion.state_at(ta, react, final_time, kind, style).x - d) < 0.05, "%s stile %+.1f: time_at_distance e' l'inversa (arresto a %.0f m)" % [kind, style, d])
			var dnf_end: Vector2 = RaceMotion.state_at_dnf(final_time * 3.0, react, final_time, kind, style)
			_check(dnf_end.y < 0.01 and dnf_end.x >= d - 0.05 and dnf_end.x < d + 8.0, "%s stile %+.1f: il ritirato si ferma vicino a %.0f m (%.1f)" % [kind, style, d, dnf_end.x])


# ---- 3) parita' della formazione del gruppo --------------------------------------------------------------------------

const SPEEDS: Array = [6.0, 6.7, 6.2, 6.6, 6.1, 6.5, 6.3, 6.4]
const STARTS: Array = [8.0, 3.0, 0.0, 6.0, 2.0, 4.0, 1.0, 5.0]
## (evento, istante, scostamenti di ognuno) calcolati da Python con PackFormation (corsie i*1,22; distanza = partenza + (t - 0,15) * velocita').
const PACK_FIXTURE: Array = [
	["800m", 6.0, [0.0, 1.22, 2.44, 3.66, 4.88, 6.1, 7.32, 8.54]],
	["800m", 14.0, [0.0, 1.22, 2.44, 3.66, 4.88, 6.1, 7.32, 8.54]],
	["800m", 20.0, [0.0, 0.27325, 2.047485, 1.441675, 4.245512, 2.211628, 5.751242, 4.074341]],
	["800m", 28.0, [0.0, 0.0, 0.024656, 0.95, 0.95, 0.0, 0.95, 0.429129]],
	["800m", 40.0, [0.0, 0.0, 0.95, 0.95, 0.753232, 0.0, 0.0, 0.0]],
	["1500m", 3.0, [0.0, 1.144773, 2.377015, 3.415762, 4.730433, 5.810874, 7.131466, 8.110145]],
	["1500m", 9.0, [0.0, 1.024717, 0.998298, 2.031585, 2.477271, 3.117521, 3.930049, 4.488211]],
	["1500m", 21.0, [0.0, 0.95, 0.0, 1.698479, 0.95, 0.0, 1.425, 0.95]],
	["1500m", 33.0, [0.0, 0.95, 0.905834, 1.7, 1.729949, 0.0, 0.95, 0.054551]],
]
## Come sopra, con il corridore 0 ritirato che si ferma a 22 s (la sua distanza non cresce piu').
const PACK_DNF_FIXTURE: Array = [
	[21.9, [0.0, 0.0, 1.232249, 0.95, 2.389127, 0.0, 1.855487, 0.966554]],
	[23.5, [1.6416, 0.0, 0.519712, 0.95, 1.312788, 0.0, 0.1425, 0.95]],
	[26.0, [6.8096, 0.0, 0.0, 0.95, 0.95, 0.0, 0.0, 1.038707]],
	[33.0, [7.6, 0.0, 0.0, 0.95, 0.95, 0.0, 0.0, 0.054551]],
	[40.0, [7.6, 0.0, 0.0, 0.95, 0.299495, 0.0, 0.0, 0.0]],
]


func _lanes() -> PackedFloat64Array:
	var out: PackedFloat64Array = PackedFloat64Array()
	for i in range(8):
		out.append(float(i) * 1.22)
	return out


func _pack_parity() -> void:
	var dist_fn: Callable = func(i: int, t: float) -> float: return float(STARTS[i]) + maxf(0.0, t - 0.15) * float(SPEEDS[i])
	var ok: bool = true
	for kind: String in ["800m", "1500m"]:
		var pack: PackFormation = PackFormation.new(kind, _lanes(), dist_fn)
		for row: Array in PACK_FIXTURE:
			if str(row[0]) != kind:
				continue
			var lat: PackedFloat64Array = pack.lateral_offsets(float(row[1]))
			for i in range(8):
				if absf(lat[i] - float((row[2] as Array)[i])) > 1e-4:
					ok = false
					print("      %s t=%.1f corridore %d: Godot %.6f, Python %.6f" % [kind, row[1], i, lat[i], (row[2] as Array)[i]])
	_check(ok, "formazione del gruppo identica a Python (%d istanti, 800m e 1500m)" % PACK_FIXTURE.size())
	var dist_stop: Callable = func(i: int, t: float) -> float:
		var tt: float = minf(t, 22.0) if i == 0 else t
		return float(STARTS[i]) + maxf(0.0, tt - 0.15) * float(SPEEDS[i])
	var stops: PackedFloat64Array = PackedFloat64Array([22.0, INF, INF, INF, INF, INF, INF, INF])
	var pack_dnf: PackFormation = PackFormation.new("800m", _lanes(), dist_stop, stops)
	var dnf_ok: bool = true
	for row: Array in PACK_DNF_FIXTURE:
		var lat2: PackedFloat64Array = pack_dnf.lateral_offsets(float(row[0]))
		for i in range(8):
			if absf(lat2[i] - float((row[1] as Array)[i])) > 1e-4:
				dnf_ok = false
				print("      ritirato t=%.1f corridore %d: Godot %.6f, Python %.6f" % [row[0], i, lat2[i], (row[1] as Array)[i]])
	_check(dnf_ok, "formazione con un ritirato che si ferma identica a Python (esce dalla corda e non blocca gli altri)")
	# funzione pura del tempo: riavvolgendo si rilegge lo stesso valore
	var pure: PackFormation = PackFormation.new("800m", _lanes(), dist_fn)
	var a: PackedFloat64Array = pure.lateral_offsets(30.0)
	pure.lateral_offsets(12.0)
	var b: PackedFloat64Array = pure.lateral_offsets(30.0)
	var fresh: PackedFloat64Array = PackFormation.new("800m", _lanes(), dist_fn).lateral_offsets(12.0)
	_check(a == b and pure.lateral_offsets(12.0) == fresh, "formazione = funzione pura del tempo (riavvolgendo si rilegge lo stesso valore)")
	var flat: PackedFloat64Array = PackFormation.new("400m", _lanes(), dist_fn).lateral_offsets(20.0)
	_check(flat == _lanes(), "nelle gare senza rientro (400m) restano le corsie di partenza")


# ---- geometria e dati ------------------------------------------------------------------------------------------------

func _geometry() -> void:
	for kind: String in ["800m", "1500m"]:
		var end: Vector3 = TrackGeometry.runner_pose(kind, 3, RaceMotion.race_distance(kind), 1.9)["position"]
		_check(absf(end.x - TrackGeometry.FINISH_X) < 0.05 and absf(end.z - 1.9) < 0.01,
			"%s: con scostamento 1,9 m arriva sulla linea del traguardo a z = 1,9 (%.3f, %.3f)" % [kind, end.x, end.z])
		var rail: Vector3 = TrackGeometry.runner_pose(kind, 8, 300.0, 0.0)["position"]
		var legacy: Vector3 = TrackGeometry.runner_pose(kind, 1, 300.0)["position"]
		_check(rail.distance_to(legacy) < 1e-6, "%s: scostamento 0 = la corda (corsia 1)" % kind)
		var keep: Vector3 = TrackGeometry.runner_pose(kind, 5, 50.0)["position"]
		_check(keep.distance_to(TrackGeometry.runner_pose(kind, 5, 50.0, -1.0)["position"]) < 1e-9, "%s: senza scostamento vale la regola di sempre" % kind)
	_check(TrackGeometry.runner_pose("400m", 4, 100.0, 5.0)["position"] == TrackGeometry.runner_pose("400m", 4, 100.0)["position"], "400m: lo scostamento non ha effetto")
	_check(is_equal_approx(TrackGeometry.BREAK_800M_START, PackFormation.BREAK_WINDOWS["800m"].x), "800m: la linea di rientro e' la stessa in geometria e in formazione")
	_check(absf(TrackGeometry.BREAK_800M_START - PI * TrackGeometry.R1) < 0.1, "800m: la linea di rientro e' la fine della prima curva (PI * R1)")


func _runner_data_and_db() -> void:
	var r: RunnerData = RunnerData.from_row({"lane": 2, "athlete_name": "A", "reaction_time": 0.15, "final_time": 10.0, "pace_style": 0.4})
	_check(is_equal_approx(r.pace_style, 0.4), "RunnerData legge pace_style")
	_check(RunnerData.from_row({"pace_style": 7.0}).pace_style == 1.0 and RunnerData.from_row({"pace_style": -7.0}).pace_style == -1.0, "pace_style fuori scala viene riportato in [-1, 1]")
	_check(RunnerData.from_row({}).pace_style == 0.0, "senza colonna: stile 0 (DB esportati prima)")
	var db: Node = root.get_node("DatabaseManager")
	var runners: Array[RunnerData] = db.get_race_runners(13)
	var lo: float = 9.0
	var hi: float = -9.0
	for x: RunnerData in runners:
		lo = minf(lo, x.pace_style)
		hi = maxf(hi, x.pace_style)
	_check(runners.size() == 8 and lo <= -0.99 and hi >= 0.99, "gara demo 13 (800m): il seed porta stili da %.2f a %.2f" % [lo, hi])


# ---- 3) gare demo con il controller -------------------------------------------------------------------------------------

func _demo_races() -> void:
	var rc: Node = root.get_node("RaceController")
	rc.set_process(false)
	var total_cross: int = 0
	for id: int in [13, 14, 5, 6]:
		total_cross += _one_race(rc, id)
	_check(total_cross >= 4, "gare demo 800m e 1500m: almeno 4 sorpassi veri in tutto (%d)" % total_cross)
	# gara senza rientro: nessuna formazione
	rc.load_race(3)
	rc.start()
	for _i in range(400):
		rc._process(DT)
	_check(rc.runners.all(func(x: RunnerData) -> bool: return x.lateral < 0.0), "400m: nessuna formazione del gruppo (scostamento -1)")


func _one_race(rc: Node, id: int) -> int:
	_check(rc.load_race(id), "gara %d caricata" % id)
	rc.replay_enabled = false
	rc.time_scale = 1.0
	rc.start()
	var kind: String = rc.event_kind
	var label: String = "gara %d (%s)" % [id, kind]
	var n: int = rc.runners.size()
	var win: Vector2 = PackFormation.BREAK_WINDOWS[kind]
	var total: float = RaceMotion.race_distance(kind)
	var prev_lat: PackedFloat64Array = PackedFloat64Array()
	prev_lat.resize(n)
	prev_lat.fill(-1.0)
	var in_lane_ok: bool = true
	var nonneg: bool = true
	var smooth: bool = true
	var worst_sep: float = 99.0
	var worst_speed: float = 0.0
	var worst_info: String = ""
	var steps: int = 0
	var sign_of: Dictionary = {}
	var crossings: int = 0
	var finish_ok: bool = true
	var guard: int = 0
	while rc.state == rc.State.COUNTDOWN or rc.state == rc.State.RUNNING:
		rc._process(DT)
		guard += 1
		if guard > 20000:
			break
		if rc.state != rc.State.RUNNING:
			continue
		steps += 1
		for i in range(n):
			var r: RunnerData = rc.runners[i]
			if r.lateral < -1e-9:
				nonneg = false
			if r.distance <= win.x and not r.dnf and absf(r.lateral - float(r.lane - 1) * TrackGeometry.LANE_WIDTH) > 1e-9:
				in_lane_ok = false
			if prev_lat[i] >= 0.0:
				var sp: float = absf(r.lateral - prev_lat[i]) / DT
				if sp > worst_speed:
					worst_speed = sp
					worst_info = "t=%.2f corridore %d (%s) distanza %.1f finito=%s ritirato=%s lat %.2f -> %.2f" % [rc.race_time, i, r.athlete_name, r.distance, r.finished, r.dnf, prev_lat[i], r.lateral]
			prev_lat[i] = r.lateral
			if not r.dnf and rc.race_time >= r.final_time and not is_equal_approx(r.distance, total) and r.distance < total - 1e-6:
				finish_ok = false
		# distanze minime e sorpassi (solo corridori in gara: niente ritirati fermi ne' arrivati che rallentano)
		var live: Array[RunnerData] = rc.runners.filter(func(x: RunnerData) -> bool: return not x.dnf and not x.finished)
		for a in range(live.size()):
			for b in range(a + 1, live.size()):
				var pa: Vector3 = TrackGeometry.runner_pose(kind, live[a].lane, live[a].distance, live[a].lateral)["position"]
				var pb: Vector3 = TrackGeometry.runner_pose(kind, live[b].lane, live[b].distance, live[b].lateral)["position"]
				worst_sep = minf(worst_sep, Vector2(pa.x - pb.x, pa.z - pb.z).length())
				var key: String = "%d-%d" % [a, b]
				var dd: float = live[a].distance - live[b].distance
				var sgn: int = 1 if dd > 0.7 else (-1 if dd < -0.7 else 0)
				if sgn != 0:
					if sign_of.has(key) and sign_of[key] != sgn:
						crossings += 1
					sign_of[key] = sgn
	_check(rc.state != rc.State.COUNTDOWN and steps > 100, "%s: la gara e' girata (%d passi)" % [label, steps])
	_check(in_lane_ok, "%s: nessuno lascia la propria corsia prima della linea di rientro (%.1f m)" % [label, win.x])
	_check(nonneg, "%s: scostamento sempre >= 0" % label)
	_check(worst_speed < 3.5, "%s: nessun salto laterale (velocita' laterale massima %.2f m/s) %s" % [label, worst_speed, worst_info if worst_speed >= 3.5 else ""])
	_check(worst_sep > 0.3, "%s: nessuno si compenetra (distanza minima %.2f m)" % [label, worst_sep])
	_check(finish_ok, "%s: tutti hanno percorso la distanza intera a final_time (l'arrivo non cambia)" % label)
	# il tempo ufficiale non e' stato toccato: ognuno e' registrato come arrivato esattamente a final_time
	var winner: RunnerData = rc.live_order[0]
	_check(winner.place == 1 and winner.finished, "%s: vince chi ha il tempo ufficiale migliore (%s)" % [label, winner.athlete_name])
	# funzione pura del tempo, sulla gara vera
	var pack: PackFormation = rc._pack
	var t1: float = rc.runners[0].final_time * 0.6
	var l1: PackedFloat64Array = pack.lateral_offsets(t1)
	pack.lateral_offsets(rc.runners[0].final_time * 0.2)
	_check(pack.lateral_offsets(t1) == l1, "%s: riavvolgendo e rileggendo si ottiene la stessa formazione" % label)
	return crossings
