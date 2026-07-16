@echo off
chcp 65001 >nul
title Production Plan Review
cd /d "%~dp0"

set PORT=%PORT: =%
if "%PORT%"=="" set PORT=8502
set VENV_DIR=.venv
set RESET=0
set CLEAN=0

REM Parse args
for %%a in (%*) do (
  if "%%a"=="--reset" set RESET=1
  if "%%a"=="--clean" (
    set CLEAN=1
    echo Cleaning uploads, pycache...
    rmdir /s /q uploads 2>nul
    mkdir uploads 2>nul
    rmdir /s /q app\__pycache__ 2>nul
    rmdir /s /q app\modules\plan_merge\__pycache__ 2>nul
    if "%RESET%"=="1" rmdir /s /q .venv 2>nul
  )
  for /f "tokens=1,2 delims==" %%b in ("%%a") do (
    if "%%b"=="--port" set PORT=%%c
  )
  echo %%a | findstr /b "--port=" >nul
  if %errorlevel% equ 0 (
    for /f "tokens=2 delims==" %%p in ("%%a") do set PORT=%%p
  )
  if "%%a"=="--help" (
    echo Usage: run.bat [--reset] [--clean] [--port=8502]
    echo   --reset : Force recreate venv and reinstall (fix env issues)
    echo   --clean : Clean uploads
    echo   --port=N: Port
    exit /b 0
  )
)

if "%RESET%"=="1" (
  echo [RESET] Forcing venv recreation...
  rmdir /s /q .venv 2>nul
)

REM ── Find Python (handles python / python3 / py launcher) ──
echo [1/5] Checking Python (supports python / python3 / py)...

set PYTHON=
REM Try python
python --version >nul 2>&1
if %errorlevel% equ 0 (
  python -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
  if %errorlevel% equ 0 (
    set PYTHON=python
  )
)
REM Try python3 if not found
if not defined PYTHON (
  python3 --version >nul 2>&1
  if %errorlevel% equ 0 (
    python3 -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
    if %errorlevel% equ 0 set PYTHON=python3
  )
)
REM Try py -3 launcher
if not defined PYTHON (
  py -3 --version >nul 2>&1
  if %errorlevel% equ 0 (
    py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
    if %errorlevel% equ 0 set PYTHON=py -3
  )
)

if not defined PYTHON (
  echo Python not found or version too old. Attempting auto-install via winget...
  where winget >nul 2>&1
  if %errorlevel% equ 0 (
    winget install -e --id Python.Python.3.12 --accept-source-agreements
    if %errorlevel% equ 0 (
      echo Python installed. Please restart this script.
      pause
      exit /b 0
    )
  )
  echo Please install Python 3.10+ from https://www.python.org/downloads/
  echo IMPORTANT: Check "Add Python to PATH" during installation
  pause
  exit /b 1
)

echo   Found: %PYTHON%
%PYTHON% --version

REM ── Diagnostic: pip / pip3 command presence (common confusion) ──
echo [2/5] Checking pip commands in PATH (diagnostics)...
where pip >nul 2>&1
if %errorlevel% equ 0 (
  for /f "delims=" %%v in ('pip --version 2^>^&1') do echo   pip command: %%v ✓ & goto :pip_done
  :pip_done
) else (
  echo   pip command: NOT FOUND (常见，未加入PATH，但可用 python -m pip 替代)
)
where pip3 >nul 2>&1
if %errorlevel% equ 0 (
  for /f "delims=" %%v in ('pip3 --version 2^>^&1') do echo   pip3 command: %%v ✓ & goto :pip3_done
  :pip3_done
) else (
  echo   pip3 command: NOT FOUND (常见，使用 python -m pip 即可)
)
echo   → 本脚本始终使用 "%PYTHON% -m pip" 而非 pip 命令，因此不受此影响 ✓

REM ── Create venv if missing ──
if not exist "%VENV_DIR%\Scripts\python.exe" (
  echo [3/5] Creating isolated venv at .venv\ using %PYTHON%...
  %PYTHON% -m venv .venv
  if %errorlevel% neq 0 (
    echo venv creation failed, trying --without-pip fallback...
    %PYTHON% -m venv --without-pip .venv
    if %errorlevel% neq 0 (
      echo venv creation failed, falling back to global python
      set VENV_DIR=
    ) else (
      echo   venv created without pip, will bootstrap later
    )
  ) else (
    echo   venv created ✓
  )
)

REM Determine python to use (always use python -m pip, not pip command)
if defined VENV_DIR (
  if exist "%VENV_DIR%\Scripts\python.exe" (
    set PY_BIN=%VENV_DIR%\Scripts\python.exe
    echo   Using venv: %PY_BIN%
  ) else (
    set PY_BIN=%PYTHON%
    echo   Using global: %PY_BIN%
  )
) else (
  set PY_BIN=%PYTHON%
  echo   Using global: %PY_BIN%
)

REM ── Ensure pip via python -m pip (handles pip command not recognized) ──
echo [4/5] Checking pip for %PY_BIN%...

%PY_BIN% -m pip --version >nul 2>&1
if %errorlevel% neq 0 (
  echo ⚠️  Detected python exists but pip is missing (pip command not found / python -m pip failed)
  echo    This is common when python installed without pip or minimal install
  echo    Attempting to bootstrap pip...

  echo    [1/5] Trying %PY_BIN% -m ensurepip --upgrade ...
  %PY_BIN% -m ensurepip --upgrade
  %PY_BIN% -m pip --version >nul 2>&1
  if %errorlevel% equ 0 goto :pip_ok

  echo    [2/5] Trying %PY_BIN% -m ensurepip --default-pip ...
  %PY_BIN% -m ensurepip --default-pip
  %PY_BIN% -m pip --version >nul 2>&1
  if %errorlevel% equ 0 goto :pip_ok

  echo    [3/5] Trying get-pip.py via PowerShell...
  powershell -Command "Invoke-WebRequest -Uri https://bootstrap.pypa.io/get-pip.py -OutFile get-pip.py" >nul 2>&1
  if exist get-pip.py (
    %PY_BIN% get-pip.py -q
    del get-pip.py
    %PY_BIN% -m pip --version >nul 2>&1
    if %errorlevel% equ 0 goto :pip_ok
  )

  echo    [4/5] Trying get-pip.py via curl (if available)...
  where curl >nul 2>&1
  if %errorlevel% equ 0 (
    curl -fsSL https://bootstrap.pypa.io/get-pip.py -o get-pip.py >nul 2>&1
    if exist get-pip.py (
      %PY_BIN% get-pip.py -q
      del get-pip.py
      %PY_BIN% -m pip --version >nul 2>&1
      if %errorlevel% equ 0 goto :pip_ok
    )
  )

  echo    [5/5] Trying get-pip.py via Python urllib (last resort)...
  %PY_BIN% -c "import urllib.request; urllib.request.urlretrieve('https://bootstrap.pypa.io/get-pip.py', 'get-pip.py'); print('download ok')" >nul 2>&1
  if exist get-pip.py (
    %PY_BIN% get-pip.py -q
    del get-pip.py
    %PY_BIN% -m pip --version >nul 2>&1
    if %errorlevel% equ 0 goto :pip_ok
  )

  echo Still no pip, resetting venv and retrying...
  rmdir /s /q .venv 2>nul
  %PYTHON% -m venv .venv
  set PY_BIN=.venv\Scripts\python.exe
  .venv\Scripts\python -m ensurepip --upgrade
  .venv\Scripts\python -m pip --version >nul 2>&1
  if %errorlevel% neq 0 (
    echo ❌ Cannot get pip even after reset
    echo    Manual fix:
    echo    %PYTHON% -m ensurepip --upgrade
    echo    curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py ^&^& %PYTHON% get-pip.py
    pause
    exit /b 1
  )
)

:pip_ok
%PY_BIN% -m pip --version >nul 2>&1
if %errorlevel% equ 0 (
  echo   pip OK via %PY_BIN% -m pip ✓
) else (
  echo ❌ pip still missing
  pause
  exit /b 1
)

echo [5/5] Installing dependencies (auto-reset on failure)...
%PY_BIN% -m pip install --upgrade pip -q
%PY_BIN% -m pip install -r requirements.txt
if %errorlevel% neq 0 (
  echo First install failed, resetting venv and retrying...
  rmdir /s /q .venv 2>nul
  %PYTHON% -m venv .venv
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
  echo Imports broken, showing details:
  %PY_BIN% -c "import flask" >nul 2>&1
  if %errorlevel% neq 0 echo   flask missing/broken
  %PY_BIN% -c "import openpyxl" >nul 2>&1
  if %errorlevel% neq 0 echo   openpyxl missing/broken
  echo Resetting venv...
  rmdir /s /q .venv 2>nul
  %PYTHON% -m venv .venv
  .venv\Scripts\python -m pip install -r requirements.txt
  .venv\Scripts\python -c "import flask, openpyxl"
  if %errorlevel% neq 0 (
    echo Still broken after reset. Try run.bat --reset
    pause
    exit /b 1
  )
)
echo   Imports OK

echo [Start] Starting server on port %PORT%...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :%PORT% ^| findstr LISTENING 2^>nul') do taskkill /f /pid %%a 2>nul

timeout /t 2 /nobreak >nul
start "" "http://localhost:%PORT%"

echo Server running at http://localhost:%PORT%
echo Press Ctrl+C to stop
echo If env breaks: run.bat --reset
echo If pip not found: script uses "python -m pip" not "pip" command
echo.

if exist ".venv\Scripts\python.exe" (
  .venv\Scripts\python run.py
) else (
  %PYTHON% run.py
)

echo.
echo Server stopped.
pause
