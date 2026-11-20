# Track & Field Manager — note per Claude

Gestionale di atletica desktop in **Python + PyQt6 + SQLite**, architettura **MVC**. Interfaccia, testi e
commenti sono in **italiano**: mantieni la lingua (nomi di variabili e codice in inglese).

## Convenzioni vincolanti (leggere prima di scrivere codice)

Sono regole per le sessioni future. Il codice **oggi non le rispetta tutte**: per ciascuna c'è lo stato attuale e il
lotto di `docs/PLAN.md` che la realizza. Mappa dei documenti: `docs/AUDIT.md` (stato e rischi), `docs/TICK.md`
(ordine del tick), `docs/BALANCE.md` (costanti), `docs/QUESTIONS.md` (decisioni aperte), `docs/PLAN.md` (lotti di
sicurezza/refactor), `docs/PIANOLAVORO.md` (**piano di lavoro corrente**: lotti A-G di gameplay, vedi sotto),
`docs/GAME.md` (descrizione completa del gioco: va aggiornata a ogni lotto chiuso), `docs/REVIEW_REALISMO.md`.

1. **`models/` non importa PyQt6**, né direttamente né tramite `views/` o `controllers/`.
   *Stato attuale: non conforme* — `models/race_export.py:22` importa `views.race_viewer` (che importa PyQt6) → lotto 5.3.
2. **Nessuna costante di gioco scritta a mano fuori dal modulo di bilanciamento.** Il modulo **non esiste ancora**
   (nome `models/balance.py` DA CONFERMARE, QUESTIONS 4). Finché non c'è: nuove costanti nei blocchi di costanti di
   `models/entities.py`, mai letterali dentro le funzioni, e aggiornare `docs/BALANCE.md`.
   *Stato attuale: non conforme* — letterali sparsi in `simulation.py`, `generator.py`, `game_controller.py` → lotto 5.2.
3. **RNG deterministico con seed/stato nel salvataggio.** Ogni funzione di simulazione riceve un `rng` e non crea
   `random.Random()` da sola per le regole di gioco; niente `hash()` su stringhe per ricavare seed (è salato per
   processo). *Stato attuale: quasi conforme* (A.3, 2026-11-20): un solo `GameController.rng` per partita, il suo stato
   completo è in `GameState.rng_state` (`models/rng_state.py`, colonna `rng_state_json`, schema v13) e si salva in ogni
   `_persist()` (**mai** `db.save_game` diretto nel controller) e si ripristina in `load_game`; un salvataggio vecchio
   senza stato si semina con `legacy_seed` (`hashlib`). `views/dialogs.py` usa `zlib.crc32`. **Resta:** il ripiego
   `rng or random.Random()` nelle funzioni di `simulation.py`/`generator.py` (usato solo se non si passa l'RNG). Gli atleti sintetici del ranking (C.1) usano `GameController.rng` (campo creato con `rng`, estrazioni al passo C-13b del tick). **Deviazione:** gli agenti (D.1, `models/agents.py`) non usano `GameController.rng` ma un `random.Random(zlib.crc32(id/nome))` locale, per non spostare le estrazioni del tick: deterministico e senza stato da salvare, ma la personalità di un agente non dipende dal seme della partita (Q29).
4. **Ogni migrazione ha backup + transazione + test su fixture**; mai `DROP` di dati su una versione sconosciuta.
   *Stato attuale: conforme* (lotti 1.1 e 1.2, 2026-11-19). Prima di ogni migrazione `_init_schema` crea un backup
   verificato con `Connection.backup()` in `<cartella dello slot>/backups/<slot>.v{N}.{timestamp-µs}.db.bak` (sempre
   nuovo, mai riusato; si tengono i 3 più recenti per slot, potati solo dopo una migrazione riuscita; fuori dal
   `glob("*.db")` degli slot, quindi non compaiono nell'elenco). La migrazione è una sola transazione
   (`BEGIN IMMEDIATE`, `isolation_level=None`, `execute()` per statement: **mai `executescript`**, fa COMMIT impliciti;
   `user_version` nella stessa transazione). Una versione non migrabile (più recente, v0/v1 con dati, nessuna tabella
   utente in un file non vuoto) solleva `UnsupportedSaveVersion` prima di qualsiasi scrittura: **non si aggiunge più
   alcun `DROP` di dati**. «DB nuovo» = file assente o di 0 byte. Il ripristino da backup è manuale (copiare il
   `.db.bak` come `.db`): non c'è ancora una funzione nel gioco. Test: `tests/test_migrations.py`.
5. **L'ordine del tick settimanale è quello di `docs/TICK.md`** e non si cambia senza aggiornare il documento (anche
   l'ordine delle chiamate all'RNG ne fa parte). *Stato attuale: conforme* (il documento descrive il codice di oggi).
6. **I test di simulazione girano senza Qt**; gli smoke test GUI usano `QT_QPA_PLATFORM=offscreen`.
   *Stato attuale: parzialmente conforme* — `tests/test_migrations.py` è senza Qt, ma i test di simulazione stanno
   ancora in `tests/test_game.py`, che importa PyQt6 a riga 15 → lotto 5.1.
7. **Niente modifiche non richieste in altre cartelle**: niente refactor, rename o «già che ci sono»; un difetto
   trovato per strada si annota in `docs/AUDIT.md`, non si corregge di nascosto. Una decisione di design resta
   all'utente (`docs/QUESTIONS.md`).
8. **Lingua**: interfaccia, testi, commenti e documenti in italiano; identificatori in inglese.

## Comandi

Verificati il 2026-11-19 (Linux, Python 3.14.4 nel `.venv`).

```bash
.venv/bin/pip install -r requirements.txt  # PyQt6, pyinstaller
.venv/bin/python main.py                   # avvia l'app (oppure ./TrackAndFieldManager.sh; --check mostra cosa userebbe)
QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests -v   # 595 test, OK, ~85 s su Windows (~6 s su Linux)
QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest tests.test_game        # 96 test (importa PyQt6)
PYTHONPATH=. python3 -m unittest tests.test_migrations tests.test_assignments tests.test_contracts tests.test_event_800m -v   # 55 test, SENZA PyQt6 (python3 di sistema)
pyinstaller --noconfirm --onefile --windowed --name "TrackAndFieldManager" main.py   # NON VERIFICATO (scrive build/, dist/, .spec)
```

- `python` **non è nel PATH** in questo ambiente: usare `.venv/bin/python`. Il `python3` di sistema non ha PyQt6
  (utile per controllare che `models/` si importi senza Qt: `PYTHONPATH=. python3 -c "import models.simulation"`).
- Percorsi di salvataggio: `~/.track_field_manager/saves/` (slot) e `~/.track_field_manager/savegame.db` (legacy).

- I test impostano `QT_QPA_PLATFORM=offscreen`. In un container Linux pulito PyQt6 può mancare di librerie di
  sistema: servono `libegl1 libgl1 libxkbcommon0 libfontconfig1 libdbus-1-3` (`apt-get update` prima).
- **Non chiamare `exec()` di dialoghi modali** in script o test: bloccano per sempre in offscreen. Nei test si
  istanziano i dialoghi e si chiamano i metodi (`_skip_race`, `_next`, …) oppure si sostituiscono con finti.

## Struttura

```text
main.py      entry point (`GameController(auto_create=False)` + `MainWindow`)
models/      entities.py (GameState, Athlete, eventi, enum, molte costanti)   generator.py (atleti, rivali, dilemmi)
             simulation.py (allenamento, gare, tick `advance_week`)           database.py (SQLite, migrazioni)
             race_export.py (export per Godot)   bibs.py (pettorali)   ranking.py (punti, campo sintetico, classifiche: C.1, senza Qt)   board.py (obiettivi del Board ed esonero: C.2, senza Qt)   career.py (ritiro e post-carriera: C.3, senza Qt)   agents.py (agenti con personalità e relazione: D.1, senza Qt)   market.py (trattativa, bonus, clausola: D.2, senza Qt)   finances.py (bilancio mensile, merchandising, sponsor con obiettivo, TV: D.3, senza Qt)   staff.py (attributi dello staff clinico e relativi effetti: E.1, senza Qt)
controllers/ game_controller.py   segnali Qt; contiene anche regole e cifre di gioco (vedi docs/AUDIT.md Q13)
views/       main_window.py  tabs.py  dialogs.py  start_screen.py  styles.py (QSS scuro)   finance_chart.py (grafico a barre dei mesi, QPainter)
             athlete_dialog.py  Scheda Atleta       results_board.py  tabellone risultati
             race_viewer.py     Gare in diretta (modello di movimento, 2D, concorsi, dialog)
             race_3d.py  field_3d.py  viste 3D software      godot_launcher.py  lancio di Godot
tests/       test_game.py   (96 test, importa PyQt6)    test_migrations.py   (48 test, senza Qt: migrazioni e slot)
             test_empty_start.py (19, avvio senza atleti, Preparazione, fondazione, senza Qt)   test_empty_start_ui.py (17, controller e viste con società vuota, Qt offscreen)   test_assignments.py (9, convocazioni)   test_tiebreaker.py (12, spareggio A.2)   test_rng.py (6, stato RNG A.3)   test_race_strategy.py (15, piano gara B.1)   test_field_strategy.py (15, rischio concorsi B.2)   test_relay_strategy.py (23, cambio staffette B.3)   test_contracts.py (12)   test_event_800m.py (9)   tutti senza Qt
             test_ranking.py (31, ranking C.1, senza Qt)   test_board.py (21, Board C.2, senza Qt)   test_retirement.py (19, ritiro e post-carriera C.3, senza Qt)   test_agents.py (35, agenti D.1, senza Qt)   test_negotiations.py (33, trattativa e bonus D.2, senza Qt)   test_finances.py (25, finanze D.3, senza Qt)   test_staff_attributes.py (16, attributi dello staff E.1, senza Qt)   test_advance_guard.py (4, tick non rientrante)   test_dilemma.py (9, dilemma ignorato)   test_economy.py (9, sostenibilità)   test_rng_controller.py (6, ricarica = stessi esiti)   test_race_strategy_ui.py (13, colonna «Piano gara / Rischio» e menu «Cambio» delle staffette B.3)   test_ranking_ui.py (7, scheda «Ranking», scheda atleta, ricarica)   test_board_ui.py (12, Board: Dashboard, dialoghi, esonero)   test_retirement_ui.py (10, lista «Ex atleti» e assunzione come allenatore C.3)   test_agents_ui.py (13, agenti nel mercato, nella scheda atleta e nel controller D.1)   test_negotiations_ui.py (26, finestra di trattativa, clausola allo svincolo D.2)   test_finances_ui.py (14, tab Finanze con il bilancio mensile D.3)   test_staff_attributes_ui.py (3, colonna «Attributi» della scheda staff E.1)   tutti con PyQt6 offscreen
data/        societa_atletica_lazio.csv      docs/  AUDIT, TICK, BALANCE, QUESTIONS, PLAN, PIANOLAVORO, GAME, REVIEW_REALISMO
```

## Piano di lavoro corrente (`docs/PIANOLAVORO.md`)

Dal 2026-11-20 il lavoro segue `docs/PIANOLAVORO.md` (scritto dall'utente): sette lotti di gameplay, **A** fondamenta e
bugfix → **B** strategia di gara → **C** progressione/carriera → **D** mercato e finanze → **E** staff e impianti →
**F** narrativa → **G** UI/UX. Branch di sviluppo: `feature/gameplay-improvements` (creato da `main` il 2026-11-20).
**Avvio senza atleti (2026-11-20, fuori dai lotti, Q32):** una Carriera nuova parte con 0 atleti e 8 settimane di **Preparazione** senza gare (`GameState.prep_weeks`; 0 nei vecchi salvataggi e nel Prototipo); obiettivi del Board di fondazione nella stagione 1 (verdetto informativo); meeting con la Prima Squadra vuota = non iscrizione, senza sanzioni. **Nei test**: una Carriera «di una volta» (16 atleti, 36 settimane) si ottiene con `tests.support.start_game`, mai con scorciatoie nel codice di gioco. Nuovi test: `test_empty_start.py` (senza Qt), `test_empty_start_ui.py`. Aperti: economia senza atleti (AUDIT R29), cifre (Q32).
**Stato (2026-11-20):** lotti A, B e D chiusi (C con C.1b da decidere); **E.1** (staff con attributi 1-20, schema v22) fatto con calibrazione neutra (al riferimento 14 gli effetti sono quelli di prima), cifre da confermare (Q33), senza un mercato dello staff gli attributi non differenziano ancora nulla (AUDIT R30); **D.3** (bilancio mensile, merchandising, sponsor con obiettivo, diritti TV, schema v20) fatto, cifre da confermare (Q31); **D.2** (trattative con un giro di controfferta, bonus per record, clausola rescissoria, schema v19) fatto, cifre da confermare (Q30); **D.1** (agenti con personalità e relazione, ingaggio al tesseramento, schema v18) fatto, cifre da confermare (Q29); **C.3** (ritiro a 33-35 anni o per infortuni, ex atleta allenatore, schema v17) fatto, cifre da confermare (Q28); **C.2** (obiettivi del Board ed esonero, schema v16) fatto, cifre da confermare (Q27); **C.1** (ranking, schema v15) fatto con atleti sintetici, cifre da confermare
(QUESTIONS Q26; `test_economy` riscritto sulla distribuzione, AUDIT R21); gli inviti Diamond League sono **C.1b**, da decidere. Prossimo: E.2 (impianti avanzati) e E.3 (vivaio); C.1b (inviti Diamond League) resta da decidere.

- **Si procede per lotti e sottopunti nell'ordine del documento** (A.1 … A.5, poi B, C…), rispettando le «Dipendenze» di
  ogni lotto. Un sottopunto = uno o pochi commit piccoli, in italiano; non si salta avanti senza dirlo all'utente.
- **Ogni sottopunto ha i test indicati** nel piano: nuovo file in `tests/`, **senza Qt** se la logica sta in `models/`
  (convenzione 6); smoke test offscreen per le viste. «Test manuale» del piano = da dichiarare come **non eseguito**
  se non lo si è fatto davvero (niente mouse reale in questo ambiente).
- **A ogni sottopunto chiuso** aggiornare: `docs/GAME.md` (sempre), `docs/BALANCE.md` (se cambiano cifre: lotti A e D),
  `docs/TICK.md` (se cambia l'ordine del tick o delle chiamate all'RNG), `docs/AUDIT.md` (difetti trovati o chiusi),
  `docs/QUESTIONS.md` (decisioni nuove) e le righe «Stato attuale» delle convenzioni qui sopra.
- **Sovrapposizioni con `docs/PLAN.md`** (il piano dell'utente prevale dove differisce): A.1 ↔ lotti 4.x e QUESTIONS 3;
  A.2 ↔ 3.3 e QUESTIONS 5 (✅ fatto 2026-11-20); A.3 ↔ 2.1 (+2.2 per `hash()`) e QUESTIONS 2 (✅ fatto 2026-11-20); A.4 ↔ 3.1 e QUESTIONS 6 (qui: chiusura senza
  scelta = «rifiuta» + pulsante «Ignora», non «ignorare Esc»); A.5 ↔ 1.4 (guardia nel controller, testabile senza mouse,
  **più** pulsante disabilitato). Chiuso un sottopunto, segnare il lotto di `PLAN.md` corrispondente come fatto.
- **Schema DB.** Il piano scrive «Lotto A: nessuna modifica schema», ma A.3 salva lo stato dell'RNG: serve una migrazione
  (**v12**, come in `PLAN.md` 2.1). I numeri di versione citati per B-F (v12…v16) sono **indicativi**: si usa sempre la
  prima versione libera, con `MIGRATIONS` + `CREATE TABLE` + test su fixture (convenzione 4).
- **Costanti nuove** (sponsor, premi, modificatori delle strategie, soglie…): nei blocchi di costanti di `entities.py`,
  mai letterali nelle funzioni (convenzione 2); cifre in `docs/BALANCE.md`.
- **Cose che il piano non decide** restano all'utente: cifre non indicate, una nuova dipendenza (`pyqtgraph`/`matplotlib`
  per il Lotto G: chiedere prima di toccare `requirements.txt`), e qualunque scelta di design che emerga lavorando.
  Il piano è una proposta ambiziosa: se un sottopunto si rivela incoerente con il codice, **si segnala e si propone**
  prima di scrivere codice, non si aggiusta di nascosto.
- Le strategie del Lotto B si **scelgono prima della gara** e le applica il modello: non sono comandi in gara, quindi non
  violano la regola «niente button mashing» né «l'esito lo decide solo il modello».

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
  `test_*_matches_fidal_ranges` le fissano con fasce larghe. 100m, 400m, **800m (ancore STIMATE, nessun dato FIDAL)**, 1500m, lungo e peso sono tarati, le
  staffette (`_relay_mark`) no. Il tetto è il record del mondo, applicato dopo il vento. Le ancore alte di lungo e
  peso vengono da dati reali (Assoluti 2025, Lazio regionali 2025); provinciale e media regionale di lungo e peso
  sono **stime**, dichiarate come tali nei commenti dei test: sostituiscile se trovi dati FIDAL veri. I
  `historic_mark` in `entities.py` non sono stati ritoccati: con le nuove curve lungo/peso richiedono score più
  alti (es. peso M 18 m ≈ score 76, prima ≈ 62).
- **Salvataggi.** `SCHEMA_VERSION = 22` (`database.py`; v22 = `staff.attributes_json` (attributi 1-20 dello staff clinico, `{}` = tutti al riferimento 14, l'effetto di prima), E.1, 2026-11-20; v21 = `game_state.prep_weeks` (settimane di Preparazione a inizio stagione, `0` = calendario di sempre), avvio senza atleti Q32, 2026-11-20; v20 = `game_state.monthly_report_json` (bilanci mensili), D.3, 2026-11-20; v19 = `athletes.record_bonus` (bonus per record pattuito in trattativa), D.2, 2026-11-20; v18 = `athletes.agent_id` e `game_state.agents_json` (agenti e relazione), D.1, 2026-11-20; v17 = `athletes.season_injuries` (infortuni della stagione) e `game_state.retired_json` (ex atleti), ritiro C.3, 2026-11-20; v16 = `game_state.board_json` (stagioni fallite di fila ed esonero), obiettivi del Board C.2 (soglie e avanzamento in `objectives_json`, verdetto in `season_history_json`), 2026-11-20; v15 = `athletes.ranking_json` e `game_state.ranking_pool_json`, ranking C.1 (i punti dei rivali stanno nel loro JSON), 2026-11-20; v14 = `game_state.race_strategy_json`, piano gara B.1, rischio concorsi B.2 (stessa colonna, chiave `risk`) e cambio staffette B.3 (stessa colonna, chiave `change`), 2026-11-20; v13 = `game_state.rng_state_json`, A.3, 2026-11-20; v10 = `athletes.contract_end_season`, v11 = `athletes.contract_no_renew`, Q22, 2026-11-19; v12 = `game_state.league_places_json`, spareggio A.2, 2026-11-20). Ogni nuova colonna va aggiunta in `database.py` con una voce in
  `MIGRATIONS` (le colonne nuove con `DEFAULT`) *e* nella `CREATE TABLE`; `_drop_columns_after` nei test usa
  `MIGRATIONS` per simulare i vecchi salvataggi. I campi mancanti dei vecchi salvataggi si riempiono al
  caricamento in modo deterministico (es. `_backfill_bodies`, seed = id atleta). Backup e rifiuto delle versioni
  sconosciute: vedi convenzione 4. `GameController.load_save_slot`/`load_game` non fanno salire le eccezioni (in PyQt6
  un'eccezione che esce da uno slot termina il processo, exit 134): ritornano `False` e riempiono `last_load_error`.

## Gare in diretta (`views/race_viewer.py`, `views/race_3d.py`)

- Si apre da `MainWindow._show_competition_results` prima dei risultati, solo se il meeting ha gare.
- **Modello di movimento** (funzioni pure, testate): `curve_progress`, `position_fraction`, `reaction_time`.
  Curva di velocità per gara (100m, 400m, 800m, 1500m, staffetta). `position_fraction` vale esattamente 1 a
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
  con `export_race`). `race_results.gender` (M/F) sceglie il modello 3D. `race_results.bib` = numero di pettorale (vedi sotto, 0 = nessuno; un DB esportato
  prima della colonna si legge senza errori, `export_race` la aggiunge con `ALTER TABLE` a un `race_results.db` vecchio). **Schema e seed si
  spezzano sul punto e virgola** (`DatabaseManager._create_demo_database`): niente `;` nei commenti di `schema.sql`/`demo_seed.sql`. `final_time` = `mark_value` e **include** `reaction_time`. Corsie sorteggiate in modo deterministico,
  reazione dalla stessa `reaction_time` della vista PyQt.
- **`godot_viewer/models/RaceMotion.gd` è la copia GDScript** di `_velocity`/`curve_progress` di
  `race_viewer.py`: se cambi la curva dei 100m in Python, cambiala anche lì.
- **Verifica (con Godot installato).** `godot --headless --path godot_viewer -s res://tests/verify_race.gd`
  controlla arrivo esatto, ordine e cronometro (esce con codice 0/1); `tests/screenshots.gd` (senza
  `--headless`) salva immagini della scena reale (`-- cartella [close] --race=2`); `tests/verify_input.gd -- --autoquit`
  prova tasti e chiusura automatica. `verify_race.gd` scorre le 14 gare del DB demo (1-2 = 100m con un ritirato,
  3-4 = 400m, 5-6 = 1500m, 7 = 4x100m, 8 = 4x400m con squadra squalificata, 9-10 = lungo, 11-12 = peso, 13-14 = 800m), geometria
  inclusa. `verify_pose.gd` gira in `--headless`; `verify_camera.gd` e `verify_input.gd` aprono una finestra vera (serve
  un display; `verify_camera.gd` dura diversi minuti: lanciarlo in background, non con un timeout breve).
  Testato con Godot 4.7.2 (flatpak `org.godotengine.Godot`) + godot-sqlite 4.9; l'import del progetto alla prima
  esecuzione crea file `.uid` (committa quelli dei nuovi script di test).
- **Personaggi.** Vestiario, pelle, capelli e libreria di animazioni sono in `scripts/CharacterDress.gd` (condiviso da `RunnerView` e
  `TrackSideCrew`). `RunnerView.gd` usa un modello con scheletro e animazioni CC0 di Quaternius
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
- **Pettorali.** Un numero a tre cifre per atleta **per meeting**, unico fra tutti i partecipanti (staffette comprese: un numero per
  squadra, uguale per tutte le frazioni), lo stesso in ogni gara del meeting. Lo assegna **solo** `models/bibs.py` (`assign_bibs(summary)`,
  chiave `(squadra, nome)`, sorteggio deterministico dal meeting; non è un campo salvato dell'atleta: `EventStanding` non ha un id, quindi
  nessuna migrazione del salvataggio. Per un numero persistente basterebbe cambiare quella funzione). `export_race` lo scrive in
  `race_results.bib`, `RunnerData.bib` lo legge. In Godot `BibPrint.gd` disegna il foglio (carta bianca, cifre scure, spille) e
  `CharacterDress.add_cloth(..., print_opts)` lo stampa **sul tessuto** della canotta davanti e dietro (stesso meccanismo di «STAMPA»;
  larghezza ≤ 0,12 altezze corporee). Un viewport per corridore, figlio del `RunnerView`: niente cache fra gare (una texture di un
  viewport liberato resta vuota). Il numero compare anche nel tabellone finale di Godot e in `views/results_board.py`. Le viste PyQt
  interne 2D/3D (ripiego senza Godot) **non** mostrano i pettorali. `tests/verify_bib.gd` (headless) controlla DB con e senza colonna.
- **Corsie e omonimi.** `race_export.draw_lanes` usa chiavi `(nome, squadra)`: con il solo nome due omonimi di squadre diverse nella stessa
  gara finivano nella stessa corsia (`IntegrityError` su `(race_id, lane)`) e la gara non arrivava mai a Godot (il ripiego sulla vista
  interna è silenzioso). Con nomi tutti diversi il sorteggio è identico a prima (c'è un test).
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
- **Concorsi** (`Salto in Lungo`, `Getto del Peso`): 6 prove per atleta in `field_attempts` (`FIELD_ROUNDS`, 3 + 3: con ≤ 8 partecipanti tutti le fanno tutte), ricavate da
  `generate_attempts` con lo stesso seed della vista PyQt (nullo = `is_foul`). `RaceController.field_queue` le mette
  in scena una dopo l'altra; `verify_race.gd` controlla che il miglior salto del vincitore coincida con il suo
  `mark_value` (solo il vincitore, non gli altri).
- **Getto del peso** (2026-11-20, dettagli in `godot_viewer/README.md` «Getto del peso»). `models/ShotPutMotion.gd` (funzioni pure, **unica fonte**:
  pedana, cronologia, posa, volo) + `scripts/ShotPutRig.gd` (posa a mano + `TwoBoneIK3D`, nessuna animazione di lancio nella libreria CC0) +
  `scripts/ShotPutView.gd` (peso, scia, terriccio, nastro, bandierina, arco del migliore; niente buche nel terreno). **Invariante: il peso atterra ESATTAMENTE a `C + u·(misura + 1,0675)`**:
  rilascio `R` scritto (mai riletto dallo scheletro), angolo fisso 36-38,5°, `v0` in forma chiusa, volo = funzione del tempo fissata a `tau ≥ T`.
  `tests/verify_shotput.gd` (headless, secondi) lo controlla; **non rompere questa proprieta'**. Tutte le prove sono animate
  (nel peso `step["animate"]` e' sempre vero; un arco dorato sul terreno segna il miglior lancio); il piano del tentativo sta in `step["plan"]` (`ShotPutMotion.Plan`). Altezza dell'atleta = `RunnerData.visual_height` (la usa
  anche `RunnerView`: devono coincidere). Rilascio a ~1,06·H, non 2,2 m. **Scelte dell'utente:** niente gabbia, settore disegnato a 30 m (non 100).
  `ShotPutMotion.Mode`/`Phase` guidano rig e regia; la posa e' tarata a descrizioni biomeccaniche, **non** su un video (da giudicare a occhio).
  Piede sinistro che pivota sulla punta (`foot_tip_reach`/`heel_lift`, `FootLevel.pitch_l`), mano orientata verso il peso (`ShotPutRig.HandAim`), dita chiuse (`FingerGrip`,
  presa di `grip_at`) e scia a tubo (`ShotPutView._update_trail`): 2026-11-20, vedi README. **Nei test `-s` `get_skeleton()` dei modificatori e' nullo e `get_bone_global_pose` non si
  aggiorna fuori dal fotogramma**: i modificatori hanno `apply_to(skel)` e i test leggono le ossa dalla catena di pose locali; i test che toccano `global_transform` o `ShotPutView`
  (che usa l'autoload `RaceController`) girano in `_process`, non in `_init`.
- **Ambiente** (solo vista, nessun effetto su tempi o ordine). `scripts/AdBoards.gd`: cartelloni LED con sponsor di
  FANTASIA (se uno coincide con un'azienda vera, cambialo); a doppia faccia nel campo perché le camere interne
  (`_o_start`, `_o_open`) li vedono da dietro (il retro nero faceva una striscia scura), a faccia singola davanti
  alle tribune. `Stadium._build_curve_stands` chiude le tribune dietro le curve con archi (MultiMesh) agganciati alle
  due tribune dritte: raggio ~110 m nei 400m; nei 100m la tribuna opposta è più vicina e resta un buco di ~14 m. Le
  camere devono stare dentro il raggio (la più lontana è a ~91 m dal centro curva). `scripts/TrackSideCrew.gd`:
  fotografi e giudici **persone vere** (stesso modello con scheletro dei corridori, vestiti da `CharacterDress`, animazioni in loop:
  `Pistol_Idle` con macchina e teleobiettivo per i fotografi, `Sitting_Idle`/`Idle_Talking` per i giudici, tavolo con computer e
  sedie; posizioni delle mani e del bacino misurate sul modello, costanti in cima al file). Le scritte «STAMPA»/«GIUDICE» sono
  **stampate sul tessuto** (`CharacterDress.add_cloth(..., print_tex, print_rect)`: texture del testo da un `SubViewport`, campionata
  con le coordinate a riposo del capo, solo sulla schiena): un'etichetta 3D restava sospesa e si sovrapponeva al corpo. Il testo
  non deve superare ±0,06 altezze corporee di larghezza, oltre la schiena gira di lato e si taglia, **solo nelle corse in pista** (nei concorsi la camera del lungo sta dove
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
- **800m** (Q16, 2026-11-19): `RaceMotion.gd` ha la copia GDScript della curva `800m` di `race_viewer._velocity`; `TrackGeometry.pose_800m`
  (partenza in piedi **allineata sulla linea d'arrivo**, prima curva in corsia, rientro alla corda fra 100 e 150 m: stessa semplificazione
  visiva della vista PyQt, l'esito non cambia) e `start_offset_800m`; `region_for("800m")` ha una tolleranza `REGION_EPS` perché la
  partenza coincide con la linea d'arrivo (senza, la regia taglierebbe un istante sul rettilineo); `RaceController` (`GUN_AT_BY_KIND` 4,6 s,
  senza blocchi); `OvalTrackBuilder` (linea di partenza e di rientro); regia = quella dell'ovale (come 1500m). **`StrideModel` per l'800m è
  una STIMA** (il file di riferimento non ha dati sull'800m): 3,85 Hz nei primi 150 m, ~3,5 a regime, volata fino a ~3,95. Gare demo 13-14
  (M/F) in `demo_seed.sql`; `verify_race.gd` va fino alla 14 e controlla la geometria, `verify_stride.gd` la cadenza.
  Provato: `verify_race`, `verify_stride`, `verify_replay`, `verify_bib` (TUTTO OK, Godot 4.7.2 flatpak) e screenshot di partenza e gara
  (`tests/screenshots.gd -- cartella --speed=4 --race=13`); **non** guardati gli scatti dell'arrivo e non provato con una gara esportata
  da `export_race` (solo con il seed demo; l'export è coperto da un test Python).

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
