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
│   ├── dialogs.py                 # Risultati gara (con vento), Scouting, Dilemmi Etici, Nuova Stagione
│   ├── tabs.py                    # Dashboard, Rosa & Allenamenti, Calendario & Gare, Staff & Impianto, Finanze
│   └── main_window.py             # QMainWindow & HUD
└── tests/
    └── test_game.py               # Unit and offscreen PyQt6 smoke tests
```

## Modalità Prototipo (Slice Verticale) & Carriera Completa

- **Prototipo Outdoor**: 10 atleti, 3 discipline (`100m`, `Salto in Lungo`, `1500m`), 2 gare ufficiali (Settimana 4 e Settimana 8) per testare subito il loop di periodizzazione, recupero/fatica, vento (> +2.0 m/s non omologato), scouting studentesco, staff e dilemmi etici.
- **Carriera Completa**: stagioni cicliche `Outdoor -> Cross -> Indoor`, 5 discipline (inclusi `400m` e `Getto del Peso`) e scalata da `Provinciale` a `Internazionale`.

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
