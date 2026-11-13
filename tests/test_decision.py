import pytest
from src.decision.kb_loader import KnowledgeBase
from src.decision.llm_router import LLMBrain
from src.decision.models import GameState, ShopSlot

def test_kb_loader_contains_all_58_heroes():
    kb = KnowledgeBase()
    assert len(kb.heroes) == 58, f"Expected 58 heroes in KB, got {len(kb.heroes)}"
    assert len(kb.synergies) == 21, f"Expected 21 synergies in KB, got {len(kb.synergies)}"

    summary = kb.get_summary_prompt_context()
    assert "=== DAFTAR LENGKAP 58 HERO PATCH 7.2 ===" in summary
    assert "=== DAFTAR 21 SINERGI PATCH 7.2 ===" in summary
    assert "Miya" in summary
    assert "Wanwan" in summary

def test_fast_rule_round_1_1_no_duplicate_deploy():
    kb = KnowledgeBase()
    dummy_config = {"llm": {"provider": "gemini", "model": "gemini-3.5-flash-lite"}}
    brain = LLMBrain(config=dummy_config, kb=kb)

    state = GameState(
        round="1-1",
        timer_seconds=25,
        gold=1,
        level=3,
        commander_hp=100,
        board_deployed_count=0,
        bench=[1],
        shop=[ShopSlot(slot=1, hero_name="Miya", cost=1, is_empty=False)],
        current_phase="PREPARATION"
    )

    decision = brain.decide_turn(state)
    assert decision.policy_source == "fast_rule"
    assert decision.latency_ms > 0

    # Pastikan tidak ada aksi DEPLOY hardcoded ganda yang memicu slot bench kosong
    action_types = [a.action for a in decision.actions]
    assert "DEPLOY" not in action_types
    assert "CLOSE_SHOP" in action_types
    assert "END_TURN" in action_types

def test_offline_heuristic_fallback_labels_source():
    kb = KnowledgeBase()
    dummy_config = {"llm": {"provider": "gemini", "model": "gemini-3.5-flash-lite"}}
    brain = LLMBrain(config=dummy_config, kb=kb)
    brain.api_key = ""  # Paksa fallback

    state = GameState(
        round="2-1",
        timer_seconds=20,
        gold=10,
        level=4,
        commander_hp=95,
        board_deployed_count=3,
        bench=[1],
        shop=[ShopSlot(slot=1, hero_name="Layla", cost=1, is_empty=False)],
        current_phase="PREPARATION"
    )

    decision = brain.decide_turn(state)
    assert decision.policy_source == "offline_heuristic"
    assert decision.latency_ms > 0
    assert len(decision.actions) > 0
