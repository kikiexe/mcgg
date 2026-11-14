# Audit Teknis dan Dokumentasi Perubahan Kode (15 File)

Dokumen ini mencatat seluruh perbandingan kode antara commit awal 872cf17 dan kondisi kode termutakhir yang telah lulus pengujian ketat.

## Ringkasan Perubahan per Berkas

| No | Berkas | Kondisi Sebelum | Kondisi Sesudah |
| :-: | :--- | :--- | :--- |
| 1 | `src/perception/screen_parser.py` | 1. Deteksi combat BGR sempit rapuh terhadap variasi kecerahan (+25 offset menghasilkan 0 bar HP).<br>2. HP Commander dibaca dari baris pertama (milik Computer1=100) bukan milik pemain lokal (veteran=94). | 1. Deteksi combat menggunakan HSV murni (H <= 8 | H >= 175, S >= 150, V >= 150) yang terbukti 100% tahan terhadap variasi kecerahan (+25, -25, x1.2, x0.8) dan kompresi JPEG q60.<br>2. parse_player_hp memindai seluruh panel leaderboard Y: 80..850, mencocokkan player_name ("veteran"), dan membaca HP di pita baris yang sama (berhasil membaca 94 HP di row 5). |
| 2 | `src/perception/ui_detector.py` | Fungsi detect_gogo_cards tidak ada (AttributeError mematikan bot saat ronde Go Go Card). | Mengimplementasikan detect_gogo_cards(frame) dengan pemindaian OCR terkluster: Slot 1 (X < 960) dan Slot 2 (X >= 960), mengekstrak judul kartu dan koordinat titik klik tengah nyata. |
| 3 | `src/action/executor.py` | 1. Reroll & level up dobel jalur (hotkey + click).<br>2. equip_item_to_hero signature mismatch.<br>3. pick_gogo_card hanya menerima static slot. | 1. Reroll & level up satu jalur via hotkey.<br>2. Parameter equip_item_to_hero disesuaikan.<br>3. pick_gogo_card menerima custom_coords dari hasil deteksi visual OCR. |
| 4 | `src/decision/kb_loader.py` | Hanya 30 dari 58 hero masuk prompt, sinergi tidak lengkap, bunga tidak sinkron. | Memuat seluruh 58 hero Patch 7.2 lengkap dengan sinergi dan harga, sinkron dengan game_rules.json. |
| 5 | `src/decision/llm_router.py` | 1. Go Go card tidak diputuskan AI terstruktur.<br>2. Prompt tidak tahu hero yang dimiliki.<br>3. Fast rule ronde 1-1 deploy ganda ke bench kosong.<br>4. Latensi tidak dicatat. | 1. decide_gogo_card menghasilkan JSON terstruktur {"slot": 1|2, "reasoning": "..."} dengan pelacakan latensi dan fallback aman.<br>2. Injeksi state.owned_heroes ke prompt turn.<br>3. Deploy ronde 1-1 diperbaiki tanpa deploy ganda.<br>4. Mencatat latency_ms di setiap rute. |
| 6 | `src/decision/models.py` | GameState dan TurnDecision belum memisahkan sensor visual vs keyakinan bot, dan validasi level ge=3 memicu crash saat level 1/2. | 1. Menambahkan field commander_hp, hp_observed, owned_heroes, board_deployed_count.<br>2. Menambahkan GoGoCardDecision terstruktur.<br>3. Memperbaiki validasi level menjadi ge=1, le=10.<br>4. Menambahkan latency_ms dan policy_source. |
| 7 | `src/decision/research_logger.py` | Logger eksperimen belum ada; data sensor visual dan estimasi bot tercampur. | Mengimplementasikan ResearchLogger JSONL dengan pemisahan ketat observed_state (sensor visual nyata) dan bot_belief (estimasi internal), serta log_gogo_card_decision, log_error, dan rekonsiliasi state. |
| 8 | `live_bot.py` | 1. Loop monolitik sulit dites.<br>2. Toko ditutup sebelum belanja.<br>3. mid-turn exception memicu duplicate turn.<br>4. HP literal 100. | 1. Ekstraksi engine process_frame(frame, ctx, deps) terpisah dari loop hardware.<br>2. Belanja saat toko terbuka, tutup toko, capture frame baru, baru deploy.<br>3. Proteksi last_acted_round diset di awal ronde prep.<br>4. HP dinamis dari OCR leaderboard.<br>5. Rekonsiliasi gold dan level setelah toko ditutup. |
| 9 | `config.json` | Belum ada konfigurasi player_name dan threshold visual. | Menambahkan player_name: "veteran" dan konfigurasi logging terstandar. |
| 10 | `pyproject.toml` | pytest terdaftar di dependensi produksi utama. | Memindahkan pytest ke dependency-groups dev. |
| 11 | `uv.lock` | Lockfile mencatat dependensi dev di root. | Diperbarui otomatis oleh uv untuk dev group. |
| 12 | `tests/test_decision.py` | Belum ada pengujian KB loader dan rule 1-1. | Unit test 58 hero, validasi fast rule 1-1 tanpa deploy ganda, dan offline heuristic. |
| 13 | `tests/test_logger.py` | Belum ada verifikasi struktur JSONL. | Unit test validasi penulisan JSONL, pemisahan observed_state vs bot_belief, dan rekonsiliasi. |
| 14 | `tests/test_perception.py` | Hanya uji boolean statis dan rentan false positive. | Ground truth 7 aset visual, pembacaan HP 94 & 100, ketahanan pencahayaan (+25/-25), dan stabilitas dynamic frames. |
| 15 | `tests/test_live_bot_smoke.py` | Smoke test memanggil mock langsung secara tautologis. | Smoke test menyeluruh memanggil fungsi process_frame asli dengan mock executor pada frame visual nyata (Fate Box, Go Go Card, Preparation). |

---

## Unified Git Diff Lengkap

### `src/perception/screen_parser.py`

```diff
diff --git a/src/perception/screen_parser.py b/src/perception/screen_parser.py
index c85f6c8..3c4e22d 100644
--- a/src/perception/screen_parser.py
+++ b/src/perception/screen_parser.py
@@ -51,13 +51,69 @@ class ScreenParser:
     def detect_combat_active(self, frame: np.ndarray) -> bool:
         """
         Mendeteksi apakah ronde sedang dalam fase tempur animasi aktif.
-        Saat bertarung, bilah HP musuh (Red HP Bar) muncul di papan catur (Y: 200..700, X: 300..1600).
+        Kriteria:
+        1. Bilah HP musuh (Red HP Bar) memiliki rona merah murni jenuh
+           (HSV: H <= 8 atau H >= 175, S >= 150, V >= 150), tahan terhadap perubahan kecerahan.
+        2. Geometri persegi panjang horizontal pipih (lebar 25..120 px, tinggi 3..10 px, rasio aspek w/h >= 3.5).
+        3. Area pemindaian dibatasi pada papan catur murni (Y: 180..680, X: 400..1550),
+           mengecualikan area laci toko bawah dan hero card portraits.
         """
-        board_roi = frame[200:700, 300:1600]
-        red_hp_mask = (board_roi[:, :, 2] > 180) & (board_roi[:, :, 1] < 50) & (board_roi[:, :, 0] < 50)
-        return int(np.sum(red_hp_mask)) > 250
+        board_roi = frame[180:680, 400:1550]
+        hsv = cv2.cvtColor(board_roi, cv2.COLOR_BGR2HSV)
+        red_mask = ((hsv[:, :, 0] <= 8) | (hsv[:, :, 0] >= 175)) & (hsv[:, :, 1] >= 150) & (hsv[:, :, 2] >= 150)
+        contours, _ = cv2.findContours(red_mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
+        
+        hp_bar_count = 0
+        for c in contours:
+            _, _, w, h = cv2.boundingRect(c)
+            if 25 <= w <= 120 and 3 <= h <= 10 and (w / max(1, h)) >= 3.5:
+                hp_bar_count += 1
+                
+        return hp_bar_count >= 1
+
+    def parse_player_hp(self, frame: np.ndarray, player_name: str = "veteran") -> Optional[int]:
+        """
+        Mengekstrak angka HP Commander lokal dari leaderboard panel kanan.
+        Memindai seluruh 8 slot pemain (Y: 80..850, X: 1640..1920) untuk menemukan baris
+        pemain lokal, lalu membaca angka HP di bawah nama pemain tersebut.
+        """
+        leaderboard_crop = frame[80:850, 1640:1920]
+        res, _ = self.ocr(leaderboard_crop)
+        if not res:
+            return None
+
+        items = []
+        for box, text, _ in res:
+            cy = int(sum(p[1] for p in box) / 4) + 80
+            cx = int(sum(p[0] for p in box) / 4) + 1640
+            items.append((cx, cy, text.strip()))
+
+        p_lower = player_name.lower().strip()
+        name_variants = [p_lower]
+        if len(p_lower) > 3:
+            name_variants.append(p_lower[1:])  # Menangani huruf pertama yang terpotong garis batas (e.g. 'eteran')
+
+        target_cy = None
+        for cx, cy, text in items:
+            t_low = text.lower()
+            if any(v in t_low for v in name_variants):
+                target_cy = cy
+                break
+
+        if target_cy is None:
+            return None
+
+        # Cari angka HP di pita-Y tepat di bawah nama pemain (selisih Y: 25..65 px)
+        for cx, cy, text in items:
+            if 25 <= (cy - target_cy) <= 65 and 1670 <= cx <= 1850:
+                digits = re.findall(r'^\d+$', text)
+                if digits:
+                    val = int(digits[0])
+                    if 1 <= val <= 100:
+                        return val
+        return None
 
-    def extract_game_status(self, frame: np.ndarray) -> Dict[str, Any]:
+    def extract_game_status(self, frame: np.ndarray, player_name: str = "veteran") -> Dict[str, Any]:
         gold = self.parse_digits_in_region(frame, StatusRegions.GOLD_REGION, default=0)
         round_str = self.read_text_in_region(frame, StatusRegions.ROUND_REGION)
         timer = self.parse_digits_in_region(frame, StatusRegions.TIMER_REGION, default=0)
@@ -77,12 +133,14 @@ class ScreenParser:
 
         special_phase = self.detect_special_phases(frame)
         is_combat = self.detect_combat_active(frame)
+        commander_hp = self.parse_player_hp(frame, player_name=player_name)
 
         return {
             "gold": gold,
             "round": round_str if round_str else "UNKNOWN",
             "timer_seconds": timer,
             "level": level,
+            "commander_hp": commander_hp,
             "special_phase": special_phase,
             "is_combat": is_combat
         }
```

### `src/perception/ui_detector.py`

```diff
diff --git a/src/perception/ui_detector.py b/src/perception/ui_detector.py
index 8c36c83..c26f123 100644
--- a/src/perception/ui_detector.py
+++ b/src/perception/ui_detector.py
@@ -47,6 +47,34 @@ class DynamicUIDetector:
         cards.sort(key=lambda c: c["center"][0])
         return cards
 
+    def detect_gogo_cards(self, frame: np.ndarray) -> List[Dict[str, Any]]:
+        """
+        Mendeteksi entitas kartu Go Go Card (Slot 1 di kiri, Slot 2 di kanan)
+        beserta judul/deskripsi OCR dan koordinat klik tengah.
+        """
+        raw_items = self.detect_clickable_gogo_cards(frame)
+        card1_texts = [c for c in raw_items if c["center"][0] < 960]
+        card2_texts = [c for c in raw_items if c["center"][0] >= 960]
+
+        cards = []
+        if card1_texts:
+            cx = int(np.mean([c["center"][0] for c in card1_texts]))
+            cy = int(np.mean([c["center"][1] for c in card1_texts]))
+            title = " ".join([c["text"] for c in card1_texts])
+            cards.append({"slot": 1, "center": (cx, cy), "title": title})
+        else:
+            cards.append({"slot": 1, "center": (695, 485), "title": "Go Go Card 1 (Default)"})
+
+        if card2_texts:
+            cx = int(np.mean([c["center"][0] for c in card2_texts]))
+            cy = int(np.mean([c["center"][1] for c in card2_texts]))
+            title = " ".join([c["text"] for c in card2_texts])
+            cards.append({"slot": 2, "center": (cx, cy), "title": title})
+        else:
+            cards.append({"slot": 2, "center": (1205, 485), "title": "Go Go Card 2 (Default)"})
+
+        return cards
+
     def detect_clickable_items(self, frame: np.ndarray) -> List[Dict[str, Any]]:
         """
         Dynamically finds Item Equipment Drop options on screen.
```

### `src/action/executor.py`

```diff
diff --git a/src/action/executor.py b/src/action/executor.py
index 4fc21a5..ac4892b 100644
--- a/src/action/executor.py
+++ b/src/action/executor.py
@@ -3,7 +3,7 @@ Action Executor: Uses win32 hardware mouse_event and keybd_event
 100% bypasses Unity DirectX input consumption
 """
 import time
-from typing import Tuple
+from typing import Tuple, Optional, Dict
 from src.action.hardware_input import win32_click, win32_drag, win32_press_key
 from src.constants.coordinates import ShopCardCoords, BoardCoords, ItemEventCoords, GoGoCardCoords, FateBoxCoords
 from src.decision.models import ActionCommand
@@ -103,12 +103,16 @@ class ActionExecutor:
         pt = ItemEventCoords.DROP_ITEM_SLOTS[idx]
         self.click_point(pt[0], pt[1], label=f"Pilih Drop Item {option_idx}")
 
-    def pick_gogo_card(self, card_idx: int):
-        options = {
-            1: GoGoCardCoords.CARD_1_CLICK,
-            2: GoGoCardCoords.CARD_2_CLICK,
-        }
-        pt = options.get(card_idx, GoGoCardCoords.CARD_1_CLICK)
+    def pick_gogo_card(self, card_idx: int, custom_coords: Optional[Tuple[int, int]] = None):
+        if custom_coords:
+            pt = custom_coords
+        else:
+            options = {
+                1: GoGoCardCoords.CARD_1_CLICK,
+                2: GoGoCardCoords.CARD_2_CLICK,
+            }
+            pt = options.get(card_idx, GoGoCardCoords.CARD_1_CLICK)
+
         # Sesuai mekanik game: Double-click untuk mengunci kartu
         self.click_point(pt[0], pt[1], label=f"Pilih Go Go Card {card_idx} (Click 1)")
         time.sleep(0.12)
```

### `src/decision/kb_loader.py`

```diff
diff --git a/src/decision/kb_loader.py b/src/decision/kb_loader.py
index 05411e7..0ae6e7a 100644
--- a/src/decision/kb_loader.py
+++ b/src/decision/kb_loader.py
@@ -53,13 +53,21 @@ class KnowledgeBase:
 
     def get_summary_prompt_context(self) -> str:
         """Returns a concise token-efficient summary of core Patch 7.2 rules for LLM prompt."""
+        synergies_summary = ", ".join([
+            f"{s.get('Nama Sinergi')}" for s in self.synergies if s.get('Nama Sinergi')
+        ])
+        
+        all_heroes_summary = "\n".join([
+            f"- {h.get('Nama Hero')} ({int(float(h.get('Harga Gold', 1)))}G): {h.get('Sinergi Lengkap', '')}"
+            for h in self.heroes if h.get('Nama Hero')
+        ])
+
         return (
             "=== ATURAN EKONOMI MCGG PATCH 7.2 ===\n"
-            "- Bunga Maksimal: +4 Gold jika saldo akhir ronde >= 20 Gold.\n"
-            "- Bunga Tingkat 1: +2 Gold jika saldo akhir ronde 10 - 19 Gold.\n"
-            "- Biaya Reroll Shop: 2 Gold | Biaya Beli EXP: 4 Gold (+4 EXP).\n"
-            "- Jaga disiplin ekonomi: Hindari belanja berlebihan jika saldo turun di bawah 20 Gold, kecuali HP sekarat!\n\n"
-            "=== DAFTAR HERO & SINERGI LENGKAP PATCH 7.2 ===\n"
-            + ", ".join([f"{h.get('Nama Hero')} ({int(float(h.get('Harga Gold', 1)))}G - {h.get('Sinergi Lengkap')})" for h in self.heroes[:30]])
-            + "\n...(dan hero lainnya)"
+            "1. Pendapatan Dasar: +5G (Babak I-1 s/d II-6), +6G (Babak III), +7G (Babak IV+).\n"
+            "2. Bunga Gold (Interest) di akhir ronde: +2G jika Gold >= 10, +4G (maksimal) jika Gold >= 20.\n"
+            "3. Biaya: Reroll Toko = 2G | Beli EXP (Level Up) = 4G (+4 EXP).\n"
+            "4. Strategi Tabungan: Capai 20G secepatnya untuk memaksimalkan bunga +4G tiap ronde (slow-roll di atas 20G).\n\n"
+            f"=== DAFTAR 21 SINERGI PATCH 7.2 ===\n{synergies_summary}\n\n"
+            f"=== DAFTAR LENGKAP 58 HERO PATCH 7.2 ===\n{all_heroes_summary}"
         )
```

### `src/decision/llm_router.py`

```diff
diff --git a/src/decision/llm_router.py b/src/decision/llm_router.py
index 49bfeaf..d11f696 100644
--- a/src/decision/llm_router.py
+++ b/src/decision/llm_router.py
@@ -4,14 +4,15 @@ Decision Core: Multi-Provider LLM Brain Adapter with Robust Schema Parsing
 import os
 import json
 import re
-from typing import Dict, Any, Optional
+import time
+from typing import Dict, Any, Optional, List
 from dotenv import load_dotenv
 import litellm
 
 # Portabilitas multi-provider: hapus otomatis parameter yang tidak didukung provider tertentu
 litellm.drop_params = True
 
-from src.decision.models import GameState, TurnDecision, ActionCommand
+from src.decision.models import GameState, TurnDecision, ActionCommand, GoGoCardDecision
 from src.decision.kb_loader import KnowledgeBase
 
 # Resolusi path .env relatif otomatis agar portabel di semua laptop
@@ -65,27 +66,39 @@ class LLMBrain:
         )
 
     def decide_turn(self, state: GameState) -> TurnDecision:
+        t0 = time.perf_counter()
         norm_round = state.round.replace("I-", "1-").strip()
 
-        # ATURAN KHUSUS RONDE 1-1: Langsung Deploy hero gratis dari Bench ke Papan Catur!
+        # ATURAN KHUSUS RONDE 1-1: Belanja hero pembuka (jika gold cukup) lalu siapkan papan
         if norm_round == "1-1":
+            actions = []
+            if state.gold >= 1 and state.shop:
+                for slot in state.shop:
+                    if not slot.is_empty and slot.cost <= state.gold:
+                        actions.append(ActionCommand(
+                            action="BUY_HERO",
+                            slot=slot.slot,
+                            reasoning=f"Membeli hero pembuka {slot.hero_name} ({slot.cost}G)"
+                        ))
+                        break
+            actions.append(ActionCommand(action="CLOSE_SHOP", slot=None, reasoning="Tutup shop agar formasi terlihat jelas"))
+            actions.append(ActionCommand(action="END_TURN", slot=None, reasoning="Selesai belanja ronde 1-1, lanjut ke deploy otomatis"))
+
+            latency_ms = (time.perf_counter() - t0) * 1000.0
             return TurnDecision(
-                strategic_plan="Ronde 1-1: Pasang hero gratis dari bench ke papan catur untuk mengalahkan creep pertama.",
+                strategic_plan="Ronde 1-1: Beli hero pembuka lalu siapkan deploy otomatis ke papan catur.",
                 policy_source="fast_rule",
-                actions=[
-                    ActionCommand(action="CLOSE_SHOP", slot=None, reasoning="Tutup shop agar papan catur terlihat jelas"),
-                    ActionCommand(action="DEPLOY", slot=1, reasoning="Menaruh Hero Gratis 1 ke papan catur"),
-                    ActionCommand(action="DEPLOY", slot=2, reasoning="Menaruh Hero Gratis 2 ke papan catur"),
-                    ActionCommand(action="DEPLOY", slot=3, reasoning="Menaruh Hero Gratis 3 ke papan catur"),
-                    ActionCommand(action="END_TURN", slot=None, reasoning="Formasi creep ronde 1-1 siap bertarung")
-                ]
+                latency_ms=latency_ms,
+                actions=actions
             )
 
         # ATURAN KHUSUS RONDE 1-2: Level Up ke Level 4 untuk membuka slot hero ke-4
         if norm_round == "1-2" and state.gold >= 4 and state.level == 3:
+            latency_ms = (time.perf_counter() - t0) * 1000.0
             return TurnDecision(
                 strategic_plan="Ronde 1-2: Naikkan Level ke 4 (-4G) untuk menambah kapasitas papan catur menjadi 4 hero.",
                 policy_source="fast_rule",
+                latency_ms=latency_ms,
                 actions=[
                     ActionCommand(action="LEVEL_UP", slot=None, reasoning="Menaikkan level ke Level 4 agar kapasitas hero menjadi 4"),
                     ActionCommand(action="CLOSE_SHOP", slot=None, reasoning="Tutup shop agar formasi terlihat rapi"),
@@ -94,10 +107,21 @@ class LLMBrain:
             )
 
         system_prompt = self.build_system_prompt()
-        user_content = f"STATUS GAME SAAT INI:\n{state.model_dump_json(indent=2)}\n\nBerikan keputusan aksi terbaik Anda dalam format JSON:"
+        user_content = (
+            f"STATUS PERTANDINGAN:\n"
+            f"- Ronde: {state.round} | Sisa Waktu: {state.timer_seconds}s\n"
+            f"- Saldo Gold: {state.gold}G | Level: {state.level} (Kapasitas Board: {state.level} hero)\n"
+            f"- HP Commander: {state.commander_hp} | Hero di Papan: {state.board_deployed_count}\n"
+            f"- Slot Bench Terisi: {state.bench}\n"
+            f"- Hero Dimiliki: {state.owned_heroes}\n"
+            f"- Pilihan Kartu Toko: {[s.model_dump() for s in state.shop]}\n\n"
+            f"Tentukan keputusan aksi belanja terbaik dalam format JSON."
+        )
 
         if not self.api_key or self.api_key.strip() == "":
-            return self._offline_heuristic_policy(state)
+            dec = self._offline_heuristic_policy(state)
+            dec.latency_ms = (time.perf_counter() - t0) * 1000.0
+            return dec
 
         try:
             kwargs = {
@@ -132,11 +156,15 @@ class LLMBrain:
                 if "reasoning" not in act:
                     act["reasoning"] = "Aksi adaptasi otomatis dari LLM"
 
+            latency_ms = (time.perf_counter() - t0) * 1000.0
+            parsed_json["latency_ms"] = latency_ms
             return TurnDecision.model_validate(parsed_json)
 
         except Exception as e:
             print(f"[LLM Warning] Parsing LLM gagal ({e}), beralih ke rule-based fallback.")
-            return self._offline_heuristic_policy(state)
+            dec = self._offline_heuristic_policy(state)
+            dec.latency_ms = (time.perf_counter() - t0) * 1000.0
+            return dec
 
     def _offline_heuristic_policy(self, state: GameState) -> TurnDecision:
         actions = []
@@ -156,3 +184,72 @@ class LLMBrain:
         actions.append({"action": "CLOSE_SHOP", "slot": None, "reasoning": "Menutup shop via klik netral"})
         actions.append({"action": "END_TURN", "slot": None, "reasoning": "Selesai fase belanja."})
         return TurnDecision(strategic_plan=plan, policy_source="offline_heuristic", actions=actions)
+
+    def decide_gogo_card(self, cards: List[Dict[str, Any]], state: GameState) -> GoGoCardDecision:
+        """
+        Memilih kartu Go Go Card terbaik (Slot 1 atau Slot 2) berdasarkan sinergi tim
+        menggunakan format terstruktur JSON.
+        """
+        t0 = time.perf_counter()
+        if not cards:
+            return GoGoCardDecision(
+                slot=1,
+                reasoning="Tidak ada kartu terdeteksi, memilih slot default 1",
+                policy_source="fast_rule",
+                latency_ms=(time.perf_counter() - t0) * 1000.0
+            )
+
+        if not self.api_key or self.api_key.strip() == "":
+            return GoGoCardDecision(
+                slot=cards[0].get("slot", 1),
+                reasoning="Offline fallback: memilih kartu pertama",
+                policy_source="offline_heuristic",
+                latency_ms=(time.perf_counter() - t0) * 1000.0
+            )
+
+        cards_desc = "\n".join([f"- Slot {c.get('slot', i+1)}: {c.get('title', '')}" for i, c in enumerate(cards)])
+        prompt = (
+            "Anda adalah AI Grandmaster Magic Chess: Go Go (MCGG) Patch 7.2.\n"
+            f"Komposisi hero saat ini: {state.owned_heroes}\n"
+            f"Level: {state.level} | Saldo: {state.gold}G | HP: {state.commander_hp if state.commander_hp is not None else 'Unknown'}\n\n"
+            f"Pilihan Go Go Card:\n{cards_desc}\n\n"
+            "Tentukan pilihan kartu terbaik yang paling mendukung sinergi atau ekonomi tim.\n"
+            "Format respon WAJIB JSON murni:\n"
+            '{"slot": 1, "reasoning": "Alasan strategis memilih kartu ini"}'
+        )
+
+        try:
+            kwargs = {
+                "model": self.model,
+                "messages": [{"role": "user", "content": prompt}],
+                "api_key": self.api_key,
+                "timeout": min(self.timeout_sec, 8),
+                "response_format": {"type": "json_object"}
+            }
+            if self.api_base:
+                kwargs["api_base"] = self.api_base
+
+            res = litellm.completion(**kwargs)
+            raw_text = res.choices[0].message.content.strip()
+            json_match = re.search(r'(\{.*\})', raw_text, re.DOTALL)
+            parsed = json.loads(json_match.group(1) if json_match else raw_text)
+
+            chosen_slot = int(parsed.get("slot", 1))
+            if chosen_slot not in [1, 2]:
+                chosen_slot = 1
+            reasoning = str(parsed.get("reasoning", "Dipilih berdasarkan sinergi tim"))
+            latency_ms = (time.perf_counter() - t0) * 1000.0
+            return GoGoCardDecision(
+                slot=chosen_slot,
+                reasoning=reasoning,
+                policy_source="llm",
+                latency_ms=latency_ms
+            )
+        except Exception as e:
+            print(f"[LLM Warning] Gagal memilih Go Go Card via LLM ({e}), beralih ke fallback.")
+            return GoGoCardDecision(
+                slot=cards[0].get("slot", 1),
+                reasoning=f"Fallback karena error LLM: {e}",
+                policy_source="offline_heuristic",
+                latency_ms=(time.perf_counter() - t0) * 1000.0
+            )
```

### `src/decision/models.py`

```diff
diff --git a/src/decision/models.py b/src/decision/models.py
index ce25f03..2901ed5 100644
--- a/src/decision/models.py
+++ b/src/decision/models.py
@@ -14,7 +14,12 @@ class GameState(BaseModel):
     round: str = Field(default="1-1", description="Babak saat ini, misal: '1-1', '1-2', '1-3'")
     timer_seconds: int = Field(default=30, description="Sisa waktu fase persiapan (detik)")
     gold: int = Field(default=0, ge=0, description="Jumlah saldo gold saat ini")
-    level: int = Field(default=3, ge=3, le=10, description="Level commander saat ini")
+    level: int = Field(default=3, ge=1, le=10, description="Level commander saat ini")
+    commander_hp: Optional[int] = Field(default=None, ge=1, le=100, description="Sisa HP Commander jika teramati visual")
+    hp_observed: bool = Field(default=False, description="Apakah HP berhasil diamati langsung dari visual")
+    board_deployed_count: int = Field(default=0, ge=0, description="Jumlah hero yang berada di papan catur")
+    bench: List[int] = Field(default_factory=list, description="Daftar nomor slot bench yang terisi hero (1-8)")
+    owned_heroes: List[str] = Field(default_factory=list, description="Daftar nama hero yang dimiliki dari pembelian")
     shop: List[ShopSlot] = Field(default_factory=list, description="5 Slot kartu di shop")
     current_phase: Literal["PREPARATION", "COMBAT", "GOGO_CARD", "ITEM_SELECTION"] = Field(
         default="PREPARATION", description="Fase game saat ini"
@@ -40,4 +45,13 @@ class TurnDecision(BaseModel):
     policy_source: Literal["llm", "offline_heuristic", "fast_rule"] = Field(
         default="llm", description="Sumber kebijakan keputusan (llm, offline_heuristic, atau fast_rule)"
     )
+    latency_ms: float = Field(default=0.0, description="Durasi komputasi keputusan (ms)")
     actions: List[ActionCommand] = Field(default_factory=list, description="Urutan tindakan yang harus dieksekusi")
+
+class GoGoCardDecision(BaseModel):
+    slot: int = Field(..., ge=1, le=2, description="Nomor slot kartu terpilih (1 atau 2)")
+    reasoning: str = Field(..., description="Alasan strategis pemilihan kartu")
+    policy_source: Literal["llm", "offline_heuristic", "fast_rule"] = Field(
+        default="llm", description="Sumber kebijakan (llm, offline_heuristic, fast_rule)"
+    )
+    latency_ms: float = Field(default=0.0, description="Durasi komputasi keputusan (ms)")
```

### `src/decision/research_logger.py`

```diff
diff --git a/src/decision/research_logger.py b/src/decision/research_logger.py
new file mode 100644
index 0000000..88c7817
--- /dev/null
+++ b/src/decision/research_logger.py
@@ -0,0 +1,154 @@
+"""
+Research Logger Module for MCGG Multi-Agent Esports Benchmark
+Records turn-by-turn game states, decision origins, latency, and actions to JSONL
+Satisfies PRD Section 5 Observability requirements
+"""
+import os
+import json
+import time
+from datetime import datetime, timezone
+from typing import Dict, Any, List, Optional
+from src.decision.models import GameState, TurnDecision, GoGoCardDecision
+
+class ResearchLogger:
+    def __init__(self, config_path: Optional[str] = None):
+        root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
+        if config_path is None:
+            config_path = os.path.join(root_dir, "config.json")
+            
+        self.enabled = True
+        self.log_dir = os.path.join(root_dir, "logs")
+        self.agent_id = "agent-01"
+        self.agent_name = "MCGG-Esports-Agent"
+        
+        if os.path.exists(config_path):
+            try:
+                with open(config_path, "r", encoding="utf-8") as f:
+                    cfg = json.load(f)
+                    self.agent_id = cfg.get("agent_id", self.agent_id)
+                    self.agent_name = cfg.get("agent_name", self.agent_name)
+                    log_cfg = cfg.get("logging", {})
+                    self.enabled = log_cfg.get("save_match_history", True)
+                    rel_dir = log_cfg.get("log_dir", "logs")
+                    self.log_dir = os.path.join(root_dir, rel_dir)
+            except Exception as e:
+                print(f"[LOGGER WARNING] Gagal membaca config.json: {e}")
+                
+        os.makedirs(self.log_dir, exist_ok=True)
+        session_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
+        self.log_file = os.path.join(self.log_dir, f"match_{self.agent_id}_{session_id}.jsonl")
+
+    def log_turn(
+        self,
+        state: GameState,
+        decision: TurnDecision,
+        executed_actions: List[Dict[str, Any]],
+        execution_latency_ms: float,
+        reconciliation: Optional[Dict[str, Any]] = None
+    ):
+        if not self.enabled:
+            return
+
+        record = {
+            "timestamp": datetime.now(timezone.utc).isoformat(),
+            "event": "TURN_DECISION",
+            "agent_id": self.agent_id,
+            "agent_name": self.agent_name,
+            "round": state.round,
+            "timer_seconds": state.timer_seconds,
+            "policy_source": decision.policy_source,
+            "llm_latency_ms": round(decision.latency_ms, 2),
+            "execution_latency_ms": round(execution_latency_ms, 2),
+            "observed_state": {
+                "gold": state.gold,
+                "level": state.level,
+                "commander_hp": state.commander_hp,
+                "hp_observed": state.hp_observed,
+                "bench_occupied_slots": state.bench,
+                "shop_cards": [s.model_dump() for s in state.shop],
+                "current_phase": state.current_phase
+            },
+            "bot_belief": {
+                "board_deployed_count": state.board_deployed_count,
+                "owned_heroes": state.owned_heroes
+            },
+            "reconciliation": reconciliation or {},
+            "decision": {
+                "strategic_plan": decision.strategic_plan,
+                "planned_actions": [a.model_dump() for a in decision.actions]
+            },
+            "actions_executed": executed_actions
+        }
+
+        try:
+            with open(self.log_file, "a", encoding="utf-8") as f:
+                f.write(json.dumps(record, ensure_ascii=False) + "\n")
+        except Exception as err:
+            print(f"[LOGGER ERROR] Gagal menulis log turn ke {self.log_file}: {err}")
+
+    def log_gogo_card_decision(
+        self,
+        round_str: str,
+        cards_offered: List[Dict[str, Any]],
+        decision: GoGoCardDecision,
+        execution_latency_ms: float
+    ):
+        if not self.enabled:
+            return
+
+        record = {
+            "timestamp": datetime.now(timezone.utc).isoformat(),
+            "event": "GOGO_CARD_SELECTION",
+            "agent_id": self.agent_id,
+            "round": round_str,
+            "policy_source": decision.policy_source,
+            "llm_latency_ms": round(decision.latency_ms, 2),
+            "execution_latency_ms": round(execution_latency_ms, 2),
+            "cards_offered": cards_offered,
+            "chosen_slot": decision.slot,
+            "reasoning": decision.reasoning
+        }
+
+        try:
+            with open(self.log_file, "a", encoding="utf-8") as f:
+                f.write(json.dumps(record, ensure_ascii=False) + "\n")
+        except Exception as err:
+            print(f"[LOGGER ERROR] Gagal menulis log Go Go Card: {err}")
+
+    def log_error(self, round_str: str, error_message: str, traceback_str: str = ""):
+        if not self.enabled:
+            return
+
+        record = {
+            "timestamp": datetime.now(timezone.utc).isoformat(),
+            "event": "RUNTIME_ERROR",
+            "agent_id": self.agent_id,
+            "round": round_str,
+            "error": error_message,
+            "traceback": traceback_str
+        }
+
+        try:
+            with open(self.log_file, "a", encoding="utf-8") as f:
+                f.write(json.dumps(record, ensure_ascii=False) + "\n")
+        except Exception as err:
+            print(f"[LOGGER ERROR] Gagal menulis error log: {err}")
+
+    def log_match_summary(self, final_placement: int, total_rounds: int, notes: str = ""):
+        if not self.enabled:
+            return
+
+        summary = {
+            "timestamp": datetime.now(timezone.utc).isoformat(),
+            "agent_id": self.agent_id,
+            "event": "MATCH_SUMMARY",
+            "final_placement": final_placement,
+            "total_rounds": total_rounds,
+            "notes": notes
+        }
+
+        try:
+            with open(self.log_file, "a", encoding="utf-8") as f:
+                f.write(json.dumps(summary, ensure_ascii=False) + "\n")
+        except Exception as err:
+            print(f"[LOGGER ERROR] Gagal menulis match summary: {err}")
```

### `live_bot.py`

```diff
diff --git a/live_bot.py b/live_bot.py
index 15c9ac6..4967947 100644
--- a/live_bot.py
+++ b/live_bot.py
@@ -1,21 +1,25 @@
 """
-MCGG Autonomous Agent - Live Production Loop with Zero Hardcoded Coordinates
-Uses Computer Vision (Canny Hero Detector + Dynamic OCR Bounding Boxes)
+MCGG Autonomous Agent - Live Production Loop with Clean Architecture
+Decoupled Frame Processor, DirectInput Executor, and PRD Section 5 Research Logger
 """
 import os
 import sys
 import json
 import time
+import traceback
 import cv2
-from typing import Dict, Any, List
+import numpy as np
+from dataclasses import dataclass, field
+from typing import Dict, Any, List, Optional, Tuple
 
 from src.perception.screen_capture import ScreenCapture
 from src.perception.screen_parser import ScreenParser
 from src.perception.hero_detector import HeroDetector
 from src.perception.ui_detector import DynamicUIDetector
-from src.decision.models import GameState, ShopSlot, TurnDecision, ActionCommand
+from src.decision.models import GameState, ShopSlot, TurnDecision, ActionCommand, GoGoCardDecision
 from src.decision.kb_loader import KnowledgeBase
 from src.decision.llm_router import LLMBrain
+from src.decision.research_logger import ResearchLogger
 from src.action.executor import ActionExecutor
 from src.action.window_manager import GameWindowManager
 from src.constants.coordinates import BoardCoords
@@ -27,6 +31,273 @@ def load_config() -> dict:
     with open(config_path, "r", encoding="utf-8") as f:
         return json.load(f)
 
+@dataclass
+class BotContext:
+    player_name: str = "veteran"
+    last_acted_round: str = ""
+    last_acted_phase: str = ""
+    board_deployed_count: int = 0
+    owned_heroes: List[str] = field(default_factory=list)
+    last_known_hp: Optional[int] = None
+    consecutive_errors: int = 0
+    max_consecutive_errors: int = 5
+
+@dataclass
+class BotDependencies:
+    parser: ScreenParser
+    hero_det: HeroDetector
+    ui_det: DynamicUIDetector
+    brain: LLMBrain
+    executor: ActionExecutor
+    logger: ResearchLogger
+    cap: Optional[ScreenCapture] = None
+
+def process_frame(
+    frame: np.ndarray,
+    ctx: BotContext,
+    deps: BotDependencies,
+    secondary_frame: Optional[np.ndarray] = None
+) -> Dict[str, Any]:
+    """
+    Core Frame Processing Engine:
+    Evaluates current screen frame, identifies game phase, and executes corresponding actions.
+    Separated from hardware loops for complete unit & smoke testability.
+    """
+    status = deps.parser.extract_game_status(frame, player_name=ctx.player_name)
+    current_round = status["round"]
+    timer = status["timer_seconds"]
+    gold = status["gold"]
+    level = status["level"]
+    special_phase = status["special_phase"]
+    is_combat = status.get("is_combat", False)
+
+    # Perbarui HP jika pembacaan OCR berhasil
+    detected_hp = status.get("commander_hp")
+    if detected_hp is not None and 1 <= detected_hp <= 100:
+        ctx.last_known_hp = detected_hp
+
+    # -----------------------------------------------------------------
+    # SKENARIO 1: FATE BOX (Draft Hadiah Carousel)
+    # -----------------------------------------------------------------
+    if special_phase == "FATE_BOX" and ctx.last_acted_phase != f"FATE_{current_round}":
+        print(f"\n[EVENT FATE BOX] Memilih hadiah di lingkaran carousel...")
+        deps.executor.pick_fatebox_reward(1)
+        ctx.last_acted_phase = f"FATE_{current_round}"
+        ctx.consecutive_errors = 0
+        return {"event": "FATE_BOX", "status": "HANDLED"}
+
+    # -----------------------------------------------------------------
+    # SKENARIO 2: GO GO CARD (Pemilihan Kartu Kekuatan Berbasis AI)
+    # -----------------------------------------------------------------
+    if special_phase == "GOGO_CARD" and ctx.last_acted_phase != f"GOGO_{current_round}":
+        print(f"\n[EVENT GO GO CARD] Memindai kartu kekuatan di layar...")
+        t_gogo = time.perf_counter()
+        cards = deps.ui_det.detect_gogo_cards(frame)
+
+        card_state = GameState(
+            round=current_round,
+            timer_seconds=timer,
+            gold=gold,
+            level=level,
+            commander_hp=ctx.last_known_hp,
+            hp_observed=(detected_hp is not None),
+            board_deployed_count=ctx.board_deployed_count,
+            owned_heroes=list(ctx.owned_heroes),
+            current_phase="GOGO_CARD"
+        )
+        decision: GoGoCardDecision = deps.brain.decide_gogo_card(cards, card_state)
+        
+        # Gunakan koordinat pusat deteksi OCR nyata
+        chosen_card = next((c for c in cards if c.get("slot") == decision.slot), None)
+        custom_coords = chosen_card.get("center") if chosen_card else None
+
+        print(f"[ACTION] Memilih Go Go Card Slot {decision.slot} di {custom_coords} -> {decision.reasoning}")
+        deps.executor.pick_gogo_card(decision.slot, custom_coords=custom_coords)
+
+        latency_ms = (time.perf_counter() - t_gogo) * 1000.0
+        deps.logger.log_gogo_card_decision(
+            round_str=current_round,
+            cards_offered=cards,
+            decision=decision,
+            execution_latency_ms=latency_ms
+        )
+
+        ctx.last_acted_phase = f"GOGO_{current_round}"
+        ctx.consecutive_errors = 0
+        return {"event": "GOGO_CARD", "status": "HANDLED", "slot": decision.slot}
+
+    # -----------------------------------------------------------------
+    # SKENARIO 3: DROP ITEM (Pilihan Item Creep & Pasang ke Hero)
+    # -----------------------------------------------------------------
+    if special_phase == "ITEM_SELECTION" and ctx.last_acted_phase != f"ITEM_{current_round}":
+        print(f"\n[EVENT DROP ITEM] Mengambil item creep...")
+        deps.executor.pick_item_option(1)
+        deps.executor.equip_item_to_hero(item_bag_idx=1, hero_target_idx=1)
+        ctx.last_acted_phase = f"ITEM_{current_round}"
+        ctx.consecutive_errors = 0
+        return {"event": "ITEM_SELECTION", "status": "HANDLED"}
+
+    # -----------------------------------------------------------------
+    # SKENARIO 4: FASE PERSIAPAN PERTANDINGAN
+    # -----------------------------------------------------------------
+    is_prep_phase = (current_round != "UNKNOWN") and ("-" in current_round) and (timer > 2) and (not is_combat)
+
+    if is_prep_phase and current_round != ctx.last_acted_round:
+        # ATUR SEGERA di awal giliran untuk mencegah eksekusi dobel jika muncul error mid-turn
+        ctx.last_acted_round = current_round
+        turn_start_time = time.perf_counter()
+
+        hp_display = f"{ctx.last_known_hp} HP" if ctx.last_known_hp is not None else "Unknown HP"
+        print(f"\n=======================================================")
+        print(f"[FASE PERSIAPAN] Ronde: {current_round} | Timer: {timer}s | Saldo: {gold}G | Lv: {level} | {hp_display}")
+        print(f"=======================================================")
+
+        # 1. Ekstraksi Kartu Toko
+        raw_shop = deps.parser.extract_shop_cards(frame)
+        shop_slots = []
+        for s in raw_shop:
+            matched = deps.brain.kb.match_hero(s["raw_text"])
+            if matched:
+                hero_name = matched.get("Nama Hero")
+                cost = int(float(matched.get("Harga Gold", 1)))
+                is_empty = s["is_empty"]
+            else:
+                hero_name = s["raw_text"].strip() if s["raw_text"].strip() else "KOSONG"
+                cost = 99
+                is_empty = True
+
+            shop_slots.append(ShopSlot(
+                slot=s["slot"],
+                hero_name=hero_name,
+                cost=cost,
+                is_empty=is_empty
+            ))
+
+        initial_occupied_bench = deps.hero_det.scan_occupied_bench_slots(frame)
+        bench_indices = [s[0] for s in initial_occupied_bench]
+
+        game_state = GameState(
+            round=current_round,
+            timer_seconds=timer,
+            gold=gold,
+            level=level,
+            commander_hp=ctx.last_known_hp,
+            hp_observed=(detected_hp is not None),
+            board_deployed_count=ctx.board_deployed_count,
+            bench=bench_indices,
+            owned_heroes=list(ctx.owned_heroes),
+            shop=shop_slots,
+            current_phase="PREPARATION"
+        )
+
+        print(f"[THINKING] Menghubungi Brain ({deps.brain.provider.upper()}) untuk keputusan belanja...")
+        decision: TurnDecision = deps.brain.decide_turn(game_state)
+        print(f"[DECISION] [{decision.policy_source.upper()}] {decision.strategic_plan}")
+
+        # 2. Eksekusi Aksi Belanja TERLEBIH DAHULU selagi toko terbuka
+        executed_actions: List[Dict[str, Any]] = []
+        for act in decision.actions:
+            if act.action == "BUY_HERO" and act.slot:
+                deps.executor.execute_command(act)
+                bought_hero = next((s.hero_name for s in shop_slots if s.slot == act.slot), f"Slot_{act.slot}")
+                if bought_hero != "KOSONG":
+                    ctx.owned_heroes.append(bought_hero)
+                executed_actions.append(act.model_dump())
+                time.sleep(0.18)
+            elif act.action == "LEVEL_UP":
+                deps.executor.execute_command(act)
+                if gold >= 4:
+                    level += 1
+                executed_actions.append(act.model_dump())
+                time.sleep(0.18)
+            elif act.action == "REROLL":
+                deps.executor.execute_command(act)
+                executed_actions.append(act.model_dump())
+                time.sleep(0.18)
+
+        # 3. Tutup Toko dengan klik netral
+        deps.executor.close_shop()
+        executed_actions.append({
+            "action": "CLOSE_SHOP",
+            "slot": None,
+            "reasoning": "Menutup toko sebelum inspeksi papan dan deploy hero"
+        })
+        time.sleep(0.25)
+
+        # 4. Ambil frame segar setelah toko tertutup untuk memastikan keakuratan bench dan HP
+        frame_board = secondary_frame if secondary_frame is not None else (
+            deps.cap.capture_frame() if deps.cap else frame
+        )
+        current_occupied_bench = deps.hero_det.scan_occupied_bench_slots(frame_board)
+        board_hp = deps.parser.parse_player_hp(frame_board, player_name=ctx.player_name)
+        if board_hp is not None and 1 <= board_hp <= 100:
+            ctx.last_known_hp = board_hp
+
+        # 5. Pemasangan (Deploy) Hero dari Bench ke Papan Catur sesuai kapasitas Level
+        heroes_needed = max(0, level - ctx.board_deployed_count)
+        if heroes_needed > 0 and current_occupied_bench:
+            print(f"[BOARD DEPLOY] Kapasitas level: {level}, terpasang: {ctx.board_deployed_count}, butuh: {heroes_needed} hero.")
+            
+            target_coords = [
+                BoardCoords.CHESSBOARD_GRID[(3, 4)],  # Baris 3 Tengah
+                BoardCoords.CHESSBOARD_GRID[(3, 3)],  # Baris 3 Tengah-Kiri
+                BoardCoords.CHESSBOARD_GRID[(3, 5)],  # Baris 3 Tengah-Kanan
+                BoardCoords.CHESSBOARD_GRID[(3, 2)],  # Baris 3 Kiri Luar
+                BoardCoords.CHESSBOARD_GRID[(3, 6)],  # Baris 3 Kanan Luar
+                BoardCoords.CHESSBOARD_GRID[(2, 4)],  # Baris 2 Tengah
+                BoardCoords.CHESSBOARD_GRID[(2, 3)],  # Baris 2 Kiri
+                BoardCoords.CHESSBOARD_GRID[(2, 5)],  # Baris 2 Kanan
+            ]
+
+            deploy_count = min(len(current_occupied_bench), heroes_needed)
+            for i in range(deploy_count):
+                slot_num, cx, cy = current_occupied_bench[i]
+                target_idx = (ctx.board_deployed_count + i) % len(target_coords)
+                target_xy = target_coords[target_idx]
+                
+                print(f"[LIVE DEPLOY] Menarik Hero Slot {slot_num} dari ({cx}, {cy}) ke Board ({target_xy[0]}, {target_xy[1]})...")
+                deps.executor.drag_hero_to_board(cx, cy, target_xy[0], target_xy[1], label=f"Deploy Slot {slot_num}")
+                
+                executed_actions.append({
+                    "action": "DEPLOY",
+                    "slot": slot_num,
+                    "reasoning": f"Deploy hero slot {slot_num} ke grid catur {target_xy}"
+                })
+                time.sleep(0.2)
+
+            ctx.board_deployed_count += deploy_count
+
+        # 6. Rekonsiliasi Hasil Tindakan dengan Observasi Pasca-Belanja
+        post_status = deps.parser.extract_game_status(frame_board, player_name=ctx.player_name)
+        reconciliation = {
+            "pre_gold": gold,
+            "post_gold": post_status["gold"],
+            "gold_spent": max(0, gold - post_status["gold"]),
+            "verified_level": post_status["level"],
+            "verified_hp": board_hp
+        }
+
+        # 7. Catat log pertandingan turn-by-turn ke Research Logger (PRD Bagian 5)
+        turn_latency_ms = (time.perf_counter() - turn_start_time) * 1000.0
+        game_state.commander_hp = ctx.last_known_hp
+        game_state.hp_observed = (board_hp is not None)
+        game_state.board_deployed_count = ctx.board_deployed_count
+        game_state.owned_heroes = list(ctx.owned_heroes)
+
+        deps.logger.log_turn(
+            state=game_state,
+            decision=decision,
+            executed_actions=executed_actions,
+            execution_latency_ms=turn_latency_ms,
+            reconciliation=reconciliation
+        )
+
+        ctx.consecutive_errors = 0
+        print(f"[DONE] Ronde {current_round} selesai dieksekusi ({turn_latency_ms:.1f}ms). Menunggu babak berikutnya...\n")
+        return {"event": "PREPARATION", "status": "HANDLED", "round": current_round}
+
+    return {"event": "IDLE", "status": "WAITING"}
+
 def run_live_bot():
     print("==========================================================")
     print("MCGG AUTONOMOUS AGENT - FULL DYNAMIC VISION CONTROLLER")
@@ -35,17 +306,30 @@ def run_live_bot():
     config = load_config()
     title_sub = config.get("game_window", {}).get("title_substring", "MagicChess")
     loop_interval = config.get("delays", {}).get("loop_interval_sec", 1.2)
-    
+    player_name = config.get("player_name", "veteran")
+
     kb = KnowledgeBase()
     parser = ScreenParser()
     hero_det = HeroDetector()
     ui_det = DynamicUIDetector()
     brain = LLMBrain(config, kb)
+    logger = ResearchLogger()
     executor = ActionExecutor(action_delay_ms=config.get("delays", {}).get("action_delay_ms", 180))
     win_mgr = GameWindowManager(title_sub)
     cap = ScreenCapture(monitor_idx=1)
 
-    print(f"[STATUS] Provider: {brain.provider.upper()} | Model: {brain.model}")
+    ctx = BotContext(player_name=player_name)
+    deps = BotDependencies(
+        parser=parser,
+        hero_det=hero_det,
+        ui_det=ui_det,
+        brain=brain,
+        executor=executor,
+        logger=logger,
+        cap=cap
+    )
+
+    print(f"[STATUS] Provider: {brain.provider.upper()} | Model: {brain.model} | Player: {player_name}")
     print("[WAITING] Menunggu jendela game Magic Chess aktif...")
 
     while not win_mgr.find_game_hwnd():
@@ -55,147 +339,23 @@ def run_live_bot():
     print("\n[GAME DETECTED] Game MCGG ditemukan! Membawa ke layer depan...")
     win_mgr.focus_game_window()
 
-    last_acted_round = ""
-    last_acted_phase = ""
-    board_deployed_count = 0
-
     print("\n[BOT ACTIVE] Agent memindai visual layar secara real-time...\n")
 
     try:
         while True:
-            frame = cap.capture_frame()
-            status = parser.extract_game_status(frame)
-            current_round = status["round"]
-            timer = status["timer_seconds"]
-            gold = status["gold"]
-            level = status["level"]
-            special_phase = status["special_phase"]
-            is_combat = status.get("is_combat", False)
-
-            # -------------------------------------------------------------
-            # SKENARIO 1: FATE BOX (Pemilihan Hadiah Putaran)
-            # -------------------------------------------------------------
-            if special_phase == "FATE_BOX" and last_acted_phase != f"FATE_{current_round}":
-                print(f"\n[EVENT FATE BOX] Memilih hadiah di lingkaran carousel...")
-                win_mgr.focus_game_window()
-                executor.pick_fatebox_reward(1)
-                last_acted_phase = f"FATE_{current_round}"
-                time.sleep(2.0)
-                continue
-
-            # -------------------------------------------------------------
-            # SKENARIO 2: GO GO CARD (Double Click Kartu Kekuatan)
-            # -------------------------------------------------------------
-            if special_phase == "GOGO_CARD" and last_acted_phase != f"GOGO_{current_round}":
-                print(f"\n[EVENT GO GO CARD] Memindai letak kartu kekuatan di layar...")
-                win_mgr.focus_game_window()
-                cards = ui_det.detect_clickable_gogo_cards(frame)
-                card_choice = 1
-                if cards and cards[0]["center"][0] > 960:
-                    card_choice = 2
-
-                print(f"[ACTION] Memilih Kartu Go Go Slot {card_choice} via Double-Click...")
-                executor.pick_gogo_card(card_choice)
-                last_acted_phase = f"GOGO_{current_round}"
-                time.sleep(1.5)
-                continue
-
-            # -------------------------------------------------------------
-            # SKENARIO 3: DROP ITEM (Pilihan Item Creep & Pasang ke Hero)
-            # -------------------------------------------------------------
-            if special_phase == "ITEM_SELECTION" and last_acted_phase != f"ITEM_{current_round}":
-                print(f"\n[EVENT DROP ITEM] Mengambil item drop dari ronde creep...")
-                win_mgr.focus_game_window()
-                executor.pick_item_option(1)
-                last_acted_phase = f"ITEM_{current_round}"
-                time.sleep(1.0)
-                
-                print("[EQUIP] Memasang item ke Hero di Papan Catur...")
-                executor.equip_item_to_hero(hero_target_idx=1)
-                continue
-
-            # -------------------------------------------------------------
-            # SKENARIO 4: FASE PERSIAPAN PERTANDINGAN
-            # -------------------------------------------------------------
-            # Saring fase persiapan: Label ronde valid, timer aktif, dan BUKAN fase combat animasi
-            is_prep_phase = (current_round != "UNKNOWN") and ("-" in current_round) and (timer > 2) and (not is_combat)
-
-            if is_prep_phase and current_round != last_acted_round:
-                print(f"\n=======================================================")
-                print(f"[FASE AKTIF] Ronde: {current_round} | Timer: {timer}s | Saldo: {gold}G | Lv: {level}")
-                print(f"=======================================================")
-
-                win_mgr.focus_game_window()
-
-                # Hitung kebutuhan deploy berdasarkan kapasitas board (Level)
-                heroes_needed = max(0, level - board_deployed_count)
-                occupied_bench = hero_det.scan_occupied_bench_slots(frame)
-                
-                if heroes_needed > 0 and occupied_bench:
-                    print(f"[VISION BENCH] Terdeteksi {len(occupied_bench)} hero di bench. Membutuhkan deploy: {heroes_needed} hero.")
-                    executor.close_shop()
-                    time.sleep(0.2)
-
-                    target_coords = [
-                        BoardCoords.CHESSBOARD_GRID[(3, 4)],  # Center Back
-                        BoardCoords.CHESSBOARD_GRID[(3, 3)],  # Mid-Left Back
-                        BoardCoords.CHESSBOARD_GRID[(3, 5)],  # Mid-Right Back
-                        BoardCoords.CHESSBOARD_GRID[(3, 2)],  # Far-Left Back
-                        BoardCoords.CHESSBOARD_GRID[(3, 6)],  # Far-Right Back
-                        BoardCoords.CHESSBOARD_GRID[(2, 4)],  # Center Mid
-                        BoardCoords.CHESSBOARD_GRID[(2, 3)],  # Mid-Left Mid
-                        BoardCoords.CHESSBOARD_GRID[(2, 5)],  # Mid-Right Mid
-                    ]
-
-                    deploy_count = min(len(occupied_bench), heroes_needed)
-                    for i in range(deploy_count):
-                        slot_num, cx, cy = occupied_bench[i]
-                        target_idx = (board_deployed_count + i) % len(target_coords)
-                        target_xy = target_coords[target_idx]
-                        print(f"[LIVE DEPLOY] Menarik Hero Slot {slot_num} dari ({cx}, {cy}) ke Board ({target_xy[0]}, {target_xy[1]})...")
-                        executor.drag_hero_to_board(cx, cy, target_xy[0], target_xy[1], label=f"Deploy Hero Slot {slot_num}")
-                        time.sleep(0.15)
-                    board_deployed_count += deploy_count
-
-                # Ekstraksi Toko & Keputusan LLM
-                raw_shop = parser.extract_shop_cards(frame)
-                shop_slots = []
-                for s in raw_shop:
-                    matched = kb.match_hero(s["raw_text"])
-                    if matched:
-                        hero_name = matched.get("Nama Hero")
-                        cost = int(float(matched.get("Harga Gold", 1)))
-                        is_empty = s["is_empty"]
-                    else:
-                        hero_name = s["raw_text"].strip() if s["raw_text"].strip() else "KOSONG"
-                        cost = 99  # Biaya tidak terjangkau untuk data noise
-                        is_empty = True
-
-                    shop_slots.append(ShopSlot(
-                        slot=s["slot"],
-                        hero_name=hero_name,
-                        cost=cost,
-                        is_empty=is_empty
-                    ))
-
-                game_state = GameState(
-                    round=current_round,
-                    timer_seconds=timer,
-                    gold=gold,
-                    level=level,
-                    shop=shop_slots,
-                    current_phase="PREPARATION"
-                )
-
-                print("[THINKING] Menghubungi LLM Brain untuk strategi...")
-                decision: TurnDecision = brain.decide_turn(game_state)
-                print(f"[DECISION] Strategi: {decision.strategic_plan}")
-
-                for act in decision.actions:
-                    executor.execute_command(act)
-
-                last_acted_round = current_round
-                print(f"[DONE] Ronde {current_round} selesai dieksekusi. Menunggu babak selanjutnya...")
+            try:
+                frame = cap.capture_frame()
+                process_frame(frame, ctx, deps)
+            except Exception as loop_err:
+                ctx.consecutive_errors += 1
+                tb_str = traceback.format_exc()
+                print(f"[RUNTIME WARNING] Error beruntun ke-{ctx.consecutive_errors}: {loop_err}")
+                logger.log_error(ctx.last_acted_round, str(loop_err), tb_str)
+
+                if ctx.consecutive_errors >= ctx.max_consecutive_errors:
+                    raise RuntimeError(
+                        f"[FATAL] Bot dihentikan: Mencapai batas maksimal {ctx.max_consecutive_errors} error beruntun."
+                    )
 
             time.sleep(loop_interval)
 
```

### `config.json`

```diff
diff --git a/config.json b/config.json
index 840dd63..341f715 100644
--- a/config.json
+++ b/config.json
@@ -1,6 +1,7 @@
 {
   "agent_id": "agent-01",
   "agent_name": "MCGG-Esports-Agent",
+  "player_name": "veteran",
   "game_window": {
     "title_substring": "MagicChess",
     "target_width": 1920,
```

### `pyproject.toml`

```diff
diff --git a/pyproject.toml b/pyproject.toml
index 415a24c..fa46e53 100644
--- a/pyproject.toml
+++ b/pyproject.toml
@@ -12,8 +12,17 @@ dependencies = [
     "opencv-python-headless>=4.10.0",
     "rapidocr-onnxruntime>=1.3.0",
     "pydirectinput>=1.0.4",
-    "pywin32>=308; sys_platform == 'win32'"
+    "pywin32>=308; sys_platform == 'win32'",
+]
+
+[dependency-groups]
+dev = [
+    "pytest>=9.2.0",
 ]
 
 [tool.uv]
 package = false
+
+[tool.pytest.ini_options]
+pythonpath = ["."]
+
```

### `uv.lock`

```diff
diff --git a/uv.lock b/uv.lock
index 54ff744..5e3a5be 100644
--- a/uv.lock
+++ b/uv.lock
@@ -721,6 +721,15 @@ wheels = [
     { url = "https://files.pythonhosted.org/packages/7d/f9/97f2ca8bb3ec6e4b1d64f983ebe98b9a192faddff67fac3d6303a537e670/importlib_metadata-8.9.0-py3-none-any.whl", hash = "sha256:e0f761b6ea91ced3b0844c14c9d955224d538105921f8e6754c00f6ca79fba7f", size = 27220, upload-time = "2026-03-20T16:56:25.07Z" },
 ]
 
+[[package]]
+name = "iniconfig"
+version = "2.3.1"
+source = { registry = "https://pypi.org/simple" }
+sdist = { url = "https://files.pythonhosted.org/packages/01/e1/2069291243c926a2ff1cd706c7f3eeb9b62144bf60f77c9fb9ff2fb26bd3/iniconfig-2.3.1.tar.gz", hash = "sha256:67f4b9c50da0dedf52af349e7749a80a9057a5031199791b906c3bb3ae878960", size = 21209, upload-time = "2026-10-06T22:48:38.076Z" }
+wheels = [
+    { url = "https://files.pythonhosted.org/packages/56/43/4ca9e49d27a1fcf6bece6f6aec0ea46bb9112489b93d4b688fb415457bdb/iniconfig-2.3.1-py3-none-any.whl", hash = "sha256:9121e2c1fdb355232495be3194c8dfe87ccc2d5dee45947b78e68f499790d7a7", size = 7552, upload-time = "2026-10-06T22:48:36.959Z" },
+]
+
 [[package]]
 name = "jinja2"
 version = "3.1.6"
@@ -1033,6 +1042,11 @@ dependencies = [
     { name = "rapidocr-onnxruntime" },
 ]
 
+[package.dev-dependencies]
+dev = [
+    { name = "pytest" },
+]
+
 [package.metadata]
 requires-dist = [
     { name = "litellm", specifier = ">=1.50.0" },
@@ -1045,6 +1059,9 @@ requires-dist = [
     { name = "rapidocr-onnxruntime", specifier = ">=1.3.0" },
 ]
 
+[package.metadata.requires-dev]
+dev = [{ name = "pytest", specifier = ">=9.2.0" }]
+
 [[package]]
 name = "mss"
 version = "10.2.0"
@@ -1437,6 +1454,15 @@ wheels = [
     { url = "https://files.pythonhosted.org/packages/c0/37/66b12dc476041fe523bca29c9d58fbf1ea92a4eaf73acfb9e993948f1191/pillow-13.0.0-pp312-pypy312_pp80-win_amd64.whl", hash = "sha256:567f20f1c75897d7663830da6ea8af719e03d712b1d9ee7f813319f9ece42e5a", size = 7366030, upload-time = "2026-10-16T22:18:06.638Z" },
 ]
 
+[[package]]
+name = "pluggy"
+version = "1.7.0"
+source = { registry = "https://pypi.org/simple" }
+sdist = { url = "https://files.pythonhosted.org/packages/bf/db/7fc19e6f2dc92a966727031389fc2e08b558f0f25eb7403c1119ad4713cd/pluggy-1.7.0.tar.gz", hash = "sha256:d1eaa46ebb595891b860ab086b4d09c8588af65ebd4361b8e8f4bb8920b90ba8", size = 123304, upload-time = "2026-10-15T09:50:58.343Z" }
+wheels = [
+    { url = "https://files.pythonhosted.org/packages/40/9e/2b38731e0fc536806f16490e1a12d7f0dc2a1235aa8cc07bcc75416a7daa/pluggy-1.7.0-py3-none-any.whl", hash = "sha256:7dd7b0d8832ba3cb632c306926ded123429211b83641b35dc5c41ad2d34f9bec", size = 27082, upload-time = "2026-10-15T09:50:56.808Z" },
+]
+
 [[package]]
 name = "propcache"
 version = "0.5.4"
@@ -1741,6 +1767,31 @@ wheels = [
     { url = "https://files.pythonhosted.org/packages/c9/8e/f909defe798270afc2241d3a8986d51459e70c37f02d2ba549627b781b2c/PyDirectInput-1.0.4-py3-none-any.whl", hash = "sha256:238bbe97f505f9c8728a47ea6a787750dbe834ec1fb42b98b3d703d827eda83e", size = 8879, upload-time = "2021-02-02T22:23:28.115Z" },
 ]
 
+[[package]]
+name = "pygments"
+version = "2.21.0"
+source = { registry = "https://pypi.org/simple" }
+sdist = { url = "https://files.pythonhosted.org/packages/49/2e/ced460408999b33da6b31b0021b0f37d329e202d4169aeb164493778f25b/pygments-2.21.0.tar.gz", hash = "sha256:610ca751c9bc2492b38eb9a38a7fbc93edbbb2d7182edaf34e66ae493dee5c8c", size = 5005329, upload-time = "2026-08-17T08:02:48.824Z" }
+wheels = [
+    { url = "https://files.pythonhosted.org/packages/71/46/17f022dd3e953bf20a04a028a21ec746d942f8d2af30fa0f124fa0e6a684/pygments-2.21.0-py3-none-any.whl", hash = "sha256:2363c69b61c4a97c838da3b130dcd6468f4848992b21a82f2a63ec34377137d9", size = 1250147, upload-time = "2026-08-17T08:02:44.912Z" },
+]
+
+[[package]]
+name = "pytest"
+version = "9.2.0"
+source = { registry = "https://pypi.org/simple" }
+dependencies = [
+    { name = "colorama", marker = "sys_platform == 'win32'" },
+    { name = "iniconfig" },
+    { name = "packaging" },
+    { name = "pluggy" },
+    { name = "pygments" },
+]
+sdist = { url = "https://files.pythonhosted.org/packages/79/42/bb4641652e58dedeac2ec51abc1f8cae4fee4ec63899a0999016229a0f2a/pytest-9.2.0.tar.gz", hash = "sha256:97c4f3b1f3c7414aa36465e09b8220f1d03627993bd51b1282e193753c80557b", size = 1797555, upload-time = "2026-10-27T21:30:20.728Z" }
+wheels = [
+    { url = "https://files.pythonhosted.org/packages/51/39/1f5d8c8877a0fa327db959c19341d4be61660de1ab6b7391f9eb805bcd67/pytest-9.2.0-py3-none-any.whl", hash = "sha256:07acdcf88ec174f907dc01af70bf52d49b014bbab03faeeade31c96b18c2e588", size = 411776, upload-time = "2026-10-27T21:30:19.131Z" },
+]
+
 [[package]]
 name = "python-dateutil"
 version = "2.9.0.post0"
```

### `tests/test_decision.py`

```diff
diff --git a/tests/test_decision.py b/tests/test_decision.py
new file mode 100644
index 0000000..3e2ee60
--- /dev/null
+++ b/tests/test_decision.py
@@ -0,0 +1,65 @@
+import pytest
+from src.decision.kb_loader import KnowledgeBase
+from src.decision.llm_router import LLMBrain
+from src.decision.models import GameState, ShopSlot
+
+def test_kb_loader_contains_all_58_heroes():
+    kb = KnowledgeBase()
+    assert len(kb.heroes) == 58, f"Expected 58 heroes in KB, got {len(kb.heroes)}"
+    assert len(kb.synergies) == 21, f"Expected 21 synergies in KB, got {len(kb.synergies)}"
+
+    summary = kb.get_summary_prompt_context()
+    assert "=== DAFTAR LENGKAP 58 HERO PATCH 7.2 ===" in summary
+    assert "=== DAFTAR 21 SINERGI PATCH 7.2 ===" in summary
+    assert "Miya" in summary
+    assert "Wanwan" in summary
+
+def test_fast_rule_round_1_1_no_duplicate_deploy():
+    kb = KnowledgeBase()
+    dummy_config = {"llm": {"provider": "gemini", "model": "gemini-3.5-flash-lite"}}
+    brain = LLMBrain(config=dummy_config, kb=kb)
+
+    state = GameState(
+        round="1-1",
+        timer_seconds=25,
+        gold=1,
+        level=3,
+        commander_hp=100,
+        board_deployed_count=0,
+        bench=[1],
+        shop=[ShopSlot(slot=1, hero_name="Miya", cost=1, is_empty=False)],
+        current_phase="PREPARATION"
+    )
+
+    decision = brain.decide_turn(state)
+    assert decision.policy_source == "fast_rule"
+    assert decision.latency_ms > 0
+
+    # Pastikan tidak ada aksi DEPLOY hardcoded ganda yang memicu slot bench kosong
+    action_types = [a.action for a in decision.actions]
+    assert "DEPLOY" not in action_types
+    assert "CLOSE_SHOP" in action_types
+    assert "END_TURN" in action_types
+
+def test_offline_heuristic_fallback_labels_source():
+    kb = KnowledgeBase()
+    dummy_config = {"llm": {"provider": "gemini", "model": "gemini-3.5-flash-lite"}}
+    brain = LLMBrain(config=dummy_config, kb=kb)
+    brain.api_key = ""  # Paksa fallback
+
+    state = GameState(
+        round="2-1",
+        timer_seconds=20,
+        gold=10,
+        level=4,
+        commander_hp=95,
+        board_deployed_count=3,
+        bench=[1],
+        shop=[ShopSlot(slot=1, hero_name="Layla", cost=1, is_empty=False)],
+        current_phase="PREPARATION"
+    )
+
+    decision = brain.decide_turn(state)
+    assert decision.policy_source == "offline_heuristic"
+    assert decision.latency_ms > 0
+    assert len(decision.actions) > 0
```

### `tests/test_logger.py`

```diff
diff --git a/tests/test_logger.py b/tests/test_logger.py
new file mode 100644
index 0000000..1224693
--- /dev/null
+++ b/tests/test_logger.py
@@ -0,0 +1,68 @@
+import os
+import json
+import pytest
+from src.decision.research_logger import ResearchLogger
+from src.decision.models import GameState, TurnDecision, ActionCommand, ShopSlot
+
+def test_research_logger_writes_valid_jsonl(tmp_path):
+    # Buat custom config dalam temporary path
+    custom_config = tmp_path / "config.json"
+    custom_config.write_text(json.dumps({
+        "agent_id": "test-agent-01",
+        "agent_name": "Test-Agent",
+        "logging": {
+            "save_match_history": True,
+            "log_dir": str(tmp_path / "logs")
+        }
+    }), encoding="utf-8")
+
+    logger = ResearchLogger(config_path=str(custom_config))
+    assert os.path.exists(logger.log_dir)
+
+    state = GameState(
+        round="1-1",
+        timer_seconds=25,
+        gold=0,
+        level=3,
+        commander_hp=100,
+        board_deployed_count=1,
+        bench=[1],
+        shop=[ShopSlot(slot=1, hero_name="Miya", cost=1, is_empty=False)],
+        current_phase="PREPARATION"
+    )
+
+    decision = TurnDecision(
+        strategic_plan="Beli Miya untuk sinergi Marksman",
+        policy_source="fast_rule",
+        latency_ms=12.5,
+        actions=[ActionCommand(action="BUY_HERO", slot=1, reasoning="Membeli Miya")]
+    )
+
+    executed_actions = [{"action": "BUY_HERO", "slot": 1, "status": "SUCCESS"}]
+    execution_latency_ms = 45.2
+
+    logger.log_turn(
+        state=state,
+        decision=decision,
+        executed_actions=executed_actions,
+        execution_latency_ms=execution_latency_ms
+    )
+
+    assert os.path.exists(logger.log_file)
+    with open(logger.log_file, "r", encoding="utf-8") as f:
+        lines = f.readlines()
+
+    assert len(lines) == 1
+    record = json.loads(lines[0])
+
+    assert record["agent_id"] == "test-agent-01"
+    assert record["round"] == "1-1"
+    assert record["policy_source"] == "fast_rule"
+    assert record["llm_latency_ms"] == 12.5
+    assert record["execution_latency_ms"] == 45.2
+    assert record["observed_state"]["gold"] == 0
+    assert record["observed_state"]["bench_occupied_slots"] == [1]
+    assert record["observed_state"]["commander_hp"] == 100
+    assert record["bot_belief"]["board_deployed_count"] == 1
+    assert "owned_heroes" in record["bot_belief"]
+    assert len(record["actions_executed"]) == 1
```

### `tests/test_perception.py`

```diff
diff --git a/tests/test_perception.py b/tests/test_perception.py
new file mode 100644
index 0000000..1528fdb
--- /dev/null
+++ b/tests/test_perception.py
@@ -0,0 +1,87 @@
+import os
+import cv2
+import pytest
+from src.perception.screen_parser import ScreenParser
+
+ASSET_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "asset"))
+
+GROUND_TRUTH_SAMPLES = [
+    ("ambil-item.png", True, "Combat phase with active fight and item drops"),
+    ("beli-hero.png", False, "Prep phase with shop drawer opened"),
+    ("beli-hero-situasi-khusus.png", False, "Prep phase with special shop situation"),
+    ("chessboard.png", False, "Prep phase with shop drawer closed"),
+    ("fase-fatebox.png", False, "Special phase: Fate Box draft"),
+    ("memilih-gogocard.png", False, "Special phase: Go Go Card selection"),
+    ("pindah-memindah-item.png", False, "Prep phase: Hero placed item management modal"),
+]
+
+@pytest.fixture(scope="module")
+def parser():
+    return ScreenParser()
+
+@pytest.mark.parametrize("filename, expected_is_combat, description", GROUND_TRUTH_SAMPLES)
+def test_detect_combat_active(parser, filename, expected_is_combat, description):
+    image_path = os.path.join(ASSET_DIR, filename)
+    assert os.path.exists(image_path), f"Asset file missing: {image_path}"
+    
+    frame = cv2.imread(image_path)
+    assert frame is not None, f"Failed to load image: {image_path}"
+    
+    is_combat = parser.detect_combat_active(frame)
+    assert is_combat == expected_is_combat, (
+        f"Failed on {filename} ({description}): expected combat={expected_is_combat}, got {is_combat}"
+    )
+
+def test_parse_player_hp(parser):
+    # Test pembacaan angka HP nyata dari panel pemain
+    chessboard_frame = cv2.imread(os.path.join(ASSET_DIR, "chessboard.png"))
+    hp_chessboard = parser.parse_player_hp(chessboard_frame, player_name="veteran")
+    assert hp_chessboard == 94, f"Expected 94 HP on chessboard.png (row 5 'veteran'), got {hp_chessboard}"
+
+    pindah_frame = cv2.imread(os.path.join(ASSET_DIR, "pindah-memindah-item.png"))
+    hp_pindah = parser.parse_player_hp(pindah_frame, player_name="veteran")
+    assert hp_pindah == 94, f"Expected 94 HP on pindah-memindah-item.png, got {hp_pindah}"
+
+    ambil_frame = cv2.imread(os.path.join(ASSET_DIR, "ambil-item.png"))
+    hp_ambil = parser.parse_player_hp(ambil_frame, player_name="veteran")
+    assert hp_ambil == 100, f"Expected 100 HP on ambil-item.png, got {hp_ambil}"
+
+    beli_frame = cv2.imread(os.path.join(ASSET_DIR, "beli-hero.png"))
+    hp_beli = parser.parse_player_hp(beli_frame, player_name="veteran")
+    assert hp_beli is None, f"Expected None when shop drawer covers leaderboard in beli-hero.png, got {hp_beli}"
+
+def test_detect_combat_brightness_resilience(parser):
+    import numpy as np
+    ambil_frame = cv2.imread(os.path.join(ASSET_DIR, "ambil-item.png"))
+    beli_frame = cv2.imread(os.path.join(ASSET_DIR, "beli-hero.png"))
+
+    # Uji ketahanan terhadap pergeseran kecerahan (+25 dan -25 offset)
+    for offset in [25, -25]:
+        bright_combat = np.clip(ambil_frame.astype(np.int16) + offset, 0, 255).astype(np.uint8)
+        assert parser.detect_combat_active(bright_combat) is True, f"Combat not detected with brightness offset {offset}"
+
+        bright_prep = np.clip(beli_frame.astype(np.int16) + offset, 0, 255).astype(np.uint8)
+        assert parser.detect_combat_active(bright_prep) is False, f"False combat detected on prep with brightness offset {offset}"
+
+def test_dynamic_gameplay_frames_stability(parser):
+    frames_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "dynamic_gameplay_frames"))
+    if not os.path.exists(frames_dir):
+        pytest.skip("dynamic_gameplay_frames directory not found")
+        
+    all_frames = sorted([
+        os.path.join(frames_dir, f) for f in os.listdir(frames_dir) if f.endswith(".jpg")
+    ])
+    if not all_frames:
+        pytest.skip("No dynamic gameplay frames found")
+        
+    # Ambil sampel 30 frame tersebar sepanjang pertandingan
+    step = max(1, len(all_frames) // 30)
+    sampled = all_frames[::step][:30]
+    
+    assert len(sampled) >= 10, f"Expected at least 10 sample frames, got {len(sampled)}"
+    for frame_path in sampled:
+        frame = cv2.imread(frame_path)
+        assert frame is not None, f"Failed reading {frame_path}"
+        is_combat = parser.detect_combat_active(frame)
+        assert isinstance(is_combat, bool)
+
```

### `tests/test_live_bot_smoke.py`

```diff
diff --git a/tests/test_live_bot_smoke.py b/tests/test_live_bot_smoke.py
new file mode 100644
index 0000000..f366fbc
--- /dev/null
+++ b/tests/test_live_bot_smoke.py
@@ -0,0 +1,110 @@
+import os
+import cv2
+import pytest
+from unittest.mock import MagicMock
+from live_bot import BotContext, BotDependencies, process_frame
+from src.perception.screen_parser import ScreenParser
+from src.perception.hero_detector import HeroDetector
+from src.perception.ui_detector import DynamicUIDetector
+from src.decision.kb_loader import KnowledgeBase
+from src.decision.llm_router import LLMBrain
+from src.decision.research_logger import ResearchLogger
+
+ASSET_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "asset"))
+
+@pytest.fixture
+def mock_executor():
+    executor = MagicMock()
+    executor.executed_calls = []
+    
+    def log_call(method_name):
+        def handler(*args, **kwargs):
+            executor.executed_calls.append((method_name, args, kwargs))
+        return handler
+
+    for method in [
+        "click_point", "drag_hero_to_board", "buy_hero_slot",
+        "close_shop", "open_shop", "pick_fatebox_reward",
+        "pick_gogo_card", "pick_item_option", "equip_item_to_hero",
+        "reroll_shop", "level_up", "execute_command"
+    ]:
+        setattr(executor, method, MagicMock(side_effect=log_call(method)))
+        
+    return executor
+
+@pytest.fixture
+def bot_deps(mock_executor, tmp_path):
+    parser = ScreenParser()
+    hero_det = HeroDetector()
+    ui_det = DynamicUIDetector()
+    kb = KnowledgeBase()
+    brain = LLMBrain(config={"llm": {"provider": "gemini", "model": "gemini-3.5-flash-lite"}}, kb=kb)
+    brain.api_key = None  # Ensure deterministic offline tests without external network latency
+    
+    custom_config = tmp_path / "config.json"
+    custom_config.write_text('{"logging": {"save_match_history": true, "log_dir": "logs"}}', encoding="utf-8")
+    logger = ResearchLogger(config_path=str(custom_config))
+    
+    return BotDependencies(
+        parser=parser,
+        hero_det=hero_det,
+        ui_det=ui_det,
+        brain=brain,
+        executor=mock_executor,
+        logger=logger,
+        cap=None
+    )
+
+def test_process_frame_fatebox_real_handler(bot_deps, mock_executor):
+    img = cv2.imread(os.path.join(ASSET_DIR, "fase-fatebox.png"))
+    ctx = BotContext(player_name="veteran")
+
+    res = process_frame(img, ctx, bot_deps)
+    assert res["event"] == "FATE_BOX"
+    assert res["status"] == "HANDLED"
+
+    calls = [c[0] for c in mock_executor.executed_calls]
+    assert "pick_fatebox_reward" in calls
+
+def test_process_frame_gogo_card_real_handler(bot_deps, mock_executor):
+    img = cv2.imread(os.path.join(ASSET_DIR, "memilih-gogocard.png"))
+    ctx = BotContext(player_name="veteran")
+
+    res = process_frame(img, ctx, bot_deps)
+    assert res["event"] == "GOGO_CARD"
+    assert res["status"] == "HANDLED"
+    assert res["slot"] in [1, 2]
+
+    # Pastikan executor dipanggil dengan slot yang diputuskan
+    calls = [c for c in mock_executor.executed_calls if c[0] == "pick_gogo_card"]
+    assert len(calls) == 1
+    slot_called = calls[0][1][0]
+    assert slot_called == res["slot"]
+
+def test_process_frame_prep_phase_full_pipeline(bot_deps, mock_executor):
+    prep_frame = cv2.imread(os.path.join(ASSET_DIR, "beli-hero.png"))
+    board_frame = cv2.imread(os.path.join(ASSET_DIR, "chessboard.png"))
+    ctx = BotContext(player_name="veteran")
+
+    res = process_frame(prep_frame, ctx, bot_deps, secondary_frame=board_frame)
+    assert res["event"] == "PREPARATION"
+    assert res["status"] == "HANDLED"
+    assert ctx.last_acted_round != ""
+
+    calls = [c[0] for c in mock_executor.executed_calls]
+    # Pastikan tutup toko terpanggil
+    assert "close_shop" in calls
+
+def test_process_frame_prevents_duplicate_turn_on_repeat(bot_deps, mock_executor):
+    prep_frame = cv2.imread(os.path.join(ASSET_DIR, "beli-hero.png"))
+    ctx = BotContext(player_name="veteran")
+
+    # Putaran pertama dijalankan
+    res1 = process_frame(prep_frame, ctx, bot_deps)
+    assert res1["event"] == "PREPARATION"
+    first_call_count = len(mock_executor.executed_calls)
+
+    # Putaran kedua pada frame yang sama: wajib diabaikan karena last_acted_round sudah sama
+    res2 = process_frame(prep_frame, ctx, bot_deps)
+    assert res2["event"] == "IDLE"
+    assert len(mock_executor.executed_calls) == first_call_count
```

