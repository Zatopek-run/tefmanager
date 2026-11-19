# QUESTIONS — decisioni di design che spettano a te

Ordinate per quanto bloccano lo sviluppo (la 1 blocca il primo lotto di `PLAN.md`). Non sono feature nuove: sono ambiguità di regole o di policy già presenti nel codice. Ogni ipotesi che ho dovuto fare è marcata **DA CONFERMARE**.

---

## 1. Che cosa fare di un salvataggio con versione sconosciuta, e quale policy di backup? — *blocca il lotto 1*

Oggi: `user_version` ≠ `SCHEMA_VERSION` e non in `MIGRATIONS` (v0, v1, o più nuova di 9) → `DROP TABLE` silenzioso (`database.py:404-415`, misurato). Hai già deciso «ogni migrazione ha backup + transazione»; non hai deciso i casi limite.
- **Raccomandazione:** *rifiutare* l'apertura senza toccare il file, con messaggio chiaro («salvataggio di una versione più recente / non riconosciuto»); copia `nomefile.db.bak-v{N}` prima di ogni migrazione, conservandone una per versione di partenza; i v1 si trattano come non migrabili (rifiuto, non DROP). **DA CONFERMARE:** nessun utente ha salvataggi v0/v1 che vuoi ancora azzerare.
- **Alternativa A:** DROP solo se esplicitamente confermato dall'utente in un dialog.
- **Alternativa B:** mantenere il DROP ma sempre dopo backup.
- **Cosa cambia:** `database.py` (`_init_schema`: transazione esplicita `BEGIN`/`COMMIT`, copia del file, eccezione tipizzata `UnsupportedSaveVersion`), `game_controller.load_save_slot` (cattura l'eccezione e mostra il messaggio), `start_screen.py` (messaggio); nuovi test su fixture.

## 2. In che forma salvare l'RNG?

Hai deciso «seed/stato nel save». Non è deciso il formato (`game_controller.py:110`, nessun salvataggio oggi).
- **Raccomandazione:** salvare lo **stato completo** (`random.Random.getstate()` serializzato in JSON) in una nuova colonna `rng_state_json` (schema v10), aggiornato a ogni `save_game`, un solo RNG per partita condiviso da tick e azioni UI (scouting `game_controller.py:500`, mercato `:388`). Così «ricarico e rigioco» dà lo stesso esito. **DA CONFERMARE:** accetti che ricaricare **dopo** un'azione che consuma RNG (es. una ricerca vivaio) produca la stessa ricerca (non puoi più «ritirare i dadi» ricaricando).
- **Alternativa A:** solo seed + contatore di estrazioni (più compatto, replay più lento).
- **Alternativa B:** RNG separati per tick e per UI (più semplice da testare, ma le azioni UI restano rilanciabili).
- **Cosa cambia:** `entities.GameState` (campo), `database.py` (colonna + migrazione v10 + test), `GameController.__init__` (carica/ripristina), `advance_week` invariato (già riceve `rng`).

## 3. L'economia di partenza deve essere in pareggio?

Misurato: Carriera −$4.432/sett. (stipendi $4.972 vs entrate $1.088), Prototipo −$2.291/sett.; in autopilota bancarotta a sett. 14 (una sola prova, seed 3).
- **Raccomandazione:** puntare a un flusso netto settimanale ≈ 0 (o leggermente negativo) *prima* dei premi, con i premi che fanno la differenza; leva più semplice: scalare `senior_wage` (`generator.py:413`). **DA CONFERMARE:** che sia intenzionale che il giocatore debba tagliare la rosa nelle prime settimane; se lo è, serve almeno un messaggio all'avvio.
- **Alternativa A:** alzare `weekly_sponsor`/quote e budget iniziale.
- **Alternativa B:** lasciare tutto com'è e documentarlo come difficoltà.
- **Cosa cambia:** solo costanti (nel modulo di bilanciamento, domanda 4) + test di sostenibilità (simulazione di N settimane con rosa iniziale).

## 4. Dove vivono le costanti di bilanciamento?

La tua regola cita «il modulo di bilanciamento», che oggi **non esiste** (`BALANCE.md`).
- **Raccomandazione (nome DA CONFERMARE):** `models/balance.py`, senza dipendenze, con le costanti oggi in `entities.py` (blocchi a `:43-68`, `:144-172`, `:186-198`, `:546-549`, `:623-624`) e i letterali delle funzioni; `entities.py` le importa e le ri-esporta per non rompere gli import esistenti.
- **Alternativa A:** `models/balance/` pacchetto con un file per dominio (economia, gara, allenamento, rivali).
- **Alternativa B:** restare in `entities.py` e solo vietare nuovi letterali.
- **Cosa cambia:** spostamenti meccanici, un lotto per dominio; test di non regressione (valori identici prima/dopo).

## 5. Come si risolve un pareggio in classifica?

Oggi alfabetico per nome (`entities.py:826-829`): decide titolo, promozione e retrocessione, e il giocatore sceglie il proprio nome; il meeting usa un'altra regola (`simulation.py:1033`).
- **Raccomandazione:** 1) più primi posti nelle gare della stagione, 2) più secondi, …, 3) sorteggio deterministico derivato dal seed della stagione. Stessa regola per lega e meeting. **DA CONFERMARE:** nessun requisito di realismo FIDAL sugli spareggi.
- **Alternativa A:** scontri diretti.
- **Alternativa B:** tenere l'alfabetico ma con ordine inverso per il giocatore (non risolve il problema di fondo).
- **Cosa cambia:** `GameState.league_standings`, `simulation.py:1033`; richiede di salvare i piazzamenti per gara (nuovo campo → migrazione) oppure ricavarli da `competition_history` (da verificare quante gare restano memorizzate: la storia non è troncata ma lo sono le notizie).

## 6. Che cosa succede se chiudi il dilemma etico senza scegliere?

Oggi resta pendente per sempre e blocca tutti i dilemmi futuri (misurato).
- **Raccomandazione:** il dialog non è chiudibile senza scelta, e un dilemma pendente nel salvataggio viene riproposto al caricamento. **DA CONFERMARE:** il dilemma deve essere obbligatorio.
- **Alternativa A:** chiudere = rifiuto automatico.
- **Alternativa B:** chiudere = rinvio; il dilemma scade dopo N settimane.
- **Cosa cambia:** `views/dialogs.py` (rifiuta Esc), `main_window.py` (riproposta al load), eventualmente `game_controller` (scadenza).

## 7. Rifiutare/accettare un dilemma può azzerare il debito?

`budget = max(0, budget − 600)` (`game_controller.py:798,825`): con saldo negativo, il rifiuto porta a 0.
- **Raccomandazione:** è un difetto; sottrarre senza `max` (il saldo può scendere). **DA CONFERMARE:** non era una scelta voluta di «aiuto in difficoltà».
- **Alternativa:** impedire il costo se il saldo è già negativo.
- **Cosa cambia:** due righe + test; `BALANCE.md`.

## 8. Il Prototipo deve finire?

Oggi non finisce (gare a sett. 12 e 16 misurate), anche se la UI dice «2 gare completate» (`tabs.py:429,967`).
- **Raccomandazione:** a settimana 9 il tick si blocca con riepilogo e invito a una Carriera. **DA CONFERMARE.**
- **Alternativa A:** lasciarlo infinito e correggere i testi.
- **Alternativa B:** convertirlo automaticamente in Carriera.
- **Cosa cambia:** `controller.advance_week` (guardia), `tabs.py` (testi), test.

## 9. Che cosa è il fallimento?

Oggi: flag `bankrupt` che blocca solo l'avanzamento (`game_controller.py:839`), il resto resta usabile.
- **Raccomandazione:** schermata di «Game Over» con riepilogo e offerta di ricaricare uno slot precedente; lo slot resta in sola lettura. **DA CONFERMARE.**
- **Alternativa A:** ristrutturazione del debito (perdi prestigio e atleti, la partita continua).
- **Alternativa B:** lasciare così.
- **Cosa cambia:** `main_window.py`, `game_controller.py`, eventualmente `simulation.py` (ristrutturazione).

## 10. Cross e Indoor devono cambiare le discipline?

Oggi sono etichette: stessi 5 eventi (`entities.py:912-917`); Indoor ha 100m con vento 0 (non 60m), Cross non ha corsa campestre.
- **Raccomandazione:** non toccarle ora; è una decisione di contenuto, non un difetto. **DA CONFERMARE:** non vuoi 60m indoor né una gara di cross nel breve.
- **Alternativa A:** Indoor = 60m al posto del 100m, niente Lungo/Peso all'aperto-only.
- **Alternativa B:** aggiungere un evento «Cross» (richiede nuove curve di punteggio e rinunciare a staffette).
- **Cosa cambia (A/B):** `entities.EVENTS`, `active_events`, `_score_to_mark`, record/obiettivi, schema (nuove chiavi nei JSON), Godot (`GODOT_EVENTS`), test. Grande.

## 11. Fan e sponsor individuali: serve un tetto o un decadimento?

`fans` solo in aumento (`simulation.py:901`), sponsor `fans//4` per atleta ≥18 a settimana (`:1230`), senza limite.
- **Raccomandazione:** decadimento lento (es. 1-2% a settimana) più tetto per categoria. **DA CONFERMARE.**
- **Alternativa:** solo tetto; oppure lasciare.
- **Cosa cambia:** `simulation.py:1230` o nuova passata nel tick (cambia l'ordine: aggiornare `TICK.md`), costanti, test di sostenibilità.

## 12. Gli stipendi degli atleti devono seguire la loro crescita?

Oggi non si rivedono mai dopo creazione/promozione (`generator.py:410`, `simulation.py:1254`).
- **Raccomandazione:** ricalcolo a ogni rotazione di stagione (`simulation.py:1380-1386`). **DA CONFERMARE.**
- **Alternativa:** ogni N settimane, o su richiesta (rinnovo contratto).
- **Cosa cambia:** una chiamata nel blocco di fine stagione + aggiornamento `TICK.md` e test.

## 13. Obiettivi stagionali: devono rinnovarsi?

Creati solo a nuova partita (`game_controller.py:172`); «promote» non si riazzera dopo retrocessione; «traguardo storico» usa la soglia maschile anche per le donne (`simulation.py:588`).
- **Raccomandazione:** rinnovarli in `close_season` per la nuova categoria e usare la soglia per divisione. **DA CONFERMARE:** gli obiettivi non hanno premi oggi (non ho trovato codice che li ricompensi); decidi se devono averne.
- **Alternativa:** lasciarli come «tutorial» della prima stagione.
- **Cosa cambia:** `generator.create_season_objectives`, `simulation.close_season`, `_evaluate_objectives`; salvataggio invariato (già in `objectives_json`).

## 14. Allineare README o codice su fedeltà e riserva?

README: fedeltà «acquisto o cessione … meno per gli under 21»; codice: cessione −8 fisso. README: «sostituire un titolare»; codice: penalità e cooldown anche per la **riserva** e per l'auto-composizione.
- **Raccomandazione:** correggere il **README** (il codice è coerente con sé stesso) — in una sessione apposita, non questa.
- **Alternativa:** cambiare il codice (sconto under 21 sulla cessione; riserva senza penalità).
- **Cosa cambia:** o testo, o `game_controller.py:453-454` / `:741-758`.

## 15. Un atleta può correre più gare nello stesso meeting?

Oggi sì: `build_default_lineup` lo preferisce evitare ma non lo vieta (`generator.py:546`), `set_event_athlete` non valida né duplicati né genere (`game_controller.py:370-374`); la fatica da gara si somma e poi si allena nella stessa settimana (`TICK.md` T5).
- **Raccomandazione:** consentire più gare per atleta, validare il genere/Prima Squadra nel controller, documentare T5 come voluto. **DA CONFERMARE.**
- **Alternativa:** un solo evento individuale per atleta e meeting.
- **Cosa cambia:** `game_controller.set_event_athlete` + test; per l'alternativa anche `build_default_lineup`.
