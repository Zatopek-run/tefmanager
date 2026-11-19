# TICK — sequenza reale dell'avanzamento settimana

Fonte: `models/simulation.py:1259-1430` (`advance_week`) chiamata da `controllers/game_controller.py:838-867`.
`r` è l'RNG del tick (`simulation.py:1264`): **l'ordine delle chiamate a `r` è parte del comportamento** (cambiarlo cambia ogni esito a parità di seed).
Settimana «completata» = `completed_week = state.week` (`:1265`); dopo il passo 20 `state.week` è già la nuova.

## A. Controller (prima del tick)

| # | Passo | File:riga |
| ---: | --- | --- |
| C1 | Se `state.bankrupt`: messaggio e **stop** (nessun tick) | `game_controller.py:839-843` |
| C2 | Chiama `advance_week(state, rng=self.rng)` | `game_controller.py:844` |

## B. Modello: `advance_week`

| # | Passo | File:riga | Usa RNG |
| ---: | --- | --- | :-: |
| 1 | Se `is_competition_week` (sett. % 4 == 0): `simulate_competition` (sotto-sequenza in §C) | `:1270-1272`; `entities.py:923-926` | sì |
| 2 | Ruoli staff assunti, presenza di un Leader sano | `:1274-1277` | no |
| 3 | Carichi allenatore `coach_load` calcolati **una volta** | `:1284` | no |
| 4 | Per ogni atleta (`state.athletes`, ordine lista): `apply_weekly_training` (doping/infortunio/recupero/crescita/fatica/forma/declino/rischio infortunio) | `:1285-1295`; `:295-464` | sì |
| 5 | Note infortunio/recupero al `news_log`; scandalo doping: reputazione −25, prestigio −45 | `:1296-1308` | no |
| 6 | `weekly_finances(state)` (calcolata **dopo** il passo 5: lo scandalo riduce già lo sponsor di questa settimana) e `budget += net` | `:1311-1312`; `:1224-1248` | no |
| 7 | Scritture del libro mastro (sponsor, individuali, quote, stipendi, staff, allenatori, palestra) | `:1314-1335` | no |
| 8 | Debito: se `budget < 0`: interesse `ceil(−budget × 0,05)` sottratto; se `budget < −20.000` e non già fallita → `bankrupt = True` | `:1337-1352` | no |
| 9 | Decadimento abilità allenatori: per ciascuno 10% → −1 a una abilità sopra 25 | `:1354-1360` | sì |
| 10 | `_update_relay_harmony` (usa gli infortuni **dopo** il passo 4) | `:1362`; `:240-258` | no |
| 11 | `progress_rivals`: deriva settimanale di tutti i rivali di tutte le categorie; ogni 4 sett. snapshot `history` | `:1363`; `:639-650` | sì |
| 12 | Usura pista `−randint(1,3)` | `:1365-1366` | sì |
| 13 | Fedeltà `+2` (max 100); `scouting_points_used = 0` | `:1368-1370` | no |
| 14 | **`state.week += 1`** | `:1372` | no |
| 15 | Solo Carriera e `(week − 1) % 12 == 0`: ruota la fase Outdoor→Cross→Indoor | `:1374-1378` | no |
| 16 | Se la nuova fase è Outdoor (fine stagione): `close_season` (verdetto), `season_number += 1`, **azzera `league_table`**, età +1 a **tutti** gli atleti, `renew_rivals_for_season` | `:1379-1386`; `close_season :1167-1210` | sì (rinnovo rivali) |
| 17 | Notizia «Inizia la stagione …» | `:1387-1390` | no |
| 18 | Promozione automatica dei ragazzi del vivaio con età ≥ 18 (età già incrementata al passo 16) | `:1392-1398` | no |
| 19 | Notizia «Settimana di Gara (casa/trasferta)» se la nuova settimana è di gara | `:1400-1405` | no |
| 20 | `_evaluate_objectives` (seconda volta: la prima è in `simulate_competition`) | `:1407` | no |
| 21 | `maybe_generate_dilemma` (con `state.week` **già incrementata**); se `pending_dilemma` è già valorizzato non fa nulla e non consuma RNG | `:1408-1410`; `generator.py:662-699` | sì (se non pendente e settimana ∉ {3,7}) |
| 22 | Troncamento liste: notizie 70, traguardi 40, transazioni 400 | `:1412-1414` | no |
| 23 | Restituisce `WeekAdvanceReport` | `:1416-1430` | no |

## C. Sotto-sequenza `simulate_competition` (`simulation.py:693-1119`)

| # | Passo | File:riga |
| ---: | --- | --- |
| 1 | Meteo (Sereno indoor, altrimenti `r.choice`), stato pista, `is_home` | `:710-719`, `:708` |
| 2 | Per divisione M poi F, per evento (ordine `active_events`): se nessun convocato o infortunato → solo punti rivali | `:733-743` |
| 3 | Atteggiamento, vento (se l'evento è sensibile), rischio ritiro (`r.random() < injury_chance`) | `:745-761` |
| 4 | Punteggio giocatore (`_compute_athlete_event_score` + atteggiamento + σ + casa +1,0) → misura | `:775-783` |
| 5 | Atleti rivali (uno per società), PB rivale se vento legale | `:801-820` |
| 6 | Ordinamento, piazzamenti, **punti squadra** `TEAM_POINTS` | `:822-832` |
| 7 | PB, record sociale, momento storico (solo vento legale e non ritirato) | `:834-888` |
| 8 | Premi, prestigio, fan | `:890-901` |
| 9 | Fatica (+atteggiamento) e forma ricalcolata dell'atleta | `:797-799` |
| 10 | Staffette M e F: sostituzioni dalla riserva, DQ, tempo, punti, record, premi | `:926-1030` |
| 11 | `_adapt_rival_ambition` | `:1032` |
| 12 | Classifica del meeting (ordine di inserimento nei pari merito), bonus prestigio 1°/2°/3° | `:1033-1039` |
| 13 | **Somma dei punti nella `league_table`** | `:1040-1041` |
| 14 | Casa: biglietti e usura pista −3; trasferta: costo; `budget += premi + biglietti − trasferta`; `prestige += …` | `:1043-1052` |
| 15 | Transazioni (premi, biglietti o trasferta), `CompetitionSummary` in testa alla storia, notizia | `:1054-1117` |
| 16 | `_evaluate_objectives` (prima chiamata) | `:1118` |

## D. Controller (dopo il tick)

| # | Passo | File:riga |
| ---: | --- | --- |
| C3 | Azzera `scouting_results` e `free_agent_pool` (in memoria) | `game_controller.py:845-846` |
| C4 | `save_game` (DELETE + INSERT in una transazione) | `game_controller.py:847`; `database.py:575-581` |
| C5 | Segnali: `state_changed`, `week_advanced` | `:848-849` |
| C6 | Se gara: `competition_completed` → dialog modali (visualizzatore + risultati) | `:851-857`; `main_window.py:332-336` |
| C7 | `season_ended` → dialog di fine stagione | `:861-862` |
| C8 | `dilemma_triggered` → dialog; se chiuso senza scelta il dilemma resta pendente | `:864-865`; `main_window.py:342-345` |

## E. Punti in cui l'ordine è sospetto

| ID | Sospetto | Evidenza | Gravità |
| --- | --- | --- | --- |
| T1 | **`week += 1` precede rotazione fase e verdetto.** Funziona perché `close_season` usa `state.week − 1` (`:1175`), ma i testi usano a volte la settimana completata (`ledger`) e a volte la nuova (`news_log` di fine stagione, `:1387-1390`). Fragile a ogni modifica. | `:1372` vs `:1375-1390`, `:1175` | media |
| T2 | **Punti gara vs verdetto**: ordine corretto (punti sommati al passo C-13, verdetto al passo 16 dello stesso tick; l'ultima gara della stagione, sett. 36, è inclusa). Verificato con simulazione. **Nessun difetto**, ma dipende dal fatto che la gara è il passo 1. | `:1040-1041` → `:1380` | ok |
| T3 | **Interessi vs fallimento**: l'interesse è calcolato sul saldo dopo premi, biglietti e flusso settimanale; il fallimento si controlla subito dopo, solo qui. Un saldo che scende sotto −20.000 *dentro* il tick (per esempio dopo la trasferta) non è verificato finché non arriva il passo 8. Poi `bankrupt` blocca solo i tick successivi (`controller:839`); il giocatore può ancora agire. | `:1338-1352` | media |
| T4 | **Scandalo doping prima delle finanze**: reputazione −25 (passo 5) entra già nello sponsor del passo 6, nello stesso tick. | `:1305` → `:1311` | bassa (da confermare se voluto) |
| T5 | **Gara e allenamento nella stessa settimana**: la fatica da gara (`:798`) e quella da allenamento (`:430`) si sommano nello stesso tick; il rischio infortunio da allenamento (`:443-462`) vede già la fatica post-gara. | `:798`, `:1285` | media (da confermare se voluto) |
| T6 | **Età +1 dopo il verdetto ma prima della promozione dal vivaio**; i rivali invecchiano dentro `renew_rivals_for_season` (`:666`) mentre `progress_rivals` (passo 11) ha usato le età vecchie nello stesso tick. | `:1383-1385`, `:1363` | bassa |
| T7 | **Dilemma con settimana già incrementata**: «sett. 3/7» significa dopo aver completato la 2/6; le settimane dispari generano sempre il tipo «doping» (`generator.py:675`). | `:1408`, `generator.py:670-675` | bassa |
| T8 | **`_evaluate_objectives` chiamata due volte** nel tick di gara; `positive_budget` non è monotono (può tornare falso) mentre gli altri obiettivi restano veri. Innocua oggi. | `:1118`, `:1407`, `:569-571` | bassa |
| T9 | **Armonia staffette dopo gli infortuni del tick** (passo 10 dopo il 4): un titolare infortunato dall'allenamento della stessa settimana conta come assente anche se ha gareggiato. | `:1362` | bassa |
| T10 | **Casa/trasferta dalla settimana corrente**: `next_meet_is_home` usa `state.week // 4` e viene letta dentro il tick (`:708`), prima di `week += 1`: corretta, ma alterna i ruoli ogni stagione (5 casa/4 trasferta, poi 4/5). | `entities.py:906-910` | bassa |
| T11 | **Nessuna atomicità del tick**: tutto muta `state` in memoria; un'eccezione a metà lascia lo stato incoerente e il successivo `save_game` di un'altra azione lo salva. | `:1259-1430`; `controller:847` | alta (vedi Q7 in AUDIT) |
