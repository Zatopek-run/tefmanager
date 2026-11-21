# Piano di Lavoro: Miglioramenti Gameplay Track & Field Manager

**Data:** 2026-11-20  
**Branch suggerito:** `feature/gameplay-improvements`  
**Obiettivo:** Trasformare il gioco da prototipo funzionante a manageriale profondo e avvincente, ispirandosi a Football Manager, Motorsport Manager e Pro Cycling Manager.

---

> **Aggiornamento 2026-11-20 — fuori dai lotti A-G (richiesta dell'utente): avvio della Carriera senza atleti** (QUESTIONS Q32, schema v21). Rosa e vivaio vuoti all'avvio, **Preparazione** di 8 settimane senza gare a inizio di ogni stagione (solo Carriere nuove; `GameState.prep_weeks`, 0 nei salvataggi esistenti), non iscrizione ai meeting con la Prima Squadra vuota, obiettivi del Board di **fondazione** nella stagione 1 e raccordo nella stagione 2, aiuti a schermo e messaggio iniziale. Budget invariato. Fatto, cifre provvisorie. Non cambia l'ordine dei lotti: restano da fare E-G e C.1b.

---

## 📋 Principi Guida (ereditati da CLAUDE.md)

1. **MVC rigoroso:** `models/` non importa PyQt6. Le viste non decidono esiti.
2. **Esiti gara immutabili:** La simulazione decide tutto, le viste mettono in scena.
3. **Test obbligatori:** Ogni feature ha test unitari (senza Qt dove possibile).
4. **Lotti piccoli:** Modifiche incrementali, commit descrittivi in italiano.
5. **Niente refactor nascosti:** Un difetto trovato si annota in AUDIT.md.
6. **Migrazioni DB:** Backup + transazione + test, mai DROP su versioni sconosciute.
7. **Determinismo:** RNG iniettabile e seminato (quando implementato).

---

## 🎯 Obiettivi del Piano

### Obiettivo Primario
Aumentare la **profondità decisionale** e la **narrativa emergente** per rendere il gioco avvincente su multiple stagioni.

### Obiettivi Secondari
- Risolvere i difetti critici di bilanciamento (economia in perdita)
- Migliorare l'UI/UX per ridurre il carico cognitivo
- Aggiungere sistemi di progressione a lungo termine (ranking, carriera)
- Creare momenti memorabili (record, rivalità, conferenze stampa)

---

## 📦 Lotti di Lavoro

### **LOTTO A: Fondamenta e Bugfix Critici** (2 settimane)
**Priorità:** 🔴 CRITICA  
**Dipendenze:** Nessuna  
**Obiettivo:** Risolvere i difetti che bloccano il gameplay.

#### A.1 Economia: Bilanciamento Entrate/Uscite
**Problema:** La società perde ~4.400€/settimana in Carriera (R3).  
**Soluzione:**
- Aumentare sponsor società del 40% (Provinciale 840€, Regionale 1.750€, ecc.)
- Aumentare premi gara del 25%
- Ridurre rimborsi spese atleti del 20%
- Aggiungere bonus promozione (+5.000€ una tantum)

**File da modificare:**
- `models/entities.py`: costanti sponsor, premi, rimborsi
- `models/simulation.py`: logica finanziaria
- `docs/BALANCE.md`: aggiornare cifre

**Test richiesti:**
- `test_economy.py`: verificare che una società media chiuda in pareggio dopo 12 settimane
- Test manuale: avviare Carriera, verificare che dopo 36 settimane il bilancio sia positivo o in leggero deficit (<1.000€)

**Stima:** 3 giorni

---

#### A.2 Spareggio Non-Alfabetico
**Problema:** A pari punti, vince chi ha il nome alfabetico (R9).  
**Soluzione:**
- Implementare spareggio basato su: (1) punti squadra cumulativi, (2) miglior piazzamento singolo, (3) sorteggio deterministico (seed = id società)

**File da modificare:**
- `models/simulation.py`: funzione `break_tie()`
- `models/entities.py`: aggiungere `tiebreaker_points` a RivalClub

**Test richiesti:**
- `test_tiebreaker.py`: verificare che due società a pari punti con piazzamenti diversi vincano correttamente
- Test determinismo: stesso seed → stesso vincitore

**Stima:** 1 giorno

---

#### A.3 RNG Seminato e Salvato
**Problema:** RNG non seminato, si può ricaricare per ritirare i dadi (R5).  
**Soluzione:**
- Seminare RNG con `seed = hash(game_state_id + season_number)` (non usare `hash()` di Python, usare `hashlib`)
- Salvare stato RNG in `game_state` (JSON)
- Ripristinare al caricamento

**File da modificare:**
- `models/entities.py`: aggiungere `rng_state` a GameState
- `controllers/game_controller.py`: inizializzare RNG con seed
- `models/database.py`: salvare/caricare rng_state
- `models/simulation.py`: usare RNG dal GameState

**Test richiesti:**
- `test_rng.py`: verificare che due partite con stesso seed producano esiti identici
- Test migrazione: vecchi salvataggi senza rng_state → seed deterministico da id

**Stima:** 2 giorni

---

#### A.4 Dilemma Bloccato
**Problema:** Chiudere la finestra senza scegliere lascia il dilemma pendente (R4).  
**Soluzione:**
- Se la finestra viene chiusa senza scelta, applicare automaticamente l'opzione "rifiuta" (effetti negativi minimi)
- Aggiungere pulsante "Ignora" esplicito nella UI

**File da modificare:**
- `views/dialogs.py`: gestire `closeEvent` di EthicalDilemmaDialog
- `controllers/game_controller.py`: fallback su rifiuto

**Test richiesti:**
- `test_dilemma.py`: verificare che chiudere la finestra applichi il rifiuto

**Stima:** 0.5 giorni

---

#### A.5 Protezione Doppio Click sul Tick
**Problema:** Nessun protezione sul pulsante "Avanza settimana" (R8).  
**Soluzione:**
- Disabilitare il pulsante durante l'esecuzione del tick
- Riabilitare al termine (anche in caso di eccezione)

**File da modificare:**
- `views/main_window.py`: disabilitare/riabilitare pulsante

**Test richiesti:**
- Test manuale: cliccare rapidamente, verificare che il tick non si esegua due volte

**Stima:** 0.5 giorni

---

### **LOTTO B: Core Gameplay - Strategia di Gara** (3 settimane)
**Priorità:** 🔴 ALTA  
**Dipendenze:** Lotto A  
**Obiettivo:** Aggiungere profondità tattica alle gare, ispirandosi a FM.

#### B.1 Piani Gara per Discipline di Fondo (800m, 1500m)
**Descrizione:**
Ogni atleta ha un piano gara con:
- **Ritmo iniziale:** Lento (-2 punti, conserva energia), Medio (0), Veloce (+3 punti, fatica +10)
- **Scatto finale:** Ultimo giro (+4 punti, fatica +15), Ultimi 200m (+2 punti, fatica +8), Nessuno (0)
- **Gestione energia:** Conservativa (fatica -20%), Bilanciata (0), Aggressiva (fatica +30%)

**File da modificare:**
- `models/entities.py`: aggiungere `RaceStrategy` (dict per evento)
- `models/simulation.py`: applicare modificatori al punteggio in base alla strategia
- `views/athlete_dialog.py`: tab "Strategia" con combo box
- `controllers/game_controller.py`: salvare/caricare strategia

**Test richiesti:**
- `test_race_strategy.py`: verificare che un piano "Veloce + Ultimo giro" dia +7 punti ma +23 fatica
- Test UI: verificare che la strategia sia salvata e caricata correttamente

**Stima:** 5 giorni

---

#### B.2 Strategia per Concorsi (Lungo, Peso)
**Descrizione:**
Ogni atleta ha:
- **Altezza/peso iniziale:** Conservativo (parte basso, +2 tecnica), Aggressivo (parte alto, -2 tecnica)
- **Rischio ultimo tentativo:** Sicuro (0), Bilanciato (+1 tecnica, +5% rischio fallo), Aggressivo (+3 tecnica, +15% rischio fallo)

**File da modificare:**
- `models/entities.py`: estendere `RaceStrategy` per concorsi
- `models/simulation.py`: applicare modificatori a tecnica e rischio
- `views/athlete_dialog.py`: UI per strategia concorsi

**Test richiesti:**
- `test_field_strategy.py`: verificare modificatori tecnica/rischio

**Stima:** 2 giorni

---

#### B.3 Strategia Staffetta
**Descrizione:**
- **Cambio:** Conservativo (-1 punto, -10% rischio DQ), Normale (0), Aggressivo (+2 punti, +15% rischio DQ)

**File da modificare:**
- `models/entities.py`: `relay_strategy` per staffetta
- `models/simulation.py`: applicare a rischio DQ e punteggio
- `views/tabs.py`: UI nella scheda staffette

**Test richiesti:**
- `test_relay_strategy.py`: verificare rischio DQ

**Stima:** 1 giorno

---

### **LOTTO C: Progressione e Carriera** (3 settimane)
**Priorità:** 🔴 ALTA  
**Dipendenze:** Lotto A  
**Obiettivo:** Dare senso alla carriera multi-stagione.

#### C.1 Ranking Individuale e Società
**Descrizione:**
- **Ranking atleta:** Punti World Athletics basati su piazzamenti (1° = 100pt, 2° = 80pt, ecc.)
- **Ranking società:** Somma punti atleti, influenza inviti Diamond League
- **Top 100 mondiale, Top 50 nazionale**

**File da modificare:**
- `models/entities.py`: `world_ranking_points` in Athlete, `club_ranking` in GameState
- `models/simulation.py`: calcolare punti dopo ogni gara
- `views/tabs.py`: tab "Ranking" nella dashboard
- `views/athlete_dialog.py`: mostrare ranking nella scheda

**Test richiesti:**
- `test_ranking.py`: verificare calcolo punti e aggiornamento classifica

**Stima:** 4 giorni

---

#### C.2 Obiettivi del Board (Board Expectations)
**Descrizione:**
A inizio stagione, il board dà obiettivi:
- **Classifica:** "Top 3 in lega" (difficoltà basata su categoria)
- **Bilancio:** "Bilancio positivo"
- **Record:** "Almeno 2 record sociali"
- **Risultato:** Se fallisci 2 stagioni → esonerato (game over)

**File da modificare:**
- `models/entities.py`: `BoardExpectations` (lista di obiettivi)
- `models/simulation.py`: generare obiettivi a inizio stagione, valutare a fine stagione
- `views/dialogs.py`: finestra obiettivi a inizio stagione
- `controllers/game_controller.py`: gestire esonero

**Test richiesti:**
- `test_board_expectations.py`: verificare generazione e valutazione obiettivi
- Test esonero: 2 fallimenti → game over

**Stima:** 5 giorni

---

#### C.3 Carriera Atleta (Ritiro e Post-Carriera)
**Descrizione:**
- **Ritiro:** A 33-35 anni (probabilità crescente), o prima se infortunato grave
- **Post-carriera:** 10% probabilità di diventare allenatore (abilità basate su PB)

**File da modificare:**
- `models/entities.py`: `is_retired` in Athlete
- `models/simulation.py`: logica ritiro a fine stagione
- `models/generator.py`: generare allenatori da atleti ritirati
- `views/tabs.py`: mostrare atleti ritirati in una lista

**Test richiesti:**
- `test_retirement.py`: verificare ritiro a 33+ anni
- Test post-carriera: atleta ritirato → 10% diventa allenatore

**Stima:** 3 giorni

---

### **LOTTO D: Mercato e Finanze** (3 settimane)
**Priorità:** 🟡 MEDIA  
**Dipendenze:** Lotto A, C  
**Obiettivo:** Aggiungere profondità al mercato e alle finanze.

#### D.1 Agenti con Personalità
**Descrizione:**
Ogni atleta ha un agente con:
- **Nome:** Generato proceduralmente
- **Personalità:** Aggressivo (chiede +20%), Ragionevole (0), Leale (-10%)
- **Relazione:** 0-100 (parte a 50, sale se tratti bene l'atleta, scende se lo tratti male)

**File da modificare:**
- `models/entities.py`: `Agent` entity, `agent_id` in Athlete
- `models/generator.py`: generare agenti
- `models/simulation.py`: trattative influenzate da agente
- `views/dialogs.py`: mostrare agente nella scheda atleta

**Test richiesti:**
- `test_agents.py`: verificare che agente aggressivo chieda di più

**Stima:** 4 giorni

---

#### D.2 Trattative Avanzate
**Descrizione:**
- **Offerta iniziale → Controfferta → Accetto/Rifiuto**
- **Clausole rescissorie:** Paghi 50.000€ per liberare un atleta
- **Bonus per risultati:** "10.000€ se fa record sociale"

**File da modificare:**
- `models/market.py` (nuovo): sistema di trattative
- `models/entities.py`: `transfer_clause` in Athlete
- `views/dialogs.py`: finestra trattativa con offerte/controfferte
- `controllers/game_controller.py`: gestire trattative

**Test richiesti:**
- `test_negotiations.py`: verificare flusso offerta/controfferta
- Test clausola: pagamento → atleta liberato

**Stima:** 5 giorni

---

#### D.3 Finanze Dettagliate
**Descrizione:**
- **Bilancio mensile:** Entrate/uscite dettagliate (non solo settimanali)
- **Sponsor con obiettivi:** "Se non fai top 5, perdi 20% dello sponsor"
- **Merchandising:** Vendita magliette (funzione di fan e prestigio)
- **Diritti TV:** Per meeting in casa (solo Internazionale)

**File da modificare:**
- `models/entities.py`: `monthly_financial_report` in GameState
- `models/simulation.py`: calcolare entrate/uscite mensili
- `views/tabs.py`: tab "Finanze" con grafici mensili

**Test richiesti:**
- `test_finances.py`: verificare calcolo bilancio mensile
- Test sponsor: top 5 → sponsor pieno, fuori top 5 → -20%

**Stima:** 4 giorni

---

### **LOTTO E: Staff e Infrastrutture** (2 settimane)
**Priorità:** 🟡 MEDIA  
**Dipendenze:** Lotto A  
**Obiettivo:** Dare profondità a staff e impianti.

#### E.1 Staff con Attributi
**Descrizione:**
Ogni membro dello staff ha attributi 1-20:
- **Fisioterapista:** Competenza infortuni, Velocità recupero
- **Medico:** Diagnosi, Prevenzione
- **Preparatore mentale:** Motivazione, Gestione pressione

**File da modificare:**
- `models/entities.py`: `attributes` dict in StaffMember
- `models/generator.py`: generare staff con attributi
- `models/simulation.py`: applicare attributi a fatica, infortuni, forma
- `views/tabs.py`: mostrare attributi nella scheda staff

**Test richiesti:**
- `test_staff_attributes.py`: verificare che fisioterapista con alta competenza riduca infortuni

**Stima:** 3 giorni

---

#### E.2 Infrastrutture Avanzate
**Descrizione:**
Nuovi impianti acquistabili:
- **Centro medico:** -15% tempo infortunio (costo 15.000€)
- **Centro analisi video:** +5% tecnica (costo 10.000€)
- **Palestra pesi:** +10% forza (costo 12.000€)
- **Campo altura:** +10% stamina per mezzofondisti (costo 20.000€)

**File da modificare:**
- `models/entities.py`: `facilities` dict in GameState
- `models/simulation.py`: applicare bonus infrastrutture
- `views/tabs.py`: tab "Infrastrutture" con acquisti
- `controllers/game_controller.py`: gestire acquisti

**Test richiesti:**
- `test_facilities.py`: verificare bonus centro medico su infortunio

**Stima:** 4 giorni

---

#### E.3 Giovanili (Academy) Avanzate
**Descrizione:**
- **Academy con livelli:** 1-5 stelle (migliora crescita vivaio)
- **Scout con attributi:** Giudizio potenziale, Giudizio attuale
- **Rete scouting globale:** Mandare scout in Africa, Giamaica, ecc. (bonus giovani forti)

**File da modificare:**
- `models/entities.py`: `academy_level`, `scout_attributes` in GameState
- `models/generator.py`: generare scout con attributi, giovani da reti globali
- `models/simulation.py`: applicare bonus academy a crescita vivaio
- `views/tabs.py`: tab "Vivaio" con upgrade academy e scout

**Test richiesti:**
- `test_academy.py`: verificare che academy 5 stelle dia +50% crescita vivaio
- Test scouting: rete Giamaica → 20% probabilità giovane velocità >80

**Stima:** 5 giorni

---

### **LOTTO F: Narrativa e Immersione** (2 settimane)
**Priorità:** 🟢 BASSA  
**Dipendenze:** Lotto B, C  
**Obiettivo:** Creare momenti memorabili e narrativa emergente.

#### F.1 Notizie Dinamiche
**Descrizione:**
Generatore di notizie basato su eventi:
- "Mario Rossi ha battuto il record sociale!"
- "Tensione nello spogliatoio: Luigi Bianchi è insoddisfatto"
- "La stampa critica la tua gestione"
- "Sei stato nominato 'Allenatore del Mese'"

**File da modificare:**
- `models/narrative.py` (nuovo): generatore notizie
- `models/simulation.py`: chiamare generatore dopo eventi chiave
- `views/tabs.py`: feed notizie nella dashboard

**Test richiesti:**
- `test_narrative.py`: verificare generazione notizie per eventi chiave

**Stima:** 3 giorni

---

#### F.2 Conferenze Stampa
**Descrizione:**
Pre/post gara, il giornalista fa domande:
- "Sei soddisfatto della prestazione?" → Risposte influenzano morale e reputazione
- "Punti sul futuro di Mario Rossi?" → Risposte influenzano relazione atleta

**File da modificare:**
- `models/narrative.py`: generare domande
- `views/dialogs.py`: finestra conferenza stampa con scelte
- `controllers/game_controller.py`: applicare effetti risposte

**Test richiesti:**
- `test_press_conference.py`: verificare effetti risposte su morale/reputazione

**Stima:** 4 giorni

---

#### F.3 Relazioni tra Atleti
**Descrizione:**
- **Amicizie:** Bonus affiatamento staffetta (+10)
- **Rivalità:** Malus affiatamento (-10)
- **Chimica di squadra:** Media relazioni influenza morale generale

**File da modificare:**
- `models/entities.py`: `relationships` dict in Athlete (id_atleta → valore -100/+100)
- `models/simulation.py`: generare relazioni a inizio stagione, influenzano affiatamento
- `views/athlete_dialog.py`: tab "Relazioni" nella scheda atleta

**Test richiesti:**
- `test_relationships.py`: verificare che amicizia dia bonus affiatamento staffetta

**Stima:** 5 giorni

---

#### F.4 Momenti di Gloria
**Descrizione:**
Popup celebrativi per:
- Record del mondo
- Convocazione in nazionale
- Invito Diamond League ✅ fatto 2026-11-21 (C.1b, per società, Q42)
- Atleta dell'anno

**File da modificare:**
- `models/narrative.py`: generare momenti di gloria
- `views/dialogs.py`: finestra popup con animazione
- `controllers/game_controller.py`: mostrare popup dopo eventi

**Test richiesti:**
- Test manuale: verificare che record del mondo mostri popup

**Stima:** 2 giorni

---

### **LOTTO G: UI/UX** (2 settimane)
**Priorità:** 🔴 ALTA  
**Dipendenze:** Lotto B, C  
**Obiettivo:** Migliorare usabilità e riduzione carico cognitivo.

#### G.1 Dashboard Potenziata
**Descrizione:**
- **Grafici performance:** Andamento forma, fatica (ultime 12 settimane)
- **Heat map gare:** Dove atleti sono forti/deboli
- **Timeline stagione:** Prossime gare, scadenze contratti
- **Notifiche visive:** Icona rossa se dilemma, verde se tutto ok

**File da modificare:**
- `views/tabs.py`: ridisegnare DashboardTab con grafici (usare `pyqtgraph` o `matplotlib`)
- `views/widgets.py` (nuovo): widget personalizzati per grafici

**Test richiesti:**
- Test UI offscreen: verificare che dashboard si renderizzi senza errori

**Stima:** 5 giorni

---

#### G.2 Scheda Atleta Migliorata
**Descrizione:**
- **Grafico radar:** Caratteristiche (velocità, stamina, forza, tecnica, resilienza)
- **Storico performance:** Grafico a linee (ultime 10 gare)
- **Confronto:** Con altri atleti stessa disciplina
- **Potenziale:** Barra di progresso verso potenziale

**File da modificare:**
- `views/athlete_dialog.py`: ridisegnare schede con grafici radar e linee
- `views/widgets.py`: widget RadarChart, PerformanceChart

**Test richiesti:**
- Test UI offscreen: verificare che scheda atleta si renderizzi

**Stima:** 4 giorni

---

#### G.3 Schermata Gara Migliorata
**Descrizione:**
- **Tabellone risultati live:** Aggiornato in tempo reale
- **Statistiche live:** Velocità media, distacco
- **Replay ultimi secondi:** (già c'è in Godot, portare anche in PyQt) ✅ fatto 2026-11-21 nella vista 2D e 3D

**File da modificare:**
- `views/race_viewer.py`: aggiungere tabellone live e statistiche
- `views/results_board.py`: migliorare visualizzazione

**Test richiesti:**
- Test UI offscreen: verificare che gara in diretta si renderizzi

**Stima:** 3 giorni

---

## 📊 Cronologia Suggerita

| Settimana | Lotto | Obiettivo |
|-----------|-------|-----------|
| 1-2 | A | Bugfix critici (economia, spareggio, RNG, dilemma, doppio click) |
| 3-5 | B | Strategia di gara (piani 800m/1500m, concorsi, staffetta) |
| 6-8 | C | Progressione (ranking, board expectations, ritiro) |
| 9-11 | D | Mercato (agenti, trattative, finanze dettagliate) |
| 12-13 | E | Staff e infrastrutture (attributi, impianti, academy) |
| 14-15 | F | Narrativa (notizie, conferenze, relazioni, gloria) |
| 16-17 | G | UI/UX (dashboard, scheda atleta, gara) |

**Totale:** 17 settimane (~4 mesi)

---

## ⚠️ Note Tecniche e Considerazioni

### Compatibilità con Salvataggi Esistenti
- **Lotto A:** Nessuna modifica schema DB (solo costanti)
- **Lotto B:** Aggiungere colonne JSON per strategie (migrazione v12)
- **Lotto C:** Aggiungere colonne per ranking, board expectations (migrazione v13)
- **Lotto D:** Nuove tabelle per agenti, trattative (migrazione v14)
- **Lotto E:** Nuove colonne per staff attributes, facilities (migrazione v15)
- **Lotto F:** Nuove tabelle per relazioni, notizie estese (migrazione v16)
- **Lotto G:** Nessuna modifica schema DB

### Test
- Ogni lotto deve avere test unitari (senza Qt dove possibile)
- Test di integrazione per feature complesse (trattative, strategie)
- Test UI con `QT_QPA_PLATFORM=offscreen`
- Test migrazione DB per ogni nuova versione schema

### Dipendenze Esterne
- `pyqtgraph` o `matplotlib` per grafici (aggiungere a `requirements.txt`)
- Nessun altro cambiamento di stack

### Documentazione
- Aggiornare `GAME.md` dopo ogni lotto completato
- Aggiornare `BALANCE.md` dopo Lotto A e D
- Aggiornare `AUDIT.md` con difetti trovati
- Aggiornare `QUESTIONS.md` con nuove decisioni di design

### Rischi
- **Lotto D (Mercato):** Complesso, potrebbe richiedere più tempo del previsto
- **Lotto F (Narrativa):** Rischio di over-engineering, mantenere semplice
- **Lotto G (UI):** Rischio di rompere layout esistenti, testare molto

---

## 🚀 Prossimi Passi

1. **Approvare il piano:** Confermare priorità e cronologia
2. **Creare branch:** `git checkout -b feature/gameplay-improvements`
3. **Iniziare con Lotto A:** Bugfix critici (2 settimane)
4. **Review dopo ogni lotto:** Testare, raccogliere feedback, aggiustare

---

**Nota finale:** Questo piano è ambizioso ma fattibile. La chiave è procedere per lotti piccoli, testare molto, e non aver paura di tagliare feature se il tempo scarseggia. Meglio avere un gioco solido con 3 feature ben fatte che uno instabile con 10 feature a metà.

Buon lavoro! 🏃‍♂️🏃‍♀️