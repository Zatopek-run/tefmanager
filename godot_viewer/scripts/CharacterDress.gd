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
## Stampa (opzionale, `print_opts`): disegno STAMPATO SUL tessuto (usa le stesse coordinate a riposo del capo), quindi segue il busto e
## la sua curvatura invece di restare sospeso come farebbe un'etichetta 3D. Chiavi:
##   "tex"       Texture2D del disegno;
##   "back"      Vector4 (x centro, y centro, larghezza, altezza) in altezze corporee del disegno sulla schiena (assente = niente);
##   "front"     idem sul davanti (assente = niente);
##   "tex_color" true: si usano i colori della texture (foglio bianco, cifre scure); false (default): conta solo l'alfa e
##               l'inchiostro e' "color" (testo su tessuto, es. STAMPA);
##   "color"     inchiostro per la modalita' solo-alfa.
static func add_cloth(skeleton: Skeleton3D, body: MeshInstance3D, base_y: float, height: float, bounds: Vector3, color: Color, inflate: float, roughness: float = 0.8, print_opts: Dictionary = {}) -> void:
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
	var has_print: bool = not print_opts.is_empty()
	if has_print:
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
	mat.shader = print_shader() if has_print else cloth_shader()
	if has_print:
		mat.set_shader_parameter("print_tex", print_opts["tex"])
		mat.set_shader_parameter("back_rect", print_opts.get("back", Vector4.ZERO))
		mat.set_shader_parameter("front_rect", print_opts.get("front", Vector4.ZERO))
		mat.set_shader_parameter("print_color", print_opts.get("color", Color(0.05, 0.05, 0.06)))
		mat.set_shader_parameter("tex_color", 1.0 if bool(print_opts.get("tex_color", false)) else 0.0)
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


## Come `cloth_shader`, con in piu' una stampa sul davanti e/o sulla schiena: la texture e' campionata con le coordinate a riposo
## del capo. Dalla schiena, con il modello che guarda +z, la destra dello schermo e' -x (la u cresce al calare di x); dal davanti
## e' +x (la u cresce al crescere di x). `rect.z == 0` = nessuna stampa su quel lato.
static func print_shader() -> Shader:
	if _print_shader_cache == null:
		_print_shader_cache = Shader.new()
		_print_shader_cache.code = """
shader_type spatial;
uniform vec4 color : source_color = vec4(1.0);
uniform vec3 bounds = vec3(0.115, 0.6, 0.82); // |x| max, y min, y max (altezze corporee)
uniform float rough = 0.8;
uniform sampler2D print_tex : filter_linear, repeat_disable;
uniform vec4 back_rect = vec4(0.0);   // x centro, y centro, larghezza, altezza (altezze corporee)
uniform vec4 front_rect = vec4(0.0);
uniform vec4 print_color : source_color = vec4(0.05, 0.05, 0.06, 1.0);
uniform float tex_color = 0.0;        // 1 = colori della texture (foglio), 0 = solo alfa con l'inchiostro print_color
varying vec2 rel;
varying float back;
void vertex() { rel = UV2; back = COLOR.r; }
void fragment() {
	if (abs(rel.x) > bounds.x || rel.y < bounds.y || rel.y > bounds.z) { discard; }
	vec3 col = color.rgb;
	vec4 tex = vec4(0.0);
	vec4 r = back > 0.5 ? back_rect : front_rect;
	if (r.z > 0.0) {
		float dx = (rel.x - r.x) / r.z;
		vec2 uv = vec2(0.5 + (back > 0.5 ? -dx : dx), 0.5 - (rel.y - r.y) / r.w);
		if (uv.x > 0.0 && uv.x < 1.0 && uv.y > 0.0 && uv.y < 1.0) { tex = texture(print_tex, uv); }
	}
	vec3 ink = tex_color > 0.5 ? tex.rgb : print_color.rgb;
	float a = tex_color > 0.5 ? tex.a : tex.a * 0.92;
	col = mix(col, ink, a);
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


# --- scarpe -------------------------------------------------------------------------------------------

const SHOE_INFLATE: float = 0.005       # la tomaia sta appena fuori dalla pelle del piede (unita' del modello, ~1,8 per l'altezza)
const SHOE_SOLE: float = 0.011          # spessore della suola, compreso nel volume del piede: la suola poggia dove poggiava la pelle
const SHOE_SECTIONS: int = 22
const SHOE_ARC: int = 8
const SHOE_LACE: Color = Color(0.95, 0.95, 0.93)


## Scarpe da atletica per i due piedi: tomaia con striscia obliqua di colore `accent` (la squadra), linguetta con lacci, suola.
## Si adattano alla mesh del piede del modello (maschile o femminile) e seguono l'osso del piede (BoneAttachment3D). La suola
## sta nel volume del piede (la parte piu' bassa e' quella della pelle): le quote di ShotPutMotion (caviglia da terra) restano valide.
static func add_shoes(skeleton: Skeleton3D, body: MeshInstance3D, upper: Color, accent: Color, sole: Color) -> void:
	var verts: PackedVector3Array = body.mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
	var mat: StandardMaterial3D = StandardMaterial3D.new()
	mat.vertex_color_use_as_albedo = true
	mat.albedo_color = Color.WHITE
	mat.roughness = 0.5
	for side: float in [1.0, -1.0]:   # +1 = sinistro (x > 0 nello spazio scheletro: il modello guarda +Z)
		var bone_name: String = "foot_l" if side > 0.0 else "foot_r"
		var mesh: ArrayMesh = _shoe_mesh(verts, side, upper, accent, sole)
		if mesh == null:
			continue
		mesh.surface_set_material(0, mat)
		var attach: BoneAttachment3D = BoneAttachment3D.new()
		attach.bone_name = bone_name
		skeleton.add_child(attach)
		var mi: MeshInstance3D = MeshInstance3D.new()
		mi.mesh = mesh
		mi.transform = skeleton.get_bone_global_rest(skeleton.find_bone(bone_name)).affine_inverse()   # mesh in spazio scheletro a riposo
		attach.add_child(mi)


static func _shoe_mesh(verts: PackedVector3Array, side: float, upper: Color, accent: Color, sole: Color) -> ArrayMesh:
	# Profilo del piede dalla mesh del corpo: per fette lungo z, quota massima e larghezza (solo vertici bassi di quel piede).
	var z0: float = INF
	var z1: float = -INF
	var ymin: float = INF
	var foot: Array[Vector3] = []
	for v: Vector3 in verts:
		if v.x * side > 0.04 and v.y < 0.112 and v.z > -0.2 and v.z < 0.2:
			foot.append(v)
			z0 = minf(z0, v.z)
			z1 = maxf(z1, v.z)
			ymin = minf(ymin, v.y)
	if foot.size() < 20:
		return null
	const BINS: int = 12
	var top: Array[float] = []
	var xlo: Array[float] = []
	var xhi: Array[float] = []
	for b in range(BINS):
		top.append(ymin + 0.02)
		xlo.append(INF)
		xhi.append(-INF)
	for v: Vector3 in foot:
		var b: int = clampi(int((v.z - z0) / (z1 - z0) * BINS), 0, BINS - 1)
		top[b] = maxf(top[b], v.y)
		xlo[b] = minf(xlo[b], v.x * side)
		xhi[b] = maxf(xhi[b], v.x * side)
	for b in range(BINS):                      # fette senza vertici: prendono quelle vicine
		if xlo[b] == INF:
			xlo[b] = xlo[maxi(b - 1, 0)]
			xhi[b] = xhi[maxi(b - 1, 0)]
	for _pass in range(2):                     # leviga il profilo
		for arr: Array in [top, xlo, xhi]:
			var prev: Array = arr.duplicate()
			for b in range(BINS):
				arr[b] = (float(prev[maxi(b - 1, 0)]) + 2.0 * float(prev[b]) + float(prev[mini(b + 1, BINS - 1)])) / 4.0
	var z_start: float = z0 - 0.004
	var z_end: float = z1 + 0.004
	var rings: Array = []          # per fetta: Array di {p, n, c}
	var centers: Array[Vector3] = []
	for k in range(SHOE_SECTIONS):
		var t: float = float(k) / float(SHOE_SECTIONS - 1)
		var z: float = lerpf(z_start, z_end, t)
		var f: float = clampf((z - z0) / (z1 - z0) * BINS - 0.5, 0.0, BINS - 1.0)
		var b0: int = int(floor(f))
		var b1: int = mini(b0 + 1, BINS - 1)
		var fr: float = f - float(b0)
		var cx: float = lerpf(0.5 * (xlo[b0] + xhi[b0]), 0.5 * (xlo[b1] + xhi[b1]), fr)
		var half_w: float = lerpf(0.5 * (xhi[b0] - xlo[b0]), 0.5 * (xhi[b1] - xlo[b1]), fr) + SHOE_INFLATE
		var tp: float = lerpf(top[b0], top[b1], fr) + SHOE_INFLATE
		var sc: float = 1.0                      # punta e tallone arrotondati
		if k == 0: sc = 0.78
		elif k == 1: sc = 0.94
		elif k == SHOE_SECTIONS - 1: sc = 0.42
		elif k == SHOE_SECTIONS - 2: sc = 0.78
		elif k == SHOE_SECTIONS - 3: sc = 0.93
		var yb: float = ymin - 0.001
		var h: float = maxf(tp - yb, 0.03) * sc
		rings.append(_shoe_ring(side, cx, z, yb, h, half_w * sc, t, upper, accent, sole))
		centers.append(Vector3(side * cx, yb + 0.45 * h, z))
	var st: SurfaceTool = SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	for k in range(SHOE_SECTIONS - 1):
		var ra: Array = rings[k]
		var rb: Array = rings[k + 1]
		var mid: Vector3 = 0.5 * (centers[k] + centers[k + 1])
		for m in range(ra.size()):
			var m2: int = (m + 1) % ra.size()
			_shoe_tri(st, [ra[m], rb[m], ra[m2]], mid)
			_shoe_tri(st, [ra[m2], rb[m], rb[m2]], mid)
	for end: Array in [[0, -1.0], [SHOE_SECTIONS - 1, 1.0]]:      # tappi alle due estremita'
		var ring: Array = rings[end[0]]
		var cen: Dictionary = {"p": centers[end[0]], "n": Vector3(0.0, 0.0, float(end[1])), "c": upper}
		for m in range(ring.size()):
			_shoe_tri(st, [cen, ring[m], ring[(m + 1) % ring.size()]], centers[end[0]] + Vector3(0.0, 0.0, float(end[1])))
	return st.commit()


## Una sezione trasversale della scarpa: suola piatta, fianchi verticali, sopra una mezza ellisse. Colori per vertice:
## suola, tomaia, striscia obliqua di squadra sui fianchi, linguetta con lacci sul collo del piede, linguetta del tallone.
static func _shoe_ring(side: float, cx: float, z: float, yb: float, h: float, w: float, t: float, upper: Color, accent: Color, sole: Color) -> Array:
	var pts: Array = []       # (u, y, suola?) con u = scostamento laterale dal centro del piede
	pts.append([-w, yb, true])
	pts.append([-w, yb + SHOE_SOLE, true])
	pts.append([-w, yb + SHOE_SOLE + 0.0005, false])
	pts.append([-w, yb + 0.3 * h, false])
	for j in range(1, SHOE_ARC):
		var phi: float = PI * (1.0 - float(j) / float(SHOE_ARC))
		pts.append([w * cos(phi), yb + 0.3 * h + 0.7 * h * sin(phi), false])
	pts.append([w, yb + 0.3 * h, false])
	pts.append([w, yb + SHOE_SOLE + 0.0005, false])
	pts.append([w, yb + SHOE_SOLE, true])
	pts.append([w, yb, true])
	var center_y: float = yb + 0.45 * h
	var ring: Array = []
	for p: Array in pts:
		var u: float = p[0]
		var y: float = p[1]
		var yrel: float = clampf((y - yb) / maxf(h, 0.001), 0.0, 1.0)
		var col: Color = sole if bool(p[2]) else upper
		if not bool(p[2]):
			if absf(u) > 0.7 * w and yrel < 0.8 and absf(t - (0.30 + 0.24 * yrel)) < 0.07:
				col = accent                                   # striscia obliqua sui fianchi
			elif t < 0.13 and yrel > 0.5:
				col = accent                                   # linguetta del tallone
			elif yrel > 0.78 and absf(u) < 0.34 * w and t > 0.2 and t < 0.64:
				col = SHOE_LACE                                # lacci sul collo del piede
		var n: Vector3 = Vector3(u, y - center_y, 0.0)
		n = Vector3(side * n.x, n.y, 0.0).normalized() if n.length() > 0.0001 else Vector3.UP
		ring.append({"p": Vector3(side * cx + side * u, y, z), "n": n, "c": col})
	return ring


## Triangolo con la faccia anteriore verso l'esterno rispetto a `inside` (in Godot e' quella oraria).
static func _shoe_tri(st: SurfaceTool, v: Array, inside: Vector3) -> void:
	var a: Dictionary = v[0]
	var b: Dictionary = v[1]
	var c: Dictionary = v[2]
	var geo: Vector3 = ((c["p"] as Vector3) - (a["p"] as Vector3)).cross((b["p"] as Vector3) - (a["p"] as Vector3))
	var centroid: Vector3 = ((a["p"] as Vector3) + (b["p"] as Vector3) + (c["p"] as Vector3)) / 3.0
	if geo.dot(centroid - inside) < 0.0:
		var tmp: Dictionary = b
		b = c
		c = tmp
	for d: Dictionary in [a, b, c]:
		st.set_color(d["c"])
		st.set_normal(d["n"])
		st.add_vertex(d["p"])
