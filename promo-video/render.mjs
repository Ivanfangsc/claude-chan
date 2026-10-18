// 导出：无头 Chrome 逐帧调用 window.renderFrame(t)，PNG 送进 ffmpeg 编码成 MP4。
//
//   node render.mjs                              # 整片 → out/claude-chan-promo.mp4（无声）
//   node render.mjs --stills 2.6,14.5,33          # 指定时间点的静帧 → out/stills/
//   node render.mjs --sheet                       # 每个场景抽几帧拼成一张总览图 → out/sheet.png
//   node render.mjs --music 文件.mp3              # 整片并合进配乐（结尾 2 秒淡出）
//   node render.mjs --from 20 --to 50            # 只导出一段（调试用）
//
// 需要 Chrome（或 Edge）和 ffmpeg：ffmpeg 用环境变量 FFMPEG 指定，默认在 PATH 里找。

import { spawn } from 'node:child_process'
import { createReadStream, existsSync, mkdirSync, writeFileSync } from 'node:fs'
import { createServer } from 'node:http'
import { extname, join, normalize } from 'node:path'
import { fileURLToPath } from 'node:url'
import puppeteer from 'puppeteer-core'

const ROOT = fileURLToPath(new URL('.', import.meta.url))
const args = process.argv.slice(2)
const opt = name => (args.includes(name) ? args[args.indexOf(name) + 1] : null)
const CHROME = process.env.CHROME ?? ['C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'].find(existsSync)
const FFMPEG = process.env.FFMPEG ?? 'ffmpeg'

const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.json': 'application/json', '.webp': 'image/webp', '.png': 'image/png' }
const server = createServer((req, res) => {
  const path = normalize(join(ROOT, decodeURIComponent(new URL(req.url, 'http://x').pathname)))
  if (!path.startsWith(normalize(ROOT)) || !existsSync(path)) { res.writeHead(404); res.end(); return }
  res.writeHead(200, { 'Content-Type': TYPES[extname(path)] ?? 'application/octet-stream' })
  createReadStream(path).pipe(res)
}).listen(0)
const port = server.address().port

const browser = await puppeteer.launch({ executablePath: CHROME, headless: true, args: ['--force-color-profile=srgb', '--hide-scrollbars'] })
const page = await browser.newPage()
await page.setViewport({ width: 1920, height: 1080, deviceScaleFactor: 1 })
page.on('pageerror', e => console.error('页面错误：', e.message))
await page.goto(`http://localhost:${port}/index.html?render=1`)
await page.waitForFunction('window.ready === true', { timeout: 60_000 })
const { DURATION, FPS } = await page.evaluate(() => ({ DURATION: window.DURATION, FPS: window.FPS }))
const canvas = await page.$('#c')

async function shot(t) {
  const ok = await page.evaluate(tt => window.renderFrame(tt), t)
  if (!ok) console.warn(`第 ${t.toFixed(2)} 秒有帧没加载完`)
  return canvas.screenshot({ type: 'png' })
}

mkdirSync(join(ROOT, 'out'), { recursive: true })

if (args.includes('--stills')) {
  mkdirSync(join(ROOT, 'out/stills'), { recursive: true })
  for (const t of opt('--stills').split(',').map(Number)) {
    writeFileSync(join(ROOT, 'out/stills', `${t.toFixed(1)}.png`), await shot(t))
  }
  console.log('静帧在 out/stills/')
} else if (args.includes('--sheet')) {
  const times = await page.evaluate(() => {
    // 每个场景取 30%、75% 两个时间点
    const out = []
    return import('./src/scenes.js').then(m => { for (const s of m.TIMELINE) out.push(s.start + s.dur * 0.3, s.start + s.dur * 0.75); return out })
  })
  const pngs = []
  for (const t of times) pngs.push((await shot(t)).toString('base64'))
  const sheet = await page.evaluate(async (list, ts) => {
    const cw = 480, ch = 270, cols = 4
    const g = new OffscreenCanvas(cw * cols, ch * Math.ceil(list.length / cols))
    const gc = g.getContext('2d')
    for (let k = 0; k < list.length; k++) {
      const bmp = await createImageBitmap(await (await fetch('data:image/png;base64,' + list[k])).blob())
      gc.drawImage(bmp, (k % cols) * cw, Math.floor(k / cols) * ch, cw, ch)
      gc.fillStyle = '#000'; gc.fillRect((k % cols) * cw, Math.floor(k / cols) * ch, 64, 22)
      gc.fillStyle = '#fff'; gc.font = '16px sans-serif'; gc.fillText(ts[k].toFixed(1), (k % cols) * cw + 6, Math.floor(k / cols) * ch + 16)
    }
    const blob = await g.convertToBlob({ type: 'image/png' })
    return await new Promise(r => { const fr = new FileReader(); fr.onload = () => r(fr.result.split(',')[1]); fr.readAsDataURL(blob) })
  }, pngs, times)
  writeFileSync(join(ROOT, 'out/sheet.png'), Buffer.from(sheet, 'base64'))
  console.log('总览图在 out/sheet.png')
} else {
  const from = Number(opt('--from') ?? 0)
  const to = Number(opt('--to') ?? DURATION)
  const music = opt('--music')
  const out = join(ROOT, 'out', music ? 'claude-chan-promo.mp4' : 'claude-chan-promo-silent.mp4')
  const audio = music
    ? ['-i', music, '-map', '0:v', '-map', '1:a', '-c:a', 'aac', '-b:a', '192k', '-shortest',
       '-af', `afade=t=in:d=1,afade=t=out:st=${(to - from - 2).toFixed(2)}:d=2`]
    : []
  const ff = spawn(FFMPEG, ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(FPS), '-c:v', 'png', '-i', '-',
    ...audio, '-c:v', 'libx264', '-preset', 'slow', '-crf', '16', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', out],
    { stdio: ['pipe', 'inherit', 'inherit'] })
  const n = Math.round((to - from) * FPS)
  const started = Date.now()
  for (let i = 0; i < n; i++) {
    const buf = await shot(from + i / FPS)
    if (!ff.stdin.write(buf)) await new Promise(r => ff.stdin.once('drain', r))
    if (i % (FPS * 5) === 0) console.log(`${(i / FPS).toFixed(0)} / ${(n / FPS).toFixed(0)} 秒（${((Date.now() - started) / 1000).toFixed(0)} 秒）`)
  }
  ff.stdin.end()
  await new Promise(r => ff.on('close', r))
  console.log('输出：', out)
}

await browser.close()
server.close()
