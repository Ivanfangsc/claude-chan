"""把生成的透明 VP9 webm（原始文件）转成 manifest 里登记的动画 AVIF（桌宠实际播放的文件）。

桌宠用 Pillow 逐帧解码动画 AVIF。webm 是 scripts/comfy/finish.py 的输出，保留下来作为原始文件，
以后可以按别的宽度重新导出。
选 AVIF 而不是 WebP：同一段过渡 AVIF 约 1.3 MB（webm 1.7 MB，WebP 6–9 MB），
每帧解码约 6 ms（WebP 约 14 ms），画质误差也最小。

需要 PyAV（带 libvpx-vp9 解码器）和 Pillow，用 ComfyUI 的 Python 运行：

    D:/comfy/.venv/Scripts/python.exe scripts/export_frames.py          # 只转换比 avif 新的 webm
    D:/comfy/.venv/Scripts/python.exe scripts/export_frames.py --all    # 全部重新转换
        --mask        只重新生成 hitmask.png
        --retime      loop 做首尾提速（旧的 K0→K0 loop 用；持续动作的 loop 不需要，默认关闭）

loop 首尾提速：生成模型在首尾帧约束附近会明显减速（接近关键帧时越来越慢，离开时慢慢加速），
每轮都这样就很有“循环感”。导出 loop 时，从首尾往里连续比中段慢的那一段（最多各 45%）加快播放：
不拉成匀速（匀速冲到关键帧再折返反而像停顿），而是按 (中段速度 / 当前速度)^0.5 提速，
保留缓入缓出的形状、只是缩短；提速倍数再平滑一下，小数位置用相邻两帧混合，避免跳帧不均。
首帧、末帧保持不变，中段不动。
"""

import os
import argparse
import json
import sys
import time
from pathlib import Path

import av
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
# 形象：环境变量 CLAUDE_GIRL_SKIN 为空是原版，chibi 是 Q 版（生成目录和素材目录都分开）
SKIN = os.environ.get("CLAUDE_GIRL_SKIN", "")
_SUFFIX = f"-{SKIN}" if SKIN else ""
ASSETS = ROOT / "resources" / f"assets{_SUFFIX}"
QUALITY = 50  # 0–100；50 时体积约为 70 的一半，与原帧的平均误差约 2.9（0–255），桌宠尺寸下看不出区别
SPEED = 6  # libavif 编码速度 0–10，越大越快、压缩率略低
# 输出宽度。桌宠默认宽度约为屏幕的 1/4（1080p 屏约 480 像素），540 已经够清晰；
# 解码量只有原尺寸 774 的一半，CPU 占用明显下降。把桌宠放得很大时可以用 --width 774 导出原尺寸。
DEFAULT_WIDTH = 540
GRID_W, GRID_H = 64, 114  # 点击网格，与 claude_girl/window.py 一致
RETIME_EDGE = 0.45  # 提速范围从首尾往里最多延伸多少比例
RETIME_CAP = 4.0  # 最多提速几倍
RETIME_GAMMA = 0.5  # 提速倍数 = (中段速度 / 当前速度)^GAMMA；1 为拉成匀速，0 为不提速


def retime(frames: list[Image.Image]) -> list[float]:
    """首尾提速后每个输出帧对应的原帧位置（可以是小数，包含首帧 0 和末帧）。"""
    small = [np.asarray(f.resize((129, 229), Image.BILINEAR), dtype=np.float32) for f in frames]
    d = [float(np.abs(a - b).mean()) for a, b in zip(small, small[1:])]
    n = len(d)
    v = float(np.median(d[n // 4 : 3 * n // 4]))
    if n < 8 or v <= 0:
        return [float(i) for i in range(len(frames))]
    # 提速范围：从首尾往里，平滑后的速度一直低于中段的那一段
    smooth = np.convolve(d, np.ones(5) / 5, mode="same")
    limit = int(RETIME_EDGE * n)
    head = next((i for i in range(limit) if smooth[i] >= v), limit)
    tail = next((i for i in range(limit) if smooth[n - 1 - i] >= v), limit)
    # 每个帧间隔在输出里占多少“帧时间”：提速范围内按速度缩短，其余为 1
    w = np.array(
        [max(1 / RETIME_CAP, min(1.0, x / v) ** RETIME_GAMMA) if i < head or i >= n - tail else 1.0 for i, x in enumerate(d)]
    )
    # 平滑提速倍数，让播放速度逐渐变化（两端用边缘值填充）
    w = np.convolve(np.pad(w, 4, mode="edge"), np.ones(9) / 9, mode="valid")
    t = np.concatenate([[0.0], np.cumsum(w)])
    count = max(1, round(t[-1]))
    return [float(np.interp(k * t[-1] / count, t, np.arange(n + 1))) for k in range(count + 1)]


def sample(frames: list[Image.Image], pos: float) -> Image.Image:
    """取小数位置的帧：相邻两帧混合（提速处动作很小，混合看不出重影）。"""
    i = min(int(pos), len(frames) - 2)
    a = pos - i
    if a < 0.05:
        return frames[i]
    if a > 0.95:
        return frames[i + 1]
    return Image.blend(frames[i], frames[i + 1], a)


def decode_rgba(path: Path) -> list[Image.Image]:
    """用 libvpx 解码器读出带透明通道的帧（FFmpeg 自带的 vp9 解码器会丢掉透明通道）。"""
    frames: list[Image.Image] = []
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        decoder = av.CodecContext.create("libvpx-vp9", "r")
        for packet in container.demux(stream):
            for frame in decoder.decode(packet):
                frames.append(Image.fromarray(frame.to_ndarray(format="rgba"), "RGBA"))
    return frames


def export(webm: Path, fps: float, width: int = DEFAULT_WIDTH, speedup_edges: bool = False) -> Path:
    target = webm.with_suffix(".avif")
    frames = decode_rgba(webm)
    if speedup_edges:
        positions = retime(frames)
        print(f"  首尾提速：{len(frames)} → {len(positions)} 帧")
        frames = [sample(frames, p) for p in positions]
    if frames and frames[0].width != width:
        height = round(frames[0].height * width / frames[0].width)
        frames = [f.resize((width, height), Image.LANCZOS) for f in frames]
    frames[0].save(
        target,
        save_all=True,
        append_images=frames[1:],
        duration=round(1000 / fps),
        loop=0,
        quality=QUALITY,
        speed=SPEED,
    )
    return target


def write_hit_mask(manifest: dict) -> Path:
    """所有片段所有帧（和关键帧）不透明区域的并集，缩到点击网格大小，存成 hitmask.png。
    桌宠用它做点击穿透和窗口形状：只用关键帧的话，随机事件里动作大的部分会被裁掉。"""
    union = np.zeros((GRID_H, GRID_W), dtype=np.uint8)
    paths = [ASSETS / c["file"] for c in manifest["clips"]]
    paths += [ASSETS / s["keyframe"] for s in manifest["states"].values() if s.get("keyframe")]
    started = time.time()
    missing = [p for p in paths if not p.exists()]
    if missing:
        print(f"hitmask.png：跳过 {len(missing)} 个还没有的文件（补齐后重新运行 --mask）")
    for path in paths:
        if not path.exists():
            continue
        im = Image.open(path)
        for i in range(getattr(im, "n_frames", 1)):
            im.seek(i)
            alpha = im.convert("RGBA").getchannel("A").resize((GRID_W, GRID_H), Image.BILINEAR)
            np.maximum(union, np.asarray(alpha), out=union)
    target = ASSETS / "hitmask.png"
    mask = Image.new("RGBA", (GRID_W, GRID_H), (255, 255, 255, 0))
    mask.putalpha(Image.fromarray(union))
    mask.save(target)
    print(f"hitmask.png：{len(paths)} 个文件，{time.time() - started:.0f}s")
    return target


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="全部重新转换")
    ap.add_argument("--width", type=int, default=DEFAULT_WIDTH, help=f"输出宽度，默认 {DEFAULT_WIDTH}")
    ap.add_argument("--mask", action="store_true", help="只重新生成 hitmask.png")
    ap.add_argument("--retime", action="store_true", help="loop 做首尾提速（旧的 K0→K0 loop 用）")
    args = ap.parse_args()

    manifest = json.loads((ASSETS / "manifest.json").read_text(encoding="utf-8"))
    if args.mask:
        write_hit_mask(manifest)
        return
    total = 0
    for clip in manifest["clips"]:
        target = ASSETS / clip["file"]
        webm = target.with_suffix(".webm")
        if not webm.exists():
            print(f"缺少原始文件 {webm.relative_to(ASSETS)}", file=sys.stderr)
            continue
        if not args.all and target.exists() and target.stat().st_mtime >= webm.stat().st_mtime:
            continue
        started = time.time()
        export(webm, manifest["fps"], args.width, clip["type"] == "loop" and args.retime)
        size = target.stat().st_size
        total += size
        print(f"{target.relative_to(ASSETS)}  {size // 1024} KB  {time.time() - started:.1f}s")
    if total:
        print(f"共写入 {total // 1024 // 1024} MB")
        write_hit_mask(manifest)


if __name__ == "__main__":
    main()
