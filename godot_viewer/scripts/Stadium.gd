extends Node3D
## VIEW 3D - scena principale: luce, ambiente, pista, tribune, corridori. Il HUD e' una scena separata.
##
## Avvio: la gara 1 del DB (o `--race=N` dopo `--` sulla riga di comando) parte da sola dopo 1.5 s.
## Tasti: Spazio = (ri)parti, 1/2/4/8 = velocita' 1x/2x/4x/8x, Esc = salta alla fine.
## `--autoquit` (dopo `--`): a gara finita chiude l'app dopo AUTOQUIT_DELAY secondi.

const LANE_WIDTH: float = 1.22
const LANES: int = 8
const AUTO_START_DELAY: float = 0.5
const CROWD_TILE_METERS: float = 32.0  # lato in metri di una ripetizione della texture della folla
const AUTOQUIT_DELAY: float = 3.0  # con --autoquit: pausa sul risultato prima di chiudere

const HUD_SCENE: PackedScene = preload("res://scenes/HUD.tscn")

@onready var _sun: DirectionalLight3D = $Sun
@onready var _track_root: Node3D = $Track
@onready var _runners_root: Node3D = $Runners

var _race_id: int = 1
var _autoquit: bool = false      # --autoquit: chiude l'app a fine gara (usato dal gioco PyQt)
var _quit_scheduled: bool = false
var _world_kind: String = ""       # "100m" (rettilineo) oppure "oval": quale scena e' costruita
var _crowd_material: StandardMaterial3D = null
var _field_marker: MeshInstance3D = null
var _shot_mesh: MeshInstance3D = null


func _ready() -> void:
	Engine.max_fps = 60
	_configure_sun()
	_configure_environment()
	add_child(HUD_SCENE.instantiate())

	RaceController.race_loaded.connect(_on_race_loaded)
	RaceController.runner_finished.connect(_on_runner_finished)
	RaceController.race_finished.connect(_on_race_finished)
	_race_id = _race_id_from_args()
	_autoquit = OS.get_cmdline_user_args().has("--autoquit")
	if RaceController.load_race(_race_id):
		get_tree().create_timer(AUTO_START_DELAY).timeout.connect(RaceController.start)
	elif _autoquit:
		push_error("Stadium: gara %d non caricabile: esco con errore." % _race_id)
		get_tree().quit(1)  # il gioco PyQt se ne accorge e usa la vista interna


func _process(_delta: float) -> void:
	if _field_marker != null:
		var is_sp: bool = RaceController.event_kind == "Getto del Peso"
		var m_x: float = RaceController.field_landed_mark
		_field_marker.visible = RaceController.is_field(RaceController.event_kind) and m_x > (-40.9 if is_sp else -9.9)
		if _field_marker.visible:
			_field_marker.position = Vector3(m_x, 0.25, -36.0 if is_sp else -14.0)
			var mat: StandardMaterial3D = _field_marker.material_override as StandardMaterial3D
			if mat != null:
				mat.albedo_color = Color(0.92, 0.22, 0.22) if RaceController.field_landed_foul else Color(0.18, 0.88, 0.56)
	if _shot_mesh != null:
		_shot_mesh.visible = RaceController.event_kind == "Getto del Peso" and RaceController.shot_visible
		if _shot_mesh.visible:
			_shot_mesh.position = RaceController.shot_pos
	if _autoquit and not _quit_scheduled and RaceController.state == RaceController.State.FINISHED:
		_quit_scheduled = true
		get_tree().create_timer(AUTOQUIT_DELAY).timeout.connect(get_tree().quit)


func _unhandled_key_input(event: InputEvent) -> void:
	var key: InputEventKey = event as InputEventKey
	if key == null or not key.pressed or key.echo:
		return
	match key.keycode:
		KEY_SPACE:
			if RaceController.load_race(_race_id):
				RaceController.start()
		KEY_1: RaceController.time_scale = 1.0
		KEY_2: RaceController.time_scale = 2.0
		KEY_4: RaceController.time_scale = 4.0
		KEY_8: RaceController.time_scale = 8.0
		KEY_ESCAPE: RaceController.skip_to_end()
		KEY_H:
			var hud: Node = get_node_or_null("HUD")
			if hud != null:
				hud.set("ranking_visible", not bool(hud.get("ranking_visible")))


func _race_id_from_args() -> int:
	for arg: String in OS.get_cmdline_user_args():
		if arg.begins_with("--race="):
			return int(arg.get_slice("=", 1))
	return 1


## Dopo il traguardo gli atleti proseguono sulla pista: i blocchi (e il cartellino di corsia) non devono restare sulla loro
## traiettoria, altrimenti ci passano attraverso. Spariscono quando taglia il traguardo l'atleta di quella corsia.
func _on_runner_finished(runner: RunnerData) -> void:
	for holder: Node in get_tree().get_nodes_in_group(OvalTrackBuilder.START_BLOCKS_GROUP):
		if int(holder.get_meta("lane", -1)) == runner.lane:
			(holder as Node3D).visible = false


## A gara conclusa non ne resta nessuno (anche quelli dei ritirati, che non tagliano mai il traguardo).
func _on_race_finished(_results: Array[RunnerData]) -> void:
	for holder: Node in get_tree().get_nodes_in_group(OvalTrackBuilder.START_BLOCKS_GROUP):
		(holder as Node3D).visible = false


func _on_race_loaded(runners: Array[RunnerData], _info: Dictionary) -> void:
	_rebuild_world(RaceController.event_kind)
	for holder: Node in get_tree().get_nodes_in_group(OvalTrackBuilder.START_BLOCKS_GROUP):
		(holder as Node3D).visible = true   # nuova gara sulla stessa pista: la scena non viene ricostruita
	for child: Node in _runners_root.get_children():
		child.queue_free()
	if _field_marker != null:
		_field_marker.queue_free()
		_field_marker = null
	if _shot_mesh != null:
		_shot_mesh.queue_free()
		_shot_mesh = null
	if RaceController.is_field(RaceController.event_kind):
		var marker_mesh: CylinderMesh = CylinderMesh.new()
		marker_mesh.top_radius = 0.06
		marker_mesh.bottom_radius = 0.06
		marker_mesh.height = 0.50
		_field_marker = MeshInstance3D.new()
		_field_marker.mesh = marker_mesh
		_field_marker.material_override = _flat(Color(0.18, 0.88, 0.56), 0.5)
		_field_marker.visible = false
		_runners_root.add_child(_field_marker)
		if RaceController.event_kind == "Getto del Peso":
			var ball: SphereMesh = SphereMesh.new()
			ball.radius = 0.16
			ball.height = 0.32
			var ball_mat: StandardMaterial3D = StandardMaterial3D.new()
			ball_mat.albedo_color = Color(0.86, 0.89, 0.94)
			ball_mat.metallic = 0.45
			ball_mat.roughness = 0.22
			ball.material = ball_mat
			_shot_mesh = MeshInstance3D.new()
			_shot_mesh.mesh = ball
			_shot_mesh.visible = false
			_runners_root.add_child(_shot_mesh)
	var relay: bool = RaceController.is_relay(RaceController.event_kind)
	var leg_len: float = RaceMotion.race_distance(RaceController.event_kind) * 0.25
	for r: RunnerData in runners:
		if relay:
			var parts: PackedStringArray = r.athlete_name.split(" / ", false)
			for leg in range(4):
				var vname: String = parts[leg].strip_edges() if parts.size() == 4 else "%s #%d" % [r.team_name, leg + 1]
				var view: RunnerView = RunnerView.new()
				view.name = "Runner_L%d_Leg%d" % [r.lane, leg + 1]
				_runners_root.add_child(view)
				view.setup(r, leg, leg_len, vname)
		else:
			var view: RunnerView = RunnerView.new()
			view.name = "Runner_L%d" % r.lane
			_runners_root.add_child(view)
			view.setup(r)


# --- luce e ambiente ----------------------------------------------------------------------------

func _configure_sun() -> void:
	# Serata con i fari accesi (come nelle dirette di riferimento): luce principale dall'alto, fredda, con ombre morbide.
	_sun.rotation_degrees = Vector3(-62.0, -30.0, 0.0)
	_sun.light_color = Color(0.82, 0.88, 1.0)
	_sun.light_energy = 0.95
	_sun.shadow_enabled = true
	_sun.shadow_bias = 0.03
	_sun.shadow_blur = 1.5
	_sun.directional_shadow_mode = DirectionalLight3D.SHADOW_PARALLEL_4_SPLITS
	_sun.directional_shadow_max_distance = 90.0  # basta a coprire lo scorrimento della telecamera


func _configure_environment() -> void:
	var sky_material: ProceduralSkyMaterial = ProceduralSkyMaterial.new()
	sky_material.sky_top_color = Color(0.015, 0.03, 0.09)
	sky_material.sky_horizon_color = Color(0.09, 0.12, 0.26)
	sky_material.ground_horizon_color = Color(0.05, 0.07, 0.14)
	var sky: Sky = Sky.new()
	sky.sky_material = sky_material

	var env: Environment = Environment.new()
	env.background_mode = Environment.BG_SKY
	env.sky = sky
	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	env.ambient_light_energy = 0.55
	env.tonemap_mode = Environment.TONE_MAPPER_ACES
	env.ssao_enabled = true        # solo Forward+/Mobile; ignorato da Compatibility
	env.glow_enabled = true        # "bloom" da diretta TV 2010
	env.glow_intensity = 0.95
	env.glow_bloom = 0.08
	env.glow_hdr_threshold = 1.0
	env.adjustment_enabled = true
	env.adjustment_contrast = 1.08
	env.adjustment_saturation = 1.12

	var world: WorldEnvironment = WorldEnvironment.new()
	world.environment = env
	add_child(world)


# --- geometria ----------------------------------------------------------------------------------

## Costruisce la pista per la gara: sempre l'ovale; i 100m aggiungono il rettilineo prolungato con blocchi e cartellini.
## Se e' gia' quella giusta, non fa nulla.
func _rebuild_world(kind: String) -> void:
	if kind == _world_kind:
		return
	_world_kind = kind
	for child: Node in _track_root.get_children():
		_track_root.remove_child(child)
		child.queue_free()
	OvalTrackBuilder.build(_track_root, kind)
	# Tribune dietro il rettilineo d'arrivo (dietro la camera) e dietro quello opposto (sfondo). Nei 100m quella opposta e'
	# vicina (fa da sfondo ai primi piani come nel riferimento); nei 400m resta lontana: le camere ci girano intorno.
	var mid_x: float = -TrackGeometry.STRAIGHT * 0.5
	var back_z: float = -92.0 if kind == "100m" else -125.0
	_build_stand_block(mid_x, 220.0, 50.0, 1.0, [-130.0, -42.0, 45.0])
	_build_stand_block(mid_x, 220.0, back_z, -1.0, [-130.0, -42.0, 45.0])
	_build_curve_stands(mid_x, 110.0, 50.0, back_z)
	_build_track_lights()
	if not RaceController.is_field(kind):
		TrackSideCrew.build(_track_root)   # nei concorsi la camera del lungo sta dove stanno i fotografi
	_sun.directional_shadow_max_distance = 160.0


## Fari sopra la pista (senza ombre: le ombre le fa la luce principale): illuminano il tartan come i fari dello stadio.
func _build_track_lights() -> void:
	for x: float in [-95.0, -48.0, 0.0]:
		for z: float in [6.0, -70.0]:
			var light: OmniLight3D = OmniLight3D.new()
			light.position = Vector3(x, 26.0, z)
			light.light_color = Color(1.0, 0.96, 0.88)
			light.light_energy = 2.4
			light.omni_range = 75.0
			light.shadow_enabled = false
			_track_root.add_child(light)


## Gradinata a gradoni che si allontana da z_start nella direzione `dir` (+1/-1), con torri faro dietro di essa.
func _build_stand_block(center_x: float, length: float, z_start: float, dir: float, lamp_xs: Array) -> void:
	if _crowd_material == null:
		_crowd_material = StandardMaterial3D.new()
		_crowd_material.albedo_texture = _crowd_texture()
		_crowd_material.uv1_triplanar = true
		_crowd_material.uv1_world_triplanar = true       # mappatura in metri: gli spettatori restano ~0,5 m
		_crowd_material.uv1_scale = Vector3.ONE / CROWD_TILE_METERS
		_crowd_material.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS_ANISOTROPIC
		_crowd_material.roughness = 1.0

	for step in range(6):
		var rise: float = 0.7 * (step + 1)
		_add_box(_track_root, Vector3(length, rise, 1.8), Vector3(center_x, rise * 0.5, z_start + dir * step * 1.8), _crowd_material)

	# Cartelloni davanti alla prima fila, rivolti verso la pista (dir = +1: tribuna a z positivi, guarda -Z).
	AdBoards.row(_track_root, center_x - length * 0.5, center_x + length * 0.5, z_start - dir * 1.3, PI if dir > 0.0 else 0.0)

	# Torri faro con testa emissiva: alimentano il bloom (glow_hdr_threshold = 1.0).
	var lamp: StandardMaterial3D = StandardMaterial3D.new()
	lamp.albedo_color = Color(1.0, 0.97, 0.88)
	lamp.emission_enabled = true
	lamp.emission = Color(1.0, 0.95, 0.8)
	lamp.emission_energy_multiplier = 6.0
	for x: float in lamp_xs:
		_add_box(_track_root, Vector3(0.5, 22.0, 0.5), Vector3(x, 11.0, z_start + dir * 14.0), _flat(Color(0.3, 0.3, 0.32), 0.6))
		_add_box(_track_root, Vector3(4.0, 1.4, 0.4), Vector3(x, 22.5, z_start + dir * 13.6), lamp)


## Gradinate dietro le due curve: un arco attorno a ciascun centro di curva che si aggancia alle estremita' delle due
## tribune dritte (home_z e back_z), cosi' lo stadio non ha le "teste" aperte. Raggio ricavato dai due punti di
## aggancio: ~110 m nei 400m (aggancio a ~1 m); nei 100m la tribuna opposta e' piu' vicina e resta un buco di ~14 m.
## Tutte le camere stanno dentro il raggio (la piu' lontana a ~91 m dal centro curva).
func _build_curve_stands(mid_x: float, half_len: float, home_z: float, back_z: float) -> void:
	var cz: float = -TrackGeometry.R1
	for side: float in [1.0, -1.0]:                       # +1 = curva 1 (x = 0), -1 = curva 2 (x = -STRAIGHT)
		var cx: float = 0.0 if side > 0.0 else -TrackGeometry.STRAIGHT
		var dx: float = absf(mid_x + side * half_len - cx)
		var radius: float = 0.5 * (Vector2(dx, home_z - cz).length() + Vector2(dx, back_z - cz).length())
		var a0: float = acos(clampf((home_z - cz) / radius, -1.0, 1.0))
		var a1: float = acos(clampf((back_z - cz) / radius, -1.0, 1.0))
		_build_stand_arc(Vector2(cx, cz), side, radius, a0, a1)
		AdBoards.arc(_track_root, Vector2(cx, cz), side, radius - 0.4, int(side * 5.0 + 5.0), a0, a1, true)


## Gradoni lungo un arco (stessa convenzione di OvalTrackBuilder._arc_point), tutti in una MultiMesh: ~300 scatole
## unitarie scalate e ruotate, una sola draw call. Ogni gradone e' alto 0,7 m piu' del precedente, come nelle tribune dritte.
func _build_stand_arc(center: Vector2, sign: float, radius: float, a0: float, a1: float) -> void:
	const STEPS: int = 6
	const DEPTH: float = 1.8
	var segments: int = maxi(1, int(ceilf((a1 - a0) * radius / 3.5)))
	var da: float = (a1 - a0) / float(segments)
	var mesh: BoxMesh = BoxMesh.new()
	mesh.size = Vector3.ONE
	mesh.material = _crowd_material
	var mm: MultiMesh = MultiMesh.new()
	mm.transform_format = MultiMesh.TRANSFORM_3D
	mm.mesh = mesh
	mm.instance_count = segments * STEPS
	for i in range(segments):
		var a: float = a0 + (i + 0.5) * da
		for step in range(STEPS):
			var r: float = radius + (step + 0.5) * DEPTH
			var rise: float = 0.7 * (step + 1)
			var chord: float = da * r * 1.06                     # 6% in piu': niente fessure tra segmenti
			var basis: Basis = Basis(Vector3.UP, sign * a).scaled_local(Vector3(chord, rise, DEPTH))
			var pos: Vector3 = Vector3(center.x + sign * r * sin(a), rise * 0.5, center.y + r * cos(a))
			mm.set_instance_transform(i * STEPS + step, Transform3D(basis, pos))
	var inst: MultiMeshInstance3D = MultiMeshInstance3D.new()
	inst.multimesh = mm
	_track_root.add_child(inst)
	# Un faro dietro l'arco, a meta' (testa emissiva come quelle delle tribune dritte).
	var mid: float = 0.5 * (a0 + a1)
	var rl: float = radius + STEPS * DEPTH + 6.0
	var lamp: StandardMaterial3D = StandardMaterial3D.new()
	lamp.albedo_color = Color(1.0, 0.97, 0.88)
	lamp.emission_enabled = true
	lamp.emission = Color(1.0, 0.95, 0.8)
	lamp.emission_energy_multiplier = 6.0
	var base: Vector3 = Vector3(center.x + sign * rl * sin(mid), 0.0, center.y + rl * cos(mid))
	_add_box(_track_root, Vector3(0.5, 22.0, 0.5), base + Vector3(0.0, 11.0, 0.0), _flat(Color(0.3, 0.3, 0.32), 0.6))
	_add_box(_track_root, Vector3(4.0, 1.4, 0.4), base + Vector3(0.0, 22.5, 0.0), lamp)


## Folla procedurale: file di spettatori (testa tonda + busto colorato) su fondo scuro, deterministica.
func _crowd_texture() -> ImageTexture:
	var size: int = 512
	var img: Image = Image.create(size, size, false, Image.FORMAT_RGB8)
	img.fill(Color(0.08, 0.12, 0.32))   # seggiolini blu dello stadio
	var rng: RandomNumberGenerator = RandomNumberGenerator.new()
	rng.seed = 2010
	var shirts: Array[Color] = [
		Color(0.75, 0.15, 0.15), Color(0.15, 0.3, 0.7), Color(0.9, 0.9, 0.88), Color(0.95, 0.75, 0.15),
		Color(0.2, 0.55, 0.3), Color(0.12, 0.12, 0.15), Color(0.85, 0.4, 0.1), Color(0.55, 0.25, 0.6)]
	var skins: Array[Color] = [
		Color(0.94, 0.76, 0.64), Color(0.82, 0.6, 0.45), Color(0.62, 0.42, 0.3), Color(0.38, 0.25, 0.17)]
	var row_h: int = 9
	var col_w: int = 8
	for row in range(0, size, row_h):
		for col in range(0, size, col_w):
			var x: int = col + rng.randi_range(0, 1)
			var y: int = row + rng.randi_range(0, 1)
			var shirt: Color = shirts[rng.randi() % shirts.size()].darkened(rng.randf_range(0.0, 0.35))
			img.fill_rect(Rect2i(x, y + 4, 6, 5), shirt)                                # busto
			img.fill_rect(Rect2i(x + 1, y + 1, 4, 3), skins[rng.randi() % skins.size()])  # testa
	img.generate_mipmaps()
	return ImageTexture.create_from_image(img)


func _flat(color: Color, roughness: float) -> StandardMaterial3D:
	var m: StandardMaterial3D = StandardMaterial3D.new()
	m.albedo_color = color
	m.roughness = roughness
	return m


func _add_box(parent: Node3D, size: Vector3, pos: Vector3, mat: Material) -> void:
	var mesh: BoxMesh = BoxMesh.new()
	mesh.size = size
	var mi: MeshInstance3D = MeshInstance3D.new()
	mi.mesh = mesh
	mi.material_override = mat
	mi.position = pos
	parent.add_child(mi)
