"""
MCGG Autonomous Agent - Live Production Loop with Zero Hardcoded Coordinates
Uses Computer Vision (Canny Hero Detector + Dynamic OCR Bounding Boxes)
"""
import os
import sys
import json
import time
import cv2
from typing import Dict, Any, List

from src.perception.screen_capture import ScreenCapture
from src.perception.screen_parser import ScreenParser
from src.perception.hero_detector import HeroDetector
from src.perception.ui_detector import DynamicUIDetector
from src.decision.models import GameState, ShopSlot, TurnDecision, ActionCommand
from src.decision.kb_loader import KnowledgeBase
from src.decision.llm_router import LLMBrain
from src.action.executor import ActionExecutor
from src.action.window_manager import GameWindowManager
from src.constants.coordinates import BoardCoords

def load_config() -> dict:
    config_path = r"C:\Projects\mcgg\config.json"
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)

def run_live_bot():
    print("==========================================================")
    print("MCGG AUTONOMOUS AGENT - FULL DYNAMIC VISION CONTROLLER")
    print("==========================================================")

    config = load_config()
    title_sub = config.get("game_window", {}).get("title_substring", "MagicChess")
    loop_interval = config.get("delays", {}).get("loop_interval_sec", 1.2)
    
    kb = KnowledgeBase()
    parser = ScreenParser()
    hero_det = HeroDetector()
    ui_det = DynamicUIDetector()
    brain = LLMBrain(config, kb)
    executor = ActionExecutor(action_delay_ms=config.get("delays", {}).get("action_delay_ms", 180))
    win_mgr = GameWindowManager(title_sub)
    cap = ScreenCapture(monitor_idx=1)

    print(f"[STATUS] Provider: {brain.provider.upper()} | Model: {brain.model}")
    print("[WAITING] Menunggu jendela game Magic Chess aktif...")

    while not win_mgr.find_game_hwnd():
        time.sleep(1.0)
        print(".", end="", flush=True)

    print("\n[GAME DETECTED] Game MCGG ditemukan! Membawa ke layer depan...")
    win_mgr.focus_game_window()

    last_acted_round = ""
    last_acted_phase = ""

    print("\n[BOT ACTIVE] Agent memindai visual layar secara real-time...\n")

    try:
        while True:
            frame = cap.capture_frame()
            status = parser.extract_game_status(frame)
            current_round = status["round"]
            timer = status["timer_seconds"]
            gold = status["gold"]
            level = status["level"]
            special_phase = status["special_phase"]

            # -------------------------------------------------------------
            # SKENARIO 1: FATE BOX (Pemilihan Hadiah Putaran)
            # -------------------------------------------------------------
            if special_phase == "FATE_BOX" and last_acted_phase != f"FATE_{current_round}":
                print(f"\n[EVENT FATE BOX] Memilih hadiah di lingkaran carousel...")
                win_mgr.focus_game_window()
                executor.pick_fatebox_reward(1)
                last_acted_phase = f"FATE_{current_round}"
                time.sleep(2.0)
                continue

            # -------------------------------------------------------------
            # SKENARIO 2: GO GO CARD (Double Click Kartu Kekuatan)
            # -------------------------------------------------------------
            if special_phase == "GOGO_CARD" and last_acted_phase != f"GOGO_{current_round}":
                print(f"\n[EVENT GO GO CARD] Memindai letak kartu kekuatan di layar...")
                win_mgr.focus_game_window()
                cards = ui_det.detect_clickable_gogo_cards(frame)
                card_choice = 1
                if cards and cards[0]["center"][0] > 960:
                    card_choice = 2

                print(f"[ACTION] Memilih Kartu Go Go Slot {card_choice} via Double-Click...")
                executor.pick_gogo_card(card_choice)
                last_acted_phase = f"GOGO_{current_round}"
                time.sleep(1.5)
                continue

            # -------------------------------------------------------------
            # SKENARIO 3: DROP ITEM (Pilihan Item Creep & Pasang ke Hero)
            # -------------------------------------------------------------
            if special_phase == "ITEM_SELECTION" and last_acted_phase != f"ITEM_{current_round}":
                print(f"\n[EVENT DROP ITEM] Mengambil item drop dari ronde creep...")
                win_mgr.focus_game_window()
                executor.pick_item_option(1)
                last_acted_phase = f"ITEM_{current_round}"
                time.sleep(1.0)
                
                print("[EQUIP] Memasang item ke Hero di Papan Catur...")
                executor.equip_item_to_hero(hero_target_idx=1)
                continue

            # -------------------------------------------------------------
            # SKENARIO 4: FASE PERSIAPAN PERTANDINGAN
            # -------------------------------------------------------------
            is_prep_phase = ("-" in current_round) and timer > 2

            if is_prep_phase and current_round != last_acted_round:
                print(f"\n=======================================================")
                print(f"[FASE AKTIF] Ronde: {current_round} | Timer: {timer}s | Saldo: {gold}G | Lv: {level}")
                print(f"=======================================================")

                win_mgr.focus_game_window()

                # Pindai hero yang secara NYATA terdeteksi oleh Computer Vision di bench
                occupied_bench = hero_det.scan_occupied_bench_slots(frame)
                if occupied_bench:
                    print(f"[VISION BENCH] Terdeteksi {len(occupied_bench)} hero nyata di bench: {[s[0] for s in occupied_bench]}")
                    executor.close_shop()
                    time.sleep(0.2)

                    # Penempatan terdistribusi pada grid catur 3x7 yang telah terkalibrasi visual
                    target_coords = [
                        BoardCoords.CHESSBOARD_GRID[(3, 4)],  # Center Back
                        BoardCoords.CHESSBOARD_GRID[(3, 3)],  # Mid-Left Back
                        BoardCoords.CHESSBOARD_GRID[(3, 5)],  # Mid-Right Back
                        BoardCoords.CHESSBOARD_GRID[(3, 2)],  # Far-Left Back
                        BoardCoords.CHESSBOARD_GRID[(3, 6)],  # Far-Right Back
                        BoardCoords.CHESSBOARD_GRID[(2, 4)],  # Center Mid
                        BoardCoords.CHESSBOARD_GRID[(2, 3)],  # Mid-Left Mid
                        BoardCoords.CHESSBOARD_GRID[(2, 5)],  # Mid-Right Mid
                    ]
                    
                    # Kapasitas maksimal pion di papan dibatasi oleh Level pemain
                    max_deploy = min(len(occupied_bench), level)
                    for i in range(max_deploy):
                        slot_num, cx, cy = occupied_bench[i]
                        target_xy = target_coords[i % len(target_coords)]
                        print(f"[LIVE DEPLOY] Menarik Hero Slot {slot_num} dari ({cx}, {cy}) ke Board ({target_xy[0]}, {target_xy[1]})...")
                        executor.drag_hero_to_board(cx, cy, target_xy[0], target_xy[1], label=f"Deploy Hero Slot {slot_num}")
                        time.sleep(0.15)

                # Ekstraksi Toko & Keputusan LLM
                raw_shop = parser.extract_shop_cards(frame)
                shop_slots = []
                for s in raw_shop:
                    matched = kb.match_hero(s["raw_text"])
                    hero_name = matched.get("Nama Hero", s["raw_text"].strip())
                    cost = int(float(matched.get("Harga Gold", 1))) if matched else 1
                    shop_slots.append(ShopSlot(
                        slot=s["slot"],
                        hero_name=hero_name,
                        cost=cost,
                        is_empty=s["is_empty"]
                    ))

                game_state = GameState(
                    round=current_round,
                    timer_seconds=timer,
                    gold=gold,
                    level=level,
                    shop=shop_slots,
                    current_phase="PREPARATION"
                )

                print("[THINKING] Menghubungi LLM Brain untuk strategi...")
                decision: TurnDecision = brain.decide_turn(game_state)
                print(f"[DECISION] Strategi: {decision.strategic_plan}")

                for act in decision.actions:
                    executor.execute_command(act)

                last_acted_round = current_round
                print(f"[DONE] Ronde {current_round} selesai dieksekusi. Menunggu babak selanjutnya...")

            time.sleep(loop_interval)

    except KeyboardInterrupt:
        print("\n[STOP] Bot dihentikan oleh pengguna.")

if __name__ == "__main__":
    run_live_bot()
