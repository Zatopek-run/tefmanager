extends CanvasLayer
## VIEW 2D - HUD "diretta TV 2010": cronometro centrale, pannello laterale scuro semi-trasparente
## con la classifica live, banner di stato. Aggiorna a ogni fotogramma (60 fps con vsync) e
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
	RaceController.race_loaded.connect(_on_race_loaded)
	_on_race_loaded(RaceController.runners, RaceController.info)


func _process(_delta: float) -> void:
	_update_timer()
	_update_ranking()
	_update_banner()


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
			if RaceController.clock < RaceController.GUN_AT * 0.5:
				text = "AI VOSTRI POSTI"
			else:
				text = "PRONTI"
		RaceController.State.RUNNING, RaceController.State.FINISHED:
			if RaceController.race_time < 1.0:
				text = "VIA!"
			elif not RaceController.live_order.is_empty() and RaceController.live_order[0].finished:
				var w: RunnerData = RaceController.live_order[0]
				text = "%s  %s" % [w.athlete_name.to_upper(), RaceController.format_time(w.final_time)]
	if text != _last_banner_text:
		_last_banner_text = text
		_banner.text = text


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
