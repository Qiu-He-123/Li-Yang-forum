@echo off
setlocal
cd /d "%~dp0"

REM ============================================================
REM LY Community Startup Script (T9-3)
REM - Auto install backend/frontend deps on first run
REM - Run Alembic migrations before backend starts (T3-1)
REM - Open browser after services are up
REM ============================================================

if not exist backend\.env copy backend\.env.example backend\.env >nul

REM --- Backend dependencies ---
if not exist backend\.venv (
  echo Creating Python virtual environment...
  cd /d "%~dp0backend"
  python -m venv .venv
  call .venv\Scripts\activate.bat
  echo Installing backend dependencies, this may take a few minutes on first run...
  pip install -r requirements.txt
  cd /d "%~dp0"
) else (
  call backend\.venv\Scripts\activate.bat
)

REM --- Frontend dependencies ---
if not exist frontend\node_modules (
  echo Installing frontend dependencies, this may take a few minutes on first run...
  cd /d "%~dp0frontend"
  call npm install --registry=https://registry.npmjs.org
  cd /d "%~dp0"
)

REM --- Database migration (T3-1, must run before backend starts) ---
echo Running Alembic migrations...
cd /d "%~dp0backend"
alembic upgrade head
if errorlevel 1 (
  echo [ERROR] Alembic migration failed. Please check backend/.env DATABASE_URL.
  pause
  exit /b 1
)
cd /d "%~dp0"

REM --- Start backend and frontend ---
start "LY Community Backend" cmd /k "cd /d %~dp0backend && call .venv\Scripts\activate.bat && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
start "LY Community Frontend" cmd /k "cd /d %~dp0frontend && npm run dev -- --host 127.0.0.1 --port 5173"

timeout /t 5 /nobreak >nul
start http://127.0.0.1:5173/
