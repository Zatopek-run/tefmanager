-- Gara dimostrativa (atleti e squadre di fantasia). Solo per provare il visualizzatore.

INSERT OR REPLACE INTO races (race_id, event_name, meet_name, distance_m, wind_ms)
VALUES (1, '100m', 'Meeting Internazionale di Prova', 100, 0.8);

INSERT OR REPLACE INTO race_results (race_id, lane, athlete_name, team_name, is_player, reaction_time, final_time) VALUES
(1, 1, 'Dario Conti',      'Atletica Brera',    0, 0.158, 10.19),
(1, 2, 'Luca Ferrante',    'Polisportiva Nord', 0, 0.171, 10.05),
(1, 3, 'Marco Valenti',    'Club Aurora',       1, 0.139, 9.93),
(1, 4, 'Ivo Salvetti',     'Atletica Brera',    0, 0.186, 10.11),
(1, 5, 'Tomas Reinholt',   'Nordic Track',      0, 0.142, 9.87),
(1, 6, 'Paulo Mendes',     'Clube Atlantico',   0, 0.163, 10.02),
(1, 7, 'Kenji Arakawa',    'Sakura AC',         0, 0.121, 9.95),
(1, 8, 'Elias Ndlovu',     'Highveld Harriers', 0, 0.198, 10.34);

-- Gara 2: come la 1, ma il corridore del club si ritira per infortunio (DNF).
INSERT OR REPLACE INTO races (race_id, event_name, meet_name, distance_m, wind_ms)
VALUES (2, '100m', 'Meeting di Prova (ritiro)', 100, -0.4);

INSERT OR REPLACE INTO race_results (race_id, lane, athlete_name, team_name, is_player, reaction_time, final_time, status) VALUES
(2, 1, 'Dario Conti',      'Atletica Brera',    0, 0.158, 10.19, 'OK'),
(2, 2, 'Luca Ferrante',    'Polisportiva Nord', 0, 0.171, 10.05, 'OK'),
(2, 3, 'Marco Valenti',    'Club Aurora',       1, 0.139, 10.00, 'DNF'),
(2, 4, 'Ivo Salvetti',     'Atletica Brera',    0, 0.186, 10.11, 'OK'),
(2, 5, 'Tomas Reinholt',   'Nordic Track',      0, 0.142, 9.87,  'OK'),
(2, 6, 'Paulo Mendes',     'Clube Atlantico',   0, 0.163, 10.02, 'OK');

-- Gara 3: 400m (partenza sfalsata sull'ovale).
INSERT OR REPLACE INTO races (race_id, event_name, meet_name, distance_m, wind_ms)
VALUES (3, '400m', 'Meeting Internazionale di Prova', 400, 0);

INSERT OR REPLACE INTO race_results (race_id, lane, athlete_name, team_name, is_player, reaction_time, final_time) VALUES
(3, 1, 'Dario Conti',      'Atletica Brera',    0, 0.158, 46.91),
(3, 2, 'Luca Ferrante',    'Polisportiva Nord', 0, 0.171, 46.35),
(3, 3, 'Marco Valenti',    'Club Aurora',       1, 0.139, 45.80),
(3, 4, 'Ivo Salvetti',     'Atletica Brera',    0, 0.186, 46.62),
(3, 5, 'Tomas Reinholt',   'Nordic Track',      0, 0.142, 45.12),
(3, 6, 'Paulo Mendes',     'Clube Atlantico',   0, 0.163, 45.57),
(3, 7, 'Kenji Arakawa',    'Sakura AC',         0, 0.121, 45.33),
(3, 8, 'Elias Ndlovu',     'Highveld Harriers', 0, 0.198, 47.48);

-- Gara 4: 400m con il corridore del club ritirato (DNF) a meta' gara.
INSERT OR REPLACE INTO races (race_id, event_name, meet_name, distance_m, wind_ms)
VALUES (4, '400m', 'Meeting di Prova (ritiro 400m)', 400, 0);

INSERT OR REPLACE INTO race_results (race_id, lane, athlete_name, team_name, is_player, reaction_time, final_time, status) VALUES
(4, 2, 'Luca Ferrante',    'Polisportiva Nord', 0, 0.171, 46.35, 'OK'),
(4, 3, 'Marco Valenti',    'Club Aurora',       1, 0.139, 46.00, 'DNF'),
(4, 4, 'Ivo Salvetti',     'Atletica Brera',    0, 0.186, 46.62, 'OK'),
(4, 5, 'Tomas Reinholt',   'Nordic Track',      0, 0.142, 45.12, 'OK'),
(4, 6, 'Paulo Mendes',     'Clube Atlantico',   0, 0.163, 45.57, 'OK');

-- Gara 5: 1500m Maschile (partenza in piedi e 3,75 giri sull'ovale).
INSERT OR REPLACE INTO races (race_id, event_name, meet_name, distance_m, wind_ms)
VALUES (5, '1500m', 'Meeting Internazionale di Prova', 1500, 0);

INSERT OR REPLACE INTO race_results (race_id, lane, athlete_name, team_name, gender, is_player, reaction_time, final_time, status) VALUES
(5, 1, 'Dario Conti',      'Atletica Brera',    'M', 0, 0.160, 236.40, 'OK'),
(5, 2, 'Luca Ferrante',    'Polisportiva Nord', 'M', 0, 0.175, 234.85, 'OK'),
(5, 3, 'Marco Valenti',    'Club Aurora',       'M', 1, 0.145, 233.12, 'OK'),
(5, 4, 'Ivo Salvetti',     'Atletica Brera',    'M', 0, 0.180, 235.90, 'OK'),
(5, 5, 'Tomas Reinholt',   'Nordic Track',      'M', 0, 0.142, 232.15, 'OK'),
(5, 6, 'Paulo Mendes',     'Clube Atlantico',   'M', 0, 0.165, 234.10, 'OK'),
(5, 7, 'Kenji Arakawa',    'Sakura AC',         'M', 0, 0.138, 232.95, 'OK'),
(5, 8, 'Elias Ndlovu',     'Highveld Harriers', 'M', 0, 0.190, 237.20, 'OK');

-- Gara 6: 1500m Femminile.
INSERT OR REPLACE INTO races (race_id, event_name, meet_name, distance_m, wind_ms)
VALUES (6, '1500m', 'Meeting Internazionale di Prova', 1500, 0);

INSERT OR REPLACE INTO race_results (race_id, lane, athlete_name, team_name, gender, is_player, reaction_time, final_time, status) VALUES
(6, 1, 'Giulia Conti',     'Atletica Brera',    'F', 0, 0.162, 256.80, 'OK'),
(6, 2, 'Nadia Moretti',    'Polisportiva Nord', 'F', 0, 0.171, 255.10, 'OK'),
(6, 3, 'Viola Ferri',      'Club Aurora',       'F', 1, 0.148, 253.45, 'OK'),
(6, 4, 'Elena Fontana',    'Atletica Brera',    'F', 0, 0.182, 256.20, 'OK'),
(6, 5, 'Astrid Lindqvist', 'Nordic Track',      'F', 0, 0.144, 252.30, 'OK'),
(6, 6, 'Sofia Carvalho',   'Clube Atlantico',   'F', 0, 0.168, 254.60, 'OK'),
(6, 7, 'Yuki Tanaka',      'Sakura AC',         'F', 0, 0.140, 253.05, 'OK'),
(6, 8, 'Amara Diallo',     'Highveld Harriers', 'F', 0, 0.192, 257.40, 'OK');
