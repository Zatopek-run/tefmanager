class_name RunnerData
extends RefCounted
## Dati di un corridore: la parte "persistente" arriva dal DB (sola lettura),
## la parte "runtime" viene riscritta a ogni fotogramma da RaceController.

# --- dal database (immutabili dopo il caricamento) ---
var athlete_name: String = ""
var team_name: String = ""
var gender: String = "M"
var lane: int = 1
var bib: int = 0                # numero di pettorale (0 = nessuno): lo assegna Python, vedi models/bibs.py
var is_player: bool = false
var reaction_time: float = 0.0  # secondi, incluso nel tempo ufficiale
var final_time: float = 0.0     # tempo ufficiale dallo sparo
var place: int = 0              # 1 = vincitore, deciso da final_time (i ritirati/squalificati vengono dopo)
var dnf: bool = false           # ritirato o squalificato: si ferma prima e non taglia il traguardo
var dq: bool = false            # squalificato (staffetta: cambio fuori zona)
var pace_style: float = 0.0     # stile di passo in [-1, 1] (solo messa in scena, lo decide Python): > 0 parte forte e cala, < 0 chiude forte
var leg_styles: PackedFloat64Array = PackedFloat64Array()  # staffette (Q41c): stili delle 4 frazioni in [-1, 1], vuoto per le altre gare (solo messa in scena)

# --- runtime ---
var distance: float = 0.0       # metri dalla linea di partenza (oltre 100 = lancio dopo il traguardo)
var speed: float = 0.0          # m/s
var finished: bool = false
var lateral: float = -1.0       # 800m/1500m: scostamento dalla corda (m) deciso dalla formazione del gruppo (PackFormation), -1 = regola di sempre
var attempts: Array = []        # concorsi: [{"round": 1..4, "mark": float, "foul": bool}, ...]
var best_mark: float = 0.0
var revealed_rounds: int = 0


static func from_row(row: Dictionary) -> RunnerData:
	var r: RunnerData = RunnerData.new()
	r.athlete_name = str(row.get("athlete_name", ""))
	r.team_name = str(row.get("team_name", ""))
	r.gender = str(row.get("gender", "M")).to_upper()
	r.lane = int(row.get("lane", 1))
	r.bib = maxi(0, int(row.get("bib", 0)))
	r.is_player = int(row.get("is_player", 0)) != 0
	r.reaction_time = float(row.get("reaction_time", 0.0))
	r.final_time = float(row.get("final_time", 0.0))
	var st: String = str(row.get("status", "OK"))
	r.dq = st == "DQ"
	r.dnf = st == "DNF" or r.dq
	r.pace_style = clampf(float(row.get("pace_style", 0.0)), -1.0, 1.0)
	r.leg_styles = parse_leg_styles(str(row.get("leg_styles", "")))
	return r


## Stili per frazione dalla colonna `leg_styles` (4 numeri separati da virgola). Qualunque cosa diversa da 4 numeri validi = nessuno stile (come un DB senza la colonna).
static func parse_leg_styles(text: String) -> PackedFloat64Array:
	var out: PackedFloat64Array = PackedFloat64Array()
	var parts: PackedStringArray = text.split(",", false)
	if parts.size() != 4:
		return out
	for p: String in parts:
		if not p.strip_edges().is_valid_float():
			return PackedFloat64Array()
		out.append(clampf(p.strip_edges().to_float(), -1.0, 1.0))
	return out


## Lo stile da passare a RaceMotion: i 4 stili per frazione di una staffetta se ci sono, altrimenti il numero di sempre.
func motion_style() -> Variant:
	if leg_styles.size() > 0:
		return leg_styles
	return pace_style


func is_valid() -> bool:
	return lane >= 1 and reaction_time > 0.0 and final_time > reaction_time


## Altezza visiva (m) del modello 3D di un atleta: deterministica dal nome (hash di stringa di Godot, stabile fra le
## esecuzioni). Unica fonte per `RunnerView` (scala del modello) e per `ShotPutMotion` (punto di rilascio del peso).
static func visual_height(visual_key: String, gender: String) -> float:
	var base_h: float = 1.63 if gender == "F" else 1.72
	return base_h + float(absi(hash(visual_key + "height")) % 15) / 100.0


func surname() -> String:
	var parts: PackedStringArray = athlete_name.split(" ", false)
	return parts[parts.size() - 1].to_upper() if parts.size() > 0 else "?"
