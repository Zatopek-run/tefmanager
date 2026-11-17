@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "PYTHON_EXE="
set "PYTHONW_EXE="

if exist ".venv\Scripts\pythonw.exe" (
    set "PYTHONW_EXE=%~dp0.venv\Scripts\pythonw.exe"
    set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
) else if exist "venv\Scripts\pythonw.exe" (
    set "PYTHONW_EXE=%~dp0venv\Scripts\pythonw.exe"
    set "PYTHON_EXE=%~dp0venv\Scripts\python.exe"
) else (
    for /f "delims=" %%I in ('where pythonw.exe 2^>nul') do (
        if not defined PYTHONW_EXE set "PYTHONW_EXE=%%I"
    )
    for /f "delims=" %%I in ('where python.exe 2^>nul') do (
        if not defined PYTHON_EXE set "PYTHON_EXE=%%I"
    )
    if not defined PYTHONW_EXE (
        for /f "delims=" %%I in ('where pyw.exe 2^>nul') do (
            if not defined PYTHONW_EXE set "PYTHONW_EXE=%%I"
        )
    )
)

if not defined PYTHONW_EXE (
    echo [Errore] Python ^(pythonw.exe^) non trovato nel virtualenv o nel PATH.
    echo Installa Python 3 e le dipendenze con: pip install -r requirements.txt
    pause
    exit /b 1
)

if defined PYTHON_EXE (
    "%PYTHON_EXE%" -c "import PyQt6" >nul 2>&1
    if errorlevel 1 (
        echo [Errore] PyQt6 non risulta installato per "%PYTHON_EXE%".
        echo Esegui: "%PYTHON_EXE%" -m pip install -r requirements.txt
        pause
        exit /b 1
    )
)

if not defined TEF_GODOT (
    for %%G in ("Godot*win64.exe") do (
        echo "%%~nxG" | findstr /i "console" >nul || (
            if not defined TEF_GODOT set "TEF_GODOT=%%~fG"
        )
    )
)

start "" "%PYTHONW_EXE%" main.py
exit /b 0
