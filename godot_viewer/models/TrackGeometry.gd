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


## Fine della prima curva (PI * R1 = 115,6 m): da qui nei 800m si puo' lasciare la corsia (regolamento). Stessa cifra di BREAK_WINDOWS in PackFormation.
const BREAK_800M_START: float = 115.6
const BREAK_800M_END: float = 145.0


## Coordinata d'anello da cui parte la 1500m in corsia 1 (3,75 giri prima del traguardo).
static func start_offset_1500m() -> float:
	return 4.0 * loop_length(1) - 1500.0


## Coordinata d'anello da cui parte la 800m in corsia 1 (2 giri esatti prima del traguardo: la partenza e' sulla linea d'arrivo).
static func start_offset_800m() -> float:
	return 2.0 * loop_length(1) - 800.0


## Posizione (x, z) alla coordinata d'anello `c` (riferita alla corsia 1) con offset radiale esterno `lat` >= 0.
static func position_at_radial(c: float, lat: float) -> Vector2:
	var r: float = R1 + lat
	c = fposmod(c, loop_length(1))
	var arc: float = PI * R1
	if c < arc:
		var a: float = c / R1
		return Vector2(r * sin(a), -R1 + r * cos(a))
	c -= arc
	if c < STRAIGHT:
		return Vector2(-c, -R1 - r)
	c -= STRAIGHT
	if c < arc:
		var a2: float = c / R1
		return Vector2(-STRAIGHT - r * sin(a2), -R1 - r * cos(a2))
	return Vector2(-STRAIGHT + (c - arc), lat)


## Posa 3D nei 1500m: partenza in linea curva sulla corsia assegnata, poi rientro graduale alla corda (corsie 1-3).
static func pose_1500m(lane: int, distance_run: float) -> Dictionary:
	var c: float = start_offset_1500m() + distance_run
	var start_lat: float = float(lane - 1) * LANE_WIDTH
	var pack_lat: float = minf(2.1, float(lane - 1) * 0.30)
	var lat: float = lerpf(start_lat, pack_lat, smoothstep(10.0, 90.0, distance_run))
	var p: Vector2 = position_at_radial(c, lat)
	var h: Vector2 = heading_at(1, c)
	return {"position": Vector3(p.x, 0.0, p.y), "heading": h, "yaw": atan2(-h.y, h.x)}


## Posa 3D nella 800m (come la vista PyQt: semplificazione visiva, la linea di partenza e' allineata invece che sfalsata):
## prima curva (~115 m) nella corsia sorteggiata, poi rientro graduale alla corda fra 100 e 150 m dalla partenza.
static func pose_800m(lane: int, distance_run: float) -> Dictionary:
	var c: float = start_offset_800m() + distance_run
	var start_lat: float = float(lane - 1) * LANE_WIDTH
	var pack_lat: float = minf(2.1, float(lane - 1) * 0.30)
	var lat: float = lerpf(start_lat, pack_lat, smoothstep(BREAK_800M_START, BREAK_800M_END, distance_run))
	var p: Vector2 = position_at_radial(c, lat)
	var h: Vector2 = heading_at(1, c)
	return {"position": Vector3(p.x, 0.0, p.y), "heading": h, "yaw": atan2(-h.y, h.x)}


## Posa 3D in un gruppo (800m, 1500m, 4x400m dopo i 400 m) con lo scostamento laterale `lat` dalla corda deciso dalla formazione (PackFormation): vedi runner_pose().
## Nella 4x400m la coordinata riparte dalla linea d'arrivo a ogni giro: dopo i 400 m si e' a `distance_run - 400` dal traguardo (come pose_4x400m).
static func pose_pack(kind: String, distance_run: float, lat: float) -> Dictionary:
	var c: float
	if kind == "4x400m":
		c = distance_run - 400.0
	else:
		c = (start_offset_800m() if kind == "800m" else start_offset_1500m()) + distance_run
	var p: Vector2 = position_at_radial(c, maxf(0.0, lat))
	var h: Vector2 = heading_at(1, c)
	return {"position": Vector3(p.x, 0.0, p.y), "heading": h, "yaw": atan2(-h.y, h.x)}


## Posa 3D nella 4x400m: prima frazione in corsia sfalsata (0..400m), poi rientro alla corda dopo la curva.
static func pose_4x400m(lane: int, distance_run: float) -> Dictionary:
	if distance_run <= 400.0:
		return pose(lane, distance_run)
	var c: float = distance_run - 400.0
	var start_lat: float = float(lane - 1) * LANE_WIDTH
	var pack_lat: float = minf(2.1, float(lane - 1) * 0.30)
	var lat: float = lerpf(start_lat, pack_lat, smoothstep(410.0, 500.0, distance_run))
	var p: Vector2 = position_at_radial(c, lat)
	var h: Vector2 = heading_at(1, c)
	return {"position": Vector3(p.x, 0.0, p.y), "heading": h, "yaw": atan2(-h.y, h.x)}


## Linea di partenza dei 100m: sul rettilineo d'arrivo prolungato all'indietro ("chute") oltre l'inizio dell'arco.
const START_100M_X: float = -100.0


## Posizione 3D, direzione e angolo di un corridore in gara. Unica fonte per RunnerView, camere e test.
## - 100m: corre dalla linea di partenza (x = -100) al traguardo (x = 0) sul rettilineo, poi prosegue nella curva
##   della sua corsia (la "corsa dopo il traguardo" segue la pista, non la attraversa).
## - 1500m: partenza a gruppi sulla linea curva e rientro alla corda.
## - 800m: partenza sulla linea d'arrivo, prima curva in corsia, poi rientro alla corda.
## - 4x400m: primo giro in corsia sfalsata, poi rientro alla corda.
## - 400m / 4x100m: partenza sfalsata per corsia (vedi pose()).
## `lat_override` >= 0 (solo 800m, 1500m e 4x400m oltre i 400 m): scostamento laterale dalla corda deciso dalla formazione del gruppo invece della regola per corsia.
## Nella 4x400m i primi 400 m restano in corsia sfalsata (pose()): la formazione vale dal secondo giro.
static func runner_pose(kind: String, lane: int, distance_run: float, lat_override: float = -1.0) -> Dictionary:
	if lat_override >= 0.0 and (kind == "1500m" or kind == "800m" or (kind == "4x400m" and distance_run > 400.0)):
		return pose_pack(kind, distance_run, lat_override)
	if kind == "1500m":
		return pose_1500m(lane, distance_run)
	if kind == "800m":
		return pose_800m(lane, distance_run)
	if kind == "4x400m":
		return pose_4x400m(lane, distance_run)
	if kind != "100m":
		return pose(lane, distance_run)
	if distance_run <= 100.0:
		return {"position": Vector3(START_100M_X + distance_run, 0.0, (lane - 1) * LANE_WIDTH),
			"heading": Vector2(1.0, 0.0), "yaw": 0.0}
	var c: float = distance_run - 100.0  # oltre il traguardo: arco 1 della propria corsia
	var p: Vector2 = position_at(lane, c)
	var h: Vector2 = heading_at(lane, c)
	return {"position": Vector3(p.x, 0.0, p.y), "heading": h, "yaw": atan2(-h.y, h.x)}


enum Region { ARC1, BACK, ARC2, HOME }

const REGION_EPS: float = 0.1   # m, vedi region_for() (800m)


## In quale tratto dell'anello si trova un corridore (usato dalla regia ovale): curva 1, rettilineo opposto,
## curva 2, rettilineo d'arrivo. Oltre il traguardo si riavvolge sulla curva 1.
static func region(lane: int, distance_run: float) -> int:
	return region_for("400m", lane, distance_run)


static func region_for(kind: String, lane: int, distance_run: float) -> int:
	var c: float
	var r: float
	if kind == "1500m":
		c = fposmod(start_offset_1500m() + distance_run, loop_length(1))
		r = R1
	elif kind == "800m":
		# +REGION_EPS: la partenza e' esattamente sulla linea d'arrivo (c = 2L - 800 = -0,04 m), che si riavvolge sul
		# rettilineo d'arrivo: senza tolleranza la regia taglierebbe per un istante sulla ripresa del rettilineo.
		c = fposmod(start_offset_800m() + distance_run + REGION_EPS, loop_length(1))
		r = R1
	elif kind == "4x400m" and distance_run > 400.0:
		c = fposmod(distance_run - 400.0, loop_length(1))
		r = R1
	else:
		c = fposmod(start_offset(lane) + distance_run, loop_length(lane))
		r = radius(lane)
	var arc: float = PI * r
	if c < arc:
		return Region.ARC1
	c -= arc
	if c < STRAIGHT:
		return Region.BACK
	c -= STRAIGHT
	return Region.ARC2 if c < arc else Region.HOME
