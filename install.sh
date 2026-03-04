#!/usr/bin/env bash
# install.sh - One-command installer for VLC Crop & Zoom Pro
# Usage: bash install.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LUA_PLUGIN="vlc_crop_zoom.lua"
PLUGIN_NAME="Crop & Zoom Pro"

echo "============================================"
echo "  VLC Crop & Zoom Pro - Installer"
echo "============================================"
echo ""

# --- Check Python ---
if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 not found. Please install Python 3.8+."
    exit 1
fi

# --- Check pip ---
if ! python3 -m pip --version &>/dev/null; then
    echo "ERROR: pip not found. Install with: sudo apt install python3-pip"
    exit 1
fi

# --- Install Python dependencies ---
echo "[1/3] Installing Python dependencies..."
# Try normal install first; fall back to --break-system-packages for Ubuntu 23.04+
# which blocks pip installs outside a virtual environment by default
python3 -m pip install --upgrade pip -q 2>/dev/null || \
    python3 -m pip install --upgrade pip -q --break-system-packages
python3 -m pip install -r "$SCRIPT_DIR/requirements.txt" 2>/dev/null || \
    python3 -m pip install -r "$SCRIPT_DIR/requirements.txt" --break-system-packages
echo "      Done."
echo ""

# --- Install VLC Lua plugin ---
echo "[2/3] Installing VLC Lua plugin..."

OS="$(uname -s)"
case "$OS" in
    Linux*)
        VLC_EXT_DIR="$HOME/.local/share/vlc/lua/extensions"
        ;;
    Darwin*)
        VLC_EXT_DIR="$HOME/Library/Application Support/org.videolan.vlc/lua/extensions"
        ;;
    MINGW*|MSYS*|CYGWIN*)
        echo ""
        echo "  Windows detected. Please copy the plugin manually:"
        echo "  From: $SCRIPT_DIR/$LUA_PLUGIN"
        echo "  To:   %APPDATA%\\vlc\\lua\\extensions\\"
        echo "  (Create the extensions folder if it doesn't exist)"
        VLC_EXT_DIR=""
        ;;
    *)
        echo "  Unknown OS: $OS"
        echo "  Please manually copy $LUA_PLUGIN to your VLC extensions folder."
        VLC_EXT_DIR=""
        ;;
esac

if [ -n "$VLC_EXT_DIR" ]; then
    mkdir -p "$VLC_EXT_DIR"
    cp "$SCRIPT_DIR/$LUA_PLUGIN" "$VLC_EXT_DIR/$LUA_PLUGIN"
    echo "      Installed to: $VLC_EXT_DIR/$LUA_PLUGIN"
fi
echo ""

# --- Make quickstart.sh executable ---
echo "[3/3] Setting permissions..."
chmod +x "$SCRIPT_DIR/quickstart.sh"
echo "      quickstart.sh is now executable."
echo ""

# --- Verify FFmpeg ---
echo "--------------------------------------------"
if command -v ffmpeg &>/dev/null; then
    echo "  FFmpeg: $(ffmpeg -version 2>&1 | head -1)"
else
    echo "  WARNING: FFmpeg not found."
    echo "  Video processing requires FFmpeg:"
    echo "    Ubuntu/Debian: sudo apt install ffmpeg"
    echo "    macOS:         brew install ffmpeg"
fi
echo ""

echo "============================================"
echo "  Installation complete!"
echo "============================================"
echo ""
echo "Next steps:"
echo "  1. Restart VLC"
echo "  2. Go to Tools → Plugins and Extensions"
echo "  3. Find and activate '$PLUGIN_NAME'"
echo ""
echo "Command-line usage:"
echo "  Single image:  bash quickstart.sh single input.jpg output.jpg 100 100 800 450 2.0"
echo "  Full video:    bash quickstart.sh video input.mp4 output.mp4 100 100 800 450 2.0"
echo "  All methods:   bash quickstart.sh compare input.jpg 100 100 800 450"
echo ""
