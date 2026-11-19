extends CanvasLayer
## VIEW 2D - HUD in stile diretta TV moderna: bug evento in alto a sinistra, cronometro/vento in basso a destra,
## barra comandi compatta a pillole, risultato non ufficiale in basso a sinistra, classifica live (tasto H) e
## banner di chiamata. Aggiorna a ogni fotogramma e riscrive le Label solo quando il testo cambia.

const FONT_SIZE_TITLE: int = 16
const FONT_SIZE_ROW: int = 17
const FONT_SIZE_BANNER: int = 24

const BG_NAVY: Color = Color(0.055, 0.075, 0.20, 0.93)
const BG_NAVY_ALT: Color = Color(0.085, 0.115, 0.27, 0.94)
const BG_PILL_DARK: Color = Color(0.04, 0.055, 0.14, 0.84)
const BG_WHITE: Color = Color(0.965, 0.975, 0.99, 0.98)
const TEXT_DARK: Color = Color(0.045, 0.065, 0.18)
const TEXT_MUTED: Color = Color(0.68, 0.76, 0.90)
const CYAN: Color = Color(0.05, 0.87, 0.80)
const MAGENTA: Color = Color(0.92, 0.16, 0.48)
const AMBER: Color = Color(0.98, 0.76, 0.18)
const PLAYER_COLOR: Color = Color(0.36, 0.86, 1.0)
const PLAYER_ROW_BG: Color = Color(0.10, 0.24, 0.42, 0.92)

@onready var _timer_panel: PanelContainer = %TimerPanel
@onready var _timer_label: Label = %TimerLabel
@onready var _ranking_panel: PanelContainer = %RankingPanel
@onready var _title_label: Label = %TitleLabel
@onready var _rows_box: VBoxContainer = %Rows
@onready var _banner: Label = %BannerLabel

var ranking_visible: bool = false     # come nella diretta TV, in gara non c'e' una classifica: tasto H per mostrarla

var _font_regular: Font
var _font_bold: Font
var _font_heavy: Font

var _rows: Array[Dictionary] = []  # {box, bg, stripe, place_bg, place, name, value}
var _last_timer_text: String = ""
var _last_banner_text: String = ""
var _last_clock_text: String = ""
var _last_clock_official: bool = false
var _last_speed_scale: int = -1

var _bug_panel: PanelContainer
var _bug_dot: ColorRect
var _bug_meet: Label
var _bug_event: Label
var _bug_state: Label

var _banner_panel: PanelContainer
var _banner_accent: ColorRect
var _banner_text: Label

var _controls_panel: PanelContainer
var _speed_chips: Dictionary = {}  # scale (1,2,4,8) -> {panel, label}

var _tv_stack: VBoxContainer
var _bug_category_prefix: String = ""
var _clock_panel: PanelContainer
var _clock_header: PanelContainer
var _clock_caption: Label
var _clock_status: Label
var _clock_plate: PanelContainer
var _clock_label: Label
var _wind_panel: PanelContainer
var _wind_label: Label

var _result_panel: PanelContainer
var _result_event: Label
var _result_title: Label
var _result_rows: Array[Dictionary] = []  # {box, bg, place_bg, place, stripe, name, value}

## Classifica finale a tutto schermo (a gara conclusa), come nelle dirette TV: tutti i corridori, ritirati compresi.
const FINAL_MAX_ROWS: int = 12
var _final_panel: PanelContainer
var _replay_panel: PanelContainer   # etichetta «RALENTI» in alto al centro durante il replay dell'arrivo
var _final_event: Label
var _final_title: Label
var _final_rows: Array[Dictionary] = []  # {box, place_bg, place, stripe, bib_chip, bib, name, team, lane, value}


func _ready() -> void:
	_init_fonts()
	_timer_panel.visible = false
	_banner.visible = false
	_style_ranking_panel()
	_build_event_bug()
	_build_banner_pill()
	_build_controls_bar()
	_build_tv_graphics()
	_build_replay_badge()
	RaceController.race_loaded.connect(_on_race_loaded)
	_on_race_loaded(RaceController.runners, RaceController.info)


func _init_fonts() -> void:
	var reg: SystemFont = SystemFont.new()
	reg.font_names = PackedStringArray(["Bahnschrift", "Segoe UI", "Arial"])
	reg.font_weight = 500
	var bold: SystemFont = SystemFont.new()
	bold.font_names = PackedStringArray(["Bahnschrift", "Segoe UI", "Arial"])
	bold.font_weight = 700
	var heavy: SystemFont = SystemFont.new()
	heavy.font_names = PackedStringArray(["Bahnschrift", "Segoe UI", "Arial"])
	heavy.font_weight = 800
	_font_regular = reg
	_font_bold = bold
	_font_heavy = heavy


func _process(_delta: float) -> void:
	_update_timer()
	_update_event_bug()
	_update_ranking()
	_update_banner()
	_update_controls_bar()
	_update_tv_graphics()
	_ranking_panel.visible = ranking_visible


func _on_race_loaded(runners: Array[RunnerData], info: Dictionary) -> void:
	for row: Dictionary in _rows:
		(row["box"] as Node).queue_free()
	_rows.clear()
	var event_name: String = str(info.get("event_name", "100m")).to_upper()
	var meet_name: String = str(info.get("meet_name", "MEETING")).to_upper()
	_title_label.text = "%s  •  CLASSIFICA LIVE" % event_name
	_bug_meet.text = meet_name
	var all_f: bool = not runners.is_empty() and runners.all(func(r: RunnerData) -> bool: return r.gender == "F")
	var all_m: bool = not runners.is_empty() and runners.all(func(r: RunnerData) -> bool: return r.gender == "M")
	var cat_label: String = " FEMMINILE" if all_f else (" MASCHILE" if all_m else "")
	_bug_category_prefix = "F " if all_f else ("M " if all_m else "")
	_bug_event.text = "%s%s" % [event_name, cat_label]
	_result_event.text = "%s  •  %s" % [event_name, meet_name]
	_final_event.text = "%s%s  •  %s" % [_bug_category_prefix, event_name, meet_name]
	for i in range(runners.size()):
		_rows.append(_make_row())
	_last_timer_text = ""
	_last_banner_text = ""
	_last_clock_text = ""
	_last_clock_official = false
	_set_clock_plate_style(false)


func _update_timer() -> void:
	var text: String = RaceController.format_time(RaceController.display_time)
	if text != _last_timer_text:
		_last_timer_text = text
		_timer_label.text = text


# --- bug evento in alto a sinistra --------------------------------------------------------------

func _build_event_bug() -> void:
	_bug_panel = PanelContainer.new()
	_bug_panel.set_anchors_and_offsets_preset(Control.PRESET_TOP_LEFT)
	_bug_panel.offset_left = 18.0
	_bug_panel.offset_top = 16.0
	_bug_panel.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_bug_panel.add_theme_stylebox_override("panel", _flat_box(BG_NAVY, CYAN, 4, 0, 0, 0, 12, 14, 7, 7))

	var row: HBoxContainer = HBoxContainer.new()
	row.add_theme_constant_override("separation", 12)
	_bug_panel.add_child(row)

	var text_col: VBoxContainer = VBoxContainer.new()
	text_col.add_theme_constant_override("separation", 1)
	row.add_child(text_col)

	_bug_meet = _styled_label(11, TEXT_MUTED, true)
	_bug_event = _styled_label(17, Color.WHITE, true, true)
	text_col.add_child(_bug_meet)
	text_col.add_child(_bug_event)

	var status_pill: PanelContainer = PanelContainer.new()
	status_pill.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	status_pill.add_theme_stylebox_override("panel", _flat_box(Color(0.11, 0.15, 0.34, 0.95), Color.TRANSPARENT, 0, 0, 0, 0, 8, 8, 3, 3))
	row.add_child(status_pill)

	var status_row: HBoxContainer = HBoxContainer.new()
	status_row.add_theme_constant_override("separation", 6)
	status_pill.add_child(status_row)

	_bug_dot = ColorRect.new()
	_bug_dot.custom_minimum_size = Vector2(8.0, 8.0)
	_bug_dot.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	_bug_dot.color = AMBER
	status_row.add_child(_bug_dot)

	_bug_state = _styled_label(11, Color.WHITE, true)
	_bug_state.text = "ATTESA"
	status_row.add_child(_bug_state)

	$Root.add_child(_bug_panel)


func _update_event_bug() -> void:
	match RaceController.state:
		RaceController.State.COUNTDOWN:
			_bug_dot.color = AMBER
			_set_text(_bug_state, "PARTENZA")
		RaceController.State.RUNNING:
			_bug_dot.color = MAGENTA
			_set_text(_bug_state, "LIVE")
		RaceController.State.REPLAY:
			_bug_dot.color = AMBER
			_set_text(_bug_state, "RALENTI")
		RaceController.State.FINISHED:
			_bug_dot.color = CYAN
			_set_text(_bug_state, "FINALE")
		_:
			_bug_dot.color = TEXT_MUTED
			_set_text(_bug_state, "PRONTO")


# --- banner chiamate ai blocchi -----------------------------------------------------------------

func _build_banner_pill() -> void:
	_banner_panel = PanelContainer.new()
	_banner_panel.set_anchors_and_offsets_preset(Control.PRESET_CENTER_BOTTOM)
	_banner_panel.grow_horizontal = Control.GROW_DIRECTION_BOTH
	_banner_panel.grow_vertical = Control.GROW_DIRECTION_BEGIN
	_banner_panel.offset_bottom = -58.0
	_banner_panel.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_banner_panel.add_theme_stylebox_override("panel", _flat_box(BG_NAVY, Color(1, 1, 1, 0.14), 1, 1, 1, 1, 0, 22, 0, 0, 4))

	var row: HBoxContainer = HBoxContainer.new()
	row.add_theme_constant_override("separation", 16)
	_banner_panel.add_child(row)

	_banner_accent = ColorRect.new()
	_banner_accent.custom_minimum_size = Vector2(6.0, 44.0)
	_banner_accent.color = AMBER
	row.add_child(_banner_accent)

	_banner_text = _styled_label(22, Color.WHITE, true, true)
	_banner_text.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	row.add_child(_banner_text)

	_banner_panel.visible = false
	$Root.add_child(_banner_panel)


func _update_banner() -> void:
	var text: String = ""
	var accent: Color = AMBER
	if RaceController.is_field(RaceController.event_kind):
		var foul_banner: bool = RaceController.field_landed_foul and RaceController.state == RaceController.State.RUNNING
		text = "LANCIO NULLO!" if (foul_banner and RaceController.event_kind == "Getto del Peso") else ("SALTO NULLO!" if foul_banner else "")
		accent = MAGENTA if foul_banner else AMBER
	else:
		match RaceController.state:
			RaceController.State.COUNTDOWN:
				if not RaceController.uses_blocks(RaceController.event_kind) or RaceController.set_amount() <= 0.0:
					text = "AI VOSTRI POSTI"
					accent = CYAN
				else:
					text = "PRONTI"
					accent = AMBER
			RaceController.State.RUNNING, RaceController.State.FINISHED:
				if RaceController.race_time < 0.9:
					text = "VIA!"
					accent = MAGENTA
	if text != _last_banner_text:
		_last_banner_text = text
		_banner_text.text = text
	_banner_panel.visible = not text.is_empty()
	if _banner_panel.visible:
		_banner_accent.color = accent


# --- barra comandi in basso a destra ------------------------------------------------------------

func _build_controls_bar() -> void:
	_controls_panel = PanelContainer.new()
	_controls_panel.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_RIGHT)
	_controls_panel.grow_horizontal = Control.GROW_DIRECTION_BEGIN
	_controls_panel.grow_vertical = Control.GROW_DIRECTION_BEGIN
	_controls_panel.offset_right = -18.0
	_controls_panel.offset_bottom = -12.0
	_controls_panel.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_controls_panel.add_theme_stylebox_override("panel", _flat_box(BG_PILL_DARK, Color(1, 1, 1, 0.12), 1, 1, 1, 1, 10, 10, 4, 4, 4))

	var row: HBoxContainer = HBoxContainer.new()
	row.add_theme_constant_override("separation", 6)
	_controls_panel.add_child(row)

	var vel_tag: Label = _styled_label(12, TEXT_MUTED, true)
	vel_tag.text = "VEL"
	row.add_child(vel_tag)

	for spd: int in [1, 2, 4, 8]:
		var chip: PanelContainer = PanelContainer.new()
		var lbl: Label = _styled_label(12, Color.WHITE, true)
		lbl.text = "%dx" % spd
		chip.add_child(lbl)
		row.add_child(chip)
		_speed_chips[spd] = {"panel": chip, "label": lbl}

	var sep1: Label = _styled_label(12, Color(1, 1, 1, 0.25), false)
	sep1.text = "|"
	row.add_child(sep1)

	var h_lbl: Label = _styled_label(12, TEXT_MUTED, true)
	h_lbl.text = "[H] Classifica"
	row.add_child(h_lbl)

	var sep2: Label = _styled_label(12, Color(1, 1, 1, 0.25), false)
	sep2.text = "•"
	row.add_child(sep2)

	var esc_lbl: Label = _styled_label(12, TEXT_MUTED, true)
	esc_lbl.text = "[Esc] Salta"
	row.add_child(esc_lbl)

	$Root.add_child(_controls_panel)


func _update_controls_bar() -> void:
	var spd: int = int(roundf(RaceController.time_scale))
	if spd == _last_speed_scale:
		return
	_last_speed_scale = spd
	for k: int in _speed_chips.keys():
		var active: bool = k == spd
		var chip: PanelContainer = _speed_chips[k]["panel"] as PanelContainer
		var lbl: Label = _speed_chips[k]["label"] as Label
		var bg: Color = CYAN if active else Color(1, 1, 1, 0.06)
		chip.add_theme_stylebox_override("panel", _flat_box(bg, Color.TRANSPARENT, 0, 0, 0, 0, 6, 6, 2, 2, 3))
		lbl.add_theme_color_override("font_color", TEXT_DARK if active else Color(0.85, 0.90, 0.98))


# --- classifica live (tasto H) ------------------------------------------------------------------

func _style_ranking_panel() -> void:
	_ranking_panel.offset_left = 18.0
	_ranking_panel.offset_right = 370.0
	_ranking_panel.add_theme_stylebox_override("panel", _flat_box(BG_NAVY, CYAN, 4, 0, 0, 0, 12, 12, 10, 10, 3))
	_title_label.add_theme_font_override("font", _font_heavy)
	_title_label.add_theme_font_size_override("font_size", FONT_SIZE_TITLE)
	_title_label.add_theme_color_override("font_color", CYAN)
	_rows_box.add_theme_constant_override("separation", 4)


func _make_row() -> Dictionary:
	var bg: PanelContainer = PanelContainer.new()
	bg.add_theme_stylebox_override("panel", _flat_box(BG_NAVY_ALT, Color.TRANSPARENT, 0, 0, 0, 0, 6, 10, 4, 4, 2))

	var box: HBoxContainer = HBoxContainer.new()
	box.add_theme_constant_override("separation", 8)
	bg.add_child(box)

	var place_bg: PanelContainer = PanelContainer.new()
	place_bg.custom_minimum_size = Vector2(26.0, 24.0)
	place_bg.add_theme_stylebox_override("panel", _flat_box(Color(0.14, 0.19, 0.38), Color.TRANSPARENT, 0, 0, 0, 0, 4, 4, 1, 1, 2))
	var place: Label = _styled_label(14, Color.WHITE, true, true)
	place.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	place.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	place_bg.add_child(place)

	var stripe: ColorRect = ColorRect.new()
	stripe.custom_minimum_size = Vector2(4.0, 20.0)
	stripe.size_flags_vertical = Control.SIZE_SHRINK_CENTER

	var name_label: Label = _styled_label(FONT_SIZE_ROW - 1, Color.WHITE, true)
	name_label.custom_minimum_size = Vector2(180.0, 0.0)

	var value: Label = _styled_label(FONT_SIZE_ROW - 1, CYAN, true, true)
	value.custom_minimum_size = Vector2(82.0, 0.0)
	value.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT

	for c: Control in [place_bg, stripe, name_label, value]:
		box.add_child(c)
	_rows_box.add_child(bg)
	return {"box": bg, "bg": bg, "stripe": stripe, "place_bg": place_bg, "place": place, "name": name_label, "value": value}


func _update_ranking() -> void:
	var order: Array[RunnerData] = RaceController.live_order
	var leader_d: float = RaceController.leader_distance()
	var field: bool = RaceController.is_field(RaceController.event_kind)
	for i in range(mini(order.size(), _rows.size())):
		var r: RunnerData = order[i]
		var row: Dictionary = _rows[i]
		var value: String
		if field:
			if r.dnf:
				value = "RIT."
			elif r.best_mark > 0.0:
				value = "%.2f m" % r.best_mark
			else:
				value = "NM"
		elif r.dnf and r.distance > 1.0 and r.speed < 0.3:
			value = "SQ." if r.dq else "RIT."
		elif r.finished:
			value = RaceController.format_time(r.final_time)
		elif i == 0 or RaceController.state == RaceController.State.COUNTDOWN:
			value = "C%d" % r.lane
		else:
			value = "-%.1fm" % (leader_d - r.distance)
		var label_name: String = r.team_name.to_upper() if RaceController.is_relay(RaceController.event_kind) else r.surname()
		_set_text(row["place"], str(i + 1))
		_set_text(row["name"], "%s  (%d)" % [label_name, r.lane])
		_set_text(row["value"], value)
		(row["stripe"] as ColorRect).color = _team_color(r.team_name)
		var is_first: bool = i == 0 and RaceController.state != RaceController.State.COUNTDOWN
		(row["place_bg"] as PanelContainer).add_theme_stylebox_override(
			"panel", _flat_box(CYAN if is_first else Color(0.14, 0.19, 0.38), Color.TRANSPARENT, 0, 0, 0, 0, 4, 4, 1, 1, 2))
		(row["place"] as Label).add_theme_color_override("font_color", TEXT_DARK if is_first else Color.WHITE)
		(row["bg"] as PanelContainer).add_theme_stylebox_override(
			"panel", _flat_box(PLAYER_ROW_BG if r.is_player else BG_NAVY_ALT, Color.TRANSPARENT, 0, 0, 0, 0, 6, 10, 4, 4, 2))
		(row["name"] as Label).add_theme_color_override("font_color", PLAYER_COLOR if r.is_player else Color.WHITE)


# --- grafica TV (cronometro, vento, risultato non ufficiale) -------------------------------------

func _build_tv_graphics() -> void:
	# Stack cronometro + vento in basso a destra sopra la barra comandi
	_tv_stack = VBoxContainer.new()
	_tv_stack.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_RIGHT)
	_tv_stack.grow_horizontal = Control.GROW_DIRECTION_BEGIN
	_tv_stack.grow_vertical = Control.GROW_DIRECTION_BEGIN
	_tv_stack.offset_right = -18.0
	_tv_stack.offset_bottom = -48.0
	_tv_stack.add_theme_constant_override("separation", 4)
	_tv_stack.mouse_filter = Control.MOUSE_FILTER_IGNORE

	_clock_panel = PanelContainer.new()
	_clock_panel.add_theme_stylebox_override("panel", _flat_box(Color.TRANSPARENT, Color.TRANSPARENT, 0, 0, 0, 0, 0, 0, 0, 0))
	var clock_col: VBoxContainer = VBoxContainer.new()
	clock_col.add_theme_constant_override("separation", 0)
	_clock_panel.add_child(clock_col)

	_clock_header = PanelContainer.new()
	_clock_header.add_theme_stylebox_override("panel", _flat_box(BG_NAVY, CYAN, 4, 0, 0, 2, 10, 12, 4, 4))
	var hdr_row: HBoxContainer = HBoxContainer.new()
	hdr_row.add_theme_constant_override("separation", 12)
	_clock_header.add_child(hdr_row)
	_clock_caption = _styled_label(13, CYAN, true, true)
	_clock_status = _styled_label(11, TEXT_MUTED, true)
	_clock_status.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_clock_status.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	hdr_row.add_child(_clock_caption)
	hdr_row.add_child(_clock_status)
	clock_col.add_child(_clock_header)

	_clock_plate = PanelContainer.new()
	_clock_label = _styled_label(38, Color.WHITE, true, true)
	_clock_label.custom_minimum_size = Vector2(188.0, 0.0)
	_clock_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	_clock_plate.add_child(_clock_label)
	_set_clock_plate_style(false)
	clock_col.add_child(_clock_plate)
	_tv_stack.add_child(_clock_panel)

	_wind_panel = PanelContainer.new()
	_wind_panel.add_theme_stylebox_override("panel", _flat_box(BG_NAVY, MAGENTA, 4, 0, 0, 0, 10, 12, 4, 4))
	_wind_label = _styled_label(15, Color.WHITE, true)
	_wind_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	_wind_panel.add_child(_wind_label)
	_wind_panel.visible = false
	_tv_stack.add_child(_wind_panel)

	$Root.add_child(_tv_stack)

	# Pannello risultati broadcast in basso a sinistra
	_result_panel = PanelContainer.new()
	_result_panel.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_LEFT)
	_result_panel.grow_vertical = Control.GROW_DIRECTION_BEGIN
	_result_panel.offset_left = 18.0
	_result_panel.offset_bottom = -48.0
	_result_panel.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_result_panel.add_theme_stylebox_override("panel", _flat_box(Color.TRANSPARENT, Color.TRANSPARENT, 0, 0, 0, 0, 0, 0, 0, 0))

	var res_col: VBoxContainer = VBoxContainer.new()
	res_col.add_theme_constant_override("separation", 3)
	_result_panel.add_child(res_col)

	var top_bar: PanelContainer = PanelContainer.new()
	top_bar.add_theme_stylebox_override("panel", _flat_box(BG_NAVY, MAGENTA, 5, 0, 0, 0, 12, 14, 5, 5))
	_result_event = _styled_label(13, Color.WHITE, true, true)
	top_bar.add_child(_result_event)
	res_col.add_child(top_bar)

	var sub_bar: PanelContainer = PanelContainer.new()
	sub_bar.add_theme_stylebox_override("panel", _flat_box(CYAN, Color.TRANSPARENT, 0, 0, 0, 0, 12, 14, 3, 3))
	_result_title = _styled_label(12, TEXT_DARK, true, true)
	sub_bar.add_child(_result_title)
	res_col.add_child(sub_bar)

	for i in range(5):
		var row_bg: PanelContainer = PanelContainer.new()
		row_bg.add_theme_stylebox_override("panel", _flat_box(BG_NAVY_ALT, Color.TRANSPARENT, 0, 0, 0, 0, 4, 12, 4, 4, 2))

		var box: HBoxContainer = HBoxContainer.new()
		box.add_theme_constant_override("separation", 10)
		row_bg.add_child(box)

		var place_bg: PanelContainer = PanelContainer.new()
		place_bg.custom_minimum_size = Vector2(28.0, 24.0)
		var place: Label = _styled_label(15, Color.WHITE, true, true)
		place.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		place.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
		place_bg.add_child(place)

		var stripe: ColorRect = ColorRect.new()
		stripe.custom_minimum_size = Vector2(4.0, 22.0)
		stripe.size_flags_vertical = Control.SIZE_SHRINK_CENTER

		var name_label: Label = _styled_label(17, Color.WHITE, true)
		name_label.custom_minimum_size = Vector2(220.0, 0.0)

		var value: Label = _styled_label(17, Color.WHITE, true, true)
		value.custom_minimum_size = Vector2(78.0, 0.0)
		value.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT

		for c: Control in [place_bg, stripe, name_label, value]:
			box.add_child(c)
		res_col.add_child(row_bg)
		_result_rows.append({"box": row_bg, "bg": row_bg, "place_bg": place_bg, "place": place, "stripe": stripe, "name": name_label, "value": value})

	_result_panel.visible = false
	$Root.add_child(_result_panel)
	_build_final_board()


func _build_replay_badge() -> void:
	_replay_panel = PanelContainer.new()
	_replay_panel.set_anchors_and_offsets_preset(Control.PRESET_CENTER_TOP)
	_replay_panel.grow_horizontal = Control.GROW_DIRECTION_BOTH
	_replay_panel.offset_top = 22.0
	_replay_panel.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_replay_panel.add_theme_stylebox_override("panel", _flat_box(MAGENTA, Color.WHITE, 0, 0, 0, 3, 22, 22, 7, 7, 3))
	var row: HBoxContainer = HBoxContainer.new()
	row.add_theme_constant_override("separation", 12)
	_replay_panel.add_child(row)
	var title: Label = _styled_label(24, Color.WHITE, true, true)
	title.text = "RALENTI"
	var sub: Label = _styled_label(13, Color(1.0, 0.86, 0.93), true)
	sub.text = "ARRIVO"
	sub.size_flags_vertical = Control.SIZE_SHRINK_END
	row.add_child(title)
	row.add_child(sub)
	_replay_panel.visible = false
	$Root.add_child(_replay_panel)


func _build_final_board() -> void:
	_final_panel = PanelContainer.new()
	_final_panel.set_anchors_and_offsets_preset(Control.PRESET_CENTER)
	_final_panel.grow_horizontal = Control.GROW_DIRECTION_BOTH
	_final_panel.grow_vertical = Control.GROW_DIRECTION_BOTH
	_final_panel.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_final_panel.add_theme_stylebox_override("panel", _flat_box(Color.TRANSPARENT, Color.TRANSPARENT, 0, 0, 0, 0, 0, 0, 0, 0))

	var col: VBoxContainer = VBoxContainer.new()
	col.add_theme_constant_override("separation", 3)
	_final_panel.add_child(col)

	var top_bar: PanelContainer = PanelContainer.new()
	top_bar.add_theme_stylebox_override("panel", _flat_box(BG_NAVY, MAGENTA, 6, 0, 0, 0, 16, 18, 8, 8))
	_final_event = _styled_label(20, Color.WHITE, true, true)
	top_bar.add_child(_final_event)
	col.add_child(top_bar)

	var sub_bar: PanelContainer = PanelContainer.new()
	sub_bar.add_theme_stylebox_override("panel", _flat_box(CYAN, Color.TRANSPARENT, 0, 0, 0, 0, 16, 18, 4, 4))
	_final_title = _styled_label(15, TEXT_DARK, true, true)
	sub_bar.add_child(_final_title)
	col.add_child(sub_bar)

	for i in range(FINAL_MAX_ROWS):
		var row_bg: PanelContainer = PanelContainer.new()
		row_bg.add_theme_stylebox_override("panel", _flat_box(BG_NAVY_ALT, Color.TRANSPARENT, 0, 0, 0, 0, 6, 16, 5, 5, 2))
		var box: HBoxContainer = HBoxContainer.new()
		box.add_theme_constant_override("separation", 12)
		row_bg.add_child(box)

		var place_bg: PanelContainer = PanelContainer.new()
		place_bg.custom_minimum_size = Vector2(38.0, 30.0)
		var place: Label = _styled_label(20, Color.WHITE, true, true)
		place.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		place.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
		place_bg.add_child(place)

		var stripe: ColorRect = ColorRect.new()
		stripe.custom_minimum_size = Vector2(5.0, 28.0)
		stripe.size_flags_vertical = Control.SIZE_SHRINK_CENTER

		# Pettorale in miniatura (foglio bianco, cifre scure) come sulla canotta
		var bib_chip: PanelContainer = PanelContainer.new()
		bib_chip.add_theme_stylebox_override("panel", _flat_box(BG_WHITE, Color.TRANSPARENT, 0, 0, 0, 0, 6, 6, 1, 1, 2))
		bib_chip.custom_minimum_size = Vector2(58.0, 0.0)
		var bib: Label = _styled_label(17, TEXT_DARK, true, true)
		bib.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		bib_chip.add_child(bib)
		var name_label: Label = _styled_label(22, Color.WHITE, true)
		name_label.custom_minimum_size = Vector2(300.0, 0.0)
		var team: Label = _styled_label(14, TEXT_MUTED, true)
		team.custom_minimum_size = Vector2(170.0, 0.0)
		team.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
		var lane: Label = _styled_label(14, TEXT_MUTED, true)
		lane.custom_minimum_size = Vector2(44.0, 0.0)
		lane.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
		var value: Label = _styled_label(24, Color.WHITE, true, true)
		value.custom_minimum_size = Vector2(110.0, 0.0)
		value.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT

		for c: Control in [place_bg, stripe, bib_chip, name_label, team, lane, value]:
			box.add_child(c)
		col.add_child(row_bg)
		_final_rows.append({"box": row_bg, "place_bg": place_bg, "place": place, "stripe": stripe, "bib_chip": bib_chip, "bib": bib,
			"name": name_label, "team": team, "lane": lane, "value": value})

	_final_panel.visible = false
	$Root.add_child(_final_panel)


## Riempie e mostra la classifica finale solo a gara conclusa (RaceController.State.FINISHED); non decide nulla,
## legge l'ordine gia' calcolato dal controller.
func _update_final_board() -> void:
	var rc: Node = RaceController
	var show: bool = rc.state == rc.State.FINISHED and not rc.live_order.is_empty()
	_final_panel.visible = show
	if not show:
		return
	var field: bool = rc.is_field(rc.event_kind)
	var relay: bool = rc.is_relay(rc.event_kind)
	_set_text(_final_title, "CLASSIFICA FINALE" if field else "ORDINE D'ARRIVO")
	var shown: int = 0
	var place_no: int = 0
	for r: RunnerData in rc.live_order:
		if shown >= _final_rows.size():
			break
		var out: bool = r.dnf and not field
		if not out:
			place_no += 1
		var row: Dictionary = _final_rows[shown]
		var value: String
		if field:
			value = "%.2f m" % r.best_mark if r.best_mark > 0.0 else "NM"
		elif out:
			value = "SQ." if r.dq else "RIT."
		else:
			value = rc.format_time(r.final_time)
		_set_text(row["place"], "-" if out else str(place_no))
		_set_text(row["name"], r.team_name.to_upper() if relay else r.athlete_name.to_upper())
		_set_text(row["bib"], str(r.bib) if r.bib > 0 else "")
		(row["bib_chip"] as Control).visible = r.bib > 0
		_set_text(row["team"], "" if relay else r.team_name)
		_set_text(row["lane"], "" if field else "C%d" % r.lane)
		_set_text(row["value"], value)
		(row["stripe"] as ColorRect).color = _team_color(r.team_name)
		var is_first: bool = place_no == 1 and not out
		(row["place_bg"] as PanelContainer).add_theme_stylebox_override(
			"panel", _flat_box(CYAN if is_first else Color(0.14, 0.19, 0.38), Color.TRANSPARENT, 0, 0, 0, 0, 4, 4, 1, 1, 2))
		(row["place"] as Label).add_theme_color_override("font_color", TEXT_DARK if is_first else Color.WHITE)
		(row["box"] as PanelContainer).add_theme_stylebox_override(
			"panel", _flat_box(PLAYER_ROW_BG if r.is_player else BG_NAVY_ALT, Color.TRANSPARENT, 0, 0, 0, 0, 6, 16, 5, 5, 2))
		(row["name"] as Label).add_theme_color_override("font_color", PLAYER_COLOR if r.is_player else (TEXT_MUTED if out else Color.WHITE))
		(row["value"] as Label).add_theme_color_override("font_color", AMBER if out else Color.WHITE)
		shown += 1
	for i in range(_final_rows.size()):
		(_final_rows[i]["box"] as Control).visible = i < shown


func _set_clock_plate_style(official: bool) -> void:
	if official:
		_clock_plate.add_theme_stylebox_override("panel", _flat_box(BG_WHITE, CYAN, 4, 0, 0, 0, 12, 14, 4, 4))
		_clock_label.add_theme_color_override("font_color", TEXT_DARK)
	else:
		_clock_plate.add_theme_stylebox_override("panel", _flat_box(BG_NAVY_ALT, CYAN, 4, 0, 0, 0, 12, 14, 4, 4))
		_clock_label.add_theme_color_override("font_color", Color.WHITE)


func _update_tv_graphics() -> void:
	var rc: Node = RaceController
	var running: bool = rc.state == rc.State.RUNNING or rc.state == rc.State.FINISHED
	_clock_panel.visible = running
	if rc.is_field(rc.event_kind):
		var done_field: bool = rc.state == rc.State.FINISHED
		if done_field != _last_clock_official:
			_last_clock_official = done_field
			_set_clock_plate_style(done_field)
		_set_text(_clock_caption, "%s%s" % [_bug_category_prefix, str(rc.info.get("event_name", "")).to_upper()])
		_set_text(_clock_status, rc.field_caption)
		if rc.field_value_text != _last_clock_text:
			_last_clock_text = rc.field_value_text
			_clock_label.text = rc.field_value_text
	else:
		_set_text(_clock_caption, "%s%s" % [_bug_category_prefix, str(rc.info.get("event_name", "")).to_upper()])
		if running:
			var winner_in: bool = not rc.live_order.is_empty() and rc.live_order[0].finished
			if winner_in != _last_clock_official:
				_last_clock_official = winner_in
				_set_clock_plate_style(winner_in)
			_set_text(_clock_status, "ARRIVO" if winner_in else "TEMPO")
			# In gara i decimi (troncati: non superano mai il tempo del vincitore), all'arrivo i centesimi.
			var truncated: float = floorf(rc.display_time * 10.0) / 10.0
			var text: String
			if winner_in:
				text = rc.format_time(rc.display_time)
			elif truncated >= 60.0:
				var mins: int = int(truncated / 60.0)
				var rem: float = truncated - float(mins) * 60.0
				text = "%d:%04.1f" % [mins, rem]
			else:
				text = "%.1f" % truncated
			if text != _last_clock_text:
				_last_clock_text = text
				_clock_label.text = text

	var leader_done: bool = running and not rc.live_order.is_empty() and rc.live_order[0].finished
	var wind: Variant = rc.info.get("wind_ms", null)
	_wind_panel.visible = (running if rc.is_field(rc.event_kind) else leader_done) and (rc.event_kind == "100m" or rc.event_kind == "Salto in Lungo") and wind != null
	if _wind_panel.visible:
		var w: float = float(wind)
		var wind_note: String = "  (N.O.)" if w > 2.0 else ""
		_set_text(_wind_label, "VENTO  %+.1f m/s%s" % [w, wind_note])
		_wind_label.add_theme_color_override("font_color", AMBER if w > 2.0 else Color.WHITE)

	# A gara conclusa la classifica completa a centro schermo sostituisce il piccolo pannello in basso a sinistra.
	_result_panel.visible = rc.state != rc.State.FINISHED and leader_done and not rc.is_field(rc.event_kind) \
		and rc.race_time > rc.live_order[0].final_time + 1.0
	_update_final_board()
	_replay_panel.visible = rc.state == rc.State.REPLAY
	if _result_panel.visible:
		_set_text(_result_title, "RISULTATO NON UFFICIALE" if rc.state == rc.State.RUNNING else "ORDINE D'ARRIVO")
		var shown: int = 0
		for r: RunnerData in rc.live_order:
			if not r.finished or shown >= _result_rows.size():
				continue
			var row: Dictionary = _result_rows[shown]
			var rname: String = r.team_name.to_upper() if rc.is_relay(rc.event_kind) else r.athlete_name.to_upper()
			_set_text(row["place"], str(r.place))
			_set_text(row["name"], rname)
			_set_text(row["value"], ("%.2f m" % r.final_time) if rc.is_field(rc.event_kind) else rc.format_time(r.final_time))
			(row["stripe"] as ColorRect).color = _team_color(r.team_name)
			var is_first: bool = r.place == 1
			(row["place_bg"] as PanelContainer).add_theme_stylebox_override(
				"panel", _flat_box(CYAN if is_first else Color(0.14, 0.19, 0.38), Color.TRANSPARENT, 0, 0, 0, 0, 4, 4, 1, 1, 2))
			(row["place"] as Label).add_theme_color_override("font_color", TEXT_DARK if is_first else Color.WHITE)
			(row["bg"] as PanelContainer).add_theme_stylebox_override(
				"panel", _flat_box(PLAYER_ROW_BG if r.is_player else BG_NAVY_ALT, Color.TRANSPARENT, 0, 0, 0, 0, 4, 12, 4, 4, 2))
			(row["name"] as Label).add_theme_color_override("font_color", PLAYER_COLOR if r.is_player else Color.WHITE)
			shown += 1
		for i in range(_result_rows.size()):
			(_result_rows[i]["box"] as Control).visible = i < shown


# --- helper -------------------------------------------------------------------------------------

func _flat_box(
	bg: Color,
	border: Color,
	bl: int,
	bt: int,
	br: int,
	bb: int,
	ml: float,
	mr: float,
	mt: float,
	mb: float,
	radius: int = 2
) -> StyleBoxFlat:
	var s: StyleBoxFlat = StyleBoxFlat.new()
	s.bg_color = bg
	s.border_color = border
	s.border_width_left = bl
	s.border_width_top = bt
	s.border_width_right = br
	s.border_width_bottom = bb
	s.set_corner_radius_all(radius)
	s.content_margin_left = ml
	s.content_margin_right = mr
	s.content_margin_top = mt
	s.content_margin_bottom = mb
	return s


func _styled_label(size: int, color: Color, bold: bool = false, heavy: bool = false) -> Label:
	var l: Label = Label.new()
	l.add_theme_font_override("font", _font_heavy if heavy else (_font_bold if bold else _font_regular))
	l.add_theme_font_size_override("font_size", size)
	l.add_theme_color_override("font_color", color)
	return l


func _team_color(team: String) -> Color:
	return Color.from_hsv(float(absi(hash(team)) % 360) / 360.0, 0.75, 0.9)


func _set_text(label: Label, text: String) -> void:
	if label.text != text:
		label.text = text
