@echo off
chcp 65001 >nul
title Production Plan Review
cd /d "%~dp0"

set PORT=%PORT: =%
if "%PORT%"=="" set PORT=8502
set VENV_DIR=.venv
set RESET=0

REM Parse args
for %%a in (%*) do (
  if "%%a"=="--reset" set RESET=1
  if "%%a"=="--clean" (
    echo Cleaning uploads, pycache...
    rmdir /s /q uploads 2>nul
    mkdir uploads 2>nul
    rmdir /s /q app\__pycache__ 2>nul
    if "%RESET%"=="1" rmdir /s /q .venv 2>nul
  )
  if "%%a"=="--help" (
    echo Usage: run.bat [--reset] [--clean] [--port=8502]
    echo   --reset : Force recreate venv and reinstall
    echo   --clean : Clean uploads
    exit /b 0
  )
)

if "%RESET%"=="1" (
  echo [RESET] Forcing venv recreation...
  rmdir /s /q .venv 2>nul
)

echo [1/4] Checking Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
  echo Python not found. Attempting auto-install via winget...
  where winget >nul 2>&1
  if %errorlevel% equ 0 (
    winget install -e --id Python.Python.3.13 --accept-source-agreements
    if %errorlevel% equ 0 (
      echo Python installed. Please restart this script.
      pause
      exit /b 0
    )
  )
  echo Please install Python 3.10+ from https://www.python.org/downloads/
  echo Check "Add Python to PATH"
  pause
  exit /b 1
)

REM Check Python version 3.10+
python -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if %errorlevel% neq 0 (
  echo Python version too old, need 3.10+
  echo Current: 
  python --version
  pause
  exit /b 1
)

REM Create venv if missing
if not exist "%VENV_DIR%\Scripts\python.exe" (
  echo [2/4] Creating isolated venv at .venv\ ...
  python -m venv .venv
  if %errorlevel% neq 0 (
    echo venv creation failed, falling back to global python
    set VENV_DIR=
  )
)

REM Determine python to use
if defined VENV_DIR (
  if exist "%VENV_DIR%\Scripts\python.exe" (
    set PY_BIN=%VENV_DIR%\Scripts\python.exe
    set PIP_BIN=%VENV_DIR%\Scripts\pip.exe
    echo Using venv: %PY_BIN%
  ) else (
    set PY_BIN=python
    set PIP_BIN=pip
  )
) else (
  set PY_BIN=python
  set PIP_BIN=pip
)

echo [3/4] Installing dependencies (with auto-reset on failure)...
%PY_BIN% -m pip install --upgrade pip -q
%PY_BIN% -m pip install -r requirements.txt
if %errorlevel% neq 0 (
  echo First install failed, resetting venv and retrying...
  rmdir /s /q .venv 2>nul
  python -m venv .venv
  set PY_BIN=.venv\Scripts\python.exe
  .venv\Scripts\python -m pip install --upgrade pip -q
  .venv\Scripts\python -m pip install -r requirements.txt
  if %errorlevel% neq 0 (
    echo Still failing after reset. Try: run.bat --reset
    pause
    exit /b 1
  )
)

echo Verifying imports...
%PY_BIN% -c "import flask, openpyxl; print('   flask+openpyxl ok')" >nul 2>&1
if %errorlevel% neq 0 (
  echo Imports broken, resetting venv...
  rmdir /s /q .venv 2>nul
  python -m venv .venv
  .venv\Scripts\python -m pip install -r requirements.txt
  .venv\Scripts\python -c "import flask, openpyxl"
  if %errorlevel% neq 0 (
    echo Still broken after reset. Please run run.bat --reset or check network
    pause
    exit /b 1
  )
)

echo [4/4] Starting server on port %PORT%...
REM Kill old process on same port (best effort)
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :%PORT% ^| findstr LISTENING') do taskkill /f /pid %%a 2>nul

timeout /t 2 /nobreak >nul
start "" "http://localhost:%PORT%"

echo Server running at http://localhost:%PORT%
echo Press Ctrl+C in this window to stop, or close window
echo If env breaks, run: run.bat --reset
echo.

REM Use venv python to run
if exist ".venv\Scripts\python.exe" (
  .venv\Scripts\python run.py
) else (
  python run.py
)

echo.
echo Server stopped. You may close this window.
pause
