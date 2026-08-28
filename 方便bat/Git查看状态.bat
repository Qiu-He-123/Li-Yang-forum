@echo off
setlocal
title Git Status
cd /d "%~dp0"

echo ============================================
echo   Git Status  (View current changes)
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

echo --- Current Branch ---
git branch --show-current
echo.
echo --- Recent Commits ---
git log --oneline -5
echo.
echo --- Changes (M=modified, ??=new, D=deleted) ---
git status -s
echo.
echo Done.
pause
