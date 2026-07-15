@echo off
chcp 65001 >nul
title Gated/Ungated/CTB Report
cd /d "%~dp0"

echo [1/3] Checking Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Python not found. Please install Python 3.10+ from https://www.python.org/downloads/
    pause
    exit /b
)

echo [2/3] Installing dependencies...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo.
    echo Dependency installation failed. Check your network connection or run manually:
    echo   pip install -r requirements.txt
    pause
    exit /b
)

echo [3/3] Starting server...
timeout /t 1 /nobreak >nul
set PORT=8502
start "" "http://localhost:%PORT%"
call python run.py

echo.
echo Server has stopped. You may close this window.
pause
