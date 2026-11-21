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

## Q27 — Obiettivi del Board ed esonero (PIANOLAVORO C.2) — 🟡 IN CORSO dal 2026-11-20, **cifre da confermare**

**Decisioni dell'utente (2026-11-20):** (1) una stagione è **fallita** se si centrano **meno di 2 obiettivi su 3**; (2) l'esonero arriva con **due stagioni fallite di fila** (una stagione centrata azzera il conto); (3) «Bilancio positivo» = **non chiudere la stagione in perdita**, cioè budget a fine stagione almeno pari a quello di inizio stagione.

**Cosa c'è** (`models/board.py`, schema v16): in **Carriera** il Board assegna tre obiettivi a inizio stagione (alla partita nuova e a ogni cambio stagione, dopo l'eventuale cambio di livello): (a) chiudere tra i primi N della lega; (b) bilancio non in perdita; (c) almeno 2 record sociali (individuali e di staffetta). A fine stagione `close_season` li giudica (prima del cambio di livello e **prima** del bonus promozione, che non aiuta il bilancio), aggiorna il conto delle stagioni fallite e, al secondo fallimento di fila, imposta `GameState.fired`: game over come il fallimento (il tick non parte più, il pulsante diventa «Esonerato dal Board», nessun nuovo obiettivo). Il verdetto sta in `SeasonEndResult` (e nella storia delle stagioni) ed è mostrato in fondo alla finestra di fine stagione; poi una finestra elenca gli obiettivi della stagione che comincia. La Dashboard mostra l'avanzamento e un avviso dopo una stagione fallita. **Nessuna chiamata all'RNG** (nessun cambio all'ordine delle estrazioni).

**Cifre PROVVISORIE (mie, da confermare — `BALANCE.md` §L):** posto massimo in lega per livello 3 / 4 / 5 / 5 (Fase regionale CdS / Finale Bronzo / Argento / Oro; il piano dice «Top 3 (difficoltà basata su categoria)»), 2 record, 2 obiettivi su 3, 2 fallimenti di fila.

**Misura (autopilota, nessuna azione del giocatore, 30 partite, Provinciale, 2 stagioni):** il **piazzamento in lega non è mai centrato** (posti finali 5-8: formazione automatica, nessun allenamento mirato), il **bilancio** nell'83% delle stagioni, i **record** nel 100%. La stagione è fallita nel 17% dei casi (solo quando salta il bilancio) e 2 partite su 30 sono esonerate entro la fine della 2ª stagione. **Lettura:** chi non fa nulla non viene licenziato quasi mai, perché bilancio e record bastano (2 su 3) senza il piazzamento. I record sono quasi regalati: in una società senza record ogni primato lo è, e l'autopilota ne stabilisce anche nella 2ª stagione. **Non misurato:** giocatore attivo che gestisce rosa e allenamenti, livelli oltre il Provinciale, il 3° anno in poi.

**Scostamenti dal piano:** (1) il piano chiede «Top 3 in lega» uguale per tutti: qui dipende dal livello; (2) niente `BoardExpectations` in `entities.py`: gli obiettivi sono i `SeasonObjective` esistenti con soglia (`target`) e avanzamento (`value`) in più, e il conto delle stagioni fallite e l'esonero stanno in `GameState` (`board_failed_streak`, `fired`) e in `board_json`; (3) in Carriera spariscono gli obiettivi di prima («promozione», «traguardo storico», «bilancio sopra 10.000»), sostituiti dai tre del Board; il Prototipo non ha stagioni e tiene i suoi; (4) i salvataggi precedenti a C.2 tengono gli obiettivi vecchi fino a fine stagione, **che non viene giudicata**; (5) la finestra degli obiettivi si apre a ogni nuova stagione, **non alla partita nuova** (lì si vedono dalla Dashboard).

**Limiti dichiarati:** (1) un salvataggio di un esonerato non è segnalato nell'elenco della schermata iniziale (come invece «SOCIETÀ FALLITA»); (2) non c'è modo di continuare dopo l'esonero (nessun nuovo club): è un game over, come il fallimento; (3) **non provato con il mouse reale**; (4) un dilemma non cambia nulla sul verdetto, ma il rifiuto del dilemma azzera un budget negativo (AUDIT R7) e può quindi aiutare il bilancio.

**Da decidere:** (a) confermare le cifre; (b) **il Board è troppo facile da soddisfare senza giocare**: con 2 su 3, bilancio e record bastano. Opzioni: tenere così; rendere il piazzamento obbligatorio; alzare i record (3 o 4, o solo record che battono un primato esistente); (c) dopo l'esonero: solo game over, o l'offerta di un altro club (non c'è nel piano).

## Q28 — Ritiro e post-carriera (PIANOLAVORO C.3) — 🟡 IN CORSO dal 2026-11-20, **cifre da confermare**

**Decisioni dell'utente (2026-11-20), date prima di scrivere codice:** (1) «infortunato grave» = **almeno 3 infortuni nella stessa stagione**, con un contatore per atleta (`season_injuries`, schema v17); (2) l'ex atleta che diventa allenatore è
un'**offerta da accettare** (pulsante), non un'assunzione automatica; (3) le abilità dell'allenatore si ricavano dagli **attributi dell'atleta**, non dal PB; (4) probabilità di ritiro **33 anni 25%, 34 anni 50%, 35+ certo**.

**Cosa c'è** (`models/career.py`, `simulation.retire_veterans`, schema v17): al cambio stagione, in Carriera, dopo il +1 d'età e prima del rinnovo dei contratti, ogni atleta della Prima Squadra può ritirarsi (33 anni 25%, 34 anni 50%,
35+ certo; da 30 anni con 3+ infortuni in stagione 35%, mai sotto la chance dell'età). L'ultimo atleta della Prima Squadra non si ritira. Chi si ritira esce dalla rosa (formazione e staffette si ricompongono) e va nella lista
«Ex atleti» della scheda *Albo & Record*. Un ex atleta su dieci (10%) si offre come allenatore: lo si assume a €750 con le sue abilità (principale e secondaria 55-85 dai suoi attributi), con le regole di `hire_coach` (1 a settimana, massimo
6 specializzati); l'offerta scade al cambio stagione successivo.

**Cifre PROVVISORIE (`BALANCE.md` §M):** tutte quelle sopra, più 30 anni come età minima per il ritiro da infortuni, 35% di chance da infortuni, €750 di ingaggio, tetto di 100 ex atleti ricordati.

**Scostamenti dal piano:** (1) il piano scrive `is_retired` in `Athlete`: **non** si tiene l'atleta ritirato in `state.athletes` con un flag (ogni ciclo su atleti, stipendi, formazione, staffette, ranking, contratti, carichi degli
allenatori e caricamento del DB avrebbe dovuto filtrarlo): l'`Athlete` esce dalla lista e resta un ricordo `RetiredAthlete` (in `game_state.retired_json`); (2) il piano mette la logica in `generator.py` («generare allenatori da atleti
ritirati»): le regole pure stanno in un modulo nuovo `models/career.py` (senza Qt e senza RNG, come `board.py`) e l'orchestrazione in `simulation.py`; la creazione del `Coach` è in `GameController.hire_retired_coach`; (3) il piano dà
le abilità «basate su PB»: scelta dell'utente, dagli attributi; (4) la lista è nella scheda *Albo & Record*, non in una scheda nuova.

**Misura (autopilota, nessuna azione del giocatore, 6 partite, 8 stagioni):** la Prima Squadra passa da 16 a 3-8 atleti e i ritirati sono 8-13 (AUDIT R24); le offerte da allenatore sono rare (0-1 vive per stagione).

**Limiti dichiarati:** (1) **non provato con il mouse reale** (solo test offscreen sui metodi collegati ai pulsanti); (2) le estrazioni del ritiro stanno prima di quelle dei rivali (TICK 16b'): una partita con atleti di 33+ anni
cambia la sequenza dell'RNG dopo il primo cambio stagione; (3) l'età di partenza della rosa (19-32 anni) fa sì che molti veterani si ritirino già nelle prime stagioni; (4) un ex atleta non torna e non ha altro seguito oltre al ruolo di
allenatore: niente dirigente, niente ex campione che porta fan o sponsor.

**Da decidere:** (a) confermare le cifre; (b) **chi rimpiazza i ritirati**: oggi solo il giocatore (vivaio, scouting, mercato), quindi in autopilota la squadra si svuota; opzioni: tenere così; far arrivare qualche giovane a costo zero al
cambio stagione; abbassare le probabilità; (c) se l'ex campione allenatore debba avere un effetto in più (sponsor, fan, prestigio).


## Q29 — Agenti con personalità e relazione (PIANOLAVORO D.1) — 🟡 IN CORSO dal 2026-11-20, **cifre da confermare**

**Decisioni dell'utente (2026-11-20), date prima di scrivere codice:** (1) la personalità agisce, in D.1, sull'**ingaggio al tesseramento** (il rimborso spese settimanale non cambia); (2) **un agente per più atleti, relazione
condivisa** (non un agente a testa come nel piano alla lettera); (3) la relazione sposta la richiesta di **±15 punti percentuali** (50 = nessuna modifica, 100 = −15, 0 = +15).

**Deviazione dalla convenzione 3** (RNG): `models/agents.py` non usa `GameController.rng` ma un `random.Random(intero)` locale seminato da `zlib.crc32` di id e nome (come `_backfill_bodies`): il motivo è non spostare le estrazioni del tick e non avere stato da salvare; la personalità di un agente, che decide il prezzo, è però una funzione di id e nome e non del seme della partita.

**Cosa c'è** (`models/agents.py`, schema v18): `Agent` (nome, personalità, relazione 0-100), `Athlete.agent_id`, `GameState.agents`. Aggressivo +20%, Ragionevole 0, Leale −10% sull'ingaggio; relazione +3 per rinnovo, +1 per podio
individuale, −10 per svincolo, −5 per mancato rinnovo, −2 per ogni atleta della Prima Squadra rimasto fermo (mai convocato in una stagione); a ogni cambio stagione si avvicina a 50 di un quarto della distanza (passo minimo 1). Il mercato mostra l'agente e la richiesta; la scheda atleta mostra l'agente. Nessuna estrazione dall'RNG
della partita: l'ordine del tick e le sequenze casuali non cambiano (solo righe nuove senza `r`: TICK 8b, 16b0, C3).

**Cifre PROVVISORIE (`BALANCE.md` §N):** tutte quelle sopra, i pesi delle personalità (30/50/20), la potatura (al più 20 agenti senza clienti), `AGENT_NEW_SLOTS` = 2.

**Scostamenti dal piano:** (1) il piano elenca `models/simulation.py` («trattative influenzate da agente») e `views/dialogs.py`: le trattative vere ci sono solo con D.2, qui l'agente agisce sull'ingaggio una tantum;
(2) **non** si usa `generator.py` per generare gli agenti: stanno in un modulo nuovo `models/agents.py` (senza Qt e senza RNG, come `career.py`); (3) un agente cura più atleti (scelta dell'utente); (4) il piano non prevede
la **deriva verso 50** a ogni stagione: l'ho aggiunta perché la misura mostrava la relazione satura a 100 (AUDIT R26); la REVIEW_REALISMO e Q22 sconsigliavano gli agenti per una ASD laziale (vivono solo nell'élite): il piano
dell'utente prevale, ma resta una scelta di realismo.

**Misura (autopilota, 6 partite, 8 stagioni):** 5-8 agenti; relazione media 67-77 a regime (senza deriva 90-100 dalla 4ª-5ª stagione). In autopilota quasi nessuno resta fermo: la penalità «resta fermo» è coperta dai
test ma **non misurata in partita**.

**Limiti dichiarati:** (1) **non provato con il mouse reale** (solo test offscreen e lettura di tabelle ed etichette); (2) l'agente non ha ancora effetto sul rimborso settimanale, sui rinnovi o sugli sponsor (AUDIT R26); (3) i
candidati del mercato si rigenerano a ogni apertura dopo una ricarica (R5) e **il loro agente non è stabile**: `assign_agent` sceglie `crc32(nome) % (agenti noti + AGENT_NEW_SLOTS)`, quindi dipende da quanti agenti esistono in
quel momento, e un agente nuovo prende `max(id)+1` (nome e personalità derivano da quell'id): dopo una ricarica o una potatura lo stesso candidato può avere un agente diverso, con un'altra richiesta; (4) i nomi degli agenti pescano dagli stessi elenchi degli
atleti (può capitare un omonimo); (4b) nome e personalità di un agente dipendono solo da id e dal nome del primo assistito, non dal seme della partita: lo stesso atleta nello stesso ordine ha lo stesso agente in partite diverse; (5) il vivaio e i ragazzi scoperti con lo scouting hanno un agente ma non pagano ingaggio, quindi la sua personalità non incide su di loro finché non vengono promossi (e la promozione è gratuita).

**Da decidere:** (a) confermare le cifre; (b) se l'agente debba pesare anche sul rimborso spese settimanale o sul rinnovo (oggi no, vedi R26); (c) se serva un effetto della relazione oltre al prezzo (sconto sul rinnovo, atleti
che rifiutano di firmare con chi ha una relazione pessima).


## Q30 — Trattative, clausola rescissoria e bonus (PIANOLAVORO D.2) — 🟡 IN CORSO dal 2026-11-20, **cifre da confermare**

**Decisioni dell'utente (2026-11-20), date prima di scrivere codice:** (1) **un giro di controfferta, senza RNG** (richiesta → offerta → controfferta → accetto/rifiuto); (2) la clausola rescissoria è una **penale in scala per lo svincolo anticipato**
(20 settimane di rimborso spese, non i 50.000 € fissi del piano: irraggiungibili con 18.000 € di budget iniziale); (3) il **bonus per risultati è facoltativo in trattativa**, con importi in scala (€300 / €600 / €1.000) e uno sconto sull'ingaggio uguale al bonus.

**Cosa c'è** (`models/market.py`, schema v19): `Negotiation` (macchina a stati: aperta → controfferta → accettata/rifiutata), `Terms` (ingaggio e bonus), flessibilità dell'agente per personalità e relazione, `NegotiationDialog` nel mercato, `Athlete.record_bonus` (salvato),
`Athlete.release_clause_cost` (calcolata) e pagamento del bonus nel meeting (TICK 14b). Dettagli in `GAME.md` §5.18, cifre in `BALANCE.md` §O.

**Cifre PROVVISORIE:** tutte quelle di §O (flessibilità 5/15/25% ± relazione, minimo €100, bonus 300/600/1.000, clausola 20 settimane).

**Scostamenti dal piano:** (1) il piano mette `transfer_clause` in `Athlete` come campo e il sistema in `market.py` (fatto) e `simulation.py`: la clausola è una **proprietà calcolata** (nessuna colonna: dipende solo dal rimborso spese e cambia da sola con esso); (2) «Paghi 50.000 € per liberare un atleta» e
«10.000 € se fa record sociale» sono scalati (scelta dell'utente); (3) il piano non dice che cosa succede ai bonus quando il contratto scade: **scadono al rinnovo** (decisione mia, non dell'utente); (4) il testo della domanda sul bonus diceva che l'agente «lo conta come valore e abbassa la richiesta»
e che «conviene se pensi che il record arrivi»: con lo sconto **uguale** al bonus è il contrario (conviene se pensi che **non** arrivi, AUDIT R27).

**Limiti dichiarati:** (1) **non provato con il mouse reale** (solo test offscreen sui metodi collegati ai pulsanti e screenshot); (2) non si tratta il **rinnovo** (resta automatico, Q22) né la clausola (uguale per tutti, non negoziabile); (3) rifiutare non ha costo e la trattativa ha una mossa vincente senza rischio: AUDIT R27; (4) la clausola rende lo svincolo
molto costoso (AUDIT R27) e può bloccarlo per mancanza di fondi; (5) il bonus vale solo per i record **individuali**.

**Da decidere:** (a) confermare le cifre; (b) **la trattativa ha una mossa vincente senza rischio** (offrire €100 e accettare la controfferta paga sempre la soglia, AUDIT R27): opzioni: l'agente rompe sotto una percentuale della richiesta con un costo in relazione; la controfferta cade tra soglia e richiesta; un'offerta troppo bassa costa relazione; (c) se il bonus debba avere uno sconto **maggiore** del bonus o pagarsi solo battendo un record già esistente (oggi i primi record sono quasi regalati, R22); (d) se il rinnovo del contratto debba passare da una trattativa.


## Q31 — Finanze dettagliate (PIANOLAVORO D.3) — 🟡 IN CORSO dal 2026-11-20, **cifre da confermare**

**Decisioni dell'utente (2026-11-20), date prima di scrivere codice:** (1) lo **sponsor con obiettivo** si valuta **a fine stagione** e vale per la successiva (fuori dai primi 5 della lega → −20% dello sponsor società); (2) merchandising e diritti TV con **cifre piccole**
(extra del 5-15%: fan ÷ 40 + prestigio ÷ 20; TV €3.000 a meeting in casa Internazionale); (3) grafici **disegnati con QPainter**, nessuna dipendenza nuova.

**Cosa c'è** (`models/finances.py`, schema v20): bilancio mensile (4 settimane, dal libro mastro, per categoria, ultimi 36 mesi salvati), merchandising settimanale, taglio dello sponsor società, diritti TV, scheda **Finanze** con grafico a barre, elenco dei mesi e dettaglio per categoria. Dettagli in `GAME.md` §5.19, cifre in
`BALANCE.md` §P, ordine del tick in `TICK.md` (6, 14c, 21b). Nessuna estrazione dall'RNG della partita.

**Cifre PROVVISORIE:** tutte quelle di §P.

**Scostamenti dal piano:** (1) il piano mette `monthly_financial_report` in `GameState` e il calcolo in `simulation.py`: il calcolo è in `models/finances.py` (senza Qt, come `career.py`) e il campo si chiama `monthly_reports` (lista di `MonthlyReport`); (2) il tab «Finanze» **esisteva già**: l'ho esteso (due sezioni) invece di crearne uno;
(3) lo sponsor con obiettivo non ha un campo salvato: si legge da `season_history[0]`; (4) il piano parla di «sponsor con obiettivi» al plurale e di grafici «mensili»: un solo obiettivo (top 5) e un solo grafico (entrate/uscite per mese).

**Misura (autopilota, 8 partite):** economia positiva come dopo A.1 (BALANCE §P); taglio sponsor attivo dopo la 1ª stagione in 7 partite su 8 (AUDIT R28).

**Limiti dichiarati:** (1) **non provato con il mouse reale** (solo test offscreen, screenshot e lettura di tabelle); (2) un solo obiettivo di sponsor, sempre «top 5» anche nei livelli alti; (3) niente confronto tra stagioni nel grafico (12 mesi); (4) i bilanci mensili sono solo per la società del giocatore.

**Da decidere:** (a) confermare le cifre; (b) se «top 5» debba cambiare con il livello (in Finale Oro la lega è la stessa di 8 club); (c) se il taglio debba scattare anche a metà stagione; (d) se i diritti TV debbano esistere anche in Nazionale.

## Q32 — Avvio della Carriera senza atleti (richiesta dell'utente, 2026-11-20) — 🟡 IN CORSO, **cifre da confermare**

**Decisioni dell'utente (date prima del codice):** (1) la Carriera nuova parte con **0 atleti** (Prima Squadra e vivaio vuoti); (2) **nessuna settimana gratuita** artificiale: l'avvio segue il calendario, con una **Preparazione** senza gare; (3) **budget iniziale invariato** (18.000), nessun regalo; (4) obiettivi del Board della stagione 1 riscritti come **fondazione**. In risposta a una domanda: la Preparazione si ripete **a ogni stagione** (ciclo da 44 settimane) e l'avvio vuoto vale **solo per la Carriera** (il Prototipo resta con 10 atleti).

**Cosa c'è** (schema v21): `SeasonPhase.PREPARAZIONE` (8 settimane, `SEASON_PREP_WEEKS`, nessuna gara); `GameState.prep_weeks` (per salvataggio: 8 nelle Carriere nuove, **0 nei salvataggi esistenti e nel Prototipo** → il loro calendario da 36 settimane non cambia); aritmetica del ciclo in `GameState` (`season_length`, `season_cycle`, `is_phase_start`, `is_race_week`); meeting con la società senza atleti = **non iscrizione** (nessun costo, nessuna sanzione, messaggio); obiettivi di fondazione (`FOUNDATION_*`: 6 atleti in società, 2 ragazzi nel vivaio, 3 meeting in cui si schiera almeno un atleta) con verdetto solo informativo; stagione 2 con le tre chiavi standard e il posto in lega allargato fino a `BOARD_RAMP_MAX_SLACK` (3) posti in base alla forza della rosa contro i rivali; nessun taglio sponsor e nessuna penalità «resta fermo» dopo la stagione 1; aiuti a schermo per rosa e vivaio vuoti; messaggio iniziale nelle notizie. Dettagli in `GAME.md` §1/§5.1/§5.13, cifre in `BALANCE.md` §Q, ordine del tick in `TICK.md`.

**Scelte mie da confermare:** (a) **`prep_weeks` per salvataggio** invece di un calendario unico: così nessun salvataggio cambia fase; il costo è che i vecchi salvataggi non avranno mai la Preparazione. (b) **Gli allenatori iniziali restano** (uno per disciplina, 4 in tutto, come nell'avvio di sempre) anche senza atleti da seguire: costano il loro stipendio settimanale; staff clinico e impianti sono invariati. Senza allenatori un atleta tesserato si allena a ×0,6. (c) `start_date` di una Carriera nuova è arretrata di 8 settimane (9 feb 2026) perché l'Outdoor si apra ancora il 6 aprile. (d) **Non iscrizione** solo se la Prima Squadra è **vuota**: una squadra con atleti tutti infortunati o non convocati paga trasferta e incassa biglietti come prima. (e) Le cifre di fondazione (6 / 2 / 3) e la formula della stagione 2 (un posto ogni 5 punti di forza sotto i rivali, al massimo 3, sulla media dei migliori 8) sono **provvisorie**. (f) Il rimborso spese a 0 non scrive più la riga «Rimborsi spese atleti (0)» nel libro mastro.

**Conseguenza economica da conoscere (non corretta):** senza atleti entrano sponsor società e quote (circa €900/settimana) e i soli costi sono gli allenatori. In autopilota la cassa sale da 18.000 a circa 53.000 dopo 40 settimane e a circa 100.000 dopo 100: le quote tesserati (€450/settimana) non hanno tesserati dietro e la Preparazione aggiunge 8 settimane di sponsor a ogni stagione. È un tema di bilanciamento (AUDIT R29), non una scelta presa.

**Limiti dichiarati:** (1) **non provato con il mouse reale** (solo test offscreen, tra cui `MainWindow` su una società vuota); (2) la Preparazione non ha ancora effetti propri sull'allenamento (nessun bonus per la fase «Prep. Generale»); (3) un giocatore che non fa nulla arriva alla stagione 2 con l'obiettivo del posto in lega allargato al massimo e rischia l'esonero dalla 3ª stagione se non costruisce la squadra.

**Da decidere:** (a) le cifre di fondazione e della stagione 2; (b) se la Preparazione debba dare un bonus di allenamento o di crescita; (c) se le quote tesserati debbano dipendere dal numero di atleti; (d) se gli allenatori iniziali debbano esserci; (e) se `prep_weeks` debba un giorno estendersi ai vecchi salvataggi al cambio stagione.

## Q33 — Staff con attributi e mercato dello staff (PIANOLAVORO E.1) — 🟡 IN CORSO dal 2026-11-20, **cifre da confermare**

**Cosa c'è** (schema v22, `staff.attributes_json`): attributi 1-20 per ruolo (`STAFF_ATTRIBUTES`: Fisioterapista *competenza*/*recupero*, Medico *diagnosi*/*prevenzione*, Preparatore mentale *motivazione*/*pressione*), funzioni pure in `models/staff.py` (senza Qt, senza RNG), colonna «Attributi (1-20)» nella scheda staff. Cifre e formule in `BALANCE.md` §R. Test: `test_staff_attributes.py` (21, senza Qt), `test_staff_attributes_ui.py` (7), `TestMigrationV22StaffAttributes` (5).

**Scelta di fondo (mia, da confermare):** **calibrazione neutra** — al riferimento `STAFF_ATTR_REF` = 14 ogni effetto è identico a prima di E.1. I tre candidati fissi e i vecchi salvataggi stanno a 14, quindi nessun test e nessun equilibrio di prima si è mosso (572 test precedenti invariati) e le sequenze dell'RNG sono le stesse (TICK.md non cambia). **Verificato contro il commit `ec99dd1` (vale fino alla prima fine stagione: il rinnovo del mercato aggiunge ogni stagione un'estrazione all'RNG, per scelta)** (prima di E.1): partita con tutti e tre i clinici assunti, 6 Impulsivi e 4 atleti molto affaticati, 72 settimane con 3 semi (7, 11, 23): stessa impronta SHA-256 di atleti, budget, notizie e stato dell'RNG nel codice vecchio e nuovo (script locale, non nel repository). I vecchi test da soli non lo provavano: lì lo staff non è mai assunto.

**Risposte dell'utente (2026-11-20, dopo la consegna):** (1) **le cifre vanno bene** (attributi, formule e candidati); (2) **il mercato deve rinnovarsi nel tempo**; (3) **sostituire uno specialista costa la liquidazione del precedente.** Il punto 2 è fatto (`renew_staff_market`, fine stagione, 1 estrazione dell'RNG, `TICK.md` 16d, **fasce e costi miei, provvisori**, `BALANCE.md` §R). Il punto 3 è fatto (`STAFF_SEVERANCE_WEEKS` = 6, **cifra mia, provvisoria**; **mia lettura da confermare:** la liquidazione si paga a ogni licenziamento di un assunto, non solo nelle sostituzioni, altrimenti basterebbe licenziare e riassumere); il punto 2 vedi sotto.

**Decisione dell'utente (2026-11-20, a E.1 già consegnata):** «sì, ora» al **mercato dello staff**: 3 candidati per ruolo con attributi e costi diversi e assunzione esclusiva per ruolo. Fatto subito dopo (`generator.STAFF_CATALOGUE`, `ensure_staff_market` al caricamento dei vecchi salvataggi, assunzione che sostituisce in `GameController.toggle_staff`, scheda raggruppata per ruolo); cifre dei 6 candidati nuovi in `BALANCE.md` §R, **tutte mie e provvisorie**. I test che assumevano 3 specialisti (`test_game`, `test_empty_start_ui`) ora ne attendono 9. Verificato di nuovo contro `ec99dd1` con i tre originali assunti: stessa impronta.

**Scostamenti dal piano:** (1) il piano dice «generare staff con attributi» in `generator.py`: il catalogo è **fisso, senza RNG** (nomi, attributi e costi scritti a mano, stessi in ogni partita), non una generazione casuale: non sposta l'RNG della partita e rende i test deterministici; (2) il piano mette `attributes` dict in `StaffMember` — fatto — ma `skill` (1-5 stelle) resta come etichetta e non pilota più gli effetti; (3) i test «alta competenza riduce gli infortuni» sono statistici su 300-400 semi fissi (deterministici), non su un seme solo.

**Limiti dichiarati:** (1) il mercato si rinnova **solo a fine stagione** e i candidati nuovi non invecchiano, non hanno un ingaggio una tantum, e nessuno scade: un candidato lasciato nel mercato sparisce al rinnovo senza preavviso (il giocatore non lo sa); i 6 candidati nuovi e il rinnovo sono **provati solo con test, non misurati in una partita lunga**; (2) *Diagnosi* agisce solo sul ritiro in gara e *Prevenzione* solo sull'allenamento: è una mia lettura dei nomi del piano; (3) **non provato con il mouse reale** (solo test offscreen e lettura della tabella); (4) lo scatto «−1 settimana» del fisioterapista è a soglia (≥ 8), perché una quantità discreta non si scala senza una nuova estrazione dell'RNG.

**Da decidere:** (a) confermare le cifre (pendenze, tetto 0,95, pavimento 0,20, soglia 8); (b) ✅ deciso: il mercato si rinnova (ma ogni fine stagione va bene? fasce e costi dei candidati sorteggiati?); (c) ✅ deciso: la liquidazione (ma 6 settimane vanno bene? e va pagata anche al semplice licenziamento, come l'ho letta io?); (e) se i senior non siano troppo convenienti: Rinaldi dà guarigioni quasi garantite per €460/sett., misura da fare con l'autopilota prima di E.2; (d) ✅ per E.2: il «riferimento neutro» è semplicemente **non possedere l'impianto** (vedi Q34); ✅ per E.3 (Q35): il riferimento neutro è non avere Academy, scout né regione, e senza scout la fascia del potenziale è quella di sempre.


## Q34 — Impianti avanzati (PIANOLAVORO E.2) — 🟡 IN CORSO dal 2026-11-21, **cifre del piano; manutenzione e arrotondamento da confermare**

**Cosa c'è** (schema v23, `game_state.facilities_json`): quattro impianti una tantum in `GameState.facilities` (`FACILITY_ORDER`): Centro medico €15.000, Centro analisi video €10.000, Palestra pesi €12.000, Campo altura €20.000, con le cifre del piano (−15% infortuni, +5% tecnica, +10% forza, +10% resistenza dei mezzofondisti). Funzioni pure in `models/facilities.py` (senza Qt), acquisto in `GameController.buy_facility` (categoria «Impianto», salvataggio con `_persist()`), quattro schede nella tab «Staff & Impianto». Test: `test_facilities.py` (26, senza Qt), `test_facilities_ui.py` (8), `TestMigrationV23Facilities` (4). Cifre in `BALANCE.md` §S, estrazioni in `TICK.md` (passi 4 e C-3).

**Decisioni dell'utente (2026-11-21):** (1) il «%» del piano è la **probabilità di crescita** (come fa la Palestra), non un bonus diretto alla statistica; (2) **si tengono entrambe** le palestre: la «Palestra» a livelli resta, la «Palestra pesi» è un impianto a parte che si somma.

**Mie scelte, da confermare:** (a) **nessuna manutenzione** (il piano non la indica: è una cifra che spetta a te); (b) **un solo livello** per impianto; (c) il centro medico taglia i tempi con **arrotondamento a caso** (una `r.random()` per infortunio, solo con il centro) e mai sotto 1 settimana: con stop da 1 a 3 settimane il taglio reale è ≈12,5%, non 15%; l'alternativa senza estrazione (arrotondare a soglia) darebbe −33% o niente; (d) il centro medico non accorcia la **squalifica per doping** (4 sett.); (e) i bonus valgono anche per il vivaio; (f) le schede stanno in «Staff & Impianto», non in una tab nuova (il piano dice «tab Infrastrutture»); Palestra e Tribune non sono state spostate (convenzione 7).

**Neutralità verificata:** senza impianti stessa impronta SHA-256 di atleti, budget, notizie e stato dell'RNG contro il commit `40540c5` (3 semi, 72 settimane, i tre clinici assunti; script locale, non nel repository). Con il centro medico cambia solo il numero di estrazioni (una per infortunio).

**Limiti dichiarati:** non misurato in una partita lunga (né l'equilibrio né quando €20.000 diventano raggiungibili); **non provato con il mouse reale** (solo test offscreen e lettura dei pulsanti); il Campo altura vale solo per `Specialty.MIDDLE_DISTANCE`.

**Da decidere:** (a) una manutenzione settimanale (e quanto)? (b) livelli per gli impianti (come la Palestra)? (c) il taglio del 12,5% effettivo va bene o si vuole il 15% pieno (per esempio ritoccando la cifra a 0,18)? (d) una tab «Infrastrutture» separata che raccolga anche Palestra e Tribune? (le quattro schede aggiungono ~125 px alla tab «Staff & Impianto»: a 900 px di altezza le tabelle sotto mostrano poche righe, scorrono.)


## Q35 — Giovanili avanzate (PIANOLAVORO E.3) — 🟡 IN CORSO dal 2026-11-21, **costi provvisori da confermare**

**Cosa c'è** (schema v24, `game_state.academy_level` e `scout_json`): **Academy** a stelle 0-5 (+10% di crescita per stella ai soli ragazzi del vivaio, 5 stelle = +50%, come da piano), **osservatore capo** con attributi *Giudizio potenziale* / *Giudizio attuale* 1-20 e **rete scouting** come filtro della ricerca con tre regioni (Giamaica 20% velocità > 80, Kenya, Nigeria). Logica pura in `models/scouting.py`, azioni in `GameController` (`upgrade_academy`, `hire_scout`, `fire_scout`, `run_youth_scouting(region=…)`), riquadri e filtro nella tab «Vivaio & Osservatori». Test: `test_academy.py` (22, senza Qt), `test_academy_ui.py` (26, Qt offscreen), `TestMigrationV24Giovanili` (4). Cifre in `BALANCE.md` §T.

**Decisioni dell'utente (2026-11-21):** (1) gli attributi dello scout sono **stime con errore**: i ragazzi segnalati si vedono come fasce, strette con uno scout bravo e larghe senza; (2) la rete regionale è un **filtro della ricerca** (+1 punto scouting e una quota in euro), non una rete permanente.

**Mie scelte, da confermare:** (a) **costi**: Academy stella N = N × €4.000 (€60.000 in tutto), osservatore Fabbri/Costa/Sartori €120/260/440 a settimana, quota di regione €800 (il piano non dà cifre); (b) il riferimento neutro: **senza scout la fascia del potenziale è ±8** (identica a prima, `potential_band_display` non toccata) e la qualità attuale (OVR, prima esatta) diventa una fascia di ±5; con attributo 1 = come senza scout, con 20 = ±2 sul potenziale e OVR esatto; (c) Academy parte da 0 stelle (il vivaio di prima) e si somma al ×1,5 di base; (d) l'osservatore si sostituisce o si licenzia pagando la liquidazione (6 settimane, come lo staff clinico); (e) regioni: Giamaica→Velocità, Kenya→Mezzofondo, Nigeria→Lanci (il piano dice «Africa, Giamaica, ecc.»), 20% di talento (dal piano) con qualità 81-90; con una regione la disciplina è fissata e il filtro disciplina non si paga due volte; (f) un **catalogo fisso** di 3 osservatori (come lo staff clinico), niente rinnovo a fine stagione; (g) il piano dice `scout_attributes` in `GameState`: ho usato un `Scout`.

**Neutralità verificata:** senza Academy, scout e regione stessa impronta SHA-256 di atleti, budget, notizie e RNG contro `e2c9c49` (3 semi, 72 settimane, una ricerca di vivaio e un tesseramento; script locale, non nel repository). Senza regione la ricerca estrae esattamente come prima (c'è un test).

**Limiti dichiarati:** non misurato in una partita lunga (né il costo delle stelle né il valore dei talenti); **non provato con il mouse reale** (solo test offscreen e uno screenshot); il tetto 0,95 della crescita limita l'effetto delle stelle sui ragazzi con molto margine; nessun effetto della nazionalità regionale oltre alla bandierina.

**Da decidere:** (a) i costi; (b) l'OVR come fascia anche senza scout va bene, o preferisci tenerlo esatto e dare agli scout solo il potenziale? (c) rinnovo del mercato degli osservatori a fine stagione come per lo staff? (d) altre regioni (Etiopia, Brasile…) o una per disciplina in più? (e) la fascia del mercato e della scheda atleta deve seguire lo scout?


## Q36 — Notizie dinamiche (PIANOLAVORO F.1) — 🟡 IN CORSO dal 2026-11-21, **soglie e tipi da confermare**

**Cosa c'è** (nessuna modifica allo schema): `models/narrative.py` (senza Qt e senza RNG) genera a ogni chiusura di mese al più una riga per tipo: **Allenatore del Mese** (vittoria del meeting del mese), **stampa critica** (conti in rosso; oppure Board con una stagione fallita; oppure ultimo posto nell'ultimo meeting) e **tensione nello spogliatoio** (relazione con l'agente ≤ `NARRATIVE_TENSION_RELATION` = 30). Agganciato al tick dopo il bilancio mensile (`TICK.md` 21c). Test: `test_narrative.py` (20, senza Qt).

**Mie scelte, da confermare:** (a) il **cadenzamento mensile** e la regola «al più una riga per tipo», per non riempire il registro (tetto 70) e non servire uno stato di «già annunciata»; (b) la soglia 30 come «insoddisfatto», perché non esiste un morale per atleta; (c) le tre cause della stampa critica e la loro priorità; (d) «Allenatore del Mese» = vittoria del meeting del mese, senza premio; (e) varianti di frase scelte con `crc32` (nessuna estrazione dell'RNG: nessun test o equilibrio spostato, i 712 test precedenti passano invariati); (f) il record sociale del piano non è stato duplicato, esiste già.

**Scostamento dal piano:** il piano chiede un «feed notizie nella dashboard» in `views/tabs.py`: la Dashboard ha già il feed (`news_list`), quindi non ho toccato la vista.

**Limiti dichiarati:** vedi AUDIT R33; **non provato con il mouse reale**; le notizie nuove non sono state lette in una partita lunga (solo test e un tick di prova).

**Da decidere:** (a) altri eventi da raccontare (stagione, infortuni gravi, ritiri, contratti in scadenza)? (b) la notizia deve ripetersi ogni mese finché dura la condizione? (c) «Allenatore del Mese» deve dare un piccolo bonus di reputazione (con F.2)?


## Q37 — Conferenza stampa (PIANOLAVORO F.2) — 🟡 IN CORSO dal 2026-11-21, **cifre da confermare**

**Proposta dell'utente accettata** («vai con la tua proposta»): conferenza **dopo la gara** con due domande; la risposta sulla prestazione sposta la **reputazione**, quella sul futuro del miglior atleta sposta la **relazione con il suo agente**; chiudere senza rispondere non ha effetti.

**Cosa c'è** (nessuna modifica allo schema, nessun RNG): `models/press.py` (senza Qt), `GameController.press_conference_for` / `answer_press_conference`, `PressConferenceDialog` in `views/dialogs.py` aperto da `MainWindow._show_competition_results` dopo i risultati. Cifre in `BALANCE.md` §U. Test: `test_press_conference.py` (16, senza Qt), `test_press_conference_ui.py` (13, Qt offscreen).

**Mie scelte, da confermare:** (a) il risultato è la classifica a squadre del meeting (primi 2 / ultimi 2 con almeno 4 squadre); (b) la risposta coerente col risultato premia (+2) e quella incoerente costa (−2): dirsi soddisfatti dopo un ultimo posto, o critici dopo una vittoria; la cauta non fa mai male; (c) +3 / 0 / −3 sulla relazione; (d) l'atleta citato è il miglior piazzamento individuale del meeting; (e) una sola conferenza per meeting, in memoria; (f) si può rispondere a una sola domanda.

**Scostamenti dal piano:** (1) niente conferenza **prima** della gara; (2) niente «morale»: non esiste un morale per atleta (vedi AUDIT R34); (3) effetti sulla relazione con l'**agente**, non con l'atleta direttamente.

**Da decidere:** (a) la conferenza pre-gara (sulle attese)? (b) un effetto delle risposte sulla **forma** della squadra (un «morale» minimo)? (c) più domande a seconda degli eventi (record, infortuni, polemiche)? (d) cifre e soglie.


## Q38 — Relazioni tra atleti (PIANOLAVORO F.3) — 🟡 IN CORSO dal 2026-11-21, **cifre da confermare**

**Decisione dell'utente (2026-11-21):** **opzione 1**, senza un morale per atleta: le amicizie e le rivalità agiscono sull'affiatamento di staffetta e, come chimica di squadra, sulla forma di tutti. Insieme: **le partite esistenti sono sacrificabili** (registrato in `CLAUDE.md` e nella memoria dell'assistente): niente vincolo di neutralità o compatibilità per le novità.

**Cosa c'è** (schema v25, `athletes.relationships_json`): `Athlete.relationships` (id dell'altro → −100…+100, simmetrico) in `models/relationships.py` (senza Qt, senza RNG); relazione di nascita deterministica (crc32 degli id) assegnata dal primo tick a ogni coppia della Prima Squadra; +10 / −10 di affiatamento in gara alle staffette con un'amicizia / una rivalità tra le frazioni; chimica di squadra → ±3 al bersaglio di forma; +2 alle coppie che corrono insieme in staffetta; tab «Relazioni» nella scheda atleta. Cifre in `BALANCE.md` §V. Test: `test_relationships.py` (29, senza Qt), `test_relationships_ui.py` (5), `TestMigrationV25Relationships` (4); suite 799 test OK.

**Mie scelte, da confermare:** (a) le relazioni nascono da una funzione degli id (12% amicizie, 6% rivalità, ±40…±90), non da eventi; (b) il +10 / −10 vale per la staffetta, non per coppia; (c) chimica = `0,25 × (amicizie − rivalità)`, tra −3 e +3; (d) +2 per coppia a meeting in staffetta (avvicina anche le rivalità); (e) il piano dice «generare relazioni a inizio stagione»: le coppie nascono al primo tick in cui sono insieme in Prima Squadra, non solo a inizio stagione.

**Scostamenti dal piano:** (1) niente morale generale (vedi sopra); (2) il piano mette `relationships` in `Athlete` — fatto — e chiede la tab nella scheda atleta — fatta.

**Limiti dichiarati:** vedi AUDIT R35; **non provato con il mouse reale** (solo test offscreen e uno screenshot); l'effetto in partite lunghe non è misurato.

**Da decidere:** (a) le cifre; (b) relazioni che nascono da eventi (compagni di allenatore, stesso vivaio, risultati) e che si rompono; (c) citare amicizie e rivalità nelle notizie (F.1) e nelle conferenze (F.2); (d) un morale per atleta (opzione 2), se la chimica deve diventare più di un bonus di forma.


## Q39 — Momenti di gloria (PIANOLAVORO F.4) — 🟡 IN CORSO dal 2026-11-21, **regole da confermare**

**Proposta dell'assistente accettata («ok»):** popup per ciò che esiste nel gioco — record del mondo, momento storico, titolo e promozione, atleta dell'anno — e **fuori** convocazione in nazionale e invito Diamond League (dipendono da C.1b).

**Cosa c'è** (nessuna modifica allo schema, nessun RNG): `models/glory.py` (senza Qt), `WORLD_RECORDS` in `entities.py`, `GameController.glory_moments` (segnale) e `_glory_of`, `GloryMomentDialog` in `views/dialogs.py` e `MainWindow._show_glory_moments`. Regole in `BALANCE.md` §W. Test: `test_glory.py` (19, senza Qt), `test_glory_ui.py` (11, Qt offscreen); suite 829 test OK.

**Mie scelte, da confermare:** (a) record del mondo = la misura raggiunge il tetto già usato dalla simulazione (non c'è una tabella dei record veri); (b) il record sociale **non** apre un popup; (c) atleta dell'anno = più vittorie, poi più podi, nel gioco individuale; (d) i momenti non sono salvati; (e) record del mondo e atleta dell'anno scrivono anche notizia e traguardo; (f) popup uno dopo l'altro, solo dissolvenza; (g) i popup compaiono dopo i risultati e la fine stagione, prima di un dilemma.

**Scostamenti dal piano:** niente nazionale e Diamond League (C.1b); «animazione» ridotta a una dissolvenza.

**Limiti dichiarati:** vedi AUDIT R36; il «test manuale» del piano (record del mondo → popup) **non eseguito con il mouse**: provato solo con test offscreen e misure forzate.

**Da decidere:** (a) i momenti da celebrare (record sociale importante? primo podio? ritiro di un campione?); (b) un'animazione più ricca; (c) salvare i momenti per rivederli (un «albo» della gloria); (d) i criteri dell'atleta dell'anno (livello della gara, ranking); (e) C.1b per aggiungere nazionale e Diamond League.


## Q40 — Lotto G (UI/UX) — 🟡 IN CORSO dal 2026-11-21, **direzione grafica da approvare**

**Decisioni dell'utente (2026-11-21):** (1) ~~nessuna libreria di grafici~~ **revocata lo stesso giorno**: prima scelta QPainter (come `finance_chart.py`) per il prototipo; poi l'utente ha approvato la direzione e **tolto ogni vincolo sulle nuove dipendenze** («disponibile a progetti più radicali»). I grafici del prototipo restano QPainter perché già fatti, non per una regola; (2) risultato «il più rifinito possibile, **a costo di ridisegnare tutta l'interfaccia**»; (3) **schema v26** (`athletes.history_json`) autorizzato, anche se il piano scriveva «Lotto G: nessuna modifica schema»: senza storico non si può fare il grafico forma/fatica né le «ultime 10 gare»; (4) font **Inter** (OFL) incluso in `assets/fonts/` (4 pesi, 1,6 MB con la licenza).

**Cosa c'è (G.1, prototipo della Dashboard):** `views/theme.py` (design system: colori, scala tipografica, spaziature, raggi, caricamento del font), `views/widgets.py` (`TrendChart`, `HeatMapWidget`, `SeasonTimelineWidget`, `StatusPill`, `BadgeDelegate`, `check_icon`, `make_card`), `models/history.py` e `models/dashboard.py` (senza Qt, senza RNG), passo 21d del tick (`TICK.md`), schema v26. Test: `test_history.py` (9), `test_dashboard_data.py` (10), `test_dashboard_ui.py` (20) e 3 di migrazione; suite 871 OK.

**Mie scelte, da confermare:** (a) la tabella dei migliori atleti perde la colonna «Carattere» (sta nella Rosa) per dare spazio ai nomi interi e ai badge; (b) la Dashboard mostra i primi 8 per valore, non tutta la rosa; (c) il semaforo è rosso con un dilemma pendente o un'urgenza, ambra con avvisi, verde altrimenti; (d) la heat map usa il punteggio atteso (`expected_event_score`, pista 75) e un anello segna la gara migliore; (e) il grafico forma/fatica è la **media della Prima Squadra**.

**Direzione grafica del prototipo: approvata (2026-11-21).** **Da decidere:** quanto radicale è il redesign del resto (vedi la proposta in chat: restare su QWidget, oppure QML per le schermate di colpo d'occhio); G.2 (scheda atleta: radar, storico gare, confronto, potenziale) e G.3 (gara in diretta) vengono dopo.

