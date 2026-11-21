# TICK — sequenza reale dell'avanzamento settimana

Fonte: `models/simulation.py:1259-1430` (`advance_week`) chiamata da `controllers/game_controller.py:838-867`.
`r` è l'RNG del tick (`simulation.py:1264`): **l'ordine delle chiamate a `r` è parte del comportamento** (cambiarlo cambia ogni esito a parità di seed).
Dal 2026-11-20 (A.3) `r` è `GameController.rng`, l'unico RNG della partita: il suo stato completo è salvato (`_persist`) dopo il tick e ripristinato al caricamento; l'ordine delle chiamate non cambia.
Settimana «completata» = `completed_week = state.week` (`:1265`); dopo il passo 20 `state.week` è già la nuova.

## A. Controller (prima del tick)

| # | Passo | File:riga |
| ---: | --- | --- |
| C0 | **Guardia di rientro** (A.5, 2026-11-20): se un tick è già in corso (`is_advancing`, anche con dialoghi modali aperti dai segnali) la chiamata è ignorata con un messaggio; il flag si abbassa sempre (`finally`) | `game_controller.py`: `advance_week` |
| C1 | Se `state.bankrupt`: messaggio e **stop** (nessun tick) | `game_controller.py:839-843` |
| C1b | **Dilemma pendente scartato** (A.4, 2026-11-20): se `pending_dilemma` non è `None` si chiama `dismiss_dilemma` (nessun effetto, una notizia). Non usa `r`, quindi l'ordine dell'RNG non cambia | `game_controller.py`: `_advance_week_unguarded` |
| C2 | Chiama `advance_week(state, rng=self.rng)` | `game_controller.py:844` |

## B. Modello: `advance_week`

| # | Passo | File:riga | Usa RNG |
| ---: | --- | --- | :-: |
| 0 | **Relazioni** (F.3, 2026-11-21): `ensure_relationships(state)` dà il valore di nascita alle coppie nuove della Prima Squadra e toglie i legami verso atleti usciti. **Non usa `r`** (crc32 degli id); va **prima** di ogni gara e allenamento, e dal passo 4 al passo C-8 la chimica di squadra (`team_chemistry_form_bonus`, ±3) sposta il bersaglio di forma di tutti | `relationships.py` | no |
| 1 | Se `is_competition_week` (sett. % 4 == 0 **e non in Preparazione**, `GameState.is_race_week`): `simulate_competition` (sotto-sequenza in §C) | `:1270-1272`; `entities.py:923-926` | sì |
| 2 | Ruoli staff assunti, presenza di un Leader sano | `:1274-1277` | no |
| 3 | Carichi allenatore `coach_load` calcolati **una volta** | `:1284` | no |
| 4 | Per ogni atleta (`state.athletes`, ordine lista): `apply_weekly_training` (doping/infortunio/recupero/crescita/fatica/forma/declino/rischio infortunio). Riceve `pre_meet = (state.weeks_until_competition == 1)`: nel tick che precede la gara la fase «Gara (Picco)» aggiunge `PEAK_FORM_BONUS` al bersaglio di forma (Q21; nessuna chiamata a `r` in più). **E.2:** con il **centro medico** posseduto, ogni nuovo infortunio da allenamento costa **una `r.random()` in più** subito dopo la `randint(1, 3)` e il taglio del fisioterapista (`injury_weeks_with_medical_center`); la squalifica per doping non è toccata. Senza il centro l'ordine è invariato; gli altri tre impianti moltiplicano solo la probabilità già estratta (nessuna chiamata in più) | `:1285-1295`; `:295-464` | sì |
| 5 | Note infortunio/recupero al `news_log`; scandalo doping: reputazione −25, prestigio −45 | `:1296-1308` | no |
| 6 | `weekly_finances(state)` (calcolata **dopo** il passo 5: lo scandalo riduce già lo sponsor di questa settimana) e `budget += net`. **D.3:** include il **merchandising** (fan ÷ 40 + prestigio ÷ 20) e, se l'ultima stagione è finita fuori dai primi 5, lo sponsor società è tagliato del 20% (si legge da `season_history[0]`, **prima** che il passo 16 lo aggiorni: vale dalla stagione dopo). Nessun RNG | `:1311-1312`; `:1224-1248` | no |
| 7 | Scritture del libro mastro (sponsor, individuali, quote, stipendi, staff, allenatori, palestra). La riga «Rimborsi spese atleti» si scrive solo se l'importo è > 0 (Q32: senza atleti niente riga da zero) | `:1314-1335` | no |
| 8 | Debito: se `budget < 0`: interesse `ceil(−budget × 0,05)` sottratto; se `budget < −20.000` e non già fallita → `bankrupt = True` | `:1337-1352` | no |
| 9 | Decadimento abilità allenatori: per ciascuno 10% → −1 a una abilità sopra 25 | `:1354-1360` | sì |
| 10 | `_update_relay_harmony` (usa gli infortuni **dopo** il passo 4) | `:1362`; `:240-258` | no |
| 11 | `progress_rivals`: deriva settimanale di tutti i rivali di tutte le categorie; ogni 4 sett. snapshot `history` | `:1363`; `:639-650` | sì |
| 12 | Usura pista `−randint(1,3)` | `:1365-1366` | sì |
| 13 | Fedeltà `+2` (max 100); `scouting_points_used = 0`. **E.3:** gli atleti del vivaio crescono con ×(1 + 0,10 × stelle Academy) nel passo 4 (nessuna chiamata in più); il compenso dell'osservatore è dentro `staff_cost` (passi 6-7, riga «Compensi Staff» del libro mastro) | `:1368-1370` | no |
| 14 | **`state.week += 1`** | `:1372` | no |
| 15 | Solo Carriera e `state.is_phase_start(week)` (posizione nel ciclo ∈ {0, `prep_weeks`, +12, +24}; con `prep_weeks` = 0 è `(week − 1) % 12 == 0` come prima): ruota la fase **[Preparazione →] Outdoor → Cross → Indoor** (`season_cycle`). Q32 | `:1374-1378` | no |
| 16 | Se la nuova fase è la **prima del ciclo** (Preparazione se `prep_weeks` > 0, altrimenti Outdoor: fine stagione; Q32): `close_season` (verdetto), `season_number += 1`, **azzera `league_table`**, età +1 a **tutti** gli atleti, `renew_rivals_for_season` | `:1379-1386`; `close_season :1167-1210` | sì (rinnovo rivali) |
| 16a | Dentro `close_season` (passo 16), se l'esito è PROMOZIONE: `budget += PROMOTION_BONUS` (5.000) e voce «Bonus promozione» nel libro mastro, settimana appena chiusa (A.1, 2026-11-20). **Non usa `r`** | `simulation.py: close_season` | no |
| 16b | Dentro il passo 16, dopo età +1: `renew_expiring_contracts`: i contratti con `contract_end_season < season_number` si rinnovano da soli (1-3 stagioni, `contract_length`: deterministica da id atleta e stagione), una sola notizia; nessun costo. Chi ha `contract_no_renew` (pulsante «non rinnovare») **lascia la società** (nessuna penale di fedeltà; l'ultimo atleta della Prima Squadra si rinnova comunque), con formazione e staffette ricomposte (`build_default_lineup`, `auto_build_relay`). **Non usa `r`** (Q22) | `simulation.py` | no | Per ogni atleta rinnovato: relazione con l'agente `+AGENT_RELATION_RENEWED`; per ogni atleta che lascia: `AGENT_RELATION_NOT_RENEWED` (D.1; nessun RNG).
| 16b0 | Dentro il passo 16, dopo età +1 e **prima** di `retire_veterans`: `drift_relations`, ogni relazione con un agente chiude un quarto (`AGENT_RELATION_DRIFT`, passo minimo 1) della distanza da 50, poi `penalize_idle_athletes`: `AGENT_RELATION_IDLE` per ogni atleta della Prima Squadra mai convocato nella stagione appena chiusa (D.1, 2026-11-20); **non si applica alla stagione di fondazione** (stagione 1 di una Carriera nuova, Q32). **Non usa `r`** | `agents.py` | no |
| 16b' | Dentro il passo 16, dopo età +1 e **prima** di `renew_expiring_contracts` (così chi si ritira non riceve anche la notizia del rinnovo): `retire_veterans` (C.3, 2026-11-20). Per ogni atleta della Prima Squadra, in ordine di lista, con probabilità di ritiro > 0 (da 33 anni, o da 30 con 3+ infortuni in stagione): **una `r.random()`**; per chi si ritira, **un'altra `r.random()`** (10%: si offre come allenatore). Gli atleti non eleggibili e il vivaio non estraggono; l'ultimo della Prima Squadra non si ritira (la prima estrazione c'è, la seconda no). Azzera `season_injuries` di tutti. Le estrazioni stanno **prima** di quelle di `renew_rivals_for_season`: ogni partita con atleti di 33+ anni cambia la sequenza successiva (senza eleggibili l'ordine è quello di prima) | `simulation.py: retire_veterans`; `career.py` | sì |
| 16c | Dentro `close_season` (passo 16), **verdetto del Board** (C.2, 2026-11-20): `settle_season` giudica i tre obiettivi con il posto finale, **prima** del cambio di livello e del bonus promozione (16a), aggiorna `board_failed_streak` e, al 2° fallimento di fila, `fired`; scrive una notizia (sotto l'esito della lega) e riempie `SeasonEndResult`. Subito dopo `renew_rivals_for_season`, `start_new_season` crea i tre obiettivi della stagione che comincia (livello e budget attuali; **dopo** il bonus promozione; nella stagione 2 di una Carriera nuova il posto in lega è allargato in base alla forza della rosa, `league_target`), tranne se esonerato. **Stagione di fondazione (Q32):** il verdetto è solo informativo (`BoardVerdict.foundation`): non tocca `board_failed_streak`, non esonera, `board_failed` = False. **Non usa `r`** | `board.py`; `simulation.py: close_season` |
| 16d | Dentro il passo 16, dopo `renew_rivals_for_season` e **prima** di `start_new_season`: `renew_staff_market` (E.1, 2026-11-20): lo specialista clinico assunto resta, i non assunti sono sostituiti da candidati nuovi (3 per ruolo, assunto compreso). **Usa `r` UNA sola volta** (`r.getrandbits(32)`, anche con lo staff vuoto) per seminare un `random.Random` locale: il flusso della partita si sposta di **una** estrazione per fine stagione, qualunque cosa si cambi nella generazione dei candidati. Solo Carriera (il Prototipo non ha fine stagione) | `simulation.py` (passo 16); `generator.py: renew_staff_market` | sì (1 estrazione) |
| 17 | Notizia «Inizia la stagione …» (per la Preparazione: «Inizia la Preparazione … senza gare fino alla settimana N») | `:1387-1390` | no |
| 18 | Promozione automatica dei ragazzi del vivaio con età ≥ 18 (età già incrementata al passo 16) | `:1392-1398` | no |
| 18b | `normalize_assignments(state)`: sostituisce le convocazioni non ammesse (oltre `MAX_INDIVIDUAL_EVENTS` gare individuali, under 20 in Internazionale: età +1 e nuovo livello sono già applicati) in formazione e staffette; scrive le note in `news_log`. **Non usa `r`** | `simulation.py` | no |
| 19 | Notizia «Settimana di Gara (casa/trasferta)» se la nuova settimana è di gara | `:1400-1405` | no |
| 20 | `_evaluate_objectives` (seconda volta: la prima è in `simulate_competition`) | `:1407` | no |
| 21 | `maybe_generate_dilemma` (con `state.week` **già incrementata**); se `pending_dilemma` è già valorizzato non fa nulla e non consuma RNG | `:1408-1410`; `generator.py:662-699` | sì (se non pendente e settimana ∉ {3,7}) |
| 21b | **Bilancio mensile** (D.3): se la nuova settimana apre un mese (`(week − 1) % 4 == 0`, `week > 4`), `close_month_if_due` somma per categoria le voci del libro mastro delle 4 settimane appena chiuse (capitale iniziale escluso) e mette il resoconto in testa a `monthly_reports` (al più 36). Va **dopo** ogni movimento del tick e **prima** del troncamento del passo 22 (che tiene 400 voci). **Non usa `r`** | `finances.py` | no |
| 21c | **Notizie dinamiche** (F.1, 2026-11-21): **solo se il passo 21b ha chiuso un mese**, `monthly_news(state, week − 4, week − 1)` scrive in testa a `news_log` al più una riga per tipo (premio «Allenatore del Mese», stampa critica, tensione nello spogliatoio), in quest'ordine. **Non usa `r`** (le varianti di frase si scelgono con `crc32`): l'ordine delle estrazioni dell'RNG non cambia. Va **dopo** 21b e **prima** del troncamento del passo 22 (70 notizie). Nessuna notizia senza atleti in Prima Squadra né nella stagione di fondazione | `narrative.py` | no |
| 21d | **Storico per i grafici** (G.1/G.2, 2026-11-21): `record_weekly(state)` aggiunge a ogni atleta (vivaio compreso) `[forma, fatica, infortunato]` di **fine tick**, al più le ultime 12 settimane. In più, dentro `simulate_competition` (passo 1), dopo ogni gara **individuale** `record_result` salva posto, partecipanti, misura e PB, al più le ultime 10 gare. **Solo scrittura, nessun effetto sul gioco, non usa `r`** (c'è un test: stesso seme, stessi esiti con e senza storico) | `history.py` | no |
| 22 | Troncamento liste: notizie 70, traguardi 40, transazioni 400 | `:1412-1414` | no |
| 23 | Restituisce `WeekAdvanceReport` | `:1416-1430` | no |

## C. Sotto-sequenza `simulate_competition` (`simulation.py:693-1119`)

| # | Passo | File:riga |
| ---: | --- | --- |
| 0 | **Decadimento del ranking** (C.1, 2026-11-20): i punti ranking di club, rivali di ogni livello e atleti sintetici si moltiplicano per `RANKING_DECAY`, per tutti insieme e prima dei nuovi punti. **Non usa `r`** | `ranking.py: decay_ranking` |
| 1 | Meteo (Sereno indoor, altrimenti `r.choice`), stato pista, `is_home` | `:710-719`, `:708` |
| 2 | Per divisione M poi F, per evento (ordine `active_events`: 100m, 400m, **800m**, 1500m, Lungo, Peso in Carriera; l'800m è stato inserito il 2026-11-19 e sposta la sequenza dell'RNG di ogni partita): se nessun convocato o infortunato → solo punti rivali | `:733-743` |
| 3 | Atteggiamento, vento (se l'evento è sensibile), rischio ritiro (`r.random() < injury_chance`). **E.2:** se si ritira e c'è il **centro medico**, una `r.random()` in più subito dopo i `weeks_out` (`injury_weeks_with_medical_center`); senza centro l'ordine è invariato | `:745-761` |
| 4 | Punteggio giocatore (`_compute_athlete_event_score` + atteggiamento + piano gara B.1 / bonus tecnica B.2 + σ + casa +1,0) → misura. **Solo in lungo/peso con rischio ≠ «Sicuro» (B.2): una `r.random()` in più subito dopo la misura** (nullo: misura −`FIELD_FOUL_LOSS`); con «Sicuro» l'ordine delle chiamate è invariato | `:775-783` |
| 5 | Atleti rivali (uno per società), PB rivale se vento legale | `:801-820` |
| 6 | Ordinamento, piazzamenti, **punti squadra** `TEAM_POINTS`. Subito dopo, **punti ranking** (C.1) a chi è classificato: club e rivali, `RANKING_PLACE_POINTS[posto-1]` × moltiplicatore del livello (`award_event_points`; il ritirato del club non è classificato e non ne ha; stessa regola per i rivali quando il club non iscrive nessuno, `_rival_only_points`). Le staffette non danno punti ranking. **Non usa `r`** | `:822-832` |
| 7 | PB, record sociale, momento storico (solo vento legale e non ritirato). Ogni record sociale (anche di staffetta) conta per l'obiettivo del Board «record» (`note_club_record`, C.2; senza RNG) | `:834-888` |
| 8 | Premi, prestigio, fan | `:890-901` |
| 8c | **Staffette** (F.3): l'affiatamento in gara è `harmony − 15 se c'è una riserva + relay_chemistry_bonus(frazioni)` (+10 se due frazioni sono amiche, −10 se rivali) e, **subito dopo averlo calcolato**, ogni coppia di frazioni si avvicina di `RELATION_BOND_PER_RELAY` (una volta a coppia per meeting). **Non usa `r`**: la `r.random()` della squalifica e la `gauss` del punteggio restano le stesse | `relationships.py` | no |
| 8b | Subito dopo i fan, per ogni gara **individuale** dell'atleta del club non ritirato con piazzamento 1°-3°: `adjust_relation(agent, +AGENT_RELATION_PODIUM)` (D.1, 2026-11-20). **Non usa `r`**: le staffette non contano | `simulation.py: simulate_competition` | no |
| 9 | Fatica (+atteggiamento) e forma ricalcolata dell'atleta | `:797-799` |
| 10 | Staffette M e F: sostituzioni dalla riserva, DQ, tempo, punti, record, premi. **Cambio scelto (B.3): nessuna chiamata RNG in più** — cambiano solo la soglia della `r.random()` della DQ e i punti sommati a `p_score`; l'ordine e il numero delle chiamate sono quelli di prima. Nota (R20): una squadra squalificata salta la `r.gauss(0; 2,5)` del proprio tempo, quindi la sequenza dopo la DQ dipende dall'esito | `:926-1030` |
| 11 | `_adapt_rival_ambition` | `:1032` |
| 12 | Classifica del meeting (ordine di inserimento nei pari merito), bonus prestigio 1°/2°/3° | `:1033-1039` |
| 13 | **Somma dei punti nella `league_table`** | `:1040-1041` |
| 13b | **Atleti sintetici del ranking** (C.1): ogni sintetico muove il livello (`gauss`) e simula un piazzamento contro un campo virtuale (`gauss` per la prestazione, una `random()` per ciascuno dei 7 avversari virtuali, nell'ordine della lista `ranking_pool`: `update_synthetic_field`). **Usa `r`**: aggiungerli sposta tutte le estrazioni successive a parità di seme (2026-11-20, decisione dell'utente). Senza campo (stato costruito a mano) non fa nulla e non consuma `r`. Il campo si crea fuori dal tick: alla partita nuova (`_create_fresh_state`) e al caricamento di un salvataggio vecchio (`upgrade_legacy_state`), con `rng` | `ranking.py: update_synthetic_field` |
| 14 | **Società senza atleti in Prima Squadra (`club_absent`, Q32): niente biglietti (e quindi **nessuna estrazione** del pubblico: `_compute_ticket_income` non gira), niente usura pista, niente trasferta, niente diritti TV, niente bonus squadra 1°-3° al passo 12; una notizia «non si iscrive (nessuna sanzione)»; il meeting si simula lo stesso (i rivali corrono e si dividono i punti).** Altrimenti: casa: biglietti e usura pista −3; trasferta: costo; `budget += premi + biglietti − trasferta`; `prestige += …` | `:1043-1052` |
| 14b | Insieme al passo 14: per ogni record sociale **individuale** segnato in questo meeting da un atleta con `record_bonus > 0` (D.2), `budget −= bonus` e una voce «Bonus Atleti» nel libro mastro (più una notizia). Il bonus si azzera al rinnovo del contratto (passo 16b). **Non usa `r`** | `simulation.py: simulate_competition` | no |
| 14c | Insieme al passo 14, solo meeting **in casa** del livello **Internazionale**: `budget += TV_RIGHTS_PER_HOME_MEET` e voce «Diritti TV» nel libro mastro (D.3). **Non usa `r`** | `simulation.py: simulate_competition` | no |
| 15 | Transazioni (premi, biglietti o trasferta), `CompetitionSummary` in testa alla storia, notizia | `:1054-1117` |
| 16 | `_evaluate_objectives` (prima chiamata) | `:1118` |

## D. Controller (dopo il tick)

| # | Passo | File:riga |
| ---: | --- | --- |
| C3 | (F.2: la **conferenza stampa** si apre dal controller dopo i risultati, **fuori dal tick**: non estrae dall'RNG e non cambia l'ordine di nulla; sposta reputazione e relazione con un agente solo se si risponde.) (E.3: una **ricerca di vivaio con regione**, fuori dal tick, fa in più una `rng.random()` per ragazzo segnalato e una `rng.randint(81, 90)` per ciascun talento, dopo la generazione dei ragazzi; senza regione l'ordine è invariato.) Azzera `scouting_results` e `free_agent_pool` (in memoria); poi `prune_idle_agents` (D.1: toglie gli agenti senza clienti e con relazione neutra, i candidati non presi) | `game_controller.py:845-846` |
| C3b | **Momenti di gloria** (F.4, 2026-11-21): subito dopo `advance_week` e **prima** del salvataggio, `_glory_of` (record del mondo e muri abbattuti del meeting; titolo, promozione e atleta dell'anno a fine stagione) scrive nel registro notizie e nei traguardi le righe dei momenti che non ne hanno già una. **Non usa `r`**. I momenti non sono salvati | `glory.py`; `game_controller.py` | no |
| C4 | `save_game` (DELETE + INSERT in una transazione) | `game_controller.py:847`; `database.py:575-581` |
| C5 | Segnali: `state_changed`, `week_advanced` | `:848-849` |
| C6 | Se gara: `competition_completed` → dialog modali (visualizzatore + risultati) | `:851-857`; `main_window.py:332-336` |
| C7 | `season_ended` → dialog di fine stagione | `:861-862` |
| C7b | `glory_moments` → un popup per momento (F.4), dopo i risultati e la fine stagione, prima del dilemma | `main_window.py: _show_glory_moments` |
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
