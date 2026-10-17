"""截取某个生成任务里每隔几帧的脸部，拼成一行，用来检查有没有张嘴。

    D:/comfy/.venv/Scripts/python.exe scripts/comfy/contact.py thinking-L
"""

import os
import sys
from pathlib import Path

from PIL import Image

# 形象：环境变量 CLAUDE_GIRL_SKIN 为空是原版，chibi 是 Q 版（生成目录和素材目录都分开）
SKIN = os.environ.get("CLAUDE_GIRL_SKIN", "")
_SUFFIX = f"-{SKIN}" if SKIN else ""
GEN_DIR = Path(f"D:/comfy/ComfyUI/output/claude-girl-gen{_SUFFIX}")
OUT_DIR = Path(__file__).resolve().parents[2] / ".scratch" / "faces"
FACE_BOX = (330, 150, 470, 290)  # 768×1344 画面里头部的大致位置

job = sys.argv[1]
files = sorted((GEN_DIR / job).glob("frame_*.png"))
step = max(1, len(files) // 16)
tiles = [Image.open(f).convert("RGB").crop(FACE_BOX).resize((80, 80)) for f in files[::step]]
sheet = Image.new("RGB", (80 * len(tiles), 80))
for i, t in enumerate(tiles):
    sheet.paste(t, (i * 80, 0))
OUT_DIR.mkdir(parents=True, exist_ok=True)
sheet.save(OUT_DIR / f"{job}.png")
print(f"脸部检查图：.scratch/faces/{job}.png（每 {step} 帧一张）")
