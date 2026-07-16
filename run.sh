#!/bin/bash
# Gated/Ungated/CTB Report - Startup Script
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

MIN_PYTHON="3.10"

# ── Auto-install Python if missing ──
install_python() {
    echo "📥 Python $MIN_PYTHON+ not found, attempting auto-install..."

    # macOS via Homebrew
    if [[ "$OSTYPE" == "darwin"* ]]; then
        if command -v brew &>/dev/null; then
            echo "   Detected Homebrew, installing Python..."
            brew install python
            # Refresh PATH so python3 is found
            if [[ -x /opt/homebrew/bin/brew ]]; then
                eval "$(/opt/homebrew/bin/brew shellenv)"
            elif [[ -x /usr/local/bin/brew ]]; then
                eval "$(/usr/local/bin/brew shellenv)"
            fi
            hash -r 2>/dev/null || true
            return 0
        fi
        # macOS via official installer (download .pkg)
        echo "   Homebrew not found. Would you like to:"
        echo "     1) Install Homebrew first (recommended)"
        echo "     2) Download Python from python.org"
        read -p "   Choice [1/2]: " choice
        if [[ "$choice" == "1" ]]; then
            echo "   Installing Homebrew..."
            /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
            # Source brew to update PATH
            if [[ -x /opt/homebrew/bin/brew ]]; then
                eval "$(/opt/homebrew/bin/brew shellenv)"
            elif [[ -x /usr/local/bin/brew ]]; then
                eval "$(/usr/local/bin/brew shellenv)"
            fi
            hash -r 2>/dev/null || true
            echo "   Installing Python via Homebrew..."
            brew install python
            if [[ -x /opt/homebrew/bin/brew ]]; then
                eval "$(/opt/homebrew/bin/brew shellenv)"
            elif [[ -x /usr/local/bin/brew ]]; then
                eval "$(/usr/local/bin/brew shellenv)"
            fi
            hash -r 2>/dev/null || true
            return 0
        else
            open "https://www.python.org/downloads/"
            echo "   Please install Python $MIN_PYTHON+ from the opened webpage, then re-run this script."
            exit 1
        fi
    fi

    # Linux via apt
    if command -v apt-get &>/dev/null; then
        echo "   Detected apt, installing python3 + pip..."
        sudo apt-get update -qq && sudo apt-get install -y python3 python3-pip python3-venv
        return 0
    fi

    # Linux via yum (CentOS/RHEL 7)
    if command -v yum &>/dev/null; then
        echo "   Detected yum, installing python3 + pip..."
        sudo yum install -y python3 python3-pip
        return 0
    fi

    # Linux via dnf (Fedora/RHEL 8+)
    if command -v dnf &>/dev/null; then
        echo "   Detected dnf, installing python3 + pip..."
        sudo dnf install -y python3 python3-pip
        return 0
    fi

    echo "❌ Could not auto-install Python. Please install manually:"
    echo "   https://www.python.org/downloads/"
    exit 1
}

# ── Ensure python3 exists ──
echo "🔍 Checking Python..."
if ! command -v python3 &>/dev/null; then
    install_python
    # Re-check after install
    if ! command -v python3 &>/dev/null; then
        echo "❌ Python installation seems to have failed. Please install manually:"
        echo "   https://www.python.org/downloads/"
        exit 1
    fi
fi

# Check version
PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
if python3 -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" 2>/dev/null; then
    echo "   Python $PY_VER ✓"
else
    echo "⚠️  Python $PY_VER detected, but 3.10+ is required."
    echo "   Please upgrade: https://www.python.org/downloads/"
    exit 1
fi

# ── Ensure pip is available ──
if ! command -v pip3 &>/dev/null; then
    echo "📥 pip3 not found, installing..."
    python3 -m ensurepip --upgrade
fi

echo "📦 Installing dependencies..."
pip3 install -r requirements.txt -q

echo "🚀 Starting server..."
python3 run.py &

sleep 2

PORT=${PORT:-8502}
echo "🌐 Opening browser..."
if command -v open &>/dev/null; then
    open http://localhost:$PORT
elif command -v xdg-open &>/dev/null; then
    xdg-open http://localhost:$PORT
fi

echo ""
echo "✅ Server started: http://localhost:$PORT"
echo "   Press Ctrl+C to stop"
wait
