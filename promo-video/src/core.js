// 基础工具：画布尺寸、配色、缓动、确定性随机、文字。所有画面都是时间 t 的纯函数（不用 Math.random、不存帧间状态），
// 所以预览和逐帧导出完全一致。

export const W = 1920
export const H = 1080
export const FPS = 30

export const C = {
  ink: '#1a1918',
  ink2: '#2a2725',
  cream: '#f2eee6',
  paper: '#e9e3d6',
  orange: '#d97757',
  orange2: '#e8956f',
  deep: '#b0553a',
  gold: '#f0c27a',
  mute: '#8a8279',
  green: '#86be7a',
  red: '#e0604f'
}

export const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x))
export const lerp = (a, b, k) => a + (b - a) * k
export const prog = (t, t0, dur) => clamp((t - t0) / dur)

export const ease = {
  out: k => 1 - Math.pow(1 - clamp(k), 3),
  in: k => Math.pow(clamp(k), 3),
  inOut: k => (k = clamp(k), k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2),
  expo: k => (k = clamp(k), k === 1 ? 1 : 1 - Math.pow(2, -10 * k)),
  back: k => { k = clamp(k); const c = 1.9; return 1 + (c + 1) * Math.pow(k - 1, 3) + c * Math.pow(k - 1, 2) },
  smooth: k => (k = clamp(k), k * k * (3 - 2 * k))
}

// 确定性的“随机”：同样的输入永远得到同样的值
export function hash(...xs) {
  let h = 2166136261
  for (const x of xs) {
    h ^= Math.floor(x * 1000) | 0
    h = Math.imul(h, 16777619)
  }
  h ^= h >>> 13
  h = Math.imul(h, 0x5bd1e995)
  h ^= h >>> 15
  return (h >>> 0) / 4294967296
}

// 动画常用的“一拍两帧”：t 量化到 12 fps，抖动类效果用它，看起来像手绘动画
export const twos = t => Math.floor(t * 12) / 12

export const FONT = {
  title: '"Bahnschrift", "Noto Sans SC", sans-serif',
  cjk: '"Noto Sans SC", "Microsoft YaHei", sans-serif',
  serif: '"Noto Serif SC", serif',
  mono: '"Consolas", "Microsoft YaHei", monospace'
}

export function font(ctx, size, family = FONT.cjk, weight = 700, stretch = 'normal') {
  ctx.font = `${weight} ${size}px ${family}`
  ctx.fontStretch = stretch
}

// 逐字弹出的文字：每个字从下方弹起、带一点回弹；stagger 是相邻两字的间隔（秒）
export function popText(ctx, text, x, y, t, t0, { size = 80, family = FONT.cjk, weight = 900, color = C.ink,
  stagger = 0.04, dur = 0.45, align = 'left', stretch = 'normal', stroke = null, shadow = null, tracking = 0 } = {}) {
  font(ctx, size, family, weight, stretch)
  const chars = [...text]
  const widths = chars.map(ch => ctx.measureText(ch).width + tracking)
  const total = widths.reduce((a, b) => a + b, 0) - tracking
  let cx = align === 'center' ? x - total / 2 : align === 'right' ? x - total : x
  ctx.textBaseline = 'alphabetic'
  chars.forEach((ch, i) => {
    const k = prog(t, t0 + i * stagger, dur)
    if (k <= 0) { cx += widths[i]; return }
    const s = ease.back(k)
    const dy = (1 - ease.out(k)) * size * 0.6
    ctx.save()
    ctx.translate(cx + widths[i] / 2, y + dy)
    ctx.scale(s, s)
    ctx.globalAlpha *= clamp(k * 3)
    if (shadow) { ctx.fillStyle = shadow.color; ctx.fillText(ch, -widths[i] / 2 + shadow.dx, shadow.dy) }
    if (stroke) { ctx.lineWidth = stroke.width; ctx.strokeStyle = stroke.color; ctx.lineJoin = 'round'; ctx.strokeText(ch, -widths[i] / 2, 0) }
    ctx.fillStyle = color
    ctx.fillText(ch, -widths[i] / 2, 0)
    ctx.restore()
    cx += widths[i]
  })
  return total
}

// 打字机：按字数显示，返回显示到的位置
export function typed(text, t, t0, cps = 18) {
  const n = Math.max(0, Math.floor((t - t0) * cps))
  return [...text].slice(0, n).join('')
}

export function text(ctx, str, x, y, { size = 32, family = FONT.cjk, weight = 500, color = C.ink, align = 'left',
  baseline = 'alphabetic', alpha = 1, stretch = 'normal' } = {}) {
  if (alpha <= 0) return
  font(ctx, size, family, weight, stretch)
  ctx.save()
  ctx.globalAlpha *= alpha
  ctx.fillStyle = color
  ctx.textAlign = align
  ctx.textBaseline = baseline
  ctx.fillText(str, x, y)
  ctx.restore()
}

export function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath()
  ctx.roundRect(x, y, w, h, r)
}
