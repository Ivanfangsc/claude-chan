#!/usr/bin/env node
// 批量生成摇晃 loop 的眨眼版本：<状态>-MK2 生成 → 拼回 <状态>-ML → 抠图 → 检测。一个失败不影响后面的。
//
//   node scripts/comfy/blink.mjs thinking reading ...
//
// 输出 <素材目录>/videos/loops/claude-girl-loop-<状态>-sway-2-transparent-9x16.webm，登记为 <状态>-loop-2。

import { spawnSync } from 'node:child_process'
import { ASSETS_DIR } from './skin.mjs'

const PY = process.env.COMFY_PYTHON ?? 'D:/comfy/.venv/Scripts/python.exe'
const states = process.argv.slice(2)
const MAX_TRIES = 3

const exec = (cmd, argv) => spawnSync(cmd, argv, { stdio: 'inherit', env: { ...process.env, PYTHONIOENCODING: 'utf-8' } }).status
const run = (cmd, argv) => exec(cmd, argv) === 0

const started = Date.now()
const failed = []
for (const [i, state] of states.entries()) {
  console.log(`\n### [${i + 1}/${states.length}] ${state}`)
  const out = `claude-girl-loop-${state}-sway-2-transparent-9x16.webm`
  let ok = false
  for (let attempt = 1; attempt <= MAX_TRIES && !ok; attempt++) {
    if (attempt > 1) console.log(`\n### ${state} 第 ${attempt} 次尝试（上一次不可用）`)
    if (!run('node', ['scripts/comfy/generate.mjs', `${state}-MK2`])) break
    if (!run('uv', ['run', 'python', 'scripts/comfy/assemble_loop.py', state, '--blink', '2'])) break
    const status = exec(PY, ['scripts/comfy/finish.py', 'loop', state, '--job', `${state}-MLK2`, '--out', out])
    ok = status === 0
    if (status !== 0 && status !== 3) break
  }
  if (!ok) {
    failed.push(state)
    continue
  }
  run('uv', ['run', 'python', 'scripts/analyze_loop.py', `${ASSETS_DIR}/videos/loops/${out}`, '--as', state])
}
console.log(`\n### 全部完成，用时 ${Math.round((Date.now() - started) / 60000)} 分钟${failed.length ? `；失败：${failed.join('、')}` : ''}`)
