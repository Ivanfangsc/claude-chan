"""用现有素材合成宣传片（1920x1080，24fps，无声）。

    uv run --with imageio-ffmpeg --with scipy --with av python scripts/promo.py            # 输出 promo/claude-girl-promo.mp4
    uv run --with imageio-ffmpeg --with scipy --with av python scripts/promo.py --stills   # 每个场景抽几张静帧到 promo/stills，先看排版
"""
import json
import math
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "promo"
W, H, FPS = 1920, 1080, 24
SKIN_DIR = {"adult": ROOT / "resources/assets", "chibi": ROOT / "resources/assets-chibi"}

BG = (240, 238, 230)
INK = (31, 30, 29)
MUTED = (115, 110, 102)
ACCENT = (217, 119, 87)
TERM_BG = (31, 30, 29)
TERM_FG = (232, 228, 218)
TERM_DIM = (140, 134, 124)
TERM_GREEN = (134, 190, 122)

FONTS = "C:/Windows/Fonts/"


@lru_cache(None)
def font(kind, size):
    if kind == "serif":
        f = ImageFont.truetype(FONTS + "NotoSerifSC-VF.ttf", size)
        f.set_variation_by_name("Bold")
        return f
    if kind == "serif-med":
        f = ImageFont.truetype(FONTS + "NotoSerifSC-VF.ttf", size)
        f.set_variation_by_name("Medium")
        return f
    return ImageFont.truetype(FONTS + {"sans": "msyh.ttc", "bold": "msyhbd.ttc", "mono": "consola.ttf",
                                       "sym": "seguisym.ttf"}[kind], size)


SYM = set("✻●⎿❯✓⏺")


def draw_mono(d, xy, text, size, fill):
    """终端里的一行：ASCII 用 Consolas，符号用 Segoe UI Symbol，中文用雅黑。"""
    x, y = xy
    for ch in text:
        if ch in SYM:
            f = font("sym", size)
        elif ord(ch) < 128:
            f = font("mono", size)
        else:
            f = font("sans", size - 2)
        d.text((x, y + (2 if f is font("sans", size - 2) else 0)), ch, font=f, fill=fill)
        x += d.textlength(ch, font=f)


# ---------- 素材 ----------

manifests = {s: json.loads((p / "manifest.json").read_text(encoding="utf-8")) for s, p in SKIN_DIR.items()}


def clip_file(skin, cid):
    m = manifests[skin]
    if cid.startswith("switch:"):
        return SKIN_DIR[skin] / m["switch"][cid[7:]]
    for c in m["clips"]:
        if c["id"] == cid:
            return SKIN_DIR[skin] / c["file"]
    raise KeyError(cid)


@lru_cache(maxsize=24)
def frames(skin, cid, h, start=0, end=None):
    im = Image.open(clip_file(skin, cid))
    end = im.n_frames if end is None else min(end, im.n_frames)
    w = round(h * 9 / 16)
    out = []
    for i in range(start, end):
        im.seek(i)
        out.append(im.convert("RGBA").resize((w, h), Image.LANCZOS))
    return out


def seq(skin, h, parts, xfade=8):
    """把若干段 (clip, start, end) 接起来；段与段之间做 xfade 帧的溶解（剪辑式跳切）。"""
    result = []
    for cid, s, e in parts:
        fr = frames(skin, cid, h, s, e)
        if result and xfade:
            tail = result[-xfade:]
            del result[-xfade:]
            for k in range(xfade):
                a = (k + 1) / (xfade + 1)
                result.append(Image.blend(tail[k], fr[k], a))
            result.extend(fr[xfade:])
        else:
            result.extend(fr)
    return result


def at(fr, i):
    return fr[min(max(i, 0), len(fr) - 1)]


# ---------- 画面元素 ----------

def ease(x):
    x = min(max(x, 0.0), 1.0)
    return 1 - (1 - x) ** 3


def smooth(x):
    """两头都平缓的缓动（淡出时不会第一帧就掉一大截）。"""
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def with_alpha(layer, a):
    if a >= 1:
        return layer
    l = layer.copy()
    l.putalpha(l.getchannel("A").point(lambda v: int(v * a)))
    return l


@lru_cache(None)
def background(glow_x=None):
    bg = Image.new("RGBA", (W, H), BG + (255,))
    if glow_x is not None:
        g = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        gd = ImageDraw.Draw(g)
        r = 470
        gd.ellipse((glow_x - r, 560 - r, glow_x + r, 560 + r), fill=ACCENT + (38,))
        g = g.filter(ImageFilter.GaussianBlur(120))
        bg.alpha_composite(g)
    return bg


@lru_cache(None)
def text_layer(text, kind, size, fill, spacing=0):
    f = font(kind, size)
    lines = text.split("\n")
    lh = int(size * 1.35)
    wmax = max(int(ImageDraw.Draw(Image.new("L", (1, 1))).textlength(l, font=f)) for l in lines) + 4
    layer = Image.new("RGBA", (wmax + 8, lh * len(lines) + size // 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for i, l in enumerate(lines):
        d.text((2, i * lh), l, font=f, fill=fill)
    return layer


def put_text(canvas, t, t0, xy, text, kind, size, fill=INK, anchor_right=False, t_out=None, center=False):
    """t 秒时贴一段文字：t0 起 0.6 秒上浮淡入；t_out 起淡出。"""
    a = ease((t - t0) / 0.6)
    if t_out is not None:
        a *= 1 - ease((t - t_out) / 0.4)
    if a <= 0:
        return
    layer = text_layer(text, kind, size, fill)
    x, y = xy
    if anchor_right:
        x -= layer.width
    if center:
        x -= layer.width / 2
    y += int((1 - a) * 24)
    canvas.alpha_composite(with_alpha(layer, a), (int(x), int(y)))


def chip(canvas, t, t0, center, label, sub, mult=1.0):
    """角色脚下的状态小胶囊：英文状态名 + 中文。"""
    a = ease((t - t0) / 0.4) * mult
    if a <= 0:
        return
    f1, f2 = font("bold", 26), font("sans", 26)
    tmp = ImageDraw.Draw(Image.new("L", (1, 1)))
    w1, w2 = tmp.textlength(label, font=f1), tmp.textlength(sub, font=f2)
    w = int(w1 + w2 + 26 + 56)
    layer = Image.new("RGBA", (w, 56), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle((0, 0, w - 1, 55), radius=28, fill=(255, 255, 255, 235), outline=ACCENT + (255,), width=2)
    d.ellipse((22, 22, 34, 34), fill=ACCENT)
    d.text((46, 11), label, font=f1, fill=ACCENT)
    d.text((46 + w1 + 14, 11), sub, font=f2, fill=INK)
    canvas.alpha_composite(with_alpha(layer, a), (int(center[0] - w / 2), int(center[1] + (1 - a) * 10)))


def terminal(canvas, box, lines, title="claude  —  ~/my-app"):
    """lines: [(文字, 颜色)]，最后一行可带光标。"""
    x0, y0, x1, y1 = box
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((x0 + 6, y0 + 18, x1 + 6, y1 + 18), radius=22, fill=(60, 40, 20, 60))
    canvas.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(18)))
    d = ImageDraw.Draw(canvas)
    d.rounded_rectangle(box, radius=22, fill=TERM_BG)
    for k, c in enumerate([(237, 106, 94), (245, 191, 79), (98, 197, 84)]):
        d.ellipse((x0 + 28 + k * 30, y0 + 24, x0 + 44 + k * 30, y0 + 40), fill=c)
    d.text(((x0 + x1) / 2, y0 + 32), title, font=font("mono", 22), fill=TERM_DIM, anchor="mm")
    d.line((x0, y0 + 62, x1, y0 + 62), fill=(55, 53, 50), width=2)
    y = y0 + 92
    for text, color in lines:
        draw_mono(d, (x0 + 44, y), text, 32, color)
        y += 54


def typed(text, t, t0, cps=14):
    n = int(max(0, (t - t0) * cps))
    return text[:n]


# ---------- 场景 ----------
# 每个场景：(时长秒, render(canvas, i, t)) ；i 为场景内帧号

SCENES = []


def scene(seconds):
    def deco(fn):
        SCENES.append((seconds, fn))
        return fn
    return deco


CH = 1080  # 主角色高度（整帧 9:16）


def place(canvas, img, cx, a=1.0, y=0):
    canvas.alpha_composite(with_alpha(img, a), (int(cx - img.width / 2), int(y)))


# 1. 开场
@scene(7)
def s_open(c, i, t):
    c.alpha_composite(background(1340))
    fr = frames("adult", "idle-loop", CH)
    place(c, at(fr, i % len(fr)), 1340, ease(t / 1.2))
    put_text(c, t, 0.6, (190, 330), "CLAUDE CODE 桌面伙伴", "bold", 30, ACCENT)
    put_text(c, t, 0.9, (180, 380), "Claude 娘", "serif", 168)
    put_text(c, t, 1.5, (190, 620), "一位安静陪你写代码的大小姐", "serif-med", 46, MUTED)


# 2. 跟着 Claude Code 切换状态
FLOW = [
    # (秒, 状态, 片段列表, 胶囊, 终端行)
    (4, "idle", None, ("idle", "待机"), "prompt"),
    (4.5, "thinking", None, ("thinking", "思考中"),
     [("✻ Thinking…", ACCENT)]),
    (4.5, "reading", None, ("reading", "读代码"),
     [("● Read(src/auth/login.py)", TERM_FG), ("  ⎿  Read 214 lines", TERM_DIM)]),
    (4.5, "writing", None, ("writing", "写代码"),
     [("● Update(src/auth/login.py)", TERM_FG), ("  ⎿  +42  -17", TERM_GREEN)]),
    (4.5, "confirmation", None,
     ("confirmation", "等你确认"),
     [("Bash command", ACCENT), ("  uv run pytest tests/auth", TERM_FG), ("", TERM_FG),
      ("Do you want to proceed?", TERM_FG), ("❯ 1. Yes", ACCENT), ("  2. No", TERM_DIM)]),
    (5.5, "complete", None, ("complete", "完成"),
     [("● Bash(uv run pytest tests/auth)", TERM_FG), ("  ⎿  23 passed in 1.84s", TERM_GREEN), ("", TERM_FG),
      ("● 重构完成：登录逻辑拆成了 3 个函数，", TERM_FG), ("  并补上了失败重试的测试。", TERM_FG)]),
]
FLOW_T = sum(f[0] for f in FLOW)
PROMPT = "帮我把登录模块重构一下，顺便补上测试"


FLOW_START = [sum(f[0] for f in FLOW[:k]) for k in range(len(FLOW))]


def flow_loop(k, n):
    st = FLOW[k][1]
    return frames("adult", f"{st}-loop", CH, 0, n)


@scene(FLOW_T)
def s_flow(c, i, t):
    c.alpha_composite(background(1420))
    put_text(c, t, 0.2, (120, 70), "通过 hooks 实时同步", "bold", 28, ACCENT)
    put_text(c, t, 0.4, (110, 110), "Claude Code 在忙什么，她都知道", "serif", 60)
    # 当前处于哪一段
    acc = 0
    for k, (sec, st, clips, (lab, sub), lines) in enumerate(FLOW):
        if t < acc + sec or k == len(FLOW) - 1:
            break
        acc += sec
    lt = t - acc
    li = i - round(acc * FPS)
    cur = flow_loop(k, int(FLOW[k][0] * FPS) + 1)
    if k == 0:
        place(c, at(cur, li), 1420, ease(t / 0.5), y=-40)
    else:
        if lt < 0.45:  # 上一个状态往左淡出
            prev = flow_loop(k - 1, int(FLOW[k - 1][0] * FPS) + 12)
            e = smooth(lt / 0.45)
            place(c, at(prev, round(FLOW[k - 1][0] * FPS) + li), 1420 - 90 * e, 1 - e, y=-40)
        a = smooth((lt - 0.15) / 0.5)
        if a > 0:
            place(c, at(cur, li), 1420 + 90 * (1 - a), a, y=-40)
    hist = [("> " + PROMPT, TERM_DIM)] if k > 0 else []
    if lines == "prompt":
        cur = typed(PROMPT, t, 1.2)
        cursor = "▌" if (i // 12) % 2 == 0 else " "
        hist = [("> " + cur + cursor, TERM_FG)]
    else:
        hist += [("", TERM_FG)] + lines
    terminal(c, (110, 230, 1010, 900), hist)
    if k > 0 and lt < 0.3:  # 上一个状态的标签淡出
        chip(c, 9, 0, (1420, 980), *FLOW[k - 1][3], mult=1 - smooth(lt / 0.3))
    chip(c, lt, 0.35, (1420, 980), lab, sub)


# 3. 对比：常见做法 vs Claude 娘（常见做法一侧用我们自己早期的旧素材演示）
OLD_GEN = Path("D:/comfy/ComfyUI/output/claude-girl-gen")
CACHE = OUT / "cache"


def old_clip(name, h):
    """早期“从关键帧出发、再回到关键帧”的旧 loop（青色背景原始帧），抠图后缓存。"""
    d = CACHE / name
    if not d.exists():
        import numpy as np
        sys.path.insert(0, str(ROOT / "scripts/comfy"))
        from finish import key_out
        key = np.array(json.loads((OLD_GEN / "_canonical/key.json").read_text()))
        d.mkdir(parents=True)
        for k, f in enumerate(sorted((OLD_GEN / name).glob("frame_*.png"))):
            rgba = key_out(np.asarray(Image.open(f).convert("RGB"), dtype=np.float32), key)
            Image.fromarray(rgba, "RGBA").save(d / f"{k:04d}.png")
    w = round(h * 9 / 16)
    return [Image.open(f).convert("RGBA").resize((w, h), Image.LANCZOS) for f in sorted(d.glob("*.png"))]


PANEL_H = 720


def pill(canvas, xy, text, fg, bg, a=1.0):
    f = font("bold", 28)
    w = int(ImageDraw.Draw(Image.new("L", (1, 1))).textlength(text, font=f)) + 48
    layer = Image.new("RGBA", (w, 52), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle((0, 0, w - 1, 51), radius=26, fill=bg)
    d.text((24, 9), text, font=f, fill=fg)
    canvas.alpha_composite(with_alpha(layer, a), (int(xy[0] - w / 2), int(xy[1])))


def compare(c, t, left, right, left_cap, right_cap, eyebrow, title):
    c.alpha_composite(background())
    put_text(c, t, 0.1, (110, 50), eyebrow, "bold", 28, ACCENT)
    put_text(c, t, 0.3, (100, 90), title, "serif", 56)
    for k, (img, cap, tag, bg) in enumerate([
        (left, left_cap, "常见做法", (150, 144, 134, 255)),
        (right, right_cap, "Claude 娘", ACCENT + (255,)),
    ]):
        cx = 520 + k * 880
        a = ease((t - 0.3 - k * 0.2) / 0.5)
        if a <= 0:
            continue
        panel = Image.new("RGBA", (800, 800), (0, 0, 0, 0))
        pd = ImageDraw.Draw(panel)
        pd.rounded_rectangle((0, 0, 799, 799), radius=30, fill=(255, 255, 255, 140))
        panel.alpha_composite(img, ((800 - img.width) // 2, 10))
        pd.text((400, 755), cap, font=font("sans", 30), fill=INK if k else MUTED, anchor="mm")
        c.alpha_composite(with_alpha(panel, a), (cx - 400, 230))
        pill(c, (cx, 204), tag, (255, 255, 255), bg, a)


@lru_cache(None)
def cmp_loop_frames():
    return old_clip("idle-L", PANEL_H), frames("adult", "idle-loop", PANEL_H)


@scene(10.5)
def s_cmp_loop(c, i, t):
    old, new = cmp_loop_frames()
    compare(c, t, old[i % len(old)], new[i % len(new)],
            "动作做完回到原位，再从头来一遍", "一直轻轻摇晃，看不出从哪开始重复",
            "对比 ① 待机", "待机再久，也不会有“又来了”的感觉")


SWITCH_AT = 72  # 第 3 秒状态变成 thinking


@lru_cache(None)
def cmp_switch_frames():
    oi, ot = old_clip("idle-L", PANEL_H), old_clip("thinking-L", PANEL_H)
    left = oi[:SWITCH_AT]
    for k in range(4):  # 0.18 秒的淡入淡出硬切
        left.append(Image.blend(oi[SWITCH_AT + k], ot[k], (k + 1) / 5))
    left += (ot[4:] + ot) * 2
    idle = frames("adult", "idle-loop", PANEL_H)
    right = idle[len(idle) - SWITCH_AT:] + frames("adult", "thinking-intro", PANEL_H) \
        + frames("adult", "thinking-loop", PANEL_H) * 2
    return left, right


@scene(10)
def s_cmp_switch(c, i, t):
    left, right = cmp_switch_frames()
    compare(c, t, at(left, i), at(right, i),
            "画面一闪，直接换成另一个姿势", "每种切换都有专门生成的过渡动画",
            "对比 ② 切换状态", "Claude 开始思考的那一刻")
    if i >= SWITCH_AT:
        chip(c, t - SWITCH_AT / FPS, 0, (W / 2, 196), "thinking", "开始思考")


# 4. 优势小结
ADVANTAGES = [
    ("看不出循环", "持续摇晃的 loop，没有“回到原位再来一遍”"),
    ("状态之间不硬切", "每种切换都有专门生成的过渡动画"),
    ("小动作不打断", "随机动作直接插进摇晃里，前后无缝衔接"),
    ("真正懂 Claude Code", "通过 hooks 同步，后台任务、多个会话都跟得上"),
    ("不挡你干活", "透明的地方鼠标直接点穿，全屏时自动隐身"),
]


@scene(11)
def s_adv(c, i, t):
    c.alpha_composite(background(1440))
    fr = frames("adult", "idle-loop-2", CH)
    place(c, at(fr, i % len(fr)), 1440, ease(t / 0.5))
    put_text(c, t, 0.2, (150, 120), "所以她看起来更像“活着”", "bold", 30, ACCENT)
    for k, (h, s) in enumerate(ADVANTAGES):
        t0 = 0.6 + k * 0.45
        y = 210 + k * 152
        a = ease((t - t0) / 0.5)
        if a > 0:
            dot = Image.new("RGBA", (24, 24), (0, 0, 0, 0))
            ImageDraw.Draw(dot).ellipse((0, 0, 23, 23), fill=ACCENT)
            c.alpha_composite(with_alpha(dot, a), (150, y + 22 + int((1 - a) * 24)))
        put_text(c, t, t0, (196, y), h, "serif", 50)
        put_text(c, t, t0 + 0.1, (198, y + 70), s, "sans", 32, MUTED)


# 5. 切换到 Q 版
@lru_cache(None)
def switch_frames():
    a = frames("adult", "idle-loop", CH)[-40:]
    s = frames("adult", "switch:chibi", CH)
    b = frames("chibi", "idle-loop", CH, 0, 60)
    return a + s + b


@scene(9.5)
def s_switch(c, i, t):
    c.alpha_composite(background(1360))
    fr = switch_frames()
    place(c, at(fr, i), 1360, ease(t / 0.4))
    put_text(c, t, 0.4, (190, 380), "两种形象", "bold", 30, ACCENT)
    put_text(c, t, 0.7, (180, 430), "还有 Q 版", "serif", 96)
    put_text(c, t, 1.3, (190, 580), "托盘里一键切换，自带变身动画。", "serif-med", 42, MUTED)


# 6. 小动作集锦：两套形象混在一起，一屏带过
def grid(c, i, t, items, title, sub):
    c.alpha_composite(background())
    put_text(c, t, 0.2, (110, 70), sub, "bold", 28, ACCENT)
    put_text(c, t, 0.4, (100, 110), title, "serif", 60)
    ch = 700
    cw = round(ch * 9 / 16)
    gap = (W - 220 - cw * len(items)) / (len(items) - 1)
    for k, (skin, cid, start, label) in enumerate(items):
        x = 110 + k * (cw + gap)
        t0 = 0.4 + k * 0.12
        a = ease((t - t0) / 0.5)
        if a <= 0:
            continue
        card = Image.new("RGBA", (cw, ch + 70), (0, 0, 0, 0))
        cd = ImageDraw.Draw(card)
        cd.rounded_rectangle((0, 40, cw - 1, ch + 69), radius=26, fill=(255, 255, 255, 150))
        fr = frames(skin, cid, ch)
        card.alpha_composite(at(fr, start + i), (0, -10))
        cd.text((cw / 2, ch + 30), label, font=font("sans", 30), fill=INK, anchor="mm")
        c.alpha_composite(with_alpha(card, a), (int(x), int(230 + (1 - a) * 30)))


REEL = [("adult", "event-waiting-watch", 6, "看怀表等任务"), ("adult", "event-idle-tea", 6, "喝口茶"),
        ("chibi", "event-idle-stretch", 6, "伸懒腰"), ("adult", "event-drowsy-bubble", 6, "犯困冒泡"),
        ("chibi", "event-reading-lean", 6, "凑近看")]


@scene(10)
def s_reel(c, i, t):
    grid(c, i, t, REEL, "二十多个随机小动作，偶尔冒出一个", "两套形象，各有一整套")


# 7. 结尾
@scene(8)
def s_end(c, i, t):
    c.alpha_composite(background(960))
    a = frames("adult", "complete-loop", 900)
    b = frames("chibi", "complete-loop", 900)
    place(c, at(a, i % len(a)), 560, ease(t / 0.8), y=150)
    place(c, at(b, i % len(b)), 1360, ease((t - 0.3) / 0.8), y=150)
    put_text(c, t, 0.8, (W / 2, 60), "Claude 娘", "serif", 110, center=True)
    put_text(c, t, 1.4, (W / 2, 230), "陪你把代码写完。", "serif-med", 46, MUTED, center=True)
    put_text(c, t, 2.4, (W / 2, 1020), "非 Anthropic 官方作品 · 同人桌宠", "sans", 24, MUTED, center=True)


# ---------- 输出 ----------

def clear_caches():
    for f in (frames, switch_frames, cmp_loop_frames, cmp_switch_frames):
        f.cache_clear()


XFADE = 12


def render_scene(k, i):
    sec, fn = SCENES[k]
    c = Image.new("RGBA", (W, H))
    fn(c, i, i / FPS)
    return c


def timeline():
    """每个场景的起始帧：相邻场景重叠 XFADE 帧做交叉溶解。"""
    starts, g = [], 0
    for sec, _ in SCENES:
        starts.append(g)
        g += int(sec * FPS) - XFADE
    return starts, g + XFADE


def render_frame(g, starts, total):
    live = [k for k, st in enumerate(starts) if st <= g < st + int(SCENES[k][0] * FPS)]
    img = render_scene(live[0], g - starts[live[0]])
    if len(live) > 1:
        k = live[1]
        img = Image.blend(img, render_scene(k, g - starts[k]), (g - starts[k] + 1) / (XFADE + 1))
    a = min(1.0, (g + 1) / 12, (total - g) / 18)  # 片头片尾淡入淡出
    if a < 1:
        img = Image.blend(Image.new("RGBA", (W, H), BG + (255,)), img, a)
    return img.convert("RGB"), live


def main():
    OUT.mkdir(exist_ok=True)
    starts, total = timeline()
    print(f"{len(SCENES)} 个场景，共 {total / FPS:.1f} 秒")
    if "--stills" in sys.argv:
        d = OUT / "stills"
        d.mkdir(exist_ok=True)
        for k, (sec, _) in enumerate(SCENES):
            n = int(sec * FPS)
            for j, f in enumerate((0.3, 0.6, 0.9)):
                render_scene(k, int(n * f)).convert("RGB").save(d / f"{k:02d}-{j}.jpg", quality=88)
            clear_caches()
        print("静帧：", d)
        return
    import imageio_ffmpeg
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    dst = OUT / "claude-girl-promo.mp4"
    p = subprocess.Popen([ff, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                          "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "slow", "-crf", "17",
                          "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(dst)], stdin=subprocess.PIPE)
    first = 0
    for g in range(total):
        img, live = render_frame(g, starts, total)
        p.stdin.write(img.tobytes())
        if live[0] > first:  # 前一个场景彻底播完，释放它的帧
            first = live[0]
            clear_caches()
            print(f"场景 {first}/{len(SCENES)} 完成（{g / FPS:.0f}/{total / FPS:.0f} 秒）", flush=True)
    p.stdin.close()
    p.wait()
    print("输出：", dst)


if __name__ == "__main__":
    main()
