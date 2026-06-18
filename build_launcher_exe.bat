@echo off
chcp 65001 > nul
cd /d "%~dp0"

set "PYINSTALLER_ARGS=--noconfirm --onefile --windowed --icon assets\sensevoice.ico --name SenseVoiceIME desktop_launcher.py"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m PyInstaller %PYINSTALLER_ARGS%
) else if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" -m PyInstaller %PYINSTALLER_ARGS%
) else (
    python -m PyInstaller %PYINSTALLER_ARGS%
)

if exist "dist\SenseVoiceIME.exe" (
    copy /Y "dist\SenseVoiceIME.exe" "SenseVoiceIME.exe" > nul
    echo Built SenseVoiceIME.exe
) else (
    echo Build failed
)
pause
