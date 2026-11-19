# GAME — descrizione completa di Track & Field Manager

Documento pensato per essere dato a un altro assistente (LLM) o a una persona che non conosce il progetto: descrive
**che cosa è il gioco, come funziona ogni componente e come è fatto il codice**. È una sintesi: i dettagli puntuali (cifre,
righe di codice, ordine esatto del tick) stanno in `docs/BALANCE.md`, `docs/TICK.md`, `docs/AUDIT.md`, `docs/QUESTIONS.md`,
`docs/PLAN.md` e in `CLAUDE.md`. Dove questo file e il codice divergono, **vince il codice**.

Stato descritto: 2026-11-19, branch `main`, commit `c2256a0` (lotti 1.1 e 1.2 di `PLAN.md` fatti). Suite di test: 105 test OK.

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
| **Carriera Completa** (`career`) | Rosa iniziale di 16 atleti (8 M + 8 F), 5 discipline (100m, 400m, 1500m, Salto in Lungo, Getto del Peso) più staffette 4x100m e 4x400m, stagioni cicliche **Outdoor → Cross → Indoor** da 12 settimane l'una (36 sett. a stagione), promozioni/retrocessioni tra 4 categorie. Fondo iniziale 18.000. |

Categorie (`CompetitionTier`): **Provinciale → Regionale → Nazionale → Internazionale**. Nell'interfaccia hanno i nomi dei Campionati di Società (`TIER_DISPLAY_NAMES`, Q18): **Fase regionale CdS → Finale Bronzo → Finale Argento → Finale Oro / Coppa Europa**; il `value` dell'enum, salvato nel DB, non cambia. Ognuna ha livello medio dei rivali,
sponsor settimanale, montepremi, costo di trasferta e prezzo dei biglietti crescenti (§6, §9).

---

## 2. Architettura e struttura del repository

```text
main.py          entry point: GameController(auto_create=False) + MainWindow
models/          LOGICA DI GIOCO, nessun import di PyQt6 (regola vincolante, oggi violata solo da race_export.py)
  entities.py      GameState, Athlete, Coach, Relay, RivalClub, EventDefinition, enum, molte costanti
  generator.py     generazione atleti, rivali, allenatori, staff, dilemmi, scouting
  simulation.py    allenamento, motore gara, staffette, finanze, tick `advance_week`
  database.py      SQLite: schema, migrazioni, backup, salvataggio/caricamento, elenco slot
  race_export.py   esporta una gara in un DB per Godot      bibs.py   numeri di pettorale
controllers/
  game_controller.py   GameController (QObject con segnali Qt): tutte le azioni del giocatore, il tick, il caricamento
views/           interfaccia PyQt6 (nessuna logica che decida esiti)
  start_screen.py main_window.py tabs.py dialogs.py athlete_dialog.py styles.py (tema scuro QSS) results_board.py
  race_viewer.py race_3d.py field_3d.py (gare in diretta)     godot_launcher.py (lancio di Godot)
godot_viewer/    progetto Godot 4.3+ separato (solo vista), legge risultati da SQLite
tests/           test_game.py (84 test, usa PyQt6)   test_migrations.py (21 test, senza Qt)
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
(`news_log`, max 70), le **transazioni** (libro mastro, max 400), la **storia delle gare** (`competition_history`, cresce senza limite),
i **rivali** (`rivals`), la classifica di lega (`league_table`), la storia delle stagioni (`season_history`), il dilemma pendente
(`pending_dilemma`), impianti (`gym_level` 0-5, `stand_seats`), `fidelity` (fedeltà sponsor), `scouting_points_used`,
`coach_hired_week`, `bankrupt`.

### 3.2 `Athlete`

Identità: `id`, `name`, `age`, `gender` (M/F), `nationality` (70% Italia), `height_cm`, `weight_kg`.
Caratteristiche (0-100): `speed`, `stamina`, `strength`, `technique`, `resilience`; stato: `form`, `fatigue`, `sleep_quality`, `nutrition`;
`potential` (tetto di crescita); `specialty` (**Velocità, Mezzofondo, Salti, Lanci**); `personality` (**Perfezionista, Impulsivo, Leader,
Resiliente**); `training_focus` (**Resistenza, Potenza Esplosiva, Tecnica, Riposo & Recupero**); `periodization`
(**Prep. Generale, Prep. Specifica, Gara (Picco), Scarico (Tapering)**); `weekly_wage`, `injured_weeks`, `is_youth_prospect`,
`in_youth_squad`, `fans`, `coach_id`, `personal_best` (per evento), `doping_boost_weeks`.
`overall` è una media pesata delle caratteristiche con pesi diversi per specialità. L'altezza e il peso concorrono al punteggio in gara
(§5.3). Il picco di età dipende dalla specialità (`peak_age_range`: Velocità 20-27, Salti 20-28, Mezzofondo 21-30, Lanci 23-32).

### 3.3 Altre entità

- `EventDefinition`: evento (nome, tipo corsa/concorso, sensibile al vento, record del mondo, ancore dei livelli). Eventi: `100m`, `400m`,
  `1500m`, `Salto in Lungo`, `Getto del Peso`; `RelayDefinition`: `4x100m`, `4x400m`.
- `Coach`: 4 abilità 1-100 (Velocità, Resistenza, Forza, Tecnica), tier, tipo (specializzato su una disciplina o del vivaio).
- `Relay`: 4 frazionisti in ordine + riserva, `harmony` (affiatamento 0-100), `last_change_week`.
- `RivalClub`/`RivalAthlete`: società avversarie persistenti (livello, ambizione, storia del livello, un atleta per gara).
- `StaffMember`: Fisioterapista, Medico Sportivo, Preparatore Mentale (attivabili/disattivabili).
- `CompetitionSummary` / `EventResult` / `EventStanding`: risultato di un meeting (per evento: classifica, misure, punti, vento, meteo).
- `EthicalDilemma`, `SeasonObjective`, `SeasonEndResult`, `Transaction`.

---

## 4. Il ciclo di gioco: la settimana

Il giocatore, durante la settimana, **prepara**: imposta allenamento e periodizzazione di ogni atleta, convoca gli atleti per gara,
sceglie l'atteggiamento, compone le staffette, spende soldi (staff, impianti, scouting, mercato). Poi preme «Avanza settimana»
(`GameController.advance_week` → `models.simulation.advance_week`). Il tick, in ordine (dettagli e numeri di riga in `TICK.md`):

1. Se la settimana è **di gara** (`settimana % 4 == 0`): simula il meeting (meteo, vento, punteggi di tutti, classifica, premi, record, staffette, punti squadra, biglietti/trasferta).
2. Per ogni atleta: allenamento settimanale (doping/infortunio/recupero/crescita/fatica/forma/declino/rischio infortunio).
3. Note di infortunio; eventuale scandalo doping (reputazione −25, prestigio −45).
4. Finanze settimanali: entrate (sponsor, individuali, quote) e uscite (rimborsi spese atleti, staff, allenatori, palestra); libro mastro.
5. Se `budget < 0`: interessi 5% a settimana; sotto −20.000 la società **fallisce** (`bankrupt`: blocca i tick successivi).
6. Decadimento abilità degli allenatori; affiatamento staffette; **evoluzione dei rivali**; usura della pista.
7. Fedeltà sponsor +2; azzera i punti scouting; **`week += 1`**.
8. Solo Carriera, ogni 12 settimane: cambio **fase** (Outdoor → Cross → Indoor). A fine ciclo (36 sett.): verdetto di lega, nuova stagione,
   azzeramento classifica di lega, +1 anno a tutti gli atleti, rinnovo dei rivali.
9. Promozione automatica dal vivaio a 18 anni; notizie; valutazione obiettivi; possibile **dilemma etico**; troncamento dei registri.

Dopo il tick il controller azzera in memoria i risultati dello scouting e il pool del mercato, **salva** su SQLite ed emette i segnali:
se c'è una gara si aprono la gara in diretta e i risultati; a fine stagione la finestra di fine stagione; se è scattato un dilemma, la sua finestra.

> Stato dei lotti sul tick: il lotto 1.3 («il tick non lascia stato a metà», snapshot e ripristino su eccezione) è **proposto ma non
> implementato**. Oggi un'eccezione nel tick lascia lo stato in memoria a metà e, essendo lanciata da uno slot Qt, chiude l'app (exit 134).

---

## 5. Regole di gioco per componente

### 5.1 Calendario, stagioni, casa/trasferta

- Gara ogni 4 settimane. **Casa/trasferta alternate**: in casa non paghi la trasferta e incassi i biglietti (spettatori limitati dalla capienza,
  funzione di prestigio, categoria, reputazione, pioggia); in trasferta paghi il costo di trasferta. La pista subisce −3% di condizione in un meeting in casa.
- Fasi in Carriera: Outdoor (sett. 1-12), Cross (13-24), Indoor (25-36). **Le discipline non cambiano con la fase** (sono sempre le 5): le differenze reali sono
  che in Cross non si corrono staffette, in Indoor non c'è la 4x100m, il meteo indoor è sempre Sereno e il vento 0. Non esiste una gara di corsa campestre
  né un 60m indoor (si corre il 100m).
- Meteo (Sereno, Ventoso, Pioggia, Caldo): Pioggia −1,8 e Caldo −0,8 punti di punteggio; il vento dipende dal meteo.

### 5.2 Allenamento, fatica, forma, infortuni

- Ogni atleta ha un **focus** (Resistenza, Potenza Esplosiva, Tecnica, Riposo) e una **fase di periodizzazione**. Ogni settimana, in base al focus, c'è una probabilità di
  +1 (talvolta +2) alla caratteristica allenata, moltiplicata per: età (sotto il picco ×1,30, nel picco ×1,00, oltre ×0,65), allenatore adatto
  (senza allenatore ×0,6), personalità (Perfezionista ×1,15), periodizzazione, palestra (+6% per livello), vivaio (×1,5) e margine rispetto al `potential`.
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
   66 vincitore regionale, 70 nazionale, 84 internazionale. 100m, 400m, 1500m, lungo e peso sono tarati su dati FIDAL/Assoluti 2025 (provinciale e media regionale di lungo e peso sono stime);
   le staffette no. Il tetto è il record del mondo, applicato dopo il vento.
3. **Vento**: solo 100m (−0,055 s per m/s) e Salto in Lungo (+0,08 m per m/s). Oltre **+2,0 m/s** la prestazione non è omologata: non aggiorna PB, record sociale né momenti storici,
   ma piazzamento, punti squadra, premi, prestigio e fan restano.
4. **Atteggiamento** per ogni gara: Prudente (−2 punti, poca fatica, rischio infortunio 0,5%), Normale, Aggressivo (+2,5 punti, tanta fatica, rischio 5%, variabilità extra).
   Il rischio di ritiro in gara aumenta con la fatica ed è ridotto da medico (×0,55) e Resiliente (×0,7). Un ritirato (DNF) arriva ultimo, forma −15, 1-3 settimane di stop.
5. Ogni società schiera **un solo atleta per evento e divisione**. Gli avversari sono i rivali (un atleta per società per gara, 7 società per categoria, quindi 8 partecipanti).
6. Premi in denaro per i primi 4 (1,00 / 0,60 / 0,35 / 0,15 del montepremi della categoria), prestigio per piazzamento (+5 se record), fan (più i piazzamenti alti, +5 per PB, +10 per record).

### 5.4 Classifiche: meeting, lega, promozioni

- **Punti squadra** per posizione: 1° = 8 … 8° = 1. Sommati per meeting danno la classifica del meeting (le prime 3 società prendono prestigio extra: 10/6/3) e una **classifica di lega
  cumulativa**, azzerata a ogni stagione. Una gara senza convocato regala punti ai rivali.
- **Verdetto a fine stagione** (Carriera, dopo 36 settimane): le prime **2** salgono di categoria, l'**ultima** scende; in Internazionale il 1° posto è il **titolo**. A pari punti
  l'ordine è alfabetico (difetto noto: decide il nome della società, vedi §13). Il prestigio resta e fa crescere il pubblico dei meeting in casa.
- Il Prototipo non ha promozioni né retrocessioni.

### 5.5 Staffette (4x100m, 4x400m)

4 frazionisti in ordine + 1 riserva, per divisione; ogni atleta può stare in una sola staffetta; la 4x400m si corre solo in Carriera (serve la gara dei 400m). Il tempo dipende dai
frazionisti (l'ultima frazione pesa 0,28 contro 0,24) e dall'**affiatamento** (E … A++, scala interna 0-100, parte da 30). L'affiatamento cresce ogni settimana con titolari sani e di più se si gareggia;
cala se mancano. Con affiatamento basso c'è rischio di **squalifica** per cambio fuori zona. Riordinare è gratis; sostituire un titolare sano costa il 25% dell'affiatamento
(una volta ogni 4 settimane); un infortunato è sostituito dalla riserva (che subentra con affiatamento −15 e +3% di rischio DQ). Le staffette contano per i punti squadra e hanno record propri;
non consumano forma, non danno fan.

### 5.6 Rivali

7 società per categoria e divisione, ciascuna con un atleta per gara (nome, età, livello, PB). Ogni settimana evolvono (under 24 crescono, 24-27 poco, 28-29 deriva nulla con rumore, dal 30 calano).
A inizio stagione invecchiano, i veterani si ritirano (a 33 sempre, da 31 il 30%), arrivano reclute di 18-22 anni, ogni anno un po' più forti. Hanno un'**ambizione**: le società che batti diventano più
ambiziose e crescono più in fretta; quelle che ti staccano molto si rilassano. La scheda *Rivali* mostra livello, tendenza e confronto gara per gara.

### 5.7 Economia

Entrate settimanali: **sponsor società** (funzione di categoria, reputazione e fedeltà), **sponsor individuali** (fan/4 per atleta maggiorenne in prima squadra), **quote tesserati** (450 fisse).
Uscite settimanali: **rimborsi spese atleti** (prima squadra, infortunati inclusi, mai rivisti), **staff** (Fisioterapista 300, Medico 340, Preparatore Mentale 220), **stipendi allenatori**
(`40 + 2,2 × Σ max(0, abilità−40)`), **gestione palestra** (40 × livello). Per gara: premi e biglietti (casa) o trasferta (fuori). Una tantum: ingaggi (atleti, allenatori), scouting, recupero, pista, ampliamenti.
**Debito**: con saldo negativo interessi del 5% a settimana; sotto −20.000 fallimento. Misura chiave: all'avvio la società perde soldi ogni settimana (Carriera ≈ −4.432, Prototipo ≈ −2.291), quindi il giocatore
deve tagliare/gestire (difetto/decisione di bilanciamento aperta, `QUESTIONS.md` 3). Cifre complete: `BALANCE.md`.

### 5.8 Vivaio e scouting

Il **vivaio** ospita fino a 8 ragazzi di 14-17 anni che non gareggiano e non costano rimborsi spese, ma si allenano ×1,5. A 18 anni passano da soli in prima squadra (in Carriera, perché l'età cresce solo al cambio stagione);
prima si possono promuovere a mano. Ogni settimana si hanno **8 punti scouting**: una ricerca costa 2 punti (+1 per filtro: disciplina, potenziale ≥85) e un costo in denaro crescente con i punti già spesi.
I ragazzi segnalati e non presi se ne vanno a fine settimana.

### 5.9 Mercato (agenti liberi)

Pool di 5 candidati a settimana (4 studenti di 15-17 anni + 1 adulto): si può solo **acquistare** (ingaggio una tantum) o **svincolare**. Nessun incasso dalle cessioni. Ogni acquisto/cessione abbassa la **fedeltà sponsor**
(−6 per under 21, −12 altrimenti; −8 per la cessione), che riduce lo sponsor della società e si recupera di +2 a settimana.

### 5.10 Allenatori e staff

Ogni **allenatore** ha 4 abilità (1-100). L'atleta che allena una qualità cresce tanto più quanto l'allenatore è bravo in quella; senza allenatore adatto ×0,6. Massimo 6 specializzati (una disciplina) e 2 del vivaio (solo ragazzi 14-17).
Si assume scegliendo abilità principale, secondaria e livello di ingaggio (1500 × livello, 1-5, una tantum, più abilità = stipendio più alto), uno a settimana. Oltre 6 atleti a testa l'effetto cala; le abilità decadono lentamente (10%/sett. di −1 a un'abilità sopra 25).
Lo **staff** (Fisioterapista, Medico Sportivo, Preparatore Mentale) si attiva/disattiva e dà effetti su fatica, guarigione, rischio infortunio e forma.

### 5.11 Impianti

**Palestra** livelli 0-5 (+6% di crescita in allenamento per livello, costa 2500 × (livello+1) da ampliare e 40 × livello a settimana). **Tribune** da ampliare di 500 posti alla volta fino a 20.000 (nessun costo di gestione).
La condizione della **pista** cala ogni settimana e ogni meeting in casa, e influenza il punteggio.

### 5.12 Fan e sponsor

Gli atleti guadagnano **fan** con piazzamenti, PB e record (i fan non calano mai: difetto di bilanciamento noto). I maggiorenni in prima squadra producono sponsor personali settimanali.

### 5.13 Dilemmi etici e obiettivi

- **Dilemmi**: nelle settimane 3 e 7 sempre, altrove 22% di probabilità; due tipi (doping / giovane promettente). Si accettano o rifiutano con effetti su soldi, reputazione, prestigio, forma. Chiudere la finestra senza scegliere
  lascia il dilemma pendente e **blocca per sempre i successivi** (difetto noto).
- **Obiettivi stagionali**: creati alla nuova partita (es. bilancio positivo, traguardo storico, promozione); non vengono rinnovati a fine stagione (difetto noto).

### 5.14 Record e PB

Per atleta e per evento si tiene il **PB** (solo con vento legale); la società ha **record sociali** per evento e divisione, più un albo e una scheda «Albo & Record». Si segnano «momenti storici» (misure oltre una soglia storica per evento).

---

## 6. Categorie: parametri principali

| Categoria | Livello rivali (pt) | Sponsor sett. | Montepremi base | Trasferta | Biglietto |
| --- | ---: | ---: | ---: | ---: | ---: |
| Provinciale | 42 | 600 | 1.200 | 350 | 4 |
| Regionale | 56 | 1.250 | 2.800 | 750 | 6 |
| Nazionale | 70 | 2.500 | 6.000 | 1.500 | 9 |
| Internazionale | 84 | 4.800 | 12.500 | 3.000 | 14 |

---

## 7. Persistenza (SQLite)

- Un file `.db` per slot in `~/.track_field_manager/saves/` (più un `savegame.db` legacy in `~/.track_field_manager/`). Tabelle: `game_state` (riga unica, molti campi JSON), `athletes`, `coaches`, `staff`, `transactions`, `competition_history`.
  `save_game` fa DELETE+INSERT in una transazione.
- **Schema `SCHEMA_VERSION = 9`**, `PRAGMA user_version`. Ogni nuova colonna: voce in `MIGRATIONS` (con `DEFAULT`) *e* nella `CREATE TABLE`.
- **Apertura sicura** (lotti 1.1/1.2): file assente o di 0 byte → DB nuovo, creato in una transazione. Versione corrente → apertura in sola lettura, nessuna scrittura. Versione migrabile (v2…v8) →
  **backup verificato** con `Connection.backup()` in `saves/backups/<slot>.v{N}.{timestamp}.db.bak` (sempre nuovo, 3 più recenti per slot, potati solo dopo una migrazione riuscita), poi **una sola transazione**
  (`BEGIN IMMEDIATE` … `COMMIT`, ALTER + creazione tabelle + `user_version` insieme, rollback su errore). Versione non supportata (più recente, v0/v1 con dati, file non vuoto senza tabelle) →
  `UnsupportedSaveVersion` **prima di scrivere**: niente DROP, file intatto. Ripristino da backup: manuale (copiare il `.db.bak` come `.db`).
- `GameController.load_save_slot`/`load_game` non fanno salire le eccezioni (in PyQt6 un'eccezione che esce da uno slot termina il processo): ritornano `False`, riempiono `last_load_error` (messaggio + percorso del backup + traceback)
  e la schermata iniziale mostra un `QMessageBox.warning` con il traceback nei dettagli.
- **Elenco slot**: `read_save_summary` (sola lettura) elenca anche gli slot non apribili («versione più recente», «non compatibile», «danneggiato») con i soli metadati affidabili; «Continua» usa il più recente slot apribile.
- I campi mancanti dei vecchi salvataggi si riempiono al caricamento in modo deterministico (es. corpo degli atleti, seed = id atleta).
- **Non salvati**: stato dell'RNG, risultati dello scouting e pool del mercato (solo in memoria: ricaricare «ritira i dadi»).

---

## 8. Interfaccia (PyQt6, tema scuro)

- **Schermata iniziale** (`StartScreen`): hero, scheda «Continua ultima partita», nuova società (nome, modalità, provincia di partenza), tabella dei salvataggi (carica, elimina, doppio clic).
- **Finestra principale** (`MainWindow`): barra laterale con tre sezioni e nove pagine:
  GESTIONE → *Dashboard*, *Rosa & Allenamenti*, *Vivaio & Osservatori*; COMPETIZIONI → *Calendario & Gare*, *Staffette*, *Rivali*; SOCIETÀ → *Staff & Impianto*, *Finanze*, *Albo & Record*.
  In alto un HUD con settimana/budget/prestigio e il pulsante **Avanza settimana**; menu per salvare/caricare.
- **Dialoghi**: Scheda Atleta (PANORAMICA, ALLENAMENTO, COMPETIZIONI), Mercato/Recluta atleta, Assumi Allenatore, Nuova Partita, Dilemma Etico, Fine Stagione, Risultati gara (tabellone con pettorali).
- La UI è piena di piccole regole duplicate (soglie fatica, zona promozione/retrocessione) che andrebbero lette dal modello: vedi `AUDIT.md` Q13.

---

## 9. Gare in diretta

Dopo il tick di una settimana di gara si apre la **gara in diretta** (`RaceViewerDialog`) prima dei risultati. Mette in scena un `CompetitionSummary` già calcolato; non cambia mai tempi, ordine o misure
(ogni atleta taglia il traguardo esattamente al suo tempo ufficiale, c'è un test).

- **Modello di movimento** (funzioni pure e testate): `curve_progress`, `position_fraction`, `reaction_time` (0,12-0,22 s, incluso nel tempo ufficiale). Curva di velocità per gara (100m, 400m, 1500m, staffetta).
- **Viste PyQt**: 2D laterale (`TrackRaceWidget`) e 3D software con `QPainter` (`Track3DWidget`, senza OpenGL: camera a foro stenopeico, `clip_near`, antialiasing spento per le grandi superfici). Il 3D copre solo le corse in pista.
  Concorsi (lungo, peso): scena 2D + tabellone; le singole prove sono ricavate dal risultato finale con un generatore deterministico (`generate_attempts`).
- **Controlli**: pausa, velocità 1×/2×/4×, vista 2D/3D, «Salta alla fine», «Prossima gara», «Vai ai risultati». Ralenti dell'arrivo.
- **Visualizzatore Godot** (`godot_viewer/`, Godot 4.3+/GDScript, **opzionale**, separato dall'app): stile «diretta TV» 2010 per 100m, 400m, 1500m, 4x100m, 4x400m, Lungo e Peso. Legge da SQLite
  (`godot_viewer/data/schema.sql` è l'unica fonte dello schema; `models/race_export.py` esporta) i risultati già calcolati. MVC interno: Model `DatabaseManager.gd` (sola lettura), Controller `RaceController.gd`, View 3D (`Stadium.tscn`, `BroadcastCameras`, `RunnerView`)
  e View 2D (`HUD.tscn`). Contiene: pista ovale con geometria reale (`TrackGeometry.gd`), regia automatica delle camere legata allo stato della gara, posa ai blocchi con IK, personaggi con scheletro e animazioni CC0 (Quaternius), cadenza/ampiezza di passo per evento (`StrideModel.gd`),
  atleti ritirati (DNF) e staffette squalificate (DQ), pettorali stampati sulla canotta (numero unico per meeting, assegnato da `models/bibs.py`), cartelloni con sponsor di fantasia, tribune, fotografi e giudici come persone vere, ralenti dell'arrivo, classifica finale.
  Il gioco lo lancia con `QProcess` (`views/godot_launcher.py`) e **ripiega sulla vista PyQt interna** se Godot, il progetto o il plugin `godot-sqlite` mancano; `TEF_NO_GODOT=1` lo disattiva (usato nei test). Non copre gli altri concorsi né più di 8 corsie.
- Le viste PyQt interne **non** mostrano i pettorali.

---

## 10. Determinismo e RNG

La simulazione riceve un `rng` iniettabile (`random.Random`), quindi a parità di stato e di RNG gli esiti sono identici. **Oggi però** il controller usa un `random.Random()` non seminato e lo stato dell'RNG non è salvato: stesso salvataggio → esiti diversi.
Anche le azioni UI (scouting, mercato) consumano l'RNG del controller. Regola di progetto: nessun `hash()` su stringhe per ricavare seed (è salato per processo; c'è ancora un caso in `views/dialogs.py:55`). Lotti 2.1/2.2 di `PLAN.md`.

---

## 11. Test e comandi

```bash
.venv/bin/pip install -r requirements.txt                                   # PyQt6, pyinstaller
.venv/bin/python main.py                                                    # avvia l'app (o ./TrackAndFieldManager.sh)
QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests -v # 105 test, ~3,6 s
PYTHONPATH=. python3 -m unittest tests.test_migrations -v                    # 21 test, SENZA PyQt6
```

`python` non è nel PATH dell'ambiente di sviluppo (si usa `.venv/bin/python`, Python 3.14.4). I test GUI usano `QT_QPA_PLATFORM=offscreen` e **non chiamano mai `exec()` di dialoghi modali** (bloccherebbero per sempre).
`test_migrations.py` genera fixture programmaticamente (una per ogni versione v2…v8), verifica migrazione, backup, rollback su fallimento a metà (E1), rifiuto delle versioni ignote (E2).
`test_game.py` copre simulazione, curve di movimento, viste in ogni stato (intercetta eccezioni di disegno, **non** giudica l'aspetto), migrazioni dei vecchi salvataggi e il click su uno slot non supportato (in un processo a parte: fallisce se l'app muore).

---

## 12. Piano di lavoro (stato)

`PLAN.md` divide l'intervento in lotti piccoli: 1 sicurezza dei salvataggi → 2 determinismo → 3 ambiguità di regole → 4 economia → 5 refactor → 6 UI.

- ✅ **1.1** migrazione transazionale con backup, ✅ **1.2** rifiuto delle versioni sconosciute (fatti).
- ⏳ **1.3** il tick non lascia stato a metà (snapshot e ripristino su eccezione, riepilogo del tick fallito): proposto, in attesa di decisione dell'utente su 5 punti.
- Poi: 1.4 protezione dal doppio click sul tick; 2.x RNG seminato/salvato; 3.x regole (spareggio, dilemma chiuso senza scelta, debito azzerato dai dilemmi…); 4.x economia; 5.x (modulo di bilanciamento `models/balance.py`, test di simulazione senza Qt, `race_export` senza dipendere da `views/`); 6.x UI.

---

## 13. Difetti noti e decisioni aperte (sintesi di `AUDIT.md` e `QUESTIONS.md`)

| Tema | Sintesi |
| --- | --- |
| Economia (R3) | L'avvio è in perdita netta ogni settimana: in autopilota bancarotta alla sett. 14. Decisione di design aperta (QUESTIONS 3). |
| Dilemma bloccato (R4) | Chiudere la finestra senza scegliere lascia il dilemma pendente e impedisce i successivi. |
| RNG (R5) | Non seminato né salvato; si può ricaricare per ritirare i dadi. |
| Debito azzerato (R7) | Rifiutare un dilemma porta a 0 un bilancio negativo (`max(0, budget − 600)`). |
| Doppio click (R8) | Nessuna protezione sul tick (dedotto, non provato con mouse reale). |
| Spareggio (R9) | Alfabetico: il giocatore può scegliere il nome del club per vincere tutti gli spareggi. |
| Fan e sponsor (R10) | Illimitati, non calano mai. |
| Obiettivi (R11/R12) | Mai rinnovati; l'obiettivo «traguardo storico» femminile usa la soglia maschile. |
| Validazione (R13) | Il controller non impedisce lo stesso atleta in più gare né la divisione sbagliata. |
| Stipendi (R14) | Mai rivisti dopo la creazione; nessun incasso da cessioni; nessun costo tribune. |
| Costanti (R15) | Sparse e duplicate (es. 12/36 settimane, soglia fatica 75): manca un modulo di bilanciamento. |
| Prototipo (R16) | Non finisce; l'età cresce solo in Carriera. |
| Mercato (R18) | Pool e scouting solo in memoria. |
| `hash()` (R17) | Salato per processo nella fascia del potenziale mostrata nel mercato. |
| Tick (T1-T11) | Dettaglio dei punti d'ordine sospetti in `TICK.md` §E. |

Le decisioni di design aperte (15 domande, es. «che cosa è il fallimento», «un atleta può correre più gare nello stesso meeting», «dove vivono le costanti di bilanciamento») sono in `docs/QUESTIONS.md` e **spettano all'utente**.

---

## 14. Per chi lavora sul progetto (anche un altro assistente)

- Rispondere e scrivere documenti in **italiano**; nomi di variabili e codice in inglese.
- Prima di scrivere codice **esplicitare le assunzioni** e, per modifiche non banali, proporre l'approccio e aspettare l'OK.
- Dichiarare con franchezza ciò che non si è potuto verificare (es. «non ho provato l'app con il mouse, solo test offscreen e screenshot»).
- Non cambiare esiti di gara nelle viste; non introdurre comandi interattivi in gara; non toccare `MIGRATIONS`/`SCHEMA_VERSION` senza migrazione e test; non fare refactor o «già che ci sono».
- Un difetto trovato per strada si annota in `docs/AUDIT.md`; una scelta di design si chiede all'utente (`docs/QUESTIONS.md`).
- Commit in italiano e descrittivi; sviluppo sul branch indicato; non aprire PR se non richiesto.
