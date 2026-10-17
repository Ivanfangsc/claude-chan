"""把 ComfyUI 生成的 PNG 帧处理成透明 WebM（VP9 + Alpha），保证所有衔接处像素一致。

用 ComfyUI 自带的 Python 运行（需要 numpy、Pillow、SciPy、PyAV，ComfyUI 环境里都有）：

    D:/comfy/.venv/Scripts/python.exe scripts/comfy/finish.py loop writing        # 单段 L，或段 A + 段 B → loop
    D:/comfy/.venv/Scripts/python.exe scripts/comfy/finish.py transition hub-A-to-B
    加 --preview 只输出检查用的图片，不写视频

为什么不用 K0 原图直接替换首尾帧：模型生成的画面比输入图略软（VAE 重建会抹平线稿细节），
直接换成原图会在每次衔接时“闪一下变清晰”。所以每张关键帧只选一个**视频域的标准帧**
（第一次处理到它的片段在该端的生成帧），之后所有接触这张关键帧的片段，都把端点处的残差
在最靠近端点的 BLEND_FRAMES 帧内按余弦权重逐渐融入，端点与标准帧完全一致。残差主要是
细节和噪声，分摊到 8 帧里看不出来。标准帧保存在 CANON_DIR，所以处理顺序决定标准帧：
先处理 loop（定义各状态的 K0 和 K1），再处理过渡。

步骤：
1. 各段剪掉首尾多余的近乎静止帧，只保留 1 帧。
2. 端点对齐到标准帧（没有就用本段端点帧建立标准帧）。
3. loop：A 接 B，去掉 B 的第 1 帧（对齐后与 A 的末帧完全相同）；loop 首尾都是 K0 标准帧。
4. 从青色背景抠图（与 ffmpeg colorkey 相同的算法，键色从画面边缘估计），去除边缘青色溢色。
5. 补边到 774×1376（内容放在 (3, 16)），输出 24fps、VP9 + Alpha、无音频。
"""

import os
import argparse
import json
import sys
from pathlib import Path

import av
import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[2]
# 形象：环境变量 CLAUDE_GIRL_SKIN 为空是原版，chibi 是 Q 版（生成目录和素材目录都分开）
SKIN = os.environ.get("CLAUDE_GIRL_SKIN", "")
_SUFFIX = f"-{SKIN}" if SKIN else ""
GEN_DIR = Path(f"D:/comfy/ComfyUI/output/claude-girl-gen{_SUFFIX}")
CANON_DIR = GEN_DIR / "_canonical"
ASSETS = ROOT / "resources" / f"assets{_SUFFIX}" / "videos"
PREVIEW_DIR = ROOT / ".scratch" / "loop-preview"

GEN_W, GEN_H = 768, 1344
OUT_W, OUT_H = 774, 1376
PAD_X, PAD_Y = 3, 16
FPS = 24

BLEND_FRAMES = 8
SIMILARITY = 0.25  # 同旧流程 colorkey=...:0.25:0.04
BLEND = 0.04
STILL_RATIO = 0.25  # 相邻帧差 < 中位数 × 这个比例，视为近乎静止
CUT_RATIO = 12  # 相邻帧差 > 中位数 × 这个倍数，视为切镜头（模型偶尔会切到脸部特写）
DRIFT_LIMIT = 30  # 画面边缘的背景色偏离键色超过这个值，视为背景漂移（长片段会慢慢变灰）
EXIT_UNUSABLE = 3  # 片段不可用的退出码：batch.mjs 看到后会换种子重新生成


def check_usable(frames: list[np.ndarray], key: np.ndarray, name: str) -> None:
    """切镜头或背景漂移的片段没法用，直接以 EXIT_UNUSABLE 退出。"""
    diffs = [diff(a, b) for a, b in zip(frames, frames[1:])]
    median = max(0.2, float(np.median(diffs)))
    cuts = [i + 1 for i, d in enumerate(diffs) if d > CUT_RATIO * median]
    drift = 0.0
    for f in frames[:: max(1, len(frames) // 24)]:
        border = np.concatenate([f[:8].reshape(-1, 3), f[-8:].reshape(-1, 3), f[:, :8].reshape(-1, 3), f[:, -8:].reshape(-1, 3)])
        drift = max(drift, float(np.abs(np.median(border, axis=0) - key).max()))
    problems = []
    if cuts:
        problems.append(f"疑似切镜头：第 {cuts} 帧")
    if drift > DRIFT_LIMIT:
        problems.append(f"背景漂移：边缘颜色偏离键色 {drift:.0f}")
    if problems:
        print(f"✗ {name} 不可用：{'；'.join(problems)}", flush=True)
        sys.exit(EXIT_UNUSABLE)


# ---------- 读取 ----------

def load(job: str) -> tuple[list[np.ndarray], dict]:
    d = GEN_DIR / job
    files = sorted(d.glob("frame_*.png"))
    if not files:
        sys.exit(f"找不到 {d} 下的帧，先运行 node scripts/comfy/generate.mjs {job}")
    meta = json.loads((d / "job.json").read_text(encoding="utf-8"))
    return [np.asarray(Image.open(f).convert("RGB"), dtype=np.float32) for f in files], meta


def diff(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.abs(a[::8, ::8] - b[::8, ::8]).mean())


# ---------- 剪静止帧 ----------

def trim_still(frames: list[np.ndarray]) -> tuple[list[np.ndarray], int, int]:
    """首尾连续的近乎静止帧只保留 1 帧。返回剪后的帧和首、尾各剪掉的数量。"""
    diffs = [diff(a, b) for a, b in zip(frames, frames[1:])]
    threshold = max(0.3, float(np.median(diffs)) * STILL_RATIO)
    head = 0
    while head < len(diffs) and diffs[head] < threshold:
        head += 1
    tail = 0
    while tail < len(diffs) - head and diffs[len(diffs) - 1 - tail] < threshold:
        tail += 1
    return frames[head : len(frames) - tail], head, tail


# ---------- 标准帧与端点对齐 ----------

def canonical(name: str, fallback: np.ndarray) -> tuple[np.ndarray, bool]:
    """关键帧 name 的标准帧；还没有时用 fallback 建立。返回 (标准帧, 是否新建)。"""
    path = CANON_DIR / f"{name}.png"
    if path.exists():
        return np.asarray(Image.open(path).convert("RGB"), dtype=np.float32), False
    CANON_DIR.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.clip(fallback, 0, 255).round().astype(np.uint8)).save(path)
    return np.asarray(Image.open(path).convert("RGB"), dtype=np.float32), True


def align_end(frames: list[np.ndarray], target: np.ndarray, at_start: bool) -> float:
    """把端点帧对齐到 target：残差按余弦权重融入最靠近端点的 BLEND_FRAMES 帧。返回残差大小。"""
    idx = 0 if at_start else len(frames) - 1
    residual = target - frames[idx]
    size = diff(target, frames[idx])
    n = min(BLEND_FRAMES, len(frames) // 2)
    for i in range(n):
        w = 0.5 * (1 + np.cos(np.pi * i / n))  # i=0 → 1，逐渐降到接近 0
        j = i if at_start else len(frames) - 1 - i
        frames[j] = frames[j] + residual * w
    frames[idx] = target.copy()
    return size


def prepare(job: str, notes: dict) -> list[np.ndarray]:
    frames, meta = load(job)
    # 安静的 loop 和眨眼整段都近乎静止，按“首尾静止帧”剪会剪掉几乎全部
    frames, head, tail = (frames, 0, 0) if meta.get("noTrim") else trim_still(frames)
    info = {"trimmed": [head, tail]}
    for at_start, key in ((True, meta["first"]), (False, meta["last"])):
        target, created = canonical(key, frames[0 if at_start else -1])
        info[f"{'start' if at_start else 'end'}:{key}"] = "新建标准帧" if created else f"残差 {align_end(frames, target, at_start):.2f}"
    notes[job] = info
    return frames


# ---------- 抠图与输出 ----------

def estimate_key(frames: list[np.ndarray]) -> np.ndarray:
    samples = []
    for f in frames[:: max(1, len(frames) // 12)]:
        samples += [f[:8].reshape(-1, 3), f[-8:].reshape(-1, 3), f[:, :8].reshape(-1, 3), f[:, -8:].reshape(-1, 3)]
    return np.median(np.concatenate(samples), axis=0)


def key_out(frame: np.ndarray, key: np.ndarray) -> np.ndarray:
    """ffmpeg colorkey 的算法，再去掉边缘的青色溢色。返回补边后的 RGBA。"""
    rgb = np.clip(frame, 0, 255)
    dist = np.sqrt(((rgb - key) ** 2).sum(axis=2) / (3 * 255.0**2))
    alpha = np.clip((dist - SIMILARITY) / BLEND, 0, 1)
    edge = (alpha < 1) | ndimage.binary_dilation(alpha < 0.5, iterations=2)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    spill = np.clip(np.minimum(g, b) - r, 0, None) * edge
    rgb = rgb.copy()
    rgb[..., 1] -= spill * 0.8
    rgb[..., 2] -= spill * 0.8
    rgba = np.dstack([np.clip(rgb, 0, 255), alpha * 255]).round().astype(np.uint8)
    rgba[alpha == 0] = 0
    canvas = np.zeros((OUT_H, OUT_W, 4), np.uint8)
    canvas[PAD_Y : PAD_Y + GEN_H, PAD_X : PAD_X + GEN_W] = rgba
    return canvas


def encode(frames: list[np.ndarray], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with av.open(str(path), "w", format="webm") as out:
        stream = out.add_stream("libvpx-vp9", rate=FPS)
        stream.width, stream.height = OUT_W, OUT_H
        stream.pix_fmt = "yuva420p"
        stream.options = {"crf": "28", "b:v": "0", "auto-alt-ref": "0", "row-mt": "1", "deadline": "good", "cpu-used": "2"}
        for f in frames:
            for packet in stream.encode(av.VideoFrame.from_ndarray(f, format="rgba")):
                out.mux(packet)
        for packet in stream.encode():
            out.mux(packet)


def preview(name: str, keyed: list[np.ndarray], picks: dict[str, int]) -> None:
    """检查图：在灰色棋盘格上铺几帧；再输出一张头部的原尺寸特写看发丝边缘。"""
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    board = (np.indices((OUT_H, OUT_W)) // 24).sum(axis=0) % 2 * 60 + 160
    bg = np.dstack([board] * 3).astype(np.float32)
    tiles = []
    for i in picks.values():
        f = keyed[i].astype(np.float32)
        a = f[..., 3:] / 255
        tiles.append((bg * (1 - a) + f[..., :3] * a).astype(np.uint8)[::2, ::2])
    Image.fromarray(np.hstack(tiles)).save(PREVIEW_DIR / f"{name}-contact.png")
    Image.fromarray(keyed[len(keyed) // 2]).crop((230, 60, 630, 460)).save(PREVIEW_DIR / f"{name}-edge.png")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("kind", choices=["loop", "transition"])
    ap.add_argument("name", help="loop 的状态名，或过渡的文件名主体（如 hub-A-to-B、writing-hub-to-state）")
    ap.add_argument("--preview", action="store_true", help="只输出检查用的图片，不写视频")
    ap.add_argument("--segment", default="L", help="单段 loop 使用的任务后缀，默认 L（任务目录为 <状态>-<后缀>）")
    ap.add_argument("--job", help="直接指定任务目录名（随机事件如 e-idle-yawn，第二版过渡如 T-hub-A-to-B），优先于 --segment")
    ap.add_argument("--out", help="输出文件名（放在对应的 videos 子目录下），默认覆盖正式素材")
    args = ap.parse_args()

    notes: dict = {}
    single = args.job or f"{args.name}-{args.segment}"
    if args.kind == "loop" and (GEN_DIR / single).exists():
        # 单段 K0 → K0（loop 或随机事件）：两端都对齐到 K0 标准帧
        frames = prepare(single, notes)
        picks = {"first": 0, "1/4": len(frames) // 4, "1/2": len(frames) // 2, "3/4": 3 * len(frames) // 4, "last": len(frames) - 1}
        target = ASSETS / "loops" / f"claude-girl-loop-{args.name}-transparent-9x16.webm"
    elif args.kind == "loop":
        a = prepare(f"{args.name}-A", notes)
        b = prepare(f"{args.name}-B", notes)
        assert diff(a[-1], b[0]) < 1e-3 and diff(a[0], b[-1]) < 1e-3, "对齐后端点不一致"
        frames = a + b[1:]
        picks = {"first": 0, "join-1": len(a) - 2, "join": len(a) - 1, "join+1": len(a), "last": len(frames) - 1}
        target = ASSETS / "loops" / f"claude-girl-loop-{args.name}-transparent-9x16.webm"
    else:
        frames = prepare(args.job or f"t-{args.name}", notes)
        picks = {"first": 0, "1/4": len(frames) // 4, "1/2": len(frames) // 2, "3/4": 3 * len(frames) // 4, "last": len(frames) - 1}
        target = ASSETS / "transitions" / f"claude-girl-{args.name}-transparent-9x16.webm"

    if args.out:
        target = target.with_name(args.out)

    # 键色也只确定一次：衔接处像素相同的帧，抠出来的透明度也必须相同
    key_path = CANON_DIR / "key.json"
    if key_path.exists():
        key = np.array(json.loads(key_path.read_text()), dtype=np.float32)
    else:
        key = estimate_key(frames)
        key_path.write_text(json.dumps([float(x) for x in key]))
    check_usable(frames, key, args.name)
    print(json.dumps({"name": args.name, "frames": len(frames), "seconds": round(len(frames) / FPS, 2), "key_rgb": [round(float(x)) for x in key], **notes}, ensure_ascii=False))
    keyed = [key_out(f, key) for f in frames]
    preview(args.name, keyed, picks)
    if args.preview:
        return
    encode(keyed, target)
    print(f"已写入 {target.relative_to(ROOT)}（{target.stat().st_size // 1024} KB）")


if __name__ == "__main__":
    main()
