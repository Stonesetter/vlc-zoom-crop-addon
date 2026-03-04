#!/usr/bin/env python3
"""
VLC Crop & Zoom Video Processor
Process entire video files with crop, zoom, and upscaling
"""

import subprocess
import tempfile
import shutil
import argparse
import sys
from pathlib import Path
from vlc_upscaler import CropZoomUpscaler

class VideoProcessor:
    """Process entire video files with crop/zoom/upscaling"""
    
    def __init__(self, input_video: str, output_video: str, temp_dir: str = None):
        """
        Initialize video processor
        
        Args:
            input_video: Path to input video
            output_video: Path to output video
            temp_dir: Temporary directory for frames (auto-created if None)
        """
        self.input_video = Path(input_video)
        self.output_video = Path(output_video)
        self.temp_dir = Path(temp_dir) if temp_dir else Path(tempfile.mkdtemp())
        self.frames_in = self.temp_dir / "frames_in"
        self.frames_out = self.temp_dir / "frames_out"
        
        if not self.input_video.exists():
            raise FileNotFoundError(f"Input video not found: {input_video}")
    
    def extract_frames(self, fps: int = 30) -> int:
        """
        Extract frames from video using FFmpeg
        
        Args:
            fps: Frames per second to extract
        
        Returns:
            Number of frames extracted
        """
        print(f"Extracting frames from {self.input_video.name}...")
        
        self.frames_in.mkdir(parents=True, exist_ok=True)
        
        cmd = [
            'ffmpeg',
            '-i', str(self.input_video),
            '-q:v', '2',  # High quality
            '-vf', f'fps={fps}',
            str(self.frames_in / 'frame_%05d.jpg')
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            
            frame_files = list(self.frames_in.glob('frame_*.jpg'))
            print(f"✓ Extracted {len(frame_files)} frames")
            return len(frame_files)
        
        except subprocess.CalledProcessError as e:
            print(f"Error extracting frames: {e.stderr}")
            sys.exit(1)
        except FileNotFoundError:
            print("Error: FFmpeg not found. Install it:")
            print("  Ubuntu: sudo apt-get install ffmpeg")
            print("  macOS: brew install ffmpeg")
            print("  Windows: Download from ffmpeg.org")
            sys.exit(1)
    
    def process_frames(self,
                      crop_x: int,
                      crop_y: int,
                      crop_w: int,
                      crop_h: int,
                      zoom: float = 1.0,
                      method: str = 'lanczos',
                      enhance: bool = True,
                      show_progress: bool = True) -> int:
        """
        Process extracted frames through upscaler
        
        Args:
            crop_x, crop_y, crop_w, crop_h: Crop parameters
            zoom: Zoom level
            method: Interpolation method
            enhance: Apply enhancement
            show_progress: Show progress bar
        
        Returns:
            Number of successfully processed frames
        """
        print(f"Processing frames with {method} interpolation...")
        
        self.frames_out.mkdir(parents=True, exist_ok=True)
        upscaler = CropZoomUpscaler(interpolation=method)
        
        frame_files = sorted(self.frames_in.glob('frame_*.jpg'))
        total = len(frame_files)
        processed = 0
        
        for idx, frame_path in enumerate(frame_files, 1):
            output_path = self.frames_out / frame_path.name
            
            success = upscaler.process_frame_file(
                str(frame_path),
                str(output_path),
                crop_x, crop_y, crop_w, crop_h,
                zoom,
                enhance
            )
            
            if success:
                processed += 1
            
            if show_progress:
                pct = (idx / total) * 100
                bar_len = 40
                filled = int(bar_len * idx / total)
                bar = '█' * filled + '░' * (bar_len - filled)
                print(f"\r[{bar}] {idx}/{total} ({pct:.1f}%)", end='', flush=True)
        
        print()  # New line
        print(f"✓ Processed {processed}/{total} frames")
        return processed
    
    def encode_video(self,
                    fps: int = 30,
                    crf: int = 20,
                    codec: str = 'libx264') -> bool:
        """
        Encode processed frames back into video
        
        Args:
            fps: Frames per second for output
            crf: Quality (0-51, lower=better, 20=default high quality)
            codec: Video codec (libx264, libx265, etc.)
        
        Returns:
            True if successful
        """
        print(f"Encoding video ({codec}, quality={crf})...")
        
        cmd = [
            'ffmpeg',
            '-framerate', str(fps),
            '-i', str(self.frames_out / 'frame_%05d.jpg'),
            '-c:v', codec,
            '-crf', str(crf),
            '-pix_fmt', 'yuv420p',
            '-y',  # Overwrite output
            str(self.output_video)
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            print(f"✓ Video encoded: {self.output_video}")
            
            # Show file size
            if self.output_video.exists():
                size_mb = self.output_video.stat().st_size / (1024 * 1024)
                print(f"  Size: {size_mb:.1f} MB")
            
            return True
        
        except subprocess.CalledProcessError as e:
            print(f"Error encoding video: {e.stderr}")
            return False
    
    def process_complete(self,
                        crop_x: int,
                        crop_y: int,
                        crop_w: int,
                        crop_h: int,
                        zoom: float = 1.0,
                        method: str = 'lanczos',
                        enhance: bool = True,
                        fps: int = 30,
                        quality: int = 20,
                        cleanup: bool = True) -> bool:
        """
        Complete pipeline: extract → process → encode
        
        Args:
            crop_x, crop_y, crop_w, crop_h: Crop parameters
            zoom: Zoom level
            method: Interpolation method
            enhance: Apply enhancement
            fps: Output frames per second
            quality: Output video quality (CRF, 0-51)
            cleanup: Delete temporary files
        
        Returns:
            True if successful
        """
        try:
            # Step 1: Extract frames
            total_frames = self.extract_frames(fps)
            
            if total_frames == 0:
                print("Error: No frames extracted")
                return False
            
            # Step 2: Process frames
            processed = self.process_frames(
                crop_x, crop_y, crop_w, crop_h,
                zoom, method, enhance
            )
            
            if processed == 0:
                print("Error: No frames processed")
                return False
            
            # Step 3: Encode video
            success = self.encode_video(fps, quality)
            
            # Step 4: Cleanup
            if cleanup and success:
                print("Cleaning up temporary files...")
                shutil.rmtree(self.temp_dir)
                print("✓ Done!")
            
            return success
        
        except KeyboardInterrupt:
            print("\n\nCancelled by user")
            return False
        except Exception as e:
            print(f"Error: {e}")
            return False


def main():
    """CLI interface"""
    parser = argparse.ArgumentParser(
        description='Process entire video files with crop, zoom, and upscaling',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Crop and 2x zoom a video
  python3 video_processor.py input.mp4 output.mp4 \
    --crop 100 100 1280 720 --zoom 2.0

  # High-quality output with enhancement
  python3 video_processor.py input.mp4 output.mp4 \
    --crop 0 0 1920 1080 --zoom 1.5 \
    --method lanczos --enhance --quality 18

  # Fast processing with cubic interpolation
  python3 video_processor.py input.mp4 output.mp4 \
    --crop 200 150 1200 800 --zoom 1.2 \
    --method cubic --quality 22

  # Extract to 60 fps
  python3 video_processor.py input.mp4 output.mp4 \
    --crop 100 100 1280 720 --zoom 1.5 --fps 60
        """
    )
    
    parser.add_argument('input', help='Input video file')
    parser.add_argument('output', help='Output video file')
    
    parser.add_argument('--crop', nargs=4, type=int, metavar=('X', 'Y', 'W', 'H'),
                       required=True,
                       help='Crop region: X Y Width Height')
    
    parser.add_argument('--zoom', type=float, default=1.0,
                       help='Zoom level (default: 1.0)')
    
    parser.add_argument('--method', choices=['lanczos', 'spline', 'cubic', 'linear', 'nearest'],
                       default='lanczos',
                       help='Interpolation method (default: lanczos)')
    
    parser.add_argument('--enhance', action='store_true',
                       help='Apply sharpening and artifact reduction')
    
    parser.add_argument('--fps', type=int, default=30,
                       help='Output frames per second (default: 30)')
    
    parser.add_argument('--quality', type=int, default=20, metavar='CRF',
                       help='Output quality 0-51 (0=lossless, 20=default, 51=worst)')
    
    parser.add_argument('--codec', choices=['libx264', 'libx265', 'libvpx-vp9'],
                       default='libx264',
                       help='Video codec (default: libx264)')
    
    parser.add_argument('--temp-dir', help='Custom temporary directory')
    
    parser.add_argument('--no-cleanup', action='store_true',
                       help='Keep temporary frames after processing')
    
    args = parser.parse_args()
    
    try:
        processor = VideoProcessor(args.input, args.output, args.temp_dir)
        
        success = processor.process_complete(
            crop_x=args.crop[0],
            crop_y=args.crop[1],
            crop_w=args.crop[2],
            crop_h=args.crop[3],
            zoom=args.zoom,
            method=args.method,
            enhance=args.enhance,
            fps=args.fps,
            quality=args.quality,
            cleanup=not args.no_cleanup
        )
        
        sys.exit(0 if success else 1)
    
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
