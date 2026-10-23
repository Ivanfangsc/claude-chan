"""照原版的 manifest 给新形象生成一份：结构、片段、事件的概率和冷却都和原版一样，
关键帧换成新形象自己的（claude-girl-<形象>-*.png），只登记新形象里已经生成了视频（webm）的片段。

    uv run python scripts/make_skin_manifest.py maid
    $env:CLAUDE_GIRL_SKIN="maid"; D:/comfy/.venv/Scripts/python.exe scripts/export_frames.py   # 再导出 AVIF

生成不了的片段（比如某个随机动作连续失败）不登记，引擎就当它不存在；缺 loop、intro / outro 时 manifest 校验会在日志里报出来。
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
skin = sys.argv[1]
src = json.loads((ROOT / "resources/assets/manifest.json").read_text(encoding="utf-8"))
assets = ROOT / "resources" / f"assets-{skin}"


def keyframe(path: str) -> str:
    return path.replace("keyframes/claude-girl-", f"keyframes/claude-girl-{skin}-")


for hub in src["hubs"].values():
    hub["keyframe"] = keyframe(hub["keyframe"])
for state in src["states"].values():
    if state.get("keyframe"):
        state["keyframe"] = keyframe(state["keyframe"])
missing_kf = [p for p in [h["keyframe"] for h in src["hubs"].values()] + [s["keyframe"] for s in src["states"].values() if s.get("keyframe")]
              if not (assets / p).exists()]
kept, dropped = [], []
for c in src["clips"]:
    (kept if (assets / c["file"]).with_suffix(".webm").exists() else dropped).append(c)
src["clips"] = kept
src.pop("switch", None)
(assets / "manifest.json").write_text(json.dumps(src, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"resources/assets-{skin}/manifest.json：登记 {len(kept)} 段，缺 {len(dropped)} 段")
for c in dropped:
    print(f"  缺：{c['id']}（{c['file']}）")
for p in missing_kf:
    print(f"  缺关键帧：{p}")
