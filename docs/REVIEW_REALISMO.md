
# Revisione di realismo atletico — Track & Field Manager

Stato esaminato: `main`, commit `c2256a0`, 2026-11-19. Nessun file di codice modificato. Le sigle (a) corretto / (b) approssimato accettabile / (c) implausibile o fuorviante seguono la richiesta.

## Sintesi esecutiva

Il gioco è più fedele di quanto sembri: il modello «1 atleta per evento, 8 società, punti 8…1» è una versione compressa di un vero Campionato di Società FIDAL; vento legale, tempo di reazione incluso nel tempo ufficiale, ordine Outdoor→Cross→Indoor, staffette senza 4x100 indoor sono corretti.
I difetti reali sono pochi e mirati:
1. **La periodizzazione «Gara (Picco)» non dà alcun vantaggio in gara** (solo ×0,90 di crescita e +2 fatica): è penalizzante, il contrario del concetto (c).
2. **Cross e Indoor non hanno contenuto proprio**: niente campestre, niente 60 m; si corre il 100 m indoor (c).
3. ~~**I concorsi mostrano 4 prove**~~ → **fatto il 2026-11-19**: `FIELD_ROUNDS = 6` (con 8 partecipanti o meno il regolamento prevede 6 prove a testa).
4. Il set di discipline lascia il **mezzofondo con un solo evento** (manca l'800 m).
5. «$», «Provinciale» e stipendi da professionisti stonano con una ASD laziale (b/c, costo minimo).

La scala di punteggio 42–84 va tenuta come variabile latente; si consiglia di **affiancarle** i punteggi tabellari WA/FIDAL (che i CdS veri usano per classificare) come valore derivato.

## Area 1 — Discipline e calendario
- **Stato attuale:** 100, 400, 1500, Lungo, Peso + 4x100, 4x400; una sola specialità per gruppo di eventi (Mezzofondo = solo 1500; Lanci = solo Peso). Prototipo: 100/Lungo/1500.
- **Realtà:** il programma del Campionato Regionale di Società Assoluto su Pista 2026 (FIDAL, «di nuova introduzione») ha 2 giornate: 100-400-1500-3000 siepi-110hs/100hs-4x100 + asta-triplo-disco-giavellotto-marcia (g1); 200-800-5000-400hs-4x400 + alto-lungo-peso-martello (g2), con scambi di giornata tra M e F (art. 2.1–2.2). Le 5 discipline del gioco sono **tutte** nel programma reale.
- **Valutazione:** (b) come set; (c) per il solo fatto che **Mezzofondo e Lanci hanno un unico evento**, quindi lo specialista non ha alternative e la «specialità» pesa poco.
- **Proposta (per valore di gameplay, non completezza):**
  1. **800 m** — rende il mezzofondo una scelta (800 vs 1500), ponte naturale tra 400 e 1500, riusa la curva di corsa; è la gara con più iscritti nei club di provincia.
  2. **60 m indoor** (variante del 100 m, solo fase Indoor) — vedi Area 7/Sintesi punto 2; costo minimo.
  3. **Salto in Alto** e **Disco** — secondo evento per Salti e Lanci; entrambi sono in ogni CdS. Alto richiede un modello di prove diverso (asticella), quindi costa più del Disco.
  4. **Rimandare:** ostacoli (nuova dimensione tecnica + vista dedicata), asta, martello, giavellotto, siepi, marcia, 200 m (poco valore aggiuntivo rispetto al costo nelle viste). Giustificazione: «una società di provincia non può coprire tutto» — con 16 atleti iniziali e un solo atleta per evento, già 9 eventi × 2 divisioni superano la rosa.
- **Dipendenza:** più discipline richiedono la regola reale «max 2 gare individuali + 1 staffetta per atleta» (art. 3.3 e 5.7 del regolamento). Oggi il controller non la impone né la vieta (GAME §13, R13).
- **Impatto stimato:** 800 m = `entities.EVENTS` + curva in `_score_to_mark` + tarature + `GODOT_EVENTS`/`DISTANCES_M`/`GUN_AT_BY_KIND` (medio); 60 m = piccolo; Alto/Disco = medio-alto (viste). QUESTIONS: **Q16** (set minimo credibile e ordine di introduzione).

## Area 2 — Categorie e fasce d'età
- **Stato attuale:** tutti seniores; vivaio 14–17 anni che non gareggia; promozione a 18 anni. Rivali 19–32, atleti generati 18–34.
- **Realtà:** Cadetti 14–15, Allievi 16–17, Juniores 18–19, Promesse 20–22, Seniores 23+ (FIDAL). Nel CdS Assoluto possono gareggiare Allievi, Juniores, Promesse e Seniores (art. 3.1), con gli **attrezzi seniores** (art. 2.3).
- **Valutazione:** (b). Il vivaio 14–17 è plausibile (Cadetti + Allievi); la deviazione è che a 16–17 anni si potrebbe già gareggiare.
- **Proposta ibrida (minima):** fascia calcolata dall'età, non salvata (zero migrazioni), mostrata come etichetta. Opzionale: Allievi (16–17) convocabili nei meeting; nel Peso lo scarto di attrezzo si traduce in un malus sul punteggio (si ricicla `body_modifier`). Opzionale: gli under 20 esclusi dal livello «Internazionale».
- **Impatto:** etichetta = solo vista (basso); convocabilità = controller + vivaio (medio). **Q17**.

## Area 3 — Struttura delle gare e calendario
- **Stato attuale:** 1 meeting ogni 4 settimane (9 a stagione), 8 partecipanti, casa/trasferta alternate, 4 livelli.
- **Realtà:** il CdS regionale è una fase unica per regione, poi finali nazionali (dai nomi dei file FIDAL 2026: Oro, Argento, Bronzo; il Bronzo a giugno — **dedotto dai nomi file, non letto**). Le società vere hanno decine di gareggianti per meeting, ranking a somma di 14 punteggi (art. 5.4), classifica per punteggi tabellari, **non** per piazzamenti.
- **Valutazione:** ordine delle fasi **(a)** (Outdoor apr–set → Cross ott–dic → Indoor gen–feb è cronologicamente corretto); una gara ogni 4 settimane **(b)**; etichetta «Provinciale» per una competizione tra società adulte **(b/c)**: il livello provinciale esiste per i giovanili, non per i CdS assoluti.
- **Proposta:** non cambiare la cadenza. Dare un **nome reale** a ogni slot (es. Outdoor: Fase regionale CdS / Campionati regionali / Finale CdS; Cross: campionato di società di campestre; Indoor: meeting/regionali/italiani) e mappare i livelli: Provinciale→«Fase regionale», Regionale→«Finale Bronzo», Nazionale→«Finale Argento», Internazionale→«Finale Oro / Coppa Europa». Solo stringhe.
- **Impatto:** stringhe e `TIER_CONFIG` (basso). **Q18**.

## Area 4 — Punteggi e record
- **Stato attuale:** punteggio interno 0–118 (norm 0,15–1,18); ancore 42/56/66/70/84. Misure ricavate con rette per evento (`simulation.py:467-519`); punti squadra 8…1.
- **Realtà:** la classifica di un CdS si fa **sommando i punteggi tabellari** (Ed. 2007 e succ.; art. 5.1, 5.4); parità risolta col **miglior punteggio singolo di tabella** (art. 5.5). WA ha aggiornato le tabelle nell'aprile 2025.
- **Mappatura delle ancore (calcolata dalle formule del codice, M):**

| Ancora | 100 m | 400 m | 1500 m | Lungo | Peso |
|---|---|---|---|---|---|
| 42 | 11,62 | 53,21 | 4:24,1 | 5,90 | 10,82 |
| 56 | 11,18 | 50,74 | 4:08,2 | 6,53 | 13,76 |
| 66 | 10,86 | 48,98 | 3:56,8 | 6,98 | 15,86 |
| 70 | 10,74 | 48,28 | 3:52,2 | 7,16 | 16,70 |
| 84 | 10,30 | 45,82 | 3:36,2 | 7,80 | 19,64 |

  «84 = internazionale» corrisponde a livello **campione italiano**, non élite mondiale (un tempo da finale di Diamond League vale ~90–95). È una scala di gioco coerente, ma l'etichetta devia. *Stima mia, non confrontata con le progressioni FIDAL 2025.*
- **Record usati come tetto** (confronto con il WR; verificati dove indicato nelle Fonti):

| Evento | Tetto nel codice | WR | Esito |
|---|---|---|---|
| 100 m M / F | 9,58 / 10,49 | 9,58 / 10,49 | ✓ (da memoria) |
| 400 m M / F | 43,10 / 47,60 | 43,03 / 47,60 | M di 0,07 s sopra il WR (verificato M) |
| 1500 m M / F | 3:26,00 / 3:49,00 | 3:26,00 / **3:48,68** | F: WR migliorato nel 2025, tetto di 0,32 s sopra |
| Lungo M / F | 8,95 / 7,52 | 8,95 / 7,52 | ✓ (da memoria) |
| Peso M / F | 23,56 / 22,63 | 23,56 / 22,63 | ✓ (da memoria) |
| 4x100 / 4x400 (pavimento) | 36,8·40,8 / 174,0·195,0 | 36,84·40,82 / 174,29·195,17 | pavimento 0,02–0,29 s **sotto** il WR |

- **Valutazione:** scala interna **(a)** come variabile latente; tetti **(b)** (scarti ≤ 0,32 s, irrilevanti); etichetta «internazionale» **(b)**.
- **Proposta:** (1) tenere la scala 42–84; (2) aggiungere come valore **derivato** i punteggi tabellari WA/FIDAL, usati solo per spareggio (coincide con la raccomandazione di QUESTIONS 5, e con l'art. 5.5), per obiettivi e per la scheda atleta; **non** per i punti squadra (che restano 8…1); (3) allineare il WR F 1500 m a 3:48,68 quando si farà il modulo di bilanciamento (lotto 5.2). Da verificare prima: licenza/uso dei coefficienti.
- **Impatto:** derivato = funzione pura + test (medio); tetti = costanti (basso). **Q19**.

## Area 5 — Regole di gara
- **Falsa partenza:** WA, soglia 0,100 s e squalifica immediata (fonti secondarie). Nel gioco il tempo di reazione è **solo di vista**, uniforme 0,12–0,22 s (`views/race_viewer.py:47`), incluso nel tempo ufficiale come nella realtà (a). Non esistono false partenze: **(b)**, accettabile; se si volesse, andrebbero decise nel modello (Impulsivo senza mentale).
- **Vento:** +2,0 m/s limite di omologazione per 100/lungo ✓ (`simulation.py:751`). Il vento è uno per meeting, tutte le gare (b). Distribuzione: Sereno −0,8…+2,5 (15 % oltre +2,0), Ventoso 0,6…3,3 (48 %): sbilanciata verso il vento a favore (b).
  **Dettaglio fedele:** nel CdS reale valgono anche i risultati con vento >2 m/s per la classifica di società (art. 5.2); il gioco fa lo stesso (piazzamenti e punti restano; PB e record no) → (a).
- **Staffette:** DQ probabilistica da affiatamento (`_relay_dq_chance`, `simulation.py:223`: 18 % all'affiatamento iniziale 30, zero da 60). La stessa funzione serve 4x100 e 4x400: nella 4x400 il cambio fuori zona è molto più raro → **(b/c)**: proposta di fattore ridotto per la 4x400 (**Q20**, costante).
- **Concorsi:** 4 prove (`views/race_viewer.py:43`, `FIELD_ROUNDS = 4`). Con più di 8 partecipanti: 3 prove + 3 ai migliori 8; **con 8 o meno, 6 prove a testa**. Il gioco ha sempre 8 partecipanti ⇒ dovrebbero essere 6. **(c)**, solo vista (esito invariato: `mark_value` è già il migliore). Impatto: `FIELD_ROUNDS`, `generate_attempts`, le 4 righe per atleta in `field_attempts`, test del ritmo dei concorsi (basso-medio). Correzione senza decisione di design.
- **Turni:** i CdS reali corrono a **serie** (art. 3.6) e i concorsi con eliminatorie e finale tra i migliori 8 (art. 3.7, 3.10). Il «meeting da 8 società in una serie» è **(b)**: giusto per un manageriale.

## Area 6 — Allenamento e periodizzazione
- **Stato attuale:** 4 focus × 4 fasi; la fase agisce solo su crescita (×1,05/1,25/0,90/0,45) e fatica (+4/+2/Scarico −14). **`GARA` compare solo in due punti di `simulation.py` (righe 375 e 417)**: non entra nel punteggio gara né nel bersaglio di forma.
- **Realtà (Matveyev/Bompa, concetto generale):** la fase di picco serve a **rendere** al massimo in gara; il carico cala (tapering) e la prestazione sale.
- **Valutazione:** **(c)** per «Gara (Picco)»: oggi è la fase peggiore da scegliere. Il resto, specializzazione per specialità inclusa (pesi per evento in `EVENTS`, picco di età per specialità), è **(a)**. Volume/intensità e microcicli **non servono**: sarebbero complessità senza decisione per il giocatore.
- **Proposta:** (1) dare a `GARA` un effetto sulla forma in settimana di gara (bonus al bersaglio di forma, non al punteggio direttamente); (2) in UI suggerire il mesociclo da 4 settimane coerente col calendario (2× Specifica → Gara → Scarico), zero modello; (3) valutare un focus «Velocità» (oggi la velocità cresce solo con Potenza Esplosiva e, in minima parte, Tecnica/Resistenza).
- **Impatto:** (1) modifica del tick → aggiornare `docs/TICK.md`/`BALANCE.md` e l'ordine RNG se cambia (medio); (2) basso. **Q21** (decisione).

## Area 7 — Fisica della corsa
- **Vento:** −0,055 s per m/s sui 100 m, +0,08 m/(m/s) nel lungo, lineare e simmetrico. Studi (Mureika, Linthorne) danno ~0,05 s/(m/s) intorno a +2 m/s sui 100 m, con effetto più forte del contrario: **(a)** per un manageriale.
- **Altitudine:** non modellata. Nel Lazio non ha senso (nessun impianto >1000 m): **(a)**, lasciare.
- **Pista:** `track_condition` agisce con 0,06 pt per punto (`simulation.py:550`): ±1,5 pt tra 50 e 100, plausibile (a).
- **Curve di velocità:** funzioni pure con arrivo esatto al tempo ufficiale; i tempi **li decide il modello**, quindi la vista non può essere irrealistica sui risultati. Una nota minore: nella 4x400 la regola reale tiene le corsie per i primi ~500 m (prima frazione + prima curva della seconda), mentre Godot rientra «dopo il primo giro» (*da verificare sul regolamento*): solo vista, **(b)**.
- **Indoor:** il 100 m indoor non esiste nella realtà (60 m) e il vento indoor è 0: **(c)** per il 100 m; la proposta è nell'Area 1 (60 m).
- **Impatto:** nessuno, salvo 60 m. Nessuna voce.

## Area 8 — Mercato, staff, sponsor
- **Stato attuale:** ingaggio una tantum + stipendio settimanale, nessuna scadenza; mercato di 5 candidati/settimana; sponsor società + individuali; valuta `$`.
- **Realtà:** una ASD laziale vive di quote, sponsor locali e impianti comunali; gli atleti sono in larga parte non pagati (rimborsi); gli atleti migliori spesso sono in **gruppi sportivi militari** e gareggiano per la società di provenienza solo se autorizzati (art. 4 del regolamento). Contratti pluriennali e agenti riguardano solo l'élite.
- **Valutazione:** **(b)**; la **valuta in dollari** per una società laziale è **(c)** estetico. Stipendi da 95 a 950 a settimana sono fuori scala per una ASD (collegato a QUESTIONS 3, già aperta).
- **Proposta leggera:** (1) `$`→`€` e «stipendio»→«rimborso spese» (solo stringhe, da verificare l'effetto sui test); (2) contratto con **scadenza stagionale** (1–3 stagioni) e rinnovo, che dà peso al mercato senza agenti; (3) *non* aggiungere agenti, diritti d'immagine o sponsor tecnici nominali. Facoltativo: lo sponsor tecnico come sconto in natura.
- **Impatto:** (1) basso; (2) campo + migrazione + test (medio). **Q22**.

## Area 9 — Impianti
- **Stato attuale:** `track_condition` 0–100 (condizione, non livello), palestra 0–5, tribune fino a 20.000 posti.
- **Realtà:** il club di norma **non possiede** lo stadio (impianto comunale); le pedane sono parte della pista; la riabilitazione è già coperta dal Fisioterapista.
- **Valutazione:** **(a)**. Non servono pedane per concorso né vasca. Una sola nota: le tribune a 20.000 posti per un meeting di società sono irrealistiche, ma restano scelta di gameplay (economia dei biglietti).
- **Impatto:** nessuno.

## Area 10 — Coerenza con i dati reali
- `data/societa_atletica_lazio.csv`: **239 società** (come dichiarato). Per provincia: Roma 171 (71,5 %), Latina 26 (10,9 %), Frosinone 22 (9,2 %), Viterbo 15 (6,3 %), Rieti 5 (2,1 %). Le 5 province del Lazio ci sono tutte; la quota segue la popolazione (circa 74/10/8/5/3 %, stime ISTAT a memoria) entro ~2 punti: **(a)**.
- Nessun duplicato di codice o di nome. Anomalie da sapere: 36 società di Roma con codice `RS…` e una società di Rieti con codice `RM276` (codici FIDAL storici, **non verificati**).
- **Categoria:** il CSV non ha colonna di livello/categoria, quindi la domanda «distribuzione per categoria» non è verificabile: i livelli sono assegnati proceduralmente.
- Nota: usa nomi di società **reali** con atleti inventati. Va bene per un gioco privato; da ripensare se distribuito.

## Priorità consigliate (top 5)
1. **«Gara (Picco)» senza effetto** (Area 6, c): è un difetto di significato, costo basso, richiede decisione (Q21).
2. **Contenuto vero per Cross e Indoor**: 60 m indoor e una gara campestre (Area 1/7, c).
3. **Regola «2 individuali + 1 staffetta» e spareggio per miglior punteggio tabellare** (Aree 1 e 4): prerequisito di ogni nuova disciplina e coerente con QUESTIONS 5.
4. **800 m**, poi Alto e Disco (Area 1).
5. **Concorsi a 6 prove** (Area 5, c, solo vista), insieme alle correzioni da stringa: €, «rimborso», nomi reali dei livelli.

## Cosa NON toccare (irrealistico ma legittimo)
- Un solo atleta per evento e divisione, 8 partecipanti, punti 8…1: è la compressione del CdS.
- Una gara ogni 4 settimane e 36 settimane a stagione.
- Scala latente 0–100 con caratteristiche generiche (non unità fisiche).
- Vento unico per meeting; altitudine assente; DQ staffette probabilistica da affiatamento.
- Doping come dilemma, vivaio come crescita ×1,5, fan e sponsor come leve di gioco.
- Nessun «button mashing» né comandi in gara (regola di progetto).
- Sponsor di fantasia; atleti e rivali procedurali.

## Voci QUESTIONS proposte (da aprire a cura dell'utente)
Q16 set di discipline · Q17 fasce d'età · Q18 nomi e struttura dei meeting · Q19 punteggi tabellari derivati · Q20 DQ 4x400 · Q21 effetto della fase «Gara» · Q22 valuta, rimborsi e scadenze contratto. Ogni voce: raccomandazione + alternativa + «cosa cambia», nello stile di `docs/QUESTIONS.md`.

## Fonti: usate e NON usate
**Usate**
- Codice e documenti del progetto: `docs/GAME.md`, `CLAUDE.md`, `models/simulation.py`, `models/entities.py`, `views/race_viewer.py`, `data/societa_atletica_lazio.csv` (analizzato con script).
- FIDAL, [Regolamento del Campionato Regionale di Società Assoluto su Pista](https://calendario.fidal.it/files/83Regolamento_Campionato%20Regionale%20CdS%20Assoluto.pdf) (testo estratto dal PDF scaricato; artt. 2–5).
- World Athletics, [novità sulle tabelle di punteggio 2025](https://worldathletics.org/news/news/scoring-tables-2025) (solo risultato di ricerca).
- Record: [1500 m F, 3:48,68, 5/7/2025](https://www.watchathletics.com/article/13413/faith-kipyegon-smashes-her-own-1500-m-world-record-3-48-68-at-pre-classic); [400 m M, 43,03](https://www.flotrack.org/articles/15744904-mens-400m-world-record-in-track-and-field-heres-what-to-know).
- Falsa partenza, soglia 0,100 s: [articolo tecnico su Devon Allen](https://arxiv.org/html/2506.11460v1) e altre fonti secondarie.

**NON consultate / non verificate** (da dichiarare onestamente)
- Il testo primario del **Rule Book WA 2025/26**: la soglia di 0,100 s e la regola delle 6 prove con 8 o meno concorrenti sono da conoscenza generale più fonti secondarie, non dal testo.
- I record 100 m, 400 m F, 1500 m M, Lungo e Peso: **da memoria**, non confrontati con una fonte 2026 (la pagina olympics.com è andata in timeout). Una notizia di agosto 2026 su «400 m storici» (Paulino) non ho potuto leggerla.
- Matveyev, Bompa, Hay: **non consultati**; il richiamo è a concetti generali, senza citazione di pagina.
- Dati FIDAL 2025 sulle progressioni: **non consultati**; le tarature delle ancore sono mie stime.
- Calendario FIDAL Lazio 2026 completo: solo nomi di file e titoli di ricerca.
- I coefficienti numerici delle tabelle WA: non letti.

