"""
Action Executor: Uses win32 hardware mouse_event and keybd_event
100% bypasses Unity DirectX input consumption
"""
import time
from typing import Tuple, Optional, Dict
from src.action.hardware_input import win32_click, win32_drag, win32_press_key
from src.constants.coordinates import ShopCardCoords, BoardCoords, ItemEventCoords, GoGoCardCoords, FateBoxCoords
from src.decision.models import ActionCommand

class ActionExecutor:
    def __init__(self, action_delay_ms: int = 180):
        self.delay_sec = max(action_delay_ms / 1000.0, 0.1)

    def click_point(self, x: int, y: int, label: str = ""):
        win32_click(x, y)
        if label:
            print(f"[EXECUTOR] Klik '{label}' di ({x}, {y})")

    def drag_hero_to_board(self, start_x: int, start_y: int, end_x: int, end_y: int, label: str = ""):
        win32_drag(start_x, start_y, end_x, end_y)
        if label:
            print(f"[EXECUTOR] Drag & Drop '{label}' dari ({start_x}, {start_y}) ke ({end_x}, {end_y})")

    def buy_hero_slot(self, slot: int):
        slots = {
            1: ShopCardCoords.SLOT_1_CLICK,
            2: ShopCardCoords.SLOT_2_CLICK,
            3: ShopCardCoords.SLOT_3_CLICK,
            4: ShopCardCoords.SLOT_4_CLICK,
            5: ShopCardCoords.SLOT_5_CLICK,
        }
        pt = slots.get(slot)
        if pt:
            self.click_point(pt[0], pt[1], label=f"Beli Hero Slot {slot}")

    def close_shop(self):
        # Klik netral di luar drawer toko (Idempotent: hanya menutup jika toko terbuka, tidak toggle buta)
        pt = ShopCardCoords.OUTSIDE_SHOP_CLICK
        self.click_point(pt[0], pt[1], label="Tutup Shop (Klik Netral)")

    def open_shop(self):
        # Buka shop via hotkey Spasi
        win32_press_key(0x20)
        time.sleep(self.delay_sec)

    def toggle_shop_key(self):
        win32_press_key(0x20)
        time.sleep(self.delay_sec)

    def deploy_bench_hero(self, bench_slot: int = 1):
        idx = max(0, min(bench_slot - 1, len(BoardCoords.BENCH_SLOTS) - 1))
        bench_pt = BoardCoords.BENCH_SLOTS[idx]
        
        # Penempatan terdistribusi pada grid catur 3x7 yang telah terkalibrasi
        target_positions = [
            BoardCoords.CHESSBOARD_GRID[(3, 4)],  # Center Back
            BoardCoords.CHESSBOARD_GRID[(3, 3)],  # Mid-Left Back
            BoardCoords.CHESSBOARD_GRID[(3, 5)],  # Mid-Right Back
            BoardCoords.CHESSBOARD_GRID[(2, 4)],  # Center Mid
            BoardCoords.CHESSBOARD_GRID[(1, 4)],  # Center Front
        ]
        target_pt = target_positions[(bench_slot - 1) % len(target_positions)]
        self.drag_hero_to_board(bench_pt[0], bench_pt[1], target_pt[0], target_pt[1], label=f"Deploy Bench {bench_slot}")

    def pick_fatebox_reward(self, item_idx: int = 1):
        ring = FateBoxCoords.REWARD_RING
        idx = max(0, min(item_idx - 1, len(ring) - 1))
        target_pt = ring[idx]
        self.click_point(target_pt[0], target_pt[1], label=f"Pilih Hadiah Fatebox {item_idx}")
        time.sleep(0.15)
        # Konfirmasi dengan tombol centang/X di kanan bawah
        self.click_point(FateBoxCoords.CONFIRM_CLICK[0], FateBoxCoords.CONFIRM_CLICK[1], label="Konfirmasi Fatebox")

    def equip_item_to_hero(self, item_bag_idx: int = 1, hero_target_idx: int = 1):
        # 1. Buka modal tas item di sidebar kiri
        self.click_point(ItemEventCoords.BAG_ICON_CLICK[0], ItemEventCoords.BAG_ICON_CLICK[1], label=f"Buka Tas Item (Item {item_bag_idx})")
        time.sleep(0.3)

        # 2. Klik slot '+' pada hero yang dituju
        slots = ItemEventCoords.HERO_PLUS_SLOTS
        idx = max(0, min(hero_target_idx - 1, len(slots) - 1))
        target_plus = slots[idx]
        self.click_point(target_plus[0], target_plus[1], label=f"Pasang Item ke Target Hero {hero_target_idx}")
        time.sleep(0.2)

        # 3. Tutup modal 'Hero yang Ditempatkan' dengan tombol '>>'
        self.click_point(ItemEventCoords.CLOSE_MODAL_CLICK[0], ItemEventCoords.CLOSE_MODAL_CLICK[1], label="Tutup Modal Item (>>)")
        time.sleep(0.1)

    def reroll_shop(self):
        # Jalur tunggal keyboard hotkey E untuk menghindari pembelanjaan ganda (double-spend)
        win32_press_key(0x45)
        print("[EXECUTOR] Reroll Shop via Hotkey E")

    def level_up(self):
        # Jalur tunggal keyboard hotkey F untuk menghindari level-up ganda
        win32_press_key(0x46)
        print("[EXECUTOR] Level Up via Hotkey F")

    def pick_item_option(self, option_idx: int):
        idx = max(0, min(option_idx - 1, len(ItemEventCoords.DROP_ITEM_SLOTS) - 1))
        pt = ItemEventCoords.DROP_ITEM_SLOTS[idx]
        self.click_point(pt[0], pt[1], label=f"Pilih Drop Item {option_idx}")

    def pick_gogo_card(self, card_idx: int, custom_coords: Optional[Tuple[int, int]] = None):
        if custom_coords:
            pt = custom_coords
        else:
            options = {
                1: GoGoCardCoords.CARD_1_CLICK,
                2: GoGoCardCoords.CARD_2_CLICK,
            }
            pt = options.get(card_idx, GoGoCardCoords.CARD_1_CLICK)

        # Sesuai mekanik game: Double-click untuk mengunci kartu
        self.click_point(pt[0], pt[1], label=f"Pilih Go Go Card {card_idx} (Click 1)")
        time.sleep(0.12)
        self.click_point(pt[0], pt[1], label=f"Kunci Go Go Card {card_idx} (Click 2)")

    def execute_command(self, cmd: ActionCommand):
        print(f"[ACTION] Menjalankan: {cmd.action} (slot={cmd.slot}) -> {cmd.reasoning}")
        if cmd.action == "BUY_HERO" and cmd.slot:
            self.buy_hero_slot(cmd.slot)
        elif cmd.action == "DEPLOY":
            self.deploy_bench_hero(cmd.slot if cmd.slot else 1)
        elif cmd.action == "EQUIP_ITEM":
            self.equip_item_to_hero(item_bag_idx=cmd.slot if cmd.slot else 1, hero_target_idx=1)
        elif cmd.action == "CLOSE_SHOP":
            self.close_shop()
        elif cmd.action == "REROLL":
            self.reroll_shop()
        elif cmd.action == "LEVEL_UP":
            self.level_up()
        elif cmd.action == "PICK_ITEM" and cmd.slot:
            self.pick_item_option(cmd.slot)
        elif cmd.action == "PICK_GOGO_CARD" and cmd.slot:
            self.pick_gogo_card(cmd.slot)
        elif cmd.action == "END_TURN":
            pass
