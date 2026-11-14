"""
MCGG Autonomous Agent - Live Production Loop with Clean Architecture
Decoupled Frame Processor, DirectInput Executor, and PRD Section 5 Research Logger
"""
import os
import sys
import json
import time
import traceback
import cv2
import numpy as np
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple

from src.perception.screen_capture import ScreenCapture
from src.perception.screen_parser import ScreenParser
from src.perception.hero_detector import HeroDetector
from src.perception.ui_detector import DynamicUIDetector
from src.decision.models import GameState, ShopSlot, TurnDecision, ActionCommand, GoGoCardDecision
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

@dataclass
class BotContext:
    player_name: str = "veteran"
    last_acted_round: str = ""
    last_acted_phase: str = ""
    board_deployed_count: int = 0
    owned_heroes: List[str] = field(default_factory=list)
    last_known_hp: Optional[int] = None
    consecutive_errors: int = 0
    max_consecutive_errors: int = 5

@dataclass
class BotDependencies:
    parser: ScreenParser
    hero_det: HeroDetector
    ui_det: DynamicUIDetector
    brain: LLMBrain
    executor: ActionExecutor
    logger: ResearchLogger
    cap: Optional[ScreenCapture] = None

def process_frame(
    frame: np.ndarray,
    ctx: BotContext,
    deps: BotDependencies,
    secondary_frame: Optional[np.ndarray] = None
) -> Dict[str, Any]:
    """
    Core Frame Processing Engine:
    Evaluates current screen frame, identifies game phase, and executes corresponding actions.
    Separated from hardware loops for complete unit & smoke testability.
    """
    status = deps.parser.extract_game_status(frame, player_name=ctx.player_name)
    current_round = status["round"]
    timer = status["timer_seconds"]
    gold = status["gold"]
    level = status["level"]
    special_phase = status["special_phase"]
    is_combat = status.get("is_combat", False)

    # Perbarui HP jika pembacaan OCR berhasil
    detected_hp = status.get("commander_hp")
    if detected_hp is not None and 1 <= detected_hp <= 100:
        ctx.last_known_hp = detected_hp

    # -----------------------------------------------------------------
    # SKENARIO 1: FATE BOX (Draft Hadiah Carousel)
    # -----------------------------------------------------------------
    if special_phase == "FATE_BOX" and ctx.last_acted_phase != f"FATE_{current_round}":
        print(f"\n[EVENT FATE BOX] Memilih hadiah di lingkaran carousel...")
        deps.executor.pick_fatebox_reward(1)
        ctx.last_acted_phase = f"FATE_{current_round}"
        ctx.consecutive_errors = 0
        return {"event": "FATE_BOX", "status": "HANDLED"}

    # -----------------------------------------------------------------
    # SKENARIO 2: GO GO CARD (Pemilihan Kartu Kekuatan Berbasis AI)
    # -----------------------------------------------------------------
    if special_phase == "GOGO_CARD" and ctx.last_acted_phase != f"GOGO_{current_round}":
        print(f"\n[EVENT GO GO CARD] Memindai kartu kekuatan di layar...")
        t_gogo = time.perf_counter()
        cards = deps.ui_det.detect_gogo_cards(frame)

        card_state = GameState(
            round=current_round,
            timer_seconds=timer,
            gold=gold,
            level=level,
            commander_hp=ctx.last_known_hp,
            hp_observed=(detected_hp is not None),
            board_deployed_count=ctx.board_deployed_count,
            owned_heroes=list(ctx.owned_heroes),
            current_phase="GOGO_CARD"
        )
        decision: GoGoCardDecision = deps.brain.decide_gogo_card(cards, card_state)
        
        # Gunakan koordinat pusat deteksi OCR nyata
        chosen_card = next((c for c in cards if c.get("slot") == decision.slot), None)
        custom_coords = chosen_card.get("center") if chosen_card else None

        print(f"[ACTION] Memilih Go Go Card Slot {decision.slot} di {custom_coords} -> {decision.reasoning}")
        deps.executor.pick_gogo_card(decision.slot, custom_coords=custom_coords)

        latency_ms = (time.perf_counter() - t_gogo) * 1000.0
        deps.logger.log_gogo_card_decision(
            round_str=current_round,
            cards_offered=cards,
            decision=decision,
            execution_latency_ms=latency_ms
        )

        ctx.last_acted_phase = f"GOGO_{current_round}"
        ctx.consecutive_errors = 0
        return {"event": "GOGO_CARD", "status": "HANDLED", "slot": decision.slot}

    # -----------------------------------------------------------------
    # SKENARIO 3: DROP ITEM (Pilihan Item Creep & Pasang ke Hero)
    # -----------------------------------------------------------------
    if special_phase == "ITEM_SELECTION" and ctx.last_acted_phase != f"ITEM_{current_round}":
        print(f"\n[EVENT DROP ITEM] Mengambil item creep...")
        deps.executor.pick_item_option(1)
        deps.executor.equip_item_to_hero(item_bag_idx=1, hero_target_idx=1)
        ctx.last_acted_phase = f"ITEM_{current_round}"
        ctx.consecutive_errors = 0
        return {"event": "ITEM_SELECTION", "status": "HANDLED"}

    # -----------------------------------------------------------------
    # SKENARIO 4: FASE PERSIAPAN PERTANDINGAN
    # -----------------------------------------------------------------
    is_prep_phase = (current_round != "UNKNOWN") and ("-" in current_round) and (timer > 2) and (not is_combat)

    if is_prep_phase and current_round != ctx.last_acted_round:
        # ATUR SEGERA di awal giliran untuk mencegah eksekusi dobel jika muncul error mid-turn
        ctx.last_acted_round = current_round
        turn_start_time = time.perf_counter()

        hp_display = f"{ctx.last_known_hp} HP" if ctx.last_known_hp is not None else "Unknown HP"
        print(f"\n=======================================================")
        print(f"[FASE PERSIAPAN] Ronde: {current_round} | Timer: {timer}s | Saldo: {gold}G | Lv: {level} | {hp_display}")
        print(f"=======================================================")

        # 1. Ekstraksi Kartu Toko
        raw_shop = deps.parser.extract_shop_cards(frame)
        shop_slots = []
        for s in raw_shop:
            matched = deps.brain.kb.match_hero(s["raw_text"])
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

        initial_occupied_bench = deps.hero_det.scan_occupied_bench_slots(frame)
        bench_indices = [s[0] for s in initial_occupied_bench]

        game_state = GameState(
            round=current_round,
            timer_seconds=timer,
            gold=gold,
            level=level,
            commander_hp=ctx.last_known_hp,
            hp_observed=(detected_hp is not None),
            board_deployed_count=ctx.board_deployed_count,
            bench=bench_indices,
            owned_heroes=list(ctx.owned_heroes),
            shop=shop_slots,
            current_phase="PREPARATION"
        )

        print(f"[THINKING] Menghubungi Brain ({deps.brain.provider.upper()}) untuk keputusan belanja...")
        decision: TurnDecision = deps.brain.decide_turn(game_state)
        print(f"[DECISION] [{decision.policy_source.upper()}] {decision.strategic_plan}")

        # 2. Eksekusi Aksi Belanja TERLEBIH DAHULU selagi toko terbuka
        executed_actions: List[Dict[str, Any]] = []
        for act in decision.actions:
            if act.action == "BUY_HERO" and act.slot:
                deps.executor.execute_command(act)
                bought_hero = next((s.hero_name for s in shop_slots if s.slot == act.slot), f"Slot_{act.slot}")
                if bought_hero != "KOSONG":
                    ctx.owned_heroes.append(bought_hero)
                executed_actions.append(act.model_dump())
                time.sleep(0.18)
            elif act.action == "LEVEL_UP":
                deps.executor.execute_command(act)
                if gold >= 4:
                    level += 1
                executed_actions.append(act.model_dump())
                time.sleep(0.18)
            elif act.action == "REROLL":
                deps.executor.execute_command(act)
                executed_actions.append(act.model_dump())
                time.sleep(0.18)

        # 3. Tutup Toko dengan klik netral
        deps.executor.close_shop()
        executed_actions.append({
            "action": "CLOSE_SHOP",
            "slot": None,
            "reasoning": "Menutup toko sebelum inspeksi papan dan deploy hero"
        })
        time.sleep(0.25)

        # 4. Ambil frame segar setelah toko tertutup untuk memastikan keakuratan bench dan HP
        frame_board = secondary_frame if secondary_frame is not None else (
            deps.cap.capture_frame() if deps.cap else frame
        )
        current_occupied_bench = deps.hero_det.scan_occupied_bench_slots(frame_board)
        board_hp = deps.parser.parse_player_hp(frame_board, player_name=ctx.player_name)
        if board_hp is not None and 1 <= board_hp <= 100:
            ctx.last_known_hp = board_hp

        # 5. Pemasangan (Deploy) Hero dari Bench ke Papan Catur sesuai kapasitas Level
        heroes_needed = max(0, level - ctx.board_deployed_count)
        if heroes_needed > 0 and current_occupied_bench:
            print(f"[BOARD DEPLOY] Kapasitas level: {level}, terpasang: {ctx.board_deployed_count}, butuh: {heroes_needed} hero.")
            
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
                target_idx = (ctx.board_deployed_count + i) % len(target_coords)
                target_xy = target_coords[target_idx]
                
                print(f"[LIVE DEPLOY] Menarik Hero Slot {slot_num} dari ({cx}, {cy}) ke Board ({target_xy[0]}, {target_xy[1]})...")
                deps.executor.drag_hero_to_board(cx, cy, target_xy[0], target_xy[1], label=f"Deploy Slot {slot_num}")
                
                executed_actions.append({
                    "action": "DEPLOY",
                    "slot": slot_num,
                    "reasoning": f"Deploy hero slot {slot_num} ke grid catur {target_xy}"
                })
                time.sleep(0.2)

            ctx.board_deployed_count += deploy_count

        # 6. Rekonsiliasi Hasil Tindakan dengan Observasi Pasca-Belanja
        post_status = deps.parser.extract_game_status(frame_board, player_name=ctx.player_name)
        reconciliation = {
            "pre_gold": gold,
            "post_gold": post_status["gold"],
            "gold_spent": max(0, gold - post_status["gold"]),
            "verified_level": post_status["level"],
            "verified_hp": board_hp
        }

        # 7. Catat log pertandingan turn-by-turn ke Research Logger (PRD Bagian 5)
        turn_latency_ms = (time.perf_counter() - turn_start_time) * 1000.0
        game_state.commander_hp = ctx.last_known_hp
        game_state.hp_observed = (board_hp is not None)
        game_state.board_deployed_count = ctx.board_deployed_count
        game_state.owned_heroes = list(ctx.owned_heroes)

        deps.logger.log_turn(
            state=game_state,
            decision=decision,
            executed_actions=executed_actions,
            execution_latency_ms=turn_latency_ms,
            reconciliation=reconciliation
        )

        ctx.consecutive_errors = 0
        print(f"[DONE] Ronde {current_round} selesai dieksekusi ({turn_latency_ms:.1f}ms). Menunggu babak berikutnya...\n")
        return {"event": "PREPARATION", "status": "HANDLED", "round": current_round}

    return {"event": "IDLE", "status": "WAITING"}

def run_live_bot():
    print("==========================================================")
    print("MCGG AUTONOMOUS AGENT - FULL DYNAMIC VISION CONTROLLER")
    print("==========================================================")

    config = load_config()
    title_sub = config.get("game_window", {}).get("title_substring", "MagicChess")
    loop_interval = config.get("delays", {}).get("loop_interval_sec", 1.2)
    player_name = config.get("player_name", "veteran")

    kb = KnowledgeBase()
    parser = ScreenParser()
    hero_det = HeroDetector()
    ui_det = DynamicUIDetector()
    brain = LLMBrain(config, kb)
    logger = ResearchLogger()
    executor = ActionExecutor(action_delay_ms=config.get("delays", {}).get("action_delay_ms", 180))
    win_mgr = GameWindowManager(title_sub)
    cap = ScreenCapture(monitor_idx=1)

    ctx = BotContext(player_name=player_name)
    deps = BotDependencies(
        parser=parser,
        hero_det=hero_det,
        ui_det=ui_det,
        brain=brain,
        executor=executor,
        logger=logger,
        cap=cap
    )

    print(f"[STATUS] Provider: {brain.provider.upper()} | Model: {brain.model} | Player: {player_name}")
    print("[WAITING] Menunggu jendela game Magic Chess aktif...")

    while not win_mgr.find_game_hwnd():
        time.sleep(1.0)
        print(".", end="", flush=True)

    print("\n[GAME DETECTED] Game MCGG ditemukan! Membawa ke layer depan...")
    win_mgr.focus_game_window()

    print("\n[BOT ACTIVE] Agent memindai visual layar secara real-time...\n")

    try:
        while True:
            try:
                frame = cap.capture_frame()
                process_frame(frame, ctx, deps)
            except Exception as loop_err:
                ctx.consecutive_errors += 1
                tb_str = traceback.format_exc()
                print(f"[RUNTIME WARNING] Error beruntun ke-{ctx.consecutive_errors}: {loop_err}")
                logger.log_error(ctx.last_acted_round, str(loop_err), tb_str)

                if ctx.consecutive_errors >= ctx.max_consecutive_errors:
                    raise RuntimeError(
                        f"[FATAL] Bot dihentikan: Mencapai batas maksimal {ctx.max_consecutive_errors} error beruntun."
                    )

            time.sleep(loop_interval)

    except KeyboardInterrupt:
        print("\n[STOP] Bot dihentikan oleh pengguna.")

if __name__ == "__main__":
    run_live_bot()
