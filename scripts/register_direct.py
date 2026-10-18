"""把直达过渡登记到 manifest（type "direct"，from / to 是状态名）。已经登记的跳过；只登记已经生成了 webm 的，登记后再导出 AVIF。

    uv run python scripts/register_direct.py            # 原版
    uv run python scripts/register_direct.py chibi      # Q 版
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAIRS = [("thinking", "reading"), ("reading", "thinking"), ("thinking", "writing"),
         ("writing", "thinking"), ("reading", "writing"), ("writing", "reading")]

skin = sys.argv[1] if len(sys.argv) > 1 else ""
assets = ROOT / "resources" / (f"assets-{skin}" if skin else "assets")
path = assets / "manifest.json"
m = json.loads(path.read_text(encoding="utf-8"))
have = {c["id"] for c in m["clips"]}
added = []
for a, b in PAIRS:
    cid = f"{a}-to-{b}"
    file = f"videos/transitions/claude-girl-{cid}-transparent-9x16.avif"
    if cid in have or not (assets / file).with_suffix(".webm").exists():  # 先登记，再用 export_frames.py 导出 AVIF
        continue
    # 放在最后：路径长度相同时，引擎先找到的是原来经过枢纽的路线
    m["clips"].append({"id": cid, "type": "direct", "from": a, "to": b, "file": file})
    added.append(cid)
path.write_text(json.dumps(m, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"{path.relative_to(ROOT)}：新登记 {len(added)} 段 {added}")
