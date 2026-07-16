#!/bin/bash
# Production Plan Review - Robust Startup Script with auto-reset
# - Isolated venv (.venv) to avoid polluting system python
# - Auto-detects broken env / missing modules and resets
# - Supports --reset and --clean flags

set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

MIN_PYTHON="3.10"
VENV_DIR="$DIR/.venv"
RESET=false
CLEAN=false
PORT="${PORT:-8502}"

# Parse args
for arg in "$@"; do
  case $arg in
    --reset) RESET=true ;;
    --clean) CLEAN=true ;;
    --port=*) PORT="${arg#--port=}" ;;
    -h|--help)
      echo "Usage: ./run.sh [--reset] [--clean] [--port=8502]"
      echo "  --reset  : Force recreate venv and reinstall deps (fix env issues)"
      echo "  --clean  : Clean uploads and pycache"
      echo "  --port=N : Specify port"
      exit 0
      ;;
  esac
done

# ── Clean if requested ──
if [ "$CLEAN" = true ]; then
  echo "🧹 Cleaning uploads, pycache, .venv..."
  rm -rf "$DIR/uploads"/* 2>/dev/null || true
  rm -rf "$DIR/app/__pycache__" "$DIR/app/modules"/*/__pycache__ 2>/dev/null || true
  rm -rf "$DIR/__pycache__" 2>/dev/null || true
  rm -rf "$DIR/build" "$DIR/dist" 2>/dev/null || true
  # keep .venv unless --reset also given
  if [ "$RESET" = true ]; then
    rm -rf "$VENV_DIR"
    echo "   Removed venv"
  fi
  echo "   Clean done"
  # If only --clean without --reset, continue to start
  if [ "$RESET" = false ]; then
    echo ""
  fi
fi

# ── Auto-install Python if missing ──
install_python() {
    echo "📥 Python $MIN_PYTHON+ not found, attempting auto-install..."
    if [[ "$OSTYPE" == "darwin"* ]]; then
        if command -v brew &>/dev/null; then
            echo "   Detected Homebrew, installing Python..."
            brew install python
            if [[ -x /opt/homebrew/bin/brew ]]; then eval "$(/opt/homebrew/bin/brew shellenv)"; elif [[ -x /usr/local/bin/brew ]]; then eval "$(/usr/local/bin/brew shellenv)"; fi
            hash -r 2>/dev/null || true
            return 0
        fi
        echo "   Homebrew not found. Install options:"
        echo "     1) Install Homebrew (recommended)"
        echo "     2) Open python.org"
        read -p "   Choice [1/2]: " choice
        if [[ "$choice" == "1" ]]; then
            /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
            if [[ -x /opt/homebrew/bin/brew ]]; then eval "$(/opt/homebrew/bin/brew shellenv)"; elif [[ -x /usr/local/bin/brew ]]; then eval "$(/usr/local/bin/brew shellenv)"; fi
            hash -r 2>/dev/null || true
            brew install python
            return 0
        else
            open "https://www.python.org/downloads/"
            echo "   Please install Python $MIN_PYTHON+ and re-run."
            exit 1
        fi
    fi
    if command -v apt-get &>/dev/null; then
        echo "   Detected apt, installing python3 + venv..."
        sudo apt-get update -qq && sudo apt-get install -y python3 python3-pip python3-venv
        return 0
    fi
    if command -v yum &>/dev/null; then sudo yum install -y python3 python3-pip; return 0; fi
    if command -v dnf &>/dev/null; then sudo dnf install -y python3 python3-pip; return 0; fi
    echo "❌ Could not auto-install Python: https://www.python.org/downloads/"
    exit 1
}

# ── Ensure python3 exists ──
echo "🔍 Checking Python..."
if ! command -v python3 &>/dev/null; then
    install_python
    if ! command -v python3 &>/dev/null; then echo "❌ Python install failed"; exit 1; fi
fi

PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
if python3 -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" 2>/dev/null; then
    echo "   Python $PY_VER ✓"
else
    echo "⚠️  Python $PY_VER detected, but 3.10+ required."
    exit 1
fi

# ── Ensure venv module available ──
if ! python3 -m venv --help &>/dev/null; then
    echo "📦 Installing python3-venv..."
    if command -v apt-get &>/dev/null; then sudo apt-get install -y python3-venv || true; fi
fi

# ── Venv handling with auto-reset ──
create_venv() {
    echo "🐍 Creating isolated venv at .venv/..."
    rm -rf "$VENV_DIR"
    if python3 -m venv "$VENV_DIR" 2>&1; then
        echo "   venv created ✓"
        return 0
    else
        echo "⚠️  venv creation failed, falling back to global python (not recommended)"
        return 1
    fi
}

# If --reset requested, force recreate
if [ "$RESET" = true ]; then
    echo "🔄 --reset requested, wiping .venv..."
    rm -rf "$VENV_DIR"
fi

# Create venv if missing
if [ ! -d "$VENV_DIR" ] || [ ! -f "$VENV_DIR/bin/python" ]; then
    if ! create_venv; then
        VENV_DIR=""  # fallback to global
    fi
fi

# Determine python/pip to use (venv or global)
if [ -n "$VENV_DIR" ] && [ -f "$VENV_DIR/bin/python" ]; then
    PY_BIN="$VENV_DIR/bin/python"
    PIP_BIN="$VENV_DIR/bin/pip"
    echo "   Using venv: $PY_BIN"
else
    PY_BIN="python3"
    PIP_BIN="pip3"
    if ! command -v pip3 &>/dev/null; then
        echo "📥 pip not found, bootstrapping..."
        python3 -m ensurepip --upgrade || true
        PIP_BIN="python3 -m pip"
    fi
    echo "   Using global: $PY_BIN"
fi

# ── Install deps with retry and auto-reset ──
install_deps() {
    local attempt=$1
    echo "📦 Installing dependencies (attempt $attempt)..."
    echo "   $PIP_BIN install -r requirements.txt"

    # Upgrade pip first
    $PY_BIN -m pip install --upgrade pip -q 2>&1 | grep -v "Requirement already satisfied" || true

    if $PY_BIN -m pip install -r requirements.txt -q; then
        echo "   Deps installed ✓"
        return 0
    else
        echo "⚠️  pip install failed"
        return 1
    fi
}

check_imports() {
    echo "🔍 Verifying imports..."
    if $PY_BIN -c "import flask, openpyxl; print('   flask+openpyxl ✓')" 2>&1; then
        return 0
    else
        echo "❌ Import check failed:"
        $PY_BIN -c "import flask" 2>&1 || echo "   flask missing/broken"
        $PY_BIN -c "import openpyxl" 2>&1 || echo "   openpyxl missing/broken"
        return 1
    fi
}

# Try install and check, with one auto-reset retry
if ! install_deps 1; then
    echo "🔄 First install failed, resetting venv and retrying..."
    rm -rf "$VENV_DIR"
    if create_venv; then
        PY_BIN="$VENV_DIR/bin/python"
        PIP_BIN="$VENV_DIR/bin/pip"
        if ! install_deps 2; then
            echo "❌ Still failing after reset. Please try:"
            echo "   ./run.sh --reset"
            echo "   or manually: rm -rf .venv && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
            exit 1
        fi
    else
        echo "❌ Cannot create venv and install failed"
        exit 1
    fi
fi

# Verify imports, if fails -> reset once
if ! check_imports; then
    echo "🔄 Imports broken, resetting venv..."
    rm -rf "$VENV_DIR"
    if create_venv; then
        PY_BIN="$VENV_DIR/bin/python"
        if install_deps 3 && check_imports; then
            echo "   Fixed after reset ✓"
        else
            echo "❌ Still broken after reset. Try:"
            echo "   ./run.sh --reset"
            echo "   Check requirements.txt or Python env"
            exit 1
        fi
    else
        echo "❌ Reset failed"
        exit 1
    fi
fi

# ── Start server ──
echo ""
echo "🚀 Starting server on port $PORT..."
# Kill any existing process on same port
if lsof -ti :$PORT &>/dev/null; then
    echo "   Port $PORT in use, killing old process..."
    lsof -ti :$PORT | xargs kill -9 2>/dev/null || true
    sleep 1
fi

# Use venv python if available
$PY_BIN run.py &
SERVER_PID=$!

sleep 2

# Check if server started
if ! ps -p $SERVER_PID &>/dev/null; then
    echo "❌ Server failed to start. Logs:"
    cat uploads/*.log 2>/dev/null || true
    echo "   Trying with console output..."
    $PY_BIN run.py
    exit 1
fi

echo "🌐 Opening browser..."
if command -v open &>/dev/null; then
    open http://localhost:$PORT 2>/dev/null || true
elif command -v xdg-open &>/dev/null; then
    xdg-open http://localhost:$PORT 2>/dev/null || true
fi

echo ""
echo "✅ Server running: http://localhost:$PORT (PID $SERVER_PID)"
echo "   - Logs: uploads/ or console"
echo "   - Press Ctrl+C to stop"
echo "   - If env breaks, run: ./run.sh --reset"
echo ""

# Wait for server (and handle Ctrl+C)
trap "echo ''; echo '🛑 Stopping...'; kill $SERVER_PID 2>/dev/null; exit 0" INT TERM
wait $SERVER_PID
