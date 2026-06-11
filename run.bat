@echo off
chcp 65001 > nul
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" sensevoice_ime.py
) else if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" sensevoice_ime.py
) else (
    python sensevoice_ime.py
)
pause
