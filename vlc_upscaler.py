#!/usr/bin/env python3
"""
VLC Crop & Zoom Upscaler Module
Handles high-quality image upscaling with multiple interpolation methods
"""

import cv2
import numpy as np
from pathlib import Path
from typing import Literal
import argparse
import sys

# Interpolation methods mapping
INTERPOLATION_METHODS = {
    'lanczos': cv2.INTER_LANCZOS4,
    'spline': cv2.INTER_CUBIC,  # OpenCV's cubic is spline-based
    'cubic': cv2.INTER_CUBIC,
    'nearest': cv2.INTER_NEAREST,
    'linear': cv2.INTER_LINEAR,
}

class CropZoomUpscaler:
    """High-quality crop and zoom upscaler for video frames"""
    
    def __init__(self, interpolation: str = 'lanczos'):
        """
        Initialize upscaler with interpolation method
        
        Args:
            interpolation: 'lanczos', 'spline', 'cubic', 'nearest', 'linear'
        """
        self.method = interpolation
        self.interp_flag = INTERPOLATION_METHODS.get(interpolation, cv2.INTER_LANCZOS4)
    
    def crop_and_zoom(self, 
                     frame: np.ndarray,
                     crop_x: int,
                     crop_y: int,
                     crop_w: int,
                     crop_h: int,
                     zoom: float = 1.0) -> np.ndarray:
        """
        Crop a frame region and zoom with quality upscaling
        
        Args:
            frame: Input image (BGR or grayscale)
            crop_x, crop_y: Top-left corner of crop region
            crop_w, crop_h: Crop region dimensions
            zoom: Zoom level (1.0 = no zoom, 2.0 = 2x magnification)
        
        Returns:
            Cropped and upscaled frame
        """
        h, w = frame.shape[:2]
        
        # Validate crop bounds
        crop_x = max(0, min(crop_x, w - 1))
        crop_y = max(0, min(crop_y, h - 1))
        crop_w = min(crop_w, w - crop_x)
        crop_h = min(crop_h, h - crop_y)
        
        # Extract crop region
        cropped = frame[crop_y:crop_y + crop_h, crop_x:crop_x + crop_w]
        
        if cropped.size == 0:
            return frame
        
        # Apply zoom with upscaling
        if zoom > 1.0:
            new_w = int(crop_w * zoom)
            new_h = int(crop_h * zoom)
            zoomed = cv2.resize(cropped, (new_w, new_h), interpolation=self.interp_flag)
            return zoomed
        elif zoom < 1.0 and zoom > 0:
            # Downscaling (if zoom < 1)
            new_w = int(crop_w * zoom)
            new_h = int(crop_h * zoom)
            downsampled = cv2.resize(cropped, (new_w, new_h), interpolation=self.interp_flag)
            return downsampled
        else:
            return cropped
    
    def enhance_sharpness(self, frame: np.ndarray, strength: float = 0.3) -> np.ndarray:
        """
        Apply unsharp masking to enhance edge definition
        Helps reduce blurriness from upscaling
        
        Args:
            frame: Input image
            strength: Sharpening strength (0.0-1.0)
        
        Returns:
            Sharpened frame
        """
        if strength <= 0:
            return frame
        
        # Unsharp mask: original + (original - blurred) * strength
        blurred = cv2.GaussianBlur(frame, (5, 5), 0)
        
        if len(frame.shape) == 3:  # Color image
            sharpened = cv2.addWeighted(frame, 1.0 + strength, blurred, -strength, 0)
        else:  # Grayscale
            sharpened = cv2.addWeighted(frame, 1.0 + strength, blurred, -strength, 0)
        
        return np.clip(sharpened, 0, 255).astype(frame.dtype)
    
    def reduce_artifacts(self, frame: np.ndarray) -> np.ndarray:
        """
        Apply bilateral filtering to reduce upscaling artifacts
        Preserves edges while smoothing
        
        Args:
            frame: Input image
        
        Returns:
            Artifact-reduced frame
        """
        if len(frame.shape) == 3:  # Color image
            # Bilateral filter works well on color
            filtered = cv2.bilateralFilter(frame, 9, 75, 75)
        else:  # Grayscale
            filtered = cv2.bilateralFilter(frame, 9, 75, 75)
        
        return filtered
    
    def apply_super_resolution(self, frame: np.ndarray, upscale_factor: int = 2) -> np.ndarray:
        """
        Apply ESRGAN-style super-resolution upscaling
        Requires cv2.dnn_superres module (optional)
        
        Args:
            frame: Input image
            upscale_factor: 2x, 3x, or 4x upscaling
        
        Returns:
            Super-resolved frame (or original if module not available)
        """
        try:
            from cv2 import dnn_superres
            
            sr = dnn_superres.DnnSuperResImpl_create()
            model_path = f"ESRGAN_x{upscale_factor}.pb"  # Requires model file
            sr.readModel(model_path)
            sr.setModel('esrgan', upscale_factor)
            
            return sr.upsample(frame)
        except (ImportError, FileNotFoundError):
            # Fall back to standard interpolation
            h, w = frame.shape[:2]
            return cv2.resize(frame, (w * upscale_factor, h * upscale_factor), 
                            interpolation=self.interp_flag)
    
    def process_frame_file(self,
                          input_path: str,
                          output_path: str,
                          crop_x: int,
                          crop_y: int,
                          crop_w: int,
                          crop_h: int,
                          zoom: float = 1.0,
                          enhance: bool = True) -> bool:
        """
        Process a frame image file
        
        Args:
            input_path: Path to input image
            output_path: Path to output image
            crop_x, crop_y, crop_w, crop_h: Crop parameters
            zoom: Zoom level
            enhance: Apply sharpening and artifact reduction
        
        Returns:
            True if successful
        """
        try:
            # Read image
            frame = cv2.imread(input_path)
            if frame is None:
                print(f"Error: Could not read image {input_path}")
                return False
            
            # Process
            result = self.crop_and_zoom(frame, crop_x, crop_y, crop_w, crop_h, zoom)
            
            if enhance:
                result = self.reduce_artifacts(result)
                result = self.enhance_sharpness(result, strength=0.3)
            
            # Write output
            success = cv2.imwrite(output_path, result)
            
            if success:
                print(f"Successfully processed: {output_path}")
                h, w = result.shape[:2]
                print(f"Output dimensions: {w}x{h}")
            else:
                print(f"Error: Could not write output to {output_path}")
            
            return success
        
        except Exception as e:
            print(f"Error processing frame: {e}", file=sys.stderr)
            return False


def main():
    """CLI interface for testing and batch processing"""
    parser = argparse.ArgumentParser(
        description='VLC Crop & Zoom Upscaler',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Crop and 2x zoom with Lanczos upscaling
  python3 vlc_upscaler.py input.jpg output.jpg --crop 100 100 800 600 --zoom 2.0 --method lanczos
  
  # Just crop with enhancement
  python3 vlc_upscaler.py input.jpg output.jpg --crop 50 50 1280 720 --enhance
  
  # Compare interpolation methods
  python3 vlc_upscaler.py input.jpg out_lanczos.jpg --crop 100 100 640 480 --zoom 1.5 --method lanczos
  python3 vlc_upscaler.py input.jpg out_cubic.jpg --crop 100 100 640 480 --zoom 1.5 --method cubic
        """
    )
    
    parser.add_argument('input', help='Input image path')
    parser.add_argument('output', help='Output image path')
    parser.add_argument('--crop', nargs=4, type=int, metavar=('X', 'Y', 'W', 'H'),
                       default=[0, 0, 1920, 1080],
                       help='Crop region: X Y Width Height (default: 0 0 1920 1080)')
    parser.add_argument('--zoom', type=float, default=1.0,
                       help='Zoom level (default: 1.0)')
    parser.add_argument('--method', choices=INTERPOLATION_METHODS.keys(),
                       default='lanczos',
                       help='Interpolation method (default: lanczos)')
    parser.add_argument('--enhance', action='store_true',
                       help='Apply sharpening and artifact reduction')
    
    args = parser.parse_args()
    
    upscaler = CropZoomUpscaler(interpolation=args.method)
    success = upscaler.process_frame_file(
        args.input,
        args.output,
        args.crop[0], args.crop[1], args.crop[2], args.crop[3],
        args.zoom,
        args.enhance
    )
    
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
