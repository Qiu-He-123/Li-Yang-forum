@echo off
setlocal
title Local Git Save
cd /d "%~dp0"

echo ============================================
echo   Local Git Save  (Add + Commit)
echo   Saves your changes to the local repository
echo ============================================
echo.

:: Check if this is a git repository
git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
    echo [ERROR] This folder is NOT a Git repository.
    echo Please run the Clone script first to download the project.
    echo.
    pause
    exit /b 1
)

:: Show what changed
echo --- Current Changes ---
git status -s
echo.

:: Check if there is anything to save
git diff --quiet 2>nul
if errorlevel 1 goto HAVE_CHANGES
git diff --cached --quiet 2>nul
if errorlevel 1 goto HAVE_CHANGES

echo [INFO] Nothing to save. Working tree is clean.
echo.
pause
exit /b 0

:HAVE_CHANGES
:: Stage everything
echo --- Staging all changes ---
git add -A
echo Done.
echo.

:: Ask for a commit message
set /p "MSG=Enter a short description (or press Enter for default): "
if "%MSG%"=="" set "MSG=Update %date% %time%"

:: Commit
echo.
echo --- Committing ---
git commit -m "%MSG%"
if errorlevel 1 (
    echo [ERROR] Commit failed.
) else (
    echo.
    echo [OK] Changes saved locally.
    echo Next step: run the Push script to upload to GitHub.
)
echo.
pause
