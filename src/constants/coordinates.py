"""
MCGG Game UI Coordinates and Configuration Constants
Resolution Standard: 1920x1080 (Windowed / Borderless)
Calibrated & Visually Verified on Asset Ground Truth (Patch 7.2)
"""
from dataclasses import dataclass
from typing import Tuple, Dict, List

class UIResolution:
    WIDTH: int = 1920
    HEIGHT: int = 1080

class ShopCardCoords:
    # 5 Hero Slots di Rak Toko (Y: 200..520)
    SLOT_1_BOX: Tuple[int, int, int, int] = (290, 200, 480, 520)
    SLOT_2_BOX: Tuple[int, int, int, int] = (575, 200, 765, 520)
    SLOT_3_BOX: Tuple[int, int, int, int] = (860, 200, 1050, 520)
    SLOT_4_BOX: Tuple[int, int, int, int] = (1145, 200, 1335, 520)
    SLOT_5_BOX: Tuple[int, int, int, int] = (1430, 200, 1620, 520)
    
    SLOT_1_CLICK: Tuple[int, int] = (385, 330)
    SLOT_2_CLICK: Tuple[int, int] = (670, 330)
    SLOT_3_CLICK: Tuple[int, int] = (955, 330)
    SLOT_4_CLICK: Tuple[int, int] = (1240, 330)
    SLOT_5_CLICK: Tuple[int, int] = (1525, 330)
    
    TOGGLE_SHOP_CLICK: Tuple[int, int] = (1805, 940) # Hotkey Spasi
    OUTSIDE_SHOP_CLICK: Tuple[int, int] = (960, 200) # Klik netral menutup shop
    REROLL_CLICK: Tuple[int, int] = (1771, 543)      # Hotkey E (Biaya 2 Gold)
    LOCK_SHOP_CLICK: Tuple[int, int] = (152, 567)    # Gembok Toko
    HERO_LIST_CLICK: Tuple[int, int] = (1734, 360)   # Daftar Hero
    LEVEL_UP_CLICK: Tuple[int, int] = (80, 975)      # Hotkey F (Level Up)

class StatusRegions:
    GOLD_REGION: Tuple[int, int, int, int] = (1705, 840, 1905, 1040)
    ROUND_REGION: Tuple[int, int, int, int] = (610, 5, 700, 50)
    TIMER_REGION: Tuple[int, int, int, int] = (920, 5, 1000, 50)
    LEVEL_REGION: Tuple[int, int, int, int] = (10, 905, 150, 1045)
    COMMANDER_SKILL_REGION: Tuple[int, int, int, int] = (30, 770, 130, 868)

class BoardCoords:
    # 8 Slot Bench Cadangan (Tepat di atas platform heksagonal, Y: 965)
    BENCH_SLOTS = [
        (450, 965),   # Slot 1
        (600, 965),   # Slot 2
        (745, 965),   # Slot 3
        (890, 965),   # Slot 4
        (1040, 965),  # Slot 5
        (1190, 965),  # Slot 6
        (1335, 965),  # Slot 7
        (1480, 965),  # Slot 8
    ]

    # Grid Papan Catur 3 Baris Tempur x 7 Kolom (Row 1-3, Col 1-7)
    CHESSBOARD_GRID = {
        # Row 1 (Garis Depan)
        (1, 1): (560, 510), (1, 2): (695, 510), (1, 3): (830, 510), (1, 4): (965, 510),
        (1, 5): (1100, 510), (1, 6): (1235, 510), (1, 7): (1370, 510),
        # Row 2 (Garis Tengah)
        (2, 1): (540, 615), (2, 2): (680, 615), (2, 3): (820, 615), (2, 4): (965, 615),
        (2, 5): (1105, 615), (2, 6): (1250, 615), (2, 7): (1395, 615),
        # Row 3 (Garis Belakang)
        (3, 1): (515, 725), (3, 2): (665, 725), (3, 3): (815, 725), (3, 4): (965, 725),
        (3, 5): (1115, 725), (3, 6): (1265, 725), (3, 7): (1425, 725)
    }

class ItemEventCoords:
    # 3 Pilihan Drop Item Ronde Creep di Sidebar Kiri
    DROP_ITEM_SLOTS = [
        (152, 132),  # Item 1 (Atas)
        (152, 245),  # Item 2 (Tengah)
        (152, 360),  # Item 3 (Bawah)
    ]
    
    BAG_ICON_CLICK: Tuple[int, int] = (48, 352)
    CLOSE_MODAL_CLICK: Tuple[int, int] = (827, 110) # Tombol >>
    
    # Target Plus Slots untuk Pindah/Pasang Item ke Hero
    HERO_PLUS_SLOTS = [
        (787, 210),  # Hero 1 (Hylos)
        (579, 335),  # Hero 2 (Granger)
        (579, 462),  # Hero 3 (Vale)
    ]

class FateBoxCoords:
    CENTER_HERO_CLICK: Tuple[int, int] = (960, 610)
    REWARD_RING = [
        (447, 620),  # Kiri
        (680, 625),  # Tengah Kiri
        (1127, 300), # Atas
        (1358, 425), # Kanan Atas
        (1240, 625), # Tengah Kanan
        (1470, 620), # Kanan Jauh
    ]
    CONFIRM_CLICK: Tuple[int, int] = (1803, 970)

class GoGoCardCoords:
    CARD_1_CLICK: Tuple[int, int] = (695, 485) # Double Click
    CARD_2_CLICK: Tuple[int, int] = (1205, 485) # Double Click
    REFRESH_1_CLICK: Tuple[int, int] = (660, 840) # Dadu Gacha Kiri
    REFRESH_2_CLICK: Tuple[int, int] = (1188, 840) # Dadu Gacha Kanan
