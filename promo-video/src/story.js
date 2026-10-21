// 剧情：一个人用 Claude Code 修 bug，中途跑去看视频。桌面、终端、浏览器、鼠标是示意，用代码画；
// 她的每一帧按 story.json 播放——那是 tools/simulate.py 把同一串 hook 事件喂给插件真实的会话汇总和动画引擎算出来的，
// 所以她什么时候转身、播哪一段、招不招手，都和桌宠里一样。气泡是插件的气泡组件渲染的图（tools/bubble_png.py）。
//
// 片子分两个镜头，中间跳过她等你确认的一分多钟（任务栏时钟往前走，画面写“过了一会儿”）。
// 每个镜头内部是连续的真实时间。

import { C, FONT, H, W, clamp, ease, font, lerp, prog, roundRect, text, typed } from './core.js'
import { frameAt, info } from './assets.js'
import STORY from './story.json' with { type: 'json' }
import BUBBLE from '../frames/bubble.json' with { type: 'json' }

// ---------- 剪辑：片中时间 → 剧情时间 ----------
const SKIP = 1.4 // 两个镜头之间“过了一会儿”的长度
export const SHOTS = [
  { s0: 0, s1: 27.5 },
  { s0: 101.0, s1: 122.6 }
]
SHOTS[0].f0 = 0
SHOTS[1].f0 = SHOTS[0].s1 - SHOTS[0].s0 + SKIP
export const STORY_DUR = SHOTS[1].f0 + SHOTS[1].s1 - SHOTS[1].s0

// 用户的动作（剧情时间）：和 simulate.py 的事件对得上
const TYPE_AT = 0.9 // 开始打字
const SUBMIT_AT = 3.2 // 回车（UserPromptSubmit）
const BROWSER_AT = 8.6 // 切到浏览器看视频
const NOTICE_AT = 101.6 // 看到她在招手
const BUBBLE_CLICK_AT = 102.2 // 点气泡 → 终端回到最前面
const APPROVE_AT = STORY.approveAt // 选“允许”
const PROMPT = '登录页点了没反应，帮我看看'

// ---------- 她：按引擎记录播放 ----------
const CLIPS = STORY.clips
const XFADE = 0.15
// 剧情时间 ts 时这一段播到片段内第几秒（按记录的速度积分）
function localTime(c, ts) {
  let lt = 0
  for (let i = 0; i < c.rates.length; i++) {
    const [t0, r] = c.rates[i]
    const t1 = i + 1 < c.rates.length ? c.rates[i + 1][0] : Infinity
    if (ts <= t0) break
    lt += (Math.min(ts, t1) - t0) * r
  }
  return lt
}
function herAt(ts) {
  let i = CLIPS.length - 1
  while (i > 0 && CLIPS[i].t > ts) i--
  const cur = CLIPS[i]
  const out = [{ clip: `adult/${cur.clip}`, lt: localTime(cur, ts), alpha: 1 }]
  if (cur.xfade && i > 0 && ts - cur.t < XFADE) {
    const prev = CLIPS[i - 1]
    out[0].alpha = (ts - cur.t) / XFADE
    out.unshift({ clip: `adult/${prev.clip}`, lt: localTime(prev, ts), alpha: 1 })
  }
  return out
}

// 她的窗口（默认大小 345×613），贴在桌面右下角
const HER = { x: 1530, y: 400, w: 345, h: 613 }
function drawHer(ctx, ts) {
  for (const { clip, lt, alpha } of herAt(ts)) {
    const { n, fps } = info(clip)
    const bmp = frameAt(clip, Math.min(lt, (n - 1) / fps), false)
    if (!bmp) continue
    ctx.save()
    ctx.globalAlpha = alpha
    ctx.drawImage(bmp, HER.x, HER.y, HER.w, HER.h)
    ctx.restore()
  }
}

// 气泡：她在“等你确认”的目标上时显示（和桌宠一样，跟着目标走，不等动画）
const bubbleImg = new Image()
export const bubbleReady = new Promise(r => { bubbleImg.onload = r; bubbleImg.src = 'frames/bubble.png' })
function drawBubble(ctx, ts) {
  if (ts < STORY.askAt || ts >= APPROVE_AT) return
  const a = prog(ts, STORY.askAt, 0.12)
  ctx.save()
  ctx.globalAlpha = a
  ctx.drawImage(bubbleImg, HER.x + BUBBLE.dx, HER.y + BUBBLE.dy, BUBBLE.w, BUBBLE.h)
  ctx.restore()
}
const BUBBLE_RECT = { x: HER.x + BUBBLE.dx, y: HER.y + BUBBLE.dy, w: BUBBLE.w, h: BUBBLE.h - 9 }

// ---------- 桌面 ----------
function wallpaper(ctx) {
  const g = ctx.createLinearGradient(0, 0, W, H)
  g.addColorStop(0, '#3b4a5c')
  g.addColorStop(0.55, '#6d7f8f')
  g.addColorStop(1, '#c9b8a3')
  ctx.fillStyle = g
  ctx.fillRect(0, 0, W, H)
  // 远山
  ctx.fillStyle = 'rgba(30,38,48,0.35)'
  ctx.beginPath(); ctx.moveTo(0, 760)
  for (let x = 0; x <= W; x += 60) ctx.lineTo(x, 700 - 90 * Math.sin(x / 260) - 40 * Math.sin(x / 97))
  ctx.lineTo(W, H); ctx.lineTo(0, H); ctx.closePath(); ctx.fill()
}

const TASKBAR = 48
function taskbar(ctx, ts, active) {
  ctx.fillStyle = 'rgba(32,32,36,0.92)'
  ctx.fillRect(0, H - TASKBAR, W, TASKBAR)
  const icons = [['term', '#2b2b2b'], ['browser', '#3a7bd5']]
  icons.forEach(([id, col], i) => {
    const x = W / 2 - 40 + i * 56, y = H - TASKBAR + 8
    ctx.fillStyle = col
    roundRect(ctx, x, y, 32, 32, 7); ctx.fill()
    if (id === 'term') text(ctx, '>_', x + 16, y + 22, { size: 15, family: FONT.mono, weight: 700, color: '#ddd', align: 'center' })
    else { ctx.strokeStyle = '#fff'; ctx.lineWidth = 2.5; ctx.beginPath(); ctx.arc(x + 16, y + 16, 9, 0, Math.PI * 2); ctx.stroke() }
    ctx.fillStyle = id === active ? '#9ecbff' : '#888'
    roundRect(ctx, x + (id === active ? 8 : 12), H - 5, id === active ? 16 : 8, 3, 1.5); ctx.fill()
  })
  // 时钟：真实时间往前走
  const base = 14 * 60 + 2 // 14:02 开始
  const min = base + Math.floor((ts + 25) / 60)
  const hh = String(Math.floor(min / 60)).padStart(2, '0'), mm = String(min % 60).padStart(2, '0')
  text(ctx, `${hh}:${mm}`, W - 70, H - 28, { size: 14, family: '"Segoe UI", sans-serif', weight: 400, color: '#eee', align: 'center' })
  text(ctx, '2026/10/20', W - 70, H - 10, { size: 13, family: '"Segoe UI", sans-serif', weight: 400, color: '#ccc', align: 'center' })
}

// ---------- 终端（Claude Code） ----------
const TERM = { x: 70, y: 60, w: 1120, h: 900 }
const TS = 21 // 字号
const LH = 31 // 行高
const WELCOME_H = 110, INPUT_H = 72, ASK_H = 9 * LH + 30, BOTTOM_PAD = 24
const DIM = '#8b8b8b', FG = '#e6e6e6', ORANGE = '#d77757', GREEN = '#5fb870'

function wrapLine(ctx, str, width) {
  const out = []
  let cur = ''
  for (const ch of str) {
    if (ctx.measureText(cur + ch).width > width && cur) { out.push(cur); cur = ch.trimStart() } else cur += ch
  }
  if (cur) out.push(cur)
  return out
}

// 截至 ts 终端里该有的行：[文字, 颜色, 圆点颜色|null, 缩进]
function transcript(ctx, ts) {
  font(ctx, TS, FONT.mono, 400)
  const width = TERM.w - 110
  const rows = []
  const ui = STORY.ui.filter(u => u.t <= ts)
  ui.forEach((u, k) => {
    const [kind, a, b] = u.line
    const later = ui.slice(k + 1).some(v => v.line[0] === 'result')
    if (kind === 'you') {
      rows.push({ gap: true })
      for (const ln of wrapLine(ctx, `> ${a}`, width)) rows.push({ s: ln, col: '#cfcfcf', bg: '#3a3a3a' })
    } else if (kind === 'say') {
      rows.push({ gap: true })
      wrapLine(ctx, a, width - 28).forEach((ln, i) => rows.push({ s: ln, col: FG, dot: i === 0 ? FG : null, indent: 28 }))
    } else if (kind === 'tool') {
      rows.push({ gap: true })
      const done = ui.slice(k + 1).some(v => v.line[0] === 'result') || later
      rows.push({ s: `${a}(${b})`, col: FG, bold: true, dot: done ? GREEN : (Math.floor(ts * 3) % 2 ? FG : '#555'), indent: 28 })
    } else if (kind === 'result') {
      rows.push({ s: `⎿  ${a}`, col: DIM, indent: 28 })
    } else if (kind === 'approve') {
      // 确认框收起，什么都不留
    }
  })
  return rows
}

function permissionBox(ctx, x, y, w, ts) {
  const lines = [
    ['Bash command', FG, true],
    ['', FG],
    ['  npm test -- login', FG],
    ['  Run login tests', DIM],
    ['', FG],
    ['Do you want to proceed?', FG],
    ['❯ 1. Yes', ORANGE],
    ['  2. Yes, and don\'t ask again for npm test commands', FG],
    ['  3. No, and tell Claude what to do differently (esc)', FG]
  ]
  const h = lines.length * LH + 30
  ctx.strokeStyle = ORANGE
  ctx.lineWidth = 2
  roundRect(ctx, x, y, w, h, 8); ctx.stroke()
  lines.forEach(([s, col, bold], i) => text(ctx, s, x + 22, y + 34 + i * LH, { size: TS, family: FONT.mono, weight: bold ? 700 : 400, color: col }))
  return h
}

function terminal(ctx, ts, front) {
  const { x, y, w, h } = TERM
  ctx.save()
  ctx.shadowColor = 'rgba(0,0,0,0.45)'; ctx.shadowBlur = 40; ctx.shadowOffsetY = 12
  ctx.fillStyle = '#1e1e1e'
  roundRect(ctx, x, y, w, h, 10); ctx.fill()
  ctx.restore()
  // 标题栏
  ctx.fillStyle = front ? '#2d2d2d' : '#262626'
  roundRect(ctx, x, y, w, 46, [10, 10, 0, 0]); ctx.fill()
  ctx.fillStyle = '#1e1e1e'
  roundRect(ctx, x + 12, y + 8, 300, 38, [8, 8, 0, 0]); ctx.fill()
  text(ctx, '>_  claude — shop-web', x + 30, y + 33, { size: 16, family: '"Segoe UI", sans-serif', weight: 400, color: '#ddd' })
  ;['—', '☐', '✕'].forEach((g, i) => text(ctx, g, x + w - 130 + i * 46, y + 30, { size: 15, family: '"Segoe UI", sans-serif', weight: 400, color: '#bbb', align: 'center' }))

  ctx.save()
  ctx.beginPath(); ctx.rect(x, y + 46, w, h - 46); ctx.clip()
  // 和真的命令行一样从上往下排：欢迎框 → 对话 → 进度 → 输入框（或确认框）；满了就整体往上滚
  const asking = ts >= STORY.askAt && ts < APPROVE_AT
  const working = ts >= SUBMIT_AT && !STORY.ui.some(u => u.t <= ts && u.line[0] === 'say' && u.line[1].startsWith('修好了'))
  const rows = transcript(ctx, ts)
  const top = y + 66
  let total = WELCOME_H
  for (const r of rows) total += r.gap ? 12 : LH
  if (working && !asking) total += LH + 10
  total += asking ? ASK_H + 16 : INPUT_H
  const scroll = Math.max(0, total - (h - 66 - BOTTOM_PAD))
  let yy = top - scroll
  // 欢迎框
  ctx.strokeStyle = ORANGE; ctx.lineWidth = 1.5
  roundRect(ctx, x + 30, yy + 4, 520, 92, 6); ctx.stroke()
  text(ctx, '✻ Welcome to Claude Code!', x + 52, yy + 40, { size: TS, family: FONT.mono, weight: 700, color: FG })
  text(ctx, '  cwd: C:\\work\\shop-web', x + 52, yy + 74, { size: TS, family: FONT.mono, weight: 400, color: DIM })
  yy += WELCOME_H
  for (const r of rows) {
    if (r.gap) { yy += 12; continue }
    yy += LH
    const rx = x + 30 + (r.indent || 0)
    if (r.bg) { ctx.fillStyle = r.bg; ctx.fillRect(x + 22, yy - LH + 8, w - 60, LH) }
    if (r.dot) { ctx.fillStyle = r.dot; ctx.beginPath(); ctx.arc(x + 40, yy - 7, 6, 0, Math.PI * 2); ctx.fill() }
    text(ctx, r.s, rx, yy, { size: TS, family: FONT.mono, weight: r.bold ? 700 : 400, color: r.col })
  }
  if (working && !asking) {
    yy += LH + 10
    const glyph = '✻✶✳✢·'[Math.floor(ts * 6) % 5]
    const secs = Math.floor(ts - SUBMIT_AT)
    const last = STORY.ui.filter(u => u.t <= ts && u.line[0] === 'tool').pop()
    const verb = !last ? 'Thinking' : { Read: 'Reading', Search: 'Reading', Update: 'Editing', Bash: 'Running' }[last.line[1]]
    text(ctx, `${glyph} ${verb}… (${secs}s · esc to interrupt)`, x + 30, yy, { size: TS, family: FONT.mono, weight: 400, color: ORANGE })
  }
  if (asking) {
    permissionBox(ctx, x + 24, yy + 16, w - 60, ts)
  } else {
    const by = yy + 10
    ctx.strokeStyle = '#5a5a5a'; ctx.lineWidth = 1.5
    roundRect(ctx, x + 24, by, w - 60, 52, 6); ctx.stroke()
    const typing = ts < SUBMIT_AT ? typed(PROMPT, ts, TYPE_AT, 7) : ''
    text(ctx, `> ${typing}`, x + 44, by + 34, { size: TS, family: FONT.mono, weight: 400, color: FG })
    if (front && Math.floor(ts * 2) % 2 === 0) {
      font(ctx, TS, FONT.mono, 400)
      const cw = ctx.measureText(`> ${typing}`).width
      ctx.fillStyle = '#ddd'; ctx.fillRect(x + 46 + cw, by + 14, 11, 26)
    }
  }
  ctx.restore()
}

// ---------- 浏览器（看视频） ----------
const BROWSER = { x: 600, y: 90, w: 880, h: 820 }
function browser(ctx, ts, front) {
  const { x, y, w, h } = BROWSER
  ctx.save()
  ctx.shadowColor = 'rgba(0,0,0,0.45)'; ctx.shadowBlur = 40; ctx.shadowOffsetY = 12
  ctx.fillStyle = '#f4f4f5'
  roundRect(ctx, x, y, w, h, 10); ctx.fill()
  ctx.restore()
  ctx.fillStyle = front ? '#e3e3e6' : '#ececee'
  roundRect(ctx, x, y, w, 84, [10, 10, 0, 0]); ctx.fill()
  ctx.fillStyle = '#fff'
  roundRect(ctx, x + 12, y + 8, 260, 34, [8, 8, 0, 0]); ctx.fill()
  text(ctx, '海边的一个下午 - 视频', x + 30, y + 31, { size: 15, weight: 500, color: '#333' })
  ctx.fillStyle = '#fff'
  roundRect(ctx, x + 80, y + 48, w - 120, 28, 14); ctx.fill()
  text(ctx, 'video.example.com/watch/sea-afternoon', x + 100, y + 67, { size: 14, family: '"Segoe UI", sans-serif', weight: 400, color: '#555' })
  // 播放器：缓慢流动的海
  const px = x + 30, py = y + 110, pw = w - 60, ph = pw * 9 / 16
  ctx.save()
  roundRect(ctx, px, py, pw, ph, 8); ctx.clip()
  const g = ctx.createLinearGradient(px, py, px, py + ph)
  g.addColorStop(0, '#f6c79a'); g.addColorStop(0.45, '#f2a477'); g.addColorStop(0.46, '#3f7fa3'); g.addColorStop(1, '#1d4863')
  ctx.fillStyle = g; ctx.fillRect(px, py, pw, ph)
  ctx.fillStyle = 'rgba(255,240,210,0.9)'
  ctx.beginPath(); ctx.arc(px + pw * 0.68, py + ph * 0.36, 34, 0, Math.PI * 2); ctx.fill()
  for (let k = 0; k < 7; k++) {
    ctx.strokeStyle = `rgba(255,255,255,${0.12 + k * 0.03})`; ctx.lineWidth = 2
    ctx.beginPath()
    for (let xx = 0; xx <= pw; xx += 20) {
      const yy = py + ph * (0.52 + k * 0.065) + 5 * Math.sin(xx / 70 + ts * (0.8 + k * 0.15) + k)
      xx ? ctx.lineTo(px + xx, yy) : ctx.moveTo(px + xx, yy)
    }
    ctx.stroke()
  }
  ctx.restore()
  // 进度条
  const p = clamp(0.18 + (ts - BROWSER_AT) / 600, 0, 1)
  ctx.fillStyle = 'rgba(255,255,255,0.35)'; ctx.fillRect(px + 16, py + ph - 18, pw - 32, 4)
  ctx.fillStyle = '#fb7299'; ctx.fillRect(px + 16, py + ph - 18, (pw - 32) * p, 4)
  text(ctx, '海边的一个下午｜4K 白噪音', px, py + ph + 44, { size: 24, weight: 700, color: '#18191c' })
  text(ctx, '12.4 万播放 · 2 天前', px, py + ph + 78, { size: 16, weight: 400, color: '#9499a0' })
  ctx.fillStyle = '#e3e5e7'
  for (let i = 0; i < 3; i++) { roundRect(ctx, px, py + ph + 110 + i * 40, pw * (0.9 - i * 0.2), 16, 8); ctx.fill() }
}

// ---------- 鼠标 ----------
// 确认框里“1. Yes”那一行（和 terminal() 里确认框的位置一致）
const ASK_BOX_Y = TERM.y + TERM.h - BOTTOM_PAD - ASK_H  // 到这时内容已经满屏，确认框贴着底
const YES = { x: TERM.x + 46 + 70, y: ASK_BOX_Y + 34 + 6 * LH - 7 }
// 用户的鼠标：[剧情时间, x, y, 是否按下]
const MOUSE = [
  [0, 900, 820], [BROWSER_AT - 0.7, 980, 1040], [BROWSER_AT - 0.1, 984, H - 24, 1], [BROWSER_AT + 0.4, 1060, 520],
  [NOTICE_AT - 2, 1060, 520], [NOTICE_AT, 1080, 520],
  [BUBBLE_CLICK_AT - 0.35, BUBBLE_RECT.x + 150, BUBBLE_RECT.y + 50], [BUBBLE_CLICK_AT, BUBBLE_RECT.x + 150, BUBBLE_RECT.y + 52, 1],
  [APPROVE_AT - 0.35, YES.x, YES.y], [APPROVE_AT, YES.x, YES.y, 1], [APPROVE_AT + 1.5, 380, 720]
]
function mouseAt(ts) {
  let i = 0
  while (i < MOUSE.length - 1 && MOUSE[i + 1][0] <= ts) i++
  const a = MOUSE[i], b = MOUSE[i + 1]
  if (!b) return { x: a[1], y: a[2], down: false }
  const k = ease.inOut((ts - a[0]) / (b[0] - a[0]))
  const down = (a[3] && ts - a[0] < 0.15) || false
  return { x: lerp(a[1], b[1], k), y: lerp(a[2], b[2], k), down }
}
function mouse(ctx, ts) {
  const m = mouseAt(ts)
  ctx.save()
  ctx.translate(m.x, m.y)
  const s = m.down ? 0.9 : 1
  ctx.scale(s * 1.1, s * 1.1)
  ctx.fillStyle = '#fff'; ctx.strokeStyle = '#111'; ctx.lineWidth = 1.6
  ctx.beginPath()
  ctx.moveTo(0, 0); ctx.lineTo(0, 24); ctx.lineTo(6.5, 18.5); ctx.lineTo(11, 28); ctx.lineTo(15, 26); ctx.lineTo(10.5, 17); ctx.lineTo(18, 17)
  ctx.closePath(); ctx.fill(); ctx.stroke()
  ctx.restore()
}

// ---------- 整个桌面 ----------
function desktop(ctx, ts) {
  wallpaper(ctx)
  const termFront = ts < BROWSER_AT || ts >= BUBBLE_CLICK_AT
  const showBrowser = ts >= BROWSER_AT
  if (termFront) {
    if (showBrowser) browser(ctx, ts, false)
    terminal(ctx, ts, true)
  } else {
    terminal(ctx, ts, false)
    browser(ctx, ts, true)
  }
  drawHer(ctx, ts)
  drawBubble(ctx, ts)
  taskbar(ctx, ts, termFront ? 'term' : 'browser')
  mouse(ctx, ts)
}

// ---------- 镜头 ----------
// [剧情时间, 中心 x, 中心 y, 缩放]，相邻关键帧之间缓动
const HERC = [HER.x + HER.w / 2, HER.y + HER.h * 0.45]
const CAM = [
  [0, W / 2, H / 2, 1], [SUBMIT_AT + 0.2, W / 2, H / 2, 1], [SUBMIT_AT + 1.6, 1180, 560, 1.18],
  [BROWSER_AT, 1100, 560, 1.12], [BROWSER_AT + 1.2, W / 2, H / 2, 1], [20.2, W / 2, H / 2, 1],
  [21.5, HERC[0] - 160, HERC[1] - 40, 1.75], [27.5, HERC[0] - 120, HERC[1] - 20, 1.9],
  [101.0, HERC[0] - 140, HERC[1] - 40, 1.8], [BUBBLE_CLICK_AT, HERC[0] - 160, HERC[1] - 40, 1.7],
  [BUBBLE_CLICK_AT + 0.9, 700, 600, 1.15], [APPROVE_AT + 4.2, 700, 620, 1.15],
  [109.0, W / 2 + 120, H / 2, 1.1], [112.0, HERC[0] - 140, HERC[1] - 10, 1.6], [122.6, HERC[0] - 120, HERC[1], 1.7]
]
function camAt(ts) {
  let i = 0
  while (i < CAM.length - 1 && CAM[i + 1][0] <= ts) i++
  const a = CAM[i], b = CAM[i + 1]
  if (!b) return a.slice(1)
  // 两个镜头之间不插值
  if (a[0] < SHOTS[0].s1 + 0.01 && b[0] >= SHOTS[1].s0) return a.slice(1)
  const k = ease.inOut((ts - a[0]) / (b[0] - a[0]))
  return [lerp(a[1], b[1], k), lerp(a[2], b[2], k), lerp(a[3], b[3], k)]
}

function storyTime(lt) {
  for (const s of SHOTS) if (lt >= s.f0 && lt < s.f0 + s.s1 - s.s0) return s.s0 + lt - s.f0
  return null
}

export function storyScene(ctx, lt) {
  const ts = storyTime(lt)
  if (ts === null) {
    // 镜头之间：过了一会儿
    const k = (lt - (SHOTS[0].f0 + SHOTS[0].s1 - SHOTS[0].s0)) / SKIP
    ctx.fillStyle = '#121212'
    ctx.fillRect(0, 0, W, H)
    text(ctx, '过了一会儿……', W / 2, H / 2 + 20, { size: 64, weight: 900, color: C.cream, align: 'center',
      alpha: ease.out(prog(k, 0.1, 0.3)) * (1 - ease.in(prog(k, 0.75, 0.25))) })
    return
  }
  const [cx, cy, z] = camAt(ts)
  ctx.save()
  ctx.translate(W / 2, H / 2)
  ctx.scale(z, z)
  ctx.translate(-clamp(cx, W / 2 / z, W - W / 2 / z), -clamp(cy, H / 2 / z, H - H / 2 / z))
  desktop(ctx, ts)
  ctx.restore()
  // 说明：她是实机，其余是示意
  ctx.save()
  font(ctx, 20, FONT.cjk, 700)
  const note = '她的动作和气泡为实机画面 · 桌面与终端为示意'
  const nw = ctx.measureText(note).width + 36
  ctx.fillStyle = 'rgba(20,20,20,0.72)'
  roundRect(ctx, 28, H - 66, nw, 40, 20); ctx.fill()
  text(ctx, note, 46, H - 39, { size: 20, weight: 700, color: '#eee' })
  ctx.restore()
  // 镜头开头淡入
  const fromShot = lt < SHOTS[1].f0 ? lt : lt - SHOTS[1].f0
  if (fromShot < 0.4) { ctx.fillStyle = `rgba(18,18,18,${1 - fromShot / 0.4})`; ctx.fillRect(0, 0, W, H) }
  // 第一个镜头结尾淡出到“过了一会儿”
  const toEnd = SHOTS[0].s1 - ts
  if (lt < SHOTS[1].f0 && toEnd < 0.5) { ctx.fillStyle = `rgba(18,18,18,${1 - toEnd / 0.5})`; ctx.fillRect(0, 0, W, H) }
}
