"""
Live Screen Capture Module using mss (Ultra Fast <10ms)
"""
import mss
import numpy as np
import cv2
from typing import Optional, Tuple

class ScreenCapture:
    def __init__(self, monitor_idx: int = 1):
        self.sct = mss.mss()
        # Default monitor 1 (Primary display)
        self.monitor = self.sct.monitors[monitor_idx]

    def capture_frame(self, target_region: Optional[Tuple[int, int, int, int]] = None) -> np.ndarray:
        """
        Captures screen.
        If target_region is None, captures primary 1920x1080 screen.
        target_region: (left, top, width, height)
        Returns: BGR numpy image (OpenCV format)
        """
        bbox = self.monitor
        if target_region:
            left, top, width, height = target_region
            bbox = {"left": left, "top": top, "width": width, "height": height}

        raw_screenshot = self.sct.grab(bbox)
        # Convert BGRA to BGR
        frame = np.array(raw_screenshot)
        return cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
