import os
import cv2
import pytest
from unittest.mock import MagicMock
from live_bot import BotContext, BotDependencies, process_frame
from src.perception.screen_parser import ScreenParser
from src.perception.hero_detector import HeroDetector
from src.perception.ui_detector import DynamicUIDetector
from src.decision.kb_loader import KnowledgeBase
from src.decision.llm_router import LLMBrain
from src.decision.research_logger import ResearchLogger

ASSET_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "asset"))

@pytest.fixture
def mock_executor():
    executor = MagicMock()
    executor.executed_calls = []
    
    def log_call(method_name):
        def handler(*args, **kwargs):
            executor.executed_calls.append((method_name, args, kwargs))
        return handler

    for method in [
        "click_point", "drag_hero_to_board", "buy_hero_slot",
        "close_shop", "open_shop", "pick_fatebox_reward",
        "pick_gogo_card", "pick_item_option", "equip_item_to_hero",
        "reroll_shop", "level_up", "execute_command"
    ]:
        setattr(executor, method, MagicMock(side_effect=log_call(method)))
        
    return executor

@pytest.fixture
def bot_deps(mock_executor, tmp_path):
    parser = ScreenParser()
    hero_det = HeroDetector()
    ui_det = DynamicUIDetector()
    kb = KnowledgeBase()
    brain = LLMBrain(config={"llm": {"provider": "gemini", "model": "gemini-3.5-flash-lite"}}, kb=kb)
    brain.api_key = None  # Ensure deterministic offline tests without external network latency
    
    custom_config = tmp_path / "config.json"
    custom_config.write_text('{"logging": {"save_match_history": true, "log_dir": "logs"}}', encoding="utf-8")
    logger = ResearchLogger(config_path=str(custom_config))
    
    return BotDependencies(
        parser=parser,
        hero_det=hero_det,
        ui_det=ui_det,
        brain=brain,
        executor=mock_executor,
        logger=logger,
        cap=None
    )

def test_process_frame_fatebox_real_handler(bot_deps, mock_executor):
    img = cv2.imread(os.path.join(ASSET_DIR, "fase-fatebox.png"))
    ctx = BotContext(player_name="veteran")

    res = process_frame(img, ctx, bot_deps)
    assert res["event"] == "FATE_BOX"
    assert res["status"] == "HANDLED"

    calls = [c[0] for c in mock_executor.executed_calls]
    assert "pick_fatebox_reward" in calls

def test_process_frame_gogo_card_real_handler(bot_deps, mock_executor):
    img = cv2.imread(os.path.join(ASSET_DIR, "memilih-gogocard.png"))
    ctx = BotContext(player_name="veteran")

    res = process_frame(img, ctx, bot_deps)
    assert res["event"] == "GOGO_CARD"
    assert res["status"] == "HANDLED"
    assert res["slot"] in [1, 2]

    # Pastikan executor dipanggil dengan slot yang diputuskan
    calls = [c for c in mock_executor.executed_calls if c[0] == "pick_gogo_card"]
    assert len(calls) == 1
    slot_called = calls[0][1][0]
    assert slot_called == res["slot"]

def test_process_frame_prep_phase_full_pipeline(bot_deps, mock_executor):
    prep_frame = cv2.imread(os.path.join(ASSET_DIR, "beli-hero.png"))
    board_frame = cv2.imread(os.path.join(ASSET_DIR, "chessboard.png"))
    ctx = BotContext(player_name="veteran")

    res = process_frame(prep_frame, ctx, bot_deps, secondary_frame=board_frame)
    assert res["event"] == "PREPARATION"
    assert res["status"] == "HANDLED"
    assert ctx.last_acted_round != ""

    calls = [c[0] for c in mock_executor.executed_calls]
    # Pastikan tutup toko terpanggil
    assert "close_shop" in calls

def test_process_frame_prevents_duplicate_turn_on_repeat(bot_deps, mock_executor):
    prep_frame = cv2.imread(os.path.join(ASSET_DIR, "beli-hero.png"))
    ctx = BotContext(player_name="veteran")

    # Putaran pertama dijalankan
    res1 = process_frame(prep_frame, ctx, bot_deps)
    assert res1["event"] == "PREPARATION"
    first_call_count = len(mock_executor.executed_calls)

    # Putaran kedua pada frame yang sama: wajib diabaikan karena last_acted_round sudah sama
    res2 = process_frame(prep_frame, ctx, bot_deps)
    assert res2["event"] == "IDLE"
    assert len(mock_executor.executed_calls) == first_call_count
