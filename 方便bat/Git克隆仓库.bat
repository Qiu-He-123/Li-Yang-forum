@echo off
setlocal
title Git Clone Repository
cd /d "%~dp0"

echo ============================================
echo   Git Clone Repository  (First-time download)
echo   Repo: Li-Yang-forum
echo ============================================
echo.

:: If already cloned, ask before re-cloning
if not exist "Li-Yang-forum\.git" goto CLONE

echo [INFO] Folder "Li-Yang-forum" already exists and is a Git repo.
set /p "REDO=Re-clone into a new folder? (y/N): "
if /i not "%REDO%"=="y" (
    echo Cancelled.
    pause
    exit /b 0
)
goto CLONE_NEW

:CLONE
echo.
echo --- Cloning from GitHub ---
git clone https://github.com/Qiu-He-123/Li-Yang-forum.git
goto CLONE_DONE

:CLONE_NEW
echo.
echo --- Cloning into a new folder ---
set /p "FOLDER=Enter a new folder name: "
if "%FOLDER%"=="" (
    echo [INFO] Cancelled.
    pause
    exit /b 0
)
git clone https://github.com/Qiu-He-123/Li-Yang-forum.git "%FOLDER%"

:CLONE_DONE
if errorlevel 1 (
    echo.
    echo [ERROR] Clone failed.
    echo Possible reasons:
    echo   - Not logged in to GitHub
    echo   - Network problem
    echo   - Repository does not exist or is private
) else (
    echo.
    echo [OK] Cloned successfully.
    echo.
    echo NEXT STEP:
    echo   Copy ALL .bat files into the cloned "Li-Yang-forum" folder,
    echo   then you can use Save / Push / Pull / Rollback from there.
)
echo.
pause
