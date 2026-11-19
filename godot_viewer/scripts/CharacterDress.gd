class_name CharacterDress
extends RefCounted
## VIEW 3D - vestiario condiviso dei personaggi (corridori in `RunnerView`, comparse in `TrackSideCrew`): pelle, acconciature,
## capi ricavati dalla mesh del corpo e libreria di animazioni. Modelli e animazioni Quaternius (CC0), vedi assets/athlete/CREDITS.md.
## Convenzione: il modello guarda +Z; stessi 65 ossa per corpo, capelli e capi (la skin si lega per nome).

const ANIMATION_PATH: String = "res://assets/athlete/UAL1_Standard.glb"
const SKIN_LIGHT_PATH: String = "res://assets/athlete/T_Superhero_Male_Light.png"
const SKIN_DARK_PATH: String = "res://assets/athlete/T_Superhero_Male_Dark.png"
const SKIN_LIGHT_PATH_F: String = "res://assets/athlete/T_Superhero_Female_Light_BaseColor.png"
const SKIN_DARK_PATH_F: String = "res://assets/athlete/T_Superhero_Female_Dark_BaseColor.png"
const HAIR_PATHS: Array[String] = [
	"res://assets/athlete/Hair_Buzzed.gltf",
	"res://assets/athlete/Hair_SimpleParted.gltf",
]
const HAIR_PATHS_F: Array[String] = [
	"res://assets/athlete/Hair_Long.gltf",
	"res://assets/athlete/Hair_Buns.gltf",
]
const HAIR_TONES: Array[Color] = [
	Color(0.05, 0.04, 0.035), Color(0.2, 0.11, 0.06), Color(0.42, 0.27, 0.12), Color(0.8, 0.62, 0.3)]
const SKIN_TINTS: Array[Color] = [Color(1, 1, 1), Color(0.82, 0.68, 0.56), Color(1, 1, 1), Color(0.8, 0.72, 0.68)]

static var _animation_library: AnimationLibrary = null
static var _cloth_shader_cache: Shader = null
static var _print_shader_cache: Shader = null


## Libreria di animazioni condivisa (si carica una volta sola).
static func animation_library() -> AnimationLibrary:
	if _animation_library == null:
		var ual: Node = (load(ANIMATION_PATH) as PackedScene).instantiate()
		var source: AnimationPlayer = ual.find_child("AnimationPlayer", true, false) as AnimationPlayer
		_animation_library = source.get_animation_library(&"")
		ual.free()
	return _animation_library


static func find_body_mesh(skeleton: Skeleton3D) -> MeshInstance3D:
	for name_try: String in ["Superhero_Female", "SuperHero_Male"]:
		var n: Node = skeleton.get_node_or_null(name_try)
		if n is MeshInstance3D:
			return n as MeshInstance3D
	for child: Node in skeleton.get_children():
		if child is MeshInstance3D and not child.name in ["Eyebrows", "Eyes"]:
			return child as MeshInstance3D
	return null


## Texture e tinta della pelle: `tone` 0..3 (0-1 chiara, 2-3 scura).
static func apply_skin(body: MeshInstance3D, gender: String, tone: int) -> void:
	var skin: StandardMaterial3D = body.get_active_material(0).duplicate() as StandardMaterial3D
	var light_tex: String = SKIN_LIGHT_PATH_F if gender == "F" else SKIN_LIGHT_PATH
	var dark_tex: String = SKIN_DARK_PATH_F if gender == "F" else SKIN_DARK_PATH
	skin.albedo_texture = load(light_tex if tone < 2 else dark_tex) as Texture2D
	skin.albedo_color = SKIN_TINTS[tone]
	body.set_surface_override_material(0, skin)


## (y minima, altezza) del corpo a riposo, in unita' del modello.
static func body_extent(body: MeshInstance3D) -> Vector2:
	var verts: PackedVector3Array = body.mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
	var min_y: float = INF
	var max_y: float = -INF
	for v: Vector3 in verts:
		min_y = minf(min_y, v.y)
		max_y = maxf(max_y, v.y)
	return Vector2(min_y, max_y - min_y)


## Aggiunge un capo ricavato dalla mesh del corpo: stessi vertici/pesi (quindi stesse ossa), gonfiati lungo
## la normale. Ogni vertice porta in UV2 la sua posizione a riposo (x, y in altezze corporee) e lo shader
## scarta i pixel fuori da `bounds` = (|x| max, y min, y max): il bordo e' netto anche se la mesh ha pochi triangoli.
## Stampa sulla schiena (opzionale): `print_tex` e' una texture con il testo nel canale alfa, `print_rect` = (x centro, y centro,
## larghezza, altezza) in altezze corporee. E' stampata SUL tessuto (usa le stesse coordinate a riposo del capo), quindi segue la
## schiena e la sua curvatura invece di restare sospesa come farebbe un'etichetta 3D.
static func add_cloth(skeleton: Skeleton3D, body: MeshInstance3D, base_y: float, height: float, bounds: Vector3, color: Color, inflate: float, roughness: float = 0.8, print_tex: Texture2D = null, print_rect: Vector4 = Vector4(0.0, 0.7, 0.19, 0.05), print_color: Color = Color(0.05, 0.05, 0.06)) -> void:
	var src: Mesh = body.mesh
	var arrays: Array = src.surface_get_arrays(0)
	var verts: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var normals: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL]
	var index: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]

	var grown: PackedVector3Array = verts.duplicate()
	var rel: PackedVector2Array = PackedVector2Array()
	rel.resize(verts.size())
	for i in range(verts.size()):
		grown[i] = verts[i] + normals[i] * inflate
		rel[i] = Vector2(verts[i].x / height, (verts[i].y - base_y) / height)

	var kept: PackedInt32Array = PackedInt32Array()
	for t in range(0, index.size(), 3):
		var y0: float = rel[index[t]].y
		var y1: float = rel[index[t + 1]].y
		var y2: float = rel[index[t + 2]].y
		if minf(y0, minf(y1, y2)) <= bounds.z and maxf(y0, maxf(y1, y2)) >= bounds.y:
			kept.append(index[t])
			kept.append(index[t + 1])
			kept.append(index[t + 2])
	if kept.is_empty():
		push_warning("CharacterDress: nessun triangolo per il capo %s" % str(color))
		return

	arrays[Mesh.ARRAY_VERTEX] = grown
	arrays[Mesh.ARRAY_INDEX] = kept
	arrays[Mesh.ARRAY_TEX_UV2] = rel
	if print_tex != null:
		# Colore del vertice: r = 1 se sta sulla schiena, cioe' dietro il centro del busto (z a riposo minore della media dei
		# vertici del capo; il modello guarda +z). Non si usa la normale: ai fianchi cambia segno e taglierebbe il testo.
		# Serve allo shader per stampare solo dietro (davanti e dietro condividono le stesse x, y).
		var z_sum: float = 0.0
		var z_n: int = 0
		for i in range(verts.size()):
			if rel[i].y >= bounds.y and rel[i].y <= bounds.z and absf(rel[i].x) <= bounds.x:
				z_sum += verts[i].z
				z_n += 1
		var z_center: float = z_sum / float(maxi(z_n, 1))
		var back: PackedColorArray = PackedColorArray()
		back.resize(verts.size())
		for i in range(verts.size()):
			back[i] = Color(1.0 if verts[i].z < z_center else 0.0, 0.0, 0.0, 1.0)
		arrays[Mesh.ARRAY_COLOR] = back
	for ci: int in [Mesh.ARRAY_CUSTOM0, Mesh.ARRAY_CUSTOM1, Mesh.ARRAY_CUSTOM2, Mesh.ARRAY_CUSTOM3]:
		arrays[ci] = null
	var mesh: ArrayMesh = ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays, [], {},
		src.surface_get_format(0) & Mesh.ARRAY_FLAG_USE_8_BONE_WEIGHTS)

	var mat: ShaderMaterial = ShaderMaterial.new()
	mat.shader = cloth_shader() if print_tex == null else print_shader()
	if print_tex != null:
		mat.set_shader_parameter("print_tex", print_tex)
		mat.set_shader_parameter("print_rect", print_rect)
		mat.set_shader_parameter("print_color", print_color)
	mat.set_shader_parameter("color", color)
	mat.set_shader_parameter("bounds", bounds)
	mat.set_shader_parameter("rough", roughness)
	mesh.surface_set_material(0, mat)

	var mi: MeshInstance3D = MeshInstance3D.new()
	mi.mesh = mesh
	mi.skin = body.skin
	skeleton.add_child(mi)  # figlio dello scheletro: segue le stesse ossa del corpo


static func cloth_shader() -> Shader:
	if _cloth_shader_cache == null:
		_cloth_shader_cache = Shader.new()
		_cloth_shader_cache.code = """
shader_type spatial;
uniform vec4 color : source_color = vec4(1.0);
uniform vec3 bounds = vec3(0.115, 0.6, 0.82); // |x| max, y min, y max (altezze corporee)
uniform float rough = 0.8;
varying vec2 rel;
void vertex() { rel = UV2; }
void fragment() {
	if (abs(rel.x) > bounds.x || rel.y < bounds.y || rel.y > bounds.z) { discard; }
	ALBEDO = color.rgb;
	ROUGHNESS = rough;
}
"""
	return _cloth_shader_cache


## Come `cloth_shader`, con in piu' una stampa (testo) sulla schiena: la texture e' campionata con le coordinate a riposo del capo.
## Dalla schiena, con il modello che guarda +z, la destra dello schermo e' -x: la u del testo cresce al calare di x.
static func print_shader() -> Shader:
	if _print_shader_cache == null:
		_print_shader_cache = Shader.new()
		_print_shader_cache.code = """
shader_type spatial;
uniform vec4 color : source_color = vec4(1.0);
uniform vec3 bounds = vec3(0.115, 0.6, 0.82); // |x| max, y min, y max (altezze corporee)
uniform float rough = 0.8;
uniform sampler2D print_tex : filter_linear, repeat_disable;
uniform vec4 print_rect = vec4(0.0, 0.7, 0.19, 0.05); // x centro, y centro, larghezza, altezza (altezze corporee)
uniform vec4 print_color : source_color = vec4(0.05, 0.05, 0.06, 1.0);
varying vec2 rel;
varying float back;
void vertex() { rel = UV2; back = COLOR.r; }
void fragment() {
	if (abs(rel.x) > bounds.x || rel.y < bounds.y || rel.y > bounds.z) { discard; }
	vec3 col = color.rgb;
	if (back > 0.5) {
		vec2 uv = vec2(0.5 - (rel.x - print_rect.x) / print_rect.z, 0.5 - (rel.y - print_rect.y) / print_rect.w);
		if (uv.x > 0.0 && uv.x < 1.0 && uv.y > 0.0 && uv.y < 1.0) {
			col = mix(col, print_color.rgb, texture(print_tex, uv).a * 0.92);
		}
	}
	ALBEDO = col;
	ROUGHNESS = rough;
}
"""
	return _print_shader_cache


## Acconciatura scelta in modo deterministico da `key` (stessa persona = stessi capelli).
static func attach_hair(skeleton: Skeleton3D, gender: String, key: String) -> void:
	var pool: Array[String] = HAIR_PATHS_F if gender == "F" else HAIR_PATHS
	var path: String = pool[absi(hash(key + "hair")) % pool.size()]
	var scene: Node = (load(path) as PackedScene).instantiate()
	var hair: MeshInstance3D = scene.find_children("*", "MeshInstance3D", true, false)[0] as MeshInstance3D
	hair.get_parent().remove_child(hair)
	scene.free()
	skeleton.add_child(hair)  # stesse 65 ossa del corpo: la skin si lega per nome
	var mat: StandardMaterial3D = hair.get_active_material(0).duplicate() as StandardMaterial3D
	mat.albedo_color = HAIR_TONES[absi(hash(key + "shade")) % HAIR_TONES.size()]
	hair.set_surface_override_material(0, mat)
