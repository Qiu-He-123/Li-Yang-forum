@echo off
setlocal
title Local Git Rollback
cd /d "%~dp0"

echo ============================================
echo   Local Git Rollback  (Reset to older commit)
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

:: Show recent commits
echo --- Recent Commits (newest first) ---
git log --oneline -10
echo.

set /p "HASH=Enter commit hash to go back to (first 7 chars OK): "
if "%HASH%"=="" (
    echo [INFO] Cancelled.
    goto END
)

echo.
echo Reset mode:
echo   [1] Soft  - keep changes staged (safest, recommended)
echo   [2] Mixed - keep changes but unstage them
echo   [3] Hard  - DISCARD all changes after this point (DANGER!)
echo.
set /p "MODE=Choose mode (1/2/3): "
if "%MODE%"=="" set "MODE=1"

if "%MODE%"=="1" goto SOFT
if "%MODE%"=="2" goto MIXED
if "%MODE%"=="3" goto HARD
echo [INFO] Invalid choice. Cancelled.
goto END

:SOFT
git reset --soft %HASH%
goto DONE

:MIXED
git reset --mixed %HASH%
goto DONE

:HARD
echo.
echo [WARNING] HARD reset will DISCARD all uncommitted changes!
set /p "CONFIRM=Type YES to confirm: "
if not "%CONFIRM%"=="YES" (
    echo Cancelled.
    goto END
)
git reset --hard %HASH%

:DONE
if errorlevel 1 (
    echo [ERROR] Reset failed. Check the hash you entered.
) else (
    echo.
    echo [OK] Rolled back.
    echo.
    echo --- Commits now ---
    git log --oneline -5
)

:END
echo.
pause
