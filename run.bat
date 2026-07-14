@echo off
chcp 65001 >nul
title Multi-Version Plan Report
cd /d "%~dp0"

echo [1/3] Checking Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Python not found. Please install Python 3.10+ from https://www.python.org/downloads/
    pause
    exit /b
)

echo [2/3] Installing dependencies...
pip install -r requirements.txt -q

echo [3/3] Starting server...
echo Opening browser...
start http://localhost:8501
python app/server.py

pause
