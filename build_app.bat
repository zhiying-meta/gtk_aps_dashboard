@echo off
REM Build script for Windows
REM Produces dist\ProductionPlanReview\ or single .exe

echo Checking Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
  echo Python not found. Please install Python 3.10+ from https://www.python.org/downloads/
  pause
  exit /b 1
)

echo Installing PyInstaller if needed...
python -m pip install pyinstaller --upgrade

set ARGS=
if "%1"=="--onefile" set ARGS=%ARGS% --onefile
if "%2"=="--onefile" set ARGS=%ARGS% --onefile
if "%1"=="--webview" set ARGS=%ARGS% --with-webview
if "%2"=="--webview" set ARGS=%ARGS% --with-webview
if "%1"=="--windowed" set ARGS=%ARGS% --windowed
if "%2"=="--windowed" set ARGS=%ARGS% --windowed

echo Building with args: %ARGS%
python build.py %ARGS%

echo.
echo Build finished. Check dist\ folder
dir dist
pause
