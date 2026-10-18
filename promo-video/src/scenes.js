// 分镜。每个场景是 draw(ctx, lt)，lt 是场景内的时间（秒）。
// 她出现的地方一律用 footage()：桌宠的实机帧原样播放，只缩放、放进画框，不加额外动作。
// 文案只讲效果，不出现命令、路径和技术名词。

import { C, FONT, H, W, clamp, ease, lerp, popText, prog, roundRect, text, typed } from './core.js'
import { appWindow, chapter, claudeWindow, cursor, flash, footage, footageTag, halftone, pill, slab, speedLines, stamp, stripes, wipe } from './fx.js'

const A = id => `adult/${id}`
const Q = id => `chibi/${id}`

// ---------- 0. 开场 ----------
function open(ctx, lt) {
  ctx.fillStyle = '#0e0d0c'
  ctx.fillRect(0, 0, W, H)
  const line1 = typed('今天也要写代码吗？', lt, 0.5, 9)
  const line2 = typed('有人陪着，会好一点。', lt, 2.0, 9)
  const k = ease.inOut(prog(lt, 3.4, 0.8))
  ctx.save()
  ctx.globalAlpha = 1 - k
  text(ctx, line1, W / 2, 470, { size: 64, weight: 700, color: C.cream, align: 'center' })
  text(ctx, line2, W / 2, 590, { size: 64, weight: 700, color: C.orange, align: 'center' })
  // 光标跟在正在打的那一行后面
  const cur = lt < 2.0 ? line1 : line2
  const cy = lt < 2.0 ? 470 : 590
  ctx.font = `700 64px ${FONT.cjk}`
  const cw = ctx.measureText(cur).width
  if (Math.floor(lt * 2) % 2 === 0) { ctx.fillStyle = C.orange; ctx.fillRect(W / 2 + cw / 2 + 10, cy - 52, 30, 62) }
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
  const fk = ease.expo(prog(lt, 0.5, 0.7))
  if (lt > 0.5 && lt < 1.3) speedLines(ctx, lt, 1470, 520, { color: C.orange, alpha: 0.35 * (1 - prog(lt, 0.9, 0.4)) })
  footage(ctx, A('idle-loop'), lt, lerp(W + 40, 1250, fk), 70, 880)
  popText(ctx, 'Claude-Chan', 120, 470, lt, 0.25, { size: 230, family: FONT.title, weight: 700, stretch: 'condensed',
    color: C.ink, stagger: 0.035, shadow: { color: C.orange, dx: 10, dy: 10 } })
  popText(ctx, '陪你写代码的桌面小伙伴', 128, 600, lt, 0.9, { size: 72, color: C.ink, stagger: 0.04 })
  text(ctx, 'A DESKTOP COMPANION FOR CLAUDE CODE', 132, 680, { size: 30, family: FONT.title, weight: 600, color: C.deep,
    alpha: prog(lt, 1.6, 0.5), stretch: 'condensed' })
  text(ctx, '免费  ·  开源  ·  Windows', 132, 968, { size: 36, weight: 700, color: C.cream, alpha: prog(lt, 1.9, 0.5) })
}

// ---------- 2. 人物介绍卡 ----------
const PROFILE = [
  ['身份', 'Claude Code 的桌面伙伴'],
  ['性格', '稳重、安静，偶尔喝口茶'],
  ['特长', '看懂 Claude 在忙什么'],
  ['形象', '原版 ／ Q 版']
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
  text(ctx, 'CHARACTER', 900, 190, { size: 34, family: FONT.title, weight: 600, color: C.orange, stretch: 'condensed', alpha: prog(lt, 0.2, 0.4) })
  popText(ctx, 'Claude-Chan', 896, 330, lt, 0.3, { size: 150, family: FONT.title, weight: 700, stretch: 'condensed', color: C.cream, stagger: 0.03 })
  PROFILE.forEach(([k, v], i) => {
    const a = ease.out(prog(lt, 0.9 + i * 0.35, 0.4))
    if (a <= 0) return
    const y = 420 + i * 120
    ctx.save()
    ctx.globalAlpha = a
    ctx.translate((1 - a) * 60, 0)
    ctx.fillStyle = C.orange
    ctx.fillRect(900, y, 130, 72)
    text(ctx, k, 965, y + 36, { size: 36, weight: 900, color: C.ink, align: 'center', baseline: 'middle' })
    text(ctx, v, 1060, y + 36, { size: 44, weight: 700, color: C.cream, baseline: 'middle' })
    ctx.restore()
  })
  text(ctx, '※ 片中她的动作，全部是桌宠的实机画面', 900, 1000, { size: 26, weight: 500, color: C.mute, alpha: prog(lt, 2.6, 0.6) })
}

// ---------- 3. 状态同步 ----------
const ME = { text: '你：帮我把登录功能整理一下', color: C.mute, size: 40, weight: 500 }
const STATES = [
  { clip: A('thinking-loop'), off: 0, en: 'THINKING', zh: '思考中', cap: '你刚提完问题',
    rows: [ME, { text: 'Claude 正在思考…', color: C.deep, gap: 18 }] },
  { clip: A('reading-loop'), off: 0, en: 'READING', zh: '读代码', cap: 'Claude 在看代码',
    rows: [ME, { text: 'Claude 正在读代码…', color: C.deep, gap: 18 }] },
  { clip: A('writing-loop'), off: 0, en: 'WRITING', zh: '写代码', cap: 'Claude 在动手改',
    rows: [ME, { text: 'Claude 正在改代码…', color: C.deep, gap: 18 }] },
  { clip: A('confirmation-loop'), off: 0, en: 'CONFIRM', zh: '等你确认', cap: 'Claude 需要你点头',
    rows: [{ text: 'Claude 想做一件事，需要你同意', color: C.ink }], buttons: [['同意', true], ['不同意', false]] },
  { clip: A('complete-loop'), off: 0, en: 'COMPLETE', zh: '完成！', cap: '事情做完了',
    rows: [ME, { text: '✓ 整理好了！', color: '#3f8a4a', gap: 18 }] },
  { clip: A('error-intro'), off: 1.9, loop: false, en: 'ERROR', zh: '出错了', cap: '遇到问题的时候',
    rows: [ME, { text: '✗ 这一步没成功', color: C.red, gap: 18 }] },
  { clip: A('event-waiting-watch'), off: 2.2, en: 'WAITING', zh: '等一等', cap: 'Claude 在后台忙',
    rows: [{ text: '后台的事情还在进行…', color: C.ink }], progress: true },
  { clip: A('event-drowsy-bubble'), off: 3.6, en: 'DROWSY', zh: '打瞌睡', cap: '很久没有动静',
    rows: [{ text: '（安静了好一会儿）', color: C.mute }] }
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
  STATES.forEach((_, j) => {
    ctx.fillStyle = j === i ? C.orange : j < i ? C.ink : '#cfc6b6'
    ctx.beginPath(); ctx.arc(120 + j * 34, 100, j === i ? 10 : 7, 0, Math.PI * 2); ctx.fill()
  })
  text(ctx, s.cap, 110, 190, { size: 56, weight: 900, color: C.ink, alpha: prog(st, 0.1, 0.3) })
  // 窗口里的字一行一行出来
  const rows = s.rows.map((r, k) => ({ ...r, text: typed(r.text, st, 0.15 + k * 0.45, 24) }))
  claudeWindow(ctx, 110, 300, 980, rows.map(r => ({ size: 54, ...r })), {
    buttons: s.buttons && st > 0.8 ? s.buttons : null,
    progress: s.progress ? clamp(st / 3.4) : null
  })
  footage(ctx, s.clip, s.off + st, 1200, 80, 900, { loop: s.loop !== false })
  stamp(ctx, st, 0.55, 560, 880, s.en, s.zh, { rot: i % 2 ? 5 : -6 })
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
  text(ctx, '偶尔，还会冒出二十多个小动作之一：', 764, 370, { size: 34, weight: 500, color: C.deep, alpha: prog(lt, 1.2, 0.4) })
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
  text(ctx, num, 158, 118, { size: 66, family: FONT.title, weight: 700, color: C.ink, align: 'center', baseline: 'middle', stretch: 'condensed' })
  popText(ctx, title, 236, 142, lt, 0.05, { size: 66, stagger: 0.035 })
  text(ctx, sub, 240, 214, { size: 34, weight: 500, color: C.mute, alpha: prog(lt, 0.4, 0.4) })
}

function featBackground(ctx, lt) {
  ctx.fillStyle = C.cream
  ctx.fillRect(0, 0, W, H)
  stripes(ctx, lt, '#ebe4d6', { gap: 52, width: 18, speed: 25 })
}

function featWaiting(ctx, lt) {
  featBackground(ctx, lt)
  featureHead(ctx, lt, '1', '后台在忙，她也知道', 'Claude 在后台做事的时候，她会时不时看一眼怀表')
  claudeWindow(ctx, 110, 330, 900, [{ text: '后台的事情还在进行…', color: C.ink }], { progress: clamp(lt / 3.4) })
  footage(ctx, A('event-waiting-watch'), lt + 2.2, 1220, 250, 790)
}

function featSessions(ctx, lt) {
  featBackground(ctx, lt)
  featureHead(ctx, lt, '2', '开好几个也不乱', '同时开好几个 Claude，她会提醒你哪一个在等你')
  const rows = [['项目 A', 'Claude 正在思考…', C.deep], ['项目 B', 'Claude 正在改代码…', C.deep], ['项目 C', '在等你确认', C.orange]]
  rows.forEach(([proj, line, col], k) => {
    const a = ease.out(prog(lt, 0.3 + k * 0.25, 0.4))
    if (a <= 0) return
    const y = 290 + k * 225
    ctx.save()
    ctx.globalAlpha = a
    claudeWindow(ctx, 110 - (1 - a) * 80, y, 760, [{ text: line, color: col, size: 36 }], { title: `Claude · ${proj}` })
    ctx.restore()
    ctx.strokeStyle = k === 2 ? C.orange : '#cfc6b6'
    ctx.lineWidth = k === 2 ? 6 : 3
    ctx.setLineDash(k === 2 ? [] : [10, 10])
    ctx.beginPath(); ctx.moveTo(880, y + 95); ctx.lineTo(1190, 620); ctx.stroke()
    ctx.setLineDash([])
  })
  footage(ctx, A('confirmation-loop'), lt, 1220, 250, 790)
  // 她头顶的气泡（桌宠在等你确认时本来就会显示是哪个项目）
  const b = ease.back(prog(lt, 1.2, 0.4))
  if (b > 0) {
    ctx.save()
    ctx.translate(1442, 372)
    ctx.scale(b, b)
    ctx.fillStyle = '#fff'
    roundRect(ctx, -150, -32, 300, 64, 18); ctx.fill()
    text(ctx, '项目 C 在等你确认', 0, 0, { size: 28, weight: 900, color: '#3d2b1f', align: 'center', baseline: 'middle' })
    ctx.restore()
  }
}

function featFollow(ctx, lt) {
  ctx.fillStyle = '#d9d2c4'
  ctx.fillRect(0, 0, W, H)
  featureHead(ctx, lt, '3', '贴着 Claude 窗口走', '窗口移到哪，她就跟到哪；窗口收起来，她也一起藏好')
  const k = ease.inOut(prog(lt, 0.6, 2.4))
  const x = lerp(160, 760, k), y = lerp(300, 330, Math.sin(k * Math.PI))
  const w = lerp(980, 900, k), h = lerp(660, 620, k)
  appWindow(ctx, x, y, w, h, { title: 'Claude' })
  const ph = 330
  footage(ctx, A('idle-loop'), lt, x + w - 186 - 20, y + h - ph - 24, ph, { frame: false, tag: false })
  footageTag(ctx, x + w - 190, y + h + 18)
  cursor(ctx, x + 300, y + 22, 1.4, true)
}

function featFullscreen(ctx, lt) {
  ctx.fillStyle = '#d9d2c4'
  ctx.fillRect(0, 0, W, H)
  const k = ease.inOut(prog(lt, 0.9, 0.6)) * (1 - ease.inOut(prog(lt, 2.6, 0.6)))
  const hide = clamp(k * 1.6)
  footage(ctx, A('idle-loop'), lt, 1280, 300, 700, { alpha: 1 - hide })
  const wx = lerp(140, 0, k), wy = lerp(300, 0, k), ww = lerp(1000, W, k), wh = lerp(620, H, k)
  ctx.fillStyle = '#111'
  roundRect(ctx, wx, wy, ww, wh, lerp(18, 0, k)); ctx.fill()
  ctx.fillStyle = C.cream
  ctx.beginPath(); ctx.moveTo(wx + ww / 2 - 40, wy + wh / 2 - 50); ctx.lineTo(wx + ww / 2 + 50, wy + wh / 2); ctx.lineTo(wx + ww / 2 - 40, wy + wh / 2 + 50); ctx.closePath(); ctx.fill()
  if (k > 0.98) text(ctx, '看视频 · 打游戏', W / 2, H / 2 + 140, { size: 40, weight: 700, color: C.mute, align: 'center' })
  ctx.save()
  ctx.globalAlpha = 1 - k
  featureHead(ctx, lt, '4', '全屏时自己躲起来', '看视频、打游戏的时候她先藏好，退出全屏再回来')
  ctx.restore()
}

function featClick(ctx, lt) {
  ctx.fillStyle = '#d9d2c4'
  ctx.fillRect(0, 0, W, H)
  featureHead(ctx, lt, '5', '不挡你点东西', '她身边的空白处，点到的是后面的窗口')
  appWindow(ctx, 200, 300, 1300, 660, { title: '你正在用的窗口' })
  // 后面窗口里的按钮，正好在她身边的空白处
  const clicked = lt > 2.0
  ctx.fillStyle = clicked ? C.orange : '#c9c0b0'
  roundRect(ctx, 1060, 420, 230, 70, 14); ctx.fill()
  text(ctx, clicked ? '点到了 ✓' : '按钮', 1175, 455, { size: 30, weight: 900, color: clicked ? C.ink : '#6f675d', align: 'center', baseline: 'middle' })
  footage(ctx, A('idle-loop'), lt, 1150, 330, 700, { frame: false, tag: false })
  footageTag(ctx, 1556, 386)
  // 她窗口的范围（虚线）：按钮有一半在这个范围里，照样点得到
  const ok = ease.out(prog(lt, 0.3, 0.4))
  ctx.save()
  ctx.globalAlpha = ok
  ctx.strokeStyle = C.deep
  ctx.lineWidth = 3
  ctx.setLineDash([14, 10])
  ctx.strokeRect(1150, 330, 394, 700)
  ctx.setLineDash([])
  ctx.restore()
  text(ctx, '她的窗口', 1556, 360, { size: 26, weight: 700, color: C.deep, alpha: ok })
  const mk = ease.inOut(prog(lt, 0.6, 1.2))
  const cx = lerp(620, 1200, mk), cy = lerp(700, 455, mk)
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
  footage(ctx, Q('idle-loop'), lt, lerp(W + 40, 1240, b), 120, 860)
  popText(ctx, '原版', 660, 1010, lt, 0.5, { size: 64, color: C.ink })
  popText(ctx, 'Q 版', 1250, 1040, lt, 0.7, { size: 64, color: C.ink })
  text(ctx, '想换就换', W / 2 - 20, 90, { size: 44, weight: 900, color: C.ink, align: 'center', alpha: prog(lt, 1.0, 0.4) })
}

// ---------- 7. 结尾 ----------
function outro(ctx, lt) {
  ctx.fillStyle = C.ink
  ctx.fillRect(0, 0, W, H)
  stripes(ctx, lt, C.ink2, { gap: 70, width: 30, speed: 40 })
  halftone(ctx, W - 760, H - 520, 760, 520, C.deep, { dir: 'br', step: 24, maxR: 9 })
  footage(ctx, A('complete-loop'), lt, 80, 240, 640, { tag: false, alpha: ease.out(prog(lt, 0.2, 0.6)) })
  footage(ctx, Q('complete-loop'), lt, W - 80 - 360, 240, 640, { tag: false, alpha: ease.out(prog(lt, 0.4, 0.6)) })
  popText(ctx, 'Claude-Chan', W / 2, 520, lt, 0.5, { size: 160, family: FONT.title, weight: 700, stretch: 'condensed',
    color: C.cream, stagger: 0.03, align: 'center', shadow: { color: C.orange, dx: 9, dy: 9 } })
  text(ctx, '陪你把代码写完。', W / 2, 630, { size: 52, weight: 700, color: C.orange, align: 'center', alpha: prog(lt, 1.3, 0.5) })
  const dl = prog(lt, 2.0, 0.5)
  if (dl > 0) {
    ctx.save()
    ctx.globalAlpha = dl
    font_(ctx)
    const label = '免费下载 · github.com/Ivanfangsc/claude-chan'
    const w = ctx.measureText(label).width + 80
    ctx.fillStyle = C.orange
    roundRect(ctx, W / 2 - w / 2, 700, w, 76, 38); ctx.fill()
    text(ctx, label, W / 2, 738, { size: 34, weight: 900, color: C.ink, align: 'center', baseline: 'middle' })
    ctx.restore()
  }
  const cr = prog(lt, 3.0, 0.6)
  text(ctx, '人设：ZipZipPipe　·　特别感谢：黑鹤001　·　角色动画由 AI 生成', W / 2, 960, { size: 24, weight: 500, color: C.mute, align: 'center', alpha: cr })
  text(ctx, '非 Anthropic 官方作品。Claude 是 Anthropic, PBC 的商标。', W / 2, 1004, { size: 24, weight: 500, color: C.mute, align: 'center', alpha: cr })
  const out = prog(lt, 7.0, 1.0)
  if (out > 0) { ctx.fillStyle = `rgba(0,0,0,${out})`; ctx.fillRect(0, 0, W, H) }
}
function font_(ctx) { ctx.font = `900 34px ${FONT.cjk}`; ctx.fontStretch = 'normal' }

// ---------- 时间线 ----------
const chap = (num, t, en) => (ctx, lt) => chapter(ctx, lt, num, t, en)
export const TIMELINE = [
  { name: '开场', dur: 4.5, draw: open },
  { name: '标题', dur: 6.5, draw: title },
  { name: '人物介绍', dur: 7.5, draw: profile, enter: 'wipe' },
  { name: '#01', dur: 1.7, draw: chap('#01', '跟着 Claude 一起忙', 'SYNCED WITH CLAUDE'), enter: 'flash' },
  { name: '状态', dur: STATES.length * STATE_DUR, draw: states, enter: 'wipe' },
  { name: '#02', dur: 1.7, draw: chap('#02', '待多久都不腻', 'NEVER GETS OLD'), enter: 'flash' },
  { name: '小动作', dur: 6.8, draw: variety, enter: 'wipe' },
  { name: '#03', dur: 1.7, draw: chap('#03', '不打扰你干活', 'STAYS OUT OF YOUR WAY'), enter: 'flash' },
  { name: '功能', dur: FEATURES.length * FEAT_DUR, draw: features, enter: 'wipe' },
  { name: '#04', dur: 1.7, draw: chap('#04', '两种形象', 'TWO LOOKS'), enter: 'flash' },
  { name: '形象', dur: 6.0, draw: looks, enter: 'wipe' },
  { name: '结尾', dur: 8, draw: outro, enter: 'wipe' }
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
  const next = TIMELINE[i + 1]
  if (next && next.enter === 'wipe' && t > next.start - 0.4) wipe(ctx, t - next.start, [C.orange, C.ink, C.cream], 0.4)
  if (s.enter === 'wipe' && t - s.start < 0.5) wipe(ctx, t - s.start, [C.orange, C.ink, C.cream], 0.4)
  if (s.enter === 'flash') flash(ctx, t - s.start, 0, 0.2)
}
