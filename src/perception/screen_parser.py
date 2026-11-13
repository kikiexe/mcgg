"""
Perception Module: Extracts game status from screen frame using Local RapidOCR
"""
import re
import cv2
import numpy as np
from typing import Dict, Any, List, Optional
from rapidocr_onnxruntime import RapidOCR

from src.constants.coordinates import StatusRegions, ShopCardCoords

class ScreenParser:
    def __init__(self):
        self.ocr = RapidOCR()

    def crop_region(self, frame: np.ndarray, box: tuple) -> np.ndarray:
        x_min, y_min, x_max, y_max = box
        return frame[y_min:y_max, x_min:x_max]

    def read_text_in_region(self, frame: np.ndarray, box: tuple) -> str:
        cropped = self.crop_region(frame, box)
        result, _ = self.ocr(cropped)
        if not result:
            return ""
        return " ".join([item[1] for item in result]).strip()

    def parse_digits_in_region(self, frame: np.ndarray, box: tuple, default: int = 0) -> int:
        text = self.read_text_in_region(frame, box)
        digits = re.findall(r'\d+', text)
        if digits:
            return int("".join(digits))
        return default

    def detect_special_phases(self, frame: np.ndarray) -> str:
        """
        Detects: 'FATE_BOX' | 'GOGO_CARD' | 'ITEM_SELECTION' | 'NONE'
        """
        # Crop area judul atas (Y: 10 - 250, X: 400 - 1500)
        header_crop = frame[10:250, 400:1500]
        res, _ = self.ocr(header_crop)
        if res:
            full_text = " ".join([item[1] for item in res]).lower()
            if "pilih hadiah" in full_text or "tentukan" in full_text:
                return "FATE_BOX"
            if "kartu" in full_text or "power" in full_text or "pilih" in full_text:
                return "GOGO_CARD"
            if "item" in full_text or "equipment" in full_text:
                return "ITEM_SELECTION"
        return "NONE"

    def detect_combat_active(self, frame: np.ndarray) -> bool:
        """
        Mendeteksi apakah ronde sedang dalam fase tempur animasi aktif.
        Kriteria:
        1. Bilah HP musuh (Red HP Bar) memiliki geometri persegi panjang horizontal pipih
           (lebar 25..120 px, tinggi 3..10 px, rasio aspek w/h >= 4.0).
        2. Area pemindaian dibatasi pada papan catur murni (Y: 180..680, X: 400..1550),
           mengecualikan area laci toko bawah dan hero card portraits.
        """
        board_roi = frame[180:680, 400:1550]
        red_mask = (board_roi[:, :, 2] > 180) & (board_roi[:, :, 1] < 60) & (board_roi[:, :, 0] < 60)
        contours, _ = cv2.findContours(red_mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        hp_bar_count = 0
        for c in contours:
            _, _, w, h = cv2.boundingRect(c)
            if 25 <= w <= 120 and 3 <= h <= 10 and (w / max(1, h)) >= 4.0:
                hp_bar_count += 1
                
        return hp_bar_count >= 1

    def extract_game_status(self, frame: np.ndarray) -> Dict[str, Any]:
        gold = self.parse_digits_in_region(frame, StatusRegions.GOLD_REGION, default=0)
        round_str = self.read_text_in_region(frame, StatusRegions.ROUND_REGION)
        timer = self.parse_digits_in_region(frame, StatusRegions.TIMER_REGION, default=0)
        
        # Sanitasi timer: Batasi range 0-60 detik untuk mencegah glitch OCR (misal: '2424' -> 24)
        if timer > 60:
            first_two = str(timer)[:2]
            timer = int(first_two) if int(first_two) <= 60 else (timer % 100)

        # Sanitasi label ronde dari interferensi pembacaan OCR
        if round_str:
            round_str = round_str.replace("11-", "II-").replace("111-", "III-").strip()

        level_str = self.read_text_in_region(frame, StatusRegions.LEVEL_REGION)
        level_digits = re.findall(r'\d+', level_str)
        level = int(level_digits[0]) if level_digits else 3

        special_phase = self.detect_special_phases(frame)
        is_combat = self.detect_combat_active(frame)

        return {
            "gold": gold,
            "round": round_str if round_str else "UNKNOWN",
            "timer_seconds": timer,
            "level": level,
            "special_phase": special_phase,
            "is_combat": is_combat
        }

    def extract_shop_cards(self, frame: np.ndarray) -> List[Dict[str, Any]]:
        slots = [
            ShopCardCoords.SLOT_1_BOX,
            ShopCardCoords.SLOT_2_BOX,
            ShopCardCoords.SLOT_3_BOX,
            ShopCardCoords.SLOT_4_BOX,
            ShopCardCoords.SLOT_5_BOX,
        ]
        
        shop_cards = []
        for idx, box in enumerate(slots, start=1):
            text = self.read_text_in_region(frame, box)
            is_empty = len(text.strip()) == 0 or "sold" in text.lower()
            shop_cards.append({
                "slot": idx,
                "raw_text": text,
                "is_empty": is_empty
            })
        return shop_cards
