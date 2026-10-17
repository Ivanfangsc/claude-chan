#!/usr/bin/env node
// 批量生成持续动作的 loop：每个状态 <状态>-M（关键帧在中间）→ <状态>-MB（接缝）→ 拼接 → 抠图 → 检测 → 脸部检查图。
// 一个状态失败不影响后面的状态。
//
//   node scripts/comfy/sway.mjs thinking reading writing ...
//
// 输出 resources/assets/videos/loops/claude-girl-loop-<状态>-sway-transparent-9x16.webm（还没登记到 manifest）。

import { spawnSync } from 'node:child_process'
import { ASSETS_DIR } from './skin.mjs'

const PY = process.env.COMFY_PYTHON ?? 'D:/comfy/.venv/Scripts/python.exe'
const states = process.argv.slice(2)
const MAX_TRIES = 3 // 切镜头、背景漂移时从 M 开始整个重来（finish.py 以退出码 3 表示片段不可用）

const exec = (cmd, argv) => spawnSync(cmd, argv, { stdio: 'inherit', env: { ...process.env, PYTHONIOENCODING: 'utf-8' } }).status
const run = (cmd, argv) => exec(cmd, argv) === 0

const started = Date.now()
const failed = []
for (const [i, state] of states.entries()) {
  console.log(`\n### [${i + 1}/${states.length}] ${state}`)
  const out = `claude-girl-loop-${state}-sway-transparent-9x16.webm`
  let ok = false
  for (let attempt = 1; attempt <= MAX_TRIES && !ok; attempt++) {
    if (attempt > 1) console.log(`\n### ${state} 第 ${attempt} 次尝试（上一次不可用）`)
    if (!run('node', ['scripts/comfy/generate.mjs', `${state}-M`])) break
    if (!run('node', ['scripts/comfy/generate.mjs', `${state}-MB`])) break
    if (!run('uv', ['run', 'python', 'scripts/comfy/assemble_loop.py', state])) break
    const status = exec(PY, ['scripts/comfy/finish.py', 'loop', state, '--job', `${state}-ML`, '--out', out])
    ok = status === 0
    if (status !== 0 && status !== 3) break
  }
  if (!ok) {
    failed.push(state)
    continue
  }
  run('uv', ['run', 'python', 'scripts/analyze_loop.py', `${ASSETS_DIR}/videos/loops/${out}`, '--as', state])
  run(PY, ['scripts/comfy/contact.py', `${state}-ML`])
}
console.log(`\n### 全部完成，用时 ${Math.round((Date.now() - started) / 60000)} 分钟${failed.length ? `；失败：${failed.join('、')}` : ''}`)
