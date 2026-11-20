class_name OvalTrackBuilder
extends RefCounted
## VIEW 3D - costruisce la pista ovale da 400 m (tartan, linee di corsia, linee di partenza sfalsate, traguardo)
## a partire da TrackGeometry: il disegno e il percorso dei corridori usano gli stessi numeri e non possono
## divergere. Tutto e' geometria procedurale (nessun asset).

const TARTAN: Color = Color(0.17, 0.31, 0.60)   # 100m: tartan blu come nel riferimento (stadio di Roma)
const TARTAN_400M: Color = Color(0.43, 0.14, 0.46)  # 400m: tartan viola (Parigi 2024); piu' chiaro sbiadiva a lavanda, piu' blu virava a indaco sotto la luce fredda
const CHUTE_BEHIND_START: float = 3.0       # 100m: il rettilineo si prolunga oltre la linea di partenza
const LINE: Color = Color(0.95, 0.95, 0.95)
const GRASS_IN: Color = Color(0.09, 0.27, 0.12)
const GRASS_OUT: Color = Color(0.16, 0.4, 0.18)
const ARC_STEPS: int = 64
const START_BLOCKS_GROUP: StringName = &"start_blocks"
const GRASS_STRIPE_PERIOD: float = 8.0   # m: una fascia chiara + una scura
const _AdBoards = preload("res://scripts/AdBoards.gd")


static func build(parent: Node3D, kind: String = "400m") -> void:
	var s: float = TrackGeometry.STRAIGHT
	var r1: float = TrackGeometry.R1
	var w: float = TrackGeometry.LANE_WIDTH
	var lanes: int = TrackGeometry.LANES
	var tartan: StandardMaterial3D = _material(TARTAN if kind == "100m" else TARTAN_400M, 0.9)
	var line: StandardMaterial3D = _material(LINE, 0.7)

	# Prato: un unico grande piano sotto la pista (interno e dintorni), con le fasce del taglio erba.
	_box(parent, Vector3(360.0, 0.1, 300.0), Vector3(-s * 0.5, -0.1, -r1 - 10.0), _grass_material())

	var inner: float = r1 - w * 0.5                  # bordo interno della corsia 1
	var outer: float = r1 + (lanes - 0.5) * w        # bordo esterno della corsia 8
	var width: float = lanes * w

	# Rettilineo d'arrivo (z da -0,61 a 9,15) e rettilineo opposto (z = -R1 - r). Nei 100m il rettilineo d'arrivo si
	# prolunga all'indietro fino a dietro la linea di partenza ("chute"): le linee di corsia divergono dall'arco.
	var home_len: float = s
	if kind == "100m":
		home_len = -TrackGeometry.START_100M_X + CHUTE_BEHIND_START
	_box(parent, Vector3(home_len, 0.1, width), Vector3(-home_len * 0.5, -0.05, (lanes - 1) * w * 0.5), tartan)
	_box(parent, Vector3(s, 0.1, width), Vector3(-s * 0.5, -0.05, -r1 - (inner + outer) * 0.5), tartan)
	# Le due curve: semicerchi anulari. Curva 1 centro (0, -R1); curva 2 centro (-S, -R1), specchiata.
	_arc_band(parent, Vector2(0.0, -r1), 1.0, inner, outer, 0.0, tartan)
	_arc_band(parent, Vector2(-s, -r1), -1.0, inner, outer, 0.0, tartan)

	# Linee di corsia (9 bordi) su rettilinei e curve.
	for i in range(lanes + 1):
		var r: float = inner + i * w
		var z_home: float = -w * 0.5 + i * w
		_box(parent, Vector3(home_len, 0.012, 0.05), Vector3(-home_len * 0.5, 0.006, z_home), line)
		_box(parent, Vector3(s, 0.012, 0.05), Vector3(-s * 0.5, 0.006, -r1 - r), line)
		_arc_band(parent, Vector2(0.0, -r1), 1.0, r - 0.025, r + 0.025, 0.006, line)
		_arc_band(parent, Vector2(-s, -r1), -1.0, r - 0.025, r + 0.025, 0.006, line)

	# Cartelloni LED sul bordo interno dei due rettilinei, rivolti verso le camere esterne (+Z).
	# Rettilinei: solo tra -S e 0 (oltre, nei 100m, il rettilineo prolungato si fonde con la curva e il cartellone starebbe
	# sul tartan). Curve: a raggio `inner - 1,6`, cioe' 1,6 m dentro il bordo interno, rivolti verso l'esterno.
	# A doppia faccia: le camere dentro il campo (_o_start, _o_open...) li vedono da dietro.
	var n: int = _AdBoards.row(parent, -s, 0.0, -2.2, 0.0, 0, true)
	n += _AdBoards.row(parent, -s, 0.0, -r1 - inner + 1.6, 0.0, n, true)
	n += _AdBoards.arc(parent, Vector2(0.0, -r1), 1.0, inner - 1.6, n, 0.0, PI, false, true)
	_AdBoards.arc(parent, Vector2(-s, -r1), -1.0, inner - 1.6, n, 0.0, PI, false, true)

	if kind == "100m":
		# Linea di partenza unica (sul rettilineo prolungato), blocchi e cartellini di corsia.
		_box(parent, Vector3(0.1, 0.014, width), Vector3(TrackGeometry.START_100M_X, 0.008, (lanes - 1) * w * 0.5), line)
		for lane in range(1, lanes + 1):
			_blocks_and_placard(parent, Vector3(TrackGeometry.START_100M_X, 0.0, (lane - 1) * w), 0.0, lane)
	elif kind == "1500m":
		# Partenza in piedi su linea curva unica senza blocchi (corsie 1..8 convergono poi alla corda).
		var c0: float = TrackGeometry.start_offset_1500m()
		for lane in range(1, lanes + 1):
			var lat: float = (float(lane) - 1.0) * w
			var p: Vector2 = TrackGeometry.position_at_radial(c0, lat)
			var h: Vector2 = TrackGeometry.heading_at(1, c0)
			var mark: MeshInstance3D = _box(parent, Vector3(0.1, 0.014, w), Vector3(p.x, 0.008, p.y), line)
			mark.rotation.y = atan2(-h.y, h.x)
	elif kind == "800m":
		# Partenza in piedi sulla linea d'arrivo (corsie 1..8 allineate), senza blocchi; il rientro alla corda e' dopo la
		# prima curva, dove sta la linea di rientro (linea sul rettilineo opposto, a x = 0).
		var c0: float = TrackGeometry.start_offset_800m()
		for lane in range(1, lanes + 1):
			var lat: float = (float(lane) - 1.0) * w
			var p: Vector2 = TrackGeometry.position_at_radial(c0, lat)
			var h: Vector2 = TrackGeometry.heading_at(1, c0)
			var mark: MeshInstance3D = _box(parent, Vector3(0.1, 0.014, w), Vector3(p.x, 0.008, p.y), line)
			mark.rotation.y = atan2(-h.y, h.x)
		_box(parent, Vector3(0.1, 0.014, width), Vector3(0.0, 0.008, -r1 - (inner + outer) * 0.5), line)
	elif kind == "Salto in Lungo":
		# Pedana di rincorsa + asse di battuta + fossa di sabbia nel prato interno (z = -14).
		var pit_z: float = -14.0
		var runway_col: StandardMaterial3D = _material(Color(0.68, 0.27, 0.22), 0.85)
		var sand_mat: StandardMaterial3D = _material(Color(0.86, 0.76, 0.56), 0.95)
		var curb_mat: StandardMaterial3D = _material(Color(0.75, 0.77, 0.80), 0.8)
		var foul_mat: StandardMaterial3D = _material(Color(0.82, 0.14, 0.14), 0.7)
		_box(parent, Vector3(46.0, 0.04, 1.28), Vector3(-33.0, 0.01, pit_z), runway_col)
		_box(parent, Vector3(46.0, 0.015, 0.05), Vector3(-33.0, 0.03, pit_z - 0.64), line)
		_box(parent, Vector3(46.0, 0.015, 0.05), Vector3(-33.0, 0.03, pit_z + 0.64), line)
		_box(parent, Vector3(0.22, 0.042, 1.28), Vector3(-10.0, 0.012, pit_z), line)      # asse di battuta
		_box(parent, Vector3(0.10, 0.044, 1.28), Vector3(-9.84, 0.012, pit_z), foul_mat) # plastilina
		_box(parent, Vector3(10.4, 0.05, 3.0), Vector3(-3.3, 0.01, pit_z), curb_mat)
		_box(parent, Vector3(10.0, 0.06, 2.75), Vector3(-3.5, 0.012, pit_z), sand_mat)   # fossa: -8.5 .. +1.5
		for m in range(4, 10):
			var mx: float = -10.0 + float(m)
			_box(parent, Vector3(0.05, 0.062, 0.25), Vector3(mx, 0.014, pit_z + 1.48), line)
			var ml: Label3D = Label3D.new()
			ml.text = "%dm" % m
			ml.font_size = 64
			ml.pixel_size = 0.004
			ml.modulate = Color(0.96, 0.96, 0.96)
			ml.position = Vector3(mx, 0.06, pit_z + 1.78)
			ml.rotation_degrees.x = -90.0
			parent.add_child(ml)
	elif kind == "Getto del Peso":
		_build_shot_put(parent, line)
	else:
		# Linee di partenza: una per corsia, sfalsate; orientate di traverso alla corsia.
		for lane in range(1, lanes + 1):
			var pose: Dictionary = TrackGeometry.pose(lane, 0.0)
			var mark: MeshInstance3D = _box(parent, Vector3(0.1, 0.014, w), pose["position"] + Vector3(0.0, 0.008, 0.0), line)
			mark.rotation.y = pose["yaw"]
			_blocks_and_placard(parent, pose["position"], pose["yaw"], lane)
		if kind == "4x100m":
			var zone_mat: StandardMaterial3D = _material(Color(0.95, 0.78, 0.16), 0.7)
			for ex_dist: float in [100.0, 200.0, 300.0]:
				for lane in range(1, lanes + 1):
					for edge: float in [-10.0, 10.0]:
						var zp: Dictionary = TrackGeometry.pose(lane, ex_dist + edge)
						var tick: MeshInstance3D = _box(parent, Vector3(0.08, 0.014, w * 0.9), zp["position"] + Vector3(0.0, 0.009, 0.0), zone_mat)
						tick.rotation.y = zp["yaw"]
	# Traguardo: linea larga sul rettilineo d'arrivo.
	_box(parent, Vector3(0.25, 0.014, width), Vector3(TrackGeometry.FINISH_X, 0.008, (lanes - 1) * w * 0.5), line)


## Blocchi di partenza (guida + due appoggi inclinati) e cartellino col numero di corsia dietro i blocchi, nel sistema
## locale della linea di partenza (x = direzione di corsa, linea a x = 0) posto in `origin` con rotazione `yaw`.
## Le posizioni seguono i punti dei piedi di SetPoseRig (FRONT_FOOT / REAR_FOOT).
static func _blocks_and_placard(parent: Node3D, origin: Vector3, yaw: float, lane: int) -> void:
	var holder: Node3D = Node3D.new()
	holder.position = origin
	holder.rotation.y = yaw
	holder.name = "StartBlocks_L%d" % lane
	holder.add_to_group(START_BLOCKS_GROUP)   # Stadium li nasconde quando l'atleta della corsia taglia il traguardo
	holder.set_meta("lane", lane)
	parent.add_child(holder)
	var metal: StandardMaterial3D = _material(Color(0.55, 0.55, 0.58), 0.4)
	var pad: StandardMaterial3D = _material(Color(0.45, 0.14, 0.1), 0.6)
	_box(holder, Vector3(0.78, 0.035, 0.12), Vector3(-0.69, 0.02, 0.0), metal)                          # guida
	for foot: Vector3 in [SetPoseRig.FRONT_FOOT, SetPoseRig.REAR_FOOT]:
		var p: MeshInstance3D = _box(holder, Vector3(0.025, 0.16, 0.13), Vector3(foot.x - 0.10, 0.11, 0.0), pad)
		p.rotation.z = deg_to_rad(48.0)  # appoggio inclinato: la normale guarda avanti e in alto
	var board: MeshInstance3D = _box(holder, Vector3(0.05, 0.40, 0.28), Vector3(-1.55, 0.2, 0.0), _material(Color(0.38, 0.08, 0.14), 0.7))
	for face: Array in [[Vector3(0.028, 0.0, 0.0), 90.0], [Vector3(-0.028, 0.0, 0.0), -90.0]]:
		var label: Label3D = Label3D.new()
		label.text = str(lane)
		label.font_size = 96
		label.pixel_size = 0.0022
		label.modulate = Color(0.96, 0.96, 0.96)
		label.outline_size = 0
		label.position = face[0]
		label.rotation_degrees.y = face[1]
		board.add_child(label)


## Semicerchio anulare piatto fra i raggi r_in e r_out. `sign` = +1 per la curva 1, -1 per la curva 2.
static func _arc_band(parent: Node3D, center: Vector2, sign: float, r_in: float, r_out: float, y: float, mat: Material) -> void:
	var st: SurfaceTool = SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	st.set_normal(Vector3.UP)
	for i in range(ARC_STEPS):
		var a0: float = PI * float(i) / ARC_STEPS
		var a1: float = PI * float(i + 1) / ARC_STEPS
		var p00: Vector3 = _arc_point(center, sign, r_in, a0, y)
		var p01: Vector3 = _arc_point(center, sign, r_out, a0, y)
		var p10: Vector3 = _arc_point(center, sign, r_in, a1, y)
		var p11: Vector3 = _arc_point(center, sign, r_out, a1, y)
		for p: Vector3 in [p00, p10, p01, p01, p10, p11]:  # senso orario visto dall'alto = faccia superiore
			st.set_normal(Vector3.UP)
			st.add_vertex(p)
	var mi: MeshInstance3D = MeshInstance3D.new()
	mi.mesh = st.commit()
	mi.material_override = mat
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	parent.add_child(mi)


static func _arc_point(center: Vector2, sign: float, r: float, a: float, y: float) -> Vector3:
	return Vector3(center.x + sign * r * sin(a), y, center.y + sign * r * cos(a))


static func _box(parent: Node3D, size: Vector3, pos: Vector3, mat: Material) -> MeshInstance3D:
	var mesh: BoxMesh = BoxMesh.new()
	mesh.size = size
	var mi: MeshInstance3D = MeshInstance3D.new()
	mi.mesh = mesh
	mi.material_override = mat
	mi.position = pos
	parent.add_child(mi)
	return mi


## Prato con le fasce chiare e scure del taglio erba (trama in metri, indipendente dalle UV della scatola).
static func _grass_material() -> StandardMaterial3D:
	var size: int = 64
	var img: Image = Image.create(size, size, false, Image.FORMAT_RGB8)
	for x in range(size):
		var v: float = 1.0 if x < size / 2 else 0.88
		for y in range(size):
			img.set_pixel(x, y, Color(v, v, v))
	img.generate_mipmaps()
	var m: StandardMaterial3D = _material(GRASS_IN, 1.0)
	m.albedo_texture = ImageTexture.create_from_image(img)
	m.uv1_triplanar = true
	m.uv1_world_triplanar = true
	m.uv1_scale = Vector3.ONE / GRASS_STRIPE_PERIOD
	m.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS_ANISOTROPIC
	return m


static func _material(color: Color, roughness: float) -> StandardMaterial3D:
	var m: StandardMaterial3D = StandardMaterial3D.new()
	m.albedo_color = color
	m.roughness = roughness
	return m


## Getto del peso (geometria da ShotPutMotion: stessa fonte di atleta, peso e camere). Terra battuta attorno alla pedana, settore
## d'erba falciata (piu' chiaro del prato interno), pedana in cemento con bordo dipinto, fermapiedi AD ARCO (corda 1,22 m) con il
## bordo interno sul cerchio, linee del settore che partono dal bordo della pedana e archi di distanza centrati sul centro.
## Il disegno si ferma a SECTOR_LENGTH metri (30): il settore vero ne ha 100 ma lungo l'asse la curva 1 e' a ~78 m.
static func _build_shot_put(parent: Node3D, line: StandardMaterial3D) -> void:
	var c: Vector3 = ShotPutMotion.CENTER
	var rc: float = ShotPutMotion.CIRCLE_RADIUS
	var half: float = ShotPutMotion.SECTOR_HALF_ANGLE
	var length: float = ShotPutMotion.SECTOR_LENGTH
	var grass_cut: StandardMaterial3D = _material(Color(0.12, 0.34, 0.15), 1.0)
	var dirt: StandardMaterial3D = _material(Color(0.33, 0.24, 0.15), 1.0)
	var concrete: StandardMaterial3D = _material(Color(0.68, 0.71, 0.76), 0.9)
	var paint: StandardMaterial3D = _material(Color(0.95, 0.95, 0.95), 0.7)
	var board_mat: StandardMaterial3D = _material(Color(0.93, 0.94, 0.96), 0.6)

	# Settore: erba falciata (piano a quota 0, come i piedi dell'atleta) + terra battuta attorno alla pedana.
	_sector_band(parent, c, rc, rc + length, -half, half, 0.0005, grass_cut, 32)
	var dirt_mesh: CylinderMesh = CylinderMesh.new()
	dirt_mesh.top_radius = 3.4
	dirt_mesh.bottom_radius = 3.4
	dirt_mesh.height = 0.05
	dirt_mesh.radial_segments = 40
	var dirt_disc: MeshInstance3D = MeshInstance3D.new()
	dirt_disc.mesh = dirt_mesh
	dirt_disc.material_override = dirt
	dirt_disc.position = Vector3(c.x, -0.025, c.z)
	dirt_disc.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	parent.add_child(dirt_disc)

	# Pedana in cemento (quota ShotPutMotion.CIRCLE_TOP) con il bordo dipinto.
	var pad_mesh: CylinderMesh = CylinderMesh.new()
	pad_mesh.top_radius = rc
	pad_mesh.bottom_radius = rc
	pad_mesh.height = ShotPutMotion.CIRCLE_TOP + 0.05
	pad_mesh.radial_segments = 48
	var pad: MeshInstance3D = MeshInstance3D.new()
	pad.mesh = pad_mesh
	pad.material_override = concrete
	pad.position = Vector3(c.x, ShotPutMotion.CIRCLE_TOP * 0.5 - 0.025, c.z)
	pad.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	parent.add_child(pad)
	_sector_band(parent, c, rc - 0.05, rc, 0.0, TAU, ShotPutMotion.CIRCLE_TOP + 0.001, paint, 48)

	# Fermapiedi: arco largo 0,112 m e alto 0,10 m, bordo interno sul cerchio, centrato sull'asse del settore.
	var board_half: float = asin(ShotPutMotion.STOPBOARD_CHORD * 0.5 / rc)
	_arc_block(parent, c, rc, rc + ShotPutMotion.STOPBOARD_WIDTH, -board_half, board_half, ShotPutMotion.STOPBOARD_HEIGHT, board_mat)

	# Linee del settore (+/-17,46 gradi) dal bordo della pedana, e archi di distanza centrati sul centro (misura dal bordo).
	for sgn: float in [-1.0, 1.0]:
		var ang: float = sgn * half
		var mid: Vector3 = c + ShotPutMotion.dir_at(ang) * (rc + length * 0.5)
		var sec_line: MeshInstance3D = _box(parent, Vector3(length, 0.012, 0.06), Vector3(mid.x, 0.004, mid.z), line)
		sec_line.rotation.y = ang
	for dm: int in range(5, int(length) + 1, 5):
		_sector_band(parent, c, rc + float(dm) - 0.03, rc + float(dm) + 0.03, -half, half, 0.004, line, 24)
		var label_at: Vector3 = c + ShotPutMotion.dir_at(-half - 0.045) * (rc + float(dm))
		var ml: Label3D = Label3D.new()
		ml.text = "%d m" % dm
		ml.font_size = 64
		ml.pixel_size = 0.0045
		ml.modulate = Color(0.96, 0.96, 0.96)
		ml.position = Vector3(label_at.x, 0.012, label_at.z)
		ml.rotation_degrees.x = -90.0
		parent.add_child(ml)


## Settore anulare piatto fra i raggi r0 e r1 e gli angoli a0..a1 (antiorari da +X, vedi ShotPutMotion.dir_at), a quota y.
static func _sector_band(parent: Node3D, center: Vector3, r0: float, r1: float, a0: float, a1: float, y: float, mat: Material, steps: int) -> void:
	var st: SurfaceTool = SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var up: Vector3 = Vector3(0.0, y, 0.0)
	for i in range(steps):
		var aa: float = lerpf(a0, a1, float(i) / steps)
		var ab: float = lerpf(a0, a1, float(i + 1) / steps)
		var p00: Vector3 = center + ShotPutMotion.dir_at(aa) * r0 + up
		var p01: Vector3 = center + ShotPutMotion.dir_at(aa) * r1 + up
		var p10: Vector3 = center + ShotPutMotion.dir_at(ab) * r0 + up
		var p11: Vector3 = center + ShotPutMotion.dir_at(ab) * r1 + up
		_tri_out(st, p00, p01, p10, Vector3.UP)
		_tri_out(st, p10, p01, p11, Vector3.UP)
	var mi: MeshInstance3D = MeshInstance3D.new()
	mi.mesh = st.commit()
	mi.material_override = mat
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	parent.add_child(mi)


## Blocco ad arco (fermapiedi): faccia superiore, pareti interna ed esterna e le due testate, tutte rivolte verso l'esterno.
static func _arc_block(parent: Node3D, center: Vector3, r0: float, r1: float, a0: float, a1: float, height: float, mat: Material) -> void:
	var st: SurfaceTool = SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var steps: int = 12
	var top: Vector3 = Vector3(0.0, height, 0.0)
	for i in range(steps):
		var aa: float = lerpf(a0, a1, float(i) / steps)
		var ab: float = lerpf(a0, a1, float(i + 1) / steps)
		var da: Vector3 = ShotPutMotion.dir_at(aa)
		var db: Vector3 = ShotPutMotion.dir_at(ab)
		var mida: Vector3 = ShotPutMotion.dir_at(0.5 * (aa + ab))
		# superiore
		_tri_out(st, center + da * r0 + top, center + da * r1 + top, center + db * r0 + top, Vector3.UP)
		_tri_out(st, center + db * r0 + top, center + da * r1 + top, center + db * r1 + top, Vector3.UP)
		# esterna (normale = radiale) e interna (normale = -radiale)
		for pair: Array in [[r1, mida], [r0, -mida]]:
			var r: float = pair[0]
			var n: Vector3 = pair[1]
			_tri_out(st, center + da * r, center + da * r + top, center + db * r, n)
			_tri_out(st, center + db * r, center + da * r + top, center + db * r + top, n)
	# testate
	for end: Array in [[a0, -1.0], [a1, 1.0]]:
		var d: Vector3 = ShotPutMotion.dir_at(end[0])
		var tangent: Vector3 = Vector3(d.z, 0.0, -d.x) * float(end[1])    # perpendicolare al raggio (verso gli angoli crescenti), verso l'esterno dell'arco
		_tri_out(st, center + d * r0, center + d * r0 + top, center + d * r1, tangent)
		_tri_out(st, center + d * r1, center + d * r0 + top, center + d * r1 + top, tangent)
	var mi: MeshInstance3D = MeshInstance3D.new()
	mi.mesh = st.commit()
	mi.material_override = mat
	parent.add_child(mi)


## Triangolo con la faccia anteriore verso `outward` (in Godot e' quella oraria: normale = (c - a) x (b - a)).
static func _tri_out(st: SurfaceTool, a: Vector3, b: Vector3, c: Vector3, outward: Vector3) -> void:
	var n: Vector3 = (c - a).cross(b - a)
	if n.dot(outward) < 0.0:
		var tmp: Vector3 = b
		b = c
		c = tmp
		n = -n
	st.set_normal(n.normalized())
	st.add_vertex(a)
	st.set_normal(n.normalized())
	st.add_vertex(b)
	st.set_normal(n.normalized())
	st.add_vertex(c)
