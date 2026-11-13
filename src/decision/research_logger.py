"""
Research Logger Module for MCGG Multi-Agent Esports Benchmark
Records turn-by-turn game states, decision origins, latency, and actions to JSONL
Satisfies PRD Section 5 Observability requirements
"""
import os
import json
import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from src.decision.models import GameState, TurnDecision

class ResearchLogger:
    def __init__(self, config_path: Optional[str] = None):
        root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        if config_path is None:
            config_path = os.path.join(root_dir, "config.json")
            
        self.enabled = True
        self.log_dir = os.path.join(root_dir, "logs")
        self.agent_id = "agent-01"
        self.agent_name = "MCGG-Esports-Agent"
        
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    self.agent_id = cfg.get("agent_id", self.agent_id)
                    self.agent_name = cfg.get("agent_name", self.agent_name)
                    log_cfg = cfg.get("logging", {})
                    self.enabled = log_cfg.get("save_match_history", True)
                    rel_dir = log_cfg.get("log_dir", "logs")
                    self.log_dir = os.path.join(root_dir, rel_dir)
            except Exception as e:
                print(f"[LOGGER WARNING] Gagal membaca config.json: {e}")
                
        os.makedirs(self.log_dir, exist_ok=True)
        session_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        self.log_file = os.path.join(self.log_dir, f"match_{self.agent_id}_{session_id}.jsonl")

    def log_turn(
        self,
        state: GameState,
        decision: TurnDecision,
        executed_actions: List[Dict[str, Any]],
        execution_latency_ms: float
    ):
        if not self.enabled:
            return

        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "round": state.round,
            "timer_seconds": state.timer_seconds,
            "policy_source": decision.policy_source,
            "llm_latency_ms": round(decision.latency_ms, 2),
            "execution_latency_ms": round(execution_latency_ms, 2),
            "observed_state": {
                "gold": state.gold,
                "level": state.level,
                "commander_hp": state.commander_hp,
                "board_deployed_count": state.board_deployed_count,
                "bench_occupied_slots": state.bench,
                "shop_cards": [s.model_dump() for s in state.shop],
                "current_phase": state.current_phase
            },
            "decision": {
                "strategic_plan": decision.strategic_plan,
                "planned_actions": [a.model_dump() for a in decision.actions]
            },
            "actions_executed": executed_actions
        }

        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as err:
            print(f"[LOGGER ERROR] Gagal menulis log turn ke {self.log_file}: {err}")

    def log_match_summary(self, final_placement: int, total_rounds: int, notes: str = ""):
        if not self.enabled:
            return

        summary = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent_id": self.agent_id,
            "event": "MATCH_SUMMARY",
            "final_placement": final_placement,
            "total_rounds": total_rounds,
            "notes": notes
        }

        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(summary, ensure_ascii=False) + "\n")
        except Exception as err:
            print(f"[LOGGER ERROR] Gagal menulis match summary: {err}")
