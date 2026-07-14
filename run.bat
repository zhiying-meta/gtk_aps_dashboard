@echo off
REM 多版本计划拼接 - 启动脚本 (Windows)
cd /d "%~dp0"

echo [1/3] 检查 Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo 请先安装 Python 3.10+: https://www.python.org/downloads/
    pause
    exit /b
)

echo [2/3] 安装依赖...
pip install -r requirements.txt -q

echo [3/3] 启动服务...
start http://localhost:8501
python app/server.py

pause
