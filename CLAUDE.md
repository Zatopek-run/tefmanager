# Track & Field Manager — note per Claude

Gestionale di atletica desktop in **Python + PyQt6 + SQLite**, architettura **MVC**. Interfaccia, testi e
commenti sono in **italiano**: mantieni la lingua (nomi di variabili e codice in inglese).

## Comandi

```bash
pip install -r requirements.txt            # PyQt6, pyinstaller
python main.py                             # avvia l'app
python -m unittest tests.test_game         # tutta la suite (offscreen, ~3 s)
```

- I test impostano `QT_QPA_PLATFORM=offscreen`. In un container Linux pulito PyQt6 può mancare di librerie di
  sistema: servono `libegl1 libgl1 libxkbcommon0 libfontconfig1 libdbus-1-3` (`apt-get update` prima).
- **Non chiamare `exec()` di dialoghi modali** in script o test: bloccano per sempre in offscreen. Nei test si
  istanziano i dialoghi e si chiamano i metodi (`_skip_race`, `_next`, …) oppure si sostituiscono con finti.

## Struttura

```text
models/      entities.py (GameState, Athlete, eventi, enum)   generator.py (atleti, corpo, nazionalità)
             simulation.py (allenamento, gare, punteggi)       database.py (SQLite, migrazioni)
controllers/ game_controller.py   segnali Qt che collegano modello e viste
views/       main_window.py  tabs.py  dialogs.py  styles.py (QSS scuro)
             athlete_dialog.py  Scheda Atleta
             race_viewer.py     Gare in diretta (modello di movimento, 2D, concorsi, dialog)
             race_3d.py         vista 3D software delle corse in pista
tests/       test_game.py
```

## Decisioni e regole da rispettare

- **L'esito delle gare lo decide solo il modello** (`models/simulation.py`). Le viste *mettono in scena* un
  `CompetitionSummary` già calcolato: non cambiano tempi, ordine o misure. Ogni atleta taglia il traguardo
  esattamente al suo `mark_value` (c'è un test). Le singole prove dei concorsi sono ricavate dal risultato
  finale con un generatore deterministico (`generate_attempts`).
- **Nessun "button mashing"** né comandi interattivi in gara: cambierebbero un risultato già simulato. Sarebbe
  una scelta di gioco da discutere con l'utente, non da introdurre di nascosto.
- **Grafica originale.** Lo stile è ispirato ai giochi arcade di atletica, ma niente nomi, sprite, layout o
  sponsor presi da giochi esistenti. I cartelloni usano sponsor di fantasia.
- **Fisico e simulazione.** Altezza, peso e nazionalità sono generati per disciplina (`generator.py`). Ogni
  gara ha un fisico ideale (`BODY_IDEALS` in `simulation.py`): lo scarto sposta il punteggio atteso tra +1,2 e −4
  e il valore dei frazionisti (peso dimezzato). Atleti senza dati fisici (vecchi salvataggi non ancora
  riempiti) restano neutri.
- **Curve punteggio → misura** (`_score_to_mark`). Una retta per evento e sesso, tarata sulle ancore di livello:
  score 42 provinciale, 56 regionale, 66 vincitore regionale, 70 nazionale, 84 internazionale; i test
  `test_*_matches_fidal_ranges` le fissano con fasce larghe. 100m, 400m, 1500m, lungo e peso sono tarati, le
  staffette (`_relay_mark`) no. Il tetto è il record del mondo, applicato dopo il vento. Le ancore alte di lungo e
  peso vengono da dati reali (Assoluti 2025, Lazio regionali 2025); provinciale e media regionale di lungo e peso
  sono **stime**, dichiarate come tali nei commenti dei test: sostituiscile se trovi dati FIDAL veri. I
  `historic_mark` in `entities.py` non sono stati ritoccati: con le nuove curve lungo/peso richiedono score più
  alti (es. peso M 18 m ≈ score 76, prima ≈ 62).
- **Salvataggi.** `SCHEMA_VERSION = 7`. Ogni nuova colonna va aggiunta in `database.py` con una voce in
  `MIGRATIONS` (le colonne nuove con `DEFAULT`) *e* nella `CREATE TABLE`; `_drop_columns_after` nei test usa
  `MIGRATIONS` per simulare i vecchi salvataggi. I campi mancanti dei vecchi salvataggi si riempiono al
  caricamento in modo deterministico (es. `_backfill_bodies`, seed = id atleta).

## Gare in diretta (`views/race_viewer.py`, `views/race_3d.py`)

- Si apre da `MainWindow._show_competition_results` prima dei risultati, solo se il meeting ha gare.
- **Modello di movimento** (funzioni pure, testate): `curve_progress`, `position_fraction`, `reaction_time`.
  Curva di velocità per gara (100m, 400m, 1500m, staffetta). `position_fraction` vale esattamente 1 a
  `t = mark_value`; il tempo di reazione (0,12–0,22 s) è incluso nel tempo ufficiale.
- **Tempo**: `TrackRaceWidget._t` è tempo di animazione (include la partenza, `GUN_AT = 2.4 s`);
  `race_time` è tempo di gara dallo sparo (`× _scale` per comprimere 400m/1500m/staffette). Il cronometro si
  blocca sul tempo del vincitore.
- **Viste**: `TrackRaceWidget` (2D laterale), `Track3DWidget` (sottoclasse: sovrascrive solo `paintEvent` e usa
  `meters()`, `fraction()`, `race_time`, … della base). Il dialog tiene `track2d`/`track3d`; `dlg.track` è
  quella attiva (3D di default) e `_toggle_view` passa dall'una all'altra mantenendo il punto della gara.
  `race_3d` è importato in modo tardivo da `race_viewer` per evitare l'import circolare.
- **Concorsi**: `FieldEventWidget` = scena (`FieldSceneWidget`) + tabellone (`FieldBoardWidget`). Solo le prove
  dell'atleta del club sono animate per intero, le altre scorrono veloci (gara sotto i ~45 s).
- Controlli: pausa, velocità 1x/2x/4x, vista 2D/3D, "Salta alla fine" (funziona anche durante il conto alla
  rovescia), "Prossima gara", "Vai ai risultati".

### Vista 3D software (`race_3d.py`)

Motore 3D minimo con `QPainter`: nessun OpenGL, nessuna dipendenza in più (OpenGL/Qt3D non sono disponibili nei
container di sviluppo e non sarebbero testabili).

- Mondo: `x` lungo la pista, `y` in alto, `z` attraverso le corsie (1,22 m l'una). `Camera` a foro stenopeico.
- **Ogni poligono passa da `clip_near`** (taglio contro il piano vicino): senza, un vertice dietro la camera
  proietta al contrario e riempie lo schermo. I cartelloni con texture (`quadToQuad`) si saltano se un angolo è
  troppo vicino. In PyQt6 `QTransform.quadToQuad(src, dst, result)` scrive nel terzo argomento.
- Ordine di disegno: cielo → tribune → prato → pista → segni → cartelloni/traguardo → atleti dal più lontano al
  più vicino → HUD 2D (classifica live, cronometro, vento, minimappa, banner).
- **Prestazioni**: antialiasing **spento** per le grandi superfici e acceso solo per atleti e HUD (da ~32 ms a
  ~10 ms a fotogramma). Non riaccenderlo per tribune/prato/pista.
- Costanti di camera in cima al file: `CAM_BACK`, `CAM_SIDE`, `CAM_HEIGHT`, `FOV_DEG`.
- Il 3D copre solo le corse in pista; lungo e peso restano nelle scene 2D.

## Visualizzatore Godot (`godot_viewer/`)

Modulo **separato** in Godot 4.3+ / GDScript (non fa parte dell'app PyQt): mette in scena le gare in pista (100m, 400m, 1500m,
4x100m, 4x400m) e due concorsi (lungo, peso) in stile "diretta TV" 2010 leggendo risultati già calcolati da SQLite (plugin godot-sqlite, in `addons/`, ignorato da git).
Dettagli e valori di luce/camere in `godot_viewer/README.md`.

- **MVC.** Model = `autoload/DatabaseManager.gd` (sola lettura), Controller = `autoload/RaceController.gd`
  (tempo, classifica, segnali), View 3D = `Stadium.tscn` + `scripts/` (`BroadcastCameras`, `RunnerView`),
  View 2D = `HUD.tscn`. Anche qui **le viste non cambiano tempi o ordine**.
- **Contratto con Python.** `godot_viewer/data/schema.sql` è l'unica fonte dello schema (`races`,
  `race_results`, `field_attempts` per le prove dei concorsi); `models/race_export.py` lo riusa per esportare
  (`python -m models.race_export [save.db] [out.db]`, da riga di comando solo i 100m; il gioco esporta ogni evento
  con `export_race`). `race_results.gender` (M/F) sceglie il modello 3D. `final_time` = `mark_value` e **include** `reaction_time`. Corsie sorteggiate in modo deterministico,
  reazione dalla stessa `reaction_time` della vista PyQt.
- **`godot_viewer/models/RaceMotion.gd` è la copia GDScript** di `_velocity`/`curve_progress` di
  `race_viewer.py`: se cambi la curva dei 100m in Python, cambiala anche lì.
- **Verifica (con Godot installato).** `godot --headless --path godot_viewer -s res://tests/verify_race.gd`
  controlla arrivo esatto, ordine e cronometro (esce con codice 0/1); `tests/screenshots.gd` (senza
  `--headless`) salva immagini della scena reale (`-- cartella [close] --race=2`); `tests/verify_input.gd -- --autoquit`
  prova tasti e chiusura automatica. `verify_race.gd` scorre le 12 gare del DB demo (1-2 = 100m con un ritirato,
  3-4 = 400m, 5-6 = 1500m, 7 = 4x100m, 8 = 4x400m con squadra squalificata, 9-10 = lungo, 11-12 = peso), geometria
  inclusa. `verify_pose.gd` gira in `--headless`; `verify_camera.gd` e `verify_input.gd` aprono una finestra vera (serve
  un display; `verify_camera.gd` dura diversi minuti: lanciarlo in background, non con un timeout breve).
  Testato con Godot 4.7.2 (flatpak `org.godotengine.Godot`) + godot-sqlite 4.9; l'import del progetto alla prima
  esecuzione crea file `.uid` (committa quelli dei nuovi script di test).
- **Personaggi.** `RunnerView.gd` usa un modello con scheletro e animazioni CC0 di Quaternius
  (`assets/athlete/`, vedi `CREDITS.md`); abiti ricavati dalla mesh con uno shader. Il modello originale guarda +Z
  e viene ruotato (`FACING_Y`) per correre verso +X.
- **Integrazione nel gioco.** `RaceViewerDialog._next` per gli eventi in `GODOT_EVENTS` chiama
  `views/godot_launcher.py`: esporta la gara (`race_export`) in `~/.track_field_manager/race_results.db`, lancia Godot (`--autoquit`) con
  `QProcess`, mostra una pagina segnaposto e prosegue quando Godot si chiude. **Ripiego sulla vista PyQt
  interna** se manca Godot (`find_godot()` cerca `TEF_GODOT`, `Godot*.exe` nella root, scoop e `godot` nel PATH: **non** vede
  un'installazione flatpak, che richiede un wrapper `godot` nel PATH o `TEF_GODOT`), il progetto o `addons/godot-sqlite/`, se l'export fallisce
  o se Godot esce subito con errore. `TEF_NO_GODOT=1` lo disattiva (impostato in `tests/test_game.py`).
- **Ritirati (DNF).** `race_results.status = 'DNF'`: il corridore corre sulla stessa curva fino a 42 m
  (`RaceMotion.dnf_stop_distance(kind)`), rallenta, si ferma (HUD «RIT.») ed è ultimo; `final_time` è solo un tempo di
  riferimento (mediana degli altri). Più corridori delle 8 corsie → `export_race` solleva `ValueError` e il gioco
  usa la vista interna (mai scarti silenziosi).
- **400m.** Pista ovale: `models/TrackGeometry.gd` (rettilinei 84,39 m, raggio corsia 1 = 36,8 m, corsie da 1,22 m;
  partenza sfalsata `start_offset`, traguardo a x = 0) è l'unica fonte sia per la posizione dei corridori sia per il
  disegno (`scripts/OvalTrackBuilder.gd`). `RaceMotion` ha una curva per evento (`kind`); la distanza è per corsia
  dalla SUA partenza. **Mira delle camere in gara:** le camere che PANORAMICANO (400m: start, rettilineo opposto,
  curva 2) puntano esattamente sul primo (`live_order[0]`), senza ritardo di inseguimento, anche a 8x. Il **carrello
  alto** (100m, rettilineo d'arrivo dei 400m, corsa oltre il traguardo) invece tiene il primo A DESTRA del centro
  (fascia 5–32% della larghezza, come nel video) e inquadra TUTTI i corridori ancora in gara, allontanandosi e
  aprendo l'obiettivo se il gruppo si sparpaglia (`_update_side_cam`). Questo inverte la richiesta precedente
  dell'utente ("primo al centro") per i carrelli: scelta di regia dal riferimento, da confermare con l'utente.
  `tests/verify_camera.gd` lo verifica su una finestra VERA 1280x720 (in `--headless` la finestra è 64x64: una
  tolleranza in pixel sarebbe vuota).
  **Niente compressione del tempo**: si guarda in tempo reale e l'utente accelera con i tasti 1/2/4/8
  (indicatore in basso a destra). `GODOT_EVENTS` in `views/godot_launcher.py` è un elenco esatto: un evento nuovo va
  aggiunto lì, in `race_export.DISTANCES_M` e in `RaceController.GUN_AT_BY_KIND`.
- **Riferimenti video (lavoro guidato dall'utente).** Il 100m e il 400m sono modellati su due dirette TV scaricate in
  `raw/` (cartella ignorata da git; non committare video): 100m di Roma (`lyles_100m_diamond_league.mp4`, pista blu) e
  finale olimpica dei 400m di Parigi 2024 (`400m_reference_C05vAdxXXEI.mp4`, pista viola). Regola del progetto: niente
  loghi, sponsor, emittenti o nomi reali (grafica originale). **Regia** (`BroadcastCameras.gd`) legata allo stato della
  gara, non al tempo reale: 100m = apertura larga dietro i blocchi → primo piano basso sui blocchi → start largo →
  carrello alto (primo a destra del centro) → traguardo dall'alto → corsa oltre il traguardo in curva; 400m = start
  largo → teleobiettivo dall'altro lato dell'interno (rettilineo opposto) → alto sulla curva 2 → carrello alto →
  traguardo. **Preparazione per evento** (`RaceController.GUN_AT_BY_KIND`: 100m 9 s, 400m 7 s; Esc/Spazio la
  saltano). **100m sull'ovale** con rettilineo prolungato (`TrackGeometry.runner_pose`; dopo il traguardo i corridori
  seguono la curva). **Posa ai blocchi** ("pronti" → "set") senza animazioni: `SetPoseRig.gd` (bacino e schiena a mano,
  braccia e gambe con `TwoBoneIK3D`); blocchi e cartellini di corsia in `OvalTrackBuilder`. **HUD** in stile TV:
  cronometro in basso a destra (decimi in gara, centesimi all'arrivo), vento e «risultato non ufficiale» dopo
  l'arrivo; la classifica laterale è **nascosta di default** (tasto H). Piste e luci: notte, blu per i 100m, viola per
  i 400m. `tests/pose_lab.gd` serve a tarare la posa (obsoleto: i corridori stanno a x ≈ −100 sull'ovale, la sua camera guarda x ≈ 0).
  **Le mani toccano la pista** (`SetPoseRig._solve_torso`): inclinazione del busto e x del bacino NON sono costanti ma si
  risolvono (bisezione, in cache) perché le spalle stiano a `ARM_REACH` × lunghezza braccio dai polsi; il bersaglio del
  polso è `HAND_Y` = 0,20 m perché le dita stanno ~0,17 m oltre l'osso `hand`; le ossa non comandate (clavicole, dita)
  tornano a riposo a ogni aggiornamento. `tests/verify_pose.gd` (headless) legge le ossa **dentro `skeleton_updated`**
  (dopo l'IK: da `_process` si legge la posa pre-IK, che mente).
- **Ralenti dell'arrivo** (solo corse; `RaceController.State.REPLAY` tra `RUNNING` e `FINISHED`). Finita la gara rivede gli
  ultimi secondi del vincitore (`REPLAY_LOOKBACK` 3 s prima del traguardo, fino a `REPLAY_AFTER` 1,8 s dopo) a
  `REPLAY_SPEED` 0,35x, come il replay della vista PyQt. È solo regia: il tempo di gara viene riavvolto e le posizioni si
  rileggono da `RaceMotion` (funzione pura del tempo); durante il ralenti `finished` è un riflesso del tempo riavvolto,
  **senza segnali né contatori** (`runner_finished` e `race_finished` restano una volta sola), e a fine ralenti
  (`_end_replay`) lo stato definitivo è ripristinato. Le animazioni dei corridori usano `RaceController.play_speed()`
  (non `time_scale`) perché le gambe vadano al rallentatore. Camera dedicata `_replay_cam` in `BroadcastCameras` (alta
  3 m, z 19, sopra fotografi e giudici che stanno a z 12–17: più bassa o più vicina viene coperta), etichetta «RALENTI» in
  alto al centro nell'HUD. Esc («Salta alla fine») salta anche il ralenti; `replay_enabled = false` lo disattiva. Gli
  script di test che aspettano `FINISHED` dal vivo (`verify_race`, `verify_camera`, `screenshots`) lo disattivano:
  `tests/verify_replay.gd` (headless, passo fisso con `set_process(false)` + `_process(dt)`) lo verifica.
- **Cadenza di passo** (`godot_viewer/models/StrideModel.gd`, solo vista). La corsa non ha più una costante di metri per
  ciclo: `RunnerView._sprint_cycle_length` chiede a `StrideModel` cadenza e ampiezza (v = f × L) per evento, punto di gara e
  altezza visiva del modello. Dati da `raw/parametri_biomeccanici_atletica.md` (cartella locale, non in git): 100m picco
  ~4,75 Hz a 25 m, 4,6–4,5 in regime, −4% finale; 400m 3,9 Hz nei primi 200 m poi in calo fino a ~3,35; 1500m ~3,2 Hz con
  volata fino a ~3,9; l'atleta più alto ha ~5% di cadenza in meno ogni 17 cm; il primo passo è lungo 1,10 m e cresce fino
  al regime in 30 m (niente «pedalare sul posto»). Le staffette usano la curva dei 100/400 m sul tratto della frazione (dalla
  2ª con partenza lanciata). **Non cambia tempi, ordine o posizioni**: decide solo a che ritmo si muovono le gambe.
  L'animazione satura a 8× (`speed_scale` ≤ 8): per misurare la cadenza reale usa `time_scale` ≤ 2.
  `tests/verify_stride.gd` (headless) confronta il modello con le fasce del file. Non c'è fatica per atleta (non è un dato
  esportato) e il tempo di contatto al suolo del file non è usato: la clip di animazione ha proporzioni fisse.
- **Classifica finale.** A gara conclusa (`FINISHED`) l'HUD Godot mostra a centro schermo la classifica completa
  (`_update_final_board`); `AUTOQUIT_DELAY` è 8 s perché resti leggibile. Alla chiusura di Godot il dialog PyQt mostra
  `views/results_board.py` (`ResultsBoardWidget`) invece di una pagina vuota; legge solo gli `EventStanding` del modello.
- **1500m** (`TrackGeometry.pose_1500m`): partenza in piedi (niente blocchi, `RaceController.uses_blocks`), anello
  unico con coordinata riferita alla corsia 1 (3,75 giri); la corsia sorteggiata dà solo uno scostamento radiale
  iniziale (partenza a linea curva) che rientra alla corda tra 10 e 90 m (`pack_lat` ≤ 2,1 m). Regia con camere
  multi-giro; il cronometro dell'HUD passa a `m:ss.x` oltre i 60 s (stessa regola di tutte le gare).
- **Staffette** (`4x100m`, `4x400m`): una riga per squadra, 4 frazioni sulla stessa curva, testimone che passa di
  mano (`RunnerView._leg_state`); la 4x400m parte in corsia sfalsata e rientra alla corda dopo il primo giro
  (`pose_4x400m`). Una squadra del giocatore squalificata ha `status = 'DQ'` (HUD «SQ.»).
- **Concorsi** (`Salto in Lungo`, `Getto del Peso`): 4 prove per atleta in `field_attempts`, ricavate da
  `generate_attempts` con lo stesso seed della vista PyQt (nullo = `is_foul`). `RaceController.field_queue` le mette
  in scena una dopo l'altra; `verify_race.gd` controlla che il miglior salto del vincitore coincida con il suo
  `mark_value` (solo il vincitore, non gli altri).
- **Ambiente** (solo vista, nessun effetto su tempi o ordine). `scripts/AdBoards.gd`: cartelloni LED con sponsor di
  FANTASIA (se uno coincide con un'azienda vera, cambialo); a doppia faccia nel campo perché le camere interne
  (`_o_start`, `_o_open`) li vedono da dietro (il retro nero faceva una striscia scura), a faccia singola davanti
  alle tribune. `Stadium._build_curve_stands` chiude le tribune dietro le curve con archi (MultiMesh) agganciati alle
  due tribune dritte: raggio ~110 m nei 400m; nei 100m la tribuna opposta è più vicina e resta un buco di ~14 m. Le
  camere devono stare dentro il raggio (la più lontana è a ~91 m dal centro curva). `scripts/TrackSideCrew.gd`:
  fotografi e giudici a forme semplici, **solo nelle corse in pista** (nei concorsi la camera del lungo sta dove
  stanno i fotografi) e i giudici a z ≥ 14 per non coprire la corsia 8 alla camera del traguardo. Tartan dei 400m
  `Color(0.43, 0.14, 0.46)`: più chiaro sbiadisce a lavanda, più blu vira a indaco (luce di scena fredda).
- **Blocchi di partenza** (gruppo `start_blocks`): spariscono quando taglia il traguardo l'atleta di quella corsia e
  tutti a `race_finished`, perché dopo l'arrivo gli atleti proseguono sulla pista (nei 400m le corsie esterne
  partono oltre il traguardo e il runout ci passa sopra). Ricompaiono a ogni `race_loaded`.
- **Nuove classi `class_name`:** Godot le vede solo dopo un import del progetto
  (`godot --headless --path godot_viewer --import`, crea anche i `.uid` da committare), altrimenti
  «Identifier not declared».
- **Flatpak.** `/tmp` dentro il sandbox è privato: gli screenshot scritti in `/tmp/...` non compaiono fuori. Salvali
  in una cartella della home. `./TrackAndFieldManager.sh` avvia il gioco con il `.venv` ed espone Godot flatpak
  (wrapper in `~/.track_field_manager/`, `TEF_GODOT`); `--check` mostra cosa userebbe.
- Il visualizzatore Godot **non** copre gli altri concorsi (salto in alto, disco, …) né più di 8 corsie.

## Test: cosa verificano e cosa no

- Curve monotone e arrivo esatto al tempo ufficiale; sequenza di partenza e salto durante il conto alla
  rovescia; ritmo dei concorsi; migrazione dei vecchi salvataggi; modificatore fisico.
- `test_track_views_paint_in_every_state` renderizza 2D e 3D in ogni stato (compresi ritirato e staffetta
  squalificata): intercetta eccezioni di disegno, **non** giudica l'aspetto. Per l'aspetto usa screenshot
  offscreen (`widget.grab().save(...)`) e guardali.
- Quando si aggiungono dati casuali al generatore la sequenza del `random` cambia: i test che dipendono da un
  seed (es. cognomi uguali) possono rompersi senza che il codice sia sbagliato. Confronta valori completi.

## Flusso git

- Sviluppa sul branch indicato dalla sessione. **Non aprire PR se non richiesto.**
- Se la PR del branch è già stata unita, riparti da `main` aggiornato: `git merge --ff-only origin/main` se il
  branch non ha commit propri, altrimenti `git merge origin/main`. Il force push può essere negato: preferisci un
  merge normale.
- Messaggi di commit e PR in italiano, descrittivi (cosa cambia e perché).

## Preferenze dell'utente

- All'inizio di ogni chat, **esplicita le assunzioni** che stai facendo.
- Rispondi in italiano; dichiara con franchezza ciò che non hai potuto verificare (per esempio: "non ho provato
  l'app con il mouse, solo test offscreen e screenshot").
