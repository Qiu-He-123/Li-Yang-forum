@echo off
setlocal
cd /d "%~dp0backend"

if not exist .venv\Scripts\python.exe (
    echo [ERROR] backend\.venv not found. Please run "启动立洋社区.bat" once first.
    pause
    exit /b 1
)

echo ============================================
echo   Backup Database to GitHub (private repo)
echo ============================================
echo.

".venv\Scripts\python.exe" scripts\backup_db.py

echo.
if errorlevel 1 (
    echo [ERROR] Backup failed. Check backend\.env (GITHUB_TOKEN / DATABASE_URL).
) else (
    echo [OK] Backup done. See https://github.com/Qiu-He-123/liyang-backups/releases
)
echo.
pause
