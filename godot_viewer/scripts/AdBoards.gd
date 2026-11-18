class_name AdBoards
extends RefCounted
## VIEW 3D - cartelloni LED a bordo campo (rettilinei, curve) e davanti alle tribune. Sponsor di FANTASIA (grafica
## originale: nessun marchio reale; se uno coincidesse con un'azienda vera, sostituiscilo).
##
## Un cartellone e' un Node3D con origine a terra: la faccia guarda +Z locale, quindi `yaw` lo orienta
## (0 = verso +Z, PI = verso -Z). I materiali sono condivisi (uno per sponsor) per tenere basse le draw call.

const PANEL_W: float = 4.0
const PANEL_H: float = 0.9
const SPONSORS: Array[String] = ["VELOCIA", "SPRINTEX", "MONTALTO", "LUMENIA", "ZEFIRO", "ORBITA", "TRIVELLA", "CAPRIOLA"]
const COLORS: Array[Color] = [
	Color(0.55, 0.08, 0.12), Color(0.06, 0.28, 0.45), Color(0.08, 0.32, 0.20), Color(0.40, 0.20, 0.50),
	Color(0.62, 0.30, 0.05), Color(0.05, 0.30, 0.36), Color(0.45, 0.10, 0.28), Color(0.15, 0.20, 0.50)]

static var _faces: Array[StandardMaterial3D] = []
static var _back: StandardMaterial3D = null


## Fila dritta da x0 a x1 (x0 < x1) alla quota z. Ritorna quanti cartelloni ha messo.
static func row(parent: Node3D, x0: float, x1: float, z: float, yaw: float = 0.0, first: int = 0) -> int:
	var count: int = int(floorf((x1 - x0) / PANEL_W))
	var x_start: float = (x0 + x1) * 0.5 - count * PANEL_W * 0.5
	for i in range(count):
		_panel(parent, Vector3(x_start + (i + 0.5) * PANEL_W, 0.0, z), yaw, first + i)
	return count


## Semicerchio di cartelloni lungo una curva, rivolti verso l'ESTERNO. Stessa convenzione di OvalTrackBuilder._arc_point:
## punto = (centro.x + sign*r*sin(a), centro.y + r*cos(a)), a da 0 a PI.
static func arc(parent: Node3D, center: Vector2, sign: float, radius: float, first: int = 0) -> int:
	var count: int = int(floorf(PI * radius / PANEL_W))
	var step: float = PI / float(count)
	for i in range(count):
		var a: float = (i + 0.5) * step
		var pos: Vector3 = Vector3(center.x + sign * radius * sin(a), 0.0, center.y + radius * cos(a))
		_panel(parent, pos, sign * a, first + i)   # la normale uscente e' (sign*sin a, cos a): yaw = sign*a
	return count


static func _panel(parent: Node3D, pos: Vector3, yaw: float, idx: int) -> void:
	_ensure_materials()
	var k: int = idx % SPONSORS.size()
	var pivot: Node3D = Node3D.new()
	pivot.position = pos
	pivot.rotation.y = yaw
	parent.add_child(pivot)
	_part(pivot, Vector3(PANEL_W - 0.06, PANEL_H, 0.12), Vector3(0.0, PANEL_H * 0.5, 0.0), _back)
	_part(pivot, Vector3(PANEL_W - 0.12, PANEL_H - 0.1, 0.02), Vector3(0.0, PANEL_H * 0.5, 0.065), _faces[k])
	var label: Label3D = Label3D.new()
	label.text = SPONSORS[k]
	label.font_size = 72
	label.pixel_size = 0.0065
	label.shaded = false
	label.double_sided = false
	label.outline_size = 0
	label.position = Vector3(0.0, PANEL_H * 0.5, 0.085)
	pivot.add_child(label)


static func _part(parent: Node3D, size: Vector3, pos: Vector3, mat: Material) -> void:
	var mesh: BoxMesh = BoxMesh.new()
	mesh.size = size
	var mi: MeshInstance3D = MeshInstance3D.new()
	mi.mesh = mesh
	mi.material_override = mat
	mi.position = pos
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	parent.add_child(mi)


static func _ensure_materials() -> void:
	if not _faces.is_empty():
		return
	_back = StandardMaterial3D.new()
	_back.albedo_color = Color(0.10, 0.10, 0.12)
	_back.roughness = 0.8
	for c: Color in COLORS:
		var m: StandardMaterial3D = StandardMaterial3D.new()
		m.albedo_color = c
		m.roughness = 0.5
		m.emission_enabled = true        # schermo LED: si vede anche di notte
		m.emission = c
		m.emission_energy_multiplier = 0.7
		_faces.append(m)
