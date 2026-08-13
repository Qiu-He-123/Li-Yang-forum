@echo off
setlocal
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
title LY Restart Server

echo ============================================================
echo   LY Community - Restart Server (auto check and fix env)
echo ============================================================
echo.

:: find usable python: prefer py -3 launcher, then python
py -3 --version >nul 2>&1
if errorlevel 1 (
    python --version >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Python not found!
        echo Please install Python 3.10+ from https://www.python.org/downloads/
        echo and check "Add python.exe to PATH" / "py launcher" during install.
        pause
        exit /b 1
    )
    set "PY=python"
) else (
    set "PY=py -3"
)

echo [1/3] Checking and fixing environment (auto install/upgrade)...
%PY% "%~dp0backend\scripts\bootstrap.py"
if errorlevel 1 (
    echo.
    echo [ERROR] Environment check failed. See messages above, then retry.
    pause
    exit /b 1
)

echo.
echo [2/3] Stopping old server processes...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0kill_old_servers.ps1"
timeout /t 1 /nobreak >nul

echo.
echo [3/3] Starting server wizard...
"%~dp0backend\.venv\Scripts\python.exe" "%~dp0start_server.py"

echo.
echo Server exited. Press any key to close.
pause >nul
