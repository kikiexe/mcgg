"""
Decision Core: Multi-Provider LLM Brain Adapter with Robust Schema Parsing
"""
import os
import json
import re
import time
from typing import Dict, Any, Optional, List
from dotenv import load_dotenv
import litellm

# Portabilitas multi-provider: hapus otomatis parameter yang tidak didukung provider tertentu
litellm.drop_params = True

from src.decision.models import GameState, TurnDecision, ActionCommand, GoGoCardDecision
from src.decision.kb_loader import KnowledgeBase

# Resolusi path .env relatif otomatis agar portabel di semua laptop
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
load_dotenv(dotenv_path=os.path.join(ROOT_DIR, ".env"), override=True)

class LLMBrain:
    def __init__(self, config: Dict[str, Any], kb: Optional[KnowledgeBase] = None):
        self.config = config
        self.kb = kb or KnowledgeBase()
        
        self.provider = os.getenv("AI_PROVIDER", config.get("provider", "gemini")).lower()
        self.model = os.getenv("AI_MODEL", config.get("model", "gemini/gemini-3.5-flash-lite"))
        self.api_base = os.getenv("AI_API_BASE") or config.get("api_base")
        self.timeout_sec = config.get("delays", {}).get("llm_timeout_sec", 15)
        self.api_key = self._resolve_api_key()

    def _resolve_api_key(self) -> Optional[str]:
        if self.provider == "deepseek":
            return os.getenv("DEEPSEEK_API_KEY")
        elif self.provider == "openai":
            return os.getenv("OPENAI_API_KEY")
        elif self.provider in ("gemini", "google"):
            return os.getenv("GEMINI_API_KEY")
        elif self.provider == "anthropic":
            return os.getenv("ANTHROPIC_API_KEY")
        elif self.provider == "groq":
            return os.getenv("GROQ_API_KEY")
        elif self.provider == "mistral":
            return os.getenv("MISTRAL_API_KEY")
        return os.getenv("AI_API_KEY")

    def build_system_prompt(self) -> str:
        kb_context = self.kb.get_summary_prompt_context()
        return (
            "Anda adalah AI Grandmaster Esports untuk Magic Chess: Go Go (MCGG) Patch 7.2.\n"
            "Tujuan Anda adalah memenangkan pertandingan (Placement 1) dengan strategi ekonomi disiplin dan pembentukan sinergi kuat.\n\n"
            f"{kb_context}\n\n"
            "=== ATURAN STRATEGI ===\n"
            "1. Jika saldo Gold >= 20, pertahankan batas bunga maksimal (+4 Gold).\n"
            "2. Beli hero yang saling mengaktifkan sinergi atau bisa naik bintang 2.\n"
            "3. Format respon WAJIB berupa objek JSON murni (bukan list/array):\n"
            "{\n"
            '  "strategic_plan": "Penjelasan ringkas strategi",\n'
            '  "actions": [\n'
            '    {"action": "BUY_HERO", "slot": 1, "reasoning": "Membeli hero untuk sinergi"},\n'
            '    {"action": "CLOSE_SHOP", "slot": null, "reasoning": "Menutup shop dengan tombol spasi"},\n'
            '    {"action": "END_TURN", "slot": null, "reasoning": "Selesai fase belanja"}\n'
            "  ]\n"
            "}\n"
        )

    def decide_turn(self, state: GameState) -> TurnDecision:
        t0 = time.perf_counter()
        norm_round = state.round.replace("I-", "1-").strip()

        # ATURAN KHUSUS RONDE 1-1: Belanja hero pembuka (jika gold cukup) lalu siapkan papan
        if norm_round == "1-1":
            actions = []
            if state.gold >= 1 and state.shop:
                for slot in state.shop:
                    if not slot.is_empty and slot.cost <= state.gold:
                        actions.append(ActionCommand(
                            action="BUY_HERO",
                            slot=slot.slot,
                            reasoning=f"Membeli hero pembuka {slot.hero_name} ({slot.cost}G)"
                        ))
                        break
            actions.append(ActionCommand(action="CLOSE_SHOP", slot=None, reasoning="Tutup shop agar formasi terlihat jelas"))
            actions.append(ActionCommand(action="END_TURN", slot=None, reasoning="Selesai belanja ronde 1-1, lanjut ke deploy otomatis"))

            latency_ms = (time.perf_counter() - t0) * 1000.0
            return TurnDecision(
                strategic_plan="Ronde 1-1: Beli hero pembuka lalu siapkan deploy otomatis ke papan catur.",
                policy_source="fast_rule",
                latency_ms=latency_ms,
                actions=actions
            )

        # ATURAN KHUSUS RONDE 1-2: Level Up ke Level 4 untuk membuka slot hero ke-4
        if norm_round == "1-2" and state.gold >= 4 and state.level == 3:
            latency_ms = (time.perf_counter() - t0) * 1000.0
            return TurnDecision(
                strategic_plan="Ronde 1-2: Naikkan Level ke 4 (-4G) untuk menambah kapasitas papan catur menjadi 4 hero.",
                policy_source="fast_rule",
                latency_ms=latency_ms,
                actions=[
                    ActionCommand(action="LEVEL_UP", slot=None, reasoning="Menaikkan level ke Level 4 agar kapasitas hero menjadi 4"),
                    ActionCommand(action="CLOSE_SHOP", slot=None, reasoning="Tutup shop agar formasi terlihat rapi"),
                    ActionCommand(action="END_TURN", slot=None, reasoning="Formasi ronde 1-2 siap")
                ]
            )

        system_prompt = self.build_system_prompt()
        user_content = (
            f"STATUS PERTANDINGAN:\n"
            f"- Ronde: {state.round} | Sisa Waktu: {state.timer_seconds}s\n"
            f"- Saldo Gold: {state.gold}G | Level: {state.level} (Kapasitas Board: {state.level} hero)\n"
            f"- HP Commander: {state.commander_hp} | Hero di Papan: {state.board_deployed_count}\n"
            f"- Slot Bench Terisi: {state.bench}\n"
            f"- Hero Dimiliki: {state.owned_heroes}\n"
            f"- Pilihan Kartu Toko: {[s.model_dump() for s in state.shop]}\n\n"
            f"Tentukan keputusan aksi belanja terbaik dalam format JSON."
        )

        if not self.api_key or self.api_key.strip() == "":
            dec = self._offline_heuristic_policy(state)
            dec.latency_ms = (time.perf_counter() - t0) * 1000.0
            return dec

        try:
            kwargs = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                "api_key": self.api_key,
                "timeout": self.timeout_sec,
                "response_format": {"type": "json_object"}
            }
            if self.api_base:
                kwargs["api_base"] = self.api_base

            response = litellm.completion(**kwargs)
            raw_text = response.choices[0].message.content

            # Ekstrak JSON
            json_match = re.search(r'(\{.*\})', raw_text, re.DOTALL)
            parsed_json = json.loads(json_match.group(1) if json_match else raw_text)

            # Jika model mengembalikan array actions langsung tanpa strategic_plan
            if isinstance(parsed_json, list):
                parsed_json = {"strategic_plan": "Strategi Penyesuaian Tim", "actions": parsed_json}

            # Lengkapi reasoning jika model lupa menyertakannya
            if "strategic_plan" not in parsed_json:
                parsed_json["strategic_plan"] = "Mengejar kombo sinergi dan bunga"
            parsed_json["policy_source"] = "llm"
            for act in parsed_json.get("actions", []):
                if "reasoning" not in act:
                    act["reasoning"] = "Aksi adaptasi otomatis dari LLM"

            latency_ms = (time.perf_counter() - t0) * 1000.0
            parsed_json["latency_ms"] = latency_ms
            return TurnDecision.model_validate(parsed_json)

        except Exception as e:
            print(f"[LLM Warning] Parsing LLM gagal ({e}), beralih ke rule-based fallback.")
            dec = self._offline_heuristic_policy(state)
            dec.latency_ms = (time.perf_counter() - t0) * 1000.0
            return dec

    def _offline_heuristic_policy(self, state: GameState) -> TurnDecision:
        actions = []
        plan = "Strategi Heuristik (Fallback): Membeli hero terjangkau dan menjaga bunga."

        current_gold = state.gold
        for slot in state.shop:
            if not slot.is_empty and current_gold >= slot.cost:
                actions.append({
                    "action": "BUY_HERO",
                    "slot": slot.slot,
                    "reasoning": f"Membeli {slot.hero_name} (Cost: {slot.cost}G)."
                })
                current_gold -= slot.cost
                break

        actions.append({"action": "CLOSE_SHOP", "slot": None, "reasoning": "Menutup shop via klik netral"})
        actions.append({"action": "END_TURN", "slot": None, "reasoning": "Selesai fase belanja."})
        return TurnDecision(strategic_plan=plan, policy_source="offline_heuristic", actions=actions)

    def decide_gogo_card(self, cards: List[Dict[str, Any]], state: GameState) -> GoGoCardDecision:
        """
        Memilih kartu Go Go Card terbaik (Slot 1 atau Slot 2) berdasarkan sinergi tim
        menggunakan format terstruktur JSON.
        """
        t0 = time.perf_counter()
        if not cards:
            return GoGoCardDecision(
                slot=1,
                reasoning="Tidak ada kartu terdeteksi, memilih slot default 1",
                policy_source="fast_rule",
                latency_ms=(time.perf_counter() - t0) * 1000.0
            )

        if not self.api_key or self.api_key.strip() == "":
            return GoGoCardDecision(
                slot=cards[0].get("slot", 1),
                reasoning="Offline fallback: memilih kartu pertama",
                policy_source="offline_heuristic",
                latency_ms=(time.perf_counter() - t0) * 1000.0
            )

        cards_desc = "\n".join([f"- Slot {c.get('slot', i+1)}: {c.get('title', '')}" for i, c in enumerate(cards)])
        prompt = (
            "Anda adalah AI Grandmaster Magic Chess: Go Go (MCGG) Patch 7.2.\n"
            f"Komposisi hero saat ini: {state.owned_heroes}\n"
            f"Level: {state.level} | Saldo: {state.gold}G | HP: {state.commander_hp if state.commander_hp is not None else 'Unknown'}\n\n"
            f"Pilihan Go Go Card:\n{cards_desc}\n\n"
            "Tentukan pilihan kartu terbaik yang paling mendukung sinergi atau ekonomi tim.\n"
            "Format respon WAJIB JSON murni:\n"
            '{"slot": 1, "reasoning": "Alasan strategis memilih kartu ini"}'
        )

        try:
            kwargs = {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "api_key": self.api_key,
                "timeout": min(self.timeout_sec, 8),
                "response_format": {"type": "json_object"}
            }
            if self.api_base:
                kwargs["api_base"] = self.api_base

            res = litellm.completion(**kwargs)
            raw_text = res.choices[0].message.content.strip()
            json_match = re.search(r'(\{.*\})', raw_text, re.DOTALL)
            parsed = json.loads(json_match.group(1) if json_match else raw_text)

            chosen_slot = int(parsed.get("slot", 1))
            if chosen_slot not in [1, 2]:
                chosen_slot = 1
            reasoning = str(parsed.get("reasoning", "Dipilih berdasarkan sinergi tim"))
            latency_ms = (time.perf_counter() - t0) * 1000.0
            return GoGoCardDecision(
                slot=chosen_slot,
                reasoning=reasoning,
                policy_source="llm",
                latency_ms=latency_ms
            )
        except Exception as e:
            print(f"[LLM Warning] Gagal memilih Go Go Card via LLM ({e}), beralih ke fallback.")
            return GoGoCardDecision(
                slot=cards[0].get("slot", 1),
                reasoning=f"Fallback karena error LLM: {e}",
                policy_source="offline_heuristic",
                latency_ms=(time.perf_counter() - t0) * 1000.0
            )
