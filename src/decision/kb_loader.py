"""
Knowledge Base Loader for Patch 7.2 Data
"""
import os
import json
from typing import Dict, Any, List

class KnowledgeBase:
    def __init__(self, base_dir: str = r"C:\Projects\mcgg\knowledge_base"):
        self.base_dir = base_dir
        self.heroes: List[Dict[str, Any]] = self._load_json("heroes.json").get("heroes", [])
        self.synergies: List[Dict[str, Any]] = self._load_json("synergies.json").get("synergies", [])
        self.items: List[Dict[str, Any]] = self._load_json("items.json").get("items", [])
        self.gogo_cards: List[Dict[str, Any]] = self._load_json("gogo_cards.json").get("gogo_cards", [])
        self.rules: Dict[str, Any] = self._load_json("game_rules.json").get("game_rules", {})

        # Fast lookup mapping: Hero Name -> Data Hero
        self.hero_map: Dict[str, Dict[str, Any]] = {}
        for h in self.heroes:
            name = h.get("Nama Hero", "").strip()
            if name:
                self.hero_map[name.lower()] = h

    def _load_json(self, filename: str) -> Dict[str, Any]:
        path = os.path.join(self.base_dir, filename)
        if not os.path.exists(path):
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def match_hero(self, raw_name: str) -> Dict[str, Any]:
        """Match OCR raw string to closest official hero name."""
        clean = raw_name.lower().strip()
        # Direct lookup
        for name, data in self.hero_map.items():
            if name in clean:
                return data
        return {}

    def get_summary_prompt_context(self) -> str:
        """Returns a concise token-efficient summary of core Patch 7.2 rules for LLM prompt."""
        return (
            "=== ATURAN EKONOMI MCGG PATCH 7.2 ===\n"
            "- Bunga Maksimal: +4 Gold jika saldo akhir ronde >= 20 Gold.\n"
            "- Bunga Tingkat 1: +2 Gold jika saldo akhir ronde 10 - 19 Gold.\n"
            "- Biaya Reroll Shop: 2 Gold | Biaya Beli EXP: 4 Gold (+4 EXP).\n"
            "- Jaga disiplin ekonomi: Hindari belanja berlebihan jika saldo turun di bawah 20 Gold, kecuali HP sekarat!\n\n"
            "=== DAFTAR HERO & SINERGI LENGKAP PATCH 7.2 ===\n"
            + ", ".join([f"{h.get('Nama Hero')} ({int(float(h.get('Harga Gold', 1)))}G - {h.get('Sinergi Lengkap')})" for h in self.heroes[:30]])
            + "\n...(dan hero lainnya)"
        )
