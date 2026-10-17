"""把 <状态>-M（关键帧锚在中间）和 <状态>-MB（接缝的过渡）拼成一圈持续动作的 loop，写到任务 <状态>-ML。

    uv run python scripts/comfy/assemble_loop.py idle
    D:/comfy/.venv/Scripts/python.exe scripts/comfy/finish.py loop idle --job idle-ML --out claude-girl-loop-idle-sway-transparent-9x16.webm

    uv run python scripts/comfy/assemble_loop.py idle --blink 2    # 把眨眼片段 idle-MK2 拼回 idle-ML，得到任务 idle-MLK2
    uv run python scripts/comfy/assemble_loop.py --insert idle-yawn  # 把 E-idle-yawn 插进 idle-ML，得到任务 E-idle-yawn-L

MB 开头的 GUIDE_LEN 帧对应 M 里靠后的一段，结尾的 GUIDE_LEN 帧对应 M 里靠前的一段。
在两段重叠的范围里各找一个跳变最小的接缝点，从 M 切到 MB、再从 MB 切回 M。
最后把这一圈转到从关键帧（M 的第 MID_AT 帧）开始、回到关键帧结束，这样还能和过渡、事件衔接。
"""

from __future__ import annotations

import os
import json
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image

# 形象：环境变量 CLAUDE_GIRL_SKIN 为空是原版，chibi 是 Q 版（生成目录和素材目录都分开）
SKIN = os.environ.get("CLAUDE_GIRL_SKIN", "")
_SUFFIX = f"-{SKIN}" if SKIN else ""
GEN_DIR = Path(f"D:/comfy/ComfyUI/output/claude-girl-gen{_SUFFIX}")
# 与 jobs.mjs 保持一致
MID_AT = 61
GUIDE_LEN = 22
LOOP_SPAN = 45
KEYFRAME = {"idle": "hub-A-approved", "hubB": "hub-B-approved", "confirmation": "waiting-confirmation"}  # 其余状态的关键帧与状态同名
BLINK_VARIANTS = {2: 10, 3: 60}  # 与 jobs.mjs 的 BLINK_VARIANTS 一致


def frames(job: str) -> list[Path]:
    files = sorted((GEN_DIR / job).glob("frame_*.png"))
    if not files:
        sys.exit(f"找不到 {job} 的帧")
    return files


def small(path: Path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("RGB").resize((128, 224)), dtype=np.float32)


def diff(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.abs(a - b).mean())


def write_job(state: str, name: str, seq: list[Path], out_name: str) -> None:
    out = GEN_DIR / name
    if out.exists():
        shutil.rmtree(out)
    out.mkdir()
    for i, f in enumerate(seq):
        shutil.copy(f, out / f"frame_{i + 1:05d}_.png")
    key = KEYFRAME.get(state, state)
    (out / "job.json").write_text(json.dumps({
        "name": name, "state": state, "segment": name.split("-", 1)[1], "first": key, "last": key, "noTrim": True,
        "frames": len(seq), "out": out_name,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{name}：{len(seq)} 帧（{len(seq) / 24:.2f}s）")


def blink(state: str, n: int) -> None:
    """眨眼变体：ML 的 [start, start+len) 换成 MK<n>，在两端引导重叠的范围里各找跳变最小的接缝。"""
    loop_files, gen_files = frames(f"{state}-ML"), frames(f"{state}-MK{n}")
    loop = [small(f) for f in loop_files]
    gen = [small(f) for f in gen_files]
    start, g = BLINK_VARIANTS[n], len(gen_files)
    # loop[start + j] ≈ gen[j]（开头的引导），loop[start + g - GUIDE_LEN + i] ≈ gen[g - GUIDE_LEN + i]（结尾的引导）
    j = min(range(1, GUIDE_LEN), key=lambda j: diff(loop[start + j - 1], gen[j]))
    i = min(range(g - GUIDE_LEN, g - 1), key=lambda i: diff(gen[i], loop[start + i + 1]))
    print(f"接缝 loop[{start + j - 1}]→MK[{j}] 差异 {diff(loop[start + j - 1], gen[j]):.2f}，"
          f"MK[{i}]→loop[{start + i + 1}] 差异 {diff(gen[i], loop[start + i + 1]):.2f}")
    seq = loop_files[: start + j] + gen_files[j : i + 1] + loop_files[start + i + 1 :]
    write_job(state, f"{state}-MLK{n}", seq, f"claude-girl-loop-{state}-sway-{n}-transparent-9x16.webm")


def insert(event: str) -> None:
    """插入式随机动作：E-<事件> 的两端分别锚住 loop 第 at 帧之前和之后的 22 帧，把它插进 loop。"""
    job = f"E-{event}"
    meta = json.loads((GEN_DIR / job / "job.json").read_text(encoding="utf-8"))
    state, at = meta["state"], meta["insertAt"]
    loop_files, gen_files = frames(f"{state}-ML"), frames(job)
    loop = [small(f) for f in loop_files]
    gen = [small(f) for f in gen_files]
    g = len(gen)
    head0, tail0 = at - GUIDE_LEN + 1, g - GUIDE_LEN  # gen[k] ≈ loop[head0 + k]；gen[tail0 + k] ≈ loop[at + 1 + k]
    # 从 loop 切到 gen：loop[head0 + j - 1] 之后接 gen[j]
    j = min(range(1, GUIDE_LEN), key=lambda j: diff(loop[head0 + j - 1], gen[j]))
    # 从 gen 切回 loop：gen[tail0 + k] 之后接 loop[at + 2 + k]
    k = min(range(0, GUIDE_LEN - 1), key=lambda k: diff(gen[tail0 + k], loop[at + 2 + k]))
    print(f"接缝 loop[{head0 + j - 1}]→E[{j}] 差异 {diff(loop[head0 + j - 1], gen[j]):.2f}，"
          f"E[{tail0 + k}]→loop[{at + 2 + k}] 差异 {diff(gen[tail0 + k], loop[at + 2 + k]):.2f}")
    seq = loop_files[: head0 + j] + gen_files[j : tail0 + k + 1] + loop_files[at + 2 + k :]
    write_job(state, f"{job}-L", seq, f"claude-girl-event-{event}-sway-transparent-9x16.webm")


def main() -> None:
    if sys.argv[1] == "--insert":
        insert(sys.argv[2])
        return
    state = sys.argv[1]
    if "--blink" in sys.argv:
        blink(state, int(sys.argv[sys.argv.index("--blink") + 1]))
        return
    m_files, b_files = frames(f"{state}-M"), frames(f"{state}-MB")
    m = [small(f) for f in m_files]
    b = [small(f) for f in b_files]
    speed = float(np.median([diff(x, y) for x, y in zip(m, m[1:])]))
    a0, b0 = MID_AT - LOOP_SPAN, MID_AT + LOOP_SPAN
    head_start = b0 - GUIDE_LEN + 1  # MB[j] ≈ M[head_start + j]
    tail_at = len(b) - GUIDE_LEN  # MB[tail_at + i] ≈ M[a0 + i]

    # M → MB：M[x] 之后接 MB[x - head_start + 1]
    out_x = min(range(head_start + 1, b0), key=lambda x: diff(m[x], b[x - head_start + 1]))
    # MB → M：MB[tail_at + i] 之后接 M[a0 + i + 1]
    in_i = min(range(0, GUIDE_LEN - 1), key=lambda i: diff(b[tail_at + i], m[a0 + i + 1]))
    j1, j2 = out_x - head_start + 1, tail_at + in_i
    print(f"中段速度 {speed:.2f}；接缝 M[{out_x}]→MB[{j1}] 差异 {diff(m[out_x], b[j1]):.2f}，"
          f"MB[{j2}]→M[{a0 + in_i + 1}] 差异 {diff(b[j2], m[a0 + in_i + 1]):.2f}")

    seq = m_files[MID_AT : out_x + 1] + b_files[j1 : j2 + 1] + m_files[a0 + in_i + 1 : MID_AT + 1]
    write_job(state, f"{state}-ML", seq, f"claude-girl-loop-{state}-sway-transparent-9x16.webm")


if __name__ == "__main__":
    main()
