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

Modulo **separato** in Godot 4.3+ / GDScript (non fa parte dell'app PyQt): mette in scena i 100m e i 400m in stile
"diretta TV" 2010 leggendo risultati già calcolati da SQLite (plugin godot-sqlite, in `addons/`, ignorato da git).
Dettagli e valori di luce/camere in `godot_viewer/README.md`.

- **MVC.** Model = `autoload/DatabaseManager.gd` (sola lettura), Controller = `autoload/RaceController.gd`
  (tempo, classifica, segnali), View 3D = `Stadium.tscn` + `scripts/` (`BroadcastCameras`, `RunnerView`),
  View 2D = `HUD.tscn`. Anche qui **le viste non cambiano tempi o ordine**.
- **Contratto con Python.** `godot_viewer/data/schema.sql` è l'unica fonte dello schema (`races`,
  `race_results`); `models/race_export.py` lo riusa per esportare (`python -m models.race_export [save.db] [out.db]`).
  `final_time` = `mark_value` e **include** `reaction_time`. Corsie sorteggiate in modo deterministico,
  reazione dalla stessa `reaction_time` della vista PyQt.
- **`godot_viewer/models/RaceMotion.gd` è la copia GDScript** di `_velocity`/`curve_progress` di
  `race_viewer.py`: se cambi la curva dei 100m in Python, cambiala anche lì.
- **Verifica (con Godot installato).** `godot --headless --path godot_viewer -s res://tests/verify_race.gd`
  controlla arrivo esatto a 100 m, ordine e cronometro (esce con codice 0/1); `tests/screenshots.gd` (senza
  `--headless`) salva immagini della scena reale (`-- cartella [close] --race=2`); `tests/verify_input.gd -- --autoquit`
  prova tasti e chiusura automatica; `verify_race.gd` copre 100m, 100m con ritirato, 400m e 400m con ritirato (geometria inclusa). Testato con Godot 4.7.2 + godot-sqlite 4.9.
- **Personaggi.** `RunnerView.gd` usa un modello con scheletro e animazioni CC0 di Quaternius
  (`assets/athlete/`, vedi `CREDITS.md`); abiti ricavati dalla mesh con uno shader. Il modello originale guarda +Z
  e viene ruotato (`FACING_Y`) per correre verso +X.
- **Integrazione nel gioco.** `RaceViewerDialog._next` per i `100m` chiama `views/godot_launcher.py`: esporta
  la gara (`race_export`) in `~/.track_field_manager/race_results.db`, lancia Godot (`--autoquit`) con
  `QProcess`, mostra una pagina segnaposto e prosegue quando Godot si chiude. **Ripiego sulla vista PyQt
  interna** se manca Godot (`TEF_GODOT`, scoop o PATH), il progetto o `addons/godot-sqlite/`, se l'export fallisce
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
  (indicatore in basso a destra). `GODOT_EVENTS` in `views/godot_launcher.py` è un elenco esatto: le staffette
  (`4x100m`…) restano sulla vista PyQt.
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
- Il visualizzatore Godot copre solo **100m e 400m** (niente 1500m, staffette, concorsi né squalificati). Il 1500m è
  stato progettato (anello unico sulla corsia 1 + scostamento laterale solo visivo, andatura `Sprint`, tempi `m:ss.xx`)
  ma NON scritto.

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
