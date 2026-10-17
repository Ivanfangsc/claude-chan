"""把 Qwen Image 编辑出的关键帧候选放进素材：对齐到参考关键帧，存青色版（视频生成用）和透明版（桌宠用）。

    uv run python scripts/comfy/place_keyframe.py <候选图> <关键帧名> [--skin chibi] [--ref <参考关键帧名>] [--no-align]

- 对齐：以画面下部的书堆（静止的道具）为准，平移、缩放到和参考关键帧一致。编辑模型偶尔会把人物挪动或缩放几个百分点，
  关键帧之间对不齐的话，过渡时整个画面会突然挪一下（error-v2 就是这样）。
- 青色版：ComfyUI input 下的 claude-girl-[<形象>-]<名字>-cyan-9x16.png
- 透明版：resources/assets[-<形象>]/keyframes/claude-girl-[<形象>-]<名字>-transparent-9x16.png
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
INPUT = Path("D:/comfy/ComfyUI/input")
KEY = np.array([0, 184, 212], dtype=np.float32)  # 青色背景
SIZE = (1026, 1824)  # 关键帧画布（和原版一致）


def mask_of(im: Image.Image) -> np.ndarray:
    a = np.asarray(im.convert("RGB"), dtype=np.float32)
    return np.sqrt(((a - KEY) ** 2).sum(axis=2)) > 60


def books_rect(ref: np.ndarray) -> tuple[int, int, int, int]:
    """参考图里书堆的范围：画面下部 35% 里偏棕色（R > G > B）的像素。"""
    h = ref.shape[0]
    r, g, b = ref[..., 0], ref[..., 1], ref[..., 2]
    brown = (r > g + 12) & (g > b + 8) & (r < 200) & (r > 50)
    brown[: int(h * 0.65)] = False
    ys, xs = np.where(brown)
    return int(np.percentile(xs, 3)), int(np.percentile(ys, 3)), int(np.percentile(xs, 97)), int(np.percentile(ys, 97))


def align(im: Image.Image, ref: Image.Image, lower: float = 1.0) -> Image.Image:
    """以书堆为模板，搜索让候选图的书堆和参考图重合的平移和缩放（±3%）。
    书堆是静止的道具；按人物轮廓对齐不可靠（收腿、裙摆垂到书堆上都会改变轮廓）。"""
    im = im.convert("RGB").resize(SIZE, Image.LANCZOS)
    ref_a = np.asarray(ref.convert("RGB").resize(SIZE, Image.LANCZOS), dtype=np.float32)
    x0, y0, x1, y1 = books_rect(ref_a)
    y0 = round(y1 - lower * (y1 - y0))  # 只用书堆下面这一部分（上面被腿或裙摆挡住时）
    k = 4  # 在 1/4 分辨率上粗搜，再在原分辨率上细搜
    patch = ref_a[y0:y1, x0:x1]
    best = (math.inf, 1.0, 0, 0)
    for s in (0.97, 0.98, 0.99, 1.0, 1.01, 1.02, 1.03):
        scaled = np.asarray(im.resize((round(SIZE[0] * s), round(SIZE[1] * s)), Image.BILINEAR), dtype=np.float32)
        # 书堆在缩放后图里的位置大约是 (x0*s, y0*s)；偏移 (dx, dy) 表示把缩放后的图再平移多少
        def cost(dx: int, dy: int, step: int) -> float:
            ys, xs = round(y0 * s) - dy, round(x0 * s) - dx
            if ys < 0 or xs < 0 or ys + patch.shape[0] > scaled.shape[0] or xs + patch.shape[1] > scaled.shape[1]:
                return math.inf
            return float(np.abs(scaled[ys : ys + patch.shape[0] : step, xs : xs + patch.shape[1] : step] - patch[::step, ::step]).mean())
        coarse = min(((cost(dx, dy, k), dx, dy) for dx in range(-120, 121, k) for dy in range(-160, 161, k)))
        fine = min(((cost(dx, dy, 2), dx, dy) for dx in range(coarse[1] - k, coarse[1] + k + 1) for dy in range(coarse[2] - k, coarse[2] + k + 1)))
        if fine[0] < best[0]:
            best = (fine[0], s, fine[1], fine[2])
    err, s, dx, dy = best
    # 缩放后的图贴到画布上的位置：书堆 (x0, y0) 要落在参考图的 (x0, y0)
    ox = dx + round(x0 - x0 * s)
    oy = dy + round(y0 - y0 * s)
    scaled = im.resize((round(SIZE[0] * s), round(SIZE[1] * s)), Image.LANCZOS)
    out = Image.new("RGB", SIZE, tuple(int(v) for v in KEY))
    out.paste(scaled, (ox, oy))
    print(f"对齐：缩放 {s:.2f}，平移 ({ox:+d}, {oy:+d})，书堆残差 {err:.1f}")
    return out


def key_out(im: Image.Image) -> Image.Image:
    """青色抠图，和 finish.py 的算法一致（距离键色的远近决定透明度，再去掉边缘的青色溢色）。"""
    rgb = np.asarray(im.convert("RGB"), dtype=np.float32)
    dist = np.sqrt(((rgb - KEY) ** 2).sum(axis=2) / (3 * 255.0**2))
    alpha = np.clip((dist - 0.25) / 0.04, 0, 1)  # 同 finish.py 的 SIMILARITY / BLEND
    spill = np.clip(np.minimum(rgb[..., 1], rgb[..., 2]) - rgb[..., 0], 0, None) * (alpha < 1)
    rgb[..., 1] -= spill * 0.8
    rgb[..., 2] -= spill * 0.8
    rgba = np.dstack([np.clip(rgb, 0, 255), alpha * 255]).round().astype(np.uint8)
    rgba[alpha == 0] = 0
    return Image.fromarray(rgba, "RGBA")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("candidate")
    ap.add_argument("name")
    ap.add_argument("--skin", default="")
    ap.add_argument("--ref", default="hub-A-approved")
    ap.add_argument("--no-align", action="store_true")
    ap.add_argument("--lower", type=float, default=1.0, help="只拿书堆下面这个比例当模板（上面被腿或裙摆挡住时调小）")
    args = ap.parse_args()
    prefix = f"{args.skin}-" if args.skin else ""
    im = Image.open(args.candidate)
    if args.no_align:
        im = im.convert("RGB").resize(SIZE, Image.LANCZOS)
    else:
        im = align(im, Image.open(INPUT / f"claude-girl-{prefix}{args.ref}-cyan-9x16.png"), args.lower)
    cyan = INPUT / f"claude-girl-{prefix}{args.name}-cyan-9x16.png"
    im.save(cyan)
    kf_dir = ROOT / "resources" / (f"assets-{args.skin}" if args.skin else "assets") / "keyframes"
    kf_dir.mkdir(parents=True, exist_ok=True)
    transparent = kf_dir / f"claude-girl-{prefix}{args.name}-transparent-9x16.png"
    key_out(im).save(transparent)
    print(f"已写入 {cyan} 和 {transparent.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
