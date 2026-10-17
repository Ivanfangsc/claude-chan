#!/usr/bin/env node
// 模拟 Claude Code 的 http hook 事件，用来测试桌宠的防抖、优先级和多会话汇总。
// 不需要任何依赖，Windows 和 WSL 里都能直接运行（需要 Node 18+）。
//
//   node scripts/simulate.mjs <场景> [--url http://127.0.0.1:47800/event] [--speed 2]
//
// 场景：
//   basic         一轮完整对话：提问 → 读文件 → 改文件 → 完成
//   rapid-tools   快速连续调用 20 次工具（间隔 100–900ms），测试 PostToolUse 防抖
//   multi         WSL 和 Windows 的 3 个会话并发，其中一个等待权限确认
//   fail-burst    20 秒内连续 5 次工具失败，只有第一次播 error
//   stop-failure  回合以 StopFailure 结束，error 常驻直到下一次提问
//   interrupt     按 Esc 中断（没有 Stop），靠 Notification idle_prompt 回到 idle
//   confirm-tool  AskUserQuestion 工具等待用户回答
//   end           结束本脚本用过的所有模拟会话
//   raw <事件名> [JSON]   发送单个事件，例如：raw PreToolUse '{"tool_name":"Bash"}'

const args = process.argv.slice(2)
const opt = (name, fallback) => {
  const i = args.indexOf(name)
  if (i < 0) return fallback
  const v = args[i + 1]
  args.splice(i, 2)
  return v
}
const url = opt('--url', 'http://127.0.0.1:47800/event')
const speed = Number(opt('--speed', '1'))
const [scenario, ...rest] = args

const SESSIONS = {
  wsl: { session_id: 'sim-wsl-0001', cwd: '/home/me/pet-demo' },
  win: { session_id: 'sim-win-0002', cwd: 'C:\\Users\\me\\code\\web-app' },
  mnt: { session_id: 'sim-mnt-0003', cwd: '/mnt/c/work/data-pipeline' }
}

const sleep = ms => new Promise(r => setTimeout(r, ms / speed))
const rand = (a, b) => a + Math.random() * (b - a)
const t0 = Date.now()

async function send(who, hook_event_name, extra = {}) {
  const s = SESSIONS[who]
  const body = {
    ...s,
    transcript_path: `/tmp/${s.session_id}.jsonl`,
    permission_mode: 'default',
    hook_event_name,
    ...extra
  }
  const stamp = ((Date.now() - t0) / 1000).toFixed(1).padStart(5)
  const detail = extra.tool_name ?? extra.notification_type ?? ''
  try {
    const res = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
    const text = await res.text()
    console.log(`${stamp}s  ${who.padEnd(3)}  ${hook_event_name} ${detail}`.trimEnd() + (res.ok && text === '{}' ? '' : `  ← ${res.status} ${text}`))
  } catch (e) {
    console.error(`${stamp}s  发送失败：${e.cause?.code ?? e.message}（桌宠没开？）`)
    process.exit(1)
  }
}

/** 一次工具调用：PreToolUse → 执行 → PostToolUse */
async function tool(who, name, ms = 600, extra = {}) {
  await send(who, 'PreToolUse', { tool_name: name, tool_input: {}, ...extra })
  await sleep(ms)
  await send(who, 'PostToolUse', { tool_name: name, tool_input: {}, tool_response: {}, ...extra })
}

const scenarios = {
  async basic() {
    await send('wsl', 'SessionStart', { source: 'startup' })
    await sleep(2000)
    await send('wsl', 'UserPromptSubmit', { prompt: '帮我修个 bug' })
    await sleep(3000)
    await tool('wsl', 'Read', 1500)
    await sleep(400)
    await tool('wsl', 'Grep', 1500)
    await sleep(2500)
    await tool('wsl', 'Edit', 4000)
    await sleep(3000)
    await send('wsl', 'Stop')
  },

  async 'rapid-tools'() {
    await send('wsl', 'UserPromptSubmit', { prompt: '重构这个模块' })
    await sleep(1500)
    const tools = ['Read', 'Grep', 'Glob', 'Read', 'Edit', 'Bash']
    for (let i = 0; i < 20; i++) {
      await tool('wsl', tools[i % tools.length], rand(100, 400))
      await sleep(rand(100, 900))
    }
    await sleep(2000)
    await send('wsl', 'Stop')
  },

  async multi() {
    await Promise.all([
      (async () => {
        await send('wsl', 'UserPromptSubmit')
        for (let i = 0; i < 6; i++) await tool('wsl', i % 2 ? 'Edit' : 'Read', 2500), await sleep(1500)
        await send('wsl', 'Stop')
      })(),
      (async () => {
        await sleep(3000)
        await send('win', 'UserPromptSubmit')
        await sleep(2000)
        await send('win', 'PermissionRequest', { tool_name: 'Bash', tool_input: { command: 'npm publish' } })
        await send('win', 'Notification', { notification_type: 'permission_prompt', message: 'Claude needs your permission to use Bash' })
        await sleep(12000) // 用户过了 12 秒才点允许
        await send('win', 'PostToolUse', { tool_name: 'Bash' })
        await sleep(3000)
        await send('win', 'Stop')
      })(),
      (async () => {
        await sleep(6000)
        await send('mnt', 'UserPromptSubmit')
        await tool('mnt', 'WebSearch', 8000)
        await sleep(2000)
        await send('mnt', 'Stop')
      })()
    ])
  },

  async 'fail-burst'() {
    await send('wsl', 'UserPromptSubmit')
    for (let i = 0; i < 5; i++) {
      await send('wsl', 'PreToolUse', { tool_name: 'Bash' })
      await sleep(500)
      await send('wsl', 'PostToolUseFailure', { tool_name: 'Bash', error: 'exit code 1' })
      await sleep(3500)
    }
    await send('wsl', 'Stop')
  },

  async 'stop-failure'() {
    await send('wsl', 'UserPromptSubmit')
    await tool('wsl', 'Read', 2000)
    await sleep(1500)
    await send('wsl', 'StopFailure', { error: 'API Error: overloaded' })
    console.log('（error 应常驻；15 秒后再次提问）')
    await sleep(15000)
    await send('wsl', 'UserPromptSubmit')
    await sleep(3000)
    await send('wsl', 'Stop')
  },

  async interrupt() {
    await send('wsl', 'UserPromptSubmit')
    await send('wsl', 'PreToolUse', { tool_name: 'Edit' })
    console.log('（模拟按 Esc：没有 PostToolUse 和 Stop；真实情况下约 60 秒后才有 idle_prompt，这里等 8 秒）')
    await sleep(8000)
    await send('wsl', 'Notification', { notification_type: 'idle_prompt', message: 'Claude is waiting for your input' })
  },

  async 'confirm-tool'() {
    await send('win', 'UserPromptSubmit')
    await sleep(2000)
    await send('win', 'PreToolUse', { tool_name: 'AskUserQuestion' })
    await sleep(8000)
    await send('win', 'PostToolUse', { tool_name: 'AskUserQuestion' })
    await sleep(3000)
    await send('win', 'Stop')
  },

  async end() {
    for (const who of Object.keys(SESSIONS)) await send(who, 'SessionEnd', { reason: 'other' })
  },

  async raw() {
    const [name, json] = rest
    if (!name) throw new Error('用法：raw <事件名> [JSON]')
    await send('wsl', name, json ? JSON.parse(json) : {})
  }
}

const run = scenarios[scenario]
if (!run) {
  console.log(`可用场景：${Object.keys(scenarios).join('、')}`)
  process.exit(scenario ? 1 : 0)
}
await run()
