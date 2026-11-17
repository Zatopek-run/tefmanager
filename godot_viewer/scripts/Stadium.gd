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


func _ready() -> void:
	Engine.max_fps = 60
	_configure_sun()
	_configure_environment()
	add_child(HUD_SCENE.instantiate())

	RaceController.race_loaded.connect(_on_race_loaded)
	_race_id = _race_id_from_args()
	_autoquit = OS.get_cmdline_user_args().has("--autoquit")
	if RaceController.load_race(_race_id):
		get_tree().create_timer(AUTO_START_DELAY).timeout.connect(RaceController.start)
	elif _autoquit:
		push_error("Stadium: gara %d non caricabile: esco con errore." % _race_id)
		get_tree().quit(1)  # il gioco PyQt se ne accorge e usa la vista interna


func _process(_delta: float) -> void:
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


func _on_race_loaded(runners: Array[RunnerData], _info: Dictionary) -> void:
	_rebuild_world(RaceController.event_kind)
	for child: Node in _runners_root.get_children():
		child.queue_free()
	for r: RunnerData in runners:
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
	_build_track_lights()
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

	# Torri faro con testa emissiva: alimentano il bloom (glow_hdr_threshold = 1.0).
	var lamp: StandardMaterial3D = StandardMaterial3D.new()
	lamp.albedo_color = Color(1.0, 0.97, 0.88)
	lamp.emission_enabled = true
	lamp.emission = Color(1.0, 0.95, 0.8)
	lamp.emission_energy_multiplier = 6.0
	for x: float in lamp_xs:
		_add_box(_track_root, Vector3(0.5, 22.0, 0.5), Vector3(x, 11.0, z_start + dir * 14.0), _flat(Color(0.3, 0.3, 0.32), 0.6))
		_add_box(_track_root, Vector3(4.0, 1.4, 0.4), Vector3(x, 22.5, z_start + dir * 13.6), lamp)


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
