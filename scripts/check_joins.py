"""检查所有可能连着播放的片段之间的衔接，以及每个片段内部的跳变。用实际播放的 AVIF。

    uv run python scripts/check_joins.py                         # 原版
    $env:CLAUDE_GIRL_SKIN="chibi"; uv run python scripts/check_joins.py   # Q 版

衔接：前一段的末帧到后一段的第 2 帧（播放时跳过相同的首帧）这一步，和两侧的步长比，以及加速度、颜色差。
内部跳变：相邻帧差异超过中位数 4 倍且大于 1.5 的位置（切镜头、画面突然挪动）。
"""
import sys
from pathlib import Path
import numpy as np
sys.path.insert(0, "scripts")
from analyze_loop import decode, diff, jerk, ASSETS as A
from claude_chan.engine.manifest import Manifest
from claude_chan.engine.graph import Graph

m = Manifest.load(A / "manifest.json")
m.clips[:] = [c for c in m.clips if (A / c.file).exists()]
g = Graph(m)
frames = {c.id: decode(A / c.file) for c in m.clips}
clips = {c.id: c for c in m.clips}

start_node = g.start_node

# 两段能连着播：前一段的结束节点 == 后一段的起始节点
pairs = [(a, b) for a in m.clips for b in m.clips if g.end_node(a) == start_node(b)
         and not (a.type == "event" and b.type == "event")]
color = lambda f: f[..., :3][f[..., 3] > 128].mean(axis=0)
rows = []
for a, b in pairs:
    fa, fb = frames[a.id], frames[b.id]
    # 播放时跳过 b 的首帧（与 a 的末帧相同）
    seq = fa[-4:] + fb[1:5]
    steps = [diff(x, y) for x, y in zip(seq, seq[1:])]
    j = 3  # a[-1] → b[1]
    around = np.median(steps[:j] + steps[j + 1:])
    jump = steps[j] / max(around, 0.3)
    jerks = [jerk(seq[k - 1], seq[k], seq[k + 1]) for k in range(1, len(seq) - 1)]
    jk = max(jerks[2], jerks[3]) / max(np.median(jerks), 0.3)
    dc = float(np.abs(color(fa[-1]) - color(fb[1])).max())
    rows.append((max(jump, jk / 2), a.id, b.id, steps[j], around, jump, jk, dc))
rows.sort(reverse=True)
print(f"{len(pairs)} 种衔接；按可疑程度排序的前 15 个（跳变=衔接处一步 / 两侧中位数，加速度=相对中位数）：")
for r in rows[:15]:
    print(f"  {r[1]:26} → {r[2]:26} 一步 {r[3]:.2f}（两侧 {r[4]:.2f}，×{r[5]:.1f}）加速度 ×{r[6]:.1f} 颜色差 {r[7]:.1f}")
print("\n片段内部的跳变（相邻帧差异超过中位数 4 倍且 > 1.5）：")
for c in m.clips:
    f = frames[c.id]
    d = [diff(x, y) for x, y in zip(f, f[1:])]
    med = float(np.median(d))
    bad = [(i, x / med) for i, x in enumerate(d) if x > 4 * med and x > 1.5]
    if bad:
        print(f"  {c.id:26} " + "，".join(f"第 {i} 帧 ×{r:.1f}" for i, r in bad[:6]))
