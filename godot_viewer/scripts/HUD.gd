extends CanvasLayer
## VIEW 2D - HUD in stile diretta TV: cronometro in basso a destra (decimi in gara, centesimi all'arrivo), vento e
## risultato non ufficiale (primi 5) dopo l'arrivo; pannello laterale scuro semi-trasparente con la classifica live
## (nascosto di default, tasto H); banner di stato. Aggiorna a ogni fotogramma (60 fps con vsync) e
## riscrive il testo di una Label solo se e' cambiato.

const FONT_SIZE_TIMER: int = 44
const FONT_SIZE_ROW: int = 20
const PANEL_COLOR: Color = Color(0.04, 0.05, 0.09, 0.72)
const ACCENT: Color = Color(1.0, 0.82, 0.2)
const PLAYER_COLOR: Color = Color(0.45, 0.85, 1.0)

@onready var _timer_panel: PanelContainer = %TimerPanel
@onready var _timer_label: Label = %TimerLabel
@onready var _ranking_panel: PanelContainer = %RankingPanel
@onready var _title_label: Label = %TitleLabel
@onready var _rows_box: VBoxContainer = %Rows
@onready var _banner: Label = %BannerLabel

var _rows: Array[Dictionary] = []  # {box, place, name, value}
var _last_timer_text: String = ""
var _last_banner_text: String = ""
var ranking_visible: bool = false     # come nella diretta TV, in gara non c'e' una classifica: tasto H per mostrarla
var _speed_label: Label = null
var _last_speed_text: String = ""
var _clock_panel: PanelContainer
var _clock_caption: Label
var _clock_label: Label
var _wind_panel: PanelContainer
var _wind_label: Label
var _result_panel: PanelContainer
var _result_title: Label
var _result_rows: Array[Dictionary] = []  # {box, place, name, value}
var _last_clock_text: String = ""


func _ready() -> void:
	_style_panel(_timer_panel)
	_style_panel(_ranking_panel)
	_timer_label.add_theme_font_size_override("font_size", FONT_SIZE_TIMER)
	_timer_label.add_theme_color_override("font_color", ACCENT)
	_title_label.add_theme_font_size_override("font_size", FONT_SIZE_ROW)
	_title_label.add_theme_color_override("font_color", ACCENT)
	_banner.add_theme_font_size_override("font_size", 36)
	_banner.add_theme_color_override("font_outline_color", Color.BLACK)
	_banner.add_theme_constant_override("outline_size", 8)
	_timer_panel.visible = false          # il cronometro centrale e' sostituito da quello in basso a destra
	_make_speed_label()
	_build_tv_graphics()
	RaceController.race_loaded.connect(_on_race_loaded)
	_on_race_loaded(RaceController.runners, RaceController.info)


func _process(_delta: float) -> void:
	_update_timer()
	_update_ranking()
	_update_banner()
	_update_speed_label()
	_update_tv_graphics()
	_ranking_panel.visible = ranking_visible


func _on_race_loaded(runners: Array[RunnerData], info: Dictionary) -> void:
	for row: Dictionary in _rows:
		(row["box"] as Node).queue_free()
	_rows.clear()
	_title_label.text = "%s  -  %s" % [str(info.get("event_name", "")), str(info.get("meet_name", ""))]
	for i in range(runners.size()):
		_rows.append(_make_row())
	_last_timer_text = ""
	_last_banner_text = ""


func _update_timer() -> void:
	var text: String = RaceController.format_time(RaceController.display_time)
	if text != _last_timer_text:
		_last_timer_text = text
		_timer_label.text = text


func _update_ranking() -> void:
	var order: Array[RunnerData] = RaceController.live_order
	var leader_d: float = RaceController.leader_distance()
	for i in range(mini(order.size(), _rows.size())):
		var r: RunnerData = order[i]
		var row: Dictionary = _rows[i]
		var value: String
		if r.dnf and r.distance > 1.0 and r.speed < 0.3:
			value = "RIT."
		elif r.finished:
			value = RaceController.format_time(r.final_time)
		elif i == 0 or RaceController.state == RaceController.State.COUNTDOWN:
			value = "L%d" % r.lane
		else:
			value = "-%.1f m" % (leader_d - r.distance)
		_set_text(row["place"], str(i + 1))
		_set_text(row["name"], "%s  (%d)" % [r.surname(), r.lane])
		_set_text(row["value"], value)
		var color: Color = PLAYER_COLOR if r.is_player else Color.WHITE
		(row["name"] as Label).add_theme_color_override("font_color", color)


func _update_banner() -> void:
	var text: String = ""
	match RaceController.state:
		RaceController.State.COUNTDOWN:
			if RaceController.set_amount() <= 0.0:
				text = "AI VOSTRI POSTI"
			else:
				text = "PRONTI"
		RaceController.State.RUNNING, RaceController.State.FINISHED:
			if RaceController.race_time < 1.0:
				text = "VIA!"
	if text != _last_banner_text:
		_last_banner_text = text
		_banner.text = text


## Indicatore in basso a destra: velocita' attuale e tasti per cambiarla.
func _make_speed_label() -> void:
	_speed_label = Label.new()
	_speed_label.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_RIGHT)
	_speed_label.grow_horizontal = Control.GROW_DIRECTION_BEGIN
	_speed_label.grow_vertical = Control.GROW_DIRECTION_BEGIN
	_speed_label.offset_right = -16.0
	_speed_label.offset_bottom = -12.0
	_speed_label.add_theme_font_size_override("font_size", 16)
	_speed_label.add_theme_color_override("font_color", Color(1, 1, 1, 0.85))
	_speed_label.add_theme_color_override("font_outline_color", Color.BLACK)
	_speed_label.add_theme_constant_override("outline_size", 6)
	$Root.add_child(_speed_label)


func _update_speed_label() -> void:
	var text: String = "Velocita' %dx    [1] [2] [4] [8]    H: classifica    Esc: salta alla fine" % int(RaceController.time_scale)
	if text != _last_speed_text:
		_last_speed_text = text
		_speed_label.text = text


# --- grafica TV ---------------------------------------------------------------------------------

func _tv_style(accent: Color) -> StyleBoxFlat:
	var style: StyleBoxFlat = StyleBoxFlat.new()
	style.bg_color = Color(0.04, 0.07, 0.20, 0.92)
	style.border_color = accent
	style.border_width_left = 5
	style.set_corner_radius_all(3)
	style.content_margin_left = 14.0
	style.content_margin_right = 14.0
	style.content_margin_top = 6.0
	style.content_margin_bottom = 6.0
	return style


func _tv_label(size: int, color: Color) -> Label:
	var l: Label = Label.new()
	l.add_theme_font_size_override("font_size", size)
	l.add_theme_color_override("font_color", color)
	return l


func _anchor_bottom_right(panel: Control, right: float, bottom: float) -> void:
	panel.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_RIGHT)
	panel.grow_horizontal = Control.GROW_DIRECTION_BEGIN
	panel.grow_vertical = Control.GROW_DIRECTION_BEGIN
	panel.offset_right = right
	panel.offset_bottom = bottom
	panel.mouse_filter = Control.MOUSE_FILTER_IGNORE


## Cronometro (in basso a destra), vento e riquadro del risultato non ufficiale (in basso a sinistra).
func _build_tv_graphics() -> void:
	var teal: Color = Color(0.2, 0.85, 0.85)
	_clock_panel = PanelContainer.new()
	_clock_panel.add_theme_stylebox_override("panel", _tv_style(teal))
	_anchor_bottom_right(_clock_panel, -16.0, -44.0)
	var column: VBoxContainer = VBoxContainer.new()
	_clock_panel.add_child(column)
	_clock_caption = _tv_label(15, teal)
	_clock_label = _tv_label(42, Color.WHITE)
	_clock_label.custom_minimum_size = Vector2(170.0, 0.0)
	_clock_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	column.add_child(_clock_caption)
	column.add_child(_clock_label)
	$Root.add_child(_clock_panel)

	_wind_panel = PanelContainer.new()
	_wind_panel.add_theme_stylebox_override("panel", _tv_style(Color(0.6, 0.7, 1.0)))
	_anchor_bottom_right(_wind_panel, -16.0, -150.0)
	_wind_label = _tv_label(20, Color.WHITE)
	_wind_panel.add_child(_wind_label)
	_wind_panel.visible = false
	$Root.add_child(_wind_panel)

	_result_panel = PanelContainer.new()
	_result_panel.add_theme_stylebox_override("panel", _tv_style(teal))
	_result_panel.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_LEFT)
	_result_panel.grow_vertical = Control.GROW_DIRECTION_BEGIN
	_result_panel.offset_left = 16.0
	_result_panel.offset_bottom = -44.0
	_result_panel.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var rows: VBoxContainer = VBoxContainer.new()
	_result_panel.add_child(rows)
	_result_title = _tv_label(15, teal)
	rows.add_child(_result_title)
	for i in range(5):
		var box: HBoxContainer = HBoxContainer.new()
		box.add_theme_constant_override("separation", 12)
		var place: Label = _tv_label(20, Color.WHITE)
		place.custom_minimum_size = Vector2(24.0, 0.0)
		var name_label: Label = _tv_label(20, Color.WHITE)
		name_label.custom_minimum_size = Vector2(210.0, 0.0)
		var value: Label = _tv_label(20, Color.WHITE)
		value.custom_minimum_size = Vector2(90.0, 0.0)
		value.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
		for l: Label in [place, name_label, value]:
			box.add_child(l)
		rows.add_child(box)
		_result_rows.append({"box": box, "place": place, "name": name_label, "value": value})
	_result_panel.visible = false
	$Root.add_child(_result_panel)


func _update_tv_graphics() -> void:
	var rc: Node = RaceController
	var running: bool = rc.state == rc.State.RUNNING or rc.state == rc.State.FINISHED
	_clock_panel.visible = running
	_clock_caption.text = "M %s" % str(rc.info.get("event_name", "")).to_upper()
	if running:
		var winner_in: bool = not rc.live_order.is_empty() and rc.live_order[0].finished
		# In gara i decimi (troncati: non superano mai il tempo del vincitore), all'arrivo i centesimi.
		var text: String = rc.format_time(rc.display_time) if winner_in else "%.1f" % (floorf(rc.display_time * 10.0) / 10.0)
		if text != _last_clock_text:
			_last_clock_text = text
			_clock_label.text = text

	var leader_done: bool = running and not rc.live_order.is_empty() and rc.live_order[0].finished
	var wind: Variant = rc.info.get("wind_ms", null)
	_wind_panel.visible = leader_done and rc.event_kind == "100m" and wind != null
	if _wind_panel.visible:
		_wind_label.text = "VENTO  %+.1f m/s" % float(wind)

	_result_panel.visible = leader_done and rc.race_time > rc.live_order[0].final_time + 1.0
	if _result_panel.visible:
		_result_title.text = "RISULTATO NON UFFICIALE" if rc.state == rc.State.RUNNING else "RISULTATO"
		var shown: int = 0
		for r: RunnerData in rc.live_order:
			if not r.finished or shown >= _result_rows.size():
				continue
			var row: Dictionary = _result_rows[shown]
			_set_text(row["place"], str(r.place))
			_set_text(row["name"], r.athlete_name.to_upper())
			_set_text(row["value"], rc.format_time(r.final_time))
			(row["name"] as Label).add_theme_color_override("font_color", PLAYER_COLOR if r.is_player else Color.WHITE)
			shown += 1
		for i in range(_result_rows.size()):
			(_result_rows[i]["box"] as Control).visible = i < shown


# --- helper -------------------------------------------------------------------------------------

func _style_panel(panel: PanelContainer) -> void:
	var style: StyleBoxFlat = StyleBoxFlat.new()
	style.bg_color = PANEL_COLOR
	style.set_corner_radius_all(6)
	style.set_content_margin_all(12)
	panel.add_theme_stylebox_override("panel", style)


func _make_row() -> Dictionary:
	var box: HBoxContainer = HBoxContainer.new()
	box.add_theme_constant_override("separation", 12)
	var place: Label = _row_label(28, HORIZONTAL_ALIGNMENT_CENTER)
	var name_label: Label = _row_label(190, HORIZONTAL_ALIGNMENT_LEFT)
	var value: Label = _row_label(84, HORIZONTAL_ALIGNMENT_RIGHT)
	for l: Label in [place, name_label, value]:
		box.add_child(l)
	_rows_box.add_child(box)
	return {"box": box, "place": place, "name": name_label, "value": value}


func _row_label(min_width: float, align: HorizontalAlignment) -> Label:
	var l: Label = Label.new()
	l.custom_minimum_size = Vector2(min_width, 0.0)
	l.horizontal_alignment = align
	l.add_theme_font_size_override("font_size", FONT_SIZE_ROW)
	return l


func _set_text(label: Label, text: String) -> void:
	if label.text != text:
		label.text = text
