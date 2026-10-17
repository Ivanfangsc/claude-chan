"""检查 loop 素材：回文（倒放感）、静止帧、首尾是否与相邻片段对齐、速度突变。

    uv run python scripts/analyze_loop.py                          # 检查 manifest 里所有 loop 和随机事件
    uv run python scripts/analyze_loop.py 文件.webm [...]          # 检查指定文件（webm 或 avif）
        --as <状态>   新文件还没进 manifest 时，按哪个状态检查衔接
        --fps <n>     帧率（默认读 manifest，24）
        --json        输出原始数据

透明 VP9 用 libvpx 解码器读取（FFmpeg 自带的 vp9 解码器会丢掉透明通道）。
有问题时退出码为 1。
"""

from __future__ import annotations

import os
import argparse
import json
import math
import sys
from pathlib import Path

import av
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
# 形象：环境变量 CLAUDE_GIRL_SKIN 为空是原版，chibi 是 Q 版（生成目录和素材目录都分开）
SKIN = os.environ.get("CLAUDE_GIRL_SKIN", "")
_SUFFIX = f"-{SKIN}" if SKIN else ""
ASSETS = ROOT / "resources" / f"assets{_SUFFIX}"
W, H = 129, 229  # 缩小到约 1/6 分辨率再比较，足够反映动作，也快

# 画面差异是缩小后 RGBA 每通道的平均绝对差（0–255）。同一段视频内的编码噪声约 0.5，
# 两段分别编码的视频之间约 1.4，所以跳变类检查都有绝对下限，避免把噪声当成问题。
JUMP_FLOOR = 1.5
JOIN_FLOOR = 2.0


def decode(path: Path) -> list[np.ndarray]:
    """读出所有帧（缩小后的 RGBA float32）。"""
    if path.suffix == ".avif":
        im = Image.open(path)
        out = []
        for i in range(getattr(im, "n_frames", 1)):
            im.seek(i)
            out.append(np.asarray(im.convert("RGBA").resize((W, H), Image.BILINEAR), dtype=np.float32))
        return out
    frames = []
    with av.open(str(path)) as container:
        decoder = av.CodecContext.create("libvpx-vp9", "r")
        for packet in container.demux(container.streams.video[0]):
            for frame in decoder.decode(packet):
                rgba = Image.fromarray(frame.to_ndarray(format="rgba"), "RGBA").resize((W, H), Image.BILINEAR)
                frames.append(np.asarray(rgba, dtype=np.float32))
    return frames


def diff(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.abs(a - b).mean())


def jerk(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
    return float(np.abs(a - 2 * b + c).mean())


def master(path: str) -> Path:
    """manifest 里写的是 .avif；检测用生成时的原始 webm（没有二次压缩）。"""
    p = ASSETS / path
    return p.with_suffix(".webm") if p.with_suffix(".webm").exists() else p


def neighbors(manifest: dict, file: Path, as_state: str | None) -> list[tuple[str, Path, str]]:
    """与这段 loop 衔接的片段：进入它的片段（取末帧）和离开它的片段（取首帧）。"""
    state = as_state or next(
        (c["state"] for c in manifest["clips"] if c["type"] in ("loop", "event") and Path(c["file"]).stem == file.stem),
        None,
    )
    d = manifest["states"].get(state or "")
    if not d:
        return []
    out = []
    for c in manifest["clips"]:
        if d.get("atHub"):
            if c["type"] in ("outro", "transition") and c.get("to") == d["hub"]:
                out.append((f"{c['id']} 末帧", master(c["file"]), "last"))
            if c["type"] in ("intro", "transition") and c.get("from") == d["hub"]:
                out.append((f"{c['id']} 首帧", master(c["file"]), "first"))
        elif c.get("state") == state:
            if c["type"] == "intro":
                out.append((f"{c['id']} 末帧", master(c["file"]), "last"))
            if c["type"] == "outro":
                out.append((f"{c['id']} 首帧", master(c["file"]), "first"))
    return out


def analyze(file: Path, nbs: list[tuple[str, Path, str]]) -> dict:
    f = decode(file)
    n = len(f)
    if n < 8:
        return {"file": str(file), "frames": n, "error": "帧数太少"}
    cons = [diff(f[i], f[i + 1]) for i in range(n - 1)]
    mean_motion = float(np.mean(cons))
    still = max(0.03, 0.25 * float(np.median(cons)))

    # 连续静止帧：相邻差低于阈值的连续区间（至少 3 帧画面几乎一样）
    runs, i = [], 0
    while i < len(cons):
        if cons[i] >= still:
            i += 1
            continue
        j = i
        while j + 1 < len(cons) and cons[j + 1] < still:
            j += 1
        if j - i + 1 >= 2:
            runs.append((i, j + 1))
        i = j + 1

    # 整体回文：镜像帧对 f[axis-d] / f[axis+d] 与同样间隔的正向帧对比较，在中间一半范围内找最佳对称轴
    travel_cache: dict[int, float] = {}

    def travel(d: int) -> float:
        if d not in travel_cache:
            step = max(1, (n - d) // 24)
            travel_cache[d] = float(np.mean([diff(f[j], f[j + d]) for j in range(0, n - d, step)]))
        return travel_cache[d]

    best_axis, best_ratio = 0.0, math.inf
    for a2 in range(n // 2, 3 * n // 2 + 1):
        axis = a2 / 2
        m = t = 0.0
        k = 0
        d = 0.5 if axis % 1 else 1.0
        while axis - d >= 0 and axis + d <= n - 1:
            m += diff(f[int(axis - d)], f[int(axis + d)])
            t += travel(int(2 * d))
            d += 2
            k += 1
        if k >= n / 8 and t > 0 and m / t < best_ratio:
            best_axis, best_ratio = axis, m / t

    jerks = [jerk(f[i - 1], f[i], f[i + 1]) for i in range(1, n - 1)]
    median_jerk = max(1e-6, float(np.median(jerks)))
    spikes = [(i + 1, j / median_jerk) for i, j in enumerate(jerks) if j / median_jerk > 4 and j > JUMP_FLOOR]

    joins = []
    for label, path, which in nbs:
        try:
            frames = decode(path)
            edge = frames[-1] if which == "last" else frames[0]
            joins.append((label, diff(edge, f[0] if which == "last" else f[-1])))
        except Exception as e:  # noqa: BLE001
            joins.append((label, f"读取失败：{e}"))

    return {
        "file": str(file),
        "frames": n,
        "mean_motion": mean_motion,
        "still_runs": runs,
        "mirror_axis": best_axis,
        "mirror_ratio": best_ratio,
        "first_last": diff(f[0], f[-1]),
        "seam_jerk": jerk(f[-2], f[0], f[1]),
        "median_jerk": median_jerk,
        "spikes": spikes,
        "joins": joins,
    }


def report(r: dict, fps: float) -> int:
    ms = lambda frames: f"{round(frames / fps * 1000)}ms"  # noqa: E731
    print(f"\n{Path(r['file']).name}  {r['frames']} 帧 / {r['frames'] / fps:.2f}s，平均每帧运动量 {r.get('mean_motion', 0):.2f}")
    if "error" in r:
        print(f"  ✗ {r['error']}")
        return 1
    problems = 0

    def warn(msg: str) -> None:
        nonlocal problems
        problems += 1
        print(f"  ⚠ {msg}")

    if r["mirror_ratio"] < 0.5:
        warn(f"回文结构（后半段是前半段倒放）：以第 {r['mirror_axis']} 帧为轴，镜像帧对的差异只有正常位移的 {r['mirror_ratio'] * 100:.0f}%")
    else:
        print(f"  ✓ 没有整体回文（镜像差 / 正常位移 = {r['mirror_ratio'] * 100:.0f}%）")
    n = r["frames"]
    edge = [(a, b) for a, b in r["still_runs"] if a <= 1 or b >= n - 2]
    long_mid = [(a, b) for a, b in r["still_runs"] if (a, b) not in edge and b - a + 1 >= fps / 2]
    if edge:
        warn("首尾附近有近乎静止的帧，循环时会在关键帧上停顿：" + "，".join(f"第 {a}–{b} 帧（{ms(b - a + 1)}）" for a, b in edge))
    else:
        print("  ✓ 首尾没有多余的静止帧")
    if long_mid:
        warn("中间有较长的静止段：" + "，".join(f"第 {a}–{b} 帧（{ms(b - a + 1)}）" for a, b in long_mid))
    jump_limit = max(JUMP_FLOOR, 2 * r["mean_motion"])
    if r["first_last"] > jump_limit:
        warn(f"首帧和末帧不一致（差异 {r['first_last']:.2f}，上限 {jump_limit:.2f}），循环时会跳一下")
    else:
        print(f"  ✓ 首帧与末帧一致（差异 {r['first_last']:.2f}）")
    join_limit = max(JOIN_FLOOR, 2 * r["mean_motion"])
    bad = [(label, v) for label, v in r["joins"] if isinstance(v, str) or v > join_limit]
    if not r["joins"]:
        print("    （不在 manifest 里，跳过与相邻片段的衔接检查；可用 --as <状态> 指定）")
    elif bad:
        warn("与相邻片段衔接处有跳变：" + "，".join(f"{label} {v if isinstance(v, str) else f'差异 {v:.2f}'}" for label, v in bad))
    else:
        print(f"  ✓ 与 {len(r['joins'])} 个相邻片段衔接一致（最大差异 {max(v for _, v in r['joins']):.2f}）")
    if r["seam_jerk"] > 3 * r["median_jerk"] and r["seam_jerk"] > JUMP_FLOOR:
        warn(f"循环接缝处速度突变（加速度为中位数的 {r['seam_jerk'] / r['median_jerk']:.1f} 倍）")
    else:
        print("  ✓ 循环接缝处速度连续")
    if r["spikes"]:
        warn("速度突变点（可能是切镜头或拼接处）：" + "，".join(f"第 {i} 帧 ×{x:.1f}" for i, x in r["spikes"]))
    return problems


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*")
    ap.add_argument("--as", dest="as_state")
    ap.add_argument("--fps", type=float)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    manifest = json.loads((ASSETS / "manifest.json").read_text(encoding="utf-8"))
    fps = args.fps or manifest.get("fps", 24)
    files = [Path(f).resolve() for f in args.files] or [
        master(c["file"]) for c in manifest["clips"] if c["type"] in ("loop", "event")
    ]
    problems = 0
    results = []
    for file in files:
        if not file.exists():
            print(f"找不到文件：{file}", file=sys.stderr)
            sys.exit(2)
        r = analyze(file, neighbors(manifest, file, args.as_state))
        results.append(r)
        if not args.json:
            problems += report(r, fps)
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2, default=str))
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
