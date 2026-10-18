// 画面元素：斜切色块、网点、速度线、印章字、章节卡、终端面板、窗口、实机画面框。
// 原则：所有华丽的东西都由这里的代码画；她本人只用 footage() 原样播放实机帧，不加任何额外动作。

import { C, FONT, H, W, clamp, ease, font, hash, lerp, popText, prog, roundRect, text, twos } from './core.js'
import { frameAt } from './assets.js'

const SLANT = Math.tan((12 * Math.PI) / 180)

// 斜切的色块：从左到右扫过（k: 0→1），带 12° 斜边
export function slab(ctx, k, color, { y0 = 0, y1 = H, reverse = false } = {}) {
  if (k <= 0) return
  const span = W + (y1 - y0) * SLANT
  const x = reverse ? W - span * k : -(y1 - y0) * SLANT
  const w = span * k
  ctx.fillStyle = color
  ctx.beginPath()
  if (!reverse) {
    ctx.moveTo(x, y1); ctx.lineTo(x + (y1 - y0) * SLANT, y0); ctx.lineTo(x + w + (y1 - y0) * SLANT, y0); ctx.lineTo(x + w, y1)
  } else {
    ctx.moveTo(x, y1); ctx.lineTo(x + (y1 - y0) * SLANT, y0); ctx.lineTo(W + (y1 - y0) * SLANT, y0); ctx.lineTo(W, y1)
  }
  ctx.closePath()
  ctx.fill()
}

// 斜切转场：几条不同颜色的色块依次扫过盖住画面，再依次扫走。t 是相对转场中点的时间
export function wipe(ctx, t, colors = [C.orange, C.ink, C.cream], dur = 0.5) {
  colors.forEach((col, i) => {
    const d = i * 0.06
    const inK = ease.inOut(prog(t, -dur + d, dur))
    const outK = ease.inOut(prog(t, d, dur))
    if (inK <= 0 || outK >= 1) return
    // 进：左边缘固定在左外侧、右边缘推进；出：左边缘推进
    const left = lerp(-W * 0.3, W * 1.3, outK)
    const right = lerp(-W * 0.3, W * 1.3, inK)
    if (right <= left) return
    ctx.fillStyle = col
    ctx.beginPath()
    ctx.moveTo(left, H); ctx.lineTo(left + H * SLANT, 0); ctx.lineTo(right + H * SLANT, 0); ctx.lineTo(right, H)
    ctx.closePath()
    ctx.fill()
  })
}

// 网点：从一角向外渐弱的圆点阵（漫画网点）
const dotCache = new Map()
export function halftone(ctx, x, y, w, h, color, { step = 22, maxR = 7, dir = 'tl' } = {}) {
  const key = [w, h, color, step, maxR, dir].join()
  let cv = dotCache.get(key)
  if (!cv) {
    cv = new OffscreenCanvas(w, h)
    const c = cv.getContext('2d')
    c.fillStyle = color
    for (let yy = 0; yy < h + step; yy += step) {
      for (let xx = 0; xx < w + step; xx += step) {
        const ox = (Math.floor(yy / step) % 2) * step / 2
        const px = xx + ox, py = yy
        const fx = dir.includes('l') ? 1 - px / w : px / w
        const fy = dir.includes('t') ? 1 - py / h : py / h
        const r = maxR * clamp(Math.min(fx, 1) * 0.6 + Math.min(fy, 1) * 0.6 - 0.25)
        if (r > 0.4) { c.beginPath(); c.arc(px, py, r, 0, Math.PI * 2); c.fill() }
      }
    }
    dotCache.set(key, cv)
  }
  ctx.drawImage(cv, x, y)
}

// 斜条纹背景，缓慢移动
export function stripes(ctx, t, color, { gap = 46, width = 14, speed = 30, alpha = 1 } = {}) {
  ctx.save()
  ctx.globalAlpha *= alpha
  ctx.strokeStyle = color
  ctx.lineWidth = width
  const off = (t * speed) % gap
  ctx.beginPath()
  for (let x = -H - gap; x < W + gap; x += gap) {
    ctx.moveTo(x + off, H); ctx.lineTo(x + off + H, 0)
  }
  ctx.stroke()
  ctx.restore()
}

// 集中线（速度线）：从画面外指向中心，一拍两帧地抖动
export function speedLines(ctx, t, cx, cy, { count = 70, inner = 380, color = C.ink, alpha = 0.9 } = {}) {
  const tt = twos(t)
  ctx.save()
  ctx.globalAlpha *= alpha
  ctx.fillStyle = color
  for (let i = 0; i < count; i++) {
    const a = (i / count) * Math.PI * 2 + hash(i, 1) * 0.08
    const r0 = inner + hash(i, tt) * 160
    const r1 = 1500
    const wdt = 0.004 + hash(i, 7) * 0.012
    ctx.beginPath()
    ctx.moveTo(cx + Math.cos(a - wdt) * r1, cy + Math.sin(a - wdt) * r1)
    ctx.lineTo(cx + Math.cos(a) * r0, cy + Math.sin(a) * r0)
    ctx.lineTo(cx + Math.cos(a + wdt) * r1, cy + Math.sin(a + wdt) * r1)
    ctx.fill()
  }
  ctx.restore()
}

// 印章字：英文大字 + 中文小字，从放大、带旋转的状态“砸”下来
export function stamp(ctx, t, t0, x, y, en, zh, { color = C.orange, ink = C.cream, rot = -6, size = 92 } = {}) {
  const k = prog(t, t0, 0.32)
  if (k <= 0) return
  const s = lerp(1.7, 1, ease.out(k))
  ctx.save()
  ctx.translate(x, y)
  ctx.rotate(((rot + (1 - ease.out(k)) * -8) * Math.PI) / 180)
  ctx.scale(s, s)
  ctx.globalAlpha *= clamp(k * 2.5)
  font(ctx, size, FONT.title, 700, 'condensed')
  const w1 = ctx.measureText(en).width
  font(ctx, size * 0.42, FONT.cjk, 900)
  const w2 = ctx.measureText(zh).width
  const bw = Math.max(w1, w2) + 70
  const bh = size * 1.62
  ctx.fillStyle = color
  ctx.fillRect(-bw / 2 + 10, -bh / 2 + 10, bw, bh)
  ctx.fillStyle = C.ink
  ctx.fillRect(-bw / 2, -bh / 2, bw, bh)
  ctx.strokeStyle = color
  ctx.lineWidth = 5
  ctx.strokeRect(-bw / 2 + 12, -bh / 2 + 12, bw - 24, bh - 24)
  text(ctx, en, 0, -bh / 2 + size * 0.98, { size, family: FONT.title, weight: 700, color: ink, align: 'center', stretch: 'condensed' })
  text(ctx, zh, 0, bh / 2 - size * 0.2, { size: size * 0.42, weight: 900, color, align: 'center' })
  ctx.restore()
}

// 章节卡：巨大的编号 + 标题 + 英文小字，背景斜纹
export function chapter(ctx, t, num, title, en) {
  ctx.fillStyle = C.ink
  ctx.fillRect(0, 0, W, H)
  stripes(ctx, t, C.ink2, { gap: 60, width: 26, speed: 60 })
  halftone(ctx, W - 760, H - 520, 760, 520, C.deep, { dir: 'br', step: 24, maxR: 9 })
  const k = ease.expo(prog(t, 0.05, 0.5))
  ctx.save()
  ctx.translate(lerp(-300, 0, k), 0)
  font(ctx, 420, FONT.title, 700, 'condensed')
  ctx.lineWidth = 6
  ctx.strokeStyle = C.orange
  ctx.strokeText(num, 150, 620)
  ctx.restore()
  // 标题条：宽度跟着标题走
  font(ctx, 84, FONT.cjk, 900)
  const tw = ctx.measureText(title).width + 170 + 110
  const bk = ease.expo(prog(t, 0.2, 0.45))
  ctx.fillStyle = C.orange
  ctx.fillRect(0, 670, tw * bk, 120)
  popText(ctx, title, 170, 760, t, 0.28, { size: 84, color: C.ink, stagger: 0.03 })
  text(ctx, en, 172, 850, { size: 30, family: FONT.title, weight: 600, color: C.mute, alpha: prog(t, 0.6, 0.4), stretch: 'condensed' })
}

// 实机画面：她的帧原样画进一个框里，左上角标“实机画面”。只做缩放、裁切和放置，不改动她本身。
export function footage(ctx, clip, lt, x, y, h, { loop = true, frame = true, tag = true, bg = C.cream, alpha = 1, crop = null } = {}) {
  const bmp = frameAt(clip, lt, loop)
  const scale = h / 960
  const w = 540 * scale * (bmp ? bmp.width / bmp.height / (540 / 960) : 1)
  ctx.save()
  ctx.globalAlpha *= alpha
  if (frame) {
    ctx.fillStyle = 'rgba(40,20,10,0.25)'
    roundRect(ctx, x + 14, y + 18, w, h, 26); ctx.fill()
    ctx.fillStyle = bg
    roundRect(ctx, x, y, w, h, 26); ctx.fill()
  }
  if (bmp) {
    ctx.save()
    roundRect(ctx, x, y, w, h, 26)
    ctx.clip()
    if (crop) {
      const [cx, cy, cw, ch] = crop.map((v, i) => v * (i % 2 ? bmp.height : bmp.width))
      ctx.drawImage(bmp, cx, cy, cw, ch, x, y, w, h)
    } else {
      ctx.drawImage(bmp, x, y, w, h)
    }
    ctx.restore()
  }
  if (tag) {
    font(ctx, 20, FONT.cjk, 900)
    const label = '实机画面  IN-APP'
    const tw = ctx.measureText(label).width + 28
    ctx.fillStyle = C.ink
    roundRect(ctx, x + 18, y + 18, tw, 38, 8); ctx.fill()
    ctx.fillStyle = C.orange
    ctx.beginPath(); ctx.arc(x + 34, y + 37, 6, 0, Math.PI * 2); ctx.fill()
    text(ctx, label, x + 48, y + 44, { size: 20, weight: 900, color: C.cream })
  }
  ctx.restore()
  return w
}

// 终端面板（Claude Code 的样子）：lines = [[文字, 颜色]]
export function terminal(ctx, x, y, w, h, lines, { title = 'claude  ~/my-app', size = 30, cursor = null } = {}) {
  ctx.save()
  ctx.fillStyle = 'rgba(0,0,0,0.3)'
  roundRect(ctx, x + 12, y + 16, w, h, 22); ctx.fill()
  ctx.fillStyle = C.ink
  roundRect(ctx, x, y, w, h, 22); ctx.fill()
  ;['#ed6a5e', '#f5bf4f', '#62c554'].forEach((c, i) => {
    ctx.fillStyle = c
    ctx.beginPath(); ctx.arc(x + 34 + i * 30, y + 32, 8, 0, Math.PI * 2); ctx.fill()
  })
  text(ctx, title, x + w / 2, y + 40, { size: 20, family: FONT.mono, weight: 400, color: C.mute, align: 'center' })
  ctx.fillStyle = '#34312e'
  ctx.fillRect(x, y + 62, w, 2)
  let yy = y + 62 + size * 1.7
  for (const [str, col] of lines) {
    text(ctx, str, x + 40, yy, { size, family: FONT.mono, weight: 400, color: col || C.cream })
    yy += size * 1.55
  }
  if (cursor !== null && Math.floor(cursor * 2) % 2 === 0) {
    const last = lines.length ? lines[lines.length - 1][0] : ''
    font(ctx, size, FONT.mono, 400)
    ctx.fillStyle = C.orange
    ctx.fillRect(x + 42 + ctx.measureText(last).width, yy - size * 1.55 - size * 0.8, size * 0.55, size * 0.95)
  }
  ctx.restore()
}

// 简化的应用窗口（用来演示跟随窗口、全屏）
export function appWindow(ctx, x, y, w, h, { title = 'Claude', color = C.paper, accent = C.orange } = {}) {
  ctx.save()
  ctx.fillStyle = 'rgba(0,0,0,0.25)'
  roundRect(ctx, x + 10, y + 14, w, h, 18); ctx.fill()
  ctx.fillStyle = color
  roundRect(ctx, x, y, w, h, 18); ctx.fill()
  ctx.fillStyle = C.ink
  roundRect(ctx, x, y, w, 46, [18, 18, 0, 0]); ctx.fill()
  ctx.fillStyle = accent
  ctx.beginPath(); ctx.arc(x + 28, y + 23, 9, 0, Math.PI * 2); ctx.fill()
  text(ctx, title, x + 48, y + 31, { size: 20, weight: 700, color: C.cream })
  // 假的内容行
  ctx.fillStyle = 'rgba(26,25,24,0.12)'
  for (let i = 0; i < 6; i++) {
    const lw = (0.35 + hash(i, w) * 0.5) * (w - 80)
    roundRect(ctx, x + 40, y + 80 + i * 44, lw, 18, 9); ctx.fill()
  }
  ctx.restore()
}

// 鼠标指针
export function cursor(ctx, x, y, s = 1.4, pressed = false) {
  ctx.save()
  ctx.translate(x, y)
  ctx.scale(s * (pressed ? 0.9 : 1), s * (pressed ? 0.9 : 1))
  ctx.fillStyle = C.cream
  ctx.strokeStyle = C.ink
  ctx.lineWidth = 2.2
  ctx.beginPath()
  ctx.moveTo(0, 0); ctx.lineTo(0, 34); ctx.lineTo(9, 26); ctx.lineTo(16, 41); ctx.lineTo(22, 38); ctx.lineTo(15, 23); ctx.lineTo(26, 23)
  ctx.closePath(); ctx.fill(); ctx.stroke()
  ctx.restore()
}

// 小标签（圆角胶囊）
export function pill(ctx, x, y, str, { bg = C.orange, color = C.ink, size = 26, alpha = 1 } = {}) {
  if (alpha <= 0) return
  font(ctx, size, FONT.cjk, 900)
  const w = ctx.measureText(str).width + size * 1.4
  ctx.save()
  ctx.globalAlpha *= alpha
  ctx.fillStyle = bg
  roundRect(ctx, x, y, w, size * 1.7, size * 0.85); ctx.fill()
  text(ctx, str, x + size * 0.7, y + size * 1.22, { size, weight: 900, color })
  ctx.restore()
  return w
}

// 白闪（转场用，很短）
export function flash(ctx, t, t0, dur = 0.18) {
  const k = prog(t, t0, dur)
  if (k <= 0 || k >= 1) return
  ctx.save()
  ctx.globalAlpha = 1 - k
  ctx.fillStyle = '#fff'
  ctx.fillRect(0, 0, W, H)
  ctx.restore()
}
