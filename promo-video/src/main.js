// 预览和导出共用的入口。预览：浏览器里实时播放、可拖动进度；导出：render.mjs 调用 window.renderFrame(t)。

import { FPS, H, W } from './core.js'
import { init, loadPending, pending } from './assets.js'
import { DURATION, TIMELINE, cover, drawAt } from './scenes.js'
import { bubbleReady } from './story.js'

const canvas = document.getElementById('c')
canvas.width = W
canvas.height = H
const ctx = canvas.getContext('2d')
// 她的帧和气泡图画上去时都要缩小：默认的低质量缩放边缘会有细小的锯齿
ctx.imageSmoothingQuality = 'high'

async function fontsReady() {
  await Promise.all([
    document.fonts.load('700 100px "Bahnschrift"'),
    document.fonts.load('900 100px "Noto Sans SC"'),
    document.fonts.load('500 100px "Noto Sans SC"'),
    document.fonts.load('400 30px "Consolas"')
  ])
}

// 导出用：画到所有需要的帧都加载好为止，保证每一帧完整
window.renderFrame = async t => {
  for (let tries = 0; tries < 6; tries++) {
    pending.clear()
    ctx.clearRect(0, 0, W, H)
    drawAt(ctx, t)
    if (pending.size === 0) return true
    await loadPending()
  }
  return false
}
// 封面：同样等帧加载好
window.renderCover = async () => {
  for (let tries = 0; tries < 6; tries++) {
    pending.clear()
    ctx.clearRect(0, 0, W, H)
    cover(ctx)
    if (pending.size === 0) return true
    await loadPending()
  }
  return false
}
window.DURATION = DURATION
window.FPS = FPS

await init()
await bubbleReady
await fontsReady()
window.ready = true

// ---------- 预览 ----------
if (!new URLSearchParams(location.search).has('render')) {
  const bar = document.getElementById('bar')
  const label = document.getElementById('label')
  const seek = document.getElementById('seek')
  seek.max = DURATION
  let playing = true
  let t0 = performance.now() / 1000
  let pos = Number(new URLSearchParams(location.search).get('t') || 0)
  document.getElementById('play').onclick = () => {
    playing = !playing
    t0 = performance.now() / 1000 - pos
  }
  seek.oninput = () => {
    pos = Number(seek.value)
    t0 = performance.now() / 1000 - pos
  }
  const jump = document.getElementById('scenes')
  for (const s of TIMELINE) {
    const b = document.createElement('button')
    b.textContent = s.name
    b.onclick = () => { pos = s.start; t0 = performance.now() / 1000 - pos }
    jump.appendChild(b)
  }
  bar.hidden = false
  t0 = performance.now() / 1000 - pos
  const tick = () => {
    if (playing) pos = (performance.now() / 1000 - t0) % DURATION
    ctx.clearRect(0, 0, W, H)
    drawAt(ctx, pos)
    loadPending()
    seek.value = pos
    label.textContent = `${pos.toFixed(2)} / ${DURATION.toFixed(1)} s`
    requestAnimationFrame(tick)
  }
  tick()
}
