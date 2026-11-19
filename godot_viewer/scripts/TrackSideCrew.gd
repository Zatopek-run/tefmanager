class_name TrackSideCrew
extends RefCounted
## VIEW 3D - personale a bordo pista: fotografi vicino al traguardo e giudici d'arrivo al tavolo. Persone vere: stesso modello con
## scheletro dei corridori (Quaternius, CC0), vestiti ricavati dalla mesh (`CharacterDress`), capelli, animazioni in loop
## (fotografi in posa di scatto, giudici seduti o in piedi a parlare) e attrezzatura (macchine con teleobiettivo, tavolo,
## computer, sedie). Solo vista: non influisce mai su tempi o ordine.
##
## Posti scelti per NON coprire gli atleti: i giudici stanno a z >= 14 (la camera del traguardo, il carrello e il ralenti guardano
## la corsia 8 da fuori: una figura piu' vicina la nasconderebbe); i fotografi dentro il campo stanno dietro i cartelloni (z = -3.5).
## Solo per le corse in pista: nei concorsi la camera del salto in lungo sta proprio li' (-12; 3,4; -3,5).
## Convenzione: il modello guarda +Z; `yaw` = PI lo gira verso -Z (verso la pista, per chi sta oltre z = 9).

const CHARACTER_PATH: String = "res://assets/athlete/Superhero_Male_FullBody.gltf"
const CHARACTER_PATH_F: String = "res://assets/athlete/Superhero_Female_FullBody.gltf"
const MODEL_HEIGHT: float = 1.8196   # altezza del modello base a riposo (m): le misure sotto sono in queste unita'

## Posizione delle mani (a meta') nella posa «Pistol_Idle» (misurata sul modello): li' va la macchina fotografica.
const HANDS_MID: Vector3 = Vector3(-0.13, 1.37, 0.33)
## Posizione del bacino da seduti («Sitting_Idle»): 0,54 m di altezza e 0,33 m dietro l'origine.
const SIT_PELVIS: Vector3 = Vector3(0.0, 0.54, -0.33)

const VEST_JUDGE: Color = Color(0.95, 0.52, 0.07)      # pettorina arancione dei giudici
const VEST_PRESS: Color = Color(0.86, 0.93, 0.12)      # pettorina giallo fluo dei fotografi
const POLO: Color = Color(0.93, 0.94, 0.96)
const TROUSERS_DARK: Color = Color(0.11, 0.12, 0.17)
const PRESS_JACKETS: Array[Color] = [Color(0.08, 0.08, 0.1), Color(0.14, 0.2, 0.32), Color(0.2, 0.22, 0.2), Color(0.32, 0.12, 0.1)]
const PRESS_TROUSERS: Array[Color] = [Color(0.13, 0.15, 0.22), Color(0.3, 0.27, 0.2), Color(0.1, 0.1, 0.12)]

const TABLE_POS: Vector3 = Vector3(-4.5, 0.0, 15.2)
const TABLE_SIZE: Vector2 = Vector2(8.0, 1.0)         # lunghezza (x) e profondita' (z)
const TABLE_TOP_Y: float = 0.76
const PRINT_ROW_Y: float = 0.69      # altezza (in altezze corporee) del centro della scritta sulla schiena
const PRINT_HEIGHT: float = 0.034    # altezza massima del testo (in altezze corporee)
const PRINT_MAX_WIDTH: float = 0.12  # larghezza massima: oltre ±0,06 la schiena gira di lato e il testo si taglia

## Texture del testo stampato (canale alfa) e rettangolo (x, y, larghezza, altezza) per ciascuna scritta; si ricreano a ogni build().
static var _prints: Dictionary = {}


static func build(parent: Node3D) -> void:
	var rng: RandomNumberGenerator = RandomNumberGenerator.new()
	rng.seed = 2024   # deterministico: stessa scena a ogni gara
	_prints = {"STAMPA": _print_texture(parent, "STAMPA"), "GIUDICE": _print_texture(parent, "GIUDICE")}
	var n: int = 0
	# Fotografi dentro il campo, dietro i cartelloni, nel tratto d'arrivo (guardano la pista, verso +z).
	for x: float in [-16.0, -11.0, -6.5, -2.5]:
		_photographer(parent, Vector3(x + rng.randf_range(-0.6, 0.6), 0.0, -3.7), 0.0, rng, n)
		n += 1
	# Fotografi appena oltre il traguardo, fuori dalla pista (la curva si allontana da z = 9,15).
	for p: Vector2 in [Vector2(4.5, 12.5), Vector2(7.0, 13.5), Vector2(9.5, 12.8)]:
		_photographer(parent, Vector3(p.x, 0.0, p.y), PI, rng, n)
		n += 1
	_judges_table(parent, rng)


# --- giudici -------------------------------------------------------------------------------------

## Tavolo della giuria con tre giudici seduti (computer e fogli davanti) e due in piedi ai lati che parlano.
static func _judges_table(parent: Node3D, rng: RandomNumberGenerator) -> void:
	_table(parent, TABLE_POS)
	var seat_z: float = TABLE_POS.z + TABLE_SIZE.y * 0.5 + 0.12 + 0.50   # il bacino sta a 0,33 m dietro l'origine del modello
	for i in range(3):
		var x: float = TABLE_POS.x - 2.1 + float(i) * 2.1 + rng.randf_range(-0.15, 0.15)
		_chair(parent, Vector3(x, 0.0, seat_z))
		var p: Dictionary = _spawn(parent, Vector3(x, 0.0, seat_z - SIT_PELVIS.z * -1.0), PI, rng, "judge_s%d" % i, "Sitting_Idle")
		_dress_judge(p)
		_laptop(parent, Vector3(x, TABLE_TOP_Y, TABLE_POS.z + 0.05), rng.randf_range(-0.12, 0.12))
		_papers(parent, Vector3(x + 0.55, TABLE_TOP_Y, TABLE_POS.z + 0.15), rng)
	for i in range(2):
		var sx: float = TABLE_POS.x + (-4.9 if i == 0 else 4.6)
		var p2: Dictionary = _spawn(parent, Vector3(sx, 0.0, TABLE_POS.z + 1.5), PI + (0.35 if i == 0 else -0.35), rng, "judge_p%d" % i, "Idle_Talking")
		_dress_judge(p2)


static func _dress_judge(p: Dictionary) -> void:
	var sk: Skeleton3D = p["skeleton"]
	var body: MeshInstance3D = p["body"]
	var y0: float = p["y0"]
	var h: float = p["h"]
	CharacterDress.add_cloth(sk, body, y0, h, Vector3(0.115, 0.045, 0.60), TROUSERS_DARK, 0.007)                      # pantaloni lunghi
	CharacterDress.add_cloth(sk, body, y0, h, Vector3(0.21, 0.57, 0.83), POLO, 0.006)                                  # polo a maniche corte
	var pr: Dictionary = _prints["GIUDICE"]
	CharacterDress.add_cloth(sk, body, y0, h, Vector3(0.125, 0.56, 0.80), VEST_JUDGE, 0.013, 0.8,
		{"tex": pr["tex"], "back": pr["rect"], "color": Color(0.05, 0.05, 0.06)})                                       # pettorina con scritta
	CharacterDress.add_cloth(sk, body, y0, h, Vector3(1.0, -1.0, 0.08), Color(0.17, 0.17, 0.19), 0.03, 0.55)          # scarpe (gonfie: arrotondano le dita)


static func _table(parent: Node3D, pos: Vector3) -> void:
	var cloth: Color = Color(0.74, 0.77, 0.83)
	var top: MeshInstance3D = _box(parent, Vector3(TABLE_SIZE.x, 0.05, TABLE_SIZE.y), pos + Vector3(0.0, TABLE_TOP_Y, 0.0), cloth, 0.7)
	top.name = "JudgeTable"
	# gonnellino blu sul lato della pista e ai fianchi
	var skirt: Color = Color(0.2, 0.36, 0.78)
	_box(parent, Vector3(TABLE_SIZE.x, 0.5, 0.02), pos + Vector3(0.0, TABLE_TOP_Y - 0.28, -TABLE_SIZE.y * 0.5 - 0.005), skirt, 0.9)
	for dx: float in [-TABLE_SIZE.x * 0.5 + 0.05, TABLE_SIZE.x * 0.5 - 0.05]:
		_box(parent, Vector3(0.06, TABLE_TOP_Y - 0.02, TABLE_SIZE.y - 0.1), pos + Vector3(dx, (TABLE_TOP_Y - 0.02) * 0.5, 0.0), Color(0.45, 0.45, 0.5), 0.5, 0.6)
	# monitor del fotofinish sul lato sinistro del tavolo
	var mon_pos: Vector3 = pos + Vector3(-TABLE_SIZE.x * 0.5 + 0.9, TABLE_TOP_Y, 0.05)
	_box(parent, Vector3(0.28, 0.02, 0.2), mon_pos + Vector3(0.0, 0.02, 0.0), Color(0.08, 0.08, 0.1), 0.5)
	_box(parent, Vector3(0.04, 0.22, 0.04), mon_pos + Vector3(0.0, 0.13, 0.0), Color(0.08, 0.08, 0.1), 0.5)
	var screen: MeshInstance3D = _box(parent, Vector3(0.62, 0.38, 0.03), mon_pos + Vector3(0.0, 0.44, 0.0), Color(0.04, 0.05, 0.08), 0.3)
	screen.rotation.x = -0.12   # inclinato all'indietro, schermo verso i giudici (+z)
	_emissive_plane(screen, Vector2(0.56, 0.32), Color(0.35, 0.65, 0.95), 0.016)


static func _chair(parent: Node3D, pos: Vector3) -> void:
	var dark: Color = Color(0.1, 0.1, 0.12)
	_box(parent, Vector3(0.46, 0.06, 0.46), pos + Vector3(0.0, 0.47, 0.0), dark, 0.8)                       # seduta
	_box(parent, Vector3(0.44, 0.5, 0.05), pos + Vector3(0.0, 0.78, 0.22), dark, 0.8)                       # schienale (alle spalle: +z)
	var post: MeshInstance3D = MeshInstance3D.new()
	var pm: CylinderMesh = CylinderMesh.new()
	pm.top_radius = 0.025
	pm.bottom_radius = 0.025
	pm.height = 0.4
	pm.material = _mat(Color(0.5, 0.5, 0.55), 0.4, 0.7)
	post.mesh = pm
	post.position = pos + Vector3(0.0, 0.24, 0.0)
	parent.add_child(post)
	for k in range(5):
		var a: float = float(k) * TAU / 5.0
		var leg: MeshInstance3D = _box(parent, Vector3(0.28, 0.03, 0.04), pos + Vector3(cos(a) * 0.14, 0.03, sin(a) * 0.14), Color(0.35, 0.35, 0.4), 0.5, 0.6)
		leg.rotation.y = -a


static func _laptop(parent: Node3D, pos: Vector3, yaw: float) -> void:
	var pivot: Node3D = Node3D.new()
	pivot.position = pos
	pivot.rotation.y = yaw
	parent.add_child(pivot)
	_box(pivot, Vector3(0.34, 0.02, 0.23), Vector3(0.0, 0.01, 0.0), Color(0.55, 0.56, 0.6), 0.4, 0.6)
	# schermo verso chi siede (+z), inclinato all'indietro
	var lid: MeshInstance3D = _box(pivot, Vector3(0.34, 0.22, 0.012), Vector3(0.0, 0.12, -0.115), Color(0.55, 0.56, 0.6), 0.4, 0.6)
	lid.rotation.x = -0.28
	_emissive_plane(lid, Vector2(0.31, 0.19), Color(0.4, 0.6, 0.9), 0.0065)


static func _papers(parent: Node3D, pos: Vector3, rng: RandomNumberGenerator) -> void:
	for k in range(3):
		var sheet: MeshInstance3D = _box(parent, Vector3(0.21, 0.004, 0.297), pos + Vector3(rng.randf_range(-0.04, 0.04), 0.003 + float(k) * 0.004, rng.randf_range(-0.03, 0.03)), Color(0.97, 0.97, 0.95), 0.9)
		sheet.rotation.y = rng.randf_range(-0.25, 0.25)


# --- fotografi -----------------------------------------------------------------------------------

static func _photographer(parent: Node3D, pos: Vector3, yaw: float, rng: RandomNumberGenerator, idx: int) -> void:
	var p: Dictionary = _spawn(parent, pos, yaw, rng, "press_%d" % idx, "Pistol_Idle")
	var sk: Skeleton3D = p["skeleton"]
	var body: MeshInstance3D = p["body"]
	var y0: float = p["y0"]
	var h: float = p["h"]
	var jacket: Color = PRESS_JACKETS[rng.randi() % PRESS_JACKETS.size()]
	CharacterDress.add_cloth(sk, body, y0, h, Vector3(0.115, 0.045, 0.58), PRESS_TROUSERS[rng.randi() % PRESS_TROUSERS.size()], 0.007)   # pantaloni
	CharacterDress.add_cloth(sk, body, y0, h, Vector3(0.42, 0.52, 0.83), jacket, 0.007)                                                  # giacca a maniche lunghe
	var pr: Dictionary = _prints["STAMPA"]
	CharacterDress.add_cloth(sk, body, y0, h, Vector3(0.125, 0.56, 0.79), VEST_PRESS, 0.014, 0.8,
		{"tex": pr["tex"], "back": pr["rect"], "color": Color(0.05, 0.05, 0.06)})                                         # pettorina con scritta
	CharacterDress.add_cloth(sk, body, y0, h, Vector3(1.0, -1.0, 0.08), Color(0.17, 0.17, 0.19), 0.03, 0.55)                           # scarpe (gonfie: arrotondano le dita)
	# Macchina con teleobiettivo tenuta con due mani all'altezza del petto, puntata verso la pista (+z locale).
	var root: Node3D = p["root"]
	var s: float = p["scale"]
	var gear: Node3D = _camera_gear(rng)
	gear.position = HANDS_MID * s
	root.add_child(gear)


## Corpo macchina + obiettivo (nero o bianco, lungo o corto) + paraluce. Origine sulle mani, l'obiettivo punta a +z.
static func _camera_gear(rng: RandomNumberGenerator) -> Node3D:
	var g: Node3D = Node3D.new()
	var black: Color = Color(0.05, 0.05, 0.06)
	_box(g, Vector3(0.15, 0.1, 0.07), Vector3(0.0, 0.0, -0.02), black, 0.5, 0.3)                # corpo
	_box(g, Vector3(0.05, 0.03, 0.05), Vector3(0.0, 0.065, -0.03), black, 0.5, 0.3)             # pentaprisma
	_box(g, Vector3(0.04, 0.11, 0.05), Vector3(0.055, -0.015, 0.0), Color(0.08, 0.08, 0.09), 0.9)   # impugnatura
	var white_tele: bool = rng.randf() < 0.45
	var length: float = rng.randf_range(0.34, 0.46) if white_tele else rng.randf_range(0.16, 0.24)
	var radius: float = 0.052 if white_tele else 0.036
	var barrel: Color = Color(0.86, 0.87, 0.88) if white_tele else Color(0.09, 0.09, 0.1)
	var lens: MeshInstance3D = MeshInstance3D.new()
	var cm: CylinderMesh = CylinderMesh.new()
	cm.top_radius = radius
	cm.bottom_radius = radius
	cm.height = length
	cm.radial_segments = 20
	cm.material = _mat(barrel, 0.35, 0.1)
	lens.mesh = cm
	lens.rotation.x = PI * 0.5
	lens.position = Vector3(0.0, 0.0, 0.015 + length * 0.5)
	g.add_child(lens)
	var ring: MeshInstance3D = MeshInstance3D.new()
	var rm: CylinderMesh = CylinderMesh.new()
	rm.top_radius = radius + 0.006
	rm.bottom_radius = radius + 0.006
	rm.height = 0.03
	rm.material = _mat(Color(0.04, 0.04, 0.05), 0.6)
	ring.mesh = rm
	ring.rotation.x = PI * 0.5
	ring.position = Vector3(0.0, 0.0, 0.015 + length * 0.35)
	g.add_child(ring)
	var hood: MeshInstance3D = MeshInstance3D.new()
	var hm: CylinderMesh = CylinderMesh.new()
	hm.top_radius = radius + 0.016
	hm.bottom_radius = radius + 0.004
	hm.height = 0.07
	hm.material = _mat(Color(0.05, 0.05, 0.06), 0.7)
	hood.mesh = hm
	hood.rotation.x = PI * 0.5
	hood.position = Vector3(0.0, 0.0, 0.015 + length + 0.03)
	g.add_child(hood)
	var glass: MeshInstance3D = MeshInstance3D.new()
	var gm: CylinderMesh = CylinderMesh.new()
	gm.top_radius = radius - 0.006
	gm.bottom_radius = radius - 0.006
	gm.height = 0.004
	gm.material = _mat(Color(0.06, 0.1, 0.2), 0.05, 0.9)
	glass.mesh = gm
	glass.rotation.x = PI * 0.5
	glass.position = Vector3(0.0, 0.0, 0.015 + length)
	g.add_child(glass)
	return g


# --- persone -------------------------------------------------------------------------------------

## Istanzia una persona: modello, pelle, capelli, altezza e animazione in loop (partenza casuale per non muoverli in coro).
## Ritorna {root, model, skeleton, body, y0, h, scale}; i vestiti li aggiunge chi chiama (dipendono dal ruolo).
static func _spawn(parent: Node3D, pos: Vector3, yaw: float, rng: RandomNumberGenerator, key: String, anim: StringName) -> Dictionary:
	var female: bool = rng.randf() < 0.38
	var gender: String = "F" if female else "M"
	var root: Node3D = Node3D.new()
	root.position = pos
	root.rotation.y = yaw
	root.add_to_group(&"crew")
	parent.add_child(root)
	var model: Node3D = (load(CHARACTER_PATH_F if female else CHARACTER_PATH) as PackedScene).instantiate() as Node3D
	root.add_child(model)
	var sk: Skeleton3D = model.find_child("Skeleton3D", true, false) as Skeleton3D
	var body: MeshInstance3D = CharacterDress.find_body_mesh(sk)
	CharacterDress.apply_skin(body, gender, rng.randi() % 4)
	var ext: Vector2 = CharacterDress.body_extent(body)
	CharacterDress.attach_hair(sk, gender, key)
	var target: float = rng.randf_range(1.58, 1.74) if female else rng.randf_range(1.68, 1.89)
	var s: float = target / ext.y
	model.scale = Vector3.ONE * s

	var player: AnimationPlayer = AnimationPlayer.new()
	model.add_child(player)
	player.add_animation_library(&"", CharacterDress.animation_library())
	var clip: Animation = player.get_animation(anim)
	if clip.loop_mode == Animation.LOOP_NONE:
		clip.loop_mode = Animation.LOOP_LINEAR
	player.speed_scale = rng.randf_range(0.85, 1.1)
	player.play(anim)
	player.seek(rng.randf() * clip.length, true)
	return {"root": root, "model": model, "skeleton": sk, "body": body, "y0": ext.x, "h": ext.y, "scale": s}


## Testo da stampare sulla pettorina: un SubViewport trasparente con una Label, disegnato una volta sola (UPDATE_ONCE) e usato come
## texture dallo shader del capo. Ritorna {tex, rect}: rect = (x centro, y centro, larghezza, altezza) in altezze corporee.
static func _print_texture(parent: Node3D, text: String) -> Dictionary:
	var size: Vector2i = Vector2i(text.length() * 56 + 24, 100)
	var vp: SubViewport = SubViewport.new()
	vp.size = size
	vp.transparent_bg = true
	vp.disable_3d = true
	vp.render_target_update_mode = SubViewport.UPDATE_ONCE
	var label: Label = Label.new()
	label.text = text
	label.size = Vector2(size)
	label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	var font: SystemFont = SystemFont.new()
	font.font_names = PackedStringArray(["Bahnschrift", "Segoe UI", "Arial", "DejaVu Sans"])
	font.font_weight = 800
	label.add_theme_font_override("font", font)
	label.add_theme_font_size_override("font_size", 76)
	label.add_theme_color_override("font_color", Color.WHITE)   # conta solo l'alfa: il colore dell'inchiostro lo da' lo shader
	vp.add_child(label)
	parent.add_child(vp)
	var aspect: float = float(size.x) / float(size.y)
	var h: float = minf(PRINT_HEIGHT, PRINT_MAX_WIDTH / aspect)
	return {"tex": vp.get_texture(), "rect": Vector4(0.0, PRINT_ROW_Y, h * aspect, h)}


# --- forme semplici --------------------------------------------------------------------------------

static func _emissive_plane(parent: Node3D, size: Vector2, color: Color, z: float) -> void:
	var quad: QuadMesh = QuadMesh.new()
	quad.size = size
	var m: StandardMaterial3D = StandardMaterial3D.new()
	m.albedo_color = color.darkened(0.3)
	m.emission_enabled = true
	m.emission = color
	m.emission_energy_multiplier = 0.9
	m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	quad.material = m
	var mi: MeshInstance3D = MeshInstance3D.new()
	mi.mesh = quad
	mi.position = Vector3(0.0, 0.0, z)
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	parent.add_child(mi)


static func _box(parent: Node3D, size: Vector3, pos: Vector3, color: Color, rough: float = 0.9, metal: float = 0.0) -> MeshInstance3D:
	var mesh: BoxMesh = BoxMesh.new()
	mesh.size = size
	var mi: MeshInstance3D = MeshInstance3D.new()
	mi.mesh = mesh
	mi.material_override = _mat(color, rough, metal)
	mi.position = pos
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	parent.add_child(mi)
	return mi


static func _mat(color: Color, rough: float = 0.9, metal: float = 0.0) -> StandardMaterial3D:
	var m: StandardMaterial3D = StandardMaterial3D.new()
	m.albedo_color = color
	m.roughness = rough
	m.metallic = metal
	return m
