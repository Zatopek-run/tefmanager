# PLAN — piano di intervento a lotti piccoli

Nessun lotto richiede di riscrivere l'app. Ogni lotto è indipendente salvo dove indicato in «Dipende da». Un lotto = un commit (o pochi) e una sessione. Prima di ogni lotto: `git status` pulito e suite verde (`QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests -v`, 151 test, ~4 s). Le decisioni citate sono in `QUESTIONS.md`; **nessun lotto parte senza la risposta indicata**. Rischi e riferimenti in `AUDIT.md`; ordine del tick in `TICK.md`.

Ordine: 1 sicurezza save → 2 determinismo → 3 ambiguità di regole → 4 economia → 5 refactor → 6 UI.

---

## Area 1 — Sicurezza dei salvataggi

### Lotto 1.1 — Migrazione transazionale con backup — ✅ FATTO (commit `5a21154`, 2026-11-19)
- **Obiettivo:** una migrazione o riesce per intero o non cambia nulla; prima di toccare un file si crea il backup.
- **File:** `models/database.py` (`_init_schema`), `tests/` (nuovo file `tests/test_migrations.py` senza Qt, vedi 5.1; fino ad allora in `test_game.py`).
- **Rischio:** medio (tocca il percorso di apertura di ogni salvataggio). Ridurlo: cambiare solo `_init_schema`, lasciare invariate `MIGRATIONS` e le colonne.
- **Verifica:** nuovi test su fixture: (a) v2…v8 → v9 con dati identici (riusa `_drop_columns_after`); (b) migrazione con ALTER che fallisce al secondo statement (monkeypatch `MIGRATIONS`): il file resta byte per byte uguale e riapribile, `user_version` invariato; (c) il backup esiste, è apribile con `sqlite3` ed è alla versione di partenza.
- **Accettazione:** il test (b) riproduce l'esperimento E1 di `AUDIT.md` e passa; nessuna regressione nei test v2/v7/v8/v9 esistenti.
- **Dipende da:** QUESTIONS 1 (politica di backup).
- **Esito:** E1 riscritto come `tests/test_migrations.py::TestMigrationSafety::test_e1_failed_migration_leaves_original_untouched` (rosso sul codice precedente: hash del file cambiato; verde dopo). Backup in `saves/backups/` (non `nomefile.db.bak-v{N}` come ipotizzato: vedi QUESTIONS 1). Misure: apertura di un v9 invariata (0,92 ms contro 0,91), migrazione v2→v9 con backup 2,1 ms una tantum.

### Lotto 1.2 — Versioni sconosciute: mai DROP silenzioso — ✅ FATTO (commit `85778a9`, 2026-11-19)
- **Obiettivo:** un salvataggio più nuovo (o v0/v1) viene rifiutato senza modifiche, con messaggio all'utente.
- **File:** `models/database.py` (eccezione `UnsupportedSaveVersion`), `controllers/game_controller.py` (`load_save_slot`, `load_game`), `views/start_screen.py` (messaggio).
- **Rischio:** basso.
- **Verifica:** test: `user_version = SCHEMA_VERSION+1` → eccezione, file invariato (hash identico); `read_save_summary` continua a elencarlo.
- **Accettazione:** il test E2 di `AUDIT.md` non cancella più i dati; il click su uno slot non crasha l'app (smoke test offscreen del controller con slot non supportato).
- **Dipende da:** 1.1, QUESTIONS 1.
- **Esito:** E2 è `tests/test_migrations.py::TestUnsupportedVersions::test_e2_unknown_versions_are_refused_not_wiped` (sul codice precedente la partita veniva cancellata: misurato). Smoke test del click: `tests/test_game.py::TestUnsupportedSlotLoading` (processo a parte, esce con -6 senza il fix). Messaggio con `QMessageBox.warning` e traceback in `setDetailedText`; nessun nuovo sottosistema di logging.

### Lotto 1.3 — Il tick non lascia stato a metà
- **Obiettivo:** se `advance_week` solleva un'eccezione, lo stato in memoria resta quello precedente e nulla viene salvato.
- **File:** `controllers/game_controller.py` (`advance_week`: lavorare su una copia con `copy.deepcopy`, sostituire `self.state` solo a tick riuscito), test.
- **Rischio:** medio-basso (costo di una copia a settimana; `competition_history` cresce: misurare il tempo).
- **Verifica:** test con `advance_week` forzato a sollevare (monkeypatch di `progress_rivals`): `state` identico a prima, nessun `save_game`.
- **Accettazione:** il test passa; durata del tick misurata e riportata nel commit.

### Lotto 1.4 — Protezione contro il doppio tick — ✅ FATTO (2026-11-20, come PIANOLAVORO A.5)
- **Obiettivo:** due click ravvicinati non producono due settimane.
- **File:** `views/main_window.py` (disabilitare il pulsante durante il tick, riabilitare in `_refresh_all`) oppure guardia di rientro nel controller.
- **Rischio:** basso. Preferire la guardia nel controller (testabile senza mouse).
- **Verifica:** test: due chiamate sincrone a `controller.advance_week` con guardia attiva da un segnale `week_advanced` ri-entrante; smoke test offscreen che emette `clicked` due volte di seguito.
- **Accettazione:** una sola settimana avanzata. Dichiarare che il doppio click reale con mouse non è provato.

## Area 2 — Riproducibilità e determinismo

### Lotto 2.1 — Stato RNG salvato nel salvataggio — ✅ FATTO (2026-11-20, come PIANOLAVORO A.3; schema v13, un solo RNG per tick e azioni UI)
- **Obiettivo:** ricaricare e avanzare produce lo stesso risultato.
- **File:** `models/entities.py` (campo `rng_state` in `GameState`), `models/database.py` (colonna `rng_state_json` con `DEFAULT '{}'` **sia** in `MIGRATIONS` **sia** nel `CREATE TABLE`, `SCHEMA_VERSION = 13` (la v12 l'ha presa `game_state.league_places_json`, A.2, 2026-11-20; indicativo: si usa la prima libera): la v10 è già presa da `athletes.contract_end_season` (Q22) e la v11 da `athletes.contract_no_renew`, 2026-11-19), `controllers/game_controller.py` (init/load/save).
- **Rischio:** medio (nuova versione di schema; formato di `getstate` tra versioni Python: lo stato è una tupla di interi, JSON-serializzabile, ma da provare su 3.14).
- **Verifica:** test: stessa partita caricata due volte → 8 tick → stato identico (l'esperimento B2 di `AUDIT.md` deve invertire l'esito); test di migrazione v11→v12 su fixture.
- **Accettazione:** B2 identico; v11 si migra senza perdita; i test esistenti restano verdi.
- **Dipende da:** 1.1, QUESTIONS 2.

### Lotto 2.2 — Eliminare `hash()` salato dalle viste — ✅ FATTO (2026-11-20, `zlib.crc32`, test in 3 processi)
- **Obiettivo:** la fascia del potenziale è stabile tra avvii.
- **File:** `views/dialogs.py:55` (sostituire `hash(...)` con `zlib.crc32` della stringa, come `race_viewer._rng`).
- **Rischio:** basso.
- **Verifica:** test che chiama `potential_band_display` in due processi (subprocess) e confronta.
- **Accettazione:** stesso output in 3 esecuzioni.

### Lotto 2.3 — Test di determinismo del tick
- **Obiettivo:** congelare l'ordine delle chiamate all'RNG.
- **File:** `tests/` (nuovo test): stato iniziale con `Random(seed)`, 36 settimane, confronto con valori attesi (budget, tabella lega, prime 5 notizie).
- **Rischio:** basso, ma il test si rompe (giustamente) a ogni modifica dell'ordine del tick: aggiornare `TICK.md` insieme.
- **Verifica/Accettazione:** il test passa due volte di fila e in due processi diversi.
- **Dipende da:** nessuno (utile prima di 3.x e 4.x).

## Area 3 — Ambiguità di regole

### Lotto 3.1 — Dilemma chiuso senza scelta — ✅ FATTO (2026-11-20, come PIANOLAVORO A.4; scelta: «Ignora» neutro, non rifiuto)
- **File:** `views/dialogs.py` (`EthicalDilemmaDialog`: ignorare Esc/chiusura), `views/main_window.py` (riproporre `pending_dilemma` al caricamento).
- **Rischio:** basso. **Verifica:** smoke test: dialog istanziato, `reject()` non chiude/non lascia pendente; stato con dilemma pendente → riproposto. **Accettazione:** nessun dilemma pendente permanente (esperimento A di `AUDIT.md` ripetuto: dilemmi di nuovo generati).
- **Dipende da:** QUESTIONS 6.

### Lotto 3.2 — Costo dei dilemmi senza azzeramento del debito
- **File:** `controllers/game_controller.py:798,825`. **Rischio:** basso. **Verifica:** test con budget −5.000 → rifiuto → budget −5.600. **Accettazione:** il saldo negativo non viene mai riportato a 0 da un dilemma.
- **Dipende da:** QUESTIONS 7.

### Lotto 3.3 — Spareggio unico e deterministico — ✅ FATTO (2026-11-20, come PIANOLAVORO A.2; più 1°, 2°, … poi sorteggio `hashlib` senza nome; schema v12, non attende 2.1)
- **File:** `models/entities.py` (`league_standings`), `models/simulation.py:1033`. **Rischio:** medio (cambia il verdetto in caso di pareggio). **Verifica:** test con tabella in pareggio: stesso esito a ogni esecuzione e indipendente dal nome del club. **Accettazione:** lega e meeting usano la stessa regola.
- **Dipende da:** QUESTIONS 5; 2.1 se si usa il sorteggio seminato.

### Lotto 3.4 — Fine del Prototipo
- **File:** `controllers/game_controller.py` (guardia), `views/tabs.py` (testi). **Rischio:** basso. **Verifica:** 9° tick in Prototipo bloccato con messaggio. **Accettazione:** nessuna gara alla sett. 12 nel Prototipo.
- **Dipende da:** QUESTIONS 8.

### Lotto 3.5 — Obiettivi: rinnovo e soglia per divisione
- **File:** `models/simulation.py` (`close_season`, `_evaluate_objectives:588`), `models/generator.py`. **Rischio:** basso. **Verifica:** test con atleta F sotto 11,80 s ma sopra 11,00 s. **Accettazione:** l'obiettivo storico usa `historic_mark_f`; a fine stagione gli obiettivi si rigenerano.
- **Dipende da:** QUESTIONS 13.

### Lotto 3.6 — Validazione delle iscrizioni
- **File:** `controllers/game_controller.py:370-374`. **Rischio:** basso. **Verifica:** test: atleta del genere sbagliato, della squadra giovanile o duplicato → rifiutato con messaggio. **Accettazione:** la UI esistente continua a funzionare (smoke test).
- **Dipende da:** QUESTIONS 15.

## Area 4 — Economia e bilanciamento

*Tutti i lotti qui modificano solo costanti o una formula e hanno un test di sostenibilità. Dopo 5.2 le costanti stanno nel modulo di bilanciamento; prima, in `entities.py`/`generator.py`.*

### Lotto 4.1 — Test di sostenibilità economica — ✅ FATTO (2026-11-20, `tests/test_economy.py`, PIANOLAVORO A.1)
- **Obiettivo:** misurare, non decidere. **File:** `tests/` (nuovo): rosa iniziale, 12 settimane di autopilota su 5 seed, report del flusso netto. **Rischio:** nullo. **Accettazione:** il test documenta la situazione attuale (flusso negativo) e fallisce se cambia oltre una soglia scelta.

### Lotto 4.2 — Riequilibrio dello stipendio di partenza — ✅ FATTO (2026-11-20, rimborsi −45%, PIANOLAVORO A.1)
- **File:** `models/generator.py:413` (o costanti in 5.2). **Rischio:** medio (cambia la difficoltà). **Verifica:** 4.1 con il nuovo obiettivo. **Accettazione:** flusso netto entro l'intervallo deciso. **Dipende da:** QUESTIONS 3, 4.1.

### Lotto 4.3 — Fan/sponsor con decadimento o tetto
- **File:** `models/simulation.py:1230` (+ passata nel tick: aggiornare `TICK.md`). **Rischio:** medio. **Verifica:** simulazione di 5 stagioni: sponsor individuali sotto il tetto. **Accettazione:** crescita limitata. **Dipende da:** QUESTIONS 11.

### Lotto 4.4 — Revisione stipendi a fine stagione
- **File:** `models/simulation.py` (blocco di fine stagione, `:1380-1386`). **Rischio:** medio. **Verifica:** test: atleta migliorato → stipendio aggiornato al cambio stagione, non prima. **Accettazione:** `TICK.md` aggiornato. **Dipende da:** QUESTIONS 12, 4.2.

## Area 5 — Refactor architetturale

### Lotto 5.1 — Test di simulazione senza Qt
- **Obiettivo:** poter eseguire i test dei modelli con un Python privo di PyQt6. **File:** spezzare `tests/test_game.py` (2.661 righe, importa PyQt6 a `:15`): nuovo `tests/test_sim_*.py` solo con `models/` (classi `TestVerticalSliceAndMechanics`, `TestMaxithlonInspiredMechanics`, `TestCoachesAndRelays`, `TestRivalClubs`, `TestPromotionAndRelegation`, `TestBodyBuild`, parti di `TestGenderDivisions`), lasciando in `test_game.py` i test GUI. **Stato (2026-11-20):** i test di migrazioni, convocazioni, contratti e 800m (55) sono già in file senza Qt; restano in `test_game.py` (96 test) quelli di simulazione. **Rischio:** basso (spostamento). **Verifica:** `python3 -m unittest tests.test_sim_*` con il `python3` di sistema **senza** PyQt6; suite totale = stessi 151 test. **Accettazione:** nessun test perso (conteggio identico), i nuovi file non importano `PyQt6` né `controllers`/`views`.
- **Nota:** i test che usano `GameController` richiedono Qt; vanno rifattorizzati in test del modello (stato costruito con `generator`) o restano GUI.

### Lotto 5.2 — Modulo di bilanciamento
- **Obiettivo:** costanti in un solo posto. **File:** nuovo `models/balance.py` (nome DA CONFERMARE), `entities.py`/`simulation.py`/`generator.py`/`game_controller.py` importano da lì. **Rischio:** medio. Un dominio per commit, in quest'ordine: (a) economia (`BALANCE.md` §A), (b) gara (§C), (c) staffette/allenatori (§D, §F), (d) rivali e stagione (§B). **Verifica:** test di non regressione che confronta i valori pre/post (importa i vecchi nomi) e 2.3 identico. **Accettazione:** `BALANCE.md` aggiornato con i nuovi `file:riga`; nessun letterale numerico di gioco rimasto nei domini già migrati (grep documentato). **Dipende da:** QUESTIONS 4, 2.3.

### Lotto 5.3 — `race_export` non dipende dalle viste
- **Obiettivo:** `import models.race_export` funziona senza PyQt6. **File:** spostare `_rng`, `generate_attempts`, `reaction_time` (e `curve_progress` se serve) da `views/race_viewer.py` in un modulo di `models/` (es. `models/race_motion.py`, nome DA CONFERMARE); `race_viewer.py` li importa. **Rischio:** medio (la vista PyQt, il 3D e il test «arrivo esatto» li usano; CLAUDE.md: `RaceMotion.gd` è la copia GDScript di `curve_progress`). **Verifica:** `python3 -c "import models.race_export"` OK senza PyQt6; i test `TestRaceViewer` e `TestRaceExport` invariati. **Accettazione:** 0 import di `views` in `models/`.

### Lotto 5.4 — Logica di zona promozione/retrocessione in un solo posto
- **File:** `models/entities.py` (metodo `league_zone`), `views/tabs.py:384-390,1058-1060`, `views/dialogs.py:689-691`, `models/simulation.py:1177-1186`. **Rischio:** basso. **Verifica:** test sul modello; le viste leggono il valore. **Accettazione:** nessuna comparazione con `PROMOTION_SPOTS` nelle viste.

### Lotto 5.5 — Soldi e regole fuori dal controller
- **File:** spostare in `models/` le funzioni che oggi mutano stato con cifre a mano (`game_controller.py:303,332,419,454,776-832`); il controller le chiama ed emette segnali. **Rischio:** medio. **Verifica:** gli stessi test, più test diretti sul modello senza Qt. **Accettazione:** il controller non contiene numeri di gioco.

## Area 6 — UI

### Lotto 6.1 — Messaggi di errore e di stato
- **File:** `views/start_screen.py`, `views/main_window.py`. Mostrare all'utente: salvataggio non supportato (1.2), fallimento (QUESTIONS 9), fine Prototipo (3.4). **Rischio:** basso. **Verifica:** smoke test offscreen.

### Lotto 6.2 — Soglie condivise
- **File:** `views/tabs.py`, `views/main_window.py`: soglia di fatica 75 (5 punti) e «36 settimane» (`tabs.py:396-397`) da costanti del modello. **Rischio:** basso. **Accettazione:** nessun letterale duplicato.

### Lotto 6.3 — Aggiornare il README
- **Obiettivo:** allineare il README al codice (versione v9, struttura, divisioni M/F, multi-slot, ingaggio vs stipendio, Cross/Indoor come etichette). **Rischio:** nullo, ma **fuori** da questa sessione di ricognizione. **Dipende da:** QUESTIONS 14.
