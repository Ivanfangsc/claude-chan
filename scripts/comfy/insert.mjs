#!/usr/bin/env node
// 批量生成插入式随机动作：E-<事件> 生成 → 插进摇晃 loop → 抠图 → 检测 → 脸部检查图。一个失败不影响后面的。
//
//   node scripts/comfy/insert.mjs idle-yawn thinking-tap ...
//
// 输出 resources/assets/videos/loops/claude-girl-event-<事件>-sway-transparent-9x16.webm（还没登记到 manifest）。

import { spawnSync } from 'node:child_process'
import { ASSETS_DIR } from './skin.mjs'
import { JOBS } from './jobs.mjs'

const PY = process.env.COMFY_PYTHON ?? 'D:/comfy/.venv/Scripts/python.exe'
const events = process.argv.slice(2)
const MAX_TRIES = 3 // 切镜头、背景漂移时换种子重来（finish.py 以退出码 3 表示片段不可用）

const exec = (cmd, argv) => spawnSync(cmd, argv, { stdio: 'inherit', env: { ...process.env, PYTHONIOENCODING: 'utf-8' } }).status
const run = (cmd, argv) => exec(cmd, argv) === 0

const started = Date.now()
const failed = []
for (const [i, event] of events.entries()) {
  const job = JOBS[`E-${event}`]
  console.log(`\n### [${i + 1}/${events.length}] ${event}`)
  if (!job) {
    failed.push(event)
    continue
  }
  const out = `claude-girl-event-${event}-sway-transparent-9x16.webm`
  let ok = false
  for (let attempt = 1; attempt <= MAX_TRIES && !ok; attempt++) {
    if (attempt > 1) console.log(`\n### ${event} 第 ${attempt} 次尝试（上一次不可用）`)
    if (!run('node', ['scripts/comfy/generate.mjs', `E-${event}`])) break
    if (!run('uv', ['run', 'python', 'scripts/comfy/assemble_loop.py', '--insert', event])) break
    const status = exec(PY, ['scripts/comfy/finish.py', 'loop', job.state, '--job', `E-${event}-L`, '--out', out])
    ok = status === 0
    if (status !== 0 && status !== 3) break
  }
  if (!ok) {
    failed.push(event)
    continue
  }
  run('uv', ['run', 'python', 'scripts/analyze_loop.py', `${ASSETS_DIR}/videos/loops/${out}`, '--as', job.state])
  run(PY, ['scripts/comfy/contact.py', `E-${event}`])
}
console.log(`\n### 全部完成，用时 ${Math.round((Date.now() - started) / 60000)} 分钟${failed.length ? `；失败：${failed.join('、')}` : ''}`)
