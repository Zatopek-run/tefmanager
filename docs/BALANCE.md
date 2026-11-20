# BALANCE — costanti di gioco

**Metodo.** (1) Costanti di modulo estratte con `ast` da `entities.py`, `simulation.py`, `generator.py`, `database.py`, `game_controller.py` (esaustivo per quei file). (2) Letterali dentro le funzioni di `simulation.py`, `game_controller.py`, `generator.py` e `entities.py` letti riga per riga e raccolti qui sotto; i letterali di 0/1 usati come indici o clamp banali sono omessi. La lista (2) è **fatta a mano dalla lettura**, non da un'estrazione automatica: non garantisco di non averne saltato qualcuno nelle parti di `generator.py` non lette per intero (elenchi di nomi, parsing del CSV).
**Esclusi esplicitamente:** costanti di presentazione di `views/` (colori, dimensioni, tempi di animazione, curve di movimento di `race_viewer.py`/`race_3d.py`/`field_3d.py`) e di `godot_viewer/`. Non influenzano il risultato di gioco.
**Nessun modulo di bilanciamento esiste**: tutto sotto è sparso nei file indicati.
Unità: **sett.** = per settimana · **stag.** = per stagione · **%** · **pt** = punti (punteggio gara/classifica) · **€** = denaro · **una tantum**.

## A. Entrate e uscite (con formula)

| Voce | Formula | Costanti | Unità | File:riga |
| --- | --- | --- | --- | --- |
| Sponsor società (entrata) | `weekly_sponsor × (0,65 + rep/100 × 0,55) × (0,8 + 0,2 × fedeltà/100)` | `TIER_CONFIG[...]["weekly_sponsor"]` **840/1750/3500/6720** (prima 600/1250/2500/4800: +40%, A.1 2026-11-20) | €/sett. | `simulation.py:1227-1229`; `entities.py:43-68` |
| Sponsor individuali (entrata) | `Σ fans // 4` per atleta ≥18 anni, Prima Squadra | divisore 4, età 18 | €/sett. | `simulation.py:1230` |
| Quote tesserati (entrata) | `member_fees_weekly` | 450 (mai modificato) | €/sett. | `entities.py:785`, `game_controller.py:185` |
| Rimborsi spese atleti (uscita; campo `weekly_wage`) | `Σ weekly_wage` Prima Squadra, infortunati inclusi | `senior_wage = clamp(WAGE_BASE_ADULT 55 | WAGE_BASE_PROSPECT 45 + overall×WAGE_PER_OVERALL 2,3; WAGE_MIN 52; WAGE_MAX 520)` (**−45%** dal 2026-11-20, A.1; prima 100|80 + overall×4,2 tra 95 e 950; vale per atleti creati o promossi da ora, i salvataggi esistenti tengono i rimborsi già scritti) | €/sett. | `simulation.py:1231`; `generator.py:410-413` |
| Staff medico/mentale (uscita) | `Σ weekly_cost` degli assunti | Fisio 300, Medico 340, Mentale 220 | €/sett. | `simulation.py:1232`; `generator.py:470-500` |
| Stipendi allenatori (uscita) | `40 + round(Σ max(0, v−40) × 2,2)` | 40, 40, 2,2 | €/sett. | `entities.py:211-212`; `simulation.py:1233` |
| Gestione palestra (uscita) | `livello × 40` | 40 | €/sett. | `entities.py:159`; `simulation.py:1234` |
| Interessi sul debito (uscita) | `ceil(−budget × 0,05)` se `budget < 0` | 0,05 | %/sett. | `entities.py:168`; `simulation.py:1338-1341` |
| Premi gara (entrata) | `prize_base × {1:1,0; 2:0,60; 3:0,35; 4:0,15}` per piazzamento (staffette idem) | `prize_base` **1500/3500/7500/15625** (prima 1200/2800/6000/12500: +25%, A.1) | €/gara | `simulation.py:890,897,1010`; `entities.py:43-68` |
| Biglietti (entrata, solo casa) | `spettatori × TICKET_PRICE`; `spettatori = min(posti, (300 + prestigio×4 + ordine_tier×900) × (0,6 + rep/250) × U(0,85;1,15) [×0,7 pioggia all'aperto])` | prezzi 4/6/9/14 | €/gara | `simulation.py:598-607`; `entities.py:162-167` |
| Bonus promozione (entrata) | `+PROMOTION_BONUS` alla chiusura della stagione se l'esito è PROMOZIONE; voce «Bonus promozione» nel libro mastro (categoria «Premi Gara») | `PROMOTION_BONUS` 5000 | € una tantum | `simulation.py: close_season`; `entities.py` |
| Trasferta (uscita, solo fuori) | `travel_cost` | 350/750/1500/3000 | €/gara | `simulation.py:1050`; `entities.py:43-68` |
| Seduta di recupero (uscita) | fisso | 250 | € una tantum | `game_controller.py:303` |
| Manutenzione pista (uscita) | fisso | 900 (+25 condizione) | € una tantum | `game_controller.py:332,337` |
| Ingaggio atleta (uscita) | giovane: `max(300, potenziale×9)`; adulto: `max(500, overall×30)` | 300, 9, 500, 30 | € una tantum | `generator.py:656-659` |
| Osservatori vivaio (uscita) | `SCOUTING_FEES[dopo] − SCOUTING_FEES[prima]` | tabella 0,0,150,350,600,1000,1500,2200,3000 | € per ricerca | `entities.py:156`; `game_controller.py:77-82` |
| Ampliamento palestra (uscita) | `(livello+1) × 2500` | 2500, max 5 | € una tantum | `entities.py:157,175-176` |
| Ampliamento tribune (uscita) | `500 × {3 se <5000; 4 se <10000; 6}` `+ 500` | +500 posti, max 20000 | € una tantum | `entities.py:160-161,179-182` |
| Ingaggio allenatore (uscita) | `1500 × tier` | tier 1-5 → 1500…7500 | € una tantum | `entities.py:207-208`; `game_controller.py:631` |
| Dilemma «doping» accettato | `+1800` | | € | `game_controller.py:778` |
| Dilemma «doping» rifiutato | `budget = max(0, budget − 600)` (**azzera il debito**) | 600 | € | `game_controller.py:798` |
| Dilemma «giovane» accettato | `+1000` | | € | `game_controller.py:807` |
| Dilemma «giovane» rifiutato | `budget = max(0, budget − 300)` (**azzera il debito**) | 300 | € | `game_controller.py:825` |
| Fondo iniziale | Prototipo 10000; Carriera 18000 (`GameState` ha 12000 di default) | | € | `game_controller.py:154,162`; `entities.py:776` |
| **Non esistono** | incasso da cessione, costo tribune, revisione stipendi | | | AUDIT §6 |

## B. Classifica, tempo, stagione

| Nome | Valore | Unità | File:riga | Effetto |
| --- | --- | --- | --- | --- |
| `TEAM_POINTS` | 1:8 … 8:1 | pt | `entities.py:171` | Punti squadra per posizione |
| Bonus prestigio squadra | 1°:10, 2°:6, 3°:3 | pt prestigio | `simulation.py:1038` | A fine meeting |
| `prestige_table` | 1:35, 2:22, 3:14, 4:7, 5:3, altro 1; +5 se record | pt prestigio | `simulation.py:891,898,1011` | Per gara |
| `fan_mult` | per ordine tier: 3, 6, 12, 25 | fan | `simulation.py:724` | `max(0, 9−posto) × fan_mult + 5 (PB) + 10 (record)` (`:900`) |
| `PROMOTION_SPOTS` / `RELEGATION_SPOTS` | 2 / 1 | posti | `entities.py:623-624` | Verdetto di lega |
| Settimane per fase | 12 (letterale) | sett. | `simulation.py:1375` | Rotazione fase |
| Settimane per stagione | 36 (letterale, separata) | sett. | `entities.py:843`; `tabs.py:396-397` | Conto alla rovescia verdetto |
| Gara ogni | 4 sett. | sett. | `entities.py:926,930` | `week % 4 == 0` |
| Alternanza casa/trasferta | `(week // 4) % 2 == 1` | — | `entities.py:910` | Casa |
| Prototipo | 8 sett., 2 gare (solo testo) | sett. | `entities.py:934-936` | Non fa terminare il gioco |
| `TIER_CONFIG[..]["opponent_skill"]` | 42/56/70/84 | pt livello | `entities.py:43-68`; `generator.py:584` | Livello medio rivali; vedi CLAUDE.md per le ancore di `_score_to_mark` |
| `RIVAL_RACE_SIGMA` | 4,5 | pt | `entities.py:546` | Variabilità giornaliera rivali |
| `RIVAL_RETIREMENT_AGE` | 33 | anni | `entities.py:547` | Ritiro certo (da 31: 30%/stag. `simulation.py:667`) |
| `RIVAL_SEASON_INFLATION` | 0,8 | pt/stag. | `entities.py:548` | Reclute più forti ogni stagione |
| `RIVAL_TREND_SNAPSHOTS` | 13 | istantanee | `entities.py:549` | Storia livello (ogni 4 sett., `simulation.py:648`) |
| Deriva rivali | ≤23: +0,13; ≤27: +0,05; ≤29: 0; ≥30: −min(0,3; 0,08×(età−29)); rumore σ 0,15 | pt/sett. | `simulation.py:628-647` | Sviluppo rivali (positiva ×ambizione) |
| Ambizione rivali | creazione U(0,8;1,25); se battuto +0,04 (max 1,6); se avanti di >8 pt −0,02 (min 0,6); ritorno 20%/stag.; offset `+= (amb−1)×1,5` | — | `generator.py:641`; `simulation.py:662-663,682-690` | Crescita rivali |
| Offset club | `gauss(0; 3,0)`; skill rivale `gauss(base; 5,5)` | pt | `generator.py:642,590` | Qualità iniziale |
| Reclute rivali | età 18-22 | anni | `simulation.py:671` | |

## C. Gara: punteggio e atteggiamento

| Nome | Valore | Unità | File:riga | Effetto |
| --- | --- | --- | --- | --- |
| `ATTITUDE_EFFECTS` | Prudente: −2,0 pt / fatica +4 / infortunio 0,005 / σ 0; Normale: 0 / 7 / 0,02 / 0; Aggressivo: +2,5 / 11 / 0,05 / σ 2,0 | pt, fatica, prob., σ | `entities.py:144-148` | Atteggiamento |
| Infortunio in gara | `att.injury + max(0, fatica−60)×0,004`; ×0,55 medico; ×0,7 Resiliente | prob. | `simulation.py:756-760` | Ritiro |
| Stop dopo ritiro | `randint(1,3) (+1 Aggressivo)` sett.; forma −15 | sett. | `simulation.py:766,768` | |
| Bonus casa | +1,0 | pt | `simulation.py:782,954` | |
| Meteo | Pioggia −1,8; Caldo −0,8 | pt | `simulation.py:531` | |
| Doping | +6,5 pt in gara; +10 forma; 24%/sett. controllo positivo → 4 sett. di stop, forma 25 | pt, % | `simulation.py:532,288,327-330` | |
| σ giornaliera atleta | Impulsivo senza mentale 5,6; Perfezionista 3,0; altri 3,8 | pt | `simulation.py:535-537` | |
| `expected_event_score` | `base + 4,0 (specialità) / −3,5 + (forma−60)×0,24 − max(0,fatica−62)×0,26 + (pista−75)×0,06 + build` | pt | `simulation.py:546-552` | |
| `BODY_MOD_MAX/MIN` | +1,2 / −4,0 | pt | `simulation.py:132-133` | Modificatore fisico (`BODY_IDEALS[_F]`, `:118-131`; penalità `0,7×(|dh|+|db|)`, `dh=Δcm/6`) |
| Tempo atleta da punteggio | rette per evento e sesso (es. 100m M `12,95 − norm×3,16`, tetto 9,58) | s/m | `simulation.py:467-519` | Vedi `CLAUDE.md` (curve tarate) |
| Vento | legale ≤ +2,0; 100m −0,055 s per m/s; Lungo +0,08 m per m/s | m/s | `simulation.py:751,479,486,513` | |
| Range vento | Ventoso U(0,6; 3,3); Pioggia U(−1,4; 1,5); altro U(−0,8; 2,5) | m/s | `simulation.py:560-563` | |
| Pista | usura −randint(1,3)/sett.; −3 per meeting in casa; stato Ottimale ≥80, Standard ≥55; clamp 25-100 | % | `simulation.py:1366,1048,716-718` | Condizione pista |
| Normalizzazione | `norm = clamp(score/100; 0,15; 1,18)` | — | `simulation.py:474` | |
| `PACE_EFFECTS` (B.1, Q23) | Lento −2,0 pt / fatica −4; Medio 0 / 0; Veloce +3,0 / +10 | pt, fatica | `entities.py` (blocco «Piano gara») | Ritmo iniziale 800m/1500m, **confermato 2026-11-20** |
| `KICK_EFFECTS` (B.1, Q23) | Nessuno 0 / 0; Ultimi 200m +2,0 / +8; Ultimo giro +4,0 / +15 | pt, fatica | `entities.py` | Scatto finale 800m/1500m |
| `STRATEGY_STAMINA_REF` / `_SPAN` / `_FACTOR_FLOOR` | rif. resistenza 47 / 59 / 72 / 84 (Prov./Reg./Naz./Int.); ampiezza 30; minimo −0,5 | resistenza, fattore | `entities.py` | Fattore f = clamp((resistenza − (rif − span/2)) / span; minimo; 1): 0,5 per la media della categoria. Moltiplica i punti di ritmo e scatto, **non** la fatica |
| `FIELD_RISK_EFFECTS` (B.2, Q24) | Sicuro 0 pt tecnica / 0%; Bilanciato +1 / 5%; Aggressivo +3 / 15% | punti di tecnica (× peso tecnica 0,35 = pt), prob. nullo | `entities.py` (blocco «Rischio nei concorsi») | Lungo e peso; cifre del piano |
| `FIELD_FOUL_LOSS` (B.2, Q24) | 3% — **PROVVISORIA, cifra mia** | quota della misura | `entities.py` | Perdita con un nullo (ripiego sul secondo tentativo). Misure in Q24 |

## D. Staffette

| Nome | Valore | Unità | File:riga | Effetto |
| --- | --- | --- | --- | --- |
| `RELAY_LEG_WEIGHTS` | 0,24 / 0,24 / 0,24 / 0,28 | peso | `entities.py:256` | Ultima frazione |
| `RELAY_CHANGE_COOLDOWN_WEEKS` | 4 | sett. | `entities.py:257` | Limite cambi |
| Penalità cambio | `int(harmony × 0,75)` (duplicata) | ×0,75 | `game_controller.py:757`; `simulation.py:198` | −25% moltiplicativo |
| Affiatamento iniziale | 30 | 0-100 | `entities.py:531` | |
| Crescita affiatamento | +4 (+6 se gareggia); +2 (+6) con riserva; −2 se mancano | pt/sett. | `simulation.py:252-257` | |
| Riserva in gara | `harmony − 15`; DQ +3% | pt, % | `simulation.py:945,224` | |
| Probabilità DQ | `(max(0, (60 − harmony) × 0,006) + 3% se riserva) × RELAY_DQ_MULT[staffetta]` (4x100m ×1,0; 4x400m ×0,5 **confermato dall'utente il 2026-11-19**, Q20) | % | `simulation.py:224`, `entities.py` | |
| Bonus tempo | `(harmony−50)×0,08 + gauss(0; 2,5)` | pt | `simulation.py:952` | |
| Staffette rivali | `gauss(skill; 4,0)`; 50 se manca l'atleta | pt | `simulation.py:969-970` | |
| Definizioni | 4x100 base 50,4 s span 11,2 min 36,8; 4x400 229/50/174 (F 55,0/11,8/40,8 e 250/53/195) | s | `entities.py:230-255` | Mappa punteggio→tempo |
| Punteggio frazione | `base + (forma−60)×0,15 − max(0,fatica−62)×0,2 + build×0,5` | pt | `simulation.py:168-172` | |

## E. Allenamento, fatica, infortuni

| Nome | Valore | Unità | File:riga | Effetto |
| --- | --- | --- | --- | --- |
| Fatica per allenamento | Resistenza +randint(11,16); Esplosiva +13-19; Tecnica +9-14; Riposo −(24-32) | pt/sett. | `simulation.py:402,406,409,412` | |
| Modulazione periodizzazione | Prep. specifica +4; Gara +2; Scarico `min(f−14; −10)` | pt | `simulation.py:415-420` | |
| Perfezionista | +2 fatica; ×1,15 crescita | | `simulation.py:424,368` | |
| Fisioterapista | −7 fatica; guarigione ×2 con prob. 0,55 | | `simulation.py:426,340` | |
| Stile di vita | recupero `(sonno+nutrizione)/2−70)×0,12`; forma `×0,18` | | `simulation.py:427,269` | |
| Crescita periodizzazione | 1,05 / 1,25 / 0,90 / 0,45 | × | `simulation.py:373-377` | |
| 800m (Q16) | retta `T = a − norm×b` da `MIDDLE_800M_CURVE` (M 144,5 / 46,4, F 160,0 / 45,2), tetto WR 100,91 s / 113,28 s; ancore **STIMATE** a score 42/56/66/70/84; pesi `stamina 0,40, speed 0,38, technique 0,15, strength 0,07`; fisico ideale M 178 cm BMI 21,0, F 168 cm BMI 19,8 (stime); traguardo storico M 1:53,00 / F 2:08,00 | s | `simulation.py` `_score_to_mark`, `BODY_IDEALS*`; `entities.py` | |
| Effetti collaterali dell'800m | una gara in più per divisione: più premi per meeting e più punti squadra in palio; un modo in più di completare l'obiettivo «traguardo storico» | | | |
| Contratti | durata `1 + (id + stagione) % CONTRACT_MAX_SEASONS` (1-3 stagioni), rinnovo automatico a fine stagione, nessun costo, salvo «non rinnovare» (l'atleta se ne va, senza penale di fedeltà); il vivaio non ha contratto (Q22) | stagioni | `simulation.py`, `entities.py` | |
| Tetto gare per atleta | `MAX_INDIVIDUAL_EVENTS` = 2 gare individuali (tra quelle attive) + 1 staffetta (già unica per atleta); FIDAL art. 3.3 e 5.7 | gare | `entities.py` | |
| Età minima Internazionale | `INTERNATIONAL_MIN_AGE` = 20 (Q17): gli under 20 non gareggiano in «Finale Oro / Coppa Europa» | anni | `entities.py` | |
| Fattore età | <picco 1,30; nel picco 1,00; oltre 0,65 | × | `simulation.py:354-359` | |
| Probabilità miglioramento | `min(0,95; base × età × coach × pers × periodo × palestra × headroom)`; `headroom = max(0,20; (cap−cur)/45)`; salto +2 con 25% | % | `simulation.py:384-391` | |
| `base_chance` | Resistenza 0,70 (+Resilienza 0,28, Velocità 0,25 per mezzofondisti); Esplosiva 0,56+0,56; Tecnica 0,72 (+Velocità 0,22) | % | `simulation.py:398-409` | |
| Forma bersaglio | fatica ≥80: `48−(f−70)×1,25`; ≥58: `74−(f−52)×0,75`; altrimenti `86−f×0,32`; +6 riposo, +9 scarico, +6 `PEAK_FORM_BONUS` (solo fase Gara nel tick che precede una gara, `weeks_until_competition == 1`), +4 mentale, +2 leader, +10 doping; fusione 35/65 | pt | `simulation.py:269-292` | |
| Infortunio da carico | se fatica ≥68: `min(0,50; (f−64)×0,011 × resilienza(≥0,35: 1,35−res/100) × 1,25 Impulsivo × 0,7 Resiliente × 0,55 medico × 1,25 ≤17 anni)`; durata randint(1,3) (−1 fisio); forma −18 | % | `simulation.py:443-462` | |
| Recupero da infortunio | fatica −randint(22,30) (+8 fisio) | pt | `simulation.py:342` | |
| Declino età | `years_past_peak × 0,10`, max 0,5, −1 a velocità/resistenza/forza | %/sett. | `simulation.py:434-440` | |
| `peak_age_range` | Velocità 20-27; Salti 20-28; Mezzofondo 21-30; Lanci 23-32 | anni | `entities.py:87-96` | |
| `YOUTH_TRAINING_MULT` | 1,5 | × | `entities.py:152` | |
| `GYM_TRAINING_BONUS_PER_LEVEL` | 0,06 | × per livello | `entities.py:158` | |
| Recupero manuale | fatica −20; sonno/nutrizione +10; forma +6 | pt | `game_controller.py:311-314` | |

## F. Allenatori

| Nome | Valore | File:riga |
| --- | --- | --- |
| `MAX_SPECIALIZED_COACHES` / `MAX_YOUTH_COACHES` | 6 / 2 | `entities.py:193-194` |
| `COACH_COMFORT_LOAD` | 6 atleti | `entities.py:195` |
| `COACH_BASE_SKILL` | 25 | `entities.py:196` |
| `COACH_MAX_TIER` | 5 | `entities.py:197` |
| `COACH_NO_COACH_MULT` | 0,6 | `entities.py:198` |
| Abilità per tier | primaria `60+7×tier`, secondaria primaria−10 | `entities.py:201-204` |
| Bonus allenatore | `(0,6 + abilità/100 × 0,8) × moltiplicatore carico` | `simulation.py:366` |
| Moltiplicatore carico | `max(0,5; 1 − 0,08 × (carico−6))` | `simulation.py:98` |
| Decadimento abilità | 10%/sett. → −1 a un'abilità sopra 25 | `simulation.py:1356-1360` |
| Assunzione | 1 per settimana | `game_controller.py:621` |

## G. Vivaio, scouting, mercato, fedeltà

| Nome | Valore | Unità | File:riga |
| --- | --- | --- | --- |
| `YOUTH_SQUAD_MAX` | 8 | atleti | `entities.py:151` |
| `WEEKLY_SCOUTING_POINTS` | 8 | pt/sett. | `entities.py:153` |
| `SCOUTING_SEARCH_POINTS` | 2 (+1 per filtro) | pt | `entities.py:154` |
| Ricerca vivaio | 1-4 ragazzi; età 14-17; potenziale 68-95 (≥85 con filtro: 85-97) | | `game_controller.py:500`; `generator.py:399,402` |
| Pool mercato | 5 (4 studenti 15-17 anni + 1 adulto) | | `game_controller.py:396`; `generator.py:368` |
| Fedeltà | acquisto −6 (<21) / −12; cessione −8; +2/sett.; sponsor `0,8+0,2×fed/100` | pt | `game_controller.py:419,454`; `simulation.py:1369,1228` |
| Reputazione | scandalo −25; doping accettato −18; rifiutato +10 | pt | `simulation.py:1305`; `game_controller.py:779,799` |
| Prestigio | scandalo −45; dilemma rifiutato +8 | pt | `simulation.py:1306`; `game_controller.py:800` |
| `STAND_EXPANSION_SEATS` / `STAND_MAX_SEATS` | 500 / 20000 | posti | `entities.py:160-161` |
| `GYM_MAX_LEVEL` | 5 | livelli | `entities.py:157` |

## H. Debito e dilemmi

| Nome | Valore | File:riga |
| --- | --- | --- |
| `DEBT_WEEKLY_INTEREST` | 0,05 | `entities.py:168` |
| `BANKRUPTCY_THRESHOLD` | −20000 | `entities.py:169` |
| Probabilità dilemma | settimane 3 e 7 sempre; altrimenti 22% | `generator.py:671` |
| Tipo dilemma | settimana dispari → doping, pari → giovane | `generator.py:675` |
| Effetti dilemma | vedi §A | `game_controller.py:776-832` |
| Doping: forma | +14; giovane: fatica +22 / resilienza +6 + forma +8 | `game_controller.py:782,809,827-828` |
| Obiettivo bilancio | Prototipo 8000; Carriera 10000 | `simulation.py:570` |

## I. Generazione atleti

| Nome | Valore | File:riga |
| --- | --- | --- |
| Livello base per tier | 42/54/67/79 (−10 giovane); stat `gauss(base+bias; 7)` | `generator.py:209-218` |
| Bias per specialità | Velocità: 12,−6,3,6; Mezzofondo: 2,14,−8,4; Salti: 9,−6,4,12; Lanci: −8,−6,15,10 (ordine velocità, resistenza, forza, tecnica) | `generator.py:220-227` |
| Resilienza | `gauss(62|56; 12)` in [25; 96] | `generator.py:229` |
| Potenziale | giovane 80-96; adulto `max(stat)+randint(4,18)` in [55; 98] | `generator.py:230-234` |
| Fatica/sonno/nutrizione/forma iniziali | 6-20; 65-90; 65-90; `70 − fatica×0,35 + randint(−4,7)` | `generator.py:236-239` |
| Età iniziale | giovane 15-17; adulto `[max(18; picco_min−2); picco_max+2]` | `generator.py:203-207` |
| Nazionalità | 70% Italia | `generator.py:149` |
| Corpo | `_BODY_PROFILE` (altezza media, σ 6, BMI); donne −11 cm, BMI −1,4 (−1,8 lanci); crescita `(18−età)×2,5` | `generator.py:155-175` |
| Rosa iniziale | Prototipo 10; Carriera 16 (8 M + 8 F) | `generator.py:276,312` |
| Valutazione complessiva | `Athlete.overall`: pesi per specialità (es. Velocità 0,42/0,23/0,15/0,12/0,08) | `entities.py:436-470` |

## J. Altre

| Nome | Valore | File:riga |
| --- | --- | --- |
| Stato iniziale `GameState` | reputazione 70, pista 82, quote 450, budget 12000 | `entities.py:776-785` |
| Stato iniziale nuova partita | reputazione 75, pista 82, quote 450 | `game_controller.py:182-185` |
| Limiti log | notizie 70, traguardi 40, transazioni 400 | `simulation.py:1412-1414` |
| `SCHEMA_VERSION` | 10 | `database.py` |
| `RELAY_DQ_MARK`, `DNF_MARK` | stringhe | `entities.py:258,172` |
