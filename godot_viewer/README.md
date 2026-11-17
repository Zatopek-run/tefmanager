# Race Viewer (Godot 4) — Track & Field Manager

Modulo di visualizzazione gare in stile "diretta TV" 2010. **Solo View**: i risultati li calcola il motore
Python (`models/simulation.py`) e finiscono in SQLite; Godot li legge e li mette in scena.
Ogni corridore taglia i 100 m esattamente a `final_time` (il tempo di reazione è incluso).

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
    HUD.tscn      + scripts/HUD.gd                                             VIEW 2D
  data/
    schema.sql  demo_seed.sql   schema delle tabelle `races` e `race_results` + gara dimostrativa
```

## Avvio

1. Apri la cartella in Godot, importa il progetto, installa il plugin SQLite.
2. Premi F5. Al primo avvio crea `user://race_results.db` con la gara demo; la gara parte da sola.
3. Con un DB reale: variabile d'ambiente `TEF_RACE_DB=C:\percorso\race_results.db`; gara diversa:
   `godot --path godot_viewer -- --race=3`.
4. Tasti: **Spazio** riparte · **1/2/4** velocità · **Esc** salta alla fine.

## Contratto con il DB

`race_results.final_time` è il tempo ufficiale dallo sparo e **include** `reaction_time`
(vincolo `final_time > reaction_time`). Corsie 1–9, una riga per corsia. Righe incoerenti vengono scartate
con un warning. L'esportatore è `models/race_export.py`: `python -m models.race_export [salvataggio.db] [race_results.db]` (esporta i 100m dell'ultimo meeting).

## Configurazione manuale in editor (equivalente a quanto fa il codice)

**Luce** — `Sun` (DirectionalLight3D): Rotation `(-38°, -50°, 0°)`, Light ▸ Energy `1.35`, Color caldo
`#FFEDD1`, **Shadow ▸ Enabled = On**, Shadow ▸ Mode `PSSM 4 Splits`, Max Distance `90`, Blur `1.5`, Bias `0.03`.

**Ambiente** — nodo `WorldEnvironment` con `Environment`: Background `Sky` (ProceduralSkyMaterial),
Tonemap `ACES`, SSAO On, Glow On (Intensity `0.7`, Bloom `0.08`, HDR Threshold `1.0`).

**Telecamere** — `Cameras/BroadcastPath` (Path3D): curva retta da `(-12, 2.3, -9)` a `(118, 2.3, -9)`
(lato prato, a ~9 m dalla corsia 1). `CameraDolly` (PathFollow3D, Loop Off, Rotation Mode `None`) porta
`SideCam` (FOV 28°, DoF far blur On, Distance 22, Transition 25, Amount 0.06). Lo script muove
`CameraDolly.progress` seguendo il leader e la camera lo inquadra con `look_at`.
`FinishCam` è fissa sul piano del traguardo `(100.15, 0.9, -7)`, FOV 22°: lo stacco avviene quando il
leader supera i 90 m (`CUT_TO_FINISH_AT`).

## Verifica

Provato con Godot 4.7.2 (Forward+, Vulkan) e godot-sqlite 4.9:

- `godot --headless --path godot_viewer -s res://tests/verify_race.gd` — arrivo esatto a 100 m per tutti,
  distanza monotona, ordine d'arrivo, cronometro bloccato sul vincitore (codice di uscita 0/1).
- `godot --path godot_viewer -s res://tests/screenshots.gd -- cartella_uscita` — screenshot della scena reale.

Limiti noti: i corridori corrono verso **sinistra** (la camera sul lato prato guarda verso +Z, quindi +X è a
sinistra dello schermo); la posa di corsa è approssimativa; mai provato con input da tastiera/mouse.
