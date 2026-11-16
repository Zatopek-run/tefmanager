# Track & Field Manager

A standalone desktop athletics management simulation built with **Python**, **PyQt6**, and **SQLite** using a clean **Model-View-Controller (MVC)** architecture.

## Project Structure

```text
tefmanager/
├── main.py                        # Application entry point
├── requirements.txt               # Dependencies (PyQt6, PyInstaller)
├── models/
│   ├── __init__.py
│   ├── entities.py                # GameState, Athlete, Events, Tiers, Enums
│   ├── generator.py               # Procedural athlete & lineup generation
│   ├── simulation.py              # Training, fatigue/form, injury, and meet engine
│   └── database.py                # SQLite save/load persistence
├── controllers/
│   ├── __init__.py
│   └── game_controller.py         # Qt signal controller coordinating Model & Views
├── views/
│   ├── __init__.py
│   ├── styles.py                  # Dark sports-management QSS theme
│   ├── dialogs.py                 # Risultati gara, Fine Stagione, Mercato, Assumi Allenatore, Dilemmi Etici, Nuova Partita
│   ├── athlete_dialog.py          # Scheda Atleta (caratteristiche a colonne, allenamento, gare)
│   ├── tabs.py                    # Dashboard, Rosa, Vivaio, Calendario & Gare, Staffette, Rivali, Staff & Impianto, Finanze
│   └── main_window.py             # QMainWindow & HUD
└── tests/
    └── test_game.py               # Unit and offscreen PyQt6 smoke tests
```

## Modalità Prototipo (Slice Verticale) & Carriera Completa

- **Prototipo Outdoor**: 10 atleti, 3 discipline (`100m`, `Salto in Lungo`, `1500m`), 2 gare ufficiali (Settimana 4 e Settimana 8) per testare subito il loop di periodizzazione, recupero/fatica, vento (> +2.0 m/s non omologato), scouting studentesco, staff e dilemmi etici.
- **Carriera Completa**: stagioni cicliche `Outdoor -> Cross -> Indoor`, 5 discipline (inclusi `400m` e `Getto del Peso`) e scalata da `Provinciale` a `Internazionale` con promozioni e retrocessioni di fine stagione.

## Gestione del Club (v3)

Meccaniche da gestionale di atletica online, adattate alla scala del gioco:

- **Vivaio & Osservatori**: fino a 8 ragazzi di 14-17 anni che non gareggiano e non prendono stipendio, ma si allenano il 50% più in fretta. A 18 anni passano in Prima Squadra da soli; prima puoi promuoverli a mano. Ogni settimana hai 8 punti scouting: una ricerca costa 2 punti, +1 per ogni filtro (disciplina, potenziale ≥85). Il costo in denaro cresce con i punti già spesi nella settimana. I ragazzi segnalati e non presi se ne vanno a fine settimana.
- **Atteggiamento in gara** (Prudente / Normale / Aggressivo), scelto per ogni gara: più spinta dà risultati migliori ma più fatica e un rischio maggiore di ritiro per infortunio. Il rischio sale con la fatica e scende se c'è il medico.
- **Classifica a squadre**: in ogni gara i piazzamenti valgono punti (1° = 8 … 8° = 1). I punti formano la classifica del meeting e una classifica di lega cumulativa, che si azzera a ogni stagione e decide promozioni e retrocessioni. Le prime 3 società prendono prestigio extra; una gara senza convocato regala punti ai rivali.
- **Impianto**: palestra (livelli 0-5, +6% di crescita in allenamento per livello, con costo di gestione) e tribune ampliabili. I meeting si alternano casa/trasferta: in casa non paghi la trasferta e incassi i biglietti, con gli spettatori limitati dalla capienza.
- **Fan & sponsor individuali**: gli atleti guadagnano fan con piazzamenti, PB e record. I maggiorenni in Prima Squadra portano sponsor personali settimanali.
- **Fedeltà sponsor**: ogni acquisto o cessione la abbassa (meno per gli under 21) e riduce lo sponsor della società; si recupera di +2 a settimana.
- **Debito & fallimento**: con il saldo negativo paghi il 5% di interessi a settimana; sotto -$20.000 la società fallisce.
- **Declino con l'età**: dopo la finestra di picco della specialità gli atleti perdono gradualmente velocità, resistenza e forza.

- **Allenatori con abilità proprie**: ogni allenatore ha un valore (1-100) in Velocità, Resistenza, Forza e Tecnica. Quando un atleta allena una qualità, cresce tanto più quanto l'allenatore è bravo in quella qualità; senza un allenatore adatto cresce molto più lentamente. Gli specializzati (max 6) seguono solo la propria disciplina; quelli del vivaio (max 2) solo i ragazzi 14-17. Si assumono scegliendo abilità principale, secondaria e livello di ingaggio ($1.500-$7.500; più abilità = stipendio più alto). Uno a settimana. Oltre 6 atleti a testa l'effetto cala, e le abilità calano lentamente col tempo.
- **Staffette 4x100m e 4x400m**: 4 frazionisti in ordine più una riserva; ogni atleta corre in una sola staffetta. La 4x400 si corre in Carriera (serve la gara dei 400m), la 4x100 non si corre indoor e in Cross non si corrono staffette. Il tempo dipende dai frazionisti (l'ultima frazione pesa di più) e dall'affiatamento (E … A++). L'affiatamento cresce ogni settimana coi titolari sani e di più quando si gareggia; se è basso aumenta il rischio di squalifica per cambio fuori zona. Riordinare è gratis; sostituire un titolare sano costa il 25% dell'affiatamento ed è possibile una volta ogni 4 settimane. Un titolare infortunato viene sostituito dalla riserva. Le staffette contano nella classifica a squadre e hanno record sociali propri, ma non consumano forma e non danno fan.

- **Rivali che migliorano nel tempo**: ogni categoria ha 7 società rivali fisse, ognuna con un atleta per gara (nome, età, livello, PB) che incontri meeting dopo meeting. Ogni settimana anche loro si allenano: gli under 24 crescono, i 24-27 crescono poco, dai 30 anni calano. A ogni nuova stagione invecchiano, i veterani si ritirano e arrivano giovani reclute, ogni anno un po' più forti. Le società che batti diventano più ambiziose e crescono più in fretta (e a fine stagione reclutano meglio); quelle che ti staccano di molto si rilassano. Le staffette rivali valgono quanto i loro velocisti. La scheda **Rivali** mostra livello e tendenza di ogni società, i suoi atleti e un confronto gara per gara con il valore atteso dei tuoi convocati.

- **Promozioni e retrocessioni (Carriera)**: la categoria si decide sul campo, non più col prestigio. A fine stagione (dopo Outdoor, Cross e Indoor: 36 settimane) conta la classifica di lega: le prime 2 salgono di categoria, l'ultima scende. In Internazionale il 1° posto vale il titolo. A pari punti l'ordine è alfabetico. Una finestra mostra la classifica finale e il verdetto; la dashboard indica posizione, zona e settimane al verdetto. Il prestigio resta e fa crescere il pubblico nei meeting in casa. Nel Prototipo (8 settimane) non ci sono promozioni né retrocessioni.

I salvataggi v2, v3, v4 e v5 vengono migrati in automatico a v6 (schema SQLite esteso con `ALTER TABLE`), senza perdere la partita; i vecchi coach "a ruolo" dello staff diventano allenatori veri e le partite senza rivali ricevono le società rivali.

## How to Run

1. Install dependencies (if not already installed):
   ```bash
   pip install -r requirements.txt
   ```
2. Launch the game:
   ```bash
   python main.py
   ```
   Save data is stored automatically in SQLite at `~/.track_field_manager/savegame.db`.

3. Run the automated test suite:
   ```bash
   python -m unittest discover -s tests -v
   ```

## Packaging as a Standalone Executable (PyInstaller)

### Single-File Windowed Executable (Recommended)
Run from the project root (`e:\Apps\tefmanager`):

```bash
pyinstaller --noconfirm --onefile --windowed --name "TrackAndFieldManager" main.py
```

- `--onefile`: Bundles Python, PyQt6, and all modules into one `.exe` inside `dist/`.
- `--windowed` (or `--noconsole`): Prevents a terminal console window from opening alongside the GUI.
- Output binary: `dist/TrackAndFieldManager.exe` (Windows) or `dist/TrackAndFieldManager` (macOS/Linux).

### Folder Distribution (Faster Startup)
If you prefer faster startup without onefile extraction overhead:

```bash
pyinstaller --noconfirm --onedir --windowed --name "TrackAndFieldManager" main.py
```
