@echo off
setlocal
title Git Pull Update
cd /d "%~dp0"

echo ============================================
echo   Git Pull Update  (Download latest from GitHub)
echo ============================================
echo.

:: Check if this is a git repository
git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
    echo [ERROR] This folder is NOT a Git repository.
    echo Please run the Clone script first.
    echo.
    pause
    exit /b 1
)

echo --- Pulling latest changes from GitHub ---
echo.
git pull origin
if errorlevel 1 (
    echo.
    echo [ERROR] Pull failed.
    echo Possible reasons:
    echo   - Network problem
    echo   - Merge conflict: open the files, resolve the marked lines,
    echo     then run the Save script and the Push script.
) else (
    echo.
    echo [OK] Updated with latest from GitHub.
)
echo.
pause
