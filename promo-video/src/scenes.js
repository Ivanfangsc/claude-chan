// 分镜（约 1 分钟）。重点放在反复打磨过的视觉效果：状态之间带着动作接上的过渡、看不出循环的摇晃、
// 插在摇晃里的小动作、两种形象；其余功能一笔带过。
// 她出现的地方一律用 footage()：桌宠的实机帧原样播放，只缩放、放进画框，不加额外动作。
// 连续播放的几段，按桌宠真正的播放顺序接起来（loop 结尾 → 过渡 → 下一个状态），和桌宠里看到的一样。

import { C, FONT, H, W, ease, lerp, popText, prog, roundRect, text, typed } from './core.js'
import { footage, halftone, slab, speedLines, stripes, wipe } from './fx.js'
import { info } from './assets.js'

const A = id => `adult/${id}`
const Q = id => `chibi/${id}`
const LOOP_END = 138 / 24 // 摇晃 loop 一圈的长度
const BEAT = 0.6 // 一拍（换配乐后按实际速度改）

// 把几段按播放顺序接起来：后一段跳过首帧（和上一段末帧是同一帧）。parts: [[片段, 起点秒]]
function chainAt(parts, lt) {
  let t = lt
  for (let k = 0; k < parts.length; k++) {
    const [clip, s = 0] = parts[k]
    const { n, fps } = info(clip)
    const skip = k > 0 ? 1 / fps : 0
    const len = n / fps - s - skip
    if (t < len || k === parts.length - 1) return { clip, t: s + skip + t, k }
    t -= len
  }
}

// ---------- 开场 ----------
function open(ctx, lt) {
  ctx.fillStyle = '#0e0d0c'
  ctx.fillRect(0, 0, W, H)
  const line = typed('Claude小姐现在在干嘛？', lt, 0.3, 10)
  text(ctx, line, W / 2, 560, { size: 72, weight: 700, color: C.cream, align: 'center' })
  ctx.font = `700 72px ${FONT.cjk}`
  const cw = ctx.measureText(line).width
  if (Math.floor(lt * 2.5) % 2 === 0) { ctx.fillStyle = C.orange; ctx.fillRect(W / 2 + cw / 2 + 12, 500, 34, 72) }
}

// ---------- 标题 ----------
function title(ctx, lt) {
  ctx.fillStyle = C.cream
  ctx.fillRect(0, 0, W, H)
  halftone(ctx, 0, 0, 900, 600, C.orange2, { dir: 'tl', step: 26, maxR: 10 })
  slab(ctx, ease.expo(prog(lt, 0.0, 0.5)), C.ink, { y0: 860, y1: H })
  slab(ctx, ease.expo(prog(lt, 0.1, 0.5)), C.orange, { y0: 830, y1: 860 })
  const fk = ease.expo(prog(lt, 0.4, 0.7))
  if (lt > 0.4 && lt < 1.2) speedLines(ctx, lt, 1470, 520, { color: C.orange, alpha: 0.35 * (1 - prog(lt, 0.8, 0.4)) })
  footage(ctx, A('idle-loop'), lt, lerp(W + 40, 1250, fk), 70, 880)
  popText(ctx, 'Claude-Chan', 120, 470, lt, 0.2, { size: 230, family: FONT.title, weight: 700, stretch: 'condensed',
    color: C.ink, stagger: 0.03, shadow: { color: C.orange, dx: 10, dy: 10 } })
  popText(ctx, '看她就知道了', 128, 600, lt, 0.75, { size: 72, color: C.ink, stagger: 0.035 })
  text(ctx, '免费  ·  开源  ·  Windows', 132, 968, { size: 36, weight: 700, color: C.cream, alpha: prog(lt, 1.6, 0.5) })
}

// ---------- 人物介绍卡 ----------
const PROFILE = [
  ['性格', '稳重、安静，偶尔喝口茶'],
  ['特长', '看懂 Claude 在忙什么']
]
function profile(ctx, lt) {
  ctx.fillStyle = C.ink
  ctx.fillRect(0, 0, W, H)
  slab(ctx, 1, C.orange, { y0: 0, y1: H })
  ctx.fillStyle = C.ink
  ctx.beginPath(); ctx.moveTo(820, 0); ctx.lineTo(W, 0); ctx.lineTo(W, H); ctx.lineTo(820 - H * Math.tan(0.21), H); ctx.closePath(); ctx.fill()
  stripes(ctx, lt, C.ink2, { gap: 70, width: 30, speed: 40, alpha: 0.6 })
  halftone(ctx, 0, H - 420, 700, 420, C.deep, { dir: 'bl', step: 22, maxR: 8 })
  footage(ctx, A('idle-loop-2'), lt, 150, 80, 900)
  PROFILE.forEach(([k, v], i) => {
    const a = ease.out(prog(lt, 0.3 + i * 0.3, 0.35))
    if (a <= 0) return
    const y = 440 + i * 140
    ctx.save()
    ctx.globalAlpha = a
    ctx.translate((1 - a) * 60, 0)
    ctx.fillStyle = C.orange
    ctx.fillRect(900, y, 130, 72)
    text(ctx, k, 965, y + 36, { size: 36, weight: 900, color: C.ink, align: 'center', baseline: 'middle' })
    text(ctx, v, 1060, y + 36, { size: 44, weight: 700, color: C.cream, baseline: 'middle' })
    ctx.restore()
  })
}

// ---------- #01 状态切换：三格同时播，按桌宠的播放顺序接起来 ----------
const tail = id => [A(id), LOOP_END - 1.1]
const ROUNDS = [
  [
    { from: '待机', to: '思考', parts: [tail('idle-loop'), [A('thinking-intro')], [A('thinking-loop')]] },
    { from: '思考', to: '读代码', parts: [tail('thinking-loop'), [A('thinking-to-reading')], [A('reading-loop')]] },
    { from: '读代码', to: '写代码', parts: [tail('reading-loop'), [A('reading-to-writing')], [A('writing-loop')]] }
  ],
  [
    { from: '待机', to: '等你确认', parts: [tail('idle-loop'), [A('confirmation-intro')], [A('confirmation-loop')]] },
    { from: '待机', to: '完成', parts: [tail('idle-loop'), [A('complete-intro')], [A('complete-loop')]] },
    { from: '写代码', to: '思考', parts: [tail('writing-loop'), [A('writing-to-thinking')], [A('thinking-loop')]] }
  ]
]
// 每轮的长度（换配乐后按小节再调）
const ROUND_DURS = [8.4, 8.4]
function switching(ctx, lt) {
  const r = lt < ROUND_DURS[0] ? 0 : 1
  const rt = lt - (r ? ROUND_DURS[0] : 0)
  ctx.fillStyle = C.cream
  ctx.fillRect(0, 0, W, H)
  stripes(ctx, lt, '#e9e2d4', { gap: 52, width: 18, speed: 25 })
  halftone(ctx, W - 640, H - 440, 640, 440, C.orange2, { dir: 'br', step: 24, maxR: 8 })
  const ph = 820, pw = 540 * ph / 960, gap = 90
  const x0 = (W - (pw * 3 + gap * 2)) / 2
  ROUNDS[r].forEach((p, k) => {
    const a = ease.back(prog(rt, 0.05 + k * 0.08, 0.4))
    if (a <= 0) return
    const x = x0 + k * (pw + gap), y = 90
    const { clip, t, k: part } = chainAt(p.parts, rt)
    ctx.save()
    ctx.translate(x + pw / 2, y + ph / 2); ctx.scale(a, a); ctx.translate(-x - pw / 2, -y - ph / 2)
    footage(ctx, clip, t, x, y, ph, { loop: part === p.parts.length - 1, tag: k === 0 })
    ctx.restore()
    // 下面的标签：过渡开始后，目标状态亮起来
    const lit = part >= 1
    const cy = y + ph + 40
    ctx.save()
    ctx.globalAlpha = a
    ctx.font = `900 34px ${FONT.cjk}`
    const w1 = ctx.measureText(p.from).width, w2 = ctx.measureText(p.to).width
    const total = w1 + 70 + w2
    const sx = x + pw / 2 - total / 2
    text(ctx, p.from, sx, cy, { size: 34, weight: 900, color: lit ? C.mute : C.ink, baseline: 'middle' })
    text(ctx, '▶', sx + w1 + 35, cy, { size: 28, weight: 900, color: C.orange, align: 'center', baseline: 'middle' })
    if (lit) {
      ctx.fillStyle = C.orange
      roundRect(ctx, sx + w1 + 62, cy - 28, w2 + 20, 56, 12); ctx.fill()
    }
    text(ctx, p.to, sx + w1 + 72, cy, { size: 34, weight: 900, color: C.ink, baseline: 'middle' })
    ctx.restore()
  })
  if (r > 0) wipe(ctx, rt, [C.orange, C.ink], 0.32)
  if (r === 0 && rt > ROUND_DURS[0] - 0.45) wipe(ctx, rt - ROUND_DURS[0], [C.orange, C.ink], 0.32)
}

// ---------- #02 看不出循环、小动作插在摇晃里 ----------
const ACTS = [A('event-idle-tea'), A('event-idle-flower'), A('event-idle-gaze')]
function variety(ctx, lt) {
  ctx.fillStyle = C.paper
  ctx.fillRect(0, 0, W, H)
  halftone(ctx, 0, H - 460, 760, 460, C.orange2, { dir: 'bl', step: 24, maxR: 9 })
  footage(ctx, A('idle-loop'), lt, 120, 100, 860)
  popText(ctx, '各种小动作，让她更加生动活泼', 700, 250, lt, 0.1, { size: 66, stagger: 0.035 })
  const ph = 540, pw = 540 * ph / 960
  ACTS.forEach((clip, k) => {
    const a = ease.back(prog(lt, 1.1 + k * 0.12, 0.4))
    if (a <= 0) return
    const x = 704 + k * (pw + 70), y = 400
    ctx.save()
    ctx.translate(x + pw / 2, y + ph / 2); ctx.scale(a, a); ctx.translate(-x - pw / 2, -y - ph / 2)
    // 小动作本身就是从摇晃里接出去、再接回摇晃的一段
    footage(ctx, clip, Math.max(0, lt - 1.1) + 0.8, x, y, ph, { tag: false })
    ctx.restore()
  })
}

// ---------- #03 两种形象 ----------
function looks(ctx, lt) {
  ctx.fillStyle = C.cream
  ctx.fillRect(0, 0, W, H)
  ctx.fillStyle = C.orange
  ctx.beginPath(); ctx.moveTo(0, 0); ctx.lineTo(1060, 0); ctx.lineTo(860, H); ctx.lineTo(0, H); ctx.closePath(); ctx.fill()
  halftone(ctx, 0, 0, 900, 560, C.deep, { dir: 'tl', step: 24, maxR: 9 })
  halftone(ctx, W - 700, H - 460, 700, 460, C.orange2, { dir: 'br', step: 24, maxR: 9 })
  const a = ease.expo(prog(lt, 0.05, 0.5)), b = ease.expo(prog(lt, 0.2, 0.5))
  footage(ctx, A('idle-loop'), lt, lerp(-500, 160, a), 120, 860)
  footage(ctx, Q('idle-loop'), lt, lerp(W + 40, 1240, b), 120, 860)
  popText(ctx, '原版', 660, 1010, lt, 0.4, { size: 64, color: C.ink })
  popText(ctx, 'Q 版', 1250, 1040, lt, 0.55, { size: 64, color: C.ink })
}

// ---------- 其余功能，一笔带过 ----------
const QUICK = ['待确认操作气泡提示，点击跳转会话', '后台任务运行状态显示', '多会话同时运行，优先显示待处理的', '跟随 Claude 桌面版窗口', '全屏应用时自动隐藏', '透明区域鼠标穿透']
function quick(ctx, lt) {
  ctx.fillStyle = C.ink
  ctx.fillRect(0, 0, W, H)
  stripes(ctx, lt, C.ink2, { gap: 70, width: 30, speed: 40 })
  halftone(ctx, W - 760, 0, 760, 520, C.deep, { dir: 'tr', step: 24, maxR: 9 })
  footage(ctx, A('idle-loop-2'), lt, 1260, 110, 860)
  QUICK.forEach((s, k) => {
    const a = ease.out(prog(lt, 0.5 + k * BEAT, 0.3)) // 一拍一条
    if (a <= 0) return
    const y = 270 + k * 132
    ctx.save()
    ctx.globalAlpha = a
    ctx.translate((1 - a) * -80, 0)
    ctx.fillStyle = C.orange
    ctx.fillRect(160, y - 34, 16, 68)
    text(ctx, s, 210, y, { size: 62, weight: 900, color: C.cream, baseline: 'middle' })
    ctx.restore()
  })
}

// ---------- 结尾 ----------
function outro(ctx, lt) {
  ctx.fillStyle = C.ink
  ctx.fillRect(0, 0, W, H)
  stripes(ctx, lt, C.ink2, { gap: 70, width: 30, speed: 40 })
  halftone(ctx, W - 760, H - 520, 760, 520, C.deep, { dir: 'br', step: 24, maxR: 9 })
  footage(ctx, A('complete-loop'), lt, 80, 240, 640, { tag: false, alpha: ease.out(prog(lt, 0.1, 0.5)) })
  footage(ctx, Q('complete-loop'), lt, W - 80 - 360, 240, 640, { tag: false, alpha: ease.out(prog(lt, 0.25, 0.5)) })
  popText(ctx, 'Claude-Chan', W / 2, 520, lt, 0.35, { size: 160, family: FONT.title, weight: 700, stretch: 'condensed',
    color: C.cream, stagger: 0.03, align: 'center', shadow: { color: C.orange, dx: 9, dy: 9 } })
  const dl = prog(lt, 1.0, 0.5)
  if (dl > 0) {
    ctx.save()
    ctx.globalAlpha = dl
    ctx.font = `900 34px ${FONT.cjk}`
    const label = '免费下载 · github.com/Ivanfangsc/claude-chan'
    const w = ctx.measureText(label).width + 80
    ctx.fillStyle = C.orange
    roundRect(ctx, W / 2 - w / 2, 640, w, 76, 38); ctx.fill()
    text(ctx, label, W / 2, 678, { size: 34, weight: 900, color: C.ink, align: 'center', baseline: 'middle' })
    ctx.restore()
  }
  const cr = prog(lt, 1.6, 0.6)
  text(ctx, '人设：ZipZipPipe　·　特别感谢：黑鹤001　·　角色动画由 AI 生成', W / 2, 960, { size: 24, weight: 500, color: C.mute, align: 'center', alpha: cr })
  text(ctx, '非 Anthropic 官方作品。Claude 是 Anthropic, PBC 的商标。', W / 2, 1004, { size: 24, weight: 500, color: C.mute, align: 'center', alpha: cr })
  const out = prog(lt, 6.2, 1.2)
  if (out > 0) { ctx.fillStyle = `rgba(0,0,0,${out})`; ctx.fillRect(0, 0, W, H) }
}

// ---------- 时间线 ----------
// 每段的长度（秒）。换配乐后再按小节线微调。
const CUTS = [
  ['开场', 3.0, open],
  ['标题', 4.5, title],
  ['人物介绍', 3.6, profile],
  ['状态切换', ROUND_DURS[0] + ROUND_DURS[1], switching],
  ['小动作', 8.0, variety],
  ['形象', 4.0, looks],
  ['其余功能', 5.8, quick],
  ['结尾', 6.5, outro]
]
export const TIMELINE = []
let acc = 0
for (const [name, dur, draw] of CUTS) { TIMELINE.push({ name, dur, draw, start: acc, enter: acc ? 'wipe' : undefined }); acc += dur }
export const DURATION = acc

export function drawAt(ctx, t) {
  const i = Math.max(0, TIMELINE.findIndex(s => t < s.start + s.dur))
  const s = i < 0 ? TIMELINE[TIMELINE.length - 1] : TIMELINE[i]
  ctx.save()
  s.draw(ctx, t - s.start)
  ctx.restore()
  const next = TIMELINE[i + 1]
  if (next && next.enter === 'wipe' && t > next.start - 0.4) wipe(ctx, t - next.start, [C.orange, C.ink, C.cream], 0.4)
  if (s.enter === 'wipe' && t - s.start < 0.5) wipe(ctx, t - s.start, [C.orange, C.ink, C.cream], 0.4)
}
