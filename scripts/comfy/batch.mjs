#!/usr/bin/env node
// 按顺序批量生成：每个任务 生成 → 拼接抠图 → 检测 → 脸部检查图。一个失败不影响后面的任务。
//
//   node scripts/comfy/batch.mjs thinking-L reading-L t-hub-A-to-B ...
//   加 --lora 使用加速 LoRA
//
// loop 要先于过渡处理：loop 的首帧会成为该状态的标准帧，过渡再对齐到它。

import { spawnSync } from 'node:child_process'
import { ASSETS_DIR } from './skin.mjs'
import { JOBS } from './jobs.mjs'

const PY = process.env.COMFY_PYTHON ?? 'D:/comfy/.venv/Scripts/python.exe'
const args = process.argv.slice(2)
const lora = args.includes('--lora') ? ['--lora'] : []
const names = args.filter(a => !a.startsWith('--'))

const MAX_TRIES = 3 // 切镜头、背景漂移时换种子重试（finish.py 以退出码 3 表示片段不可用）

const exec = (cmd, argv) => spawnSync(cmd, argv, { stdio: 'inherit', env: { ...process.env, PYTHONIOENCODING: 'utf-8' } }).status
const run = (cmd, argv) => exec(cmd, argv) === 0

const started = Date.now()
const failed = []
for (const [i, name] of names.entries()) {
  const job = JOBS[name]
  if (!job) {
    console.log(`\n### 跳过未知任务 ${name}`)
    failed.push(name)
    continue
  }
  console.log(`\n### [${i + 1}/${names.length}] ${name}`)
  const loop = !job.transition
  const target = loop ? ['loop', job.state, '--job', name] : ['transition', job.transition, '--job', name]
  if (job.out) target.push('--out', job.out)
  let ok = false
  for (let attempt = 1; attempt <= MAX_TRIES && !ok; attempt++) {
    if (attempt > 1) console.log(`
### ${name} 第 ${attempt} 次尝试（上一次不可用）`)
    if (!run('node', ['scripts/comfy/generate.mjs', name, ...lora])) break
    const status = exec(PY, ['scripts/comfy/finish.py', ...target])
    ok = status === 0
    if (status !== 0 && status !== 3) break // 其他错误不重试
  }
  if (!ok) {
    failed.push(name)
    continue
  }
  if (loop) {
    const file = job.out ?? `claude-girl-loop-${job.state}-transparent-9x16.webm`
    run('uv', ['run', 'python', 'scripts/analyze_loop.py', `${ASSETS_DIR}/videos/loops/${file}`, '--as', job.state])
  }
  run(PY, ['scripts/comfy/contact.py', name])
}
console.log(`\n### 全部完成，用时 ${Math.round((Date.now() - started) / 60000)} 分钟${failed.length ? `；失败：${failed.join('、')}` : ''}`)
