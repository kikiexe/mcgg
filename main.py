"""
MCGG Autonomous Agent Entry Point
"""
import os
import sys
import json
import time
import cv2
import mss
import numpy as np

from src.perception.screen_parser import ScreenParser
from src.decision.models import GameState, ShopSlot, TurnDecision
from src.decision.kb_loader import KnowledgeBase
from src.decision.llm_router import LLMBrain
from src.action.executor import ActionExecutor
from src.action.window_manager import GameWindowManager

def load_config() -> dict:
    config_path = r"C:\Projects\mcgg\config.json"
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)

def run_dry_test():
    """Runs a complete test cycle on sample screenshot."""
    print("==================================================")
    print("MEMULAI DRY-RUN TEST: MCGG AUTONOMOUS AGENT")
    print("==================================================")
    
    config = load_config()
    kb = KnowledgeBase()
    parser = ScreenParser()
    brain = LLMBrain(config, kb)
    win_mgr = GameWindowManager(config.get("game_window", {}).get("title_substring", "MagicChess"))

    # Auto Focus MCGG window if running
    if win_mgr.find_game_hwnd():
        print("[WINDOW] Game MCGG terdeteksi! Membawa jendela ke paling depan...")
        win_mgr.focus_game_window()
    else:
        print("[WINDOW INFO] Game MCGG belum dibuka. Menjalankan simulasi via gambar...")

    # 1. Perception Step (Load test image)
    test_img_path = r"C:\Projects\mcgg\asset\beli-hero.png"
    frame = cv2.imread(test_img_path)
    assert frame is not None, "Gagal memuat aset beli-hero.png"

    status = parser.extract_game_status(frame)
    raw_shop = parser.extract_shop_cards(frame)

    # 2. State Construction
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
        round=status["round"],
        timer_seconds=status["timer_seconds"],
        gold=status["gold"],
        level=status["level"],
        shop=shop_slots,
        current_phase="PREPARATION"
    )

    print(f"[PERCEPTION] GameState berhasil dibuat:")
    print(f"  Babak: {game_state.round} | Saldo: {game_state.gold}G | Level: {game_state.level}")
    print("  Toko Hero:")
    for card in game_state.shop:
        print(f"    Slot {card.slot}: {card.hero_name} ({card.cost} Gold)")

    # 3. Decision Step
    print("\n[DECISION] Mengirim status ke LLM Brain...")
    decision: TurnDecision = brain.decide_turn(game_state)
    print(f"[DECISION] Rencana Strategis: {decision.strategic_plan}")
    print("[DECISION] Aksi yang diputuskan:")
    for i, act in enumerate(decision.actions, 1):
        print(f"  {i}. {act.action} (slot={act.slot}) -> {act.reasoning}")

    print("\nDRY-RUN SELESAI: Pipeline dari Image -> OCR -> GameState -> LLM Brain -> Action berhasil terhubung!")

if __name__ == "__main__":
    run_dry_test()
