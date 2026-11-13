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

