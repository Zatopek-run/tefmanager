# Race Viewer (Godot 4) — Track & Field Manager

Modulo di visualizzazione gare in stile "diretta TV" 2010. **Solo View**: i risultati li calcola il motore
Python (`models/simulation.py`) e finiscono in SQLite; Godot li legge e li mette in scena.
Ogni corridore taglia il traguardo esattamente a `final_time` (il tempo di reazione è incluso).
Eventi: 100m, 400m, 800m, 1500m, 4x100m, 4x400m, Salto in Lungo, Getto del Peso.

## Requisiti

- Godot **4.3+** (Forward+). `CameraAttributesPractical` richiede ≥ 4.2.
- Plugin **godot-sqlite** (GDExtension, classe globale `SQLite`): scaricalo dall'Asset Library o da
  GitHub (2shady4u/godot-sqlite) e copia la cartella in `addons/godot-sqlite/` (è in `.gitignore`).

## Struttura (MVC)

```text
godot_viewer/
  project.godot                 autoload: DatabaseManager, RaceController
  autoload/
    DatabaseManager.gd          MODEL       SQLite in sola lettura (+ DB demo se manca)
    RaceController.gd           CONTROLLER  stato gara, tempo, classifica, segnali
  models/
    RunnerData.gd               dati corridore (DB + stato runtime)
    RaceMotion.gd               curva di velocità, distanza/velocità al tempo t (funzioni pure)
    ShotPutMotion.gd            getto del peso: pedana, tentativo, posa e volo del peso (funzioni pure)
  scenes/
    Stadium.tscn  + scripts/Stadium.gd, BroadcastCameras.gd, RunnerView.gd     VIEW 3D
                    scripts/ShotPutRig.gd (posa del lanciatore), ShotPutView.gd (peso, scia, nastro, arco del migliore)
  assets/athlete/               personaggio con scheletro + animazioni (CC0, Quaternius), vedi CREDITS.md
    HUD.tscn      + scripts/HUD.gd                                             VIEW 2D
  data/
    schema.sql  demo_seed.sql   schema delle tabelle `races` e `race_results` + gara dimostrativa
```

## Avvio

1. Apri la cartella in Godot, importa il progetto, installa il plugin SQLite.
2. Premi F5. Al primo avvio crea `user://race_results.db` con la gara demo; la gara parte da sola.
3. Con un DB reale: variabile d'ambiente `TEF_RACE_DB=C:\percorso\race_results.db`; gara diversa:
   `godot --path godot_viewer -- --race=3`.
4. Tasti: **Spazio** riparte · **1/2/4/8** velocità (indicatore in basso a destra) · **Esc** salta alla fine. Il tempo
   scorre sempre in tempo reale (anche nei 400m, ~50 s): sta all'utente accelerare.

## Contratto con il DB

`race_results.final_time` è il tempo ufficiale dallo sparo e **include** `reaction_time`
(vincolo `final_time > reaction_time`). Corsie 1–9, una riga per corsia. Righe incoerenti vengono scartate
con un warning. `status` = `OK` o `DNF` (ritirato: corre fino a 42 m e si ferma). L'esportatore è `models/race_export.py`: `python -m models.race_export [salvataggio.db] [race_results.db]` (esporta i 100m dell'ultimo meeting).

## Configurazione manuale in editor (equivalente a quanto fa il codice)

**Luce** — `Sun` (DirectionalLight3D): Rotation `(-38°, -50°, 0°)`, Light ▸ Energy `1.35`, Color caldo
`#FFEDD1`, **Shadow ▸ Enabled = On**, Shadow ▸ Mode `PSSM 4 Splits`, Max Distance `90`, Blur `1.5`, Bias `0.03`.

**Ambiente** — nodo `WorldEnvironment` con `Environment`: Background `Sky` (ProceduralSkyMaterial),
Tonemap `ACES`, SSAO On, Glow On (Intensity `0.7`, Bloom `0.08`, HDR Threshold `1.0`).

**Telecamere** — `Cameras/BroadcastPath` (Path3D): curva retta da `(-12, 2.3, 17)` a `(118, 2.3, 17)`
(lato esterno, davanti alla corsia 8: guardando verso -Z, +X è a destra). `CameraDolly` (PathFollow3D, Loop Off, Rotation Mode `None`) porta
`SideCam` (FOV 28°, DoF far blur On, Distance 22, Transition 25, Amount 0.06). Lo script muove
`CameraDolly.progress` seguendo il leader e la camera lo inquadra con `look_at`.
`FinishCam` è fissa sul piano del traguardo `(100.15, 0.9, 16)`, FOV 22°: lo stacco avviene quando il
leader supera i 90 m (`CUT_TO_FINISH_AT`).

## Verifica

Provato con Godot 4.7.2 (Forward+, Vulkan) e godot-sqlite 4.9:

- `godot --headless --path godot_viewer -s res://tests/verify_race.gd` — arrivo esatto a 100 m per tutti,
  distanza monotona, ordine d'arrivo, cronometro bloccato sul vincitore (codice di uscita 0/1).
- `godot --path godot_viewer -s res://tests/screenshots.gd -- cartella_uscita` — screenshot della scena reale.

Limiti noti: niente altri concorsi (alto, disco, …) né più di 8 corsie; la posizione ai blocchi è ottenuta con IK (`SetPoseRig`), non
da un'animazione, e la spinta di uscita dai blocchi è l'animazione `Sprint` (non c'è una vera partenza); la finestra Godot è separata dal gioco; nessun pettorale
(dalla camera laterale non si vedrebbe); il pubblico è una texture procedurale a blocchetti, non persone modellate.
Provati: tasti Spazio/1/2/4/Esc e `--autoquit` (`tests/verify_input.gd`), ritiro per infortunio (gara 2 del DB
demo), fotofinish (la camera fissa stacca quando il leader supera i 90 m).

## 400m (pista ovale)

`TrackGeometry.gd` descrive l'ovale (rettilinei 84,39 m, raggio corsia 1 = 36,8 m): ogni corsia fa esattamente 400 m
con la partenza sfalsata e tutte arrivano sulla linea a x = 0 (`verify_race.gd` lo controlla corsia per corsia).
`OvalTrackBuilder.gd` disegna tartan, linee di corsia, linee di partenza sfalsate e traguardo dagli stessi numeri.
La regia dei 400m (`BroadcastCameras._direct_oval`) cambia ripresa in base al tratto dell'anello in cui si trova il primo
(`TrackGeometry.region`): start largo, teleobiettivo dall'altro lato dell'interno, alto sulla curva 2, carrello alto sul
rettilineo d'arrivo, traguardo dall'alto. Le camere che panoramicano puntano esattamente sul primo; il carrello alto lo tiene
a destra del centro e inquadra tutto il gruppo. `tests/verify_camera.gd` lo misura su una finestra 1280x720 (in `--headless`
la finestra di default è 64x64: i test in pixel vanno fatti impostando `root.size`).

## Getto del peso

Geometria, cronologia, posa dell'atleta e volo del peso stanno in `models/ShotPutMotion.gd` (funzioni **pure** del tempo del
tentativo, senza scene: è l'unica fonte per costruttore della pista, controller, rig, vista del peso, camere e test).
**Il peso atterra ESATTAMENTE alla misura del DB**: il punto di caduta è `L = C + u · (misura + 1,0675 m)` (misura dal bordo
interno del cerchio, in linea retta dal centro della pedana), il punto di rilascio `R` è scritto (ricavato dalla posa a
`T_REL` e dall'altezza visiva dell'atleta, `RunnerData.visual_height`) e con l'angolo di rilascio fisso (36-38,5°, sempre fra 35° e 40°)
la velocità iniziale è in forma chiusa: `v0 = (D/cosθ) · sqrt(g / (2 (D tanθ + h)))`. Il volo è una funzione del tempo fissata a
`tau ≥ T`, quindi esatta a 1x, a 8x e con «Salta alla fine». Il punto di caduta ha uno scarto deterministico dall'asse
(±0,13 rad, stesso atleta e stessa prova = stessa traiettoria): il raggio non cambia.

- **Tutti i lanci sono animati per intero** (≈ 10 s ciascuno a 1x: ingresso, posizione iniziale, rotazione, rilascio, volo, misura,
  uscita; con 6 concorrenti sono circa 6 minuti a 1x, i tasti 2/4/8 accelerano). Sul terreno **non restano buche**: un
  **arco dorato** centrato sulla pedana segna la distanza del miglior lancio, con «COGNOME  misura» accanto (si sposta quando qualcuno lo
  supera; i nulli non contano). Nell'attimo dell'impatto si alza solo un po' di terriccio.
- **Piedi** (`ShotPutRig.FootLevel`): l'IK posiziona solo la caviglia e il piede seguirebbe l'inclinazione dello stinco (punta in giu', suola
  dentro la pedana). Un modificatore dopo l'IK rimette ogni piede orizzontale (punte leggermente in fuori) e la quota della caviglia sopra la
  suola e' per sesso (`ANKLE_H`, `ANKLE_H_F`: l'osso del piede sta a 8,65 cm da terra nel modello maschile e a 7,07 nel femminile).
- **Tecnica a rotazione**, destrorso (sequenza gambe → bacino → tronco → braccio; spalle «chiuse» fino alla posizione di potenza).
  Ingresso e uscita a piedi (camminata Quaternius, peso al collo con IK delle braccia); dalla posizione iniziale lo scheletro è
  comandato da `scripts/ShotPutRig.gd` (bacino e schiena a mano, braccia e gambe con `TwoBoneIK3D`, piedi piantati: la libreria CC0
  non ha un gesto di lancio). I bersagli IK arrivano già risolti da `ShotPutMotion.pose_at`: il rig non legge mai lo scheletro per
  decidere dove mettere le cose. Il peso in mano segue il polso reale dopo l'IK (`skeleton_updated`).
- **Altezza del rilascio ≈ 1,06·H** (1,85 m per 1,75 m), non 2,2 m: i modelli sono alti 1,63-1,86 m e il braccio teso arriva a ~1,1·H.
- **Nullo**: una sola resa deterministica, il piede destro scavalca il fermapiedi e atterra oltre il cerchio (`is_foul` non porta una
  motivazione). Il peso atterra comunque alla misura nominale esportata (0,96 × risultato: è un segnaposto del motore Python).
- **Ambiente** (`OvalTrackBuilder._build_shot_put`): pedana con bordo dipinto, fermapiedi ad arco (corda 1,22 m), terra battuta, settore
  d'erba falciata con linee dal bordo e archi di distanza ogni 5 m. **Niente gabbia** (non c'è nel getto del peso in gara: serve per
  disco e martello; scelta dell'utente) e **settore disegnato per 30 m** (il vero ne ha 100, ma lungo l'asse la curva 1 è a ~78 m).
- **Regia** (`BroadcastCameras._direct_shot`, legata alla fase `ShotPutMotion.phase_at`): larga laterale all'ingresso e alla posizione
  iniziale → teleobiettivo laterale sulla rotazione → teleobiettivo laterale che segue il peso con la scia → punto d'impatto, nastro e
  bandierina (verde valido, rossa nullo) → larga all'uscita. Panoramica sul settore per le prove non animate.
- Verifica: `godot --headless --path godot_viewer -s res://tests/verify_shotput.gd` (~15 s: atterraggio entro 0,5 mm per 480 combinazioni
  di misura/altezza/sesso/nullo, angolo 35-40°, peso sempre sopra il suolo, posa continua, piedi dentro la pedana fino al rilascio,
  uscita dal lato posteriore, controller sulle gare demo 11 e 12). `tests/screenshots_shot.gd` (con finestra) salva i fotogrammi del
  tentativo: `-- cartella [--race=12] [--round=2] [--debug] [--instant]`.
- Limiti: posa tarata su descrizioni biomeccaniche e non su un video di riferimento (non guardabile da qui); il piede e' orizzontale ma
  non pivota attorno alla punta (gira con il bacino, con una rotazione costante rispetto a esso); le dita restano a riposo (la mano non stringe il peso); nessun
  giudice nei concorsi; il disegno dell'arco della scia è una linea da 1 px.

## Riprese e grafica "da diretta TV"

Le riprese, i tempi di preparazione, la posa ai blocchi, la pista (blu per i 100m, viola per i 400m) e la grafica sono
ricavati da due dirette di riferimento (100m di Roma e finale 400m di Parigi 2024), tenute in `raw/` (non su git).
Sequenza dei 100m: apertura larga dall'alto dietro i blocchi → primo piano basso sui blocchi ("pronti", poi "set") →
start largo → carrello alto sul gruppo (il primo a destra del centro) → traguardo dall'alto → corsa oltre il traguardo,
in curva. Sequenza dei 400m: start largo → teleobiettivo dall'altro lato dell'interno → alto sulla curva 2 → carrello alto →
traguardo. Le camere che panoramicano puntano esattamente sul primo; il carrello alto lo tiene a destra del centro e
inquadra tutto il gruppo (si allontana se si sparpaglia). HUD: cronometro in basso a destra, vento e risultato non
ufficiale dopo l'arrivo; **H** mostra/nasconde la classifica laterale (nascosta di default).
Limiti: niente 9ª corsia (le corsie sono 8), niente audio, niente primi piani degli atleti, i marchi reali sono sostituiti
da grafica originale.

## Uso dal gioco PyQt

Per tutti gli eventi elencati sopra il gioco lancia questo visualizzatore da solo (`views/godot_launcher.py`): esporta la gara,
avvia Godot con `--autoquit` e riprende quando si chiude (a fine gara, dopo 3 s). Serve Godot (`TEF_GODOT`,
`~/scoop/apps/godot/current/godot.exe` o PATH) e il plugin in `addons/godot-sqlite/`; altrimenti il gioco usa
la vista interna. «Salta alla fine» nel dialog chiude Godot.

## Personaggi

`RunnerView.gd` carica `Superhero_Male_FullBody.gltf` (65 ossa) e gli applica le animazioni `Crouch_Idle`,
`Jog_Fwd`, `Sprint`, `Walk` di `UAL1_Standard.glb` (stesso scheletro, versione senza root motion). La cadenza
dell'animazione segue la velocità reale (`speed / metri per ciclo`), così i piedi non scivolano. Il modello è
quasi nudo: canotta e pantaloncini sono copie della mesh del corpo gonfiate di pochi mm e tagliate per
altezza con uno shader (UV2 = posizione a riposo), colorate con la squadra. Pelle (4 toni), capelli e altezza
(1,72–1,88 m) sono deterministici dal nome dell'atleta. **Scarpe** (`CharacterDress.add_shoes`): mesh a parte per ogni piede, ricavata dal profilo del piede del modello (maschile o femminile), appesa all'osso del piede; tomaia bianca, scura o grigia a scelta dal nome, striscia obliqua, linguetta del tallone e suola nei colori di squadra/neri, lacci. La suola sta nel volume del piede (la pelle resta il livello del suolo). Gli asset pesano ~28 MB.
