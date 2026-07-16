#!/bin/bash
# Production Plan Review - Robust Startup Script with auto-reset
# - Isolated venv (.venv) to avoid polluting system python
# - Auto-detects broken env / missing modules and resets
# - Handles case: python installed but pip command not found (use python -m pip + auto bootstrap)
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
  if [ "$RESET" = true ]; then
    rm -rf "$VENV_DIR"
    echo "   Removed venv"
  fi
  echo "   Clean done"
  if [ "$RESET" = false ]; then
    echo ""
  fi
fi

# ── Helpers ──
is_python_ok() {
  local py_bin=$1
  if ! command -v "$py_bin" &>/dev/null && [ ! -x "$py_bin" ]; then
    return 1
  fi
  # Check version >= 3.10
  if "$py_bin" -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" 2>/dev/null; then
    return 0
  else
    return 1
  fi
}

# Find a suitable python interpreter (handles python/python3 both, and brew paths)
find_python() {
  local candidates=(
    "python3"
    "python"
    "python3.13"
    "python3.12"
    "python3.11"
    "python3.10"
    "/opt/homebrew/bin/python3"
    "/usr/local/bin/python3"
    "/usr/bin/python3"
    "/opt/homebrew/bin/python"
    "/usr/local/bin/python"
  )

  for cand in "${candidates[@]}"; do
    if is_python_ok "$cand"; then
      echo "$cand"
      return 0
    fi
  done

  # Try py launcher on some systems (git bash on Windows)
  if command -v py &>/dev/null; then
    if py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" 2>/dev/null; then
      echo "py -3"
      return 0
    fi
  fi

  return 1
}

# ── Auto-install Python if missing ──
install_python() {
    echo "📥 Python $MIN_PYTHON+ not found, attempting auto-install..."
    if [[ "$OSTYPE" == "darwin"* ]]; then
        if command -v brew &>/dev/null; then
            echo "   Detected Homebrew, installing Python..."
            brew install python || brew install python@3.12 || true
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
            open "https://www.python.org/downloads/" 2>/dev/null || xdg-open "https://www.python.org/downloads/" 2>/dev/null || true
            echo "   Please install Python $MIN_PYTHON+ and re-run."
            exit 1
        fi
    fi
    if command -v apt-get &>/dev/null; then
        echo "   Detected apt, installing python3 + pip + venv..."
        sudo apt-get update -qq && sudo apt-get install -y python3 python3-pip python3-venv python3-full 2>&1 | tail -20 || sudo apt-get install -y python3 python3-pip python3-venv
        return 0
    fi
    if command -v yum &>/dev/null; then sudo yum install -y python3 python3-pip; return 0; fi
    if command -v dnf &>/dev/null; then sudo dnf install -y python3 python3-pip; return 0; fi
    if command -v pacman &>/dev/null; then sudo pacman -S --noconfirm python python-pip; return 0; fi
    echo "❌ Could not auto-install Python: https://www.python.org/downloads/"
    exit 1
}

# ── Ensure pip for a given python (handles "pip not found" case) ──
ensure_pip() {
    local py=$1
    echo "🔍 Checking pip for: $py"

    # Most reliable: python -m pip (works even if pip command missing)
    if $py -m pip --version &>/dev/null; then
        echo "   pip available via $py -m pip ✓ ($($py -m pip --version 2>&1 | head -1))"
        return 0
    fi

    echo "⚠️  Detected python exists but pip is missing/unavailable (pip command not found / python -m pip failed)"
    echo "   This is common when python is installed without pip or via minimal install"
    echo "   Attempting to bootstrap pip..."

    # 1) ensurepip (stdlib)
    echo "   [1/6] Trying $py -m ensurepip --upgrade ..."
    if $py -m ensurepip --upgrade 2>&1; then
        echo "   ensurepip succeeded"
        if $py -m pip --version &>/dev/null; then echo "   pip now available ✓"; return 0; fi
    fi

    echo "   [2/6] Trying $py -m ensurepip --default-pip ..."
    if $py -m ensurepip --default-pip 2>&1; then
        if $py -m pip --version &>/dev/null; then echo "   pip now available ✓"; return 0; fi
    fi

    # 2) Try system package manager to install pip-only (for case: python exists but pip missing)
    if [[ "$OSTYPE" != "darwin"* ]]; then
        echo "   [3/6] Trying system package manager to install pip..."
        if command -v apt-get &>/dev/null; then
            echo "       apt-get install python3-pip python3-venv"
            sudo apt-get update -qq && sudo apt-get install -y python3-pip python3-venv 2>&1 | tail -10 || true
            if $py -m pip --version &>/dev/null; then echo "   pip fixed via apt ✓"; return 0; fi
        fi
        if command -v yum &>/dev/null; then
            sudo yum install -y python3-pip 2>&1 | tail -10 || true
            if $py -m pip --version &>/dev/null; then echo "   pip fixed via yum ✓"; return 0; fi
        fi
        if command -v dnf &>/dev/null; then
            sudo dnf install -y python3-pip 2>&1 | tail -10 || true
            if $py -m pip --version &>/dev/null; then echo "   pip fixed via dnf ✓"; return 0; fi
        fi
        if command -v pacman &>/dev/null; then
            sudo pacman -S --noconfirm python-pip 2>&1 | tail -10 || true
            if $py -m pip --version &>/dev/null; then echo "   pip fixed via pacman ✓"; return 0; fi
        fi
    fi

    # 3) get-pip.py via curl
    if command -v curl &>/dev/null; then
        echo "   [4/6] Downloading get-pip.py via curl..."
        if curl -fsSL https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py 2>&1; then
            $py /tmp/get-pip.py -q 2>&1 | tail -5 || $py /tmp/get-pip.py 2>&1 | tail -20
            rm -f /tmp/get-pip.py
            if $py -m pip --version &>/dev/null; then echo "   pip installed via curl get-pip.py ✓"; return 0; fi
        fi
    fi

    # 4) get-pip.py via wget
    if command -v wget &>/dev/null; then
        echo "   [5/6] Downloading get-pip.py via wget..."
        if wget -q https://bootstrap.pypa.io/get-pip.py -O /tmp/get-pip.py 2>&1; then
            $py /tmp/get-pip.py -q 2>&1 | tail -5 || $py /tmp/get-pip.py 2>&1 | tail -20
            rm -f /tmp/get-pip.py
            if $py -m pip --version &>/dev/null; then echo "   pip installed via wget get-pip.py ✓"; return 0; fi
        fi
    fi

    # 5) get-pip.py via python urllib (last resort, no curl/wget needed)
    echo "   [6/6] Downloading get-pip.py via python urllib..."
    if $py -c "import urllib.request; urllib.request.urlretrieve('https://bootstrap.pypa.io/get-pip.py', '/tmp/get-pip.py'); print('download ok')" 2>&1; then
        $py /tmp/get-pip.py -q 2>&1 | tail -5 || $py /tmp/get-pip.py 2>&1 | tail -20
        rm -f /tmp/get-pip.py
        if $py -m pip --version &>/dev/null; then echo "   pip installed via urllib get-pip.py ✓"; return 0; fi
    fi

    echo "❌ Failed to get pip for $py"
    echo "   Manual fix:"
    echo "     $py -m ensurepip --upgrade"
    echo "     curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py && $py get-pip.py"
    echo "     # Debian/Ubuntu: sudo apt-get install python3-pip python3-venv"
    echo "     # macOS: brew reinstall python"
    return 1
}

# ── Ensure python3/python exists ──
echo "🔍 Checking Python..."
PYTHON_BIN=""
if FOUND=$(find_python); then
    PYTHON_BIN="$FOUND"
    echo "   Found: $FOUND ($($FOUND --version 2>&1 | head -1 || $FOUND -c 'import sys; print(sys.version)' 2>&1))"
else
    echo "   No suitable python found"
    install_python
    # Retry after install
    if FOUND=$(find_python); then
        PYTHON_BIN="$FOUND"
        echo "   Found after install: $FOUND"
    else
        echo "❌ Python install failed or not in PATH"
        echo "   Please install Python $MIN_PYTHON+ from https://www.python.org/downloads/"
        exit 1
    fi
fi

# Extra diagnostic: pip / pip3 command presence (user confusion case)
echo "🔍 Checking pip commands in PATH (for diagnostics)..."
if command -v pip &>/dev/null; then
    echo "   pip command: $(pip --version 2>&1 | head -1) ✓"
else
    echo "   pip command: NOT FOUND (常见，可能是未加入PATH，但可用 python -m pip 替代)"
fi
if command -v pip3 &>/dev/null; then
    echo "   pip3 command: $(pip3 --version 2>&1 | head -1) ✓"
else
    echo "   pip3 command: NOT FOUND (常见，使用 python -m pip 即可)"
fi
echo "   → 本脚本始终使用 '$PYTHON_BIN -m pip' 而非 pip 命令，因此不受此影响 ✓"

PY_VER=$($PYTHON_BIN -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
if $PYTHON_BIN -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" 2>/dev/null; then
    echo "   Python $PY_VER ✓ (via $PYTHON_BIN)"
else
    echo "⚠️  Python $PY_VER detected via $PYTHON_BIN, but 3.10+ required."
    exit 1
fi

# ── Ensure venv module available ──
if ! $PYTHON_BIN -m venv --help &>/dev/null; then
    echo "📦 venv module missing, installing python3-venv..."
    if command -v apt-get &>/dev/null; then sudo apt-get install -y python3-venv python3-full 2>&1 | tail -5 || true; fi
fi

# ── Venv handling with auto-reset ──
create_venv() {
    local py_bin=$1
    echo "🐍 Creating isolated venv at .venv/ using $py_bin..."
    rm -rf "$VENV_DIR"

    # Try normal creation
    if $py_bin -m venv "$VENV_DIR" 2>&1; then
        echo "   venv created ✓"
        return 0
    fi

    # If fails (common on Debian where ensurepip disabled), try --without-pip then bootstrap
    echo "⚠️  venv creation failed, trying --without-pip + ensurepip fallback..."
    if $py_bin -m venv --without-pip "$VENV_DIR" 2>&1; then
        echo "   venv created without pip, bootstrapping pip..."
        if [ -f "$VENV_DIR/bin/python" ]; then
            ensure_pip "$VENV_DIR/bin/python" || $VENV_DIR/bin/python -m ensurepip --default-pip || true
        elif [ -f "$VENV_DIR/bin/python3" ]; then
            ensure_pip "$VENV_DIR/bin/python3" || $VENV_DIR/bin/python3 -m ensurepip --default-pip || true
        fi
        if [ -f "$VENV_DIR/bin/python" ] && $VENV_DIR/bin/python -m pip --version &>/dev/null; then
            echo "   venv fixed via ensurepip ✓"
            return 0
        fi
    fi

    echo "⚠️  venv creation failed, falling back to global python (not recommended)"
    return 1
}

# If --reset requested, force recreate
if [ "$RESET" = true ]; then
    echo "🔄 --reset requested, wiping .venv..."
    rm -rf "$VENV_DIR"
fi

# Create venv if missing
if [ ! -d "$VENV_DIR" ] || { [ ! -f "$VENV_DIR/bin/python" ] && [ ! -f "$VENV_DIR/bin/python3" ]; }; then
    if ! create_venv "$PYTHON_BIN"; then
        VENV_DIR=""  # fallback to global
    fi
fi

# Determine python to use (venv or global) - always use "python -m pip" to avoid pip command not found
if [ -n "$VENV_DIR" ] && [ -f "$VENV_DIR/bin/python" ]; then
    PY_BIN="$VENV_DIR/bin/python"
    echo "   Using venv: $PY_BIN"
elif [ -n "$VENV_DIR" ] && [ -f "$VENV_DIR/bin/python3" ]; then
    PY_BIN="$VENV_DIR/bin/python3"
    echo "   Using venv: $PY_BIN"
else
    # Use found python bin, handle "py -3" special case
    if [[ "$PYTHON_BIN" == "py -3" ]]; then
        PY_BIN="py -3"
    else
        PY_BIN="$PYTHON_BIN"
    fi
    echo "   Using global: $PY_BIN"
fi

# ── Ensure pip for current PY_BIN ──
if ! ensure_pip "$PY_BIN"; then
    echo "🔄 pip still missing for $PY_BIN, resetting venv and retrying..."
    rm -rf "$DIR/.venv"
    VENV_DIR="$DIR/.venv"
    if create_venv "$PYTHON_BIN"; then
        if [ -f "$VENV_DIR/bin/python" ]; then
            PY_BIN="$VENV_DIR/bin/python"
        elif [ -f "$VENV_DIR/bin/python3" ]; then
            PY_BIN="$VENV_DIR/bin/python3"
        fi
        ensure_pip "$PY_BIN" || { echo "❌ Cannot get pip even after reset"; exit 1; }
    else
        echo "❌ Cannot create venv and pip missing"
        exit 1
    fi
fi

# ── Install deps with retry and auto-reset ──
install_deps() {
    local attempt=$1
    echo "📦 Installing dependencies (attempt $attempt)..."
    echo "   $PY_BIN -m pip install -r requirements.txt"

    # Upgrade pip first (using python -m pip, not pip command)
    $PY_BIN -m pip install --upgrade pip -q 2>&1 | grep -v "Requirement already satisfied" || true

    if $PY_BIN -m pip install -r requirements.txt -q; then
        echo "   Deps installed ✓"
        return 0
    else
        echo "⚠️  pip install failed"
        $PY_BIN -m pip install -r requirements.txt 2>&1 | tail -30
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
    rm -rf "$DIR/.venv"
    VENV_DIR="$DIR/.venv"
    if create_venv "$PYTHON_BIN"; then
        if [ -f "$VENV_DIR/bin/python" ]; then
            PY_BIN="$VENV_DIR/bin/python"
        elif [ -f "$VENV_DIR/bin/python3" ]; then
            PY_BIN="$VENV_DIR/bin/python3"
        fi
        ensure_pip "$PY_BIN"
        if ! install_deps 2; then
            echo "❌ Still failing after reset. Please try:"
            echo "   ./run.sh --reset"
            echo "   or manually: rm -rf .venv && $PYTHON_BIN -m venv .venv && .venv/bin/python -m pip install -r requirements.txt"
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
    rm -rf "$DIR/.venv"
    VENV_DIR="$DIR/.venv"
    if create_venv "$PYTHON_BIN"; then
        if [ -f "$VENV_DIR/bin/python" ]; then
            PY_BIN="$VENV_DIR/bin/python"
        elif [ -f "$VENV_DIR/bin/python3" ]; then
            PY_BIN="$VENV_DIR/bin/python3"
        fi
        ensure_pip "$PY_BIN"
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
export PORT
# Kill any existing process on same port
if command -v lsof &>/dev/null && lsof -ti :$PORT &>/dev/null; then
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
echo "   - Note: pip command not found is handled via '$PY_BIN -m pip'"
echo ""

# Wait for server (and handle Ctrl+C)
trap "echo ''; echo '🛑 Stopping...'; kill $SERVER_PID 2>/dev/null; exit 0" INT TERM
wait $SERVER_PID
