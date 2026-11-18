# Race Viewer (Godot 4) — Track & Field Manager

Modulo di visualizzazione gare in stile "diretta TV" 2010. **Solo View**: i risultati li calcola il motore
Python (`models/simulation.py`) e finiscono in SQLite; Godot li legge e li mette in scena.
Ogni corridore taglia il traguardo esattamente a `final_time` (il tempo di reazione è incluso).
Eventi: 100m, 400m, 1500m, 4x100m, 4x400m, Salto in Lungo, Getto del Peso.

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
  scenes/
    Stadium.tscn  + scripts/Stadium.gd, BroadcastCameras.gd, RunnerView.gd     VIEW 3D
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
quasi nudo: canotta, pantaloncini e scarpette sono copie della mesh del corpo gonfiate di pochi mm e tagliate per
altezza con uno shader (UV2 = posizione a riposo), colorate con la squadra. Pelle (4 toni), capelli e altezza
(1,72–1,88 m) sono deterministici dal nome dell'atleta. Gli asset pesano ~28 MB.
