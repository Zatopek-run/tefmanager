extends SceneTree
## Laboratorio della posizione ai blocchi: scatta screenshot di "pronti" e "set" dall'angolo basso del video di riferimento.
##   godot --path godot_viewer -s res://tests/pose_lab.gd -- cartella_uscita [lane]
var _out: String = "user://pose_lab"
var _stage: int = 0
var _frames: int = 0
var _runners: Array = []
var _cam: Camera3D

func _process(_d: float) -> bool:
	_frames += 1
	if _stage == 0:
		var args: PackedStringArray = OS.get_cmdline_user_args()
		if args.size() > 0: _out = args[0]
		DirAccess.make_dir_recursive_absolute(_out)
		_build()
		_stage = 1; _frames = 0
		return false
	if _frames < 6: return false
	var shots: Array = [[0.0, "pronti"], [1.0, "set"], [0.5, "mezzo"]]
	if _stage > shots.size():
		quit(0); return true
	var s: Array = shots[_stage - 1]
	if _frames == 6:
		for r in _runners: r.set_amount_override = s[0]
		return false
	if _frames < 12: return false
	root.get_texture().get_image().save_png("%s/%s_%s.png" % [_out, "lab", s[1]])
	print("salvato ", s[1])
	_stage += 1; _frames = 0
	return false

func _build() -> void:
	var env := Environment.new()
	env.background_mode = Environment.BG_COLOR; env.background_color = Color(0.05, 0.07, 0.14)
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR; env.ambient_light_color = Color(0.5, 0.55, 0.8); env.ambient_light_energy = 0.8
	var we := WorldEnvironment.new(); we.environment = env; root.add_child(we)
	var sun := DirectionalLight3D.new(); sun.rotation_degrees = Vector3(-50, -40, 0); sun.shadow_enabled = true; sun.light_energy = 1.2; root.add_child(sun)
	var ground := MeshInstance3D.new(); var bm := BoxMesh.new(); bm.size = Vector3(60, 0.1, 40)
	ground.mesh = bm; ground.position = Vector3(0, -0.05, 4)
	var gm := StandardMaterial3D.new(); gm.albedo_color = Color(0.13, 0.25, 0.55); gm.roughness = 0.9; ground.material_override = gm; root.add_child(ground)
	var line := MeshInstance3D.new(); var lm := BoxMesh.new(); lm.size = Vector3(0.05, 0.01, 12)
	line.mesh = lm; line.position = Vector3(0, 0.006, 4.2)
	var wm := StandardMaterial3D.new(); wm.albedo_color = Color(0.95, 0.95, 0.95); line.material_override = wm; root.add_child(line)
	var names := ["Dario Conti", "Luca Ferrante", "Marco Valenti", "Ivo Salvetti", "Tomas Reinholt", "Paulo Mendes", "Kenji Arakawa", "Elias Ndlovu"]
	for i in range(8):
		var d = load("res://models/RunnerData.gd").new(); d.athlete_name = names[i]; d.team_name = "Club %d" % (i % 4); d.lane = i + 1; d.reaction_time = 0.15; d.final_time = 10.0
		var v = load("res://scripts/RunnerView.gd").new(); root.add_child(v); v.setup(d); _runners.append(v)
	_cam = Camera3D.new(); root.add_child(_cam)
	_cam.fov = 42.0
	_cam.position = Vector3(1.4, 0.75, 12.5)
	_cam.look_at(Vector3(-0.5, 0.55, 5.0), Vector3.UP)
	_cam.make_current()
