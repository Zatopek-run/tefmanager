class_name BibPrint
extends RefCounted
## VIEW 3D - pettorale di gara: foglio bianco con il numero a cifre scure e le quattro spille agli angoli, stampato davanti e
## dietro sulla canotta (vedi `CharacterDress.add_cloth`, opzione `print`). Il numero lo assegna Python (`models/bibs.py`) e arriva
## in `RunnerData.bib`: qui si disegna soltanto, non si decide nulla.
##
## Il foglio e' una texture da un SubViewport trasparente-no (opaco), disegnato una sola volta (UPDATE_ONCE) e figlio di chi lo
## chiede: sparisce con il corridore. Non c'e' una cache fra gare: una texture di un viewport gia' liberato resterebbe vuota.

const SIZE: Vector2i = Vector2i(240, 180)
## Larghezza del foglio in altezze corporee: oltre ±0,06 la schiena/il petto girano di lato e il disegno si taglierebbe.
const WIDTH: float = 0.115
const CENTER_Y: float = 0.70   # centro del foglio: il petto/le scapole, dentro la fascia 0,60-0,82 della canotta
const PAPER: Color = Color(0.97, 0.97, 0.94)
const INK: Color = Color(0.05, 0.05, 0.07)
const PIN: Color = Color(0.55, 0.55, 0.58)


## (x centro, y centro, larghezza, altezza) del foglio in altezze corporee, nel formato di `CharacterDress.add_cloth`.
static func rect() -> Vector4:
	return Vector4(0.0, CENTER_Y, WIDTH, WIDTH * float(SIZE.y) / float(SIZE.x))


## Texture del pettorale con quel numero. `owner` deve essere nell'albero (il viewport diventa suo figlio).
static func make_texture(owner: Node, number: int) -> Texture2D:
	var vp: SubViewport = SubViewport.new()
	vp.size = SIZE
	vp.disable_3d = true
	vp.render_target_update_mode = SubViewport.UPDATE_ONCE
	var paper: ColorRect = ColorRect.new()
	paper.color = PAPER
	paper.size = Vector2(SIZE)
	vp.add_child(paper)
	for corner: Vector2 in [Vector2(10.0, 10.0), Vector2(SIZE.x - 20.0, 10.0), Vector2(10.0, SIZE.y - 20.0), Vector2(SIZE.x - 20.0, SIZE.y - 20.0)]:
		var pin: ColorRect = ColorRect.new()
		pin.color = PIN
		pin.position = corner
		pin.size = Vector2(10.0, 10.0)
		vp.add_child(pin)
	var label: Label = Label.new()
	label.text = str(number)
	label.size = Vector2(SIZE)
	label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	var font: SystemFont = SystemFont.new()
	font.font_names = PackedStringArray(["Bahnschrift", "Segoe UI", "Arial", "DejaVu Sans"])
	font.font_weight = 800
	label.add_theme_font_override("font", font)
	label.add_theme_font_size_override("font_size", 112)
	label.add_theme_color_override("font_color", INK)
	vp.add_child(label)
	owner.add_child(vp)
	return vp.get_texture()
