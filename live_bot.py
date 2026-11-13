"""
MCGG Autonomous Agent - Live Production Loop with Dynamic Vision & Single Flow Action Pipeline
Integrated with Computer Vision, Win32 DirectInput, and PRD Section 5 Research Logger
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
from src.decision.research_logger import ResearchLogger
from src.action.executor import ActionExecutor
from src.action.window_manager import GameWindowManager
from src.constants.coordinates import BoardCoords

ROOT_DIR = os.path.abspath(os.path.dirname(__file__))

def load_config() -> dict:
    config_path = os.path.join(ROOT_DIR, "config.json")
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
    logger = ResearchLogger()
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
    board_deployed_count = 0

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
            is_combat = status.get("is_combat", False)

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
                card_boxes = ui_det.detect_gogo_cards(frame)
                if card_boxes:
                    print(f"[UI DETECTOR] Terdeteksi {len(card_boxes)} Go Go Card via Contours.")
                    executor.pick_gogo_card(1)
                else:
                    print("[FALLBACK] Memilih Go Go Card Slot 1 (Koordinat Default)...")
                    executor.pick_gogo_card(1)
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
                executor.equip_item_to_hero(item_bag_idx=1, hero_target_idx=1)
                continue

            # -------------------------------------------------------------
            # SKENARIO 4: FASE PERSIAPAN PERTANDINGAN
            # -------------------------------------------------------------
            # Syarat: Label ronde valid, ada tanda "-", timer aktif, dan bukan combat aktif
            is_prep_phase = (current_round != "UNKNOWN") and ("-" in current_round) and (timer > 2) and (not is_combat)

            if is_prep_phase and current_round != last_acted_round:
                turn_start_time = time.perf_counter()
                print(f"\n=======================================================")
                print(f"[FASE PERSIAPAN] Ronde: {current_round} | Timer: {timer}s | Saldo: {gold}G | Lv: {level}")
                print(f"=======================================================")

                win_mgr.focus_game_window()

                # 1. Ekstraksi Toko & Bench saat toko terbuka
                raw_shop = parser.extract_shop_cards(frame)
                shop_slots = []
                for s in raw_shop:
                    matched = kb.match_hero(s["raw_text"])
                    if matched:
                        hero_name = matched.get("Nama Hero")
                        cost = int(float(matched.get("Harga Gold", 1)))
                        is_empty = s["is_empty"]
                    else:
                        hero_name = s["raw_text"].strip() if s["raw_text"].strip() else "KOSONG"
                        cost = 99
                        is_empty = True

                    shop_slots.append(ShopSlot(
                        slot=s["slot"],
                        hero_name=hero_name,
                        cost=cost,
                        is_empty=is_empty
                    ))

                # Pindai slot bench yang terisi hero
                initial_occupied_bench = hero_det.scan_occupied_bench_slots(frame)
                bench_indices = [s[0] for s in initial_occupied_bench]

                game_state = GameState(
                    round=current_round,
                    timer_seconds=timer,
                    gold=gold,
                    level=level,
                    commander_hp=100,
                    board_deployed_count=board_deployed_count,
                    bench=bench_indices,
                    shop=shop_slots,
                    current_phase="PREPARATION"
                )

                print(f"[THINKING] Menghubungi Brain ({brain.provider.upper()}) untuk keputusan belanja...")
                decision: TurnDecision = brain.decide_turn(game_state)
                print(f"[DECISION] [{decision.policy_source.upper()}] {decision.strategic_plan}")

                # 2. Eksekusi Aksi Belanja TERLEBIH DAHULU selagi toko terbuka
                executed_actions: List[Dict[str, Any]] = []
                for act in decision.actions:
                    if act.action in ("BUY_HERO", "LEVEL_UP", "REROLL"):
                        executor.execute_command(act)
                        executed_actions.append(act.model_dump())
                        time.sleep(0.18)

                # 3. Tutup Toko dengan aman (idempotent klik netral)
                executor.close_shop()
                executed_actions.append({
                    "action": "CLOSE_SHOP",
                    "slot": None,
                    "reasoning": "Menutup toko sebelum inspeksi papan dan deploy hero"
                })
                time.sleep(0.25)

                # 4. Ambil FRAME BARU setelah toko tertutup untuk memastikan keakuratan bench
                frame_board = cap.capture_frame()
                current_occupied_bench = hero_det.scan_occupied_bench_slots(frame_board)

                # 5. Pemasangan (Deploy) Hero dari Bench ke Papan Catur sesuai kapasitas Level
                heroes_needed = max(0, level - board_deployed_count)
                if heroes_needed > 0 and current_occupied_bench:
                    print(f"[BOARD DEPLOY] Kapasitas level: {level}, terpasang: {board_deployed_count}, butuh: {heroes_needed} hero.")
                    
                    target_coords = [
                        BoardCoords.CHESSBOARD_GRID[(3, 4)],  # Baris 3 Tengah
                        BoardCoords.CHESSBOARD_GRID[(3, 3)],  # Baris 3 Tengah-Kiri
                        BoardCoords.CHESSBOARD_GRID[(3, 5)],  # Baris 3 Tengah-Kanan
                        BoardCoords.CHESSBOARD_GRID[(3, 2)],  # Baris 3 Kiri Luar
                        BoardCoords.CHESSBOARD_GRID[(3, 6)],  # Baris 3 Kanan Luar
                        BoardCoords.CHESSBOARD_GRID[(2, 4)],  # Baris 2 Tengah
                        BoardCoords.CHESSBOARD_GRID[(2, 3)],  # Baris 2 Kiri
                        BoardCoords.CHESSBOARD_GRID[(2, 5)],  # Baris 2 Kanan
                    ]

                    deploy_count = min(len(current_occupied_bench), heroes_needed)
                    for i in range(deploy_count):
                        slot_num, cx, cy = current_occupied_bench[i]
                        target_idx = (board_deployed_count + i) % len(target_coords)
                        target_xy = target_coords[target_idx]
                        
                        print(f"[LIVE DEPLOY] Menarik Hero Slot {slot_num} dari ({cx}, {cy}) ke Board ({target_xy[0]}, {target_xy[1]})...")
                        executor.drag_hero_to_board(cx, cy, target_xy[0], target_xy[1], label=f"Deploy Slot {slot_num}")
                        
                        executed_actions.append({
                            "action": "DEPLOY",
                            "slot": slot_num,
                            "reasoning": f"Deploy hero slot {slot_num} ke grid catur {target_xy}"
                        })
                        time.sleep(0.2)

                    board_deployed_count += deploy_count

                # 6. Catat log pertandingan turn-by-turn ke Research Logger (PRD Bagian 5)
                turn_latency_ms = (time.perf_counter() - turn_start_time) * 1000.0
                logger.log_turn(
                    state=game_state,
                    decision=decision,
                    executed_actions=executed_actions,
                    execution_latency_ms=turn_latency_ms
                )

                last_acted_round = current_round
                print(f"[DONE] Ronde {current_round} selesai dieksekusi ({turn_latency_ms:.1f}ms). Menunggu babak berikutnya...\n")

            time.sleep(loop_interval)

    except KeyboardInterrupt:
        print("\n[STOP] Bot dihentikan oleh pengguna.")

if __name__ == "__main__":
    run_live_bot()
