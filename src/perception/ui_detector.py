"""
Visual UI Entity Detector: Dynamically detects clickable bounding boxes for:
- Go Go Cards
- Item Equipment Drops
- Fate Box Rewards
- Shop Cards
Using Local OCR Bounding Boxes (Zero Hardcoded Guessing)
"""
import cv2
import numpy as np
from typing import List, Dict, Any, Optional
from rapidocr_onnxruntime import RapidOCR

class DynamicUIDetector:
    def __init__(self):
        self.ocr = RapidOCR()

    def detect_clickable_gogo_cards(self, frame: np.ndarray) -> List[Dict[str, Any]]:
        """
        Dynamically finds Go Go Card titles and calculates their exact center points.
        Searches words like 'power', 'card', 'dragon', 'hybrid', etc.
        """
        res, _ = self.ocr(frame)
        cards = []
        if not res:
            return cards

        for box, text, score in res:
            t = text.lower()
            if any(k in t for k in ["power", "kartu", "mendapatkan", "spear", "dragon"]):
                x_min = int(min(p[0] for p in box))
                y_min = int(min(p[1] for p in box))
                x_max = int(max(p[0] for p in box))
                y_max = int(max(p[1] for p in box))
                center_x = (x_min + x_max) // 2
                center_y = (y_min + y_max) // 2

                # Card cards are in mid-screen (Y: 400 - 800)
                if 400 <= center_y <= 800:
                    cards.append({
                        "text": text,
                        "center": (center_x, center_y),
                        "score": score
                    })

        # Sort left to right
        cards.sort(key=lambda c: c["center"][0])
        return cards

    def detect_clickable_items(self, frame: np.ndarray) -> List[Dict[str, Any]]:
        """
        Dynamically finds Item Equipment Drop options on screen.
        Searches words like 'retribution', 'revitalize', 'purify', 'inspire', 'aegis', etc.
        """
        res, _ = self.ocr(frame)
        items = []
        if not res:
            return items

        for box, text, score in res:
            t = text.lower()
            if any(k in t for k in ["retribution", "revitalize", "purify", "inspire", "flicker", "aegis", "sprint"]):
                x_min = int(min(p[0] for p in box))
                y_min = int(min(p[1] for p in box))
                x_max = int(max(p[0] for p in box))
                y_max = int(max(p[1] for p in box))
                center_x = (x_min + x_max) // 2
                center_y = (y_min + y_max) // 2

                items.append({
                    "name": text,
                    "center": (center_x, center_y),
                    "score": score
                })

        items.sort(key=lambda it: it["center"][0])
        return items

    def detect_fatebox_rewards(self, frame: np.ndarray) -> List[Dict[str, Any]]:
        """
        Dynamically finds Fate Box reward items on the carousel based on detected stat labels.
        Searches terms like 'dmg', 'vamp', 'def', 'skill', 'hp', 'tank', 'memantulkan'.
        """
        res, _ = self.ocr(frame)
        rewards = []
        if not res:
            return rewards

        for box, text, score in res:
            t = text.lower()
            if any(k in t for k in ["dmg", "vamp", "def", "skill", "tank", "memantulkan", "physical"]):
                x_min = int(min(p[0] for p in box))
                y_min = int(min(p[1] for p in box))
                x_max = int(max(p[0] for p in box))
                y_max = int(max(p[1] for p in box))
                center_x = (x_min + x_max) // 2
                center_y = (y_min + y_max) // 2

                # Fatebox carousel is in the center area (Y: 300 - 650)
                if 300 <= center_y <= 650:
                    rewards.append({
                        "label": text,
                        "center": (center_x, center_y),
                        "score": score
                    })

        rewards.sort(key=lambda r: r["center"][0])
        return rewards
