# GAME — descrizione completa di Track & Field Manager

Documento pensato per essere dato a un altro assistente (LLM) o a una persona che non conosce il progetto: descrive
**che cosa è il gioco, come funziona ogni componente e come è fatto il codice**. È una sintesi: i dettagli puntuali (cifre,
righe di codice, ordine esatto del tick) stanno in `docs/BALANCE.md`, `docs/TICK.md`, `docs/AUDIT.md`, `docs/QUESTIONS.md`,
`docs/PLAN.md` e in `CLAUDE.md`. Dove questo file e il codice divergono, **vince il codice**.

**Aggiornamento 2026-11-20 (sera): avvio della Carriera senza atleti con Preparazione, schema 21, §5.0, 572 test OK.** Stato descritto: 2026-11-20, branch `feature/gameplay-improvements` (da `main` `099064d`, lotto A.1-A.5, B.1, B.2 e B.3 di `PIANOLAVORO.md` fatti; **cifre di B.2 provvisorie**, quelle di B.3 misurate e confermate) (lotti 1.1 e 1.2 di `PLAN.md` fatti; decisioni Q15-Q18 e Q20-Q22 e 800m, compreso Godot, implementate). Aggiornamento 2026-11-20: fatti anche C.1-C.3 (ranking, Board, ritiro) e **tutto il lotto D** (agenti, trattative, finanze; §5.15-5.19), cifre provvisorie (Q26-Q31); schema 20. Suite di test: **532 test OK** (eseguita il 2026-11-20; i modelli nuovi girano senza PyQt6).

**Che cosa è verificato e che cosa no.** Le regole e le cifre qui sotto vengono dalla lettura del codice e dagli esperimenti
registrati in `AUDIT.md`. Non è mai stato provato il gioco con mouse e tastiera reali (solo test offscreen e screenshot), non è stata
eseguita la build PyInstaller e Godot non è nel PATH dell'ambiente di sviluppo. Le cifre di bilanciamento sono quelle del
codice, non necessariamente quelle «giuste» per il design: molte sono provvisorie (vedi §13).

---

## 1. Che cos'è

Gestionale di **atletica leggera** per desktop (single player, offline): il giocatore dirige una società sportiva del Lazio.
Allena gli atleti, sceglie chi schierare in ogni gara, gestisce soldi, staff, impianti e vivaio, e prova a far salire la società di
categoria nell'arco delle stagioni. Le gare sono simulate dal modello e poi **mostrate** in diretta (2D, 3D software in PyQt, oppure
un visualizzatore Godot opzionale in stile «diretta TV»).

- **Stack:** Python 3.14 + PyQt6 + SQLite, architettura MVC. Interfaccia, testi, commenti e documenti in **italiano**;
  identificatori nel codice in **inglese**.
- **Moneta e tempo:** il tempo avanza a **settimane** (un clic su «Avanza settimana»). Una gara si corre ogni 4 settimane.
  La moneta è l'euro (`€`); le cifre sono ancora formattate con la virgola come separatore delle migliaia (`1,200`) nelle viste e con il punto nei testi del generatore (`8.000`): incoerenza nota, non corretta qui.
- **Genere:** ogni gara ha due **divisioni**, maschile (M) e femminile (F), con convocazioni, record e staffette separati.
- **Società e dati reali:** i nomi dei club rivali vengono da `data/societa_atletica_lazio.csv` (239 società per provincia:
  Roma, Latina, Frosinone, Rieti, Viterbo). Atleti, rivali e sponsor sono generati proceduralmente; gli sponsor delle grafiche sono di fantasia.

### Modalità di gioco

| Modalità | Contenuto |
| --- | --- |
| **Prototipo Outdoor** (`vertical_slice`) | 10 atleti, 3 discipline (100m, Salto in Lungo, 1500m), 2 gare ufficiali (sett. 4 e 8), nessuna promozione. Serve a provare il ciclo allenamento/recupero/vento/scouting/staff/dilemmi. Nulla ferma il gioco dopo la sett. 8 (difetto noto). Fondo iniziale 10.000. |
| **Carriera Completa** (`career`) | **Società da fondare: parte con 0 atleti** (Prima Squadra e vivaio vuoti; budget 18.000 invariato, staff e 4 allenatori iniziali come sempre) e una **Preparazione** di 8 settimane senza gare (Q32; i salvataggi vecchi hanno il calendario di prima), 6 discipline (100m, 400m, **800m**, 1500m, Salto in Lungo, Getto del Peso) più staffette 4x100m e 4x400m, stagioni cicliche **[Preparazione →] Outdoor → Cross → Indoor** (Preparazione 8 sett., poi 12 settimane per fase: 44 sett. a stagione nelle Carriere nuove, 36 nei salvataggi vecchi), promozioni/retrocessioni tra 4 categorie. Fondo iniziale 18.000. |

Categorie (`CompetitionTier`): **Provinciale → Regionale → Nazionale → Internazionale**. Nell'interfaccia hanno i nomi dei Campionati di Società (`TIER_DISPLAY_NAMES`, Q18): **Fase regionale CdS → Finale Bronzo → Finale Argento → Finale Oro / Coppa Europa**; il `value` dell'enum, salvato nel DB, non cambia. Ognuna ha livello medio dei rivali,
sponsor settimanale, montepremi, costo di trasferta e prezzo dei biglietti crescenti (§6, §9).

---

## 2. Architettura e struttura del repository

```text
main.py          entry point: GameController(auto_create=False) + MainWindow
models/          LOGICA DI GIOCO, nessun import di PyQt6 (regola vincolante, oggi violata solo da race_export.py)
  entities.py      GameState, Athlete, Coach, Relay, RivalClub, EventDefinition, enum, molte costanti
  generator.py     generazione atleti, rivali, allenatori, staff, dilemmi, scouting
  ranking.py board.py career.py   ranking (C.1), obiettivi del Board (C.2), ritiro (C.3)   agents.py market.py finances.py   agenti (D.1), trattativa (D.2), finanze (D.3)
  simulation.py    allenamento, motore gara, staffette, finanze, tick `advance_week`
  database.py      SQLite: schema, migrazioni, backup, salvataggio/caricamento, elenco slot
  race_export.py   esporta una gara in un DB per Godot      bibs.py   numeri di pettorale
controllers/
  game_controller.py   GameController (QObject con segnali Qt): tutte le azioni del giocatore, il tick, il caricamento
views/           interfaccia PyQt6 (nessuna logica che decida esiti)
  start_screen.py main_window.py tabs.py dialogs.py athlete_dialog.py styles.py (tema scuro QSS) results_board.py finance_chart.py (grafico a barre dei mesi)
  race_viewer.py race_3d.py field_3d.py (gare in diretta)     godot_launcher.py (lancio di Godot)
godot_viewer/    progetto Godot 4.3+ separato (solo vista), legge risultati da SQLite
tests/           test_game.py (96 test, usa PyQt6)   test_migrations.py (48), test_assignments.py (9), test_contracts.py (12), test_event_800m.py (9), test_ranking/board/retirement/agents/negotiations/finances.py (lotti C e D): senza Qt; i `*_ui.py` usano PyQt6 offscreen (elenco completo in CLAUDE.md)
data/            societa_atletica_lazio.csv          docs/   AUDIT, TICK, BALANCE, QUESTIONS, PLAN, GAME
```

**Flusso:** le viste chiamano metodi del `GameController`; il controller modifica il `GameState` (usando funzioni di `models/`),
salva su SQLite ed emette segnali (`state_changed`, `week_advanced`, `competition_completed`, `season_ended`, `dilemma_triggered`,
`status_message`); le viste si ridisegnano leggendo `controller.state`. Le viste non scrivono mai nello stato.

**Principi non negoziabili (dal `CLAUDE.md`):**

1. L'**esito delle gare lo decide solo il modello** (`simulation.py`). Le viste mettono in scena un risultato già calcolato:
   non cambiano tempi, ordine o misure. Ogni atleta taglia il traguardo esattamente al suo `mark_value`.
2. **Niente «button mashing»** né comandi interattivi in gara: cambierebbero un risultato già simulato (sarebbe una scelta di design da discutere).
3. **Grafica originale**: niente nomi, sprite, layout o sponsor presi da giochi esistenti.
4. `models/` non importa PyQt6. Le costanti di gioco vanno nei blocchi di costanti di `entities.py` (non letterali nelle funzioni).
5. Ogni migrazione del salvataggio ha backup + transazione + test; mai `DROP` di dati su una versione sconosciuta.
6. L'ordine del tick settimanale è quello di `docs/TICK.md` (anche l'ordine delle chiamate all'RNG ne fa parte).
7. Niente modifiche non richieste: un difetto trovato per strada si annota in `AUDIT.md`, non si corregge di nascosto; le decisioni di design restano all'utente (`QUESTIONS.md`).

---

## 3. Modello dati

### 3.1 `GameState` (lo stato di una partita, un solo oggetto)

Contiene: nome società, modalità, `budget`, `week`, `season_number`, `season_phase`, `start_date`, `prestige`, `reputation`,
`tier`, `track_condition` (0-100, default 82), `member_fees_weekly` (450); la **rosa** (`athletes`), il **vivaio** (`youth_squad`),
gli **allenatori** (`coaches`) e lo **staff** (`staff`); le **convocazioni** per evento (`event_lineup` M, `event_lineup_f` F, un solo
atleta per evento e divisione; ogni atleta al massimo in 2 gare individuali + 1 staffetta, e gli under 20 non gareggiano in «Finale Oro / Coppa Europa»), gli atteggiamenti di gara per evento (`event_attitude`), le **staffette** (`relays` M, `relays_f` F),
i **record sociali** (`club_records`, `club_records_f`), gli **obiettivi stagionali**, i traguardi (`milestones`), il registro notizie
(`news_log`, max 70; dal lotto F.1 anche notizie dinamiche, vedi §5.20), le **transazioni** (libro mastro, max 400), la **storia delle gare** (`competition_history`, cresce senza limite),
i **rivali** (`rivals`), la classifica di lega (`league_table`), la storia delle stagioni (`season_history`), il dilemma pendente
(`pending_dilemma`), impianti (`gym_level` 0-5, `stand_seats`, `facilities`, `academy_level` 0-5, `scout`), `fidelity` (fedeltà sponsor), `scouting_points_used`,
`coach_hired_week`, `bankrupt`, `board_failed_streak` e `fired` (Board, C.2); il campo mondiale di atleti sintetici del ranking (`ranking_pool`, C.1); gli ex atleti (`retired`, C.3), gli **agenti** (`agents`, D.1) e i **bilanci mensili** (`monthly_reports`, D.3).

### 3.2 `Athlete`

Identità: `id`, `name`, `age`, `gender` (M/F), `nationality` (70% Italia), `height_cm`, `weight_kg`.
Caratteristiche (0-100): `speed`, `stamina`, `strength`, `technique`, `resilience`; stato: `form`, `fatigue`, `sleep_quality`, `nutrition`;
`potential` (tetto di crescita); `specialty` (**Velocità, Mezzofondo, Salti, Lanci**); `personality` (**Perfezionista, Impulsivo, Leader,
Resiliente**); `training_focus` (**Resistenza, Potenza Esplosiva, Tecnica, Riposo & Recupero**); `periodization`
(**Prep. Generale, Prep. Specifica, Gara (Picco), Scarico (Tapering)**); `weekly_wage`, `injured_weeks`, `is_youth_prospect`,
`in_youth_squad`, `fans`, `coach_id`, `personal_best` (per evento), `doping_boost_weeks`, `contract_end_season` (ultima stagione di contratto, inclusa; 0 = nessuno, cioè vivaio)
e `contract_no_renew` (il giocatore non vuole rinnovarlo: §5.9), `ranking_points` (punti ranking per evento, §5.15), `season_injuries` (infortuni della stagione, §5.16), `agent_id` (agente, §5.17) e `record_bonus` (bonus per record pattuito, §5.18). La **fascia d'età** (`age_category`: Cadetti 14-15, Allievi 16-17, Juniores 18-19, Promesse 20-22, Seniores 23+) è solo un'etichetta
calcolata da `age`, non salvata, mostrata nella scheda atleta.
`overall` è una media pesata delle caratteristiche con pesi diversi per specialità. L'altezza e il peso concorrono al punteggio in gara
(§5.3). Il picco di età dipende dalla specialità (`peak_age_range`: Velocità 20-27, Salti 20-28, Mezzofondo 21-30, Lanci 23-32).

### 3.3 Altre entità

- `EventDefinition`: evento (nome, tipo corsa/concorso, sensibile al vento, record del mondo, ancore dei livelli). Eventi: `100m`, `400m`,
  `800m`, `1500m`, `Salto in Lungo`, `Getto del Peso`; `RelayDefinition`: `4x100m`, `4x400m`.
- `Coach`: 4 abilità 1-100 (Velocità, Resistenza, Forza, Tecnica), tier, tipo (specializzato su una disciplina o del vivaio).
- `RetiredAthlete`: ricordo di un ex atleta del club (nome, disciplina, età e stagione del ritiro, motivo, PB, offerta da allenatore con le sue abilità); l'`Athlete` esce da `GameState.athletes` (§5.16).
- `Relay`: 4 frazionisti in ordine + riserva, `harmony` (affiatamento 0-100), `last_change_week`.
- `RivalClub`/`RivalAthlete`: società avversarie persistenti (livello, ambizione, storia del livello, un atleta per gara, `ranking_points`).
- `SyntheticAthlete`: atleta di fantasia del ranking mondiale (nome, nazionalità, evento, sesso, livello, punti); non gareggia con il club (§5.15).
- `StaffMember`: Fisioterapista, Medico Sportivo, Preparatore Mentale (attivabili/disattivabili), con **due attributi 1-20** per ruolo (`attributes`, E.1).
- `CompetitionSummary` / `EventResult` / `EventStanding`: risultato di un meeting (per evento: classifica, misure, punti, vento, meteo).
- `EthicalDilemma`, `SeasonObjective` (con `target` e `value`: soglia e avanzamento degli obiettivi del Board), `SeasonEndResult` (anche il verdetto del Board), `Transaction`.

---

## 4. Il ciclo di gioco: la settimana

Il giocatore, durante la settimana, **prepara**: imposta allenamento e periodizzazione di ogni atleta, convoca gli atleti per gara,
sceglie l'atteggiamento, compone le staffette, spende soldi (staff, impianti, scouting, mercato). Poi preme «Avanza settimana»
(`GameController.advance_week` → `models.simulation.advance_week`). Il tick, in ordine (dettagli e numeri di riga in `TICK.md`):

1. Se la settimana è **di gara** (`settimana % 4 == 0`): simula il meeting (meteo, vento, punteggi di tutti, classifica, premi, record, staffette, punti squadra, biglietti/trasferta).
2. Per ogni atleta: allenamento settimanale (doping/infortunio/recupero/crescita/fatica/forma/declino/rischio infortunio). Nel tick che precede una gara la fase «Gara (Picco)» aggiunge `PEAK_FORM_BONUS` (+6) al bersaglio di forma.
3. Note di infortunio; eventuale scandalo doping (reputazione −25, prestigio −45).
4. Finanze settimanali: entrate (sponsor, individuali, merchandising, quote) e uscite (rimborsi spese atleti, staff, allenatori, palestra); libro mastro.
5. Se `budget < 0`: interessi 5% a settimana; sotto −20.000 la società **fallisce** (`bankrupt`: blocca i tick successivi).
6. Decadimento abilità degli allenatori; affiatamento staffette; **evoluzione dei rivali**; usura della pista.
7. Fedeltà sponsor +2; azzera i punti scouting; **`week += 1`**.
8. Solo Carriera, a ogni inizio di fase: cambio **fase** ([Preparazione →] Outdoor → Cross → Indoor). A fine ciclo (44 sett. con la Preparazione, 36 senza): verdetto di lega, nuova stagione,
   azzeramento classifica di lega, +1 anno a tutti gli atleti, **ritiro dei veterani** (§5.16), rinnovo dei rivali, poi **contratti scaduti**: rinnovo automatico (1-3 stagioni, senza costo e senza RNG) o, per chi ha «Non rinnovare», uscita dalla società (§5.9).
9. Promozione automatica dal vivaio a 18 anni; **convocazioni non più ammesse sostituite** (tetto di 2 gare individuali + 1 staffetta, under 20 fuori da «Finale Oro / Coppa Europa», `normalize_assignments`); notizie; valutazione obiettivi; possibile **dilemma etico**; troncamento dei registri.

Dopo il tick il controller azzera in memoria i risultati dello scouting e il pool del mercato, **salva** su SQLite ed emette i segnali:
se c'è una gara si aprono la gara in diretta e i risultati; a fine stagione la finestra di fine stagione; se è scattato un dilemma, la sua finestra.

> Stato dei lotti sul tick: il lotto 1.3 («il tick non lascia stato a metà», snapshot e ripristino su eccezione) è **proposto ma non
> implementato**. Oggi un'eccezione nel tick lascia lo stato in memoria a metà e, essendo lanciata da uno slot Qt, chiude l'app (exit 134).

---

## 5. Regole di gioco per componente

### 5.1 Calendario, stagioni, casa/trasferta

- Gara ogni 4 settimane. **Casa/trasferta alternate**: in casa non paghi la trasferta e incassi i biglietti (spettatori limitati dalla capienza,
  funzione di prestigio, categoria, reputazione, pioggia); in trasferta paghi il costo di trasferta. La pista subisce −3% di condizione in un meeting in casa.
- Fasi in Carriera: Outdoor (sett. 1-12), Cross (13-24), Indoor (25-36). **Le discipline non cambiano con la fase** (in Carriera sono sempre le 6: 100m, 400m, 800m, 1500m, Lungo, Peso): le differenze reali sono
  che in Cross non si corrono staffette, in Indoor non c'è la 4x100m, il meteo indoor è sempre Sereno e il vento 0. Non esiste una gara di corsa campestre
  né un 60m indoor (si corre il 100m).
- Meteo (Sereno, Ventoso, Pioggia, Caldo): Pioggia −1,8 e Caldo −0,8 punti di punteggio; il vento dipende dal meteo.

### 5.2 Allenamento, fatica, forma, infortuni

- Ogni atleta ha un **focus** (Resistenza, Potenza Esplosiva, Tecnica, Riposo) e una **fase di periodizzazione**. Ogni settimana, in base al focus, c'è una probabilità di
  +1 (talvolta +2) alla caratteristica allenata, moltiplicata per: età (sotto il picco ×1,30, nel picco ×1,00, oltre ×0,65), allenatore adatto
  (senza allenatore ×0,6), personalità (Perfezionista ×1,15), periodizzazione (la fase «Gara (Picco)» ha ×0,90 di crescita e +2 fatica, ma +6 al bersaglio di forma nel tick pre-gara; lo Scarico dà +9), palestra (+6% per livello), vivaio (×1,5) e margine rispetto al `potential`.
  Tetto della probabilità 0,95.
- **Fatica** sale con l'allenamento (a seconda del focus) e scende con Riposo, Scarico, fisioterapista, sonno e nutrizione. La **forma** converge a un bersaglio
  che dipende dalla fatica (fatica alta → forma bassa), con bonus per Riposo/Scarico, preparatore mentale, Leader, doping.
- **Infortunio da carico** possibile con fatica ≥68 (più alto per fatica elevata e bassa resilienza; ridotto da Resiliente, medico, Fisioterapista; più alto per ≤17 anni).
  Durata 1-3 settimane; da infortunato non si gareggia e si prende comunque il rimborso spese.
- **Declino con l'età**: dopo il picco della specialità si perdono gradualmente velocità, resistenza e forza.
- Azioni manuali: **seduta di recupero** per atleta (fatica −20, sonno/nutrizione +10, forma +6, costo 250); **manutenzione pista** (costo 900, +25 condizione).
- **Doping** esiste solo come scelta di un dilemma etico: +6,5 punti in gara e +10 forma, ma 24%/settimana di controllo positivo (4 settimane di stop) e scandalo.

### 5.3 Gara: punteggio, misura, vento, atteggiamento

1. Per ogni atleta convocato si calcola un **punteggio atteso**: base dell'evento (+4 se la specialità coincide, −3,5 altrimenti) + effetto forma/fatica + condizione pista +
   **modificatore fisico** (ogni gara ha un fisico ideale in altezza/peso; lo scarto sposta il punteggio tra +1,2 e −4) + atteggiamento + bonus casa (+1) + meteo + doping,
   più una **variabilità giornaliera** gaussiana (σ ≈ 3,8; Perfezionista 3,0; Impulsivo senza mentale 5,6).
2. Il punteggio diventa una **misura** (tempo o distanza) con una retta per evento e sesso, tarata su ancore: punteggio 42 ≈ livello provinciale, 56 regionale,
   66 vincitore regionale, 70 nazionale, 84 internazionale. 100m, 400m, 1500m, lungo e peso sono tarati su dati FIDAL/Assoluti 2025 (provinciale e media regionale di lungo e peso sono stime); **800m**: stessa retta per livello del 1500m ma con ancore **stimate** (M 2:05 / 1:58,5 / 1:45,5; F 2:21 / 2:14,7 / 2:02 a score 42 / 56 / 84), tetto WR 1:40,91 e 1:53,28;
   le staffette no. Il tetto è il record del mondo, applicato dopo il vento.
3. **Vento**: solo 100m (−0,055 s per m/s) e Salto in Lungo (+0,08 m per m/s). Oltre **+2,0 m/s** la prestazione non è omologata: non aggiorna PB, record sociale né momenti storici,
   ma piazzamento, punti squadra, premi, prestigio e fan restano.
3b. **Piano gara 800m/1500m** (B.1, 2026-11-20, cifre confermate dall'utente): prima della gara si sceglie un *ritmo iniziale* (Lento −2 / Medio 0 / Veloce +3 punti; fatica −4 / 0 / +10) e uno *scatto finale* (Nessuno / Ultimi 200m +2, fatica +8 / Ultimo giro +4, fatica +15). Si somma all'atteggiamento. Il punteggio di ogni scelta si moltiplica per un **fattore di resistenza** (0,5 per un atleta nella media della categoria, 1 se molto resistente, fino a −0,5 senza fondo: chi non ha fiato crolla col ritmo Veloce e guadagna col Lento); la fatica non dipende dalla resistenza. Nessuna estrazione in più all'RNG. Si sceglie nella scheda Calendario (colonna «Piano gara / Rischio»), vale per evento (M e F insieme, come l'atteggiamento), compare nei risultati. Rivali e viste di gara non lo usano.
3c. **Rischio nei concorsi** (B.2, 2026-11-20, **cifre provvisorie**, Q24): per Salto in Lungo e Getto del Peso si sceglie prima della gara *Sicuro* (0), *Bilanciato* (+1 tecnica, 5% di tentativo nullo) o *Aggressivo* (+3 tecnica, 15% di nullo). I punti di tecnica valgono il peso della tecnica nell'evento (0,35 per punto). Il modello non simula i singoli tentativi (la vista li ricava dal risultato), quindi un nullo fa perdere il tentativo migliore: la misura scende del 3% (`FIELD_FOUL_LOSS`, cifra mia, ripiego sul secondo tentativo). Una sola estrazione RNG, e solo se il rischio non è «Sicuro» (con «Sicuro» la sequenza è identica a prima). Non c'è «altezza/peso iniziale» del piano: nel lungo e nel peso non esiste. Si sceglie nella scheda Calendario (stessa colonna del piano gara), vale per evento (M e F insieme), compare nei risultati («Rischio Aggressivo, tentativo nullo»). I tentativi mostrati dalle viste di gara restano quelli inventati a posteriori: non sanno del nullo del modello.
3d. **Cambio nelle staffette** (B.3, 2026-11-20, cifre misurate e confermate dall'utente, Q25): per 4x100m e 4x400m si sceglie prima della gara *Conservativo* (−1 punto di squadra, −10 punti percentuali di rischio di squalifica), *Normale* (0) o *Aggressivo* (+2 punti, +10 punti percentuali). I punti percentuali si sommano alla probabilità finale (dopo il ×0,5 della 4x400m, Q20) e il risultato resta tra 0 e 100%: con affiatamento alto «Aggressivo» ha comunque un costo, e «Conservativo» non porta il rischio sotto zero. Nessuna estrazione RNG in più (cambia solo la soglia dell'estrazione che c'è già). Si sceglie nella scheda Staffette (menu «Cambio»), vale per staffetta (M e F insieme, come l'atteggiamento), compare nei risultati («Affiatamento B · Cambio Aggressivo»). Nelle misure è una mossa per la squadra che insegue: conviene a una squadra media nella 4x400m e non a chi è già favorito nella 4x100m (tabelle in Q25).
4. **Atteggiamento** per ogni gara: Prudente (−2 punti, poca fatica, rischio infortunio 0,5%), Normale, Aggressivo (+2,5 punti, tanta fatica, rischio 5%, variabilità extra).
   Il rischio di ritiro in gara aumenta con la fatica ed è ridotto da medico (×0,55) e Resiliente (×0,7). Un ritirato (DNF) arriva ultimo, forma −15, 1-3 settimane di stop.
5. Ogni società schiera **un solo atleta per evento e divisione**, e ogni atleta al massimo **2 gare individuali + 1 staffetta** per meeting (tetto FIDAL, Q15); gli under 20 non gareggiano nel livello «Finale Oro / Coppa Europa» (Q17). Gli avversari sono i rivali (un atleta per società per gara, 7 società per categoria, quindi 8 partecipanti).
6. Premi in denaro per i primi 4 (1,00 / 0,60 / 0,35 / 0,15 del montepremi della categoria), prestigio per piazzamento (+5 se record), fan (più i piazzamenti alti, +5 per PB, +10 per record).

### 5.4 Classifiche: meeting, lega, promozioni

- **Punti squadra** per posizione: 1° = 8 … 8° = 1. Sommati per meeting danno la classifica del meeting (le prime 3 società prendono prestigio extra: 10/6/3) e una **classifica di lega
  cumulativa**, azzerata a ogni stagione. Una gara senza convocato regala punti ai rivali.
- **Verdetto a fine stagione** (Carriera, dopo 44 settimane con la Preparazione, 36 senza): le prime **2** salgono di categoria, l'**ultima** scende; in Internazionale il 1° posto è il **titolo**. A pari punti (A.2, 2026-11-20):
  più **1° posti** nelle gare della stagione, poi più 2°, … (si contano i piazzamenti che danno punti, salvati per club in `league_places`, azzerati a fine stagione); se è ancora parità, un
  **sorteggio deterministico** (`hashlib` su stagione + posizione del club nell'elenco, non il nome: chiamare il club «Aaa» non serve). Stessa regola per la classifica del meeting
  (là contano i piazzamenti di quel meeting). Un salvataggio di metà stagione senza contatori (v11) ripiega sul sorteggio fino al meeting successivo. Il prestigio resta e fa crescere il pubblico dei meeting in casa.
- Il Prototipo non ha promozioni né retrocessioni.

### 5.5 Staffette (4x100m, 4x400m)

4 frazionisti in ordine + 1 riserva, per divisione; ogni atleta può stare in una sola staffetta; la 4x400m si corre solo in Carriera (serve la gara dei 400m). Il tempo dipende dai
frazionisti (l'ultima frazione pesa 0,28 contro 0,24) e dall'**affiatamento** (E … A++, scala interna 0-100, parte da 30). L'affiatamento cresce ogni settimana con titolari sani e di più se si gareggia;
cala se mancano. Con affiatamento basso c'è rischio di **squalifica** per cambio fuori zona (la probabilità nella 4x400m è la metà di quella della 4x100m: `RELAY_DQ_MULT`, Q20). Riordinare è gratis; sostituire un titolare sano costa il 25% dell'affiatamento
(una volta ogni 4 settimane); un infortunato è sostituito dalla riserva (che subentra con affiatamento −15 e +3% di rischio DQ). Le staffette contano per i punti squadra e hanno record propri;
non consumano forma, non danno fan. Prima della gara si sceglie il **cambio** (Conservativo / Normale / Aggressivo, B.3: punti di squadra e rischio di squalifica, vedi 3d) nel menu della scheda Staffette.

### 5.6 Rivali

7 società per categoria e divisione, ciascuna con un atleta per gara (nome, età, livello, PB). Ogni settimana evolvono (under 24 crescono, 24-27 poco, 28-29 deriva nulla con rumore, dal 30 calano).
A inizio stagione invecchiano, i veterani si ritirano (a 33 sempre, da 31 il 30%), arrivano reclute di 18-22 anni, ogni anno un po' più forti. Hanno un'**ambizione**: le società che batti diventano più
ambiziose e crescono più in fretta; quelle che ti staccano molto si rilassano. La scheda *Rivali* mostra livello, tendenza e confronto gara per gara.

### 5.7 Economia

Entrate settimanali: **sponsor società** (funzione di categoria, reputazione e fedeltà; −20% dopo una stagione fuori dai primi 5, §5.19), **sponsor individuali** (fan/4 per atleta maggiorenne in prima squadra), **merchandising** (fan e prestigio, §5.19), **quote tesserati** (450 fisse).
Uscite settimanali: **rimborsi spese atleti** (prima squadra, infortunati inclusi, mai rivisti), **staff** (secondo lo specialista scelto: Fisioterapista 180-460, Medico 200-520, Preparatore Mentale 140-340; gli originali 300, 340, 220), **stipendi allenatori**
(`40 + 2,2 × Σ max(0, abilità−40)`), **gestione palestra** (40 × livello). Per gara: premi e biglietti (casa) o trasferta (fuori). Una tantum: ingaggi (atleti, allenatori), scouting, recupero, pista, ampliamenti.
**Debito**: con saldo negativo interessi del 5% a settimana; sotto −20.000 fallimento. **Bilanciamento dell'avvio** (A.1, 2026-11-20): sponsor società e montepremi sono saliti del 40% e del 25%, i rimborsi spese degli atleti sono scesi del 45% (`WAGE_*` in `entities.py`) e la promozione di categoria dà un bonus una tantum di 5.000 € (`PROMOTION_BONUS`). In autopilota (nessuna spesa) la Carriera chiude le prime 12 settimane tra +4.700 e +15.300 € e le prime 36 tra +300 e +23.800 € (8 seed); i rimborsi vecchi restano nei salvataggi esistenti. Cifre complete: `BALANCE.md`.

### 5.8 Vivaio e scouting

Il **vivaio** ospita fino a 8 ragazzi di 14-17 anni che non gareggiano e non costano rimborsi spese, ma si allenano ×1,5. A 18 anni passano da soli in prima squadra (in Carriera, perché l'età cresce solo al cambio stagione);
prima si possono promuovere a mano. Ogni settimana si hanno **8 punti scouting**: una ricerca costa 2 punti (+1 per filtro: disciplina, potenziale ≥85) e un costo in denaro crescente con i punti già spesi.
I ragazzi segnalati e non presi se ne vanno a fine settimana.
Dal lotto **E.3** (2026-11-21, effetti del piano, costi provvisori, Q35) le giovanili hanno tre leve nella tab «Vivaio & Osservatori»: **Academy a stelle** (0-5, stella N costa N × €4.000, una tantum: ogni stella +10% di probabilità di crescita per i ragazzi del vivaio, 5 stelle = +50% oltre al ×1,5 di base); un **osservatore capo** con due attributi 1-20 (*Giudizio potenziale* e *Giudizio attuale*; tre candidati, compenso settimanale €120-440, liquidazione di 6 settimane come lo staff) che stringe le **fasce d'incertezza** con cui si vedono i ragazzi segnalati (potenziale da ±8 a ±2, qualità attuale da ±5 fino al valore esatto con 20; senza osservatore le fasce sono larghe); e la **rete scouting globale**: una regione (Giamaica velocisti, Kenya mezzofondisti, Nigeria lanciatori) è un filtro in più (+1 punto, €800) in cui ogni ragazzo ha il 20% di essere un talento con la qualità tipica oltre 80 (`models/scouting.py`, `BALANCE.md` §T).

### 5.9 Mercato (agenti liberi) e contratti

**Contratti** (Q22): ogni atleta di Prima Squadra ha una scadenza stagionale (`contract_end_season`), assegnata alla firma (acquisto, promozione dal vivaio, nuova partita, vecchi salvataggi al caricamento) con una
durata di 1-3 stagioni deterministica (da id atleta e stagione, nessun RNG). Il vivaio non ha contratto. A fine stagione i contratti scaduti si **rinnovano da soli**, senza costo; il rimborso spese non viene rivisto (R14).
Dalla scheda atleta il pulsante **«Non rinnovare»** (annullabile con «Annulla non rinnovo») fa sì che, alla scadenza, l'atleta lasci la società **senza** la penale di fedeltà dello svincolo; l'ultimo atleta della
Prima Squadra si rinnova comunque. Chi se ne va viene tolto da formazione e staffette, che si ricompongono da sole, con una notizia nel registro.

Pool di 5 candidati a settimana (4 studenti di 15-17 anni + 1 adulto): si può solo **acquistare** (ingaggio una tantum, **trattato con l'agente**, §5.17-5.18) o **svincolare** (con **clausola rescissoria**, §5.18). Nessun incasso dalle cessioni. Ogni acquisto/cessione abbassa la **fedeltà sponsor**
(−6 per under 21, −12 altrimenti; −8 per la cessione), che riduce lo sponsor della società e si recupera di +2 a settimana.

### 5.10 Allenatori e staff

Ogni **allenatore** ha 4 abilità (1-100). L'atleta che allena una qualità cresce tanto più quanto l'allenatore è bravo in quella; senza allenatore adatto ×0,6. Massimo 6 specializzati (una disciplina) e 2 del vivaio (solo ragazzi 14-17).
Si assume scegliendo abilità principale, secondaria e livello di ingaggio (1500 × livello, 1-5, una tantum, più abilità = stipendio più alto), uno a settimana. Oltre 6 atleti a testa l'effetto cala; le abilità decadono lentamente (10%/sett. di −1 a un'abilità sopra 25).
Lo **staff** (Fisioterapista, Medico Sportivo, Preparatore Mentale) si attiva/disattiva e dà effetti su fatica, guarigione, rischio infortunio e forma.
Dal lotto **E.1** (2026-11-20, cifre provvisorie, Q33) ogni specialista ha due **attributi 1-20** che scalano quegli effetti (`models/staff.py`, tabella in `BALANCE.md` §R): Fisioterapista → *Competenza infortuni* (guarigione più veloce, settimane tolte) e *Velocità recupero* (fatica); Medico → *Prevenzione* (rischio infortunio in allenamento) e *Diagnosi* (rischio di ritiro in gara); Preparatore mentale → *Motivazione* (bonus di forma) e *Gestione pressione* (deviazione degli Impulsivi in gara). Gli attributi sono visibili nella scheda «Staff & Impianto». **Al valore 14 gli effetti sono quelli di sempre** e i tre candidati attuali stanno tutti a 14: il resto del mercato ha profili diversi: per ogni ruolo un **junior** (attributi ~10, costo basso), l'originale e un **senior** (attributi fino a 19 in una o due qualità, costo fino a circa +50%). **Un solo specialista per ruolo**: assumerne uno licenzia quello in carica; **a ogni fine stagione il mercato si rinnova** (chi è assunto resta, gli altri sono sostituiti da 3 candidati nuovi per ruolo con profili junior / esperto / senior e compenso legato agli attributi, `BALANCE.md` §R); **ogni licenziamento (anche una sostituzione) costa la liquidazione di chi esce, 6 settimane di compenso**, e senza i soldi non si fa nulla (i pulsanti mostrano «Licenzia (€…)» e «Sostituisci (€…)»); la scheda li raggruppa per ruolo dal più economico al più caro (QUESTIONS Q33).

### 5.11 Impianti

**Palestra** livelli 0-5 (+6% di crescita in allenamento per livello, costa 2500 × (livello+1) da ampliare e 40 × livello a settimana). **Tribune** da ampliare di 500 posti alla volta fino a 20.000 (nessun costo di gestione).
La condizione della **pista** cala ogni settimana e ogni meeting in casa, e influenza il punteggio.
Dal lotto **E.2** (2026-11-21, cifre del piano, Q34) quattro **impianti avanzati** si comprano una volta sola nella tab «Staff & Impianto» (nessuna manutenzione): **Centro medico** (€15.000: −15% sui tempi di infortunio, in allenamento e in gara; non sulla squalifica per doping; in pratica ≈−12,5% perché gli stop sono interi e mai sotto 1 settimana), **Centro analisi video** (€10.000: +5% di probabilità di migliorare la Tecnica), **Palestra pesi** (€12.000: +10% sulla Forza, si somma alla Palestra a livelli) e **Campo altura** (€20.000: +10% sulla Resistenza, solo atleti di Mezzofondo). Il «%» è la probabilità settimanale di crescita in allenamento, come la Palestra. Senza impianti il gioco è identico a prima (`models/facilities.py`, `BALANCE.md` §S).

### 5.12 Fan e sponsor

Gli atleti guadagnano **fan** con piazzamenti, PB e record (i fan non calano mai: difetto di bilanciamento noto). I maggiorenni in prima squadra producono sponsor personali settimanali.

### 5.0 Avvio senza atleti e Preparazione (Q32, 2026-11-20; cifre provvisorie)

Una **Carriera nuova** nasce con rosa e vivaio **vuoti**: il generatore di atleti (`generate_initial_roster`) resta per mercato, scouting e rivali ma non si chiama più all'avvio. Il giocatore ha 18.000 € (invariato) e costruisce la squadra con **«Vivaio & Osservatori»** (scouting giovanile) e **«Rosa & Allenamenti» → «Mercato Svincolati»**, disponibili dalla settimana 1. Le notizie spiegano la situazione con un messaggio iniziale; schede e Dashboard mostrano un aiuto («Nessun atleta in rosa…») invece di tabelle vuote.

- **Preparazione:** `SeasonPhase.PREPARAZIONE`, `GameState.prep_weeks` = 8 nelle Carriere nuove (0 nei vecchi salvataggi e nel Prototipo). **Nessuna gara**: `is_race_week` è falso in Preparazione e `weeks_until_competition` la salta (a settimana 1 la prima gara è la 12). Si ripete a inizio di ogni stagione; la stagione si chiude al giro del ciclo (settimana 45, 89, …). `start_date` parte 8 settimane prima, così l'Outdoor apre il 6 aprile.
- **Non iscrizione:** se la Prima Squadra è vuota, il meeting si simula (i rivali corrono) ma la società non partecipa: niente trasferta, biglietti, usura pista, bonus squadra o diritti TV, **nessuna sanzione**, una notizia lo spiega e non si apre alcuna finestra di gara. Con atleti (anche tutti infortunati) il meeting va come prima.
- **Stagione di fondazione (stagione 1):** il Board assegna tre obiettivi di fondazione (6 atleti in società, 2 ragazzi nel vivaio, 3 meeting con un atleta schierato). Il verdetto è **solo informativo**: non conta come stagione fallita, non tocca il conteggio per l'esonero, e dopo la stagione 1 non scattano il taglio dello sponsor né la penalità «resta fermo» degli agenti. **Stagione 2:** le tre chiavi standard (posto in lega, bilancio, record), con il posto in lega allargato di un posto ogni 5 punti di forza che la rosa ha sotto la media dei rivali (al massimo 3 posti); dalla stagione 3 tutto standard.
- Aperto: economia senza atleti (AUDIT R29), cifre da confermare (QUESTIONS Q32).

### 5.13 Dilemmi etici e obiettivi

- **Dilemmi**: nelle settimane 3 e 7 sempre, altrove 22% di probabilità; due tipi (doping / giovane promettente). Si accettano o rifiutano con effetti su soldi, reputazione, prestigio, forma. Chiudere la finestra (X, Esc) o premere «Ignora» fa decadere il dilemma **senza effetti** (`dismiss_dilemma`: né il bonus
  dell'accettazione né il premio del rifiuto), con una notizia; un dilemma ancora pendente (vecchio salvataggio) viene scartato dal tick successivo. Non blocca più i successivi (A.4).
- **Obiettivi del Board** (C.2, 2026-11-20; cifre provvisorie, Q27): in **Carriera**, a inizio stagione (alla partita nuova e a ogni cambio stagione) il Board assegna tre obiettivi: **chiudere tra i primi N della lega** (3 / 4 / 5 / 5 per livello), **non chiudere la stagione in perdita** (budget a fine stagione almeno quello di inizio stagione) e **stabilire almeno 2 record sociali** (individuali e di staffetta). A fine stagione (`close_season`, prima del cambio di livello e del bonus promozione) si contano: con **meno di 2 centrati su 3** la stagione è **fallita**; **2 stagioni fallite di fila** portano all'**esonero** (`fired`, game over come il fallimento: il tick non parte, il pulsante diventa «Esonerato dal Board»); una stagione non fallita azzera il conto. Il verdetto è nella finestra di fine stagione e nella storia delle stagioni; una finestra elenca gli obiettivi della stagione che comincia; la Dashboard mostra l'avanzamento e un avviso dopo una stagione fallita. Il Prototipo (nessuna stagione) tiene i suoi tre obiettivi fissi; un salvataggio precedente a C.2 tiene i vecchi fino a fine stagione, che non viene giudicata. Nessuna estrazione di RNG.

### 5.14 Record e PB

Per atleta e per evento si tiene il **PB** (solo con vento legale); la società ha **record sociali** per evento e divisione, più un albo e una scheda «Albo & Record» (con anche la lista degli **ex atleti**, §5.16). Si segnano «momenti storici» (misure oltre una soglia storica per evento).

### 5.15 Ranking (C.1, 2026-11-20; cifre provvisorie, `QUESTIONS.md` Q26)

Ogni piazzamento in una gara **individuale** dà punti ranking: `RANKING_PLACE_POINTS[posto-1]` (100, 80, 65, 52, 42, 34, 28, 22; oltre l'8° nulla) × il moltiplicatore del livello (0,10 / 0,25 / 0,50 / 1,00). Li prendono gli atleti del club e quelli dei rivali (anche quando il club non iscrive nessuno); il ritirato non è classificato; le staffette non danno punti. A ogni meeting i punti già posseduti decadono ×0,9 (metà del peso in ~6 meeting), per tutti nello stesso tick e **prima** dei nuovi.

Per riempire le classifiche ci sono **100 atleti sintetici per disciplina e sesso**: nome e nazionalità di fantasia (25% italiani), un livello dal 94 al 58, che a ogni meeting si muove di poco e simula un piazzamento contro un campo virtuale di 7 avversari del livello di gara più vicino al loro, con la stessa tabella dei punti. Non invecchiano né si ritirano. Usano **l'RNG della partita** (convenzione 3; scelta dell'utente, Q26): il campo si crea con `rng` alla partita nuova e al caricamento di un salvataggio v14, e a ogni meeting estraggono da `r` al passo C-13b del tick; essendo lo stato dell'RNG salvato, ricaricare dà gli stessi risultati. Aggiungere il ranking ha spostato le estrazioni di ogni partita a parità di seme.

Classifiche (`models/ranking.py`): **mondiale** (Top 100: sintetici + rivali + club), **nazionale** (solo `Italia`, Top 50), **società** (le società del livello attuale, per somma dei punti dei loro atleti). Un atleta del club fuori dalla Top N compare comunque in fondo alla tabella con il suo posto vero. Oggi è **solo informativo** (nessun effetto su sponsor, premi, inviti): gli inviti Diamond League sono il sottopunto C.1b, da decidere. Calibrazione misurata: chi vince sempre in Fase regionale resta fuori dalla Top 100, in Finale Oro è 1°.

### 5.16 Ritiro e post-carriera (C.3, 2026-11-20; cifre provvisorie, `QUESTIONS.md` Q28)

Solo in **Carriera**, al cambio stagione, dopo il +1 d'età e **prima** del rinnovo dei contratti: ogni atleta della **Prima Squadra** (il vivaio no) può ritirarsi. Probabilità per età: 33 anni **25%**, 34 anni **50%**,
da 35 anni **certo**. Ritiro anticipato per infortuni: da 30 anni, con **almeno 3 infortuni nella stagione appena chiusa** (`Athlete.season_injuries`: allenamento e ritiro in gara; la squalifica per doping non conta), 35% di
probabilità (non scende mai sotto quella dell'età). L'**ultimo atleta** della Prima Squadra non si ritira mai (come per i contratti). Chi si ritira esce da formazione e staffette, che si ricompongono da sole, e finisce
nella lista **«Ex atleti»** della scheda *Albo & Record* (gli ultimi 100, con stagione, età, motivo e stato); una notizia annuncia il ritiro.

**Post-carriera:** un ex atleta su dieci (10%) **si offre come allenatore** della società. Non entra in automatico (costerebbe lo stipendio senza chiedere): nella lista compare «Disponibile come allenatore» e il
pulsante **«Assumi come allenatore»** lo ingaggia a **€750** (ridotto: ex atleta della casa; un allenatore di livello 1 ne costa 1.500), con le solite regole (un allenatore a settimana, massimo 6 specializzati). Le sue
abilità vengono dagli **attributi che aveva da atleta**, non dal PB: principale e secondaria della sua disciplina (come per gli altri allenatori) limitate a 55-85, la secondaria 10 punti sotto, le altre al livello base 25.
L'offerta **scade al cambio stagione successivo**.

**Conseguenza di gioco:** nessuno rimpiazza chi si ritira da solo; si rimpiazza con il vivaio (promozione a 18 anni), lo scouting e il mercato. Un club in autopilota (nessun acquisto, 6 partite, 8 stagioni) passa da
16 atleti a 3-8 (AUDIT R24).

### 5.17 Agenti (D.1, 2026-11-20; cifre provvisorie, `QUESTIONS.md` Q29)

Ogni atleta (anche del vivaio e dei candidati del mercato) ha un **agente**; un agente ne cura più d'uno (in media 2-3: con la rosa iniziale 6-8 agenti per 16 atleti), quindi la **relazione** (0-100, parte da 50) è del
giocatore con l'agente, non con il singolo atleta. L'agente ha nome di fantasia e una **personalità**: **Aggressivo** (30% dei nuovi agenti) chiede **+20%** sull'ingaggio al tesseramento, **Ragionevole** (50%) 0,
**Leale** (20%) **−10%**. La relazione sposta la richiesta di altri **±15 punti percentuali**: a 50 nessuna modifica, a 100 −15, a 0 +15 (un Aggressivo con ottimi rapporti chiede ancora circa +5%, un Leale circa −25%).

**Dove agisce oggi:** solo sull'**ingaggio una tantum** del Mercato svincolati (`negotiated_fee` = ingaggio standard × (1 + personalità + relazione)). La finestra del mercato mostra una colonna **Agente** (nome, personalità, relazione;
il tooltip dà la percentuale chiesta) e il costo già con la richiesta dell'agente. Il rimborso spese settimanale non cambia (R14), e il vivaio non ha ingaggio. La scheda atleta mostra l'agente nella riga **Agente**.
Con D.2 la stessa richiesta è l'apertura della trattativa (§5.18).

**Come cambia la relazione:** **+3** per ogni suo atleta che alla scadenza del contratto viene rinnovato, **+1** per ogni **podio** (1°-3°) in una gara individuale di un suo atleta (le staffette non contano); **−10** se si
**svincola** un atleta della Prima Squadra (peggiora anche con i suoi altri assistiti), **−5** per ogni atleta non rinnovato che lascia la società, **−2** per ogni atleta della Prima Squadra che **resta fermo** (mai convocato
in una gara individuale della stagione appena chiusa, né in una staffetta in formazione: non conta l'atleta del vivaio). A ogni **cambio stagione** la relazione si avvicina a 50 di un quarto della distanza, con passo minimo
di 1 punto (senza questo, in autopilota tutti gli agenti arrivavano a 100 entro la quarta stagione); la penalità dei «fermi» si applica **dopo** l'attenuazione. Misura in autopilota (6 partite, 8 stagioni): relazione media
tra 67 e 77 a regime, mai bloccata a 100. In autopilota quasi nessuno resta fermo, quindi la penalità si vede solo lasciando in panchina qualcuno per un'intera stagione (coperta dai test, non misurata in partita).

**Mantenimento:** gli agenti senza clienti e con relazione neutra si tolgono a fine settimana (sono i candidati del mercato non presi); se ne ricordano al più 20 senza clienti, quelli con la relazione più lontana da 50. Nessuna
estrazione dell'RNG della partita: nome e personalità di un agente nuovo derivano da id e nome del primo assistito; l'assegnazione di un atleta a un agente esistente o nuovo dal suo nome (`zlib.crc32`).

### 5.18 Trattative, clausola rescissoria e bonus per record (D.2, 2026-11-20; cifre provvisorie, `QUESTIONS.md` Q30)

**Trattativa** (`models/market.py`, senza RNG). Dal Mercato svincolati, «Tessera Atleta Selezionato» apre la finestra di **trattativa** con l'agente del candidato (se non ha agente si paga l'ingaggio standard come prima):
1. L'agente **apre** con la sua richiesta (§5.17: ingaggio standard × personalità × relazione).
2. Puoi **accettare**, **rifiutare** o **offrire** una cifra più bassa. Se l'offerta arriva alla **soglia** dell'agente (la sua richiesta meno la **flessibilità**) è accettata subito (si paga l'offerta, mai più della richiesta).
   La flessibilità è **5%** per un Aggressivo, **15%** per un Ragionevole, **25%** per un Leale, ±10 punti secondo la relazione (a 100 +10, a 0 −10; tra 0 e 50%).
3. Sotto la soglia l'agente **controffre una volta**, a metà strada tra la tua offerta e la sua richiesta ma mai sotto la soglia; puoi solo accettare o rifiutare (non si rilancia). Rifiutare non costa nulla e non cambia la relazione.
L'ingaggio minimo trattabile è €100. Il controller (`recruit_athlete(prospect, terms)`) ricontrolla che le condizioni siano ottenibili da quell'agente (ingaggio tra soglia e richiesta, bonus ammesso): una finestra «falsificata» non paga meno.

**Bonus per risultati.** Nella trattativa si può scegliere un bonus (€300, €600 o €1.000) pagato a **ogni record sociale individuale** dell'atleta finché dura il contratto (le staffette non contano): l'agente abbassa l'ingaggio **dello stesso importo**.
È quindi un pagamento rimandato: conviene se pensi che i record non arrivino o vuoi liquidità subito, e costa di più se ne arrivano molti (AUDIT R27). Il bonus esce dal budget nel meeting (libro mastro «Bonus Atleti», con una notizia) e **scade al rinnovo del contratto**.

**Clausola rescissoria.** Svincolare un atleta di **Prima Squadra** costa **20 settimane del suo rimborso spese** (circa €1.000-10.400; `Athlete.release_clause_cost`, calcolata, non salvata): senza i fondi lo svincolo è rifiutato; il vivaio non ha clausola. **«Non rinnovare»** e la scadenza del contratto restano **gratuiti**. La conferma di svincolo mostra
la clausola; restano la penale di fedeltà (−8) e il calo di relazione con l'agente (−10). La scheda atleta mostra la riga **Clausola** (con il bonus per record, se c'è).

### 5.19 Finanze dettagliate (D.3, 2026-11-20; cifre provvisorie, `QUESTIONS.md` Q31)

**Bilancio mensile.** Un mese = **4 settimane** (la stagione di 36 ne ha 9). Quando comincia un nuovo mese il tick (`close_month_if_due`, in fondo al tick, dopo ogni movimento: bonus promozione compreso) chiude quello appena finito e ne ricava
il resoconto **dal libro mastro**: entrate e uscite **per categoria** (il capitale iniziale non è un incasso d'esercizio) e il saldo a fine mese. Il saldo del mese è **esattamente** la variazione del budget del mese (c'è un test).
Si ricordano gli ultimi **36 mesi** (quattro stagioni), salvati (schema v20). La scheda **Finanze** ha due sezioni: **Bilancio mensile** (grafico a barre entrate/uscite degli ultimi 12 mesi, elenco dei mesi con saldo e budget a fine mese,
dettaglio per categoria del mese scelto) e **Libro mastro** (i movimenti, come prima). Il grafico è disegnato con `QPainter` (nessuna dipendenza nuova: `requirements.txt` non cambia).

**Merchandising.** Incasso settimanale (libro mastro «Merchandising», incluso nelle entrate settimanali): **fan della Prima Squadra ÷ 40 + prestigio ÷ 20** (zero a inizio partita; in autopilota circa €100-150 a settimana dopo una stagione, il 5-10% delle entrate).

**Sponsor con obiettivo.** Se l'ultima stagione è finita **fuori dai primi 5** della lega, lo **sponsor società** della stagione che comincia vale **−20%**; chiudere tra i primi 5 lo ripristina. Si legge dal verdetto dell'ultima stagione (`season_history`): nessun dato in più da salvare.
Taglia solo lo sponsor società (non gli individuali, il merchandising o le quote). La carta «Entrate settimanali» e la riga del libro mastro dicono il motivo. In autopilota (nessuna azione) 7 partite su 8 chiudono la prima stagione fuori dai primi 5.

**Diritti TV.** Solo per i meeting **in casa** del livello **Internazionale**: **€3.000** a meeting (libro mastro «Diritti TV»). Negli altri livelli e in trasferta nulla.

### 5.20 Notizie dinamiche (F.1, 2026-11-21; soglie provvisorie, `QUESTIONS.md` Q36)
Dal lotto **F.1** (2026-11-21, Q36) a ogni **chiusura di mese** (quattro settimane, quando si scrive il bilancio mensile) il giornale racconta, **al più una riga per tipo**, nel feed della Dashboard: **«Allenatore del Mese»** se il club ha vinto il meeting del mese; **«La stampa critica la tua gestione»** se i conti sono in rosso, il Board ha già bocciato una stagione o il club è ultimo nell'ultimo meeting (in quest'ordine di priorità); **«Tensione nello spogliatoio»** per l'atleta di Prima Squadra il cui agente ha una relazione con te ≤ 30. Sono solo cronaca (nessun effetto su morale o reputazione: arrivano con le conferenze stampa, F.2); la frase tra tre varianti si sceglie in modo deterministico, senza RNG. Niente notizie senza atleti in Prima Squadra né nella stagione di fondazione. I record sociali, i primati personali, gli infortuni e il resto del registro notizie c'erano già e non sono cambiati (`models/narrative.py`).

### 5.21 Conferenza stampa (F.2, 2026-11-21; cifre provvisorie, `QUESTIONS.md` Q37)

Dopo i risultati di ogni meeting del club si apre una **conferenza stampa** con due domande (solo se la società ha gareggiato): **«come giudica la prestazione?»** — dirsi *soddisfatti*, *cauti* o *critici* sposta la **reputazione** in modo coerente col risultato (classifica a squadre: tra i primi 2 = buono, tra gli ultimi 2 = brutto, con almeno 4 squadre; da +2 a −2: dirsi soddisfatti dopo un ultimo posto costa 2, la risposta cauta non fa mai male) — e **«punta sul futuro di X?»**, con X il miglior atleta del meeting: *punto fermo* (+3), *valuteremo* (0) o *il posto non è garantito* (−3) sulla **relazione con il suo agente** (D.1). Si può rispondere a una sola domanda o chiudere con «Nessun commento»: allora non cambia nulla. Una conferenza per meeting. Non c'è un morale per atleta: la relazione con l'agente è l'unico canale verso l'atleta. Nessun RNG (`models/press.py`, `BALANCE.md` §U).

### 5.22 Relazioni tra atleti (F.3, 2026-11-21; cifre provvisorie, `QUESTIONS.md` Q38)

Ogni coppia della Prima Squadra ha una **relazione** (−100…+100): per ora nessuna, un'**amicizia** (≥ +30) o una **rivalità** (≤ −30), assegnata la prima settimana in modo deterministico (circa il 12% di amicizie e il 6% di rivalità). Si vede nella tab **«Relazioni»** della scheda atleta. Effetti: una staffetta con **due frazioni amiche ha +10 di affiatamento in gara** (−10 con due rivali; amici e rivali insieme si annullano); la **chimica di squadra** (amicizie meno rivalità) sposta la forma di tutti fino a ±3 (di solito intorno a +2); chi corre insieme in staffetta si avvicina di +2 a meeting. Non c'è un morale per atleta (scelta dell'utente: opzione 1); nessun RNG (`models/relationships.py`, `BALANCE.md` §V).

### 5.23 Momenti di gloria (F.4, 2026-11-21; regole provvisorie, `QUESTIONS.md` Q39)

Cinque eventi aprono un **popup celebrativo** (finestra dorata con dissolvenza d'ingresso, uno dopo l'altro, dopo i risultati e la fine stagione): **record del mondo** (la misura raggiunge il tetto del gioco, solo gare individuali valide), **momento storico** (un muro di `historic_mark` abbattuto), **titolo** e **promozione** a fine stagione e **atleta dell'anno** (più vittorie, poi più podi nella stagione). Sono messe in scena: nessun effetto su soldi, reputazione o atleti. Record del mondo e atleta dell'anno lasciano anche una riga nelle notizie e nei traguardi (gli altri tre le avevano già); i momenti non sono salvati. **Non ci sono** la convocazione in nazionale e l'invito alla Diamond League del piano: nel gioco non esistono (C.1b). Il record sociale non apre popup (capita spesso e ha già la sua notizia). `models/glory.py`, `BALANCE.md` §W.


### 5.24 Dashboard potenziata (G.1, 2026-11-21; prototipo, `QUESTIONS.md` Q40)

La **Dashboard** («Panoramica») si ridisegna con il design system del Lotto G (`views/theme.py`, font Inter incluso) ed è ora in **QML** (`views/qml/`; animazioni di ingresso, linea del grafico che si disegna, suggerimenti a comparsa; con ripiego sulla versione QWidget se QML non parte). In alto un **semaforo** (rosso: dilemma da risolvere o urgenza; ambra: c'è da guardare; verde: tutto ok) e i quattro indicatori; poi il **grafico di forma e fatica medie della Prima Squadra** (ultime 12 settimane, con valori al passaggio del mouse), gli obiettivi con spunte vere, la **timeline della stagione** (una casella per settimana, gare in rilievo, Preparazione tratteggiata, «oggi», contratti in scadenza), la **heat map** dei migliori 8 atleti sulle gare della fase (punteggio atteso, anello sulla specialità), le priorità, la tabella dei migliori con stato a «pillola» e la cronaca. Lo **storico** che alimenta i grafici (forma, fatica e ultime 10 gare per atleta) si scrive a fine tick e a ogni gara individuale, **senza RNG e senza effetti sul gioco**; le partite già in corso lo riempiono giocando. `models/history.py`, `models/dashboard.py`, `views/widgets.py`.


### 5.25 Scheda atleta potenziata (G.2, 2026-11-21; `QUESTIONS.md` Q40)

La tab «Panoramica» della **Scheda Atleta** ha una parte grafica in QML: **radar** delle cinque caratteristiche (con la media dei compagni di disciplina tratteggiata), **barra verso il potenziale** («mancano N punti»), **condizione** (forma, fatica, sonno, alimentazione) e **caratteristiche** a barre colorate per livello (verde da 80, giallo da 65, arancione da 45, rosso sotto; la fatica si legge al contrario), **ultime 10 gare** come linea del piazzamento (vittorie, primati e ritiri segnati) e **confronto** con gli atleti della stessa disciplina in rosa. L'anagrafica a sinistra e le azioni in basso sono QWidget come prima. Solo presentazione: nessun effetto sul gioco. `models/athlete_view.py`.


### 5.26 Tabellone live della gara (G.3, 2026-11-21; `QUESTIONS.md` Q40)

Durante le **corse in pista** (vista interna 2D o 3D) a destra compare un **tabellone live**: tempo di gara, fase di partenza, passo del primo, distacco 1°-2° e, per ogni corridore, posto (la classifica si riordina scorrendo), pettorale, squadra, velocità in km/h, distacco e avanzamento. All'arrivo mostra i tempi ufficiali e i distacchi in secondi. È solo una lettura di ciò che la vista sta già mostrando: **non cambia tempi, ordine o misure**. Pulsante «📊 Tabellone» per nasconderlo. `views/race_live.py`, `views/qml/RaceBoard.qml`.

---

## 6. Categorie: parametri principali

| Categoria | Livello rivali (pt) | Sponsor sett. | Montepremi base | Trasferta | Biglietto |
| --- | ---: | ---: | ---: | ---: | ---: |
| Provinciale | 42 | 840 | 1.500 | 350 | 4 |
| Regionale | 56 | 1.750 | 3.500 | 750 | 6 |
| Nazionale | 70 | 3.500 | 7.500 | 1.500 | 9 |
| Internazionale | 84 | 6.720 | 15.625 | 3.000 | 14 |

---

## 7. Persistenza (SQLite)

- Un file `.db` per slot in `~/.track_field_manager/saves/` (più un `savegame.db` legacy in `~/.track_field_manager/`). Tabelle: `game_state` (riga unica, molti campi JSON), `athletes`, `coaches`, `staff`, `transactions`, `competition_history`.
  `save_game` fa DELETE+INSERT in una transazione.
- **Schema `SCHEMA_VERSION = 21`** (v21 = `game_state.prep_weeks`, settimane di Preparazione, Q32, 2026-11-20, `0` = calendario di prima; la stagione di fondazione si riconosce da `prep_weeks` > 0 e stagione 1; `SeasonEndResult.board_foundation` sta nel JSON della storia stagioni; v20 = `game_state.monthly_report_json`, D.3; v19 = `athletes.record_bonus`, D.2; v18 = `athletes.agent_id` e `game_state.agents_json`, D.1; v17 = `athletes.season_injuries` e `game_state.retired_json`, C.3; v16 = `game_state.board_json`, C.2; soglie e avanzamento degli obiettivi in `objectives_json`, verdetto in `season_history_json`) — (v12 = `game_state.league_places_json`, A.2; v13 = `game_state.rng_state_json`, A.3; v14 = `game_state.race_strategy_json`, B.1; v15 = `athletes.ranking_json` e `game_state.ranking_pool_json`, C.1; i punti dei rivali stanno nel loro JSON), `PRAGMA user_version`. Ogni nuova colonna: voce in `MIGRATIONS` (con `DEFAULT`) *e* nella `CREATE TABLE`.
- **Apertura sicura** (lotti 1.1/1.2): file assente o di 0 byte → DB nuovo, creato in una transazione. Versione corrente → apertura in sola lettura, nessuna scrittura. Versione migrabile (v2…v8) →
  **backup verificato** con `Connection.backup()` in `saves/backups/<slot>.v{N}.{timestamp}.db.bak` (sempre nuovo, 3 più recenti per slot, potati solo dopo una migrazione riuscita), poi **una sola transazione**
  (`BEGIN IMMEDIATE` … `COMMIT`, ALTER + creazione tabelle + `user_version` insieme, rollback su errore). Versione non supportata (più recente, v0/v1 con dati, file non vuoto senza tabelle) →
  `UnsupportedSaveVersion` **prima di scrivere**: niente DROP, file intatto. Ripristino da backup: manuale (copiare il `.db.bak` come `.db`).
- `GameController.load_save_slot`/`load_game` non fanno salire le eccezioni (in PyQt6 un'eccezione che esce da uno slot termina il processo): ritornano `False`, riempiono `last_load_error` (messaggio + percorso del backup + traceback)
  e la schermata iniziale mostra un `QMessageBox.warning` con il traceback nei dettagli.
- **Elenco slot**: `read_save_summary` (sola lettura) elenca anche gli slot non apribili («versione più recente», «non compatibile», «danneggiato») con i soli metadati affidabili; «Continua» usa il più recente slot apribile.
- **Schema 26** (G.1/G.2): `athletes.history_json` = storico di forma, fatica e ultime gare per i grafici (`{}` = nessuno). Le versioni elencate sopra sono ferme alla v21 per brevità: la corrente è `SCHEMA_VERSION` in `database.py`.
- I campi mancanti dei vecchi salvataggi si riempiono al caricamento in modo deterministico (es. corpo degli atleti, seed = id atleta).
- **Non salvati**: risultati dello scouting e pool del mercato (solo in memoria). Lo stato dell'RNG **sì** (A.3): ricaricare non «ritira i dadi». Resta una crepa: il pool del mercato si rigenera dall'RNG al momento in cui lo si apre; se dopo averlo aperto si fa un'altra azione che salva, il pool riaperto dopo la ricarica è diverso (AUDIT R5).

---

## 8. Interfaccia (PyQt6, tema scuro)

- **Schermata iniziale** (`StartScreen`): hero, scheda «Continua ultima partita», nuova società (nome, modalità, provincia di partenza), tabella dei salvataggi (carica, elimina, doppio clic).
- **Finestra principale** (`MainWindow`): barra laterale con tre sezioni e dieci pagine:
  GESTIONE → *Dashboard*, *Rosa & Allenamenti*, *Vivaio & Osservatori*; COMPETIZIONI → *Calendario & Gare*, *Staffette*, *Rivali*, *Ranking* (classifica mondiale, nazionale e delle società, per disciplina e sesso: C.1); SOCIETÀ → *Staff & Impianto*, *Finanze*, *Albo & Record*.
  In alto un HUD con settimana/budget/prestigio e il pulsante **Avanza settimana**; menu per salvare/caricare.
- **Dialoghi**: Scheda Atleta (PANORAMICA, ALLENAMENTO, COMPETIZIONI, con in testa la riga di ranking: posto mondiale e nazionale e punti per gara), Mercato/Recluta atleta, Assumi Allenatore, Nuova Partita, Dilemma Etico, Fine Stagione (con il verdetto del Board), Obiettivi del Board a inizio stagione, Risultati gara (tabellone con pettorali).
- La UI è piena di piccole regole duplicate (soglie fatica, zona promozione/retrocessione) che andrebbero lette dal modello: vedi `AUDIT.md` Q13.

---

## 9. Gare in diretta

Dopo il tick di una settimana di gara si apre la **gara in diretta** (`RaceViewerDialog`) prima dei risultati. Mette in scena un `CompetitionSummary` già calcolato; non cambia mai tempi, ordine o misure
(ogni atleta taglia il traguardo esattamente al suo tempo ufficiale, c'è un test).

- **Modello di movimento** (funzioni pure e testate): `curve_progress`, `position_fraction`, `reaction_time` (0,12-0,22 s, incluso nel tempo ufficiale). Curva di velocità per gara (100m, 400m, 800m, 1500m, staffetta).
- **Viste PyQt**: 2D laterale (`TrackRaceWidget`) e 3D software con `QPainter` (`Track3DWidget`, senza OpenGL: camera a foro stenopeico, `clip_near`, antialiasing spento per le grandi superfici). Il 3D copre solo le corse in pista.
  Concorsi (lungo, peso): scena 2D + tabellone; le singole prove sono ricavate dal risultato finale con un generatore deterministico (`generate_attempts`).
- **Controlli**: pausa, velocità 1×/2×/4×, vista 2D/3D, «Salta alla fine», «Prossima gara», «Vai ai risultati». Ralenti dell'arrivo.
- **Visualizzatore Godot** (`godot_viewer/`, Godot 4.3+/GDScript, **opzionale**, separato dall'app): stile «diretta TV» 2010 per 100m, 400m, 800m, 1500m, 4x100m, 4x400m, Lungo e Peso. Legge da SQLite
  (`godot_viewer/data/schema.sql` è l'unica fonte dello schema; `models/race_export.py` esporta) i risultati già calcolati. MVC interno: Model `DatabaseManager.gd` (sola lettura), Controller `RaceController.gd`, View 3D (`Stadium.tscn`, `BroadcastCameras`, `RunnerView`)
  e View 2D (`HUD.tscn`). Contiene: pista ovale con geometria reale (`TrackGeometry.gd`), regia automatica delle camere legata allo stato della gara, posa ai blocchi con IK, personaggi con scheletro e animazioni CC0 (Quaternius), cadenza/ampiezza di passo per evento (`StrideModel.gd`),
  atleti ritirati (DNF) e staffette squalificate (DQ), pettorali stampati sulla canotta (numero unico per meeting, assegnato da `models/bibs.py`), cartelloni con sponsor di fantasia, tribune, fotografi e giudici come persone vere, ralenti dell'arrivo, classifica finale.
  Il gioco lo lancia con `QProcess` (`views/godot_launcher.py`) e **ripiega sulla vista PyQt interna** se Godot, il progetto o il plugin `godot-sqlite` mancano; `TEF_NO_GODOT=1` lo disattiva (usato nei test). Non copre gli altri concorsi né più di 8 corsie. Il peso ha tentativi animati (rotazione, volo balistico esatto alla misura del DB, nastro, arco del migliore) con regia dedicata, vedi `godot_viewer/README.md`.
- Le viste PyQt interne **non** mostrano i pettorali.

---

## 10. Determinismo e RNG

La simulazione riceve un `rng` iniettabile (`random.Random`), quindi a parità di stato e di RNG gli esiti sono identici. **Dal 2026-11-20 (A.3)** il controller ha un solo `rng` per partita (seme casuale a ogni avvio dell'app), il cui **stato completo** (`getstate()` come JSON, `GameState.rng_state`, schema v13) è scritto a ogni salvataggio e ripristinato al caricamento: lo stesso salvataggio caricato due volte dà gli stessi esiti, e ricaricare dopo una ricerca vivaio non permette di rifarla. Un salvataggio vecchio senza stato si semina in modo deterministico con `hashlib` da società, stagione e settimana (`legacy_seed`).
Anche le azioni UI (scouting, mercato, allenatori) consumano lo stesso RNG. Regola di progetto: nessun `hash()` su stringhe per ricavare seed (è salato per processo): la fascia del potenziale ora usa `zlib.crc32`. Lotti 2.1/2.2 di `PLAN.md` fatti. Dal 2026-11-21 (E.2, E.3, F.1, F.2) le novità sono **neutre per l'RNG** salvo: il centro medico (una estrazione per infortunio, solo se posseduto) e la rete scouting regionale (una o due estrazioni per ragazzo, solo con una regione); notizie dinamiche e conferenza stampa non estraggono nulla (varianti con `crc32`).

---

## 11. Test e comandi

```bash
.venv/bin/pip install -r requirements.txt                                   # PyQt6, pyinstaller
.venv/bin/python main.py                                                    # avvia l'app (o ./TrackAndFieldManager.sh)
QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests -v # 829 test, ~39 s su Linux
PYTHONPATH=. python3 -m unittest tests.test_migrations tests.test_assignments tests.test_contracts tests.test_event_800m -v   # 99 test, SENZA PyQt6
```

`python` non è nel PATH dell'ambiente di sviluppo (si usa `.venv/bin/python`, Python 3.14.4). I test GUI usano `QT_QPA_PLATFORM=offscreen` e **non chiamano mai `exec()` di dialoghi modali** (bloccherebbero per sempre).
`test_migrations.py` genera fixture programmaticamente (una per ogni versione v2…v8), verifica migrazione, backup, rollback su fallimento a metà (E1), rifiuto delle versioni ignote (E2).
`test_game.py` copre simulazione, curve di movimento, viste in ogni stato (intercetta eccezioni di disegno, **non** giudica l'aspetto), migrazioni dei vecchi salvataggi e il click su uno slot non supportato (in un processo a parte: fallisce se l'app muore).

---

## 12. Piano di lavoro (stato)

`PLAN.md` divide l'intervento in lotti piccoli: 1 sicurezza dei salvataggi → 2 determinismo → 3 ambiguità di regole → 4 economia → 5 refactor → 6 UI.

- ✅ **1.1** migrazione transazionale con backup, ✅ **1.2** rifiuto delle versioni sconosciute (fatti).
- Fuori dai lotti, decisioni di `QUESTIONS.md` già implementate (2026-11-19): Q15 tetto 2+1, Q16 800m (anche in Godot; restano Salto in Alto e Disco), Q17 fascia d'età e under 20 fuori da Internazionale, Q18 nomi dei meeting,
  Q20 DQ 4x400m, Q21 bonus Picco, Q22 € / rimborsi / contratti (schema v10 e v11). La Q19 (punteggi tabellari WA) è rinviata.
- ✅ **Lotti A e B** del piano di gameplay (`PIANOLAVORO.md`) e **C.1** (ranking, 2026-11-20; resta **C.1b**, gli inviti Diamond League, da decidere). **C.2** (obiettivi del Board ed esonero, 2026-11-20; cifre da confermare, Q27). **C.3** (ritiro e post-carriera, 2026-11-20; cifre da confermare, Q28). **D.1** (agenti con personalità e relazione, 2026-11-20; cifre da confermare, Q29). **D.2** (trattative, clausola rescissoria, bonus per record, 2026-11-20; cifre da confermare, Q30). **D.3** (finanze dettagliate: bilancio mensile, merchandising, sponsor con obiettivo, diritti TV, 2026-11-20; cifre da confermare, Q31): **lotto D chiuso**. Prossimo: lotto E (staff e impianti).
- ✅ **Lotto E** (2026-11-20/21): **E.1** staff con attributi e mercato dello staff (Q33), **E.2** impianti avanzati (schema v23, Q34), **E.3** Academy, osservatore e rete scouting (schema v24, Q35). **Lotto F** (chiuso, con i limiti di Q39): **F.1** notizie dinamiche (Q36), **F.2** conferenze stampa (Q37), **F.3** relazioni tra atleti (Q38, schema v25) e **F.4** momenti di gloria (Q39). Cifre provvisorie in `BALANCE.md` §R-§U.
- ⏳ **1.3** il tick non lascia stato a metà (snapshot e ripristino su eccezione, riepilogo del tick fallito): proposto, in attesa di decisione dell'utente su 5 punti.
- Fatti il 2026-11-20 dentro `PIANOLAVORO.md` (lotto A): **1.4** protezione dal doppio click (A.5), **3.1** dilemma chiuso senza scelta (A.4) e **3.3** spareggio (A.2). **2.1/2.2** RNG salvato e niente `hash()` (A.3). Poi: 3.x regole (spareggio, debito azzerato dai dilemmi…); 4.x economia; 5.x (modulo di bilanciamento `models/balance.py`, test di simulazione senza Qt, `race_export` senza dipendere da `views/`); 6.x UI.

---

## 13. Difetti noti e decisioni aperte (sintesi di `AUDIT.md` e `QUESTIONS.md`)

| Tema | Sintesi |
| --- | --- |
| Economia (R3) | **Risolto** il 2026-11-20 (A.1) per le partite nuove: sponsor +40%, premi +25%, rimborsi −45%, bonus promozione 5.000 €. I salvataggi esistenti tengono i rimborsi vecchi. |
| Dilemma bloccato (R4) | **Risolto** il 2026-11-20 (A.4): chiudere = «Ignora», nessun effetto. |
| RNG (R5) | **Risolto** il 2026-11-20 (A.3): stato salvato e ripristinato; resta la crepa del pool del mercato (non salvato). |
| Debito azzerato (R7) | Rifiutare un dilemma porta a 0 un bilancio negativo (`max(0, budget − 600)`). |
| Doppio click (R8) | **Risolto** il 2026-11-20 (A.5): tick non rientrante e pulsante spento durante il tick (non provato con mouse reale). |
| Spareggio (R9) | **Risolto** il 2026-11-20 (A.2): piazzamenti, poi sorteggio deterministico indipendente dal nome. |
| Fan e sponsor (R10) | Illimitati, non calano mai. |
| Obiettivi (R11/R12) | Mai rinnovati; l'obiettivo «traguardo storico» femminile usa la soglia maschile. |
| Validazione (R13) | Il controller non impedisce lo stesso atleta in più gare né la divisione sbagliata. |
| Stipendi (R14) | Mai rivisti dopo la creazione; nessun incasso da cessioni; nessun costo tribune. |
| Costanti (R15) | Sparse e duplicate (es. 12/36 settimane, soglia fatica 75): manca un modulo di bilanciamento. |
| Prototipo (R16) | Non finisce; l'età cresce solo in Carriera. |
| Mercato (R18) | Pool e scouting solo in memoria. |
| `hash()` (R17) | Salato per processo nella fascia del potenziale mostrata nel mercato. |
| Tick (T1-T11) | Dettaglio dei punti d'ordine sospetti in `TICK.md` §E. |

Le decisioni di design aperte (parte delle 22 domande, es. «che cosa è il fallimento», «dove vivono le costanti di bilanciamento») sono in `docs/QUESTIONS.md` e **spettano all'utente**.

---

## 14. Per chi lavora sul progetto (anche un altro assistente)

- Rispondere e scrivere documenti in **italiano**; nomi di variabili e codice in inglese.
- Prima di scrivere codice **esplicitare le assunzioni** e, per modifiche non banali, proporre l'approccio e aspettare l'OK.
- Dichiarare con franchezza ciò che non si è potuto verificare (es. «non ho provato l'app con il mouse, solo test offscreen e screenshot»).
- Non cambiare esiti di gara nelle viste; non introdurre comandi interattivi in gara; non toccare `MIGRATIONS`/`SCHEMA_VERSION` senza migrazione e test; non fare refactor o «già che ci sono».
- Un difetto trovato per strada si annota in `docs/AUDIT.md`; una scelta di design si chiede all'utente (`docs/QUESTIONS.md`).
- Commit in italiano e descrittivi; sviluppo sul branch indicato; non aprire PR se non richiesto.
