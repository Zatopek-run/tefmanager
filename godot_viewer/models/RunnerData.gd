class_name RunnerData
extends RefCounted
## Dati di un corridore: la parte "persistente" arriva dal DB (sola lettura),
## la parte "runtime" viene riscritta a ogni fotogramma da RaceController.

# --- dal database (immutabili dopo il caricamento) ---
var athlete_name: String = ""
var team_name: String = ""
var gender: String = "M"
var lane: int = 1
var is_player: bool = false
var reaction_time: float = 0.0  # secondi, incluso nel tempo ufficiale
var final_time: float = 0.0     # tempo ufficiale dallo sparo
var place: int = 0              # 1 = vincitore, deciso da final_time (i ritirati vengono dopo i classificati)
var dnf: bool = false           # ritirato: si ferma a DNF_STOP_DISTANCE e non taglia il traguardo

# --- runtime ---
var distance: float = 0.0       # metri dalla linea di partenza (oltre 100 = lancio dopo il traguardo)
var speed: float = 0.0          # m/s
var finished: bool = false


static func from_row(row: Dictionary) -> RunnerData:
	var r: RunnerData = RunnerData.new()
	r.athlete_name = str(row.get("athlete_name", ""))
	r.team_name = str(row.get("team_name", ""))
	r.gender = str(row.get("gender", "M")).to_upper()
	r.lane = int(row.get("lane", 1))
	r.is_player = int(row.get("is_player", 0)) != 0
	r.reaction_time = float(row.get("reaction_time", 0.0))
	r.final_time = float(row.get("final_time", 0.0))
	r.dnf = str(row.get("status", "OK")) == "DNF"
	return r


func is_valid() -> bool:
	return lane >= 1 and reaction_time > 0.0 and final_time > reaction_time


func surname() -> String:
	var parts: PackedStringArray = athlete_name.split(" ", false)
	return parts[parts.size() - 1].to_upper() if parts.size() > 0 else "?"
