@echo off
setlocal
cd /d "%~dp0backend"

if not exist .venv\Scripts\python.exe (
    echo [%date% %time%] ERROR: backend\.venv not found >> logs\backup.log 2>&1
    exit /b 1
)

".venv\Scripts\python.exe" scripts\backup_db.py >> logs\backup.log 2>&1
