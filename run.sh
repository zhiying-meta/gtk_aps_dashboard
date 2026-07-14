#!/bin/bash
# 多版本计划拼接 - 启动脚本
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

echo "🔍 检查 Python..."
if ! command -v python3 &>/dev/null; then
    echo "❌ 请先安装 Python 3.10+: https://www.python.org/downloads/"
    exit 1
fi

echo "📦 安装依赖..."
pip3 install -r requirements.txt -q

echo "🚀 启动服务..."
python3 app/server.py &

sleep 2

echo "🌐 正在打开浏览器..."
if command -v open &>/dev/null; then
    open http://localhost:8501
elif command -v xdg-open &>/dev/null; then
    xdg-open http://localhost:8501
fi

echo ""
echo "✅ 服务已启动: http://localhost:8501"
echo "   按 Ctrl+C 停止服务"
wait
