// 剧情：一个人用 Claude Code 修 bug。先连着拍几秒（打字、回车、她开始思考），之后按配乐的拍子快切：
// 每一镜是终端的一个状态 + 她在对应状态里的一小段实机画面（不放完整段，只取最有动感的一两秒）。
// 桌面和终端是示意，用代码画；终端内容按 story.json（tools/simulate.py 生成的事件时间线）走，
// 她的帧原样播放；气泡是插件的气泡组件渲染的图（tools/bubble_png.py）。

import { C, FONT, H, W, ease, font, prog, roundRect, text, typed } from './core.js'
import { frameAt, info } from './assets.js'
import STORY from './story.json' with { type: 'json' }
import BUBBLE from '../frames/bubble.json' with { type: 'json' }

const TYPE_AT = 0.9 // 开始打字（剧情时间）
const SUBMIT_AT = 3.2 // 回车
const APPROVE_AT = STORY.approveAt // 选“允许”
const PROMPT = '登录页点了没反应，帮我看看'

// ---------- 分镜 ----------
// 画面始终是同一个桌面、同一个构图，不缩放不移动；切的是工作状态：每一镜换终端内容和她的动作。
// 片中时间都落在配乐《おしんこ》的小节 / 半小节上（一小节约 2.41 秒），22.83 主旋律进来时切到标题。
// at：片中开始时间；tag：她脚边的状态标签；ts：终端停在剧情的哪一刻；her：[片段, 从片段第几秒开始]；bubble：有没有气泡；click：鼠标按在“1. Yes”上
const OPEN_END = 5.74
const CUTS = [
  { at: 5.74, ts: 6.3, her: ['thinking-loop', 1.0], tag: '思考' }, // 思考
  { at: 7.04, ts: 8.0, her: ['thinking-to-reading', 1.7], tag: '思考 → 读代码' }, // 开始读文件
  { at: 8.34, ts: 9.6, her: ['reading-loop', 1.0], tag: '读代码' }, // 读代码
  { at: 9.6, ts: 11.7, her: ['reading-loop', 3.4], tag: '读代码' },
  { at: 10.87, ts: 13.2, her: ['reading-to-writing', 2.0], tag: '读代码 → 写代码' }, // 找到原因，开始改
  { at: 12.07, ts: 14.9, her: ['writing-loop', 0.8], tag: '写代码' }, // 写代码
  { at: 13.26, ts: 17.4, her: ['event-writing-ink', 4.0], tag: '写代码' },
  { at: 14.46, ts: 21.9, her: ['confirmation-intro', 2.4], bubble: true, tag: '等你确认' }, // 要确认：冒气泡
  { at: 15.65, ts: 60, her: ['event-confirmation-wave', 3.0], bubble: true, tag: '等你确认' }, // 还在等：招手
  { at: 16.85, ts: 102.95, her: ['confirmation-loop', 2.0], bubble: true, click: true, tag: '等你确认' }, // 点“允许”
  { at: 18.04, ts: 105.8, her: ['confirmation-outro', 2.0], tag: '等你确认 → 完成' }, // 测试通过
  { at: 19.24, ts: 107.3, her: ['complete-intro', 2.2], tag: '完成' }, // 修好了
  { at: 20.43, ts: 108.5, her: ['complete-intro', 3.6], tag: '完成' }
]
export const STORY_DUR = 22.83

// 她的窗口：放大到默认（345×613）的 1.4 倍，放在终端右边（气泡也按这个大小渲染）
const HER = { x: 1290, y: 172, w: 483, h: 858 }
function drawHer(ctx, clip, lt, alpha = 1) {
  const { n, fps } = info(clip)
  const bmp = frameAt(clip, Math.min(lt, (n - 1) / fps), false)
  if (!bmp) return
  ctx.save()
  ctx.globalAlpha = alpha
  ctx.drawImage(bmp, HER.x, HER.y, HER.w, HER.h)
  ctx.restore()
}

const bubbleImg = new Image()
export const bubbleReady = new Promise(r => { bubbleImg.onload = r; bubbleImg.src = 'frames/bubble.png' })
function drawBubble(ctx) {
  ctx.drawImage(bubbleImg, HER.x + BUBBLE.dx, HER.y + BUBBLE.dy, BUBBLE.w, BUBBLE.h)
}

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
function taskbar(ctx) {
  const active = 'term'
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
  text(ctx, '14:02', W - 70, H - 28, { size: 14, family: '"Segoe UI", sans-serif', weight: 400, color: '#eee', align: 'center' })
  text(ctx, '2026/10/20', W - 70, H - 10, { size: 13, family: '"Segoe UI", sans-serif', weight: 400, color: '#ccc', align: 'center' })
}

// ---------- 终端（Claude Code） ----------
const TERM = { x: 40, y: 36, w: 1200, h: 970 }
const TS = 25 // 字号
const LH = 37 // 行高
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
      for (const ln of wrapLine(ctx, `> ${a}`, width)) rows.push({ s: ln, col: '#cfcfcf', bg: '#3a3a3a', t: u.t })
    } else if (kind === 'say') {
      rows.push({ gap: true })
      wrapLine(ctx, a, width - 28).forEach((ln, i) => rows.push({ s: ln, col: FG, dot: i === 0 ? FG : null, indent: 28, t: u.t }))
    } else if (kind === 'tool') {
      rows.push({ gap: true })
      const done = ui.slice(k + 1).some(v => v.line[0] === 'result') || later
      rows.push({ s: `${a}(${b})`, col: FG, bold: true, dot: done ? GREEN : (Math.floor(ts * 3) % 2 ? FG : '#555'), indent: 28, t: u.t })
    } else if (kind === 'result') {
      rows.push({ s: `⎿  ${a}`, col: DIM, indent: 28, t: u.t })
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

// glow：切到这一镜后过了多久；这一镜里新出现的行（剧情时间在 glowFrom 之后）用橙色底闪一下
function terminal(ctx, ts, front, glow = null, glowFrom = 0) {
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
    if (glow !== null && r.t > glowFrom) {
      ctx.fillStyle = `rgba(217,119,87,${0.16 * (1 - ease.smooth(glow / 1.2))})`
      ctx.fillRect(x + 22, yy - LH + 8, w - 60, LH)
    }
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

// 鼠标指针
function pointer(ctx, x, y, down) {
  ctx.save()
  ctx.translate(x, y)
  const s = down ? 0.99 : 1.1
  ctx.scale(s, s)
  ctx.fillStyle = '#fff'; ctx.strokeStyle = '#111'; ctx.lineWidth = 1.6
  ctx.beginPath()
  ctx.moveTo(0, 0); ctx.lineTo(0, 24); ctx.lineTo(6.5, 18.5); ctx.lineTo(11, 28); ctx.lineTo(15, 26); ctx.lineTo(10.5, 17); ctx.lineTo(18, 17)
  ctx.closePath(); ctx.fill(); ctx.stroke()
  ctx.restore()
}
// 确认框里“1. Yes”那一行：到确认时内容已经满屏，确认框贴着终端底边
const YES = { x: TERM.x + 46 + 70, y: TERM.y + TERM.h - BOTTOM_PAD - ASK_H + 34 + 6 * LH - 7 }

// ---------- 画面 ----------
function desktop(ctx, ts, her, { bubble = false, click = false, typing = false, glow = null, glowFrom = 0 } = {}) {
  wallpaper(ctx)
  terminal(ctx, ts, typing, glow, glowFrom)
  for (const h of her) drawHer(ctx, ...h)
  if (bubble) drawBubble(ctx)
  taskbar(ctx)
  if (click) pointer(ctx, YES.x, YES.y, true)
}

// 她脚边的状态标签：状态变了才换字、弹一下
function stateTag(ctx, lt) {
  let label, since
  if (lt < OPEN_END) {
    const go = SUBMIT_AT - 0.55
    if (lt < go) return
    label = '思考'; since = lt - go
  } else {
    let i = CUTS.length - 1
    while (i > 0 && CUTS[i].at > lt) i--
    label = CUTS[i].tag
    // 只在状态变了的那一镜弹出来，同一个状态里切镜头不动
    let j = i
    while (j > 0 && CUTS[j - 1].tag === label) j--
    since = j === 0 && label === '思考' ? lt - (SUBMIT_AT - 0.55) : lt - CUTS[j].at
  }
  const pop = ease.back(prog(since, 0, 0.28))
  font(ctx, 34, FONT.cjk, 900)
  const w = ctx.measureText(label).width + 56
  const cx = HER.x + HER.w / 2, cy = 984
  ctx.save()
  ctx.translate(cx, cy)
  ctx.scale(0.6 + 0.4 * pop, 0.6 + 0.4 * pop)
  ctx.globalAlpha = Math.min(1, pop * 1.5)
  ctx.fillStyle = C.orange
  roundRect(ctx, -w / 2, -30, w, 60, 30); ctx.fill()
  text(ctx, label, 0, 2, { size: 34, weight: 900, color: C.ink, align: 'center', baseline: 'middle' })
  ctx.restore()
}

export function storyScene(ctx, lt) {
  if (lt < OPEN_END) {
    // 开头连着拍：打字、回车，她从待机交叉淡化进思考（和桌宠一样：待机一有动静就立刻离开）
    const ts = lt + 0.55 // 片中 2.65 秒（一拍上）回车 = 剧情里的 SUBMIT_AT
    const go = SUBMIT_AT - 0.55
    const her = lt < go ? [['adult/idle-loop', lt + 1.2]]
      : lt < go + 0.15 ? [['adult/idle-loop', lt + 1.2], ['adult/thinking-intro', lt - go, (lt - go) / 0.15]]
        : [['adult/thinking-intro', lt - go]]
    desktop(ctx, ts, her, { typing: true })
  } else {
    let i = CUTS.length - 1
    while (i > 0 && CUTS[i].at > lt) i--
    const c = CUTS[i]
    const prev = i > 0 ? CUTS[i - 1].ts : SUBMIT_AT + OPEN_END - 2.65
    desktop(ctx, c.ts, [[`adult/${c.her[0]}`, c.her[1] + lt - c.at]], { ...c, glow: lt - c.at, glowFrom: prev })
  }
  stateTag(ctx, lt)
  // 说明：她是实机，其余是示意
  font(ctx, 20, FONT.cjk, 700)
  const note = '她的动作和气泡为实机画面 · 桌面与终端为示意'
  const nw = ctx.measureText(note).width + 36
  ctx.fillStyle = 'rgba(20,20,20,0.72)'
  roundRect(ctx, W - nw - 28, 24, nw, 40, 20); ctx.fill()
  text(ctx, note, W - nw - 10, 51, { size: 20, weight: 700, color: '#eee' })
}
