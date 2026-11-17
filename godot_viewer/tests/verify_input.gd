extends SceneTree
## Verifica headless dei comandi da tastiera e della chiusura automatica sulla scena vera:
##   godot --headless --path godot_viewer -s res://tests/verify_input.gd -- --autoquit
## Esce con codice 0 se tutto torna, 1 altrimenti.

var _failures: int = 0
var _stadium: Node = null
var _step: int = 0
var _frames: int = 0


func _check(cond: bool, what: String) -> void:
	print(("OK    " if cond else "FAIL  ") + what)
	if not cond:
		_failures += 1


func _press(key: Key) -> void:
	for pressed: bool in [true, false]:
		var ev: InputEventKey = InputEventKey.new()
		ev.keycode = key
		ev.physical_keycode = key
		ev.pressed = pressed
		root.push_input(ev)  # stessa via dei tasti reali: viewport -> _unhandled_key_input


func _process(_delta: float) -> bool:
	var rc: Node = root.get_node("RaceController")
	_frames += 1
	match _step:
		0:
			_stadium = (load("res://scenes/Stadium.tscn") as PackedScene).instantiate()
			root.add_child(_stadium)
			_step = 1
			_frames = 0
		1:
			if _frames < 3:
				return false
			_check(rc.state == rc.State.LOADED, "gara caricata dalla scena (stato LOADED)")
			_check(_stadium.get_node("Runners").get_child_count() == 8, "8 corridori in scena")
			_check(bool(_stadium.get("_autoquit")), "--autoquit riconosciuto")
			_press(KEY_2)
			_check(is_equal_approx(rc.time_scale, 2.0), "tasto 2 -> velocita' 2x")
			_press(KEY_4)
			_check(is_equal_approx(rc.time_scale, 4.0), "tasto 4 -> velocita' 4x")
			_press(KEY_8)
			_check(is_equal_approx(rc.time_scale, 8.0), "tasto 8 -> velocita' 8x")
			_press(KEY_1)
			_check(is_equal_approx(rc.time_scale, 1.0), "tasto 1 -> velocita' 1x")
			_press(KEY_SPACE)
			_check(rc.state == rc.State.COUNTDOWN, "Spazio avvia la gara (COUNTDOWN)")
			_step = 2
			_frames = 0
		2:
			if _frames < 30:
				return false
			var before: float = rc.clock
			_press(KEY_ESCAPE)
			_check(rc.clock > before + 10.0, "Esc salta alla fine (clock %.1f -> %.1f)" % [before, rc.clock])
			_step = 3
		3:
			if rc.state != rc.State.FINISHED:
				return false
			_check(true, "la gara arriva a FINISHED dopo Esc")
			_step = 4
			_frames = 0
		4:
			if _frames < 3:
				return false
			_check(bool(_stadium.get("_quit_scheduled")), "--autoquit: chiusura programmata a gara finita")
			print("RISULTATO: %s" % ("TUTTO OK" if _failures == 0 else "%d FALLIMENTI" % _failures))
			quit(0 if _failures == 0 else 1)
			return true
	return false
