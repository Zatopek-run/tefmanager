# AUDIT — stato reale del codice (sessione di ricognizione)

Data: 2026-11-19 · branch `main` · working tree pulito all'inizio · **nessun file di codice modificato** (nella sessione di ricognizione).

> **Aggiornamento 2026-11-19 — lotti 1.1 e 1.2:** R1 e R2 sono **chiusi** (commit `5a21154`, `85778a9`); le righe sotto che descrivono migrazioni non atomiche, assenza di backup e `DROP` silenzioso sono lo stato *prima* di quei commit. Nuovi rilievi emersi: §7. Test: 105 (80 + 21 senza Qt + 4 smoke).
Il codice descrive lo stato attuale; il README è stato confrontato con esso (sezione 4).

## 0. Come è stato verificato (e cosa no)

| Tipo | Cosa | Esito |
| --- | --- | --- |
| Lettura | `simulation.py` (quasi intero), `entities.py`, `generator.py` (gran parte), `game_controller.py` (quasi intero), `database.py` (schema/migrazioni/salvataggio), punti mirati di `views/` | letto |
| Test | `QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests -v` | **80 test, OK, 3,1 s** (rieseguito anche `tests.test_game`: 80 OK, 3,2 s) |
| Esperimento | Migrazione con ALTER fallito a metà (**migrazione sintetica** in scratchpad, Python 3.14.4, non una migrazione reale del progetto) | salvataggio non più apribile (R1) |
| Esperimento | `.db` con `user_version` = `SCHEMA_VERSION`+1 aperto con `DatabaseManager` | dati azzerati (R2) |
| Esperimento | Dilemma lasciato pendente, 40 settimane | nessun nuovo dilemma (controllo: 12 senza pendente) (R4) |
| Esperimento | `deepcopy` + `Random(42)` per tick, 8 sett. | identico; stesso `.db` ricaricato 2×, RNG del controller non seminato, 8 sett. → **diverso** (budget 1713 vs −2821) (R5) |
| Esperimento | `import models.*` con `python3` di sistema senza PyQt6 | tutti OK **tranne** `models.race_export` (R6) |
| Esperimento | Carriera 36 sett. con budget illimitato: cambi fase, verdetto, gare per fase | vedi Q1/Q2 |
| Esperimento | Carriera in autopilota (nessuna azione del giocatore) | bancarotta alla sett. 14 (R3) |
| Esperimento | Eccezione non gestita in uno slot PyQt6 (pulsante `clicked` → `raise`, offscreen, PyQt6 su Python 3.14.4) | **il processo termina**: traceback poi `Aborted (core dumped)`, exit 134 (SIGABRT). Con `UnsupportedSaveVersion` che esce da `load_save_slot` lo smoke test del lotto 1.2 muore con -6 |
| **NON verificato** | App con mouse/tastiera reali; doppio click reale; build PyInstaller (**non eseguita**: scriverebbe `build/`, `dist/`, `.spec`); Godot (non installato nel PATH) | — |

Gli esperimenti sono script in `/tmp/claude-1000/.../scratchpad/exp/` (fuori dal repo). `git status` dopo gli esperimenti: pulito.

## 1. Baseline

- `git status` iniziale: pulito. Commit: 76.
- File tracciati: 23 `.py` (16.658 righe), 25 `.gd` (5.038 righe). Nota: `godot_viewer/.godot/imported/*` (file generati dall'import) è **tracciato in git** (`git ls-files`).
- Python non è nel PATH (`python: command not found`); si usa `.venv/bin/python` (Python 3.14.4, PyQt6 presente). `python3` di sistema **non** ha PyQt6.

Righe di codice per file (ordine decrescente, solo i principali):

| LOC | File | | LOC | File |
| ---: | --- | --- | ---: | --- |
| 2326 | views/tabs.py | | 527 | views/styles.py |
| 2187 | tests/test_game.py | | 524 | godot_viewer/autoload/RaceController.gd |
| 2075 | views/race_3d.py | | 436 | views/athlete_dialog.py |
| 1449 | views/race_viewer.py | | 364 | godot_viewer/scripts/Stadium.gd |
| 1430 | models/simulation.py | | 352 | views/main_window.py |
| 998 | models/database.py | | 335 | views/start_screen.py |
| 936 | models/entities.py | | 228 | views/godot_launcher.py |
| 867 | controllers/game_controller.py | | 210 | views/results_board.py |
| 793 | godot_viewer/scripts/HUD.gd | | 172 | models/race_export.py |
| 709 | views/dialogs.py | | 47 | models/bibs.py |
| 699 | models/generator.py | | 27 | main.py |
| 645 | views/field_3d.py | | 3×1 | `__init__.py` |

Struttura reale: `main.py`, `models/` (entities, generator, simulation, database, race_export, bibs), `controllers/game_controller.py`, `views/` (main_window, tabs, dialogs, athlete_dialog, start_screen, styles, race_viewer, race_3d, field_3d, results_board, godot_launcher), `tests/test_game.py` (unico file di test), `godot_viewer/` (modulo Godot separato), `data/societa_atletica_lazio.csv`, `TrackAndFieldManager.{sh,bat}`.

## 2. Tabella meccaniche (README → codice)

Legenda: OK · PARZIALE · ASSENTE · DIVERGENTE.

| Meccanica (README) | Stato | Evidenza | Nota |
| --- | --- | --- | --- |
| Vivaio (max 8, 14-17 anni, no stipendio) | OK | `entities.py:151`, `generator.py:399,404`, `game_controller.py:528-531` | |
| Vivaio +50% allenamento | OK | `entities.py:152`, `simulation.py:370-371` | È un moltiplicatore ×1,5 sulla *probabilità* di miglioramento (tetto 0,95, `simulation.py:385-388`), non sulla velocità |
| Promozione automatica a 18 anni | PARZIALE | `simulation.py:1392-1398` | L'età cresce **solo** alla rotazione di stagione in Carriera (`simulation.py:1383-1384`): nel Prototipo non scatta mai; in Carriera un 17enne diventa 18 solo al cambio stagione |
| Scouting: 8 punti/sett., ricerca 2 punti + 1 per filtro | OK | `entities.py:153-154`, `game_controller.py:77-82,483-485` | Filtri: disciplina e potenziale ≥85 |
| Scouting: costo in denaro crescente | OK | `entities.py:156`, `game_controller.py:77-82` | Tabella cumulativa 0,0,150,350,600,1000,1500,2200,3000 |
| Scouting: segnalati e non presi se ne vanno a fine settimana | OK | `game_controller.py:845` (azzera `scouting_results`), `simulation.py:1370` (azzera punti) | I risultati vivono **solo in memoria** (`game_controller.py:119`): chiudere l'app li perde |
| Atteggiamento in gara (Prudente/Normale/Aggressivo) | OK | `entities.py:135-148`, `simulation.py:745-761` | Rischio ×0,55 con medico (`:757`), ×0,7 Resiliente (`:759`) |
| Classifica a squadre (1°=8 … 8°=1) | OK | `entities.py:171`, `simulation.py:827-832` | Vedi Q3 per N≠8 |
| Classifica di lega cumulativa, azzerata a stagione | OK | `simulation.py:1040-1041` (somma), `:1382` (azzera) | |
| Prime 3 società: prestigio extra | OK | `simulation.py:1038-1039` | `{1:10, 2:6, 3:3}` |
| Gara senza convocato regala punti ai rivali | OK | `simulation.py:741-743,610-624` | |
| Impianto: palestra 0-5, +6%/livello, costo di gestione | OK | `entities.py:157-159,175-176`, `game_controller.py:579-593`, `simulation.py:369,1234` | |
| Impianto: tribune ampliabili | OK | `entities.py:160-161,179-182`, `game_controller.py:595-606` | Nessun costo di gestione delle tribune (NON TROVATO, vedi §6) |
| Casa/trasferta alternati | OK | `entities.py:906-910` | Stagione 1: casa a sett. 4,12,20,28,36 (verificato); stagione 2 invertita (calcolato dalla formula, non simulato) |
| Biglietti, spettatori limitati dalla capienza | OK | `simulation.py:598-607`, `entities.py:162-167` | |
| Fan da piazzamenti/PB/record | OK | `simulation.py:899-901` | I fan **non scendono mai** (solo `+=`, `:901`) |
| Sponsor individuali (maggiorenni, Prima Squadra) | OK | `simulation.py:1230` | `fans // 4` per atleta ≥18 anni; illimitato (R10) |
| Fedeltà sponsor (acquisto/cessione −, meno per under 21; +2/sett.) | PARZIALE | `game_controller.py:419,454`, `simulation.py:1228,1369` | Acquisto: −6 (<21) / −12; cessione: **−8 fisso** solo Prima Squadra, senza sconto under 21 (`:453-454`); ingresso/promozione dal vivaio: nessun effetto |
| Debito: 5% a settimana | OK | `entities.py:168`, `simulation.py:1338-1341` | L'etichetta «(5%)» è scritta a mano (`simulation.py:1341`, `tabs.py:363`) |
| Fallimento sotto −$20.000 | PARZIALE | `entities.py:169`, `simulation.py:1345-1352`, `game_controller.py:839` | Imposta solo `bankrupt` e blocca `advance_week`; il giocatore può ancora agire; il bug del debito azzerato (R7) lo aggira |
| Declino con l'età | OK | `simulation.py:433-440`, `entities.py:87-96` | Solo velocità/resistenza/forza (non tecnica); prob. `min(0,5; 0,10×anni oltre picco)` a settimana |
| Allenatori: 4 abilità 1-100 | OK | `entities.py:186-198`, `generator.py:425-446` | |
| Assunzione: abilità principale+secondaria+livello, uno a settimana, max 6/2 | OK | `game_controller.py:609-655,621-630` | Il «$1.500-$7.500» è l'**ingaggio una tantum** (`entities.py:207-208`), non uno stipendio (vedi Q4) |
| Allenatori: decay abilità | OK | `simulation.py:1354-1360` | 10%/sett.: −1 a una abilità sopra 25 |
| Allenatori: saturazione oltre 6 atleti | OK | `simulation.py:94-98,363-366` | `max(0,5; 1−0,08×(carico−6))` |
| Senza allenatore adatto cresce più lentamente | OK | `entities.py:198`, `simulation.py:364-365` | ×0,6 |
| Staffette: 4 frazionisti + riserva, una sola staffetta per atleta | OK | `entities.py:525-542`, `game_controller.py:736-739` | Per divisione (M/F) |
| Staffette: 4x400 solo con 400m; 4x100 non indoor; in Cross nessuna | OK | `entities.py:859-871`, `:230-255` | |
| Staffette: tempo con frazione finale più pesante, affiatamento | OK | `entities.py:256`, `simulation.py:950-955` | |
| Staffette: affiatamento E…A++ | OK | `entities.py:261-264` | Scala interna 0-100 (Q8) |
| Staffette: sostituzione −25% e cooldown 4 sett. | PARZIALE | `game_controller.py:741-758`, `simulation.py:197-199` | Vale anche per la **riserva** (slot 4) e per l'auto-composizione; in gara c'è un altro meccanismo additivo (−15, +3% DQ: `simulation.py:945,224`) |
| Staffette: DQ cambio fuori zona | OK | `simulation.py:223-224,946` | |
| Staffette: infortunato sostituito dalla riserva | OK | `simulation.py:936-938` | |
| Staffette: contano per la squadra, record propri, nessuna forma/fan | OK | `simulation.py:926-1030` | Nessuna fatica per i frazionisti |
| Rivali: 7 società/categoria con un atleta per gara | OK | `generator.py:628-653`, verificato 7/7/7/7 | M e F |
| Rivali: si allenano (under 24 crescono, 24-27 poco, dai 30 calano) | OK | `simulation.py:628-636,639-650` | 28-29: deriva zero (Q9) |
| Rivali: invecchiano, si ritirano, reclutano | OK | `simulation.py:653-679`, `entities.py:547` | Ritiro a 33; da 31 il 30%/stagione |
| Rivali: ambizione | OK | `simulation.py:682-690`, `:662-663` | |
| Promozioni/retrocessioni (prime 2 su, ultima giù, titolo) | OK | `entities.py:623-624`, `simulation.py:1167-1210` | Pareggio alfabetico (Q10) |
| Prototipo: 8 settimane, 2 gare, niente promozioni | PARZIALE | `entities.py:934-936`, `tabs.py:429,967-971` | Nulla ferma il gioco dopo la sett. 8: misurate gare alle sett. 12 e 16 (4 gare in 16 sett.) |
| Dilemmi etici | PARZIALE | `generator.py:662-699`, `game_controller.py:767-836` | Due soli tipi; si bloccano se la finestra viene chiusa (R4); effetti nel controller con cifre scritte a mano; bug debito (R7) |
| Mercato (agenti liberi) | PARZIALE | `game_controller.py:396-444`, `generator.py:346-372,656-659` | Solo acquisto; nessun incasso dalle cessioni; il pool è in memoria (si rigenera ricaricando) |
| Migrazioni save v2→v6 | **DIVERGENTE** (README) | `database.py:42,107-115`, `_init_schema` | Il codice è a **v9**; migra v2…v8→v9. *Prima dei lotti 1.1/1.2:* nessun backup, non atomico, DROP su versioni ignote. *Ora:* backup verificato + transazione + rifiuto delle versioni ignote (R1, R2 chiusi) |

## 3. Risposte alle 14 domande

**Q1 — Stagione.** Una fase dura **12 settimane**: `simulation.py:1375` `(state.week - 1) % 12 == 0` dopo `week += 1` (`:1372`). Cicli: Outdoor sett. 1-12, Cross 13-24, Indoor 25-36 (misurato: cambi a 13, 25, 37). I punti di lega si azzerano in `simulation.py:1382` (subito dopo `close_season`, `:1380`); il verdetto si calcola in `close_season` (`simulation.py:1167-1210`) sulla tabella `league_standings()` (`entities.py:821-829`). La tabella si somma in `simulation.py:1040-1041` durante il tick di gara, **prima** del verdetto dello stesso tick: l'ultima gara (sett. 36) è inclusa. Coerente con una classifica cumulativa su 36 settimane (misurato: 9 gare, verdetto a fine sett. 36). **Ma** 12 e 36 sono letterali separati: `simulation.py:1375`, `entities.py:843`, `tabs.py:396-397`; nessuna costante comune.

**Q2 — Discipline × fase.** `active_events` (`entities.py:912-917`) **ignora la fase**: in Carriera sono sempre tutte e 6 (100m, 400m, 800m, 1500m, Lungo, Peso; l'800m dal 2026-11-19). Cross e Indoor sono **etichette** sugli stessi eventi. Differenze reali: Cross → nessuna staffetta (`entities.py:863-864`); Indoor → niente 4x100m, sì 4x400m (`entities.py:868-869`, `:249`), meteo sempre Sereno (`simulation.py:710-714`), vento 0,0 (`simulation.py:557-558`), niente calo di pubblico per pioggia (`:603`). In Cross velocisti e pesisti corrono **100m e Peso** come in Outdoor; non esiste una gara di corsa campestre (grep `cross` → solo la fase, §6). Indoor si corre il **100m** (non 60m; grep `60 ?m` → NON TROVATO come evento, §6), con vento 0,0 (verificato: `wind_ms` = 0.0 nelle gare indoor).

**Q3 — Iscritti per gara e punti.** **Uno** per società per gara e per divisione: `event_lineup: Dict[str, Optional[int]]` (`entities.py:790,808`), usata in `simulation.py:734-739`. Ogni rivale schiera un atleta per evento/divisione (`generator.py:644-650`). Con 7 rivali per categoria (verificato) N = 8: scala `TEAM_POINTS` 8…1 (`entities.py:171`, applicata per posizione in `simulation.py:832` con `.get(idx, 0)`). Se N≠8: oltre l'8° posto 0 punti, nessuna rinormalizzazione. Giocatore assente: i 7 rivali prendono 8…2 e **l'1 non viene mai assegnato** (`simulation.py:610-624`). Giocatore ritirato/squalificato: ultimo e senza punti (`:823-825,831`), i rivali 8…2. Il controller **non valida** che lo stesso atleta non sia in più gare né che il genere coincida con la divisione (`game_controller.py:370-374`; la UI potrebbe filtrare — non verificato).

**Q4 — Salari ed entrate/uscite.** L'«$1.500-$7.500» è `coach_hire_cost(tier) = 1500×tier` (`entities.py:207-208`), **pagato una volta** all'assunzione (`game_controller.py:631-633`): non è settimanale né stagionale. Lo stipendio settimanale dell'allenatore è `40 + round(Σ max(0, v−40) × 2,2)` (`entities.py:211-212`); misurato: tier 1 = $99 (1 abilità) / $137 (2); tier 5 = $161 / $260 a settimana. Gli atleti **hanno** stipendio settimanale (`senior_wage = clamp(100|80 + overall×4,2; 95; 950)`, `generator.py:410-413`; vivaio 0, `generator.py:404`), pagato per tutta la Prima Squadra, infortunati inclusi (`simulation.py:1231`), mai rivisto dopo la creazione o la promozione (grep, §6). Elenco completo di entrate/uscite con formula e costante: `docs/BALANCE.md` §A. Misura chiave: all'avvio la Carriera ha flusso netto **−$4.432/sett.** (sponsor 638 + quote 450 contro stipendi 4.972 + allenatori 548) e il Prototipo **−$2.291/sett.**

**Q5 — Vento.** Solo `100m` e `Salto in Lungo` (`wind_affected=True`: `entities.py:301,336`; gli altri `False`). Tiro per gara/divisione (`simulation.py:748`, `:555-563`): 0,0 indoor. Effetto: 100m −0,055 s per m/s (`:479,486`), Lungo +0,08 m per m/s (`:513`), simmetrico per vento contrario. Non valido se **> +2,0** (`:751`): vento contrario non invalida mai. Una prestazione con vento illegale **non** aggiorna PB (`:838-844`), record sociale (`:846-852`), momento storico (`:873`), obiettivo storico (`:587`) né il PB del rivale (`:808`); **però** piazzamento, punti squadra, premi, prestigio e fan restano (`:827-832,890-901`). PB (per atleta, `personal_best`) e record (per società e divisione, `club_records[_f]`) sono oggetti distinti con la **stessa** soglia di legalità; non esiste un «migliore assistito» salvato (grep, §6).

**Q6 — RNG.** Usi: `random.Random()` non seminato nel controller (`game_controller.py:110`) e come ripiego `rng or random.Random()` in ogni funzione (`simulation.py:299,313,698,1131,1264`; `generator.py:189,278,314,354,388,434,453,583,634,669`); tutta la simulazione riceve un `rng` iniettabile (verificato: `deepcopy` + `Random(42)` → esito identico). Seed/stato **non salvati** (grep `seed|rng_state|getstate|setstate` in `database.py`/`entities.py` → nessun risultato). Ricaricare lo stesso salvataggio e avanzare **non** dà lo stesso risultato (misurato: budget 1713 vs −2821). Anche le azioni UI consumano l'RNG del controller (scouting `game_controller.py:500`, mercato `:388-391`), quindi il solo seed non basterebbe: serve lo stato (`getstate`). Seed deterministici esistenti: `database.py:152` (backfill, seed = id atleta), `race_viewer.py:55-57`, `bibs.py:40`, `race_export.py:49` (CRC32). **Difetto**: `views/dialogs.py:55` usa `hash()` su stringhe, salato per processo (misurato: 3 esecuzioni → 3, −3, 2): la fascia del potenziale mostrata nel mercato cambia a ogni avvio dell'app.

**Q7 — Idempotenza dell'avanzamento.** Non idempotente per natura (`week += 1`, `simulation.py:1372`). Nessuna protezione: `advance_btn.clicked.connect(controller.advance_week)` (`main_window.py:142`); il pulsante si disabilita solo se `bankrupt` (`:312`); grep `_advancing|_busy|debounce` → NON TROVATO. In una settimana senza gara il tick è sincrono e i click in coda produrrebbero due tick (dedotto dal codice, **non provato con mouse reale**). In settimana di gara le finestre modali (`main_window.py:332-336`) bloccano la finestra principale. Nessun rollback: se un'eccezione interrompe il tick, lo stato in memoria resta mutato a metà e il successivo `save_game` di qualunque azione lo persiste (il salvataggio del tick è a `game_controller.py:847`, dopo). Si può avanzare con un dilemma pendente.

**Q8 — Affiatamento staffette.** `Relay.harmony` intero 0-100, iniziale 30 (`entities.py:531`); grado = `harmony // 10` su `E,D,C-,C,C+,B-,B,B+,A,A+,A++` (`entities.py:261-264`; 100 → A++). Crescita settimanale: +4 (+6 se ha gareggiato) a organico completo, +2 (+6) con 1 assente e riserva in forma, −2 altrimenti (`simulation.py:252-257`). La penalità del 25% è **moltiplicativa**: `int(harmony × 0.75)` (`game_controller.py:757`, duplicata in `simulation.py:198`). Cooldown: `RELAY_CHANGE_COOLDOWN_WEEKS = 4` (`entities.py:257`), campo `last_change_week` per staffetta (default −100, `entities.py:532`), confronto `state.week − last_change_week < 4` (`game_controller.py:750-756`, auto `:701-707`), persistito in JSON (`database.py:125,139`). In gara, una riserva che subentra è invece **additiva**: `harmony − 15` (`simulation.py:945`) e +3% di DQ (`:224`); DQ base `(60 − harmony)×0,006` (`:224`).

**Q9 — Rivali a 28 e 29 anni.** Deriva settimanale **0,0** (`simulation.py:634-635`: ≤23 → 0,13; ≤27 → 0,05; ≤29 → 0,0; da 30 `−min(0,3; 0,08×(età−29))`), più rumore gaussiano σ 0,15 a settimana (`:647`): passeggiata casuale senza tendenza. L'ambizione scala solo la deriva positiva (`:645-646`). Ritiro: a 33 sempre, da 31 il 30% a stagione (`:667`). Il README non descrive 28-29.

**Q10 — Spareggio.** `entities.py:826-829`: `sorted(..., key=(−punti, nome))`. **Può decidere** promozione (2° vs 3°), retrocessione (ultimo) e titolo (`close_season` usa `league_position`, `entities.py:832-836`). Il nome del giocatore lo sceglie l'utente: un nome che inizia per «A» vince tutti gli spareggi. La classifica del singolo meeting usa invece l'ordine di inserimento (`simulation.py:1033`, giocatore per primo): regole diverse.

**Q11 — Migrazioni.** Sono in `database.py:42-115` e vengono applicate in `_init_schema` (`:393-415`). Transazione: **no** (ALTER in autocommit nel modulo `sqlite3`; misurato su 3.14.4: colonne già aggiunte restano, `user_version` resta quello vecchio, al tentativo successivo `duplicate column name`). Backup: **no** (grep `backup|shutil|\.bak|copyfile` → nessun risultato). `PRAGMA user_version`: letto a `:395`, scritto a `:403` e `:415`. Se un ALTER fallisce a metà: salvataggio inapribile in modo permanente. Se `user_version` non è né in `MIGRATIONS` né uguale a `SCHEMA_VERSION` (v0, v1, o **più nuovo**): `DROP TABLE` di tutto (`:404-415`; misurato). Si innesca al **caricamento** di uno slot (`game_controller.py:260` ← `start_screen.py:306,313`), non all'avvio (`main.py:20` usa `auto_create=False`) né all'elenco degli slot (`read_save_summary` apre in sola lettura, `database.py:307-309`). Test esistenti: solo percorsi di successo (`test_game.py:698,1730,1792`); nessun test di fallimento o backup.

**Q12 — Import PyQt6 in `models/`.** Diretti: **nessuno** (grep `PyQt|PySide|QtCore|QtGui|QtWidgets`: solo commenti in `race_export.py:5,38`, `bibs.py:31`). Indiretto: **`models/race_export.py:22`** `from views.race_viewer import _rng, generate_attempts, reaction_time`, e `views/race_viewer.py:13-15` importa PyQt6 → `import models.race_export` fallisce senza PyQt6 (misurato). È anche una dipendenza invertita models→views. Gli altri moduli di `models/` si importano senza Qt (misurato: entities, generator, simulation, database, bibs).

**Q13 — Viste: DB e logica.** Accesso a SQLite dalle viste: **nessuno** diretto (grep `sqlite3|\.execute\(` in `views/` → nessun risultato); usano solo `get_default_save_path` (`godot_launcher.py:25`), `SaveSlotInfo` (`start_screen.py:25`) ed `export_race` (`godot_launcher.py:27`). Scritture dirette allo stato dalle viste: nessuna (grep di assegnazioni `state.x = / += / -=` in `views/` → nessun risultato). Logica di gioco nelle viste: zona promozione/retrocessione duplicata (`tabs.py:384-390,1058-1060`, `dialogs.py:689-691`; modello: `simulation.py:1177-1186`); «36 settimane» (`tabs.py:396-397`); soglia di severità debito `BANKRUPTCY_THRESHOLD // 2` (`tabs.py:171`); soglia fatica ≥75 in 5 punti (`main_window.py:283`, `tabs.py:187,468,752,756`); controlli di fondi duplicati (`dialogs.py:373,406,632`; controller `:404,490`, `_pay :568`); testo «5% interessi» (`tabs.py:363`); `hash()` salato (`dialogs.py:55`); `generate_attempts`/`reaction_time` in `race_viewer.py` usati dal modello (§Q12; per CLAUDE.md è una scelta voluta: la vista mette in scena un risultato già deciso). Il **controller** contiene logica di gioco con cifre a mano: `game_controller.py:303,332,419,454,776-832`.

**Q14 — Costanti di bilanciamento.** **Sparse**, non centralizzate. Moduli: `entities.py` (blocchi di costanti e `TIER_CONFIG`), `simulation.py` (`BODY_*` e centinaia di letterali nelle funzioni), `generator.py` (letterali), `game_controller.py` (letterali). Non esiste un modulo di bilanciamento (nessun file `balance`/`config`). Inventario in `docs/BALANCE.md`. Inoltre i default di `GameState` (`entities.py:776-785`: budget 12000, reputazione 70) differiscono da quelli di `_create_fresh_state` (`game_controller.py:154,162,182`: budget 10000/18000, reputazione 75).

## 4. Discrepanze README / codice

1. **Versione schema**: README «migrati a v6»; codice `SCHEMA_VERSION = 9` (`database.py:42`). `CLAUDE.md` diceva 7 (corretto in questa sessione).
2. **Struttura**: il README elenca 4 file in `models/`, 3 in `controllers`/`views`; mancano `race_export.py`, `bibs.py`, `race_viewer.py`, `race_3d.py`, `field_3d.py`, `results_board.py`, `start_screen.py`, `godot_launcher.py`, `godot_viewer/`, `data/`.
3. **Salvataggio**: README «`~/.track_field_manager/savegame.db`»; ora multi-slot in `~/.track_field_manager/saves/` (`database.py:259-263`) con `savegame.db` come file legacy.
4. **Ingaggio allenatori**: «livello di ingaggio ($1.500-$7.500; più abilità = stipendio più alto)» confonde costo una tantum (`entities.py:207`) e stipendio settimanale (`:211`).
5. **Prototipo «8 settimane, 2 gare»**: il codice non si ferma (gare a sett. 12 e 16).
6. **Fedeltà**: «cessione … meno per gli under 21» non implementato (`game_controller.py:453-454`).
7. **Staffette**: «sostituire un titolare» vale anche per la riserva e per l'auto-composizione; esiste un secondo meccanismo in gara.
8. **Funzioni non documentate nel README**: divisione femminile (lineup, record e staffette separati, v8/v9), nazionalità/altezza/peso e modificatore fisico (v7), tabellone risultati, pettorali, visualizzatore Godot.
9. **Cross/Indoor**: il README parla di stagioni «Outdoor → Cross → Indoor» come se cambiassero le discipline; sono etichette (Q2).
10. **Comandi**: `python …` non funziona in questo ambiente (`python: command not found`); il README non cita il `.venv`.
11. `generator.py:670-671`: il commento dice «55% chance on week 3/7», il codice le rende certe (settimane 3 e 7).

## 5. Rischi (per impatto)

Categorie: **S** perdita save · **C** crash · **R** regole incoerenti · **B** bilanciamento · **T** debito tecnico.

| # | Cat. | Rischio | Evidenza |
| --- | --- | --- | --- |
| R1 | S/C | **✅ CHIUSO (lotto 1.1, `5a21154`)** — test `test_migrations.py::TestMigrationSafety` (E1: `test_e1_failed_migration_leaves_original_untouched`, rosso prima, verde dopo). **Era anche un crash**: l'eccezione usciva dal click e PyQt6 termina il processo (exit 134, misurato). **Migrazione non atomica**: un ALTER che fallisce a metà lascia colonne aggiunte e `user_version` vecchio; ogni apertura successiva solleva `duplicate column name` → salvataggio perso per l'utente. L'eccezione sale dal click di caricamento (`game_controller.py:260`); il comportamento di PyQt6 su eccezione in uno slot non è stato verificato | `database.py:393-415`; esperimento sintetico E1 |
| R2 | S/C | **✅ CHIUSO (lotto 1.2, `85778a9`)** — test `test_migrations.py::TestUnsupportedVersions` (E2) e `test_game.py::TestUnsupportedSlotLoading` (il click non uccide l'app). **Anche un crash**, come R1. **DROP silenzioso** di un salvataggio con versione non riconosciuta (più nuovo, v0, v1): aprire con un'app più vecchia cancella la partita senza avviso né backup | `database.py:404-415`; esperimento E2 |
| R3 | B | ✅ **CHIUSO il 2026-11-20 (PIANOLAVORO A.1)**: sponsor +40%, premi +25%, rimborsi −45%, bonus promozione; vale per le partite nuove, non per i salvataggi esistenti (rimborsi già scritti). Originale: **Economia insostenibile all'avvio**: Carriera −$4.432/sett., Prototipo −$2.291/sett.; in autopilota bancarotta alla sett. 14 (seed 3, una sola esecuzione). Il giocatore deve tagliare atleti per sopravvivere | `simulation.py:1224-1248`, `generator.py:410-413`; misura |
| R4 | R | ✅ **CHIUSO il 2026-11-20 (PIANOLAVORO A.4)**: chiudere la finestra o «Ignora» chiama `dismiss_dilemma` (nessun effetto), e il tick scarta un pendente. Descrizione originale: **Dilemma bloccato**: chiudere la finestra (Esc) non risolve `pending_dilemma`; nessuna vista lo riapre; `maybe_generate_dilemma` non ne crea altri finché è pendente → dilemmi finiti per sempre (misurato: 0 in 40 sett. contro 12). Resta salvato nel DB | `main_window.py:342-345`, `generator.py:667` |
| R5 | R | ✅ **CHIUSO il 2026-11-20 (PIANOLAVORO A.3)**: stato dell'RNG salvato (v13) e ripristinato, `tests/test_rng_controller.py`. **Crepa residua:** il pool del mercato non è salvato e si rigenera dall'RNG all'apertura. Originale: **Non riproducibile**: RNG non seminato né salvato; stesso salvataggio → esiti diversi; si può ricaricare per ritirare i dadi (scouting, mercato, gara) | `game_controller.py:110`; esperimento |
| R6 | T | **models→views→PyQt6**: `models/race_export.py` non importabile senza Qt; i test di simulazione non possono girare senza Qt (l'intera suite importa PyQt6 a `test_game.py:15`) | `race_export.py:22` |
| R7 | R/B | **Debito azzerato dai dilemmi**: `budget = max(0, budget − 600)` (e −300) porta a 0 un bilancio negativo | `game_controller.py:798,825` |
| R8 | R | ✅ **CHIUSO il 2026-11-20 (PIANOLAVORO A.5)**: `GameController.advance_week` non è rientrante (`is_advancing`) e il pulsante si spegne durante il tick; il doppio click con mouse vero resta **non provato**. Originale: **Doppio click**: nessuna protezione sul tick (dedotto) | `main_window.py:142,312` |
| R9 | R | ✅ **CHIUSO il 2026-11-20 (PIANOLAVORO A.2)**: piazzamenti salvati (v12) + sorteggio deterministico, stessa regola per lega e meeting. Originale: **Spareggio alfabetico** modificabile dal giocatore (nome club) e diverso dalla regola del meeting | `entities.py:826-829`, `simulation.py:1033` |
| R10 | B | **Fan e sponsor illimitati**: i fan non calano mai; `fans//4` per atleta ≥18 a settimana senza tetto | `simulation.py:901,1230` |
| R11 | R | (✅ **risolto il 2026-11-20, C.2**: in Carriera gli obiettivi del Board si rinnovano a ogni stagione e si giudicano a fine stagione; resta vero per il Prototipo, che non ha stagioni) **Obiettivi mai rinnovati**: creati solo alla nuova partita; «promote» non si riazzera dopo una retrocessione | `game_controller.py:172`; nessun altro chiamante |
| R12 | R | **Obiettivo «traguardo storico» femminile** confronta con la soglia maschile (`ev.historic_mark`), mentre il momento storico usa quella femminile | `simulation.py:588` vs `:863-867` |
| R13 | R | **Eventi/atleti non validati**: stesso atleta in più gare o divisione sbagliata non bloccati dal controller | `game_controller.py:370-374` |
| R14 | B | Stipendi mai rivisti (l'atleta migliora ma costa uguale); quote tesserati fisse a 450; nessun costo tribune; cessioni senza incasso | grep §6 |
| R15 | T | Costanti sparse e duplicate (0,75 in due punti; 36/12 in tre; fatica 75 in cinque); default di `GameState` ≠ nuova partita | `BALANCE.md` |
| R16 | R | Il prototipo non finisce; l'età cresce solo in Carriera: promozione vivaio a 18 anni e declino non avvengono nel Prototipo | `entities.py:934`, `simulation.py:1383` |
| R17 | T | (`hash()` salato per la fascia del potenziale: ✅ risolto il 2026-11-20, A.3); `godot_viewer/.godot/imported/*` tracciato; un solo file di test da 2.187 righe | `dialogs.py:55` |
| R18 | B | Pool mercato e risultati scouting solo in memoria: chiudere e riaprire rigenera il mercato (ritiro dei dadi gratuito) | `game_controller.py:119-121` |
| R19 | R | I tentativi di lungo e peso mostrati dalle viste (PyQt e Godot) sono inventati a posteriori da `generate_attempts` (15% di nulli a caso) e **non** coincidono col «tentativo nullo» del rischio B.2 deciso dal modello (2026-11-20; visibile solo nel testo del risultato). L'esito resta quello del modello | `views/race_viewer.py:128`, `simulation.py` |
| R20 | T | Una staffetta **squalificata salta** la `r.gauss(0; 2,5)` del proprio tempo (`if disqualified: … else: … r.gauss`), e `random.gauss` tiene una cache a coppie: se due partite identiche (stesso seme) differiscono per una sola DQ, le estrazioni successive del meeting (altre staffette, gauss dei rivali) si sfasano. Trovato lavorando a B.3 (2026-11-20) **leggendo il codice**, non con un esperimento dedicato. Conseguenza pratica: nelle misure di Q25 le differenze tra strategie sono appaiate solo in parte e gli errori standard riportati sono per questo un po' ottimistici (le medie restano corrette). **Non corretto** (cambierebbe i risultati di tutte le partite esistenti: scelta di design, da discutere) | `simulation.py` (blocco staffette) |
| R21 | T | **`test_economy` (A.1) passa per fortuna dei cinque semi.** Il test chiede `min(deltas) >= -1000` su 5 partite da 36 settimane. Misurato il 2026-11-20 su 15 semi con due sequenze di estrazioni diverse (stesso codice; il campo del ranking sposta le estrazioni o no): con la sequenza di prima 0 partite su 15 sotto −1.000 € (min −29), con quella spostata 3 su 15 (−11.249, −1.718, −4.800). Su 30 partite 3 sono sotto soglia (~10%): con quella frequenza il test fallirebbe nel ~40% dei casi cambiando i semi. Campione piccolo: l'ipotesi è che la cifra di A.1 lasci una coda di partite in deficit, **non verificata** con più semi. **Test corretto il 2026-11-20** (richiesta dell'utente, dopo il passaggio dei sintetici del ranking all'RNG della partita): ora guarda la distribuzione di 30 partite (mediana in attivo, al massimo il 30% sotto −1.000 €, nessun fallimento, media ≤ 40.000 €). Misura con la sequenza nuova su 40 semi: 6 su 40 (15%) sotto −1.000 €, minimo circa −10.100 €, mediana circa 9.900 €. **Resta un fatto di design, non corretto:** il criterio di A.1 («deficit < 1.000 € dopo 36 settimane») non vale per ogni partita in autopilota; ritoccare le cifre per ottenerlo è una scelta tua | `tests/test_economy.py` |
| R22 | R | **Il Board si soddisfa senza giocare** (C.2): in autopilota il piazzamento in lega non è mai centrato (posti 5-8 su 30 partite) ma bilancio (83%) e record (100%) bastano, quindi la stagione è fallita solo nel 17% dei casi e 2 partite su 30 sono esonerate in 2 stagioni. I record sono quasi regalati: una società senza record li stabilisce a ogni gara. Misurato il 2026-11-20 (30 semi, Provinciale, nessuna azione). **Non corretto**: sono cifre provvisorie e la difficoltà è una scelta tua (QUESTIONS Q27) | `models/board.py` |
| R23 | B | Lo slot di un **esonerato** non è segnalato nell'elenco della schermata iniziale (il fallimento sì: «SOCIETÀ FALLITA»): `read_save_summary` non legge `board_json`. Trovato lavorando a C.2 (2026-11-20). **Non corretto** | `database.py: read_save_summary`, `start_screen.py` |
| R24 | B | **La Prima Squadra si svuota col tempo** (C.3): nessuno rimpiazza chi si ritira. Misura in autopilota (6 partite, 8 stagioni, nessun acquisto né scouting): da 16 atleti a 3-8, 8-13 ritirati. La rosa iniziale ha 19-32 anni, quindi già nelle prime 2-3 stagioni molti sono a 33+; il rimpiazzo è tutto a carico del giocatore (vivaio, scouting, mercato). Non è un difetto del codice ma una conseguenza di design: va confermata (QUESTIONS Q28). Misurato il 2026-11-20 | `simulation.py: retire_veterans` |
| R25 | B | **Nessun infortunio è davvero «grave»**: durano 1-4 settimane (`simulation.py`, allenamento `randint(1,3)`, gara `randint(1,3)+1`, squalifica doping 4), quindi il «ritiro per infortunio grave» del piano è stato definito come 3 infortuni nella stessa stagione (Q28). Gli infortuni lunghi sono un'idea per i lotti E (medico/impianti). Trovato lavorando a C.3 (2026-11-20). **Non corretto** | `simulation.py: apply_weekly_training` |
| R26 | B | **L'agente pesa solo sull'ingaggio al tesseramento** (D.1): il rimborso spese settimanale non cambia (R14), il vivaio non ha ingaggio e la relazione non influisce su rinnovi, scambi o sponsor. Trovato lavorando a D.1 (2026-11-20). Senza attenuazione stagionale, in autopilota la relazione saliva a 90-100 in 4-5 stagioni: corretto con `AGENT_RELATION_DRIFT` (Q29). **Il resto non corretto**: con D.2 la relazione sposta la flessibilità dell'agente in trattativa (R27), ma non pesa su rinnovi o sponsor. Un atleta arrivato a fine stagione e mai convocato conta come «fermo» (`AGENT_RELATION_IDLE`) come gli altri | `agents.py`, `simulation.py` |
| R27 | B | **Bonus per record e clausola (D.2): tre effetti da tenere d'occhio.** (1) Il bonus ha uno sconto **uguale** all'importo: è un pagamento rimandato, **non** un risparmio atteso; con record sociali quasi regalati (R22: senza record precedenti il primo risultato di ogni gara lo è) un atleta con bonus matura il bonus in ogni gara in cui debutta, e può costare più dello sconto. (2) La clausola vale per **tutti** gli atleti di Prima Squadra (20 settimane di rimborso, fino a ~€10.400, più del budget iniziale di €18.000 per i più cari): svincolare è diventato una decisione costosa e senza fondi è impossibile; l'unica uscita gratuita è «Non rinnovare» a fine contratto. (3) **La trattativa ha una mossa vincente senza rischio**: la flessibilità arriva al 50%, quindi la soglia è almeno metà della richiesta e un'offerta da €100 riceve quasi sempre la controfferta «soglia»; accettarla paga esattamente la soglia (misurato: 240 casi su 240, ogni personalità e relazione). Il giro di controfferta non conta mai e rifiutare non costa nulla (si può riaprire la trattativa sullo stesso candidato). È una scelta di design da prendere (Q30 b). Trovato lavorando a D.2 (2026-11-20). **Non corretto** | `market.py`, `simulation.py`, `game_controller.py` |
| R28 | B | **Finanze (D.3): quattro cose da sapere.** (1) Il **taglio dello sponsor** colpisce l'autopilota quasi sempre (7 partite su 8 chiudono la prima stagione fuori dai primi 5: nessuna scelta del giocatore lo evita da sola) e pesa €100-200 a settimana in Provinciale; è la cifra del piano, ma resta una scelta di bilanciamento. (2) Il bilancio mensile si ricava dal **libro mastro**, che il tick tronca a 400 voci: basta perché un mese ne ha 20-40, ma **ogni nuovo movimento di denaro deve passare dal libro mastro** o il saldo del mese non torna (c'è un test sull'invariante). (3) I mesi sono continui da inizio partita (4 settimane), non agganciati alle fasi da 12 settimane: 3 mesi per fase esatti, ma la prima settimana di una stagione non ha un bilancio proprio. (4) I diritti TV valgono solo in Internazionale, quindi non si vedono finché non si arriva là. (5) **Trovato e corretto**: i rifiuti dei dilemmi etici (−€600 e −€300) cambiavano il budget **senza** voce nel libro mastro, quindi il saldo del mese non tornava; ora passano da `_dilemma_cost` (categoria «Dilemmi»), che paga al più quello che c'è (prima `max(0, budget − costo)` **azzerava un debito**: con −5.000 il budget tornava a 0). Trovato lavorando a D.3 (2026-11-20). **Non corretto** | `finances.py`, `simulation.py` |
| R29 | B | **Avvio senza atleti (Q32): quattro effetti da tenere d'occhio.** (1) **Economia senza atleti:** entrano sponsor società e quote (450/sett. senza tesserati), i soli costi sono gli allenatori: la cassa sale da 18.000 a ~53.000 in 40 settimane e a ~100.000 in 100 (probe, seme 1); la Preparazione aggiunge 8 settimane di sponsor a ogni stagione. Non corretto: è bilanciamento. (2) **Obiettivi di fondazione quasi regalati:** il verdetto non ha conseguenze, quindi le cifre 6/2/3 non pesano; alla stagione 2 chi non ha fatto nulla ha il posto in lega allargato al massimo (3+3 = 6° su 8) e il conteggio delle stagioni fallite parte da 0. (3) **`release_athlete` rifiuta di svincolare l'ultimo atleta della Prima Squadra** (esistente): in una società nata vuota il primo tesserato non si può più mandare via. Non corretto. (4) **Rosa vuota, punti ancora da guardare:** il codice che fa `max()`/`min()`/medie sulle liste vuote delle schede non toccate qui (Rivali, Ranking, Staff, Albo) è stato provato solo con uno smoke test (nessuna eccezione, nessun giudizio sull'aspetto). **Nessuna eccezione** nelle 100 settimane senza atleti (modello) né nell'aggiornamento di tutte le schede (vista offscreen). `CompetitionSummary.club_absent` **non è salvato** (transitorio, serve ai dialoghi del tick): dopo una ricarica un meeting passato senza atleti si vede come un meeting senza gare. | `models/simulation.py`, `board.py`, `game_controller.py` |
| R30 | B | **Staff con attributi e mercato (E.1): tre limiti.** (1) **Il mercato parte da un catalogo di 9 candidati e si rinnova a ogni fine stagione** (`renew_staff_market`, 1 estrazione dell'RNG): le cifre dei candidati, delle fasce, del costo e della liquidazione (6 settimane) sono provvisorie e **non misurate in una partita lunga**; un candidato non assunto sparisce al rinnovo senza preavviso; l'identità con il codice di prima di E.1 (verificata contro `ec99dd1`) vale solo fino alla prima fine stagione (Q33). (2) **Esclusività per ruolo solo nel controller** (`toggle_staff`): il modello non la impone; un salvataggio con due assunti dello stesso ruolo conta il migliore (`hired_staff_attributes`) ma ne paga entrambi. (3) **Letterali vicini non toccati** (convenzione 2): il doppio passo di guarigione senza fisioterapista (0,35), `randint(22, 30)`, `randint(1, 3)` e la soglia di fatica 68 restano letterali in `apply_weekly_training`; ho spostato in `entities.py` solo i valori dello staff. | `models/staff.py`, `simulation.py` |
| R31 | B | **Impianti avanzati (E.2): limiti.** (1) **Nessuna manutenzione** e un solo livello per impianto: il piano non indica costi correnti, quindi l'acquisto è una tantum e conviene appena ci si arriva (Q34). (2) **Il taglio reale del centro medico è ≈12,5%**, non 15%: gli stop sono interi (1-3) con minimo 1 settimana, e un infortunio di 1 settimana non cambia mai. (3) **«Palestra pesi» e «Palestra» (a livelli) coesistono e si sommano**: due nomi simili, scelta dell'utente. (4) **Non misurati in una partita lunga**: né l'effetto sull'equilibrio né quando il budget permetta €20.000 (il Campo altura vale solo per il Mezzofondo). (5) **Nessuna tab «Infrastrutture» separata**: le quattro schede stanno in «Staff & Impianto» accanto a Palestra e Tribune (un test conta 10 tab): **la tab è più alta di ~125 px** e a 900 px di finestra le tabelle di allenatori e staff mostrano poche righe (scorrono); visto solo in uno screenshot offscreen, non con il mouse. | `models/facilities.py`, `simulation.py`, `views/tabs.py` |
| R32 | B | **Giovanili avanzate (E.3): limiti.** (1) **Costi provvisori e mai misurati**: Academy €60.000 per le cinque stelle (il budget iniziale è 18.000), osservatore €120-440 a settimana, quota di regione €800; non so se le cinque stelle siano raggiungibili o troppo facili. (2) **Il tetto 0,95 della probabilità di crescita** satura per i ragazzi con molto margine: le stelle in più non servono lì (BALANCE §T). (3) **Un solo osservatore capo, regioni fisse e un solo talento per regione**: nessun invio di scout in più paesi nello stesso tempo, nessuna rete permanente (scelta dell'utente: filtro della ricerca). (4) **L'OVR dei segnalati ora è una fascia** (±5 senza scout): è un passo indietro di informazione rispetto a prima di E.3 per chi non assume nessuno. (5) **I talenti regionali hanno `potential` ≥ qualità** ma gli altri valori restano quelli di un ragazzo grezzo: un velocista a 85 di velocità ha ancora resistenza e tecnica basse. (6) Il piano chiama `scout_attributes` un dizionario in `GameState`: ho usato un `Scout` con attributi nominati (catalogo fisso, come lo staff). (7) `potential_band_display` (mercato, scheda atleta) non è stata toccata: lì la fascia resta ±8 anche con un osservatore. | `models/scouting.py`, `controllers/game_controller.py`, `views/tabs.py` |
| R33 | B | **Notizie dinamiche (F.1): limiti.** (1) **Solo a fine mese** e senza memoria: se la condizione resta vera (conti in rosso, un atleta scontento) la stessa notizia si ripete ogni mese, con frase variata; non c'è un «nuova notizia» solo al cambio di stato. (2) **L'insoddisfazione è la relazione con l'agente ≤ 30** (D.1): non esiste un morale per atleta, quindi la notizia cita il cliente di quell'agente con il nome alfabeticamente primo e non per forza chi è davvero scontento. (3) **Il «record sociale» del piano non è stato duplicato**: c'era già («Nuovo Record Sociale…»). (4) **Il feed della Dashboard esisteva già** (`news_list`, 18 voci): non ho cambiato la vista, le nuove righe vi compaiono come le altre e possono spingere fuori le più vecchie (tetto 70 nel registro). (5) **«Allenatore del Mese» è solo una riga**: nessun premio, reputazione o prestigio (decisione rinviata a F.2/F.4). (6) Le soglie (30, ultimo posto, vittoria del meeting) sono mie e non misurate in partite lunghe. | `models/narrative.py` |
| R34 | B | **Conferenza stampa (F.2): limiti.** (1) **Solo dopo la gara**, non prima: il piano dice «pre/post gara». (2) **Il «morale» del piano non esiste** nel modello: le risposte agiscono su reputazione e relazione con l'agente (D.1); la relazione non ha effetto sul rendimento in gara, solo sul costo dell'ingaggio e sulle trattative. (3) **«Una conferenza per meeting» è tenuta solo in memoria** (`GameController._press_done`): dopo un riavvio la conferenza di un meeting già giocato non si riapre (non c'è modo di rivederla), ma lo stesso meeting non viene mai ripresentato dal gioco. (4) **L'atleta citato** è il miglior piazzamento individuale (a parità il nome alfabeticamente primo): una staffetta vinta senza vincitori individuali non porta alla domanda sul futuro. (5) **Cifre e soglie mie**, non misurate in partite lunghe: l'effetto su reputazione è piccolo (±2). (6) **Dialogo non provato con il mouse reale** (solo test offscreen e uno screenshot). | `models/press.py`, `views/dialogs.py`, `controllers/game_controller.py` |

## 6. Registro NON TROVATO (con il pattern usato)

| Cosa | Pattern/ricerca | Esito |
| --- | --- | --- |
| Backup del `.db` | `backup\|shutil\|\.bak\|copyfile` in `database.py entities.py simulation.py controllers/ views/main_window.py` | nessun risultato *(al momento della ricognizione; dal lotto 1.1 c'è `_create_backup`)* |
| Seed/stato RNG salvato | `rng_state\|getstate\|setstate\|seed` in `database.py entities.py simulation.py controllers/ views/main_window.py` | nessun risultato |
| Protezione doppio click | `_advancing\|_busy\|debounce\|QTimer.singleShot.*advance` | nessun risultato |
| Gara 60m | `60 ?m\|\b60m\b` in `models controllers views` | solo un commento a `race_viewer.py:62` |
| Gara di Cross (corsa campestre) | `cross` (case-insens.) in `entities.py simulation.py generator.py` | solo l'enum di fase |
| Incasso da cessione | `sell\|vend\|cession\|transfer_fee\|sale_price` in `models controllers` | nessun risultato |
| Costo di gestione tribune | `stand` in `simulation.py` | solo capienza (`:601,606`) |
| Revisione stipendi | assegnazioni `weekly_wage` in `models controllers` | solo `generator.py:264,272,404`, `simulation.py:1254` |
| «Migliore assistito dal vento» | `assist\|wind_best\|ventoso_pb\|best_wind` | nessun risultato |
| Decadimento dei fan | assegnazioni a `fans` | solo `+=` (`simulation.py:901`) |
| Rinnovo obiettivi a fine stagione | chiamanti di `create_season_objectives` | solo `game_controller.py:172` |
| Re-apertura dilemma pendente | `pending_dilemma` in `views/` | nessun risultato |
| Test di fallimento migrazione / backup | `def test_.*(migrat\|backup\|old_save…)` | solo percorsi di successo *(ora: `tests/test_migrations.py`)* |
| Modulo di bilanciamento | nessun file `balance`/`config` in `models/` | assente |

## 7. Rilievi emersi nei lotti 1.1/1.2 (NON corretti: fuori scope)

| # | Cosa | Dove |
| --- | --- | --- |
| N1 | `GameController(auto_create=True)` apre lo slot legacy dentro `__init__` (`_load_or_create_initial_state` → `self.db`) **senza** catturare `UnsupportedSaveVersion`/`SaveMigrationError`: con un legacy non apribile solleverebbe alla costruzione. Oggi non succede perché `main.py` usa `auto_create=False`. Anche `_create_fresh_state` apre `DatabaseManager(slot_path)` per i nuovi slot (file nuovo, rischio basso) | `game_controller.py:~138,~224` |
| N2 | «File → Carica» (`main_window.py:127` → `controller.load_game`) ora non solleva più, ma mostra l'errore solo nella barra di stato (`status_message`), non in un dialog: il dialog c'è solo dalla start screen | `main_window.py:127` |
| N3 | I backup di uno slot eliminato restano in `backups/` (orfani) e un nuovo slot con lo stesso nome li erediterebbe nella potatura (pattern per nome slot). Il ripristino è manuale: nessuna funzione nel gioco | `delete_save_slot`, `_prune_backups` |
| N4 | Nella tabella degli slot il segnaposto «Salvataggio di versione più recente (vN)» / «…danneggiato» è troncato dalla larghezza della colonna; il testo intero è nel tooltip. Solo estetica | `start_screen.py` |
| N5 | Le fixture di `test_migrations.py` hanno righe sentinella con `''` nelle colonne enum: si aprono con `DatabaseManager` ma **non** si caricano con `load_game` (`'' is not a valid Specialty`). I test di caricamento reale restano quelli di `test_game.py` | `tests/test_migrations.py` |
| N6 | Comportamento cambiato per coerenza con «`state`/`_db` invariati»: se `load_game` ritorna `False` (slot senza partita salvata) `load_save_slot` ripristina il `_db` precedente; prima restava puntato al nuovo slot | `game_controller.py:load_save_slot` |
| N7 | Su questa macchina `git` non ha `user.name`/`user.email`: i commit dei lotti 1.1/1.2 sono stati fatti passando l'identità con variabili d'ambiente per il solo comando (nulla scritto in `git config`) | — |

## Difetti annotati il 2026-11-19 (non corretti, convenzione 7)

- **Separatore delle migliaia incoerente.** Le viste formattano con `:,` (`1,200`), i testi del generatore (dilemmi, obiettivi) usano il punto (`€8.000`). Visto durante il passaggio `$` → `€` (Q22), non toccato.
- **Rimborso spese mai rivisto al rinnovo.** Il rinnovo automatico dei contratti (Q22) non ricalcola `weekly_wage` (resta R14).
- **Riferimenti `file:riga` di `TICK.md` ormai spostati** dopo le modifiche del 2026-11-19 (`simulation.py` è cresciuto): valgono come ordine dei passi, non come numeri di riga.
- **`verify_pose.gd` in headless** stampa `ERROR: Parameter "material" is null` (rendering fittizio) dopo «posa ai blocchi: OK»; non confrontato con una versione precedente.

## Getto del peso nel visualizzatore Godot (2026-11-20)

Lavoro solo in `godot_viewer/` (niente `models/` né `views/`). Vedi `godot_viewer/README.md` «Getto del peso».

**Difetti trovati e chiusi** (stato precedente):
- Il peso era una sfera da 0,16 m di raggio (32 cm di diametro, ~2,5× quello vero): ora 0,0605 m (uomini) e 0,052 m (donne).
- Fermapiedi a scatola centrato sul bordo (per metà dentro la pedana), linee del settore che partivano dal fermapiedi invece che dal bordo
  del cerchio, distanze segnate con linee dritte: ora fermapiedi ad arco col bordo interno sul cerchio, linee dal bordo e archi centrati sul centro.
- `field_landed_mark` era una coordinata x con z = -36 fisso (marcatore e soglia `> -40.9` cablati in `Stadium._process`): per il peso il punto di
  caduta e' un vettore del piano del tentativo (`ShotPutMotion.Plan.landing`); per il lungo resta com'era.
- Il nullo cadeva 3,6 m di lato (dentro un settore vero): ora il peso atterra alla misura nominale e il nullo si vede dal piede oltre il fermapiedi.
- Prima del rilascio non c'era nessun gesto di lancio (solo `Walk` + `Punch_Cross`).

**Limiti / da tenere d'occhio (non corretti):**
- **La posa non e' stata confrontata con un video di riferimento** (non raggiungibile da qui): e' tarata su descrizioni biomeccaniche e sui numeri
  del modello. Provati solo fotogrammi (`tests/screenshots_shot.gd`), **non** la fluidita' del movimento a schermo né con il mouse.
- ✅ (2026-11-20) Il piede sinistro ora pivota sulla punta (punta ferma a terra, tallone su) e la mano destra stringe il peso (palmo orientato verso di lui,
  dita chiuse, distese di scatto al rilascio); la scia e' un tubo e non piu' una linea da 1 px. Dettagli in `godot_viewer/README.md`. Resta il piede destro (non pivota).
- Al rilascio il peso passa da «in mano» (polso reale + scarto) a «in volo» da `R`: l'IK non arriva esattamente al bersaglio. Misurato con `screenshots_shot.gd`
  (finestra vera, gare 11 e 12): una volta 3,3-3,5 cm pochi centesimi prima del rilascio; **il 2026-11-20, su Windows con Godot 4.7.2, 17-21 cm, uguale con e senza le
  modifiche a piede e dita (confronto con `git stash`)**: non e' stato indagato (e' un salto del peso visibile al rilascio, da verificare a occhio).
- Il tempo del tentativo animato e' fisso (≈ 10 s a 1x): 6 prove ≈ 1 minuto di sola atleta del club. A 8x resta accettabile.
- Nei concorsi non ci sono giudici né fotografi (`TrackSideCrew` e' disattivato: la camera del lungo sta dove stanno loro).
- `is_foul` non porta una motivazione e il valore esportato di un nullo e' 0,96 × risultato (segnaposto del motore Python): la resa del nullo
  e' una sola, deterministica (piede oltre il fermapiedi).
- Il settore e' disegnato per 30 m (non 100) e non c'e' gabbia: scelte dell'utente, vedi sopra.
- `TwoBoneIK3D` (gia' usato da `SetPoseRig`) richiede in pratica Godot ≥ 4.6, non 4.3 come scritto nel README (non verificato su versioni piu' vecchie).
- `godot_viewer/.godot/global_script_class_cache.cfg` e `uid_cache.bin` sono **tracciati da git** e cambiano a ogni `--import`: sono stati inclusi nel commit
  perche' le nuove `class_name` (`ShotPutMotion`, `ShotPutRig`, `ShotPutView`) devono essere registrate, ma tenerli in git e' fonte di conflitti.
- `verify_race.gd` impiega ~5 minuti (gare in tempo reale a 4x/8x): per il solo peso usare `verify_shotput.gd`.
- **`verify_camera.gd` sul peso (gare 11 e 12).** Ha trovato due difetti di regia, corretti: dopo il rilascio la camera della rotazione restava
  sull'atleta 0,25 s mentre il peso (13 m/s) usciva dall'inquadratura (ora 0,08 s, `SPIN_AFTER_REL`) e la panoramica sul settore non conteneva i lanci
  oltre ~20 m (allargata). Il test e' stato adattato in un solo punto: nella fase `EXIT` il bersaglio previsto e' l'atleta che esce, non il peso
  gia' atterrato (`_world_of`). Le camere `_sp_*` risultano di tipo «start» (inquadratura contenente il bersaglio), non «pan».

### Richieste successive sul peso e sulle scarpe (2026-11-20)

- **Scarpe per tutti gli atleti** (tutte le gare): prima i piedi erano la mesh del corpo gonfiata e tagliata per altezza (`add_cloth`, «scarpette»),
  cioe' pelle con uno strato bianco. Ora `CharacterDress.add_shoes` costruisce una mesh per piede dal profilo del piede del modello, appesa all'osso
  (`BoneAttachment3D`). La suola sta nel volume del piede. **Non** si flette alla punta (l'osso `ball_*` non e' usato) e non ci sono chiodi. Le
  scarpe di giudici e fotografi (`TrackSideCrew`) restano le vecchie scarpe gonfie.
- **«Piedi che sprofondano nella pedana»**: due cause. (1) L'IK posiziona solo la caviglia e il piede seguiva l'inclinazione dello stinco (punta
  in giu'). (2) `ANKLE_H` era 4,75% di H per entrambi i sessi, ma la caviglia sta a 5,28% (M) e 4,46% (F) sopra la suola. Corretto con `FootLevel`
  (piede orizzontale dopo l'IK) e quota per sesso. Gli altri eventi non usano questo rig: ai blocchi (`SetPoseRig`) e in corsa il piede segue ancora
  il suo osso; non e' stato rivisto.
- **Tutti i lanci animati**: ≈ 10 s ciascuno, 6 concorrenti ≈ 6 minuti a 1x (a 2x/4x/8x molto meno). Non c'e' un tasto «prossimo lancio»: c'e' solo
  «Salta alla fine» (che salta tutta la gara). Da valutare se serve.
- **Arco del miglior lancio**: un arco per il solo migliore (non uno per concorrente). Il nome sta nel testo sul terreno; i nulli non lasciano segno
  (il loro valore esportato e' nominale).
- **Piedi sotto terra in ingresso e in uscita dalla pedana** (segnalato dall'utente): non era la pedana ma le animazioni `Walk` e `Idle`, che abbassano
  il corpo rispetto al riposo: misurato nella scena vera (`screenshots_shot.gd --soles`) la suola scende fino a 5,7 cm (M) e 4,9 cm (F) sotto il
  livello del nodo, con la terra battuta a quota 0. Compenso in `ShotPutMotion` (`WALK_SINK*`, `IDLE_SINK*` in frazioni di H, per sesso, piu' la
  quota del terreno: pedana 1,2 cm dentro il cerchio, terra fuori). **Lo stesso abbassamento puo' valere per `Walk`/`Idle` negli altri eventi** (a fine
  gara, dopo il traguardo): non verificato né corretto, fuori dal peso. La misura dell'attesa maschile (`IDLE`) e' sporcata dal passaggio fra le due
  animazioni (0,25 s): si e' usato il valore massimo trovato.
- **Crateri tolti** (richiesta dell'utente): il peso non lascia più nessuna buca, né per il lancio in corso né per quelli già fatti. Restano il
  terriccio sollevato all'impatto, il nastro, la bandierina e l'arco dorato del migliore. Conseguenza: sul terreno non resta un segno per ogni
  lancio (prima i valid lasciavano un cratere): se serve vedere dove sono caduti tutti, e' una scelta di design da prendere (es. puntini o
  bandierine piccole).
