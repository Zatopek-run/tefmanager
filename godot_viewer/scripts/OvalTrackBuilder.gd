class_name OvalTrackBuilder
extends RefCounted
## VIEW 3D - costruisce la pista ovale da 400 m (tartan, linee di corsia, linee di partenza sfalsate, traguardo)
## a partire da TrackGeometry: il disegno e il percorso dei corridori usano gli stessi numeri e non possono
## divergere. Tutto e' geometria procedurale (nessun asset).

const TARTAN: Color = Color(0.17, 0.31, 0.60)   # 100m: tartan blu come nel riferimento (stadio di Roma)
const TARTAN_400M: Color = Color(0.45, 0.42, 0.78)  # 400m: tartan viola/lavanda come nel riferimento (Parigi 2024)
const CHUTE_BEHIND_START: float = 3.0       # 100m: il rettilineo si prolunga oltre la linea di partenza
const LINE: Color = Color(0.95, 0.95, 0.95)
const GRASS_IN: Color = Color(0.09, 0.27, 0.12)
const GRASS_OUT: Color = Color(0.16, 0.4, 0.18)
const ARC_STEPS: int = 64


static func build(parent: Node3D, kind: String = "400m") -> void:
	var s: float = TrackGeometry.STRAIGHT
	var r1: float = TrackGeometry.R1
	var w: float = TrackGeometry.LANE_WIDTH
	var lanes: int = TrackGeometry.LANES
	var tartan: StandardMaterial3D = _material(TARTAN if kind == "100m" else TARTAN_400M, 0.9)
	var line: StandardMaterial3D = _material(LINE, 0.7)

	# Prato: un unico grande piano sotto la pista (interno e dintorni).
	_box(parent, Vector3(360.0, 0.1, 300.0), Vector3(-s * 0.5, -0.1, -r1 - 10.0), _material(GRASS_IN, 1.0))

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
		# Pedana circolare in cemento (centro x = -42, z = -36), fermapiedi e settore 34.92° verso +X.
		var sp_z: float = -36.0
		var cx: float = -42.0
		var concrete: StandardMaterial3D = _material(Color(0.68, 0.71, 0.76), 0.9)
		var rim_mat: StandardMaterial3D = _material(Color(0.92, 0.93, 0.95), 0.7)
		var circle_mesh: CylinderMesh = CylinderMesh.new()
		circle_mesh.top_radius = 1.07
		circle_mesh.bottom_radius = 1.07
		circle_mesh.height = 0.04
		var circle: MeshInstance3D = MeshInstance3D.new()
		circle.mesh = circle_mesh
		circle.material_override = concrete
		circle.position = Vector3(cx, 0.01, sp_z)
		parent.add_child(circle)
		_box(parent, Vector3(0.14, 0.12, 1.22), Vector3(cx + 1.07, 0.06, sp_z), rim_mat)  # fermapiedi
		# Linee del settore (34.92° -> +/-17.46°) lunghe 26 m
		for sgn: float in [-1.0, 1.0]:
			var ang: float = sgn * deg_to_rad(17.46)
			var seg_len: float = 26.0
			var sec_line: MeshInstance3D = _box(
				parent,
				Vector3(seg_len, 0.012, 0.06),
				Vector3(cx + 1.07 + cos(ang) * seg_len * 0.5, 0.008, sp_z + sin(ang) * seg_len * 0.5),
				line
			)
			sec_line.rotation.y = -ang
		for dm: int in [12, 14, 16, 18, 20, 22]:
			var mx: float = cx + 1.07 + float(dm)
			var half_w: float = float(dm) * tan(deg_to_rad(17.46))
			_box(parent, Vector3(0.05, 0.012, half_w * 2.0), Vector3(mx, 0.008, sp_z), line)
			var ml: Label3D = Label3D.new()
			ml.text = "%dm" % dm
			ml.font_size = 64
			ml.pixel_size = 0.0045
			ml.modulate = Color(0.96, 0.96, 0.96)
			ml.position = Vector3(mx, 0.05, sp_z + half_w + 0.55)
			ml.rotation_degrees.x = -90.0
			parent.add_child(ml)
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


static func _material(color: Color, roughness: float) -> StandardMaterial3D:
	var m: StandardMaterial3D = StandardMaterial3D.new()
	m.albedo_color = color
	m.roughness = roughness
	return m
