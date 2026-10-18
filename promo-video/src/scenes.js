// 分镜。每个场景是 draw(ctx, lt)，lt 是场景内的时间（秒）。
// 她出现的地方一律用 footage()：桌宠的实机帧原样播放，只缩放、放进画框，不加额外动作。

import { C, FONT, H, W, clamp, ease, hash, lerp, popText, prog, roundRect, text, typed, twos } from './core.js'
import { appWindow, chapter, cursor, flash, footage, halftone, pill, slab, speedLines, stamp, stripes, terminal, wipe } from './fx.js'

const A = id => `adult/${id}`
const Q = id => `chibi/${id}`

// ---------- 0. 开场：终端里敲下 claude ----------
function open(ctx, lt) {
  ctx.fillStyle = '#0e0d0c'
  ctx.fillRect(0, 0, W, H)
  const prompt = 'C:\\Users\\you> '
  const cmd = typed('claude', lt, 0.7, 9)
  const lines = [[prompt + cmd, C.cream]]
  if (lt > 1.7) lines.push(['', null], ['* Welcome to Claude Code', C.orange])
  if (lt > 2.5) lines.push(['', null], ['  …… 桌面的角落里，好像有人在等你。', C.mute])
  ctx.save()
  const k = ease.inOut(prog(lt, 3.3, 0.9))
  ctx.translate(W / 2, H / 2)
  ctx.scale(1 + k * 0.25, 1 + k * 0.25)
  ctx.translate(-W / 2, -H / 2)
  terminal(ctx, 360, 260, 1200, 560, lines, { size: 36, cursor: lt, title: 'Windows Terminal' })
  ctx.restore()
  wipe(ctx, lt - 4.2, [C.orange, C.cream], 0.45)
}

// ---------- 1. 标题 ----------
function title(ctx, lt) {
  ctx.fillStyle = C.cream
  ctx.fillRect(0, 0, W, H)
  halftone(ctx, 0, 0, 900, 600, C.orange2, { dir: 'tl', step: 26, maxR: 10 })
  slab(ctx, ease.expo(prog(lt, 0.0, 0.5)), C.ink, { y0: 860, y1: H })
  slab(ctx, ease.expo(prog(lt, 0.1, 0.5)), C.orange, { y0: 830, y1: 860 })
  // 实机画面从右侧推进来（推的是画框，她本身照常播放）
  const fk = ease.expo(prog(lt, 0.5, 0.7))
  if (lt > 0.5 && lt < 1.3) speedLines(ctx, lt, 1470, 520, { color: C.orange, alpha: 0.35 * (1 - prog(lt, 0.9, 0.4)) })
  footage(ctx, A('idle-loop'), lt, lerp(W + 40, 1250, fk), 70, 880)
  popText(ctx, 'Claude-Chan', 120, 470, lt, 0.25, { size: 230, family: FONT.title, weight: 700, stretch: 'condensed',
    color: C.ink, stagger: 0.035, shadow: { color: C.orange, dx: 10, dy: 10 } })
  popText(ctx, '陪你写代码的桌面小伙伴', 128, 600, lt, 0.9, { size: 72, color: C.ink, stagger: 0.04 })
  text(ctx, 'A DESKTOP COMPANION FOR CLAUDE CODE', 132, 680, { size: 30, family: FONT.title, weight: 600, color: C.deep,
    alpha: prog(lt, 1.6, 0.5), stretch: 'condensed' })
  text(ctx, 'WINDOWS  ·  FREE  ·  OPEN SOURCE', 132, 965, { size: 34, family: FONT.title, weight: 600, color: C.cream,
    alpha: prog(lt, 1.9, 0.5), stretch: 'condensed' })
}

// ---------- 2. 人物介绍卡 ----------
const PROFILE = [
  ['身份', 'Claude Code 的桌面伙伴'],
  ['性格', '稳重、安静，偶尔喝口茶'],
  ['特长', '看懂 Claude 在忙什么'],
  ['形象', '原版 ／ 冷脸萌 Q 版']
]
function profile(ctx, lt) {
  ctx.fillStyle = C.ink
  ctx.fillRect(0, 0, W, H)
  stripes(ctx, lt, C.ink2, { gap: 70, width: 30, speed: 40 })
  slab(ctx, 1, C.orange, { y0: 0, y1: H })
  ctx.fillStyle = C.ink
  ctx.beginPath(); ctx.moveTo(820, 0); ctx.lineTo(W, 0); ctx.lineTo(W, H); ctx.lineTo(820 - H * Math.tan(0.21), H); ctx.closePath(); ctx.fill()
  stripes(ctx, lt, C.ink2, { gap: 70, width: 30, speed: 40, alpha: 0.6 })
  halftone(ctx, 0, H - 420, 700, 420, C.deep, { dir: 'bl', step: 22, maxR: 8 })
  footage(ctx, A('idle-loop-2'), lt, 150, 80, 900)
  text(ctx, 'CHARACTER', 900, 190, { size: 34, family: FONT.title, weight: 600, color: C.orange, stretch: 'condensed', alpha: prog(lt, 0.2, 0.4) })
  popText(ctx, 'Claude-Chan', 896, 330, lt, 0.3, { size: 150, family: FONT.title, weight: 700, stretch: 'condensed', color: C.cream, stagger: 0.03 })
  PROFILE.forEach(([k, v], i) => {
    const t0 = 0.9 + i * 0.35
    const a = ease.out(prog(lt, t0, 0.4))
    if (a <= 0) return
    const y = 420 + i * 120
    ctx.save()
    ctx.globalAlpha = a
    ctx.translate((1 - a) * 60, 0)
    ctx.fillStyle = C.orange
    ctx.fillRect(900, y, 130, 72)
    text(ctx, k, 965, y + 50, { size: 36, weight: 900, color: C.ink, align: 'center' })
    text(ctx, v, 1060, y + 52, { size: 44, weight: 700, color: C.cream })
    ctx.restore()
  })
  text(ctx, '※ 片中她的动作，全部是桌宠的实机画面', 900, 1000, { size: 26, weight: 500, color: C.mute, alpha: prog(lt, 2.6, 0.6) })
}

// ---------- 3. 状态同步 ----------
const STATES = [
  { clip: A('thinking-loop'), off: 0, en: 'THINKING', zh: '思考中', cap: '你刚提完问题',
    lines: [['> 帮我把登录模块重构一下', C.mute], ['', null], ['* Thinking…', C.orange]] },
  { clip: A('reading-loop'), off: 0, en: 'READING', zh: '读代码', cap: 'Claude 在读文件',
    lines: [['* Read(src/auth/login.py)', C.cream], ['  └ Read 214 lines', C.mute]] },
  { clip: A('writing-loop'), off: 0, en: 'WRITING', zh: '写代码', cap: 'Claude 在改代码',
    lines: [['* Update(src/auth/login.py)', C.cream], ['  └ +42  -17', C.green]] },
  { clip: A('confirmation-loop'), off: 0, en: 'CONFIRM', zh: '等你确认', cap: 'Claude 需要你点头',
    lines: [['Bash command', C.orange], ['  uv run pytest tests/auth', C.cream], ['Do you want to proceed?', C.cream], ['> 1. Yes', C.orange], ['  2. No', C.mute]] },
  { clip: A('complete-loop'), off: 0, en: 'COMPLETE', zh: '完成！', cap: '任务做完了',
    lines: [['* 23 passed in 1.84s', C.green], ['', null], ['* 重构完成，补上了 6 个测试。', C.cream]] },
  { clip: A('error-intro'), off: 1.9, loop: false, en: 'ERROR', zh: '出错了', cap: '命令失败的时候',
    lines: [['* Bash(npm run build)', C.cream], ['  └ Error: exit code 1', C.red]] },
  { clip: A('event-waiting-watch'), off: 2.2, en: 'WAITING', zh: '等后台任务', cap: '任务在后台跑着',
    lines: [['* Bash(npm run build)', C.cream], ['  └ Running in the background', C.mute], ['', null], ['等它跑完…', C.mute]] },
  { clip: A('event-drowsy-bubble'), off: 3.6, en: 'DROWSY', zh: '打瞌睡', cap: '十分钟没有动静',
    lines: [['', null], ['（安静了很久）', C.mute]] }
]
export const STATE_DUR = 3.6
function states(ctx, lt) {
  const i = Math.min(STATES.length - 1, Math.floor(lt / STATE_DUR))
  const s = STATES[i]
  const st = lt - i * STATE_DUR
  ctx.fillStyle = C.cream
  ctx.fillRect(0, 0, W, H)
  stripes(ctx, lt, '#e7e0d2', { gap: 52, width: 18, speed: 25 })
  halftone(ctx, W - 640, 0, 640, 440, C.orange2, { dir: 'tr', step: 24, maxR: 8 })
  // 进度点
  STATES.forEach((_, j) => {
    ctx.fillStyle = j === i ? C.orange : j < i ? C.ink : '#cfc6b6'
    ctx.beginPath(); ctx.arc(110 + j * 34, 90, j === i ? 10 : 7, 0, Math.PI * 2); ctx.fill()
  })
  text(ctx, s.cap, 110, 160, { size: 44, weight: 900, color: C.ink, alpha: prog(st, 0.1, 0.3) })
  const shown = s.lines.map(([str, col], k) => [typed(str, st, 0.15 + k * 0.28, 40), col])
  terminal(ctx, 110, 230, 960, 470, shown, { size: 36, cursor: st })
  footage(ctx, s.clip, s.off + st, 1200, 80, 900, { loop: s.loop !== false })
  stamp(ctx, st, 0.55, 560, 900, s.en, s.zh, { rot: i % 2 ? 5 : -6 })
  // 状态之间的斜切：上一个状态的最后 0.4 秒开始盖，新状态的前 0.4 秒揭开
  if (i > 0) wipe(ctx, st, [C.orange, C.ink], 0.32)
  if (i < STATES.length - 1 && st > STATE_DUR - 0.45) wipe(ctx, st - STATE_DUR, [C.orange, C.ink], 0.32)
}

// ---------- 4. 看不出循环、随机小动作 ----------
const EVENTS = [
  [A('event-idle-tea'), '喝口茶', 0.6], [A('event-idle-flower'), '扶正发饰', 0.8], [A('event-writing-ink'), '蘸墨水', 1.2],
  [A('event-confirmation-wave'), '挥手提醒', 0.9], [A('event-idle-gaze'), '望向远方', 1.0], [A('event-thinking-ponder'), '沉思', 1.1]
]
function variety(ctx, lt) {
  ctx.fillStyle = C.paper
  ctx.fillRect(0, 0, W, H)
  halftone(ctx, 0, H - 460, 760, 460, C.orange2, { dir: 'bl', step: 24, maxR: 9 })
  footage(ctx, A('idle-loop'), lt, 130, 90, 880)
  popText(ctx, '一直轻轻摇晃，', 760, 200, lt, 0.2, { size: 70, stagger: 0.04 })
  popText(ctx, '看不出“又从头开始了”。', 760, 290, lt, 0.5, { size: 70, stagger: 0.04 })
  text(ctx, '偶尔，还会冒出二十多个随机小动作之一：', 764, 370, { size: 34, weight: 500, color: C.deep, alpha: prog(lt, 1.2, 0.4) })
  EVENTS.forEach(([clip, label, d], k) => {
    const a = ease.back(prog(lt, 1.4 + k * 0.12, 0.45))
    if (a <= 0) return
    const x = 764 + (k % 3) * 360
    const y = 410 + Math.floor(k / 3) * 320
    ctx.save()
    ctx.translate(x + 85, y + 140)
    ctx.scale(a, a)
    ctx.translate(-x - 85, -y - 140)
    footage(ctx, clip, lt + d, x, y, 280, { tag: false })
    pill(ctx, x + 168, y + 200, label, { size: 26 })
    ctx.restore()
  })
}

// ---------- 5. 不打扰你：五个功能 ----------
function featureHead(ctx, lt, num, title, sub) {
  ctx.fillStyle = C.orange
  ctx.fillRect(110, 70, 96, 96)
  text(ctx, num, 158, 145, { size: 66, family: FONT.title, weight: 700, color: C.ink, align: 'center', stretch: 'condensed' })
  popText(ctx, title, 236, 140, lt, 0.05, { size: 66, stagger: 0.035 })
  text(ctx, sub, 240, 210, { size: 32, weight: 500, color: C.mute, alpha: prog(lt, 0.4, 0.4) })
}

function featBackground(ctx, lt) {
  ctx.fillStyle = C.cream
  ctx.fillRect(0, 0, W, H)
  stripes(ctx, lt, '#ebe4d6', { gap: 52, width: 18, speed: 25 })
}

function featWaiting(ctx, lt) {
  featBackground(ctx, lt)
  featureHead(ctx, lt, '1', '后台任务也看得见', '后台命令、子代理跑完之前，她会时不时掏出怀表看一眼')
  const p = clamp(lt / 3.4)
  const bar = '█'.repeat(Math.round(p * 18)).padEnd(18, '░')
  terminal(ctx, 110, 300, 900, 420, [
    ['* Bash(npm run build)', C.cream], ['  └ Running in the background', C.mute], ['', null], [`  ${bar}  ${Math.round(p * 100)}%`, C.orange]
  ], { size: 32 })
  footage(ctx, A('event-waiting-watch'), lt + 2.2, 1220, 250, 790)
}

function featSessions(ctx, lt) {
  featBackground(ctx, lt)
  featureHead(ctx, lt, '2', '好几个会话一起看', 'Windows、WSL、桌面版同时开着也不乱；等你确认的排最前')
  const rows = [['Windows', 'api-server', '* Thinking…', C.orange], ['WSL', 'web-app', '* Update(app.tsx)', C.cream], ['桌面版', 'my-app', '> 等你确认', C.gold]]
  rows.forEach(([src, proj, line, col], k) => {
    const a = ease.out(prog(lt, 0.3 + k * 0.25, 0.4))
    if (a <= 0) return
    ctx.save()
    ctx.globalAlpha = a
    const y = 290 + k * 230
    terminal(ctx, 110 - (1 - a) * 80, y, 760, 190, [[line, col]], { size: 30, title: `${src}  ·  ${proj}` })
    ctx.restore()
    // 连线
    ctx.strokeStyle = k === 2 ? C.orange : '#cfc6b6'
    ctx.lineWidth = k === 2 ? 6 : 3
    ctx.setLineDash(k === 2 ? [] : [10, 10])
    ctx.beginPath(); ctx.moveTo(880, y + 95); ctx.lineTo(1180, 600); ctx.stroke()
    ctx.setLineDash([])
  })
  footage(ctx, A('confirmation-loop'), lt, 1220, 250, 790)
  // 桌宠在 confirmation 时头顶的气泡（桌宠本身就会显示项目名）
  const b = ease.back(prog(lt, 1.2, 0.4))
  if (b > 0) {
    ctx.save()
    ctx.translate(1442, 372)
    ctx.scale(b, b)
    ctx.fillStyle = '#fff'
    roundRect(ctx, -170, -34, 340, 64, 18); ctx.fill()
    ctx.fillStyle = C.orange
    roundRect(ctx, -158, -22, 70, 40, 8); ctx.fill()
    text(ctx, 'Win', -123, 7, { size: 22, weight: 900, color: '#fff', align: 'center' })
    text(ctx, 'my-app 在等你确认', -76, 10, { size: 26, weight: 900, color: '#3d2b1f' })
    ctx.restore()
  }
}

function featFollow(ctx, lt) {
  ctx.fillStyle = '#d9d2c4'
  ctx.fillRect(0, 0, W, H)
  featureHead(ctx, lt, '3', '贴着 Claude 窗口走', '打开“跟随 Claude 窗口”：窗口移到哪、她就跟到哪；最小化时一起藏起来')
  // 窗口沿路径移动、缩放；她贴在窗口右下角（窗口在动，她本身照常播放）
  const k = ease.inOut(prog(lt, 0.6, 2.4))
  const x = lerp(160, 760, k), y = lerp(300, 330, Math.sin(k * Math.PI))
  const w = lerp(980, 900, k), h = lerp(660, 620, k)
  appWindow(ctx, x, y, w, h, { title: 'Claude' })
  const ph = 330
  footage(ctx, A('idle-loop'), lt, x + w - 186 - 20, y + h - ph - 24, ph, { frame: false, tag: false })
  pill(ctx, x + w - 330, y + h + 20, '实机画面', { bg: C.ink, color: C.cream, size: 22 })
  cursor(ctx, x + 300, y + 22, 1.4, true)
}

function featFullscreen(ctx, lt) {
  ctx.fillStyle = '#d9d2c4'
  ctx.fillRect(0, 0, W, H)
  // 视频窗口展开成全屏，她自己藏起来；退出全屏后回来
  const k = ease.inOut(prog(lt, 0.9, 0.6)) * (1 - ease.inOut(prog(lt, 2.6, 0.6)))
  const hide = clamp(k * 1.6)
  footage(ctx, A('idle-loop'), lt, 1280, 300, 700, { alpha: 1 - hide })
  const wx = lerp(140, 0, k), wy = lerp(300, 0, k), ww = lerp(1000, W, k), wh = lerp(620, H, k)
  ctx.fillStyle = '#111'
  roundRect(ctx, wx, wy, ww, wh, lerp(18, 0, k)); ctx.fill()
  ctx.fillStyle = C.cream
  ctx.beginPath(); ctx.moveTo(wx + ww / 2 - 40, wy + wh / 2 - 50); ctx.lineTo(wx + ww / 2 + 50, wy + wh / 2); ctx.lineTo(wx + ww / 2 - 40, wy + wh / 2 + 50); ctx.closePath(); ctx.fill()
  if (k > 0.98) text(ctx, '全屏看视频 · 打游戏', W / 2, H / 2 + 140, { size: 40, weight: 700, color: C.mute, align: 'center' })
  ctx.save()
  ctx.globalAlpha = 1 - k
  featureHead(ctx, lt, '4', '全屏时自动隐身', '有窗口全屏时她先躲起来，退出全屏再回来；隐藏时几乎不占 CPU')
  ctx.restore()
}

function featClick(ctx, lt) {
  ctx.fillStyle = '#d9d2c4'
  ctx.fillRect(0, 0, W, H)
  featureHead(ctx, lt, '5', '透明的地方，鼠标直接点穿', '只有她身上接收鼠标；旁边的空白处，点到的是下面的窗口')
  appWindow(ctx, 200, 300, 1300, 660, { title: '你的编辑器' })
  // 窗口里的按钮：被点穿后亮起来
  const clicked = lt > 2.0
  ctx.fillStyle = clicked ? C.orange : '#c9c0b0'
  roundRect(ctx, 720, 800, 220, 70, 14); ctx.fill()
  text(ctx, clicked ? '已点击 ✓' : '运行', 830, 846, { size: 30, weight: 900, color: clicked ? C.ink : '#6f675d', align: 'center' })
  footage(ctx, A('idle-loop'), lt, 1150, 330, 700, { frame: false, tag: false })
  pill(ctx, 1500, 960, '实机画面', { bg: C.ink, color: C.cream, size: 22 })
  // 指针移到她旁边的透明处，点下去
  const mk = ease.inOut(prog(lt, 0.6, 1.2))
  const cx = lerp(480, 820, mk), cy = lerp(560, 830, mk)
  const pressed = lt > 1.9 && lt < 2.15
  if (lt > 1.95) {
    const r = ease.out(prog(lt, 1.95, 0.5))
    ctx.strokeStyle = C.orange
    ctx.lineWidth = 6 * (1 - r)
    ctx.beginPath(); ctx.arc(cx, cy, 20 + r * 60, 0, Math.PI * 2); ctx.stroke()
  }
  cursor(ctx, cx, cy, 1.5, pressed)
}

export const FEATURES = [featWaiting, featSessions, featFollow, featFullscreen, featClick]
export const FEAT_DUR = 3.8
function features(ctx, lt) {
  const i = Math.min(FEATURES.length - 1, Math.floor(lt / FEAT_DUR))
  const st = lt - i * FEAT_DUR
  FEATURES[i](ctx, st)
  if (i > 0) wipe(ctx, st, [C.ink, C.orange], 0.32)
  if (i < FEATURES.length - 1 && st > FEAT_DUR - 0.45) wipe(ctx, st - FEAT_DUR, [C.ink, C.orange], 0.32)
}

// ---------- 6. 两种形象 ----------
function looks(ctx, lt) {
  ctx.fillStyle = C.cream
  ctx.fillRect(0, 0, W, H)
  ctx.fillStyle = C.orange
  ctx.beginPath(); ctx.moveTo(0, 0); ctx.lineTo(1060, 0); ctx.lineTo(860, H); ctx.lineTo(0, H); ctx.closePath(); ctx.fill()
  halftone(ctx, 0, 0, 900, 560, C.deep, { dir: 'tl', step: 24, maxR: 9 })
  halftone(ctx, W - 700, H - 460, 700, 460, C.orange2, { dir: 'br', step: 24, maxR: 9 })
  const a = ease.expo(prog(lt, 0.1, 0.6)), b = ease.expo(prog(lt, 0.3, 0.6))
  footage(ctx, A('idle-loop'), lt, lerp(-500, 160, a), 120, 860)
  const duck = lt > 3.4
  footage(ctx, duck ? Q('error-intro') : Q('idle-loop'), duck ? lt - 3.4 + 0.9 : lt, lerp(W + 40, 1240, b), 120, 860, { loop: !duck })
  popText(ctx, '原版', 660, 1010, lt, 0.5, { size: 64, color: C.ink })
  popText(ctx, 'Q 版 · 冷脸萌', 1250, 1040, lt, 0.7, { size: 52, color: C.ink })
  text(ctx, '设置里一键切换', W / 2 - 20, 90, { size: 40, weight: 900, color: C.ink, align: 'center', alpha: prog(lt, 1.0, 0.4) })
  if (duck) stamp(ctx, lt, 3.9, 950, 330, 'DUCK & COVER', '出错时：抱头蹲防', { rot: 7, size: 76 })
}

// ---------- 7. 结尾 ----------
function outro(ctx, lt) {
  ctx.fillStyle = C.ink
  ctx.fillRect(0, 0, W, H)
  stripes(ctx, lt, C.ink2, { gap: 70, width: 30, speed: 40 })
  halftone(ctx, W - 760, H - 520, 760, 520, C.deep, { dir: 'br', step: 24, maxR: 9 })
  const cmds = [
    ['> claude plugin marketplace add Ivanfangsc/claude-chan', 0.3],
    ['> claude plugin install claude-chan@claude-chan', 2.0]
  ]
  const lines = cmds.map(([c, t0]) => [typed(c, lt, t0, 30), C.cream])
  lines.push(['', null])
  if (lt > 3.6) lines.push(['* Installed claude-chan@claude-chan', C.green])
  const up = ease.inOut(prog(lt, 4.2, 0.7))
  ctx.save()
  ctx.translate(0, -up * 330)
  ctx.globalAlpha = 1 - up * 0.65
  terminal(ctx, 260, 330, 1400, 360, lines, { size: 34, cursor: lt < 4 ? lt : null })
  ctx.restore()
  if (lt > 4.4) {
    footage(ctx, A('complete-loop'), lt, 80, 300, 600, { tag: false, alpha: ease.out(prog(lt, 4.4, 0.6)) })
    footage(ctx, Q('complete-loop'), lt, W - 80 - 338, 300, 600, { tag: false, alpha: ease.out(prog(lt, 4.6, 0.6)) })
  }
  popText(ctx, 'Claude-Chan', W / 2, 590, lt, 4.7, { size: 160, family: FONT.title, weight: 700, stretch: 'condensed',
    color: C.cream, stagger: 0.03, align: 'center', shadow: { color: C.orange, dx: 9, dy: 9 } })
  text(ctx, '陪你把代码写完。', W / 2, 700, { size: 50, weight: 700, color: C.orange, align: 'center', alpha: prog(lt, 5.5, 0.5) })
  text(ctx, 'github.com/Ivanfangsc/claude-chan', W / 2, 790, { size: 38, family: FONT.mono, weight: 400, color: C.cream, align: 'center', alpha: prog(lt, 6.0, 0.5) })
  const cr = prog(lt, 6.6, 0.6)
  text(ctx, '人设：ZipZipPipe　·　视频生成工作流：黑鹤001　·　角色动画由 MiniMax H3 生成', W / 2, 960, { size: 24, weight: 500, color: C.mute, align: 'center', alpha: cr })
  text(ctx, '非 Anthropic 官方作品。Claude 是 Anthropic, PBC 的商标。', W / 2, 1004, { size: 24, weight: 500, color: C.mute, align: 'center', alpha: cr })
  // 最后一秒淡出
  const out = prog(lt, 9.0, 1.0)
  if (out > 0) { ctx.fillStyle = `rgba(0,0,0,${out})`; ctx.fillRect(0, 0, W, H) }
}

// ---------- 时间线 ----------
const chap = (num, t, en) => (ctx, lt) => chapter(ctx, lt, num, t, en)
export const TIMELINE = [
  { name: '开场', dur: 4.5, draw: open },
  { name: '标题', dur: 6.5, draw: title },
  { name: '人物介绍', dur: 7.5, draw: profile, enter: 'wipe' },
  { name: '#01', dur: 1.7, draw: chap('#01', '跟着 Claude Code 一起忙', 'SYNCED WITH CLAUDE CODE'), enter: 'flash' },
  { name: '状态', dur: STATES.length * STATE_DUR, draw: states, enter: 'wipe' },
  { name: '#02', dur: 1.7, draw: chap('#02', '待多久都不腻', 'NO VISIBLE LOOP'), enter: 'flash' },
  { name: '小动作', dur: 6.8, draw: variety, enter: 'wipe' },
  { name: '#03', dur: 1.7, draw: chap('#03', '不打扰你干活', 'STAYS OUT OF YOUR WAY'), enter: 'flash' },
  { name: '功能', dur: FEATURES.length * FEAT_DUR, draw: features, enter: 'wipe' },
  { name: '#04', dur: 1.7, draw: chap('#04', '两种形象', 'TWO LOOKS'), enter: 'flash' },
  { name: '形象', dur: 7.6, draw: looks, enter: 'wipe' },
  { name: '结尾', dur: 10, draw: outro, enter: 'wipe' }
]
let acc = 0
for (const s of TIMELINE) { s.start = acc; acc += s.dur }
export const DURATION = acc

export function drawAt(ctx, t) {
  const i = Math.max(0, TIMELINE.findIndex(s => t < s.start + s.dur))
  const s = i < 0 ? TIMELINE[TIMELINE.length - 1] : TIMELINE[i]
  ctx.save()
  s.draw(ctx, t - s.start)
  ctx.restore()
  // 场景之间：斜切色块（进入新场景的前 0.35 秒从上一场景的末尾就开始盖）或白闪
  const next = TIMELINE[i + 1]
  if (next && next.enter === 'wipe' && t > next.start - 0.4) wipe(ctx, t - next.start, [C.orange, C.ink, C.cream], 0.4)
  if (s.enter === 'wipe' && t - s.start < 0.5) wipe(ctx, t - s.start, [C.orange, C.ink, C.cream], 0.4)
  if (s.enter === 'flash') flash(ctx, t - s.start, 0, 0.2)
}
