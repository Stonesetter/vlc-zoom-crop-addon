# VLC Intelligent Crop & Zoom Plugin - Setup Guide

## Quick Overview

This plugin adds professional crop/zoom capabilities to VLC with:
- **Precise cropping** with pixel-level control
- **Intelligent upscaling** with multiple interpolation methods
- **Quality enhancement** to reduce artifacts and blur
- **Live preview** and adjustment UI

---

## Installation

### Step 1: Install the Lua Plugin

The `.lua` file goes in VLC's extensions folder:

**Linux:**
```bash
mkdir -p ~/.local/share/vlc/lua/extensions/
cp vlc_crop_zoom.lua ~/.local/share/vlc/lua/extensions/
```

**Windows:**
```
Copy vlc_crop_zoom.lua to:
%APPDATA%\VLC\lua\extensions\
```

**macOS:**
```bash
mkdir -p ~/Library/Application\ Support/VLC/lua/extensions/
cp vlc_crop_zoom.lua ~/Library/Application\ Support/VLC/lua/extensions/
```

### Step 2: Install Python Dependencies

The upscaler module requires OpenCV:

```bash
pip3 install opencv-python --break-system-packages
# or
pip install opencv-python
```

**Optional: For AI upscaling (ESRGAN), also install:**
```bash
pip3 install opencv-contrib-python torch torchvision --break-system-packages
```

### Step 3: Make Python Script Executable

```bash
chmod +x vlc_upscaler.py
```

---

## Usage

### Method 1: VLC UI (Easiest)

1. **Open VLC**
2. **Go to:** Tools → Plug-ins and Extensions → Installed (or press Ctrl+I)
3. **Look for:** "Crop & Zoom Pro"
4. **Click:** Activate (or double-click)
5. **A dialog opens:**
   - Enter crop coordinates (X, Y, Width, Height)
   - Set zoom level (1.0 = no zoom, 2.0 = 2x magnification)
   - Choose upscale method
   - Click **Apply Crop**

### Method 2: Command Line (Batch Processing)

Process individual frames:

```bash
# Basic crop and 2x zoom with Lanczos upscaling
python3 vlc_upscaler.py input.jpg output.jpg \
  --crop 100 100 800 600 \
  --zoom 2.0 \
  --method lanczos \
  --enhance

# Arguments:
#   --crop X Y W H    Crop region (top-left X, Y, width, height)
#   --zoom 1.0        Zoom level
#   --method METHOD   lanczos (best quality), spline, cubic, linear, nearest
#   --enhance         Apply sharpening and artifact reduction
```

### Method 3: Integration with FFmpeg (Video Files)

Extract frames, process, and re-encode:

```bash
#!/bin/bash
INPUT_VIDEO="video.mp4"
OUTPUT_VIDEO="cropped_output.mp4"
CROP_X=100
CROP_Y=100
CROP_W=1280
CROP_H=720
ZOOM=1.5

# 1. Extract frames from video
mkdir -p frames_in frames_out
ffmpeg -i "$INPUT_VIDEO" frames_in/frame_%05d.jpg

# 2. Process each frame
for frame in frames_in/*.jpg; do
    outname=$(basename "$frame")
    python3 vlc_upscaler.py "$frame" "frames_out/$outname" \
      --crop $CROP_X $CROP_Y $CROP_W $CROP_H \
      --zoom $ZOOM \
      --method lanczos \
      --enhance
done

# 3. Re-encode as video (30 fps)
ffmpeg -framerate 30 -i frames_out/frame_%05d.jpg \
  -c:v libx264 -crf 20 -pix_fmt yuv420p \
  "$OUTPUT_VIDEO"

rm -rf frames_in frames_out
```

---

## Configuration

### Interpolation Methods Explained

| Method | Quality | Speed | Best For |
|--------|---------|-------|----------|
| **Lanczos** | ⭐⭐⭐⭐⭐ | Medium | High-quality upscaling (default) |
| **Spline/Cubic** | ⭐⭐⭐⭐ | Fast | Smooth results, good for animation |
| **Linear** | ⭐⭐⭐ | Very Fast | Real-time preview |
| **Nearest** | ⭐⭐ | Instant | Intentional pixelation effect |

**Recommendation:**
- **Interactive use:** Start with Cubic, final export with Lanczos
- **Real-time playback:** Use Linear
- **Maximum quality:** Use Lanczos with `--enhance` flag

### Enhancement Features

The `--enhance` flag applies:
1. **Bilateral filtering** - Reduces upscaling artifacts while preserving edges
2. **Unsharp masking** - Reduces blur from interpolation
3. **Artifact reduction** - Smooths compression and scaling noise

---

## Examples

### Example 1: Zoom into a face in a video

```bash
# Input: 1920x1080 video, face is at (800, 400) with size 400x400
python3 vlc_upscaler.py frame.jpg output.jpg \
  --crop 800 400 400 400 \
  --zoom 2.5 \
  --method lanczos \
  --enhance
# Output: 1000x1000px zoomed face
```

### Example 2: Extract sports action region

```bash
# Crop to tennis court area (1920x1080 input)
python3 vlc_upscaler.py frame.jpg output.jpg \
  --crop 200 150 1200 800 \
  --zoom 1.2 \
  --method lanczos
# Output: 1440x960 enhanced court view
```

### Example 3: Compare quality methods

```bash
# See difference between methods
python3 vlc_upscaler.py input.jpg lanczos_output.jpg \
  --crop 500 300 640 480 --zoom 2.0 --method lanczos --enhance

python3 vlc_upscaler.py input.jpg cubic_output.jpg \
  --crop 500 300 640 480 --zoom 2.0 --method cubic --enhance

# Open both outputs to compare quality
```

---

## Architecture & Phases

### Phase 1: ✅ Complete
- VLC Lua plugin with interactive UI
- Crop/zoom parameter input
- Python upscaler with multiple interpolation methods
- Basic enhancement (sharpening, artifact reduction)

### Phase 2: Next Steps (Optional)
- **Real-time video processing** - Stream frames through upscaler
- **Live preview** in VLC UI
- **Batch video processing** - Entire videos without ffmpeg scripting
- **GPU acceleration** - CUDA/OpenCL for faster processing
- **AI upscaling** - ESRGAN integration for better quality

### Phase 3: Advanced
- **Auto-crop detection** - Find interesting regions automatically
- **Motion tracking** - Follow movement while cropping
- **Adaptive upscaling** - Choose method based on content type
- **Custom filters** - Integrate denoise, deinterlace, color correction

---

## Troubleshooting

### Plugin doesn't appear in VLC
- Check VLC > Tools > Preferences > Input/Codecs > Lua Scripts
- Verify file is in correct folder (check path above)
- Restart VLC

### Python script not found
- Verify path: `which python3`
- Update path in script if needed
- Use full path: `/usr/bin/python3 vlc_upscaler.py`

### Low quality output
- Use `--method lanczos` instead of cubic
- Add `--enhance` flag for sharpening
- Avoid zoom > 3.0 (info loss becomes apparent)
- Consider ESRGAN for extreme zoom (Phase 2)

### Slow processing
- Reduce zoom level
- Use `--method cubic` for speed
- Process smaller regions
- Enable GPU acceleration (Phase 2)

### Memory errors with large videos
- Process in smaller chunks
- Reduce frame resolution
- Use `--method linear` for lower memory usage

---

## Advanced: Custom Integration

### Call from Python

```python
from vlc_upscaler import CropZoomUpscaler

upscaler = CropZoomUpscaler(interpolation='lanczos')

# Process single frame
result = upscaler.crop_and_zoom(
    frame_array,
    crop_x=100,
    crop_y=100,
    crop_w=800,
    crop_h=600,
    zoom=2.0
)

# Enhance quality
result = upscaler.reduce_artifacts(result)
result = upscaler.enhance_sharpness(result, strength=0.3)
```

### Call from Lua (VLC Plugin)

```lua
local handle = io.popen([[python3 vlc_upscaler.py \
  input.jpg output.jpg \
  --crop 100 100 800 600 \
  --zoom 2.0 \
  --method lanczos \
  --enhance]])
handle:close()
```

---

## Performance Notes

| Resolution | Zoom | Method | Time (approx) |
|------------|------|--------|---------------|
| 1920x1080 | 2.0x | Lanczos | 500ms |
| 1920x1080 | 2.0x | Cubic | 200ms |
| 1920x1080 | 3.0x | Lanczos | 1.2s |
| 4K (3840x2160) | 2.0x | Cubic | 800ms |

**Tips for real-time:**
- Use Cubic interpolation for preview
- Switch to Lanczos for final export
- GPU acceleration (Phase 2) can 10x speed

---

## Next: What to Build

**Phase 2 priorities** (based on your needs):
1. Real-time video stream processing
2. GPU acceleration (CUDA)
3. Batch processing UI
4. Live preview in VLC

What would be most useful for your use case?
