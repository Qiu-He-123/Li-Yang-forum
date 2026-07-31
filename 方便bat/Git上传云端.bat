@echo off
setlocal
title Git Push to Cloud
cd /d "%~dp0"

echo ============================================
echo   Git Push to Cloud  (Upload to GitHub)
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

:: Show status first
echo --- Current Status ---
git status -s
echo.

:: Check for uncommitted changes
git diff --quiet 2>nul
if errorlevel 1 goto HAS_CHANGES
git diff --cached --quiet 2>nul
if errorlevel 1 goto HAS_CHANGES
goto PUSH

:HAS_CHANGES
echo [WARNING] You have uncommitted changes.
echo Please run the Save script first to save them.
echo.
set /p "GO=Continue pushing anyway? (y/N): "
if /i not "%GO%"=="y" (
    echo Cancelled.
    pause
    exit /b 0
)

:PUSH
echo.
echo --- Pushing to GitHub ---
git push origin
if errorlevel 1 (
    echo.
    echo [ERROR] Push failed.
    echo Possible reasons:
    echo   - Not logged in to GitHub
    echo   - Network problem
    echo   - Need to pull first (run the Pull script)
) else (
    echo.
    echo [OK] Uploaded to GitHub successfully.
)
echo.
pause
