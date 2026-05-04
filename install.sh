#!/usr/bin/env bash
# ──────────────────────────────────────────────
# VPlot installer for Linux / macOS
# After install, launch with:  vp
# ──────────────────────────────────────────────
set -e

echo "╔══════════════════════════════════════╗"
echo "║       VPlot Installer  v1.0.0       ║"
echo "╚══════════════════════════════════════╝"
echo ""

# Check Python >= 3.9
if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 not found. Please install Python 3.9+."
    exit 1
fi

PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJ=$(echo "$PY_VER" | cut -d. -f1)
PY_MIN=$(echo "$PY_VER" | cut -d. -f2)
if [ "$PY_MAJ" -lt 3 ] || { [ "$PY_MAJ" -eq 3 ] && [ "$PY_MIN" -lt 9 ]; }; then
    echo "ERROR: Python >= 3.9 required (found $PY_VER)"
    exit 1
fi
echo "[+] Python $PY_VER found"

# Check tkinter
if ! python3 -c "import tkinter" 2>/dev/null; then
    echo ""
    echo "WARNING: tkinter not found."
    echo "  Ubuntu/Debian:  sudo apt install python3-tk"
    echo "  Fedora/RHEL:    sudo dnf install python3-tkinter"
    echo "  Arch:           sudo pacman -S tk"
    echo "  macOS:          brew install python-tk"
    echo ""
    exit 1
fi
echo "[+] tkinter OK"

# Install
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
echo "[+] Installing VPlot from $SCRIPT_DIR ..."
pip3 install --user "$SCRIPT_DIR"

# Verify the 'vp' command is accessible
if command -v vp &>/dev/null; then
    echo ""
    echo "╔══════════════════════════════════════╗"
    echo "║  Install complete!  Launch with: vp  ║"
    echo "╚══════════════════════════════════════╝"
else
    USER_BIN=$(python3 -m site --user-base)/bin
    echo ""
    echo "[!] 'vp' command not on PATH."
    echo "    Add this to your ~/.bashrc or ~/.zshrc:"
    echo ""
    echo "      export PATH=\"$USER_BIN:\$PATH\""
    echo ""
    echo "    Then run:  source ~/.bashrc && vp"
fi
