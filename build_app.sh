#!/bin/bash
# Build script for macOS / Linux
# Produces dist/ProductionPlanReview/ (one-folder) or single file
# Usage: ./build_app.sh [--onefile] [--webview]

set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

echo "🔍 Checking Python..."
if ! command -v python3 &>/dev/null; then
  echo "❌ python3 not found"
  exit 1
fi

# Install pyinstaller if missing
if ! python3 -c "import PyInstaller" &>/dev/null; then
  echo "📦 Installing PyInstaller..."
  python3 -m pip install pyinstaller --upgrade
fi

# Parse args
ONEFILE=""
WINDOWED=""
WITH_WEBVIEW=""

for arg in "$@"; do
  case $arg in
    --onefile) ONEFILE="--onefile" ;;
    --windowed) WINDOWED="--windowed" ;;
    --webview) WITH_WEBVIEW="--with-webview" ;;
  esac
done

if [[ "$WITH_WEBVIEW" == "--webview" ]]; then
  echo "📦 Installing pywebview + waitress..."
  python3 -m pip install pywebview waitress --upgrade || true
else
  python3 -m pip install waitress -q || true
fi

echo "🚀 Building..."
python3 build.py $ONEFILE $WINDOWED $WITH_WEBVIEW

echo ""
echo "✅ Build finished. Check dist/ folder"
ls -lh dist/ || true
