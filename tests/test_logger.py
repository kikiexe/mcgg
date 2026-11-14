import os
import json
import pytest
from src.decision.research_logger import ResearchLogger
from src.decision.models import GameState, TurnDecision, ActionCommand, ShopSlot

def test_research_logger_writes_valid_jsonl(tmp_path):
    # Buat custom config dalam temporary path
    custom_config = tmp_path / "config.json"
    custom_config.write_text(json.dumps({
        "agent_id": "test-agent-01",
        "agent_name": "Test-Agent",
        "logging": {
            "save_match_history": True,
            "log_dir": str(tmp_path / "logs")
        }
    }), encoding="utf-8")

    logger = ResearchLogger(config_path=str(custom_config))
    assert os.path.exists(logger.log_dir)

    state = GameState(
        round="1-1",
        timer_seconds=25,
        gold=0,
        level=3,
        commander_hp=100,
        board_deployed_count=1,
        bench=[1],
        shop=[ShopSlot(slot=1, hero_name="Miya", cost=1, is_empty=False)],
        current_phase="PREPARATION"
    )

    decision = TurnDecision(
        strategic_plan="Beli Miya untuk sinergi Marksman",
        policy_source="fast_rule",
        latency_ms=12.5,
        actions=[ActionCommand(action="BUY_HERO", slot=1, reasoning="Membeli Miya")]
    )

    executed_actions = [{"action": "BUY_HERO", "slot": 1, "status": "SUCCESS"}]
    execution_latency_ms = 45.2

    logger.log_turn(
        state=state,
        decision=decision,
        executed_actions=executed_actions,
        execution_latency_ms=execution_latency_ms
    )

    assert os.path.exists(logger.log_file)
    with open(logger.log_file, "r", encoding="utf-8") as f:
        lines = f.readlines()

    assert len(lines) == 1
    record = json.loads(lines[0])

    assert record["agent_id"] == "test-agent-01"
    assert record["round"] == "1-1"
    assert record["policy_source"] == "fast_rule"
    assert record["llm_latency_ms"] == 12.5
    assert record["execution_latency_ms"] == 45.2
    assert record["observed_state"]["gold"] == 0
    assert record["observed_state"]["bench_occupied_slots"] == [1]
    assert record["observed_state"]["commander_hp"] == 100
    assert record["bot_belief"]["board_deployed_count"] == 1
    assert "owned_heroes" in record["bot_belief"]
    assert len(record["actions_executed"]) == 1
