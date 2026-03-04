#!/usr/bin/env bash
# VLC Crop & Zoom - Quick Start Examples
# Run these commands to process your first video

set -e

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║      VLC Intelligent Crop & Zoom - Quick Start Guide          ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Check dependencies
echo "Checking dependencies..."

if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 not found. Install it:"
    echo "   Ubuntu: sudo apt-get install python3"
    echo "   macOS: brew install python3"
    exit 1
fi

if ! python3 -c "import cv2" 2>/dev/null; then
    echo "❌ OpenCV not installed. Installing..."
    pip3 install opencv-python --break-system-packages || pip install opencv-python
fi

if ! command -v ffmpeg &> /dev/null; then
    echo "❌ FFmpeg not found. Install it:"
    echo "   Ubuntu: sudo apt-get install ffmpeg"
    echo "   macOS: brew install ffmpeg"
    echo "   Windows: Download from ffmpeg.org"
    exit 1
fi

echo "✓ All dependencies ready"
echo ""

# Parse arguments
if [ $# -eq 0 ]; then
    echo "Usage: ./quickstart.sh [command] [args]"
    echo ""
    echo "Commands:"
    echo "  gui         Launch the interactive GUI player (Shift+scroll zoom, drag-to-crop)"
    echo "  single      Process a single image frame"
    echo "  video       Process an entire video file"
    echo "  compare     Compare interpolation methods"
    echo "  batch       Process multiple videos"
    echo "  install     Install VLC Lua plugin"
    echo ""
    echo "Examples:"
    echo "  ./quickstart.sh gui                                               # open GUI player"
    echo "  ./quickstart.sh gui myvideo.mp4                                   # open GUI with file"
    echo "  ./quickstart.sh single input.jpg 100 100 800 600 2.0 lanczos"
    echo "  ./quickstart.sh video input.mp4 output.mp4 100 100 1280 720 1.5"
    echo "  ./quickstart.sh compare input.jpg 100 100 640 480 1.5"
    echo ""
    exit 0
fi

COMMAND=$1

# ========== GUI PLAYER ==========
if [ "$COMMAND" = "gui" ]; then
    # Check for PyQt5 and python-vlc; offer to install if missing
    if ! python3 -c "import PyQt5" 2>/dev/null; then
        echo "PyQt5 not found. Installing..."
        pip3 install PyQt5 --break-system-packages 2>/dev/null || pip3 install PyQt5
    fi
    if ! python3 -c "import vlc" 2>/dev/null; then
        echo "python-vlc not found. Installing..."
        pip3 install python-vlc --break-system-packages 2>/dev/null || pip3 install python-vlc
    fi

    # Optional: pass a video file as the second argument
    VIDEO_ARG="${2:-}"
    echo "Launching GUI player..."
    python3 vlc_player_gui.py $VIDEO_ARG
    exit 0
fi

# ========== INSTALL PLUGIN ==========
if [ "$COMMAND" = "install" ]; then
    echo "Installing VLC Plugin..."
    
    # Use case for POSIX-compatible OS detection (avoids [[ ]] portability issues)
    case "$OSTYPE" in
        linux-gnu*)
            mkdir -p ~/.local/share/vlc/lua/extensions/
            cp vlc_crop_zoom.lua ~/.local/share/vlc/lua/extensions/
            echo "✓ Installed to ~/.local/share/vlc/lua/extensions/"
            ;;
        darwin*)
            mkdir -p ~/Library/Application\ Support/VLC/lua/extensions/
            cp vlc_crop_zoom.lua ~/Library/Application\ Support/VLC/lua/extensions/
            echo "✓ Installed to ~/Library/Application Support/VLC/lua/extensions/"
            ;;
        *)
            echo "Please copy vlc_crop_zoom.lua to:"
            echo "  Windows: %APPDATA%\\VLC\\lua\\extensions\\"
            exit 1
            ;;
    esac
    
    echo ""
    echo "Restart VLC and go to Tools > Plug-ins and Extensions"
    exit 0
fi

# ========== SINGLE IMAGE PROCESSING ==========
if [ "$COMMAND" = "single" ]; then
    if [ $# -lt 8 ]; then
        echo "Usage: ./quickstart.sh single [input] [x] [y] [width] [height] [zoom] [method]"
        echo ""
        echo "Example (crop face and 2x zoom):"
        echo "  ./quickstart.sh single photo.jpg 800 400 400 400 2.5 lanczos"
        exit 1
    fi
    
    INPUT=$2
    CROP_X=$3
    CROP_Y=$4
    CROP_W=$5
    CROP_H=$6
    ZOOM=$7
    METHOD=$8
    OUTPUT="${INPUT%.*}_cropped.jpg"
    
    echo "Processing single image..."
    echo "  Input: $INPUT"
    echo "  Crop: ($CROP_X, $CROP_Y) ${CROP_W}x${CROP_H}"
    echo "  Zoom: ${ZOOM}x"
    echo "  Method: $METHOD"
    
    python3 vlc_upscaler.py "$INPUT" "$OUTPUT" \
        --crop $CROP_X $CROP_Y $CROP_W $CROP_H \
        --zoom $ZOOM \
        --method $METHOD \
        --enhance
    
    echo ""
    echo "✓ Output saved to: $OUTPUT"
    exit 0
fi

# ========== VIDEO PROCESSING ==========
if [ "$COMMAND" = "video" ]; then
    if [ $# -lt 8 ]; then
        echo "Usage: ./quickstart.sh video [input] [output] [x] [y] [width] [height] [zoom]"
        echo ""
        echo "Example (sports video, 1.5x zoom on action region):"
        echo "  ./quickstart.sh video game.mp4 output.mp4 200 150 1200 800 1.5"
        exit 1
    fi
    
    INPUT=$2
    OUTPUT=$3
    CROP_X=$4
    CROP_Y=$5
    CROP_W=$6
    CROP_H=$7
    ZOOM=$8
    
    echo "Processing video..."
    echo "  Input: $INPUT"
    echo "  Output: $OUTPUT"
    echo "  Crop: ($CROP_X, $CROP_Y) ${CROP_W}x${CROP_H}"
    echo "  Zoom: ${ZOOM}x"
    echo ""
    
    python3 video_processor.py "$INPUT" "$OUTPUT" \
        --crop $CROP_X $CROP_Y $CROP_W $CROP_H \
        --zoom $ZOOM \
        --method lanczos \
        --enhance \
        --quality 20
    
    exit 0
fi

# ========== COMPARE METHODS ==========
if [ "$COMMAND" = "compare" ]; then
    if [ $# -lt 6 ]; then
        echo "Usage: ./quickstart.sh compare [input] [x] [y] [width] [height] [zoom]"
        echo ""
        echo "Example:"
        echo "  ./quickstart.sh compare photo.jpg 100 100 640 480 1.5"
        exit 1
    fi
    
    INPUT=$2
    CROP_X=$3
    CROP_Y=$4
    CROP_W=$5
    CROP_H=$6
    ZOOM=${7:-1.5}
    
    echo "Comparing interpolation methods..."
    echo ""
    
    METHODS=("lanczos" "cubic" "linear" "nearest")
    
    for method in "${METHODS[@]}"; do
        OUTPUT="${INPUT%.*}_${method}.jpg"
        
        echo "→ Processing with $method..."
        
        python3 vlc_upscaler.py "$INPUT" "$OUTPUT" \
            --crop $CROP_X $CROP_Y $CROP_W $CROP_H \
            --zoom $ZOOM \
            --method $method \
            --enhance > /dev/null 2>&1
        
        if [ -f "$OUTPUT" ]; then
            SIZE=$(ls -lh "$OUTPUT" | awk '{print $5}')
            echo "  ✓ ${method}_output.jpg ($SIZE)"
        fi
    done
    
    echo ""
    echo "Comparison complete! Open all images to compare quality."
    echo "Recommendation: lanczos (best quality) vs cubic (faster)"
    exit 0
fi

# ========== BATCH PROCESSING ==========
if [ "$COMMAND" = "batch" ]; then
    echo "Batch Video Processing"
    echo ""
    echo "Create a 'videos.txt' file with one video per line:"
    echo "  input1.mp4"
    echo "  input2.mp4"
    echo "  input3.mp4"
    echo ""
    echo "Then run with crop parameters:"
    echo "  ./quickstart.sh batch 100 100 1280 720 1.5"
    echo ""
    
    if [ $# -lt 5 ]; then
        echo "Usage: ./quickstart.sh batch [x] [y] [width] [height] [zoom]"
        exit 1
    fi
    
    if [ ! -f "videos.txt" ]; then
        echo "❌ videos.txt not found"
        exit 1
    fi
    
    CROP_X=$2
    CROP_Y=$3
    CROP_W=$4
    CROP_H=$5
    ZOOM=${6:-1.0}
    
    echo "Processing videos..."
    echo "  Crop: ($CROP_X, $CROP_Y) ${CROP_W}x${CROP_H}"
    echo "  Zoom: ${ZOOM}x"
    echo ""
    
    COUNT=0
    while IFS= read -r INPUT; do
        # Skip empty lines and comment lines (# prefix) - POSIX case avoids [[ =~ ]]
        case "$INPUT" in
            ''|'#'*) continue ;;
        esac
        
        if [ ! -f "$INPUT" ]; then
            echo "⚠ Skipping missing: $INPUT"
            continue
        fi
        
        OUTPUT="${INPUT%.*}_processed.mp4"
        
        echo "[$((++COUNT))] Processing: $INPUT"
        
        python3 video_processor.py "$INPUT" "$OUTPUT" \
            --crop $CROP_X $CROP_Y $CROP_W $CROP_H \
            --zoom $ZOOM \
            --method lanczos \
            --enhance
        
        echo ""
    done < videos.txt
    
    echo "✓ Batch processing complete!"
    exit 0
fi

echo "Unknown command: $COMMAND"
exit 1
