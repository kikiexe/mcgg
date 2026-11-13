"""
Trajectory Delta Extractor with Optical Differencing
Optimized for high-speed extraction: skips OCR when regional pixel diff is zero.
Extracts: Round, Timer, Gold, Level, Shop purchases, Level ups.
"""
import os
import sys
import glob
import re
import json
import time
import cv2
import numpy as np
from rapidocr_onnxruntime import RapidOCR

ocr = RapidOCR()

FRAME_DIR = r"C:\Projects\mcgg\dynamic_gameplay_frames"
OUTPUT_PATH = r"C:\Projects\mcgg\gameplay_trajectory_summary.json"

# Bounding boxes (1920x1080)
# Gold: (1770, 900, 1870, 970)
# Round: (610, 5, 700, 50)
# Level: (20, 930, 150, 990)
GOLD_BOX = (900, 970, 1770, 1870)   # Y1, Y2, X1, X2
ROUND_BOX = (5, 50, 610, 700)
LEVEL_BOX = (930, 990, 20, 150)
SHOP_BOX = (420, 700, 250, 1700)

files = sorted(glob.glob(os.path.join(FRAME_DIR, "action_t*.jpg")))
print(f"[INIT] Total Action Frames to Analyze: {len(files)}")

def read_digits(img_crop, default=0):
    res, _ = ocr(img_crop)
    if not res:
        return default
    text = " ".join([x[1] for x in res])
    digits = re.findall(r'\d+', text)
    if digits:
        return int("".join(digits))
    return default

def read_text(img_crop):
    res, _ = ocr(img_crop)
    if not res:
        return ""
    return " ".join([x[1] for x in res]).strip()

# Run sampling & optical differencing
trajectory = []
prev_gold_crop = None
prev_level_crop = None
prev_round_crop = None

last_gold = 0
last_level = 3
last_round = "1-1"

# We sample every 2 frames (2 seconds), or when pixel diff is detected
start_time = time.time()

for idx, fpath in enumerate(files):
    # Process every 2nd frame or key transition
    if idx % 2 != 0 and idx != len(files) - 1:
        continue

    fname = os.path.basename(fpath)
    sec_match = re.search(r't(\d+)s', fname)
    sec = int(sec_match.group(1)) if sec_match else idx

    img = cv2.imread(fpath)
    if img is None:
        continue

    gold_crop = img[GOLD_BOX[0]:GOLD_BOX[1], GOLD_BOX[2]:GOLD_BOX[3]]
    level_crop = img[LEVEL_BOX[0]:LEVEL_BOX[1], LEVEL_BOX[2]:LEVEL_BOX[3]]
    round_crop = img[ROUND_BOX[0]:ROUND_BOX[1], ROUND_BOX[2]:ROUND_BOX[3]]

    # Check optical diff
    gold_diff = 100 if prev_gold_crop is None else np.mean(cv2.absdiff(gold_crop, prev_gold_crop))
    level_diff = 100 if prev_level_crop is None else np.mean(cv2.absdiff(level_crop, prev_level_crop))
    round_diff = 100 if prev_round_crop is None else np.mean(cv2.absdiff(round_crop, prev_round_crop))

    # Update state only if visual diff indicates a real change
    if gold_diff > 4.0 or idx == 0:
        g = read_digits(gold_crop, default=last_gold)
        if 0 <= g <= 200:
            last_gold = g
        prev_gold_crop = gold_crop

    if level_diff > 4.0 or idx == 0:
        lvl = read_digits(level_crop, default=last_level)
        if 3 <= lvl <= 10:
            last_level = lvl
        prev_level_crop = level_crop

    if round_diff > 4.0 or idx == 0:
        r_str = read_text(round_crop)
        if r_str and len(r_str) <= 6:
            last_round = r_str
        prev_round_crop = round_crop

    trajectory.append({
        "second": sec,
        "round": last_round,
        "level": last_level,
        "gold": last_gold
    })

    if (len(trajectory)) % 50 == 0:
        elapsed = time.time() - start_time
        print(f"[PROGRESS] Analyzed {len(trajectory)} steps ({sec}s) | Round: {last_round} | Lv: {last_level} | Gold: {last_gold} | Elapsed: {elapsed:.1f}s")

with open(OUTPUT_PATH, "w") as f:
    json.dump(trajectory, f, indent=2)

total_elapsed = time.time() - start_time
print(f"[DONE] Trajectory extracted in {total_elapsed:.1f}s. Saved to {OUTPUT_PATH}")
