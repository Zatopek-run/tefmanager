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
| Quote tesserati (entrata) | `member_fees_weekly` × min(1, atleti / `MEMBER_FEES_FULL_ROSTER` 10) (Q32c, 2026-11-21: prima fisse) | 450 a pieno regime | €/sett. | `entities.py:785`, `game_controller.py:185` |
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
| `FIELD_FOUL_LOSS` (B.2, Q24) | 6% — **confermata dall'utente, 2026-11-21** (era 3%) | quota della misura | `entities.py` | Perdita con un nullo (ripiego sul secondo tentativo). Misure in Q24 |

## D. Staffette

| Nome | Valore | Unità | File:riga | Effetto |
| --- | --- | --- | --- | --- |
| `RELAY_LEG_WEIGHTS` | 0,24 / 0,24 / 0,24 / 0,28 | peso | `entities.py:256` | Ultima frazione |
| `RELAY_CHANGE_COOLDOWN_WEEKS` | 4 | sett. | `entities.py:257` | Limite cambi |
| Penalità cambio | `int(harmony × 0,75)` (duplicata) | ×0,75 | `game_controller.py:757`; `simulation.py:198` | −25% moltiplicativo |
| Affiatamento iniziale | 30 | 0-100 | `entities.py:531` | |
| Crescita affiatamento | +4 (+6 se gareggia); +2 (+6) con riserva; −2 se mancano | pt/sett. | `simulation.py:252-257` | |
| Riserva in gara | `harmony − 15`; DQ +3% | pt, % | `simulation.py:945,224` | |
| Probabilità DQ | `(max(0, (60 − harmony) × 0,006) + 3% se riserva) × RELAY_DQ_MULT[staffetta]` (4x100m ×1,0; 4x400m ×0,5 **confermato dall'utente il 2026-11-19**, Q20) **+ `RELAY_CHANGE_EFFECTS[cambio][1]`** (B.3), poi limitata a 0-1 | % | `simulation.py` (`_relay_dq_chance`), `entities.py` | Con «Normale» è identica a prima di B.3 (test) |
| `RELAY_CHANGE_EFFECTS` (B.3, Q25) | Conservativo −1,0 pt / −10 punti perc.; Normale 0 / 0; Aggressivo +2,0 pt / +10 punti perc. | pt di squadra, punti percentuali di rischio DQ | `entities.py` (blocco «Cambio nelle staffette») | **Misurate e confermate 2026-11-20.** I punti percentuali si sommano alla probabilità DQ **finale** (dopo `RELAY_DQ_MULT`) e il risultato è limitato a 0-1; i punti si sommano al punteggio di squadra (stessa scala del bonus casa +1,0). Misure e limiti in Q25 |
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
| Fisioterapista | −7 fatica; guarigione ×2 con prob. 0,55 (cifre al **riferimento** degli attributi, vedi §R: E.1 le scala con `recupero` e `competenza`) | | `simulation.py`, `models/staff.py` | |
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
| `SCHEMA_VERSION` | 15 | `database.py` |
| `RELAY_DQ_MARK`, `DNF_MARK` | stringhe | `entities.py:258,172` |

## K. Ranking (PIANOLAVORO C.1, 2026-11-20) — tabella punti, moltiplicatori e decadimento CONFERMATI il 2026-11-21 (QUESTIONS Q26); campo sintetico ancora provvisorio

| Nome | Valore | File |
| --- | --- | --- |
| `RANKING_PLACE_POINTS` | 1°…8° = 100, 80, 65, 52, 42, 34, 28, 22; oltre l'8° 0 | `entities.py` |
| `RANKING_TIER_MULT` | Fase regionale CdS 0,10 · Finale Bronzo 0,25 · Finale Argento 0,50 · Finale Oro 1,00 | `entities.py` |
| `RANKING_DECAY` | 0,9 per meeting (a regime: punti = 10 × guadagno medio del meeting) | `entities.py` |
| `RANKING_WORLD_SIZE`, `RANKING_NATIONAL_SIZE` | 100, 50 (100 è anche la dimensione del campo sintetico per disciplina e sesso) | `entities.py` |
| `RANKING_HOME_NATION` | Italia | `entities.py` |
| `RANKING_SYNTH_ITALIAN_SHARE` | 0,25 | `entities.py` |
| `RANKING_SYNTH_SKILL_TOP`, `…_BOTTOM`, `…_JITTER` | 94, 58, σ 2,0 (livello del 1° e del 100° sintetico, sulla scala del punteggio di gara) | `entities.py` |
| `RANKING_SYNTH_DRIFT` | σ 0,3 a meeting sul livello di ogni sintetico (limiti 30-100) | `entities.py` |
| `RANKING_SYNTH_FIELD` | 8 (7 avversari virtuali) | `entities.py` |
| `SYNTH_WARMUP_MEETINGS` | 3 (oltre alla stima analitica dei punti a regime) | `ranking.py` |
| Livello di un sintetico | il livello di gara con `opponent_skill` più vicino al suo livello | `ranking.py` |

Calibrazione: vedi Q26 (chi vince sempre in Fase regionale resta fuori dalla Top 100; in Finale Oro è 1°).

## L. Obiettivi del Board (PIANOLAVORO C.2, 2026-11-20) — CIFRE PROVVISORIE (QUESTIONS Q27)

| Nome | Valore | File |
| --- | --- | --- |
| `BOARD_LEAGUE_TARGET` | posto massimo in lega: Fase regionale CdS 3 · Finale Bronzo 4 · Finale Argento 5 · Finale Oro 5 | `entities.py` |
| `BOARD_MIN_RECORDS` | 2 record sociali nella stagione (individuali e di staffetta) | `entities.py` |
| Bilancio | budget a fine stagione ≥ budget a inizio stagione (prima del bonus promozione) | `board.py` |
| `BOARD_OBJECTIVES_TO_PASS` | 2 obiettivi su 3: sotto, la stagione è fallita | `entities.py` |
| `BOARD_LEAGUE_REQUIRED` | vero (scelta dell'utente, 2026-11-21): il posto in lega è obbligatorio, senza la stagione è fallita anche con gli altri due obiettivi centrati | `entities.py` |
| `BOARD_MAX_FAILED_STREAK` | 2 stagioni fallite di fila → esonero (game over) | `entities.py` |

Misura in autopilota (30 partite, Provinciale): piazzamento centrato 0%, bilancio 83%, record 100%; stagione fallita 17%; esonerati entro la 2ª stagione 2 su 30 (Q27). Rimisurato il 2026-11-21 (20 partite × 3 stagioni): posto mai centrato, 4 stagioni su 60 fallite per il bilancio, nessun esonero; con il posto obbligatorio quel club sarebbe esonerato in due stagioni.

## M. Ritiro e post-carriera (PIANOLAVORO C.3, 2026-11-20) — CIFRE PROVVISORIE (QUESTIONS Q28)

| Nome | Valore | File |
| --- | --- | --- |
| `RETIREMENT_MIN_AGE` / `RETIREMENT_CHANCE_BY_AGE` | dal 33° anno: 33 → 25% · 34 → 50% (una estrazione a cambio stagione) | `entities.py` |
| `RETIREMENT_CERTAIN_AGE` | 35: ritiro certo | `entities.py` |
| `RETIREMENT_INJURY_MIN_AGE` | 30: età minima per il ritiro anticipato per infortuni | `entities.py` |
| `RETIREMENT_INJURIES_PER_SEASON` | 3 infortuni nella stagione appena chiusa = «infortunato grave» (gli infortuni durano 1-4 sett.) | `entities.py` |
| `RETIREMENT_INJURY_CHANCE` | 35% (mai sotto la chance dell'età) | `entities.py` |
| `RETIRED_COACH_CHANCE` | 10% degli ex atleti si offre come allenatore | `entities.py` |
| `RETIRED_COACH_HIRE_COST` | €750 (livello 1 = 1.500) | `entities.py` |
| `RETIRED_COACH_SKILL_MIN` / `_MAX` | 55-85: abilità principale e secondaria dagli attributi dell'atleta | `entities.py` |
| `RETIRED_COACH_SECONDARY_GAP` | 10: la secondaria vale 10 meno della principale (come `coach_hire_skills`) | `entities.py` |
| `MAX_RETIRED_LIST` | 100 ex atleti ricordati | `entities.py` |
| `EX_CHAMPION_FAN_BONUS` | +20 fan a ogni atleta allenato da un ex campione della società, a ogni cambio stagione (Q28c, cifra mia) | `entities.py` |

Misura in autopilota (6 partite, 8 stagioni, nessun acquisto): Prima Squadra da 16 a 3-8 atleti, 8-13 ritirati, 0-1 offerte da allenatore vive per stagione (Q28, AUDIT R24).

## N. Agenti (PIANOLAVORO D.1, 2026-11-20) — CIFRE PROVVISORIE (QUESTIONS Q29)

| Nome | Valore | File |
| --- | --- | --- |
| `AGENT_FEE_MARKUP` | richiesta sull'ingaggio per personalità: Aggressivo +20% · Ragionevole 0 · Leale −10% | `entities.py` |
| `AGENT_PERSONALITY_WEIGHTS` | peso nella scelta della personalità di un agente nuovo: 30 / 50 / 20 | `entities.py` |
| `AGENT_RELATION_START` / `AGENT_RELATION_MAX` | relazione 0-100, parte da 50 | `entities.py` |
| `AGENT_RELATION_FEE_SPAN` | ±15 punti percentuali sulla richiesta (a 100 −15, a 0 +15) | `entities.py` |
| `AGENT_RELATION_RENEWED` | +3 per atleta rinnovato alla scadenza | `entities.py` |
| `AGENT_RELATION_PODIUM` | +1 per podio in una gara individuale | `entities.py` |
| `AGENT_RELATION_RELEASED` | −10 per svincolo di un atleta della Prima Squadra | `entities.py` |
| `AGENT_RELATION_NOT_RENEWED` | −5 per atleta non rinnovato che lascia | `entities.py` |
| `AGENT_RELATION_IDLE` | −2 per atleta della Prima Squadra mai convocato in una stagione («resta fermo»): né gara individuale né staffetta in formazione | `entities.py` |
| `SEASON_WEEKS` | 36 settimane per stagione (3 fasi da 12; la settimana è continua): serve a ritrovare le gare di una stagione nello storico | `entities.py` |
| `AGENT_REFUSE_BELOW` | 15: sotto questa relazione l'agente rifiuta di trattare (tesseramento dal mercato; Q29c, cifra mia) | `entities.py` |
| `AGENT_RELATION_DRIFT` | 0,25: a ogni cambio stagione la relazione chiude un quarto della distanza da 50 (passo minimo 1 punto: arrotondato per eccesso) | `entities.py` |
| `AGENT_NEW_SLOTS` | 2: un atleta nuovo va a un agente noto o ne ha uno nuovo con probabilità slot/(agenti+slot) | `entities.py` |
| `AGENT_MAX_IDLE` | 20 agenti senza clienti ricordati al massimo | `entities.py` |

Misura in autopilota (6 partite, 8 stagioni, Carriera): 6-8 agenti; **senza** `AGENT_RELATION_DRIFT` la relazione media saliva a 90-100 entro la 4ª-5ª stagione (inutile), **con** 0,25 sta tra 67 e 77 a regime e tocca 100 solo
raramente (Q29). La penalità `AGENT_RELATION_IDLE` non cambia la misura in autopilota (quasi nessuno resta fermo).

## O. Trattative, clausola e bonus (PIANOLAVORO D.2, 2026-11-20) — CIFRE PROVVISORIE (QUESTIONS Q30)

| Nome | Valore | File |
| --- | --- | --- |
| `AGENT_FLEXIBILITY` | quanto sotto la richiesta l'agente accetta: Aggressivo 5% · Ragionevole 15% · Leale 25% | `entities.py` |
| `AGENT_FLEXIBILITY_RELATION_SPAN` | ±10 punti percentuali di flessibilità secondo la relazione (100 → +10, 0 → −10) | `entities.py` |
| `AGENT_FLEXIBILITY_MAX` | 0,50: tetto della flessibilità | `entities.py` |
| `MIN_NEGOTIATED_FEE` | €100: ingaggio minimo trattabile | `entities.py` |
| `AGENT_BREAK_FRACTION` | 0,7: un'offerta sotto il 70% della **soglia** dell'agente rompe la trattativa (Q30b, cifra mia; scala con personalità e relazione) | `entities.py` |
| `AGENT_RELATION_BROKEN` | −3: relazione persa quando la trattativa si rompe (Q30b, cifra mia) | `entities.py` |
| `RECORD_BONUS_OPTIONS` | bonus per record sociale individuale: €300 · €600 · €1.000 (sconto sull'ingaggio uguale al bonus) | `entities.py` |
| `RELEASE_CLAUSE_WEEKS` | 20 settimane di rimborso spese per svincolare un atleta di Prima Squadra (≈ €1.000-10.400) | `entities.py` |

Controfferta: un solo giro, a metà strada tra offerta e richiesta, mai sotto la soglia. Nessuna estrazione casuale.
Esempio (atleta con ingaggio standard €1.770, agente Ragionevole a relazione 50): richiesta €1.770, soglia €1.504, un'offerta di €100 riceve la controfferta €1.504.

## P. Finanze dettagliate (PIANOLAVORO D.3, 2026-11-20) — CIFRE PROVVISORIE (QUESTIONS Q31)

| Nome | Valore | File |
| --- | --- | --- |
| `MONTH_WEEKS` | 4 settimane per mese (9 mesi a stagione) | `entities.py` |
| `MAX_MONTHLY_REPORTS` | 36 bilanci mensili ricordati (quattro stagioni) | `entities.py` |
| `MERCH_FANS_DIVISOR` / `MERCH_PRESTIGE_DIVISOR` | merchandising settimanale = fan Prima Squadra ÷ 40 + prestigio ÷ 20 | `entities.py` |
| `TV_RIGHTS_PER_HOME_MEET` | €3.000 a meeting in casa, solo livello Internazionale | `entities.py` |
| `SPONSOR_TOP_N_BY_TIER` | per livello (Q31b, 2026-11-21, cifre mie): Provinciale 5 · Regionale 5 · Nazionale 4 · Internazionale 3; chiudere la stagione nei primi N della lega **del livello in cui si è giocato** tiene lo sponsor società intero (prima: 5 per tutti) | `entities.py` |
| `SPONSOR_MISS_PENALTY` | 0,20: fuori dai primi N lo sponsor società della stagione dopo vale −20% | `entities.py` |

Misura in autopilota (8 partite, Carriera, nessuna azione): dopo 12 settimane +€6.400/+13.700 (prima di D.3: +€4.700/+15.300, A.1), dopo 36 settimane +€7.000/+19.200, dopo 72 settimane +€12.100/+46.400; il taglio dello sponsor è attivo dopo la prima stagione in 7 partite su 8 (nessuno
arriva tra i primi 5 senza giocare). Il merchandising pesa il 5-10% delle entrate settimanali (Q31, AUDIT R28).

## Q. Avvio senza atleti e Preparazione (2026-11-20) — CIFRE PROVVISORIE (QUESTIONS Q32)

**Budget di partenza: INVARIATO** (fondo 18.000 in Carriera, 10.000 nel Prototipo, staff e impianti come sempre). Cambia che la rosa parte vuota, **senza allenatori iniziali** (Q32d) e con **quote tesserati e sponsor società proporzionali agli atleti** (Q32c: 0 a rosa vuota, pieni da 10 atleti).

| Nome | Valore | File |
| --- | --- | --- |
| `MEMBER_FEES_FULL_ROSTER` | 10: quote tesserati **e sponsor società** pieni da 10 atleti in su (Prima Squadra e vivaio), proporzionali sotto, 0 senza atleti (Q32c, cifra mia; `finances.roster_factor`) | `entities.py` |
| `SEASON_PREP_WEEKS` | 8 settimane di Preparazione a inizio di ogni stagione (solo Carriere nuove, `prep_weeks`); multipla di 4 | `entities.py` |
| `PHASE_WEEKS` | 12 settimane per fase con gare (invariato, prima era un letterale `12`) | `entities.py` |
| `SEASON_WEEKS` | 36 settimane di gara (invariato); la stagione di una Carriera nuova ne ha 44 | `entities.py` |
| `FOUNDATION_MIN_ATHLETES` | 6 atleti in società (Prima Squadra e vivaio) a fine stagione 1 | `entities.py` |
| `FOUNDATION_MIN_YOUTH` | 2 ragazzi nel vivaio | `entities.py` |
| `FOUNDATION_MIN_MEETS` | 3 meeting con almeno un atleta schierato | `entities.py` |
| `BOARD_RAMP_GAP_PER_PLACE` / `BOARD_RAMP_MAX_SLACK` / `BOARD_RAMP_SQUAD_SIZE` | stagione 2: posto in lega richiesto + 1 ogni 5 punti di forza sotto la media dei rivali (media dei migliori 8 atleti), al massimo +3 | `entities.py` |

Gare: con la Preparazione la prima gara è alla settimana 12 (poi ogni 4: 9 gare per stagione, come prima). Stagione di fondazione: nessuna conseguenza del verdetto, nessun taglio sponsor (`SPONSOR_MISS_PENALTY` non si applica dopo la stagione 1), nessuna penalità «resta fermo». Società senza atleti a un meeting: nessuna trasferta, nessun biglietto.

Misura in autopilota (Carriera nuova, nessuna azione): dal 2026-11-21 il budget **resta a 18.000** (nessuna entrata e nessuna uscita: sponsor e quote scalano con gli atleti, nessun allenatore). Prima (seme 1): 18.000 → circa 53.000 dopo 40 settimane e circa 100.000 dopo 100; reputazione e prestigio fermi. È una **conseguenza non voluta** dell'avvio vuoto (entrate senza costi atleti), non una cifra scelta: vedi QUESTIONS Q32 e AUDIT R29.

## R. Staff con attributi (PIANOLAVORO E.1, 2026-11-20) — cifre degli attributi e del catalogo **confermate dall'utente il 2026-11-20** (QUESTIONS Q33); liquidazione, rinnovo del mercato e formula del costo PROVVISORI

Fisioterapista, Medico e Preparatore mentale hanno **due attributi 1-20 ciascuno**. Principio: **al riferimento (`STAFF_ATTR_REF` = 14) ogni effetto è identico a prima di E.1**; i tre candidati fissi e i vecchi salvataggi stanno al riferimento, quindi il bilanciamento non si sposta (c'è un test sull'identità, e i 572 test precedenti passano invariati). Sopra il riferimento l'effetto cresce in proporzione, sotto cala. Nessuna estrazione di RNG in più (il tick non cambia).

| Nome | Valore | File |
| --- | --- | --- |
| `STAFF_ATTR_MIN` / `STAFF_ATTR_MAX` / `STAFF_ATTR_REF` | 1 / 20 / 14 | `entities.py` |
| Fisioterapista · `recupero` | sollievo di fatica a settimana `round(7 × recupero/14)` (`PHYSIO_FATIGUE_RELIEF`); recupero extra da infortunato `round(8 × recupero/14)` (`PHYSIO_INJURY_RECOVERY_BONUS`) | `entities.py`, `staff.py` |
| Fisioterapista · `competenza` | probabilità del doppio passo di guarigione `min(0,95; 0,55 × competenza/14)` (`PHYSIO_HEAL_STEP_CHANCE`, tetto `PHYSIO_HEAL_STEP_CHANCE_CAP`); da `PHYSIO_WEEK_CUT_MIN` = 8 in su toglie 1 settimana a un nuovo infortunio di più di una (sotto non la toglie) | idem |
| Medico · `prevenzione` | moltiplicatore del rischio d'infortunio da sovraccarico in allenamento `max(0,20; 1 − 0,45 × prevenzione/14)` (`DOCTOR_RISK_CUT` 0,45, `DOCTOR_RISK_FLOOR` 0,20): 0,55 al riferimento, ≈0,36 a 20, ≈0,94 a 2 | idem |
| Medico · `diagnosi` | stessa formula, applicata al rischio di **ritiro in gara** | idem |
| Preparatore mentale · `motivazione` | bonus al bersaglio di forma `round(4 × motivazione/14)` (`MENTAL_FORM_BONUS`) | idem |
| Preparatore mentale · `pressione` | deviazione in gara dell'Impulsivo: 5,6 senza preparatore (`IMPULSIVE_SIGMA`); con preparatore `max(3,0; 5,6 − 1,8 × pressione/14)`: 3,8 al riferimento (`CALM_SIGMA`), ≈3,0 a 20 (`MENTAL_SIGMA_FLOOR`) | idem |

**Mercato dello staff** (scelta dell'utente, 2026-11-20: «sì, ora»): 3 candidati per ruolo, dati fissi in `generator.STAFF_CATALOGUE` (nessun RNG), un solo assunto per ruolo (assumerne uno licenzia l'altro, senza penale). Cifre PROVVISORIE; i tre originali (ids 4, 5, 6) restano a 14/14 e costano come prima.

| Ruolo | Junior | Originale (riferimento) | Senior |
| --- | --- | --- | --- |
| Fisioterapista (competenza / recupero) | Greco ★2, 10 / 10, €180 | Neri ★4, 14 / 14, €300 | Rinaldi ★5, 19 / 13, €460 |
| Medico (diagnosi / prevenzione) | Villa ★2, 10 / 10, €200 | Conti ★4, 14 / 14, €340 | Marchetti ★5, 12 / 19, €520 |
| Preparatore mentale (motivazione / pressione) | Bellini ★2, 10 / 10, €140 | Ferretti ★3, 14 / 14, €220 | Fabbri ★5, 12 / 19, €340 |

Il costo sale con gli attributi (circa ×0,6 a 10, ×1 a 14, ×1,5 a 18-19).

**Rinnovo del mercato** (scelta dell'utente 2026-11-20: «il mercato deve rinnovarsi nel tempo»; cifre mie, provvisorie): a ogni **fine stagione** (Carriera, `TICK.md` 16d) lo specialista assunto resta e i non assunti sono sostituiti da candidati nuovi, sempre `STAFF_POOL_PER_ROLE` = 3 per ruolo (assunto compreso: 3 nuovi se non c'è nessuno, 2 se c'è). Profili (`STAFF_TIERS`), attributo estratto a parte nella fascia: **junior** 8-11 (★2), **esperto** 12-15 (★4), **senior** 13-19 (★5); i candidati di un ruolo hanno profili tutti diversi. Costo = base del ruolo (300 / 340 / 220, `STAFF_COST_BASE`) × `(1 + pendenza × (media attributi − 14))`, pendenza 0,10 sotto il riferimento e 0,27 sopra, arrotondato a €10 e mai sotto €100 (media 10 → ×0,6; media 16 → ×1,5; 19/19 → ×2,35). Nomi da `FIRST_NAMES`/`LAST_NAMES` con «Dott.»/«Dott.ssa», mai uguali a chi è assunto. Id nuovi da `max(12, ids presenti) + 1`. **Una sola estrazione dell'RNG della partita per stagione** (seme di un generatore locale). I candidati del catalogo iniziale (ids 4-12) restano fino alla prima fine stagione.

**Liquidazione** (scelta dell'utente 2026-11-20: «sostituire uno specialista costa la liquidazione del precedente»): `STAFF_SEVERANCE_WEEKS` = 6 settimane di compenso di chi esce (es. fisioterapista da €300 → €1.800), cifra **mia e provvisoria**. Si paga a **ogni** licenziamento di un assunto, anche quando è una sostituzione (sennò basterebbe licenziare e poi assumere); assumere in un ruolo scoperto è gratis. Se il budget non basta l'operazione è rifiutata e non cambia nulla. Voce «Liquidazione …» nel libro mastro, categoria «Staff». Salvataggi vecchi: `staff.attributes_json = '{}'` → tutti a 14, e al caricamento si aggiungono i candidati del catalogo che mancano (`ensure_staff_market`, per id, senza toccare chi è già assunto). Se per un salvataggio risultano più assunti dello stesso ruolo (non può succedere dal gioco) vale il migliore.

## S. Impianti avanzati (PIANOLAVORO E.2, 2026-11-21) — CIFRE DEL PIANO, interpretazione e arrotondamento PROVVISORI (QUESTIONS Q34)

Quattro impianti **una tantum** (nessuna manutenzione: il piano non ne indica, aperta in Q34), in `GameState.facilities` (schema v23). **Senza impianti ogni effetto è identico a prima di E.2** (stessa impronta SHA-256 di atleti, budget, notizie e RNG contro `40540c5`: 3 semi, 72 settimane, clinici assunti). Tutte le cifre sono in `entities.py`.

| Impianto | Costo | Effetto | Costanti |
| --- | ---: | --- | --- |
| Centro medico | €15.000 | −15% sul tempo di infortunio, in allenamento e in gara (non sulla squalifica per doping), minimo 1 sett. | `FACILITY_COSTS`, `MEDICAL_CENTER_INJURY_CUT` 0,15, `INJURY_MIN_WEEKS` 1 |
| Centro analisi video | €10.000 | ×1,05 sulla probabilità settimanale di migliorare la Tecnica | `VIDEO_CENTER_TECHNIQUE_BONUS` 0,05 |
| Palestra pesi | €12.000 | ×1,10 sulla probabilità di migliorare la Forza (si somma alla Palestra a livelli) | `WEIGHTS_ROOM_STRENGTH_BONUS` 0,10 |
| Campo altura | €20.000 | ×1,10 sulla probabilità di migliorare la Resistenza, **solo Mezzofondo** | `ALTITUDE_CAMP_STAMINA_BONUS` 0,10 |

- **«%» = probabilità di crescita** (scelta dell'utente, 2026-11-21): il moltiplicatore entra in `chance` prima del tetto `min(0,95; …)`; nessuna estrazione in più.
- **Centro medico, arrotondamento:** gli stop sono 1-3 settimane intere, quindi il taglio si arrotonda a caso (`injury_weeks_with_medical_center`): **una `r.random()` per infortunio, solo con il centro**. Con stop equiprobabili da 1 a 3 il taglio reale è ≈**12,5%** e non 15% (il minimo di 1 settimana mangia il resto: un infortunio di 1 sett. non cambia); su stop lunghi è 15%. Sui tempi: 2 sett. → 1,7 in media, 3 → 2,55.
- Le giovanili (`in_youth_squad`) ricevono i bonus come tutti (il moltiplicatore non distingue la squadra).

## T. Giovanili avanzate (PIANOLAVORO E.3, 2026-11-21) — EFFETTI DEL PIANO, COSTI PROVVISORI (QUESTIONS Q35)

Academy a stelle, osservatore con attributi, rete scouting regionale. **Senza Academy, scout e regione il gioco è identico a prima di E.3** (stessa impronta SHA-256 di atleti, budget, notizie e RNG contro `e2c9c49`: 3 semi, 72 settimane, una ricerca di vivaio e un tesseramento). Costanti in `entities.py`, logica in `models/scouting.py` (senza Qt).

| Cosa | Cifra | Costante | Stato |
| --- | --- | --- | --- |
| Academy · stelle | 0-5 (0 = il vivaio di prima), ×(1 + 0,10 × stelle) sulla probabilità di crescita dei **soli** ragazzi del vivaio (5 stelle = +50%, si somma al ×1,5 di base: ×2,25 in tutto) | `ACADEMY_MAX_LEVEL`, `ACADEMY_GROWTH_BONUS_PER_LEVEL` | del piano |
| Academy · costo | stella N costa N × €4.000 (4k, 8k, 12k, 16k, 20k = €60.000 per le cinque), una tantum, nessuna gestione | `ACADEMY_UPGRADE_COST_STEP` | **provvisorio** |
| Scout · attributi | `potenziale` e `attuale`, 1-20 | `SCOUT_ATTRIBUTES` | del piano |
| Scout · fascia del potenziale | mezza larghezza 8 senza scout o con attributo 1 (la fascia di sempre), 2 con attributo 20, lineare; scarto del centro ±3 (ridotto se la fascia è più stretta, così contiene sempre il valore vero) | `SCOUT_POTENTIAL_BAND`, `SCOUT_POTENTIAL_BAND_MIN`, `SCOUT_BAND_OFFSET` | cifre mie |
| Scout · fascia dell'OVR | mezza larghezza 5 senza scout, 0 (valore esatto) con attributo 20 | `SCOUT_CURRENT_BAND`, `SCOUT_CURRENT_BAND_MIN` | cifre mie |
| Scout · candidati | Fabbri 8/8 €120, Costa 13/13 €260, Sartori 19/16 €440 a settimana; la liquidazione è `STAFF_SEVERANCE_WEEKS` (6) settimane | `models/scouting.py: SCOUT_CATALOGUE` | **provvisori** |
| Rete regionale | filtro in più (+1 punto, quota €800); fissa la disciplina; ogni ragazzo ha 20% di essere un talento con la qualità tipica a 81-90 e potenziale non sotto quel valore; nazionalità della regione | `SCOUT_REGIONS`, `SCOUT_REGION_*` | 20% del piano; quota e regioni mie |

Regioni: Giamaica (Velocità, `speed`), Kenya (Mezzofondo, `stamina`), Nigeria (Lanci, `strength`; non nel Prototipo, che non ha i lanci).

- **Nota sul tetto 0,95:** la probabilità di crescita è limitata a 0,95 (`try_improve`): un ragazzo con molto margine di crescita (potenziale alto, qualità bassa) e cinque stelle può già saturare il tetto, e allora le stelle in più non servono; l'effetto pieno si vede dove la probabilità di partenza è sotto ~0,63.
- **L'OVR e il Potenziale dei ragazzi segnalati si vedono ora come fasce**: cambia rispetto a prima di E.3 solo l'OVR (prima esatto, ora ±5 senza scout); la fascia del potenziale senza scout è identica a quella di sempre (`views.dialogs.potential_band_display`, che non è stata toccata e resta per mercato e scheda atleta). L'ordinamento per OVR e Potenziale nei risultati è disattivato (rivelerebbe il valore vero).

## U. Conferenza stampa (PIANOLAVORO F.2, 2026-11-21) — CIFRE PROVVISORIE (QUESTIONS Q37)

Nessun RNG e nessuna modifica allo schema. Costanti in `entities.py`, logica in `models/press.py`.

| Cosa | Cifra | Costante |
| --- | --- | --- |
| Prestazione «buona» | club tra i primi 2 della classifica a squadre del meeting | `PRESS_GOOD_MAX_PLACEMENT` 2 |
| Prestazione «brutta» | club tra gli ultimi 2 | `PRESS_BAD_FROM_BOTTOM` 2 |
| Squadre minime per giudicare | 4 (sotto, sempre «media») | `PRESS_MIN_TEAMS` |
| Reputazione · buona | soddisfatto +2, cauto +1, critico −2 | `PRESS_REPUTATION["good"]` |
| Reputazione · media | soddisfatto 0, cauto +1, critico 0 | `PRESS_REPUTATION["average"]` |
| Reputazione · brutta | soddisfatto −2, cauto 0, critico +1 | `PRESS_REPUTATION["bad"]` |
| Relazione con l'agente del miglior atleta | punto fermo +3, valuteremo 0, posto non garantito −3 | `PRESS_RELATION` |

Ordine di grandezza: al massimo +2 di reputazione per meeting (9-10 meeting a stagione); la reputazione pesa sugli sponsor (`0,65 + rep/100 × 0,55`) e sulla domanda di pubblico (`0,6 + rep/250`), quindi ±2 vale circa ±1% dello sponsor. Il +3 / −3 sulla relazione è di poco più di una stagione di «resta fermo» (−2 per atleta).

## V. Relazioni tra atleti (PIANOLAVORO F.3, 2026-11-21) — CIFRE PROVVISORIE (QUESTIONS Q38)

Opzione 1 scelta dall'utente: **nessun morale per atleta**; amicizie e rivalità agiscono sull'affiatamento di staffetta e, come «chimica», sul bersaglio di forma di tutti. Nessun RNG. Schema v25 (`athletes.relationships_json`). Costanti in `entities.py`, logica in `models/relationships.py`.

| Cosa | Cifra | Costante |
| --- | --- | --- |
| Coppie che nascono amiche / rivali | 12% / 6% (crc32 degli id: deterministico e simmetrico) | `RELATION_FRIEND_PCT`, `RELATION_RIVAL_PCT` |
| Forza di una relazione di nascita | ±40…±90 | `RELATION_STRENGTH_MIN`, `RELATION_STRENGTH_MAX` |
| Soglie | amicizia ≥ +30, rivalità ≤ −30 | `RELATION_FRIEND_MIN`, `RELATION_RIVAL_MAX` |
| Affiatamento di staffetta in gara | +10 se due frazioni sono amiche, −10 se rivali (non si sommano per coppia; amici e rivali insieme = 0) | `RELAY_FRIEND_HARMONY`, `RELAY_RIVAL_HARMONY` (del piano) |
| Chimica di squadra → forma | `round(0,25 × (coppie amiche − coppie rivali))` nella Prima Squadra, tra −3 e +3 | `CHEMISTRY_FORM_PER_NET_PAIR`, `CHEMISTRY_FORM_MAX` |
| Avvicinamento | +2 a ogni coppia della stessa staffetta a ogni meeting (una volta a coppia), fino a 100 | `RELATION_BOND_PER_RELAY` |

Con 16 atleti le coppie sono 120: in media circa 14 amicizie e 7 rivalità, cioè +7 coppie nette e **+2 di forma** (il Leader dà +2, il picco +6). L'affiatamento di staffetta pesa `(affiatamento − 50) × 0,08` sul punteggio: +10 vale +0,8 punti, e fa scendere la probabilità di squalifica (`(60 − affiatamento) × 0,006` sotto 60).

## W. Momenti di gloria (PIANOLAVORO F.4, 2026-11-21) — CIFRE PROVVISORIE (QUESTIONS Q39)

Nessun RNG e nessuna modifica allo schema. Costanti in `entities.py`, logica in `models/glory.py`.

| Cosa | Regola |
| --- | --- |
| Record del mondo | una misura individuale **valida** (non ritirata, non squalificata, vento legale) che raggiunge il tetto già usato da `_score_to_mark`: 100m 9,58 / 10,49; 400m 43,10 / 47,60; 800m 100,91 s / 113,28 s; 1500m 206,0 / 229,0 s; lungo 8,95 / 7,52 m; peso 23,56 / 22,63 m (`WORLD_RECORDS`, tolleranza `WORLD_RECORD_EPSILON`). Con le curve attuali serve un punteggio ben sopra il livello internazionale: un evento rarissimo |
| Momento storico | un nuovo «MOMENTO STORICO!» in `milestones` nel tick (il muro di `historic_mark`) |
| Promozione / titolo | `SeasonOutcome.PROMOTED` / `CHAMPION` a fine stagione |
| Atleta dell'anno | l'atleta del club con più **vittorie**, poi più **podi** (1°-3°, gare individuali non ritirate né squalificate) nella stagione; a parità il nome alfabeticamente primo; serve almeno un podio |


## X. Grafici della Dashboard (PIANOLAVORO G.1, 2026-11-21) — SOLO PRESENTAZIONE, nessun effetto sul gioco

| Costante (`entities.py`) | Valore | Uso |
|---|---|---|
| `HISTORY_WEEKS` | 12 | settimane di forma e fatica conservate per atleta (`athletes.history_json`) |
| `HISTORY_RESULTS` | 10 | gare individuali conservate per atleta |
| `HEATMAP_SCORE_LOW` / `HEATMAP_SCORE_HIGH` | 40 / 80 | punteggio atteso che colora la cella di freddo / di caldo (scala dei rivali: 42 provinciale, 56 regionale, 70 nazionale, 84 internazionale) |
| `HEATMAP_ATHLETES` | 8 | righe della heat map: i migliori per valore complessivo |

| `STAT_LEVEL_GREAT` / `STAT_LEVEL_GOOD` / `STAT_LEVEL_MID` | 80 / 65 / 45 | scheda atleta (G.2): soglie dei livelli di una caratteristica (verde / giallo / arancione / rosso), le stesse del badge di prima; la fatica si legge al contrario |

## Y. Inviti alla Diamond League (PIANOLAVORO C.1b, 2026-11-21) — CIFRE PROVVISORIE (QUESTIONS Q42)

| Nome | Valore | File |
| --- | --- | --- |
| `DIAMOND_MEET_PHASE_OFFSET` | 7 — posizione (da 0) del meeting nella stagione, contata dall'inizio della fase Outdoor: settimana 8, o 16 con la Preparazione (il secondo dei tre meeting Outdoor) | `entities.py` |
| `DIAMOND_INVITE_MAX_RANK` | 3 — primi posti della classifica di società del livello attuale | `entities.py` |
| `DIAMOND_INVITE_MIN_POINTS` | 100 — punti ranking minimi del club: una vittoria in Finale Oro (100 × 1,00) non ancora decaduta | `entities.py` |
| `DIAMOND_PRIZE_MULT` / `DIAMOND_PRESTIGE_MULT` | 2,0 / 2,0 — moltiplicatori di premio e prestigio di ogni gara del meeting a invito (nessun bonus squadra) | `entities.py` |
| `DIAMOND_MEET_LABEL` | «Diamond League» — prefisso del nome del meeting | `entities.py` |

## Z. Primati personali per gara (Q43, 2026-11-21)

| Nome | Valore | File |
| --- | --- | --- |
| `PB_LOG_MAX` | 20 — quanti miglioramenti del primato si ricordano per gara e per atleta (i più recenti; l'ultimo è il primato attuale, quindi tagliare i vecchi non lo cambia) | `entities.py` |
