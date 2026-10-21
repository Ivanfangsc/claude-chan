// 分镜（约 1 分钟）：先是一段真实使用的剧情（story.js：她的反应是插件真实会做的），再是标题、两种形象、其余功能、结尾。
// 她出现的地方一律是实机帧原样播放，只缩放、放进画框，不加额外动作。

import { C, FONT, H, W, ease, lerp, popText, prog, roundRect, text } from './core.js'
import { footage, halftone, slab, speedLines, stripes, wipe } from './fx.js'
import { STORY_DUR, storyScene } from './story.js'

const A = id => `adult/${id}`
const Q = id => `chibi/${id}`
const BEAT = 0.604 // 配乐一拍

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

// ---------- 小动作：插在摇晃里 ----------
const ACTS = [A('event-idle-tea'), A('event-idle-flower'), A('event-idle-gaze')]
function variety(ctx, lt) {
  ctx.fillStyle = C.paper
  ctx.fillRect(0, 0, W, H)
  halftone(ctx, 0, H - 460, 760, 460, C.orange2, { dir: 'bl', step: 24, maxR: 9 })
  footage(ctx, A('idle-loop'), lt, 120, 100, 860)
  popText(ctx, '各种小动作，让她更加生动活泼', 700, 250, lt, 0.1, { size: 66, stagger: 0.035 })
  const ph = 540, pw = 540 * ph / 960
  ACTS.forEach((clip, k) => {
    const a = ease.back(prog(lt, 0.5 + k * 0.12, 0.4))
    if (a <= 0) return
    const x = 704 + k * (pw + 70), y = 400
    ctx.save()
    ctx.translate(x + pw / 2, y + ph / 2); ctx.scale(a, a); ctx.translate(-x - pw / 2, -y - ph / 2)
    // 小动作本身就是从摇晃里接出去、再接回摇晃的一段；从动作开始的地方播
    footage(ctx, clip, Math.max(0, lt - 0.5) + 1.2, x, y, ph, { tag: false })
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
    const a = ease.out(prog(lt, (k + 1) * BEAT, 0.3)) // 一拍一条
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
  const out = prog(lt, 3.8, 1.0)
  if (out > 0) { ctx.fillStyle = `rgba(0,0,0,${out})`; ctx.fillRect(0, 0, W, H) }
}

// ---------- 时间线 ----------
// 每段的长度（秒），按配乐《おしんこ》对过：约 99 BPM，一小节 2.41 秒，四小节一个乐句。
// 剧情快切的每一镜落在小节 / 半小节上，标题在主旋律进来时（22.83）出现，之后每段两小节左右。
const CUTS = [
  ['剧情', STORY_DUR, storyScene],
  ['标题', 4.82, title],
  ['小动作', 4.81, variety],
  ['形象', 3.58, looks],
  ['其余功能', 6.01, quick],
  ['结尾', 4.81, outro]
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

// ---------- 封面（不在时间线里，render.mjs --cover 单独导出）----------
// 16:9 和 4:3 共用一张：4:3 是从中间裁出 1440 宽（x 240–1680），字和她都放在这一块里，两边只有装饰。
// 缩成小图也要看得清：字大、只有三行；她用实机帧
const SAFE = (W - H * 4 / 3) / 2 // 240
export function cover(ctx) {
  ctx.fillStyle = C.cream
  ctx.fillRect(0, 0, W, H)
  halftone(ctx, 0, 0, 1100, 640, C.orange2, { dir: 'tl', step: 26, maxR: 10 })
  halftone(ctx, W - 520, 0, 520, 860, C.orange2, { dir: 'tr', step: 26, maxR: 10 })
  slab(ctx, 1, C.orange, { y0: 862, y1: 892 })
  slab(ctx, 1, C.ink, { y0: 892, y1: H })
  const x = SAFE + 40
  footage(ctx, A('idle-loop'), 0, W - SAFE - 30 - 540 * 960 / 960 * 0.98, 50, 940, { tag: false })
  popText(ctx, 'Claude-Chan', x - 6, 290, 10, 0, { size: 166, family: FONT.title, weight: 700, stretch: 'condensed',
    color: C.ink, shadow: { color: C.orange, dx: 9, dy: 9 } })
  text(ctx, 'Claude小姐现在在干嘛？', x, 450, { size: 72, weight: 900, color: C.ink })
  ctx.font = `900 76px ${FONT.cjk}`
  const ans = '看她就知道了'
  const w = ctx.measureText(ans).width + 64
  ctx.fillStyle = C.orange
  roundRect(ctx, x - 6, 508, w, 118, 18); ctx.fill()
  text(ctx, ans, x + 26, 567, { size: 76, weight: 900, color: C.ink, baseline: 'middle' })
  text(ctx, 'Claude Code 桌面伙伴 · 免费开源 · Windows', x, 996, { size: 35, weight: 900, color: C.cream })
}
