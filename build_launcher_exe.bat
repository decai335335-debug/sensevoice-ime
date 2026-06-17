@echo off
chcp 65001 > nul
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m PyInstaller --noconfirm --onefile --windowed --icon "assets\sensevoice.ico" --name SenseVoiceIME desktop_launcher.py
) else if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" -m PyInstaller --noconfirm --onefile --windowed --icon "assets\sensevoice.ico" --name SenseVoiceIME desktop_launcher.py
) else (
    python -m PyInstaller --noconfirm --onefile --windowed --icon "assets\sensevoice.ico" --name SenseVoiceIME desktop_launcher.py
)

if exist "dist\SenseVoiceIME.exe" (
    copy /Y "dist\SenseVoiceIME.exe" "SenseVoiceIME.exe" > nul
    echo Built SenseVoiceIME.exe
) else (
    echo Build failed
)
pause
