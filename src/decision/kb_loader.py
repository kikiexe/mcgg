"""
Knowledge Base Loader for Patch 7.2 Data
"""
import os
import json
from typing import Dict, Any, List

class KnowledgeBase:
    def __init__(self, base_dir: str = None):
        if base_dir is None:
            # Resolusi path relatif otomatis agar portabel di semua laptop
            root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            candidates = [
                os.path.join(root_dir, "data", "knowledge_base"),
                os.path.join(root_dir, "knowledge_base")
            ]
            self.base_dir = next((c for c in candidates if os.path.exists(c)), candidates[0])
        else:
            self.base_dir = base_dir

        self.heroes: List[Dict[str, Any]] = self._load_json("heroes.json").get("heroes", [])
        self.synergies: List[Dict[str, Any]] = self._load_json("synergies.json").get("synergies", [])
        self.items: List[Dict[str, Any]] = self._load_json("items.json").get("items", [])
        self.gogo_cards: List[Dict[str, Any]] = self._load_json("gogo_cards.json").get("gogo_cards", [])
        self.rules: Dict[str, Any] = self._load_json("game_rules.json").get("game_rules", {})

        if not self.heroes:
            raise FileNotFoundError(f"[CRITICAL] Knowledge Base kosong! Direktori '{self.base_dir}' tidak ditemukan atau tidak valid.")

        # Fast lookup mapping: Hero Name -> Data Hero
        self.hero_map: Dict[str, Dict[str, Any]] = {}
        for h in self.heroes:
            name = h.get("Nama Hero", "").strip()
            if name:
                self.hero_map[name.lower()] = h

    def _load_json(self, filename: str) -> Dict[str, Any]:
        path = os.path.join(self.base_dir, filename)
        if not os.path.exists(path):
            print(f"[WARN] File KB tidak ditemukan: {path}")
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
        synergies_summary = ", ".join([
            f"{s.get('Nama Sinergi')}" for s in self.synergies if s.get('Nama Sinergi')
        ])
        
        all_heroes_summary = "\n".join([
            f"- {h.get('Nama Hero')} ({int(float(h.get('Harga Gold', 1)))}G): {h.get('Sinergi Lengkap', '')}"
            for h in self.heroes if h.get('Nama Hero')
        ])

        return (
            "=== ATURAN EKONOMI MCGG PATCH 7.2 ===\n"
            "1. Pendapatan Dasar: +5G (Babak I-1 s/d II-6), +6G (Babak III), +7G (Babak IV+).\n"
            "2. Bunga Gold (Interest) di akhir ronde: +2G jika Gold >= 10, +4G (maksimal) jika Gold >= 20.\n"
            "3. Biaya: Reroll Toko = 2G | Beli EXP (Level Up) = 4G (+4 EXP).\n"
            "4. Strategi Tabungan: Capai 20G secepatnya untuk memaksimalkan bunga +4G tiap ronde (slow-roll di atas 20G).\n\n"
            f"=== DAFTAR 21 SINERGI PATCH 7.2 ===\n{synergies_summary}\n\n"
            f"=== DAFTAR LENGKAP 58 HERO PATCH 7.2 ===\n{all_heroes_summary}"
        )
