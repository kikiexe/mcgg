"""
Live Hero Occupancy Detector for Bench and Board using Computer Vision
"""
import cv2
import numpy as np
from typing import List, Tuple

from src.constants.coordinates import BoardCoords

class HeroDetector:
    def __init__(self):
        # 8 Slot Bench Akurat (Y: 965, X: 450..1480)
        self.bench_centers = BoardCoords.BENCH_SLOTS

    def scan_occupied_bench_slots(self, frame: np.ndarray) -> List[Tuple[int, int, int]]:
        """
        Scans all 8 bench slots live using Computer Vision (Edge & Contour density).
        Returns list of (slot_index, center_x, center_y) for slots that ACTUALLY contain a hero.
        """
        occupied_slots = []
        for idx, (cx, cy) in enumerate(self.bench_centers, start=1):
            # Crop area tubuh hero yang berdiri di atas ubin heksagonal (Y: 820 - 930)
            roi = frame[820:930, cx - 45:cx + 45]
            if roi.shape[0] == 0 or roi.shape[1] == 0:
                continue

            gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            edges = cv2.Canny(gray, 50, 150)
            edge_density = int(np.sum(edges > 0))

            # Ambang batas kalibrasi visual: Ubin kosong ~950-1050, ada hero > 1300
            if edge_density > 1300:
                occupied_slots.append((idx, cx, cy))

        return occupied_slots
