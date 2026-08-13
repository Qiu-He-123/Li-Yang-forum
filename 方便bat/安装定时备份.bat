@echo off
setlocal
title Install Daily DB Backup Task (run as Administrator)
cd /d "%~dp0"

echo ============================================
echo   Install Daily DB Backup Task
echo   Runs every day at 03:00 automatically
echo ============================================
echo.

schtasks /Create /F /TN "LY Community DB Backup" /SC DAILY /ST 03:00 /TR "%~dp0定时备份数据库.bat"

if errorlevel 1 (
    echo.
    echo [ERROR] Failed. Please right-click this file and choose
    echo         "Run as administrator", then try again.
) else (
    echo.
    echo [OK] Task installed. It will run every day at 03:00.
    echo To test it now, run:  schtasks /Run /TN "LY Community DB Backup"
)
echo.
pause
