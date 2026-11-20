# QUESTIONS — decisioni di design che spettano a te

Ordinate per quanto bloccano lo sviluppo (la 1 blocca il primo lotto di `PLAN.md`). Non sono feature nuove: sono ambiguità di regole o di policy già presenti nel codice. Ogni ipotesi che ho dovuto fare è marcata **DA CONFERMARE**.

---

## 1. Che cosa fare di un salvataggio con versione sconosciuta, e quale policy di backup? — ✅ DECISA il 2026-11-19 (lotti 1.1 e 1.2 fatti)

**Decisione presa (risposta dell'utente):**
- Una `user_version` né corrente né migrabile (più recente di 9, v0, v1) viene **rifiutata**: nessun `DROP`, nessuna scrittura, file intatto. Messaggi distinti: «versione più recente, aggiorna il gioco» e «non riconosciuto o non migrabile». Scartate le alternative A (DROP con conferma) e B (DROP dopo backup).
- Un file è «DB nuovo» solo se assente o di 0 byte; un file non vuoto senza tabelle utente (`sqlite_%` escluso) si rifiuta.
- Prima di **ogni** migrazione, backup verificato (apribile, `integrity_check` ok, `user_version` = versione di partenza), sempre nuovo: `saves/backups/<slot>.v{N}.{AAAAmmGG-HHMMSS-µs}.db.bak` (non `nomefile.db.bak-v{N}`, e non uno per versione di partenza). Si conservano i 3 più recenti per slot, eliminando i più vecchi solo dopo una migrazione riuscita; un tentativo fallito non cancella nulla.
- `read_save_summary` continua a elencare gli slot non supportati (sola lettura, solo metadati affidabili) e un file non SQLite è marcato «danneggiato».
- Il messaggio all'utente è un `QMessageBox.warning` con il traceback in `setDetailedText` e il percorso del backup se creato.

Testo originale della domanda, per memoria:

Oggi: `user_version` ≠ `SCHEMA_VERSION` e non in `MIGRATIONS` (v0, v1, o più nuova di 9) → `DROP TABLE` silenzioso (`database.py:404-415`, misurato). Hai già deciso «ogni migrazione ha backup + transazione»; non hai deciso i casi limite.
- **Raccomandazione:** *rifiutare* l'apertura senza toccare il file, con messaggio chiaro («salvataggio di una versione più recente / non riconosciuto»); copia `nomefile.db.bak-v{N}` prima di ogni migrazione, conservandone una per versione di partenza; i v1 si trattano come non migrabili (rifiuto, non DROP). **DA CONFERMARE:** nessun utente ha salvataggi v0/v1 che vuoi ancora azzerare.
- **Alternativa A:** DROP solo se esplicitamente confermato dall'utente in un dialog.
- **Alternativa B:** mantenere il DROP ma sempre dopo backup.
- **Cosa cambia:** `database.py` (`_init_schema`: transazione esplicita `BEGIN`/`COMMIT`, copia del file, eccezione tipizzata `UnsupportedSaveVersion`), `game_controller.load_save_slot` (cattura l'eccezione e mostra il messaggio), `start_screen.py` (messaggio); nuovi test su fixture.

## 2. In che forma salvare l'RNG? — ✅ FATTA il 2026-11-20 (PIANOLAVORO A.3), come da raccomandazione

**Fatto:** stato completo in `rng_state_json` (schema v13), un solo RNG condiviso da tick e azioni UI; ricaricare dopo un'azione che consuma RNG dà lo stesso esito (non si «ritirano i dadi»). Il piano diceva «seed = hash(id + stagione)»: l'id dello slot è sempre 1, quindi ogni nuova partita avrebbe avuto lo stesso seme; il seme resta casuale per partita e il seed deterministico (`hashlib`: società, stagione, settimana) vale solo per i vecchi salvataggi senza stato. **Non coperto:** il pool del mercato (non salvato).

Hai deciso «seed/stato nel save». Non è deciso il formato (`game_controller.py:110`, nessun salvataggio oggi).
- **Raccomandazione:** salvare lo **stato completo** (`random.Random.getstate()` serializzato in JSON) in una nuova colonna `rng_state_json` (schema v10), aggiornato a ogni `save_game`, un solo RNG per partita condiviso da tick e azioni UI (scouting `game_controller.py:500`, mercato `:388`). Così «ricarico e rigioco» dà lo stesso esito. **DA CONFERMARE:** accetti che ricaricare **dopo** un'azione che consuma RNG (es. una ricerca vivaio) produca la stessa ricerca (non puoi più «ritirare i dadi» ricaricando).
- **Alternativa A:** solo seed + contatore di estrazioni (più compatto, replay più lento).
- **Alternativa B:** RNG separati per tick e per UI (più semplice da testare, ma le azioni UI restano rilanciabili).
- **Cosa cambia:** `entities.GameState` (campo), `database.py` (colonna + migrazione v10 + test), `GameController.__init__` (carica/ripristina), `advance_week` invariato (già riceve `rng`).

## 3. L'economia di partenza deve essere in pareggio? — ✅ FATTA il 2026-11-20 (PIANOLAVORO A.1, cifre riviste dall'utente)

**Fatto:** sponsor società +40%, montepremi +25%, rimborsi spese atleti **−45%** (non −20% come nel piano: con −20% il flusso restava a −3.237 €/sett. e −55.000 € in 36 sett.), bonus promozione +5.000 €. Misura su 8 seed in autopilota (nessuna spesa del giocatore): 12 sett. da +4.727 a +15.349 (media +9.485); 36 sett. da +286 a +23.775 (media +11.508); 108 sett. minimo +21.050. Con −50% la media a 36 sett. sarebbe +20.445, con −60% il peggior seed scende a −8.606. Test: `tests/test_economy.py`. **Limite:** i salvataggi esistenti tengono i rimborsi vecchi (nessuna migrazione): per loro l'economia resta in perdita.

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

## 5. Come si risolve un pareggio in classifica? — ✅ FATTA il 2026-11-20 (PIANOLAVORO A.2), **scelta dell'utente: «salva i piazzamenti»**

**Fatto:** più 1° posti, poi più 2°, …, poi sorteggio deterministico (`hashlib`, stagione + posizione del club; non il nome e non `random`). Piazzamenti per club in `GameState.league_places` (schema v12). Il piano scriveva «punti cumulativi, miglior piazzamento, sorteggio con seed = id società»: i punti sono già il criterio che va in pareggio e il club non ha un id; l'utente ha scelto il conteggio completo dei piazzamenti. Quando arriverà A.3 il sorteggio potrà passare al seed della partita.

Oggi alfabetico per nome (`entities.py:826-829`): decide titolo, promozione e retrocessione, e il giocatore sceglie il proprio nome; il meeting usa un'altra regola (`simulation.py:1033`).
- **Raccomandazione:** 1) più primi posti nelle gare della stagione, 2) più secondi, …, 3) sorteggio deterministico derivato dal seed della stagione. Stessa regola per lega e meeting. **DA CONFERMARE:** nessun requisito di realismo FIDAL sugli spareggi.
- **Alternativa A:** scontri diretti.
- **Alternativa B:** tenere l'alfabetico ma con ordine inverso per il giocatore (non risolve il problema di fondo).
- **Cosa cambia:** `GameState.league_standings`, `simulation.py:1033`; richiede di salvare i piazzamenti per gara (nuovo campo → migrazione) oppure ricavarli da `competition_history` (da verificare quante gare restano memorizzate: la storia non è troncata ma lo sono le notizie).

## 6. Che cosa succede se chiudi il dilemma etico senza scegliere? — ✅ FATTA il 2026-11-20 (PIANOLAVORO A.4), **chiudi = ignora CONFERMATO dall'utente**

**Fatto:** chiudere (X, Esc) o «Ignora» = il dilemma decade **senza effetti** (`dismiss_dilemma`), non «rifiuto». Motivo: il rifiuto dà un premio (doping: +10 reputazione, +8 prestigio, −600 €; giovane: +6 resilienza, +8 forma), quindi «chiudi = rifiuta» renderebbe Esc la scelta migliore. Il piano diceva «applica l'opzione rifiuta (effetti negativi minimi)»: L'utente ha confermato il 2026-11-20 la lettura «chiudi = ignora» (nessun effetto).

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

## 15. Un atleta può correre più gare nello stesso meeting? — ✅ DECISA il 2026-11-19 (tetto FIDAL: max 2 gare individuali + 1 staffetta)

**Decisione dell'utente (2026-11-19):** vale il tetto del regolamento FIDAL (art. 3.3 e 5.7), non «più gare senza tetto». Implementato: `MAX_INDIVIDUAL_EVENTS`, `GameState.lineup_problem`, validazione in `set_event_athlete`, `build_default_lineup` e `normalize_assignments` (vecchi salvataggi). La raccomandazione originale qui sotto è superata; la T5 di `TICK.md` (gara e allenamento nella stessa settimana) resta com'è.

Oggi sì: `build_default_lineup` lo preferisce evitare ma non lo vieta (`generator.py:546`), `set_event_athlete` non valida né duplicati né genere (`game_controller.py:370-374`); la fatica da gara si somma e poi si allena nella stessa settimana (`TICK.md` T5).
- **Raccomandazione:** consentire più gare per atleta, validare il genere/Prima Squadra nel controller, documentare T5 come voluto. **DA CONFERMARE.**
- **Alternativa:** un solo evento individuale per atleta e meeting.
- **Cosa cambia:** `game_controller.set_event_athlete` + test; per l'alternativa anche `build_default_lineup`.

---

## Q16 — Set di discipline e ordine di introduzione — ✅ 800 m FATTO il 2026-11-19 (Alto e Disco restano da fare)

**Fatto:** 800 m come seconda specialità di Mezzofondo: `EVENTS`, curva `_score_to_mark` (ancore **stimate**), fisico ideale, viste PyQt 2D/3D, vecchi salvataggi (rivali e convocazioni riempiti al caricamento). Prerequisito «max 2 individuali + 1 staffetta» fatto (Q15). L'800 m è anche nel **visualizzatore Godot** (geometria, regia, cadenza stimata, gare demo 13-14). **Non fatto:** Salto in Alto, Disco, e la scelta con Q10 (60 m indoor / campestre).

**Raccomandazione.** Aggiungere 800 m come seconda specialità di Mezzofondo, poi Salto in Alto e Disco. Rimandare ostacoli, asta, martello, giavellotto, siepi, marcia, 200 m.

**Alternativa.** Aggiungere solo 800 m e fermarsi; oppure aggiungere tutte le discipline dei CdS regionali (anche ostacoli e concorsi multipli).

**Cosa cambia.**
- 800 m: `entities.EVENTS` + curva in `simulation._score_to_mark` + tarature + costanti Godot (`GODOT_EVENTS`, `DISTANCES_M`, `GUN_AT_BY_KIND`). Impatto medio.
- Alto: modello di prove diverso (asticella, eliminatorie per altezza), vista dedicata. Impatto medio-alto.
- Disco: simile al Peso, costo medio.
- **Prerequisito**: regola «max 2 gare individuali + 1 staffetta per atleta» (art. 3.3 e 5.7 regolamento FIDAL). Senza questa, aggiungere discipline crea ambiguità.
- **Dipende dalla Q15** (un atleta può correre più gare nello stesso meeting?): la Q15 raccomanda di consentire più gare **senza tetto**, mentre il regolamento FIDAL pone il tetto «2 individuali + 1 staffetta». Le due raccomandazioni vanno riconciliate: decidere prima la Q15, eventualmente aggiornandola con il tetto reale.
- **Correlata alla Q10** (Cross e Indoor devono cambiare le discipline?): il 60 m indoor e una gara campestre sono la risposta concreta alla Q10; vanno decisi insieme al set di discipline.

---

## Q17 — Fasce d'età e categorie FIDAL — ✅ in parte FATTA il 2026-11-19

**Fatto (scelta dell'utente: «solo etichetta da `age`»):** `age_category` e riga «Fascia d'età» nella scheda atleta; under 20 esclusi da «Internazionale» (`INTERNATIONAL_MIN_AGE`, formazione, staffette, simulazione). **Non fatto, per scelta:** Allievi convocabili con malus nel Peso (pesi degli attrezzi non verificati) e anno di nascita. Nota: nel gioco i 16-17enni stanno nel vivaio e non gareggiano; un'atleta di 17 anni può però stare già in Prima Squadra.

**Raccomandazione.** Calcolare la fascia d'età da `Athlete.age` (il gioco non ha l'anno di nascita; l'età cresce di 1 a ogni cambio stagione) e mostrarla come etichetta nella scheda atleta, senza salvarla (Cadetti 14-15, Allievi 16-17, Juniores 18-19, Promesse 20-22, Seniores 23+). Opzionale: Allievi (16-17) convocabili nei meeting, con malus nel Getto del Peso per lo scarto di attrezzo rispetto al peso seniores di 7,26 kg (nel CdS Assoluto si usano gli attrezzi seniores, art. 2.3). **DA CONFERMARE:** il peso dell'attrezzo per categoria (per quanto ricordo, Allievi M 5 kg e Juniores M 6 kg; non verificato sul regolamento FIDAL). Under-20 esclusi dal livello «Internazionale».

**Alternativa.** Lasciare tutto come oggi (tutti seniores) o introdurre le categorie complete con attrezzi differenziati (costo alto, migrazioni).

**Cosa cambia.**
- Etichetta: solo vista, zero migrazioni. Impatto basso.
- Convocabilità Allievi: controller + vivaio + malus `body_modifier` per il Peso. Impatto medio.
- Esclusione under-20 da Internazionale: controller. Impatto basso.

---

## Q18 — Nomi e struttura dei meeting — ✅ FATTA il 2026-11-19

**Fatto:** `TIER_DISPLAY_NAMES` / `CompetitionTier.display_name` in tutti i testi mostrati, schermata di avvio compresa; il `value` dell'enum (salvato nel DB) non cambia. Le voci già scritte nel libro mastro e nelle notizie restano con il nome vecchio.

**Raccomandazione.** Dare nomi reali a ogni slot di gara mappando i livelli: Provinciale → «Fase regionale CdS», Regionale → «Finale Bronzo», Nazionale → «Finale Argento», Internazionale → «Finale Oro / Coppa Europa». Solo stringhe in `entities.TIER_CONFIG`.

**Alternativa.** Lasciare i nomi generici attuali.

**Cosa cambia.** Solo stringhe e `TIER_CONFIG`. Impatto basso. Nessuna migrazione.

---

## Q19 — Punteggi tabellari WA/FIDAL come valore derivato — ⏸ RINVIATA il 2026-11-19

**Rinviata su scelta dell'utente:** nessun `models/balance.py` (nome ancora «DA CONFERMARE», QUESTIONS 4) e nessun coefficiente WA finché non si conferma la licenza. Non fatto nemmeno l'allineamento del WR F 1500 m a 3:48,68.

**Raccomandazione.** Tenere la scala interna 42-84 come variabile latente. Aggiungere i punteggi tabellari WA (edizione 2025) come valore derivato, calcolato da una funzione pura `score_to_table_points(event, mark)`. Usarli solo per: spareggio (coincide con Q5), obiettivi stagionali, scheda atleta. NON usarli per i punti squadra (che restano 8...1).

**Alternativa.** Sostituire completamente la scala interna con i punteggi tabellari (costo alto, richiede ri-taratura di tutte le ancore).

**Cosa cambia.**
- Funzione pura + test. Impatto medio.
- **Nota**: verificare licenza/uso dei coefficienti WA prima di implementare.
- Allineare il WR F 1500 m a 3:48,68 (migliorato nel 2025) quando si farà il modulo di bilanciamento (lotto 5.2).

---

## Q20 — DQ staffette 4x400 — ✅ FATTA il 2026-11-19 (valore confermato)

**Fatto:** `RELAY_DQ_MULT` (4x100m ×1,0; 4x400m ×0,5). **Il 0,5 è stato confermato dall'utente il 2026-11-19.**

**Raccomandazione.** Ridurre la probabilità di DQ per la 4x400 rispetto alla 4x100. Nella realtà, il cambio fuori zona nella 4x400 è più raro: i frazionisti arrivano più lenti e il cambio non è lanciato come nella 4x100. **DA CONFERMARE:** l'entità della differenza; la zona di cambio è di 20 m in entrambe le staffette (nella 4x100 con in più 10 m di pre-zona), quindi non è una differenza di zona.

**Alternativa.** Lasciare la stessa funzione `_relay_dq_chance` per entrambe.

**Cosa cambia.** Costante in `simulation._relay_dq_chance` (es. moltiplicatore 0,5 per la 4x400). Impatto basso. Nessun test da aggiornare se il comportamento resta deterministico.

---

## Q21 — Effetto della fase «Gara (Picco)» — ✅ FATTA il 2026-11-19 (valore confermato)

**Fatto:** `PEAK_FORM_BONUS` = +6 al bersaglio di forma, solo nel tick che precede una settimana di gara (la gara usa la forma calcolata lì), senza nuove chiamate all'RNG. **Il +6 è stato confermato dall'utente il 2026-11-19** (resta sotto il +9 dello Scarico). Non fatto: il suggerimento in UI del mesociclo.

**Raccomandazione.** Dare a `GARA` un effetto positivo sulla forma in settimana di gara: bonus al bersaglio di forma (non al punteggio direttamente). Oggi la fase «Gara» è penalizzante (solo ×0,90 di crescita e +2 fatica), il contrario del concetto di tapering/picco. Opzionale: suggerire in UI il mesociclo coerente col calendario (2× Specifica → Gara → Scarico).

**Alternativa.** Lasciare `GARA` senza effetto (stato attuale) o rimuovere la fase.

**Cosa cambia.**
- Modifica del tick in `simulation.py` (bersaglio di forma). Aggiornare `docs/TICK.md` e `docs/BALANCE.md`.
- **Attenzione**: se cambia l'ordine delle chiamate all'RNG, aggiornare i test deterministici.
- Impatto medio.

---

## Q22 — Valuta, rimborsi e scadenze contratto — ✅ FATTA il 2026-11-19

**Fatto:** (1) `$` → `€` e «rimborso spese» per gli atleti (gli allenatori restano «stipendio»). (2) `contract_end_season` (schema v10), durata 1-3 stagioni deterministica, **rinnovo automatico** a fine stagione senza costo (scelta dell'utente: non «mai rinnovato in automatico»); pulsante **«Non rinnovare»** nella scheda atleta (`contract_no_renew`, schema v11): a scadenza l'atleta lascia la società senza la penale di fedeltà dello svincolo (−8); l'ultimo atleta della Prima Squadra si rinnova comunque; formazione e staffette si ricompongono da sole. **Non fatto:** un costo di rinnovo, l'adeguamento del rimborso spese al rinnovo (resta R14).

**Raccomandazione.** (1) Cambiare `$` → `€` e «stipendio» → «rimborso spese» (solo stringhe). (2) Introdurre contratti con scadenza stagionale (1-3 stagioni) e rinnovo automatico salvo decisione del giocatore. Non aggiungere agenti, diritti d'immagine o sponsor tecnici nominali.

**Alternativa.** Lasciare la valuta in dollari e i contratti perpetui (stato attuale).

**Cosa cambia.**
- (1) Stringhe: impatto basso, ma verificare l'effetto sui test che cercano `$`.
- (2) Campo `contract_end_season` in `Athlete`, migrazione, logica di rinnovo nel tick di fine stagione. Impatto medio.


## Q23 — Piano gara di 800m/1500m (PIANOLAVORO B.1) — ✅ FATTA 2026-11-20 (cifre confermate dall'utente)

**Decisioni dell'utente (2026-11-20):** (1) **solo ritmo e scatto**: la «Gestione energia» del piano non c'è, perché l'atteggiamento esistente (Prudente/Normale/Aggressivo) fa già quel lavoro e il piano si somma ad esso; (2) **costo legato alla resistenza**: i punteggi di ritmo e scatto si moltiplicano per un fattore di resistenza relativo alla categoria, e le cifre esatte vanno misurate e proposte prima di fissarle in `BALANCE.md`.

**Scostamenti dal piano (confermati dall'utente il 2026-11-20, insieme alle cifre):** «Veloce + Ultimo giro» = +7 punti e **+25** di fatica (il piano scrive +23, ma le sue cifre sono 10 + 15); «Lento» ha fatica −4 (il piano dice solo «conserva energia»: cifra mia); UI nella scheda Calendario accanto all'atteggiamento e non in `athlete_dialog.py` (il piano è per evento, non per atleta); schema v14 e non v12; il piano è per evento, M e F insieme (come `event_attitude`).

**Cifre confermate** (`entities.py`, blocco «Piano gara»; tabella in `BALANCE.md`, sezione C): `PACE_EFFECTS`, `KICK_EFFECTS`, `STRATEGY_STAMINA_REF` (47/59/72/84 = resistenza media dei mezzofondisti generati per categoria), `STRATEGY_STAMINA_SPAN` 30, `STRATEGY_FACTOR_FLOOR` −0,5.


## Q24 — Rischio nei concorsi (PIANOLAVORO B.2) — 🟡 IN CORSO dal 2026-11-20, **`FIELD_FOUL_LOSS` da confermare**

**Decisione dell'utente (2026-11-20):** «solo rischio, nel modello». Il piano parlava di «altezza/peso iniziale» (non esiste nel lungo e nel peso) e di «rischio fallo» (il modello non simula i tentativi: la vista li ricava dal risultato). Quindi: una scelta per evento (Sicuro/Bilanciato/Aggressivo, M e F insieme come l'atteggiamento) con bonus di tecnica e probabilità di nullo del piano; il nullo toglie una quota fissa dalla misura.

**Scostamenti dal piano:** niente altezza/peso iniziale; nessuna migrazione (la scelta sta nella colonna `race_strategy_json` di v14, chiave `risk`); i «punti di tecnica» sono convertiti in punteggio col peso della tecnica nell'evento (0,35 in entrambi); UI nella scheda Calendario e non in `athlete_dialog.py`; le viste dei tentativi non sono toccate.

**Cifra mia, provvisoria:** `FIELD_FOUL_LOSS` = 3% (quota di misura persa con un nullo: ripiego sul secondo tentativo). Misure (40 partite da 36 settimane, Provinciale, stesso rischio per lungo e peso, piazzamento medio, 1° = 1):

| `FIELD_FOUL_LOSS` | Sicuro | Bilanciato | Aggressivo |
| --- | ---: | ---: | ---: |
| 3% | 2,79 | 2,65 | 2,60 |
| 6% | 2,79 | 2,67 | 2,67 |
| 10% | 2,79 | 2,71 | 2,78 |

Con 3% rischiare conviene sempre e Aggressivo è il migliore; con 6% Bilanciato e Aggressivo si equivalgono; con 10% Aggressivo non conviene più. Il campione è piccolo (differenze di ~0,05 posizioni sono rumore). **Da decidere:** tenere il 3% (rischio quasi sempre conveniente) o salire verso il 6% (scelta davvero tattica)? Chiusa la decisione, la cifra va in `BALANCE.md`.


## Q25 — Cambio nelle staffette (PIANOLAVORO B.3) — ✅ FATTA 2026-11-20 (cifre misurate e confermate dall'utente)

**Decisione dell'utente (2026-11-20):** misurare le cifre invece di prendere quelle del piano alla lettera, e adottare quelle proposte dopo la misura. **Cifre adottate** (`entities.py`, blocco «Cambio nelle staffette»; `BALANCE.md` sezione D): `RELAY_CHANGE_EFFECTS` = Conservativo −1 punto di squadra e −10 punti percentuali di rischio di squalifica; Normale 0 / 0; Aggressivo +2 punti e +10 punti percentuali. I punti percentuali si sommano alla probabilità **finale** (dopo il ×0,5 della 4x400m, Q20) e il risultato è limitato a 0-1.

**Scostamenti dal piano:** (1) «−10% / +15% di rischio DQ» è letto in **punti percentuali**, non come moltiplicatore, e **+15 diventa +10**; (2) il piano non indica la fatica per le staffette e non c'è: le staffette non consumano forma; (3) la scelta è per staffetta e vale per M e F insieme (come l'atteggiamento, il piano gara e il rischio nei concorsi), nella colonna `race_strategy_json` (chiave `change`): **nessuna migrazione**, schema ancora v14; (4) UI nella scheda Staffette e non in `athlete_dialog.py`.

**Perché non le due letture del piano.** Misurate su 10 partite × 40 semi (rose diverse), con numeri casuali comuni, per 6 affiatamenti (20-90), due staffette e due livelli di forza della squadra («forte» = la squadra attuale; «media» = −8 punti a ogni frazione):
- *Come moltiplicatore* (×0,9 / ×1,15): «Aggressivo» guadagna in **tutte** le 24 celle misurate (da +0,1 a +0,7 punti squadra) e «Conservativo» perde quasi sempre. Non è una scelta. Con affiatamento ≥ 60 il rischio base è 0 e un moltiplicatore non costa nulla.
- *Come punti percentuali con +15:* nella 4x100m «Aggressivo» perde sempre (da −0,3 a −0,9) e conviene solo a una squadra media nella 4x400m; con +8 resta sempre vantaggioso in tutta la 4x400m, perché lì la DQ è già dimezzata (Q20) e +2 punti valgono di più (il campo è più sparso).

**Differenza in punti squadra rispetto a «Normale» con le cifre adottate** (differenza appaiata; errore standard tra ±0,02 e ±0,09: sotto ~0,1 non si distingue da zero):

| Caso (affiatamento) | Normale (punti) | Conservativo | Aggressivo |
| --- | ---: | ---: | ---: |
| 4x100m forte (20) | 5,53 | +0,52 | −0,52 |
| 4x100m forte (50) | 7,01 | +0,33 | −0,35 |
| 4x100m forte (90) | 7,79 | −0,07 | −0,57 |
| 4x100m media (20) | 3,82 | +0,16 | −0,10 |
| 4x100m media (50) | 5,34 | −0,01 | +0,09 |
| 4x100m media (90) | 6,56 | −0,26 | −0,16 |
| 4x400m forte (20) | 3,62 | +0,07 | +0,20 |
| 4x400m forte (50) | 4,77 | −0,27 | +0,06 |
| 4x400m forte (90) | 5,82 | −0,29 | −0,04 |
| 4x400m media (20) | 1,69 | −0,02 | +0,12 |
| 4x400m media (50) | 2,32 | −0,22 | +0,27 |
| 4x400m media (90) | 3,25 | −0,30 | +0,35 |

Lettura: «Conservativo» serve nella 4x100m con poco affiatamento (≤ 50) ed è un costo oltre; nella 4x400m quasi non serve, perché la squalifica è già rara. «Aggressivo» è una mossa da squadra che insegue: dannoso per chi è già favorito nella 4x100m, utile a una squadra media nella 4x400m, vicino a zero per una squadra forte nella 4x400m.

**Limiti delle misure (dichiarati):**
- **Affiatamento reale.** Giocando 36 settimane senza gestire le staffette (8 partite) la mediana è circa 40 e solo il 3% (4x100m) o il 16% (4x400m) delle squadre completa supera 60: le righe 20-50 sono le più realistiche. Un giocatore che tiene stabile la formazione arriva più in alto: **non misurato**.
- **Solo categoria Provinciale;** «forte» e «media» sono simulate con uno spostamento delle frazioni, non con rose diverse.
- **Errori standard un po' ottimistici** perché le partite con e senza DQ non restano appaiate (la squadra squalificata salta una estrazione: AUDIT R20). Le medie non ne sono toccate.
- Nelle colonne a +15 punti percentuali il rischio osservato era 12-13% invece del 15% nominale: probabilmente rumore delle estrazioni condivise, **non verificato**.
- Si misurano solo i punti squadra, non premi o prestigio legati al piazzamento.
- **Test manuale della UI non eseguito:** il menu è provato solo da codice offscreen, non con il mouse reale.

## Q26 — Ranking individuale e di società (PIANOLAVORO C.1) — 🟡 IN CORSO dal 2026-11-20, **cifre da confermare**

**Decisioni dell'utente (2026-11-20):** (1) per le classifiche «Top 100 mondiale» e «Top 50 nazionale» il piano si realizza **con atleti sintetici** (di fantasia, che riempiono le classifiche); (2) gli **inviti Diamond League** si separano in un sottopunto **C.1b**, da decidere dopo (oggi il gioco non ha meeting a invito: sarebbe un meeting nuovo con premi e prestigio e un passo nuovo nel tick).

**Cosa c'è** (`models/ranking.py`, scheda «Ranking», riga nella scheda atleta; schema v15): punti per piazzamento nelle gare **individuali** (tabella `RANKING_PLACE_POINTS` × moltiplicatore del livello `RANKING_TIER_MULT`), per atleti del club e dei rivali; decadimento ×`RANKING_DECAY` a ogni meeting per tutti insieme; 100 sintetici per disciplina e sesso (`SyntheticAthlete`) che gareggiano su un campo virtuale con la stessa tabella; classifica mondiale, nazionale (solo `Italia`) e delle società della lega attuale (somma dei punti dei loro atleti). **Non cambia nulla nel gioco**: è informativo; niente effetti su sponsor, premi, inviti.

**Cifre PROVVISORIE (mie, da confermare — `BALANCE.md` §K):** punti 1°…8° = 100, 80, 65, 52, 42, 34, 28, 22 (il piano dà solo «1° = 100, 2° = 80, ecc.»); moltiplicatori 0,10 / 0,25 / 0,50 / 1,00 (Fase regionale CdS / Finale Bronzo / Argento / Oro); decadimento 0,9 a meeting (metà del peso in ~6 meeting, circa sei mesi); campo sintetico: livello dal 94 (1°) al 58 (100°), deriva σ 0,3 a meeting, 7 avversari virtuali, 25% di italiani.

**Misura di coerenza** (100m maschili, medie su 5 campi; «a regime» = piazzamento fisso a ogni meeting, punti = 1° × moltiplicatore ÷ (1 − 0,9)): i sintetici hanno al 1°, 10°, 50°, 100° posto circa 993, 884, 345, 120 punti. Chi **vince sempre** in Fase regionale (100 punti) resta **fuori** dalla Top 100 (posto ~101); in Finale Bronzo (250) arriva circa al 69°; in Finale Argento (500) al ~30°; in Finale Oro (1.000) è 1°. Chi arriva **3°** ogni volta: ~91°, 54°, 22° nei tre livelli alti. La calibrazione è fissata in `test_ranking.py` (`test_calibration_…`): ha senso solo con queste cifre.

**Scostamenti dal piano:** (1) non c'è un «mondo» oltre al campo sintetico e ai rivali della lega (gli altri club e i livelli superiori non esistono come squadre); (2) la **classifica di società** confronta solo le società del **livello attuale**, e le società degli altri livelli non gareggiano mai, quindi hanno sempre 0 punti: **dopo ogni cambio di livello il club tiene i suoi punti (decaduti) e i nuovi rivali partono da zero, quindi per diversi meeting è 1° nella classifica delle società** (difetto di design, da decidere: per esempio simulare punti anche per le società degli altri livelli); (3) le **staffette** non danno punti ranking; (4) il Prototipo li dà, con le sue 3 gare; (5) un rivale che si ritira porta via i suoi punti, il sostituto parte da zero; (6) i sintetici **non invecchiano né si ritirano** (solo una deriva casuale del livello); (7) alla creazione i sintetici partono dai punti a regime attesi, club e rivali da zero: il primo anno la classifica del club è «in costruzione»; (8) il campo sintetico si crea alla creazione della partita (o al caricamento di un salvataggio vecchio); gli stati costruiti a mano (test) non lo hanno e i sintetici restano assenti; (9) il piano mette il ranking in una scheda **della Dashboard**: ho fatto una **pagina a sé** nella barra laterale (Competizioni); (10) il piano chiama il campo `world_ranking_points` e `club_ranking` in `GameState`: i punti sono un dizionario per evento, `ranking_points` (su `Athlete` e `RivalAthlete`), e la classifica di società **non è salvata**, si calcola quando serve.

**RNG (decisione dell'utente, 2026-11-20): i sintetici usano `GameController.rng`**, come vuole la convenzione 3. Prima li avevo fatti estrarre da un flusso derivato con `hashlib` (per non spostare le sequenze); l'utente ha chiesto di usare `r`. Il campo si crea con `rng` alla partita nuova (`_create_fresh_state`) e al caricamento di un salvataggio v14 o precedente (`upgrade_legacy_state`); a ogni meeting i sintetici estraggono da `r` al passo C-13b del tick (`TICK.md`). Lo stato dell'RNG è salvato, quindi ricaricare dà gli stessi risultati (test). **Conseguenza misurata:** tutte le sequenze di estrazioni cambiano a parità di seme; per il seme 7, per esempio, la settimana 2 ora genera un dilemma (prima no) e il test del pulsante «Avanza» si bloccava su un dialogo modale: ora quel test disattiva i dilemmi. Le viste non creano più il campo: non scrivono sul modello.

**Limiti dichiarati:** (1) la creazione del campo costa ~20 ms (1.200 atleti), il meeting ~5 ms; la suite di test è più lenta (da ~29 a ~42 s su Windows); (3) **non provato con il mouse reale**, e lo screenshot offscreen non ha font (si vede il layout, non il testo); (4) le società di altri livelli non hanno classifica.

**Da decidere:** (a) confermare o cambiare tabella punti, moltiplicatori e decadimento; (b) il difetto del punto (2), il club 1° dopo una promozione; (c) **C.1b**, inviti Diamond League: proposta concreta se la vuoi — con il ranking di società sopra una soglia, **un meeting a invito a stagione** con solo premio e prestigio e senza punti di lega (cifre mie, da misurare).
