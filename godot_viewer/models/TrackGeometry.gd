class_name TrackGeometry
extends RefCounted
## Geometria della pista ovale di 400 m (funzioni pure) e posizione di un corridore sulla sua corsia.
##
## Piano XZ, su = +Y. Il traguardo e' a x = 0 alla fine del rettilineo d'arrivo (x da -STRAIGHT a 0, corsia k a
## z = (k-1)*LANE_WIDTH, quindi la corsia 1 e' la piu' interna e il prato e' a z < 0). I corridori vanno verso +X
## sul rettilineo d'arrivo e girano a sinistra (antiorario visto dall'alto).
##
## Coordinata d'anello `c` di una corsia: 0 al traguardo, poi curva 1 (pi*r), rettilineo opposto (STRAIGHT),
## curva 2 (pi*r), rettilineo d'arrivo (STRAIGHT). Chi corre 400 m parte da c0 = lunghezza_anello - 400
## (partenza sfalsata: le corsie esterne sono piu' lunghe) e arriva a c = lunghezza_anello = traguardo.

const STRAIGHT: float = 84.39
const R1: float = 36.8         # raggio della linea di corsa della corsia 1 (da' esattamente 400 m)
const LANE_WIDTH: float = 1.22
const LANES: int = 8
const FINISH_X: float = 0.0


static func radius(lane: int) -> float:
	return R1 + (lane - 1) * LANE_WIDTH


static func loop_length(lane: int) -> float:
	return 2.0 * STRAIGHT + TAU * radius(lane)


## Coordinata d'anello da cui parte un corridore dei 400 m in questa corsia.
static func start_offset(lane: int) -> float:
	return loop_length(lane) - 400.0


## Posizione (x, z) sulla corsia alla coordinata d'anello `c` (qualsiasi valore: si riavvolge).
static func position_at(lane: int, c: float) -> Vector2:
	var r: float = radius(lane)
	var l: float = loop_length(lane)
	c = fposmod(c, l)
	var arc: float = PI * r
	if c < arc:  # curva 1, centro (0, -R1)
		var a: float = c / r
		return Vector2(r * sin(a), -R1 + r * cos(a))
	c -= arc
	if c < STRAIGHT:  # rettilineo opposto, verso -X
		return Vector2(-c, -R1 - r)
	c -= STRAIGHT
	if c < arc:  # curva 2, centro (-STRAIGHT, -R1)
		var a2: float = c / r
		return Vector2(-STRAIGHT - r * sin(a2), -R1 - r * cos(a2))
	c -= arc
	return Vector2(-STRAIGHT + c, (lane - 1) * LANE_WIDTH)  # rettilineo d'arrivo, verso +X


## Direzione di marcia (versore x, z) alla coordinata d'anello `c`.
static func heading_at(lane: int, c: float) -> Vector2:
	var r: float = radius(lane)
	c = fposmod(c, loop_length(lane))
	var arc: float = PI * r
	if c < arc:
		var a: float = c / r
		return Vector2(cos(a), -sin(a))
	c -= arc
	if c < STRAIGHT:
		return Vector2(-1.0, 0.0)
	c -= STRAIGHT
	if c < arc:
		var a2: float = c / r
		return Vector2(-cos(a2), sin(a2))
	return Vector2(1.0, 0.0)


## Posizione 3D (y = 0) e angolo di rotazione attorno a Y che porta +X sulla direzione di marcia.
static func pose(lane: int, distance_run: float) -> Dictionary:
	var c: float = start_offset(lane) + distance_run
	var p: Vector2 = position_at(lane, c)
	var h: Vector2 = heading_at(lane, c)
	return {"position": Vector3(p.x, 0.0, p.y), "heading": h, "yaw": atan2(-h.y, h.x)}
