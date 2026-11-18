#!/usr/bin/env bash
# Avvia Track & Field Manager su Linux (equivalente di TrackAndFieldManager.bat).
#   ./TrackAndFieldManager.sh            avvia il gioco
#   ./TrackAndFieldManager.sh --check    mostra Python e Godot che userebbe, senza aprire la finestra
# Variabili utili: TEF_GODOT=/percorso/godot (Godot da usare), TEF_NO_GODOT=1 (solo vista PyQt interna).
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

CHECK=0
if [[ "${1:-}" == "--check" ]]; then
    CHECK=1
    shift
fi

# --- Python: virtualenv del progetto, poi il python3 di sistema ---------------------------------------
PYTHON=""
for candidate in .venv/bin/python venv/bin/python; do
    if [[ -x "$candidate" ]]; then
        PYTHON="$candidate"
        break
    fi
done
if [[ -z "$PYTHON" ]]; then
    PYTHON="$(command -v python3 || true)"
fi
if [[ -z "$PYTHON" ]]; then
    echo "[Errore] Python 3 non trovato. Installalo e poi: pip install -r requirements.txt" >&2
    exit 1
fi
if ! "$PYTHON" -c "import PyQt6" >/dev/null 2>&1; then
    echo "[Errore] PyQt6 non risulta installato per $PYTHON." >&2
    echo "Esegui: $PYTHON -m pip install -r requirements.txt" >&2
    exit 1
fi

# --- Godot: il gioco cerca TEF_GODOT o 'godot' nel PATH; un'installazione flatpak non la vede, quindi la si
#     espone con un piccolo wrapper (fuori dal repository). Senza Godot il gioco usa la vista PyQt interna. ----
GODOT_INFO="vista PyQt interna (Godot non trovato)"
if [[ -n "${TEF_NO_GODOT:-}" ]]; then
    GODOT_INFO="disattivato (TEF_NO_GODOT)"
elif [[ -n "${TEF_GODOT:-}" ]]; then
    GODOT_INFO="TEF_GODOT=$TEF_GODOT"
elif command -v godot >/dev/null 2>&1; then
    GODOT_INFO="$(command -v godot)"
elif command -v flatpak >/dev/null 2>&1 && flatpak info org.godotengine.Godot >/dev/null 2>&1; then
    WRAPPER_DIR="$HOME/.track_field_manager"
    WRAPPER="$WRAPPER_DIR/godot-flatpak"
    mkdir -p "$WRAPPER_DIR"
    printf '#!/usr/bin/env bash\nexec flatpak run org.godotengine.Godot "$@"\n' > "$WRAPPER"
    chmod +x "$WRAPPER"
    export TEF_GODOT="$WRAPPER"
    GODOT_INFO="flatpak org.godotengine.Godot (via $WRAPPER)"
fi

if [[ "$CHECK" == 1 ]]; then
    echo "Python: $PYTHON ($("$PYTHON" --version 2>&1))"
    echo "Godot:  $GODOT_INFO"
    exit 0
fi

exec "$PYTHON" main.py "$@"
