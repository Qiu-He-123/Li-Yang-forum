@echo off
setlocal
title One-Click Sync (Pull + Save + Push)
cd /d "%~dp0"

echo ============================================
echo   One-Click Sync  (Pull + Save + Push)
echo   Downloads latest, saves your changes, uploads
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

echo [1/4] Pulling latest changes...
git pull origin
if errorlevel 1 (
    echo [ERROR] Pull failed. Please resolve conflicts manually,
    echo then run the Save script and the Push script.
    pause
    exit /b 1
)
echo.

echo [2/4] Staging all changes...
git add -A
echo Done.
echo.

set /p "MSG=[3/4] Enter a short description (or press Enter for default): "
if "%MSG%"=="" set "MSG=Sync update %date% %time%"

echo.
echo [3/4] Committing...
git commit -m "%MSG%"
echo.

echo [4/4] Pushing to GitHub...
git push origin
if errorlevel 1 (
    echo [ERROR] Push failed.
) else (
    echo.
    echo [OK] All synced with GitHub.
)
echo.
pause
