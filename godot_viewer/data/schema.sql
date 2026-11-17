-- Schema dei risultati pre-calcolati letti da Godot (sola lettura).
-- Il motore Python (models/simulation.py) decide tutto: Godot non cambia mai tempi o ordine.
-- final_time e' il tempo UFFICIALE e include reaction_time (come nel modello Python).
-- status = 'DNF' (ritirato): final_time e' solo un tempo di riferimento per la velocita' di corsa;
-- il corridore si ferma a DNF_STOP_DISTANCE metri e non entra nella classifica d'arrivo.

CREATE TABLE IF NOT EXISTS races (
    race_id INTEGER PRIMARY KEY,
    event_name TEXT NOT NULL,
    meet_name TEXT NOT NULL,
    distance_m REAL NOT NULL DEFAULT 100,
    wind_ms REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS race_results (
    race_id INTEGER NOT NULL REFERENCES races(race_id),
    lane INTEGER NOT NULL CHECK (lane BETWEEN 1 AND 9),
    athlete_name TEXT NOT NULL,
    team_name TEXT NOT NULL DEFAULT '',
    gender TEXT NOT NULL DEFAULT 'M' CHECK (gender IN ('M', 'F')),
    is_player INTEGER NOT NULL DEFAULT 0,
    reaction_time REAL NOT NULL CHECK (reaction_time > 0),
    final_time REAL NOT NULL CHECK (final_time > reaction_time),
    status TEXT NOT NULL DEFAULT 'OK' CHECK (status IN ('OK', 'DNF')),
    PRIMARY KEY (race_id, lane)
);
