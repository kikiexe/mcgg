import os
import cv2
import pytest
from src.perception.screen_parser import ScreenParser

ASSET_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "asset"))

GROUND_TRUTH_SAMPLES = [
    ("ambil-item.png", True, "Combat phase with active fight and item drops"),
    ("beli-hero.png", False, "Prep phase with shop drawer opened"),
    ("beli-hero-situasi-khusus.png", False, "Prep phase with special shop situation"),
    ("chessboard.png", False, "Prep phase with shop drawer closed"),
    ("fase-fatebox.png", False, "Special phase: Fate Box draft"),
    ("memilih-gogocard.png", False, "Special phase: Go Go Card selection"),
    ("pindah-memindah-item.png", False, "Prep phase: Hero placed item management modal"),
]

@pytest.fixture(scope="module")
def parser():
    return ScreenParser()

@pytest.mark.parametrize("filename, expected_is_combat, description", GROUND_TRUTH_SAMPLES)
def test_detect_combat_active(parser, filename, expected_is_combat, description):
    image_path = os.path.join(ASSET_DIR, filename)
    assert os.path.exists(image_path), f"Asset file missing: {image_path}"
    
    frame = cv2.imread(image_path)
    assert frame is not None, f"Failed to load image: {image_path}"
    
    is_combat = parser.detect_combat_active(frame)
    assert is_combat == expected_is_combat, (
        f"Failed on {filename} ({description}): expected combat={expected_is_combat}, got {is_combat}"
    )

def test_parse_player_hp(parser):
    # Test pembacaan angka HP nyata dari panel pemain
    chessboard_frame = cv2.imread(os.path.join(ASSET_DIR, "chessboard.png"))
    hp_chessboard = parser.parse_player_hp(chessboard_frame, player_name="veteran")
    assert hp_chessboard == 94, f"Expected 94 HP on chessboard.png (row 5 'veteran'), got {hp_chessboard}"

    pindah_frame = cv2.imread(os.path.join(ASSET_DIR, "pindah-memindah-item.png"))
    hp_pindah = parser.parse_player_hp(pindah_frame, player_name="veteran")
    assert hp_pindah == 94, f"Expected 94 HP on pindah-memindah-item.png, got {hp_pindah}"

    ambil_frame = cv2.imread(os.path.join(ASSET_DIR, "ambil-item.png"))
    hp_ambil = parser.parse_player_hp(ambil_frame, player_name="veteran")
    assert hp_ambil == 100, f"Expected 100 HP on ambil-item.png, got {hp_ambil}"

    beli_frame = cv2.imread(os.path.join(ASSET_DIR, "beli-hero.png"))
    hp_beli = parser.parse_player_hp(beli_frame, player_name="veteran")
    assert hp_beli is None, f"Expected None when shop drawer covers leaderboard in beli-hero.png, got {hp_beli}"

def test_detect_combat_brightness_resilience(parser):
    import numpy as np
    ambil_frame = cv2.imread(os.path.join(ASSET_DIR, "ambil-item.png"))
    beli_frame = cv2.imread(os.path.join(ASSET_DIR, "beli-hero.png"))

    # Uji ketahanan terhadap pergeseran kecerahan (+25 dan -25 offset)
    for offset in [25, -25]:
        bright_combat = np.clip(ambil_frame.astype(np.int16) + offset, 0, 255).astype(np.uint8)
        assert parser.detect_combat_active(bright_combat) is True, f"Combat not detected with brightness offset {offset}"

        bright_prep = np.clip(beli_frame.astype(np.int16) + offset, 0, 255).astype(np.uint8)
        assert parser.detect_combat_active(bright_prep) is False, f"False combat detected on prep with brightness offset {offset}"

def test_dynamic_gameplay_frames_stability(parser):
    frames_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "dynamic_gameplay_frames"))
    if not os.path.exists(frames_dir):
        pytest.skip("dynamic_gameplay_frames directory not found")
        
    all_frames = sorted([
        os.path.join(frames_dir, f) for f in os.listdir(frames_dir) if f.endswith(".jpg")
    ])
    if not all_frames:
        pytest.skip("No dynamic gameplay frames found")
        
    # Ambil sampel 30 frame tersebar sepanjang pertandingan
    step = max(1, len(all_frames) // 30)
    sampled = all_frames[::step][:30]
    
    assert len(sampled) >= 10, f"Expected at least 10 sample frames, got {len(sampled)}"
    for frame_path in sampled:
        frame = cv2.imread(frame_path)
        assert frame is not None, f"Failed reading {frame_path}"
        is_combat = parser.detect_combat_active(frame)
        assert isinstance(is_combat, bool)

