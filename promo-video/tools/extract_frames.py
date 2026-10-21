"""把宣传片要用的实机片段（manifest 里登记、桌宠实际播放的 AVIF）拆成 WebP 帧序列，给网页逐帧绘制。

    uv run python promo-video/tools/extract_frames.py

只缩放、不做任何别的处理：片子里她的每一帧都和桌宠里播放的一模一样。
输出 promo-video/frames/<形象>/<片段>/0000.webp …，以及 frames/index.json（每段的帧数和尺寸）。
"""

import json
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "promo-video" / "frames"
SKINS = {"adult": ROOT / "resources/assets", "chibi": ROOT / "resources/assets-chibi"}

# (形象, 片段 id, 高度)
CLIPS = [
    ("adult", "idle-loop", 960), ("adult", "idle-loop-2", 960),
    ("adult", "thinking-loop", 960), ("adult", "reading-loop", 960), ("adult", "writing-loop", 960),
    ("adult", "confirmation-loop", 960), ("adult", "complete-loop", 960), ("adult", "error-intro", 960),
    ("adult", "event-waiting-watch", 960), ("adult", "drowsy-loop", 960), ("adult", "event-drowsy-bubble", 960),
    ("adult", "thinking-intro", 960), ("adult", "confirmation-intro", 960), ("adult", "complete-intro", 960),
    ("adult", "thinking-to-reading", 960), ("adult", "reading-to-writing", 960), ("adult", "writing-to-thinking", 960),
    ("adult", "event-idle-tea", 960), ("adult", "event-idle-flower", 960), ("adult", "event-writing-ink", 960),
    ("adult", "event-confirmation-wave", 960), ("adult", "event-idle-gaze", 960), ("adult", "event-thinking-ponder", 960),
    ("chibi", "idle-loop", 960), ("chibi", "error-intro", 960), ("chibi", "complete-loop", 960),
    ("chibi", "event-idle-stretch", 480), ("chibi", "event-waiting-watch", 480),
]


# 剧情（tools/simulate.py 算出的 src/story.json）里她实际播到的片段
STORY = ROOT / "promo-video" / "src" / "story.json"
if STORY.exists():
    _have = {(sk, c) for sk, c, _h in CLIPS}
    for _c in json.loads(STORY.read_text(encoding="utf-8"))["clips"]:
        if ("adult", _c["clip"]) not in _have:
            CLIPS.append(("adult", _c["clip"], 960))
            _have.add(("adult", _c["clip"]))
    CLIPS = [(sk, c, 960 if sk == "adult" and any(x["clip"] == c for x in json.loads(STORY.read_text(encoding="utf-8"))["clips"]) else h)
             for sk, c, h in CLIPS]


def clip_file(skin: str, cid: str) -> Path:
    m = json.loads((SKINS[skin] / "manifest.json").read_text(encoding="utf-8"))
    for c in m["clips"]:
        if c["id"] == cid:
            return SKINS[skin] / c["file"]
    raise KeyError(f"{skin}/{cid}")


def main() -> None:
    index = {}
    for skin, cid, h in CLIPS:
        d = OUT / skin / cid
        im = Image.open(clip_file(skin, cid))
        w = round(h * im.width / im.height)
        n = im.n_frames
        first = d / "0000.webp"
        if not (d.exists() and len(list(d.glob("*.webp"))) == n and Image.open(first).height == h):
            d.mkdir(parents=True, exist_ok=True)
            for i in range(n):
                im.seek(i)
                im.convert("RGBA").resize((w, h), Image.LANCZOS).save(d / f"{i:04d}.webp", quality=88, method=4)
        index[f"{skin}/{cid}"] = {"n": n, "w": w, "h": h, "fps": 24}
        print(f"{skin}/{cid}: {n} 帧 {w}×{h}", flush=True)
    (OUT / "index.json").write_text(json.dumps(index, indent=1), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
