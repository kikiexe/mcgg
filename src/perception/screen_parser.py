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
        1. Bilah HP musuh (Red HP Bar) memiliki rona merah murni jenuh
           (HSV: H <= 8 atau H >= 175, S >= 150, V >= 150), tahan terhadap perubahan kecerahan.
        2. Geometri persegi panjang horizontal pipih (lebar 25..120 px, tinggi 3..10 px, rasio aspek w/h >= 3.5).
        3. Area pemindaian dibatasi pada papan catur murni (Y: 180..680, X: 400..1550),
           mengecualikan area laci toko bawah dan hero card portraits.
        """
        board_roi = frame[180:680, 400:1550]
        hsv = cv2.cvtColor(board_roi, cv2.COLOR_BGR2HSV)
        red_mask = ((hsv[:, :, 0] <= 8) | (hsv[:, :, 0] >= 175)) & (hsv[:, :, 1] >= 150) & (hsv[:, :, 2] >= 150)
        contours, _ = cv2.findContours(red_mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        hp_bar_count = 0
        for c in contours:
            _, _, w, h = cv2.boundingRect(c)
            if 25 <= w <= 120 and 3 <= h <= 10 and (w / max(1, h)) >= 3.5:
                hp_bar_count += 1
                
        return hp_bar_count >= 1

    def parse_player_hp(self, frame: np.ndarray, player_name: str = "veteran") -> Optional[int]:
        """
        Mengekstrak angka HP Commander lokal dari leaderboard panel kanan.
        Memindai seluruh 8 slot pemain (Y: 80..850, X: 1640..1920) untuk menemukan baris
        pemain lokal, lalu membaca angka HP di bawah nama pemain tersebut.
        """
        leaderboard_crop = frame[80:850, 1640:1920]
        res, _ = self.ocr(leaderboard_crop)
        if not res:
            return None

        items = []
        for box, text, _ in res:
            cy = int(sum(p[1] for p in box) / 4) + 80
            cx = int(sum(p[0] for p in box) / 4) + 1640
            items.append((cx, cy, text.strip()))

        p_lower = player_name.lower().strip()
        name_variants = [p_lower]
        if len(p_lower) > 3:
            name_variants.append(p_lower[1:])  # Menangani huruf pertama yang terpotong garis batas (e.g. 'eteran')

        target_cy = None
        for cx, cy, text in items:
            t_low = text.lower()
            if any(v in t_low for v in name_variants):
                target_cy = cy
                break

        if target_cy is None:
            return None

        # Cari angka HP di pita-Y tepat di bawah nama pemain (selisih Y: 25..65 px)
        for cx, cy, text in items:
            if 25 <= (cy - target_cy) <= 65 and 1670 <= cx <= 1850:
                digits = re.findall(r'^\d+$', text)
                if digits:
                    val = int(digits[0])
                    if 1 <= val <= 100:
                        return val
        return None

    def extract_game_status(self, frame: np.ndarray, player_name: str = "veteran") -> Dict[str, Any]:
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
        commander_hp = self.parse_player_hp(frame, player_name=player_name)

        return {
            "gold": gold,
            "round": round_str if round_str else "UNKNOWN",
            "timer_seconds": timer,
            "level": level,
            "commander_hp": commander_hp,
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
