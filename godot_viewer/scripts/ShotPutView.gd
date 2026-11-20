class_name ShotPutView
extends Node3D
## VIEW 3D - il peso in volo e quello che resta sul terreno: sfera di dimensioni vere (7,26 kg = 121 mm, 4 kg = 104 mm) con
## una cucitura scura che ne mostra la rotazione, scia della traiettoria (grafica da diretta TV), terriccio sollevato all'impatto (nessuna buca nel terreno),
## nastro dal centro della pedana al punto d'impatto e bandierina (verde = valido, rossa = nullo).
## Legge soltanto RaceController (piano del tentativo e tempo) e ShotPutMotion (funzioni pure): la posizione del peso e'
## quella calcolata dal modello, quindi atterra esattamente alla misura del DB. Non decide nulla.

const TAPE_COLOR: Color = Color(0.97, 0.88, 0.25)
const FLAG_OK: Color = Color(0.18, 0.88, 0.56)
const FLAG_FOUL: Color = Color(0.92, 0.22, 0.22)
const TRAIL_COLOR: Color = Color(0.72, 0.92, 1.0, 0.7)
const BALL_SPIN: float = 9.0              # rad/s: il peso non e' aerodinamico, ruota lentamente su se stesso
const LEADER_COLOR: Color = Color(1.0, 0.80, 0.15)
const LEADER_WIDTH: float = 0.14
const TAPE_DELAY: float = 0.45            # i giudici stendono il nastro e piantano la bandierina dopo l'atterraggio
const TRAIL_AFTER_LAND: float = 0.6       # la scia resta poco dopo l'atterraggio, poi sparisce

var _ball: MeshInstance3D
var _ball_mesh: SphereMesh
var _trail: MeshInstance3D
var _trail_mesh: ImmediateMesh
var _tape: MeshInstance3D
var _flag: Node3D
var _flag_cloth: MeshInstance3D
var _flag_mat: StandardMaterial3D
var _dust: CPUParticles3D
var _leader_arc: MeshInstance3D       # arco dorato alla distanza del miglior lancio
var _leader_label: Label3D            # "COGNOME  19.42 m" accanto all'arco
var _leader_key: String = ""
var _plan: ShotPutMotion.Plan = null
var _was_landed: bool = false


func _ready() -> void:
	_ball_mesh = SphereMesh.new()
	_ball_mesh.radial_segments = 24
	_ball_mesh.rings = 12
	var mat: StandardMaterial3D = StandardMaterial3D.new()
	mat.albedo_color = Color(0.86, 0.89, 0.94)
	mat.metallic = 0.45
	mat.roughness = 0.22
	_ball_mesh.material = mat
	_ball = MeshInstance3D.new()
	_ball.mesh = _ball_mesh
	_ball.visible = false
	add_child(_ball)
	# Cucitura: anello scuro lungo un cerchio massimo (rende visibile la rotazione).
	var seam: TorusMesh = TorusMesh.new()
	seam.inner_radius = 0.985
	seam.outer_radius = 1.015
	seam.rings = 24
	seam.ring_segments = 6
	var seam_mat: StandardMaterial3D = StandardMaterial3D.new()
	seam_mat.albedo_color = Color(0.12, 0.13, 0.16)
	seam_mat.roughness = 0.6
	seam.material = seam_mat
	var seam_node: MeshInstance3D = MeshInstance3D.new()
	seam_node.mesh = seam
	seam_node.rotation.x = PI * 0.5
	seam_node.scale = Vector3.ONE * 1.0
	_ball.add_child(seam_node)

	_trail_mesh = ImmediateMesh.new()
	_trail = MeshInstance3D.new()
	_trail.mesh = _trail_mesh
	_trail.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(_trail)

	_leader_arc = MeshInstance3D.new()
	_leader_arc.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	_leader_arc.visible = false
	var arc_mat: StandardMaterial3D = StandardMaterial3D.new()
	arc_mat.albedo_color = LEADER_COLOR
	arc_mat.emission_enabled = true
	arc_mat.emission = LEADER_COLOR
	arc_mat.emission_energy_multiplier = 0.7
	arc_mat.roughness = 0.6
	_leader_arc.material_override = arc_mat
	add_child(_leader_arc)
	_leader_label = Label3D.new()
	_leader_label.font_size = 96
	_leader_label.pixel_size = 0.0065
	_leader_label.modulate = LEADER_COLOR
	_leader_label.outline_size = 14
	_leader_label.outline_modulate = Color(0.03, 0.08, 0.04)
	_leader_label.rotation_degrees.x = -90.0
	_leader_label.visible = false
	add_child(_leader_label)

	var tape_mat: StandardMaterial3D = StandardMaterial3D.new()
	tape_mat.albedo_color = TAPE_COLOR
	tape_mat.roughness = 0.6
	var tape_mesh: BoxMesh = BoxMesh.new()
	tape_mesh.size = Vector3.ONE
	tape_mesh.material = tape_mat
	_tape = MeshInstance3D.new()
	_tape.mesh = tape_mesh
	_tape.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	_tape.visible = false
	add_child(_tape)

	_flag = Node3D.new()
	_flag.visible = false
	add_child(_flag)
	var pole: CylinderMesh = CylinderMesh.new()
	pole.top_radius = 0.008
	pole.bottom_radius = 0.008
	pole.height = 0.7
	var pole_mat: StandardMaterial3D = StandardMaterial3D.new()
	pole_mat.albedo_color = Color(0.9, 0.9, 0.92)
	pole.material = pole_mat
	var pole_node: MeshInstance3D = MeshInstance3D.new()
	pole_node.mesh = pole
	pole_node.position.y = 0.35
	_flag.add_child(pole_node)
	var cloth: BoxMesh = BoxMesh.new()
	cloth.size = Vector3(0.22, 0.14, 0.004)
	_flag_mat = StandardMaterial3D.new()
	_flag_mat.albedo_color = FLAG_OK
	_flag_mat.emission_enabled = true
	_flag_mat.emission = FLAG_OK
	_flag_mat.emission_energy_multiplier = 0.5
	cloth.material = _flag_mat
	_flag_cloth = MeshInstance3D.new()
	_flag_cloth.mesh = cloth
	_flag_cloth.position = Vector3(0.115, 0.62, 0.0)
	_flag.add_child(_flag_cloth)

	_dust = CPUParticles3D.new()
	_dust.emitting = false
	_dust.one_shot = true
	_dust.amount = 36
	_dust.lifetime = 0.9
	_dust.explosiveness = 0.95
	_dust.direction = Vector3.UP
	_dust.spread = 55.0
	_dust.initial_velocity_min = 1.1
	_dust.initial_velocity_max = 2.9
	_dust.gravity = Vector3(0.0, -7.0, 0.0)
	_dust.scale_amount_min = 0.6
	_dust.scale_amount_max = 1.5
	var puff: SphereMesh = SphereMesh.new()
	puff.radius = 0.04
	puff.height = 0.08
	puff.radial_segments = 6
	puff.rings = 3
	var puff_mat: StandardMaterial3D = StandardMaterial3D.new()
	puff_mat.albedo_color = Color(0.45, 0.35, 0.24)
	puff_mat.roughness = 1.0
	puff_mat.vertex_color_use_as_albedo = true
	puff_mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	puff.material = puff_mat
	_dust.mesh = puff
	var fade: Gradient = Gradient.new()
	fade.set_color(0, Color(1.0, 1.0, 1.0, 0.85))
	fade.set_color(1, Color(1.0, 1.0, 1.0, 0.0))
	_dust.color_ramp = fade
	_dust.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(_dust)


func _process(_delta: float) -> void:
	var plan: ShotPutMotion.Plan = RaceController.shot_plan
	_update_leader()
	if plan == null or RaceController.event_kind != "Getto del Peso":
		_hide_all()
		_plan = null
		return
	if plan != _plan:
		_start_attempt(plan)
	var t: float = RaceController.shot_t
	var ball: Dictionary = ShotPutMotion.ball_at(plan, t)
	_ball.visible = bool(ball["visible"])
	if _ball.visible:
		_ball.position = ball["pos"]
		_ball.basis = Basis(Vector3(0.7, 1.0, 0.4).normalized(), 0.0 if plan.instant else minf(t - ShotPutMotion.T_REL, plan.flight) * BALL_SPIN)
	var landed: bool = bool(ball["landed"])
	if landed:
		if not _was_landed and not plan.instant:
			_dust.global_position = plan.landing + Vector3(0.0, 0.05, 0.0)
			_dust.restart()
			_dust.emitting = true
		var marked: bool = plan.instant or (t - plan.t_land) >= TAPE_DELAY
		_tape.visible = marked
		_flag.visible = marked
	_was_landed = landed
	_update_trail(plan, t)


func _start_attempt(plan: ShotPutMotion.Plan) -> void:
	_plan = plan
	_was_landed = false
	_tape.visible = false
	_flag.visible = false
	_dust.emitting = false
	_ball_mesh.radius = plan.ball_r
	_ball_mesh.height = plan.ball_r * 2.0
	(_ball.get_child(0) as MeshInstance3D).scale = Vector3.ONE * plan.ball_r
	# Nastro dal centro della pedana al punto d'impatto (non allo stoppino): lungo `mark + raggio` metri.
	var length: float = plan.mark + ShotPutMotion.CIRCLE_RADIUS
	_tape.scale = Vector3(length, 0.006, 0.016)
	_tape.position = ShotPutMotion.CENTER + plan.dir * (length * 0.5) + Vector3(0.0, 0.022, 0.0)
	_tape.rotation = Vector3(0.0, plan.land_angle, 0.0)
	# Bandierina accanto al punto d'impatto, dalla parte esterna.
	var side: Vector3 = Vector3(-plan.dir.z, 0.0, plan.dir.x)
	_flag.position = plan.landing + side * 0.30
	_flag.rotation.y = plan.land_angle + PI * 0.5
	var col: Color = FLAG_FOUL if plan.foul else FLAG_OK
	_flag_mat.albedo_color = col
	_flag_mat.emission = col


func _update_trail(plan: ShotPutMotion.Plan, t: float) -> void:
	_trail_mesh.clear_surfaces()
	if plan.instant or t <= ShotPutMotion.T_REL or t > plan.t_land + TRAIL_AFTER_LAND:
		return
	var tau_end: float = minf(t - ShotPutMotion.T_REL, plan.flight)
	var n: int = maxi(2, int(tau_end / 0.04))
	var mat: StandardMaterial3D = StandardMaterial3D.new()
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	mat.albedo_color = TRAIL_COLOR
	mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	_trail_mesh.surface_begin(Mesh.PRIMITIVE_LINE_STRIP, mat)
	for i in range(n + 1):
		_trail_mesh.surface_add_vertex(ShotPutMotion.flight_position(plan, tau_end * float(i) / float(n)))
	_trail_mesh.surface_end()


func _hide_all() -> void:
	_ball.visible = false
	_tape.visible = false
	_flag.visible = false
	_trail_mesh.clear_surfaces()


## Arco dorato sul terreno alla distanza del miglior lancio (centrato sulla pedana: tutti i punti a quella misura), con il nome.
## Si aggiorna quando qualcuno lo supera (l'atterraggio committa la misura in RaceController).
func _update_leader() -> void:
	var best: float = 0.0
	var who: String = ""
	var live: Array[RunnerData] = RaceController.live_order
	if RaceController.event_kind == "Getto del Peso" and not live.is_empty() and live[0].best_mark > 0.0:
		best = live[0].best_mark
		who = live[0].surname()
	var key: String = "%s|%.2f" % [who, best]
	if key == _leader_key:
		return
	_leader_key = key
	_leader_arc.visible = best > 0.0
	_leader_label.visible = best > 0.0
	if best <= 0.0:
		return
	var r: float = ShotPutMotion.CIRCLE_RADIUS + best
	var half: float = ShotPutMotion.SECTOR_HALF_ANGLE
	var st: SurfaceTool = SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	st.set_normal(Vector3.UP)
	var steps: int = 40
	var up: Vector3 = Vector3(0.0, 0.009, 0.0)
	for i in range(steps):
		var aa: float = lerpf(-half, half, float(i) / steps)
		var ab: float = lerpf(-half, half, float(i + 1) / steps)
		var p00: Vector3 = ShotPutMotion.CENTER + ShotPutMotion.dir_at(aa) * (r - LEADER_WIDTH * 0.5) + up
		var p01: Vector3 = ShotPutMotion.CENTER + ShotPutMotion.dir_at(aa) * (r + LEADER_WIDTH * 0.5) + up
		var p10: Vector3 = ShotPutMotion.CENTER + ShotPutMotion.dir_at(ab) * (r - LEADER_WIDTH * 0.5) + up
		var p11: Vector3 = ShotPutMotion.CENTER + ShotPutMotion.dir_at(ab) * (r + LEADER_WIDTH * 0.5) + up
		_up_tri(st, p00, p01, p10)
		_up_tri(st, p10, p01, p11)
	_leader_arc.mesh = st.commit()
	_leader_label.text = "%s  %.2f m" % [who, best]
	# Il testo sta dentro il settore, dal lato delle camere laterali, e finisce contro l'arco (si legge da +Z verso -Z).
	var at: Vector3 = ShotPutMotion.CENTER + ShotPutMotion.dir_at(-half + 0.11) * (r - 2.7)
	_leader_label.position = Vector3(at.x, 0.016, at.z)


## Triangolo con la faccia superiore verso l'alto (in Godot la faccia anteriore e' quella oraria).
func _up_tri(st: SurfaceTool, a: Vector3, b: Vector3, c: Vector3) -> void:
	if (c - a).cross(b - a).y < 0.0:
		var tmp: Vector3 = b
		b = c
		c = tmp
	st.add_vertex(a)
	st.add_vertex(b)
	st.add_vertex(c)
