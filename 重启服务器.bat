@echo off
setlocal
cd /d "%~dp0"

chcp 65001 >nul

echo ============================================================
echo  LY Community - Restart Server
echo  Step 1: stop old backend/frontend processes
echo ============================================================

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0kill_old_servers.ps1"

timeout /t 1 /nobreak >nul

echo Step 2: select WeChat account and run decryption gate...
python "%~dp0start_server.py"

echo.
echo Server exited. Press any key to close.
pause >nul
