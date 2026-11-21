class_name RaceMotion
extends RefCounted
## Modello di movimento delle gare in pista: funzioni pure, nessuno stato di scena.
##
## E' la trascrizione GDScript di `_velocity` / `curve_progress` di views/race_viewer.py:
## una curva di velocita' per tipo di gara viene integrata e normalizzata in modo che lo spazio percorso
## valga ESATTAMENTE 1 a u = 1. Per questo ogni corridore taglia il traguardo al suo `final_time`,
## qualunque sia la curva. `kind` e' il nome dell'evento ("100m", "400m"): se cambi una curva in Python,
## cambiala anche qui.

const DISTANCES: Dictionary = {"100m": 100.0, "400m": 400.0, "800m": 800.0, "1500m": 1500.0, "4x100m": 400.0, "4x400m": 1600.0}
const STEPS: int = 600
const RUNOUT_TAU: float = 1.1   # costante di tempo della decelerazione dopo il traguardo (s)
const DNF_FRACTION: float = 0.42  # un ritirato smette di correre a questa frazione di gara (DNF_PROGRESS in Python)
const DNF_TAU: float = 0.7      # ...e rallenta con questa costante di tempo (s)
## Stile di passo (solo messa in scena): ogni corridore ha `style` in [-1, 1] (lo calcola Python, vedi `pace_style` in views/race_viewer.py, e lo esporta).
## Il tempo normalizzato si deforma in u' = u + style * AMP * sin(PI * u): 0 e 1 restano fissi, quindi l'arrivo e' ESATTAMENTE `final_time`.
## > 0 parte forte e cala, < 0 parte piano e chiude forte. Con style = 0 i valori sono quelli di sempre. AMP: copia di PACE_AMPLITUDE di race_viewer.py.
const PACE_AMPLITUDE: Dictionary = {"100m": 0.008, "400m": 0.012, "800m": 0.016, "1500m": 0.014, "4x100m": 0.010, "4x400m": 0.010}
## Staffette (Q41c): lo stile e' PER FRAZIONE, un PackedFloat64Array di 4 numeri in [-1, 1] (colonna `leg_styles`, li calcola Python). Il tempo normalizzato si deforma
## con scostamenti cumulativi ai cambi, D_k = AMP * somma_{i<k}(stile_i - media), D_0 = D_4 = 0 (via e arrivo ESATTI), raccordati con una smoothstep tra un cambio e
## l'altro: ai cambi le squadre non sono nell'ordine d'arrivo, e la velocita' resta continua. I cambi cadono su quarti esatti di tempo perche' la velocita' delle
## staffette e' periodica sui quarti. Copia di `relay_offset` di views/race_viewer.py (stesse cifre): se cambi una, cambia l'altra. Uno stile numerico singolo su una staffetta e' inerte.
const RELAY_LEGS: int = 4

static var _tables: Dictionary = {}


static func is_supported(kind: String) -> bool:
	return DISTANCES.has(kind)


static func race_distance(kind: String) -> float:
	return float(DISTANCES.get(kind, 100.0))


static func dnf_stop_distance(kind: String) -> float:
	return DNF_FRACTION * race_distance(kind)


## Velocita' relativa (sempre > 0) al tempo normalizzato u in [0, 1].
static func _velocity(kind: String, u: float) -> float:
	if kind == "400m":  # partenza veloce, calo nella seconda meta'
		return (1.0 - exp(-u / 0.05)) * (1.0 - 0.16 * u) + 0.02
	if kind == "800m":  # partenza in corsia veloce, ritmo regolare, volata negli ultimi 100 m
		return (1.0 - exp(-u / 0.03)) * (0.96 + 0.02 * u + 1.1 * pow(maxf(0.0, u - 0.9), 1.4)) + 0.02
	if kind == "1500m":  # gruppo compatto, poi volata finale
		return (1.0 - exp(-u / 0.02)) * (0.92 + 0.05 * u + 1.3 * pow(maxf(0.0, u - 0.88), 1.4)) + 0.02
	if kind == "4x100m" or kind == "4x400m":  # 4 frazioni: ogni cambio accelera, leggero calo a fine frazione
		var s: float = fposmod(u * 4.0, 1.0)
		return 0.72 + 0.28 * (1.0 - exp(-s / 0.2)) - 0.06 * s
	# 100m: spinta esplosiva dai blocchi, accelerazione fino a ~60 m, poi leggero calo
	return (0.22 + 0.78 * (1.0 - exp(-u / 0.10))) * (1.0 - 0.07 * maxf(0.0, (u - 0.6) / 0.4))


## Tabella dello spazio normalizzato 0..1 a passi uniformi di tempo, per tipo di gara.
static func _get_table(kind: String) -> PackedFloat64Array:
	if not _tables.has(kind):
		var cum: PackedFloat64Array = PackedFloat64Array([0.0])
		for i in range(1, STEPS + 1):
			var u0: float = float(i - 1) / STEPS
			var u1: float = float(i) / STEPS
			cum.append(cum[i - 1] + 0.5 * (_velocity(kind, u0) + _velocity(kind, u1)) / STEPS)
		var total: float = cum[STEPS]
		for i in range(cum.size()):
			cum[i] = cum[i] / total
		_tables[kind] = cum
	return _tables[kind]


static func pace_amplitude(kind: String) -> float:
	return float(PACE_AMPLITUDE.get(kind, 0.0))


static func _is_relay(kind: String) -> bool:
	return kind == "4x100m" or kind == "4x400m"


## Vero se `style` deforma qualcosa: un numero diverso da 0 oppure una lista di stili per frazione non vuota.
static func _has_style(style: Variant) -> bool:
	if style is PackedFloat64Array:
		return (style as PackedFloat64Array).size() > 0
	return float(style) != 0.0


## Scostamenti di tempo normalizzato ai cambi (nodi): D_0 = D_n = 0, D_k = amp * somma_{i<k}(stile_i - media).
static func _relay_nodes(styles: PackedFloat64Array, amp: float) -> PackedFloat64Array:
	var n: int = styles.size()
	var mean: float = 0.0
	for s: float in styles:
		mean += s
	mean /= float(n)
	var nodes: PackedFloat64Array = PackedFloat64Array([0.0])
	for i in range(n - 1):
		nodes.append(nodes[i] + amp * (styles[i] - mean))
	nodes.append(0.0)  # arrivo esatto per costruzione (e senza portarsi dietro l'errore dei float)
	return nodes


static func _relay_offset(styles: PackedFloat64Array, amp: float, u: float) -> float:
	var n: int = styles.size()
	var nodes: PackedFloat64Array = _relay_nodes(styles, amp)
	var x: float = clampf(u, 0.0, 1.0) * float(n)
	var k: int = mini(n - 1, int(x))
	var f: float = x - float(k)
	return nodes[k] + (nodes[k + 1] - nodes[k]) * (f * f * (3.0 - 2.0 * f))


## Derivata di _relay_offset rispetto a u (la smoothstep ha derivata 6 f (1 - f)).
static func _relay_offset_slope(styles: PackedFloat64Array, amp: float, u: float) -> float:
	var n: int = styles.size()
	var nodes: PackedFloat64Array = _relay_nodes(styles, amp)
	var x: float = clampf(u, 0.0, 1.0) * float(n)
	var k: int = mini(n - 1, int(x))
	var f: float = x - float(k)
	return (nodes[k + 1] - nodes[k]) * float(n) * 6.0 * f * (1.0 - f)


## Tempo normalizzato deformato dallo stile di passo (identita' senza stile; 0 e 1 fissi). `style`: un numero, o per le staffette la lista dei 4 stili per frazione.
static func warp(u: float, kind: String, style: Variant) -> float:
	var c: float = clampf(u, 0.0, 1.0)
	if style is PackedFloat64Array:
		var legs: PackedFloat64Array = style
		return c + _relay_offset(legs, pace_amplitude(kind), c) if legs.size() > 0 else c
	if _is_relay(kind):
		return c
	return c + float(style) * pace_amplitude(kind) * sin(PI * c)


## Derivata di warp() rispetto a u (positiva finche' |style| * AMP * PI <= 1).
static func warp_slope(u: float, kind: String, style: Variant) -> float:
	if style is PackedFloat64Array:
		var legs: PackedFloat64Array = style
		return 1.0 + _relay_offset_slope(legs, pace_amplitude(kind), u) if legs.size() > 0 else 1.0
	if _is_relay(kind):
		return 1.0
	return 1.0 + float(style) * pace_amplitude(kind) * PI * cos(PI * clampf(u, 0.0, 1.0))


static func _raw_progress(u: float, kind: String) -> float:
	var table: PackedFloat64Array = _get_table(kind)
	var x: float = clampf(u, 0.0, 1.0) * STEPS
	var i: int = mini(STEPS - 1, int(x))
	return lerpf(table[i], table[i + 1], x - float(i))


static func _raw_slope(u: float, kind: String) -> float:
	var table: PackedFloat64Array = _get_table(kind)
	var i: int = mini(STEPS - 1, int(clampf(u, 0.0, 1.0) * STEPS))
	return (table[i + 1] - table[i]) * STEPS


## Frazione di percorso (0..1) al tempo normalizzato u. Monotona; 0 a u=0, 1 a u=1 (anche con uno stile di passo).
static func progress(u: float, kind: String = "100m", style: Variant = 0.0) -> float:
	return _raw_progress(warp(u, kind, style) if _has_style(style) else u, kind)


## Derivata di progress() rispetto a u (spazio normalizzato per unita' di tempo normalizzato).
static func slope(u: float, kind: String = "100m", style: Variant = 0.0) -> float:
	if not _has_style(style):
		return _raw_slope(u, kind)
	return _raw_slope(warp(u, kind, style), kind) * warp_slope(u, kind, style)


## Stato di un corridore al tempo di gara `race_t` (secondi dallo sparo).
## Ritorna Vector2(distanza_m, velocita_m_s), con la distanza misurata dalla SUA linea di partenza.
## - prima di `reaction`: fermo ai blocchi
## - fino a `final_time`: corre sulla curva, arrivando a race_distance(kind) esatti a `final_time`
## - dopo: continua e rallenta (lancio oltre il traguardo)
static func state_at(race_t: float, reaction: float, final_time: float, kind: String = "100m", style: Variant = 0.0) -> Vector2:
	if race_t <= reaction:
		return Vector2.ZERO
	var total: float = race_distance(kind)
	var run_duration: float = final_time - reaction
	if race_t < final_time:
		var u: float = (race_t - reaction) / run_duration
		return Vector2(total * progress(u, kind, style), total * slope(u, kind, style) / run_duration)
	var finish_speed: float = total * slope(1.0, kind, style) / run_duration
	var dt: float = race_t - final_time
	var decay: float = exp(-dt / RUNOUT_TAU)
	return Vector2(total + finish_speed * RUNOUT_TAU * (1.0 - decay), finish_speed * decay)


## Tempo di gara (s dallo sparo) a cui un corridore ha percorso `distance` m, sulla stessa curva di state_at().
static func time_at_distance(distance: float, reaction: float, final_time: float, kind: String = "100m", style: Variant = 0.0) -> float:
	var target: float = clampf(distance / race_distance(kind), 0.0, 1.0)
	var lo: float = 0.0
	var hi: float = 1.0
	for i in range(40):
		var mid: float = (lo + hi) * 0.5
		if progress(mid, kind, style) < target:
			lo = mid
		else:
			hi = mid
	return reaction + hi * (final_time - reaction)


## Come state_at(), ma per un ritirato: corre sulla stessa curva fino a dnf_stop_distance(kind), poi rallenta e si ferma.
static func state_at_dnf(race_t: float, reaction: float, final_time: float, kind: String = "100m", style: Variant = 0.0) -> Vector2:
	var t_stop: float = time_at_distance(dnf_stop_distance(kind), reaction, final_time, kind, style)
	if race_t < t_stop:
		return state_at(race_t, reaction, final_time, kind, style)
	var at_stop: Vector2 = state_at(t_stop, reaction, final_time, kind, style)
	var dt: float = race_t - t_stop
	var decay: float = exp(-dt / DNF_TAU)
	return Vector2(at_stop.x + at_stop.y * DNF_TAU * (1.0 - decay), at_stop.y * decay)
