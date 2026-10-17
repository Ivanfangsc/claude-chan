"""生成 README 用的图：docs/images/hero.webp（原版和 Q 版一起摇晃的动图）、docs/images/states.png（各状态一览）。

    uv run python scripts/readme_images.py
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "images"
FONT = "C:/Windows/Fonts/msyh.ttc"
BG = (0, 0, 0, 0)


def frames(path: Path, h: int) -> list[Image.Image]:
    im = Image.open(path)
    w = round(h * 9 / 16)
    out = []
    for i in range(im.n_frames):
        im.seek(i)
        out.append(im.convert("RGBA").resize((w, h), Image.LANCZOS))
    return out


def hero() -> None:
    h = 320
    a = frames(ROOT / "resources/assets/videos/loops/claude-girl-loop-idle-sway-transparent-9x16.avif", h)
    b = frames(ROOT / "resources/assets-chibi/videos/loops/claude-girl-loop-idle-sway-transparent-9x16.avif", h)
    n = min(len(a), len(b))
    w = a[0].width
    out = []
    for i in range(n):
        f = Image.new("RGBA", (w * 2, h), BG)
        f.alpha_composite(a[i], (0, 0))
        f.alpha_composite(b[i], (w, 0))
        out.append(f)
    out[0].save(OUT / "hero.webp", save_all=True, append_images=out[1:], duration=round(1000 / 24), loop=0,
                quality=55, method=4)


STATES = [("idle", "待机", "hub-A-approved"), ("thinking", "思考", "thinking"), ("reading", "读代码", "reading"),
          ("writing", "写代码", "writing"), ("confirmation", "等你确认", "waiting-confirmation"),
          ("complete", "完成", "complete"), ("error", "出错", "error"), ("drowsy", "打瞌睡", "drowsy")]


def states() -> None:
    h = 300
    w = round(h * 9 / 16)
    pad, label = 8, 34
    sheet = Image.new("RGBA", (len(STATES) * (w + pad) + pad, 2 * (h + label) + pad), BG)
    d = ImageDraw.Draw(sheet)
    f1 = ImageFont.truetype(FONT, 17)
    for row, (skin, prefix) in enumerate((("assets", "claude-girl-"), ("assets-chibi", "claude-girl-chibi-"))):
        kdir = ROOT / "resources" / skin / "keyframes"
        for k, (state, zh, key) in enumerate(STATES):
            name = "error-v3" if (key == "error" and skin == "assets") else key
            im = Image.open(kdir / f"{prefix}{name}-transparent-9x16.png").convert("RGBA").resize((w, h), Image.LANCZOS)
            x, y = pad + k * (w + pad), row * (h + label)
            sheet.alpha_composite(im, (x, y))
            d.text((x + w / 2, y + h + 4), f"{zh} {state}", font=f1, fill=(120, 110, 100, 255), anchor="ma")
    sheet.save(OUT / "states.png", optimize=True)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    hero()
    states()
    for p in sorted(OUT.iterdir()):
        print(p.name, f"{p.stat().st_size // 1024} KB")
