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
             race_3d.py         motore 3D software (Camera, Scene3D, figure_joints) + vista 3D delle corse
             field_3d.py        vista 3D di salto in lungo e getto del peso (pose pure + FieldScene3D)
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
- **Concorsi**: `FieldEventWidget` = scena + tabellone (`FieldBoardWidget`). La scena è `scene2d`
  (`FieldSceneWidget`) o `scene3d` (`FieldScene3D`), in un `QStackedWidget`; `widget.scene` è quella attiva (3D di
  default) e `set_view(three_d)` passa dall'una all'altra copiando `kind/lo/hi/cur/t/dur`. Il pulsante "Vista 2D/3D"
  del dialog cambia sia le corse sia i concorsi. Solo le prove dell'atleta del club sono animate per intero, le
  altre scorrono veloci (gara sotto i ~45 s).
- **Fasi dei concorsi**: gli istanti (`LJ_RUN_END`, `LJ_JUMP_END`, `SP_WIND_END`, `SP_FLY_END`) sono costanti di
  `FieldSceneWidget`, usate da 2D e 3D: se li cambi cambiano per entrambe e `PLAYER_SECONDS` resta valido.
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
- Le primitive (`_poly`, `_line3`, `_textured_quad`, `_draw_stand`, `_draw_figure`, …) stanno nel mixin `Scene3D`,
  usato da `Track3DWidget` e `FieldScene3D`. `figure_joints` (pura) calcola lo scheletro con orientamento libero
  (`yaw`); gli angoli degli arti partono dalla verticale verso il basso, positivi in avanti, e sono assoluti.

### Vista 3D dei concorsi (`field_3d.py`)

- Mondo: `x` = direzione di rincorsa/lancio con origine sulla linea di battuta (lungo) o sul bordo anteriore del
  cerchio (peso, centro a `RING_CX = -1,067`); la camera sta a `z > 0` così si corre da sinistra a destra e il
  braccio destro è quello vicino. Camera ravvicinata che segue l'azione (`_camera`), calcolata solo da `t`.
- **La misura non si tocca.** `lj_pose` calcola `LJ_LAND_REACH` dalla posa d'atterraggio, così a fine volo il tallone
  è esattamente a `x = d`; `sp_shot_position` chiude la parabola esattamente a `x = d`. C'è un test
  (`test_3d_field_poses_land_exactly_on_the_mark`): se cambi pose o camera, deve restare verde.
- In volo l'anca non scende sotto 0,2 m e l'attrezzo non va mai sotto terra (testato).
- Nullo: la bandierina rossa sta sulla linea (lungo) e il banner "NULLO" compare in grande; l'animazione però arriva
  comunque a `dist`, come nella vista 2D.
- Le etichette dei metri (`_label3`) si saltano se cadono a < 34 px da una già disegnata: chiamare dal più vicino.
- Prestazioni: ~5 ms a fotogramma (900×480); stesse regole delle corse (antialiasing spento per le superfici).

## Test: cosa verificano e cosa no

- Curve monotone e arrivo esatto al tempo ufficiale; sequenza di partenza e salto durante il conto alla
  rovescia; ritmo dei concorsi; migrazione dei vecchi salvataggi; modificatore fisico.
- `test_track_views_paint_in_every_state` e `test_field_3d_paints_in_every_state` renderizzano 2D e 3D in ogni stato
  (ritirato, staffetta squalificata, nullo, prove di altri, ogni fase): intercettano eccezioni di disegno,
  **non** giudicano l'aspetto. Per l'aspetto usa screenshot (`widget.grab().save(...)`) e guardali.
- Con `QT_QPA_PLATFORM=offscreen` su Windows i font mancano e il testo diventa quadratini (visto anche nelle corse).
  Per screenshot leggibili negli script usa la piattaforma nativa; nei test resta `offscreen`.
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
