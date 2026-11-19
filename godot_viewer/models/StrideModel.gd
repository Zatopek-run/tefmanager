class_name StrideModel
extends RefCounted
## MODEL (solo vista) - cadenza e ampiezza di passo per evento, fase di gara e altezza dell'atleta.
## Dati da raw/parametri_biomeccanici_atletica.md (atleti evoluti): la velocita' e' v = f x L, con f cadenza (Hz = passi/s)
## e L ampiezza del singolo passo (m). Serve SOLO ad animare le gambe in `RunnerView`: tempi, ordine e posizioni li decide il
## modello Python (RaceMotion); qui si ricava come "riempire" la velocita' gia' decisa con frequenza e falcata credibili.
##
## Cadenza di riferimento (Hz) a distanza `d` dalla propria partenza, per un atleta alto REF_HEIGHT:
##   100m  : sale dai primi passi (3,6) al picco (~4,75) entro 25 m, si stabilizza 4,6-4,5 fra 35 e 80 m e cala del 4% a fine
##           gara (affaticamento neuromuscolare). L cresce da 1,10 m a oltre 2,30 m nei primi 30 m.
##   400m  : 3,9 Hz nei primi 200 m (azione economica), poi cala (acidosi: il contatto si allunga) fino a ~3,35 Hz alla fine.
##   800m  : STIMA (il file di riferimento non ha dati sull'800m): fra i 400m e i 1500m, 3,85 Hz nei primi 150 m,
##           ~3,5 Hz a regime, volata fino a ~3,95 Hz negli ultimi 100 m.
##   1500m : ~3,2 Hz costanti (risparmio energetico); nella volata degli ultimi 200-300 m sale a ~3,9 Hz.
## Altezza: a parita' di tempo l'atleta piu' alto ha una cadenza minore del ~5% ogni 17 cm (1,75 -> 1,92 m) e compensa con
## un'ampiezza maggiore (L = v / f la ricava da sola).
## Fatica: colpisce prima il tempo di contatto e quindi la frequenza (curve in calo oltre meta' gara); l'ampiezza cala solo
## perche' la velocita' cala. Non c'e' una fatica per atleta: non e' un dato esportato dal gioco.

const REF_HEIGHT: float = 1.78
const HEIGHT_COEF: float = 0.30           # frazione di cadenza persa per ogni metro in piu' di altezza (17 cm = -5,1%)
const HEIGHT_FACTOR_MIN: float = 0.9
const HEIGHT_FACTOR_MAX: float = 1.1
const FLYING_START_OFFSET: float = 30.0   # frazioni di staffetta col testimone in corsa: partono gia' "lanciate"
const ACCEL_ZONE: float = 30.0            # m: nei primi 30 m l'ampiezza cresce da 1,10 m al valore di regime
const START_STEP_LENGTH: float = 1.10     # m: primo passo (dai blocchi o da fermo)

## Punti (distanza m, cadenza Hz) interpolati linearmente. Per le gare non elencate: vedi `curve_kind`.
const CURVES: Dictionary = {
	"100m": [[0.0, 3.6], [12.0, 4.45], [25.0, 4.75], [35.0, 4.62], [80.0, 4.5], [100.0, 4.32]],
	"400m": [[0.0, 3.5], [30.0, 3.9], [200.0, 3.9], [300.0, 3.65], [340.0, 3.5], [400.0, 3.35]],
	"800m": [[0.0, 3.6], [40.0, 3.85], [150.0, 3.7], [650.0, 3.5], [700.0, 3.6], [800.0, 3.95]],
	"1500m": [[0.0, 3.4], [60.0, 3.2], [1200.0, 3.15], [1300.0, 3.45], [1400.0, 3.75], [1500.0, 3.9]],
}
## Ampiezza di passo a regime (m) per evento: serve solo al pavimento dei primi 30 m.
const STEP_LENGTH_CRUISE: Dictionary = {"100m": 2.30, "400m": 2.10, "800m": 1.95, "1500m": 1.80}


## La curva da usare: le staffette sono tratti di 100 o 400 m.
static func curve_kind(event_kind: String) -> String:
	match event_kind:
		"4x100m": return "100m"
		"4x400m": return "400m"
		_: return event_kind


static func is_supported(event_kind: String) -> bool:
	return CURVES.has(curve_kind(event_kind))


static func height_factor(height_m: float) -> float:
	return clampf(1.0 - HEIGHT_COEF * (height_m - REF_HEIGHT), HEIGHT_FACTOR_MIN, HEIGHT_FACTOR_MAX)


## Cadenza (Hz = passi/s) a distanza `d` dalla partenza per un atleta alto `height_m`. Gara non supportata: 0.
static func cadence(event_kind: String, d: float, height_m: float = REF_HEIGHT) -> float:
	var kind: String = curve_kind(event_kind)
	if not CURVES.has(kind):
		return 0.0
	return _interp(CURVES[kind], d) * height_factor(height_m)


## Ampiezza del singolo passo (m) con v = f x L, ma mai sotto il pavimento dei primi metri: 1,10 m al primo passo che cresce
## fino al valore di regime in ACCEL_ZONE (cosi' da fermi non si "pedala sul posto").
static func step_length(event_kind: String, d: float, speed: float, height_m: float = REF_HEIGHT) -> float:
	var f: float = cadence(event_kind, d, height_m)
	if f <= 0.0:
		return 0.0
	var kind: String = curve_kind(event_kind)
	var cruise: float = float(STEP_LENGTH_CRUISE.get(kind, 2.0))
	var floor_len: float = lerpf(START_STEP_LENGTH, cruise, smoothstep(0.0, ACCEL_ZONE, d))
	return maxf(speed / f, floor_len)


## Metri per ciclo completo (2 passi): e' il "stride" che `RunnerView` usa per regolare la velocita' dell'animazione.
static func cycle_length(event_kind: String, d: float, speed: float, height_m: float = REF_HEIGHT) -> float:
	return 2.0 * step_length(event_kind, d, speed, height_m)


static func _interp(points: Array, d: float) -> float:
	if d <= float((points[0] as Array)[0]):
		return float((points[0] as Array)[1])
	for i in range(1, points.size()):
		var a: Array = points[i - 1]
		var b: Array = points[i]
		if d <= float(b[0]):
			var t: float = (d - float(a[0])) / (float(b[0]) - float(a[0]))
			return lerpf(float(a[1]), float(b[1]), t)
	return float((points[points.size() - 1] as Array)[1])
