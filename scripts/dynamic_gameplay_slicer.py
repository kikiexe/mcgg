"""
Dynamic Gameplay Frame Extractor for MCGG
Extracts 1-fps frames during active player interaction phases (Prep, Events, Cards, Shop).
Dynamically skips combat battle animations via real-time board health bar detection.
"""
import os
import sys
import json
import time
import cv2
import numpy as np

VIDEO_PATH = r"C:\Users\ASUS 25\Videos\Perekaman Layar\Perekaman Layar 2026-11-13 200101.mp4"
OUTPUT_DIR = r"C:\Projects\mcgg\dynamic_gameplay_frames"
TIMELINE_PATH = r"C:\Projects\mcgg\dynamic_gameplay_timeline.json"

os.makedirs(OUTPUT_DIR, exist_ok=True)

cap = cv2.VideoCapture(VIDEO_PATH)
fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
total_duration_sec = int(total_frames / fps)

print(f"[INIT] Video Duration: {total_duration_sec}s (~{total_duration_sec/60:.1f} min) | FPS: {fps}")

timeline = []
current_sec = 0
saved_count = 0
combat_streak = 0

start_wall_time = time.time()

while current_sec < total_duration_sec:
    frame_no = int(current_sec * fps)
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_no)
    ret, frame = cap.read()
    if not ret:
        break

    # Region of Interest: Chessboard area where enemy red HP bars appear during combat
    # Y: 200 to 700, X: 300 to 1600
    board_roi = frame[200:700, 300:1600]
    red_hp_mask = (board_roi[:, :, 2] > 180) & (board_roi[:, :, 1] < 50) & (board_roi[:, :, 0] < 50)
    red_hp_pixels = int(np.sum(red_hp_mask))

    is_combat = red_hp_pixels > 250

    if is_combat:
        combat_streak += 1
        # Fast-forward through combat battle animations (2s step)
        current_sec += 2
    else:
        combat_streak = 0
        # Active Player Phase: Save 1-fps frame for tactical analysis
        frame_filename = f"action_t{current_sec:04d}s.jpg"
        frame_path = os.path.join(OUTPUT_DIR, frame_filename)
        cv2.imwrite(frame_path, frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        
        timeline.append({
            "second": current_sec,
            "file": frame_filename,
            "hp_pixels": red_hp_pixels,
            "phase": "INTERACTION"
        })
        saved_count += 1
        current_sec += 1

    # Status log every 100 seconds
    if current_sec % 100 == 0 or current_sec >= total_duration_sec - 2:
        elapsed = time.time() - start_wall_time
        print(f"[PROGRESS] {current_sec}/{total_duration_sec}s | Saved: {saved_count} frames | Elapsed: {elapsed:.1f}s")

cap.release()

with open(TIMELINE_PATH, "w") as f:
    json.dump(timeline, f, indent=2)

total_elapsed = time.time() - start_wall_time
print(f"[COMPLETE] Dynamic Slicing Finished in {total_elapsed:.1f}s!")
print(f"[RESULT] Total Action Frames Extracted: {saved_count} (Combat animations skipped).")
