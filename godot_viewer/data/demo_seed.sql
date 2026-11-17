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
