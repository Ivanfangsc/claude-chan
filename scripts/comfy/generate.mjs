#!/usr/bin/env node
// 通过 ComfyUI API 用 MiniMax H3 首尾帧工作流生成一段视频，输出 PNG 帧序列。
//
//   node scripts/comfy/generate.mjs <任务名>           # 任务定义见 jobs.mjs
//   node scripts/comfy/generate.mjs <任务名> --lora    # 用 4 步加速 LoRA（快约 3 倍，但动作幅度更大、结尾更容易偏离关键帧）
//   node scripts/comfy/generate.mjs --list
//
// 节点搭法照着 B 站 UP 主黑鹤001《MiniMaxH3全功能低显加速流》（BV14Zu16YERZ）工作流里的“首尾帧”组，
// 在此基础上加了 MiniMaxH3AddGuide（中间帧 / 多帧锚定）、RepeatImageBatch（定格）、参考图版（refs）和 PNG 帧输出。
//
// 768×1344，每段随机种子不同。默认按素材说明的原始设置：不用加速 LoRA，20 步；
// --lora 使用 4 步加速 LoRA（强度 0.75，同原工作流的首尾帧组）。输出无损 PNG，方便后续抠图（scripts/comfy/finish.py）。

import { existsSync, mkdirSync, readdirSync, renameSync, writeFileSync } from 'node:fs'
import { JOBS, COMMON_PROMPT, SHOT_PROMPT } from './jobs.mjs'
import { GEN_SUBDIR, SKIN, cyan } from './skin.mjs'

const COMFY = process.env.COMFY_URL ?? 'http://127.0.0.1:8188'
// 文本编码器：NVFP4（15.7 GB，RTX 50 系原生支持）比 int8（27 GB）省一半内存；COMFY_TE=int8 换回旧的
const TEXT_ENCODER =
  process.env.COMFY_TE === 'int8' ? 'qwen3vl_32b_minimax_h3_int8_convrot.safetensors' : 'qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors'
const COMFY_OUTPUT = process.env.COMFY_OUTPUT ?? `D:/comfy/ComfyUI/output/${GEN_SUBDIR}`
const args = process.argv.slice(2)
const useLora = args.includes('--lora')
const [name] = args.filter(a => !a.startsWith('--'))

if (!name || name === '--list') {
  for (const [k, j] of Object.entries(JOBS)) console.log(`${k.padEnd(24)} ${j.first} → ${j.last}  ${j.frames} 帧`)
  process.exit(0)
}
const job = JOBS[name]
if (!job) throw new Error(`没有这个任务：${name}`)

const seed = process.env.COMFY_SEED ? Number(process.env.COMFY_SEED) : Math.floor(Math.random() * 2 ** 48) // COMFY_SEED 固定种子（对比测试用）

const resize = image => ({
  class_type: 'ImageResizeKJv2',
  inputs: { image, width: 768, height: 1344, upscale_method: 'lanczos', keep_proportion: 'crop', pad_color: '0, 0, 0', crop_position: 'center', divisible_by: 32, device: 'cpu' }
})

const prompt = {
  unet: { class_type: 'UNETLoader', inputs: { unet_name: 'Minimax_H3\\minimax_h3_fl2va_pruned_int8_convrot.safetensors', weight_dtype: 'default' } },
  sage: { class_type: 'MiniMaxH3MemoryEfficientSageAttentionPatch', inputs: { model: ['unet', 0] } },
  clip: { class_type: 'CLIPLoader', inputs: { clip_name: TEXT_ENCODER, type: 'minimax', device: 'default' } },
  vae: { class_type: 'VAELoader', inputs: { vae_name: 'minimax_h3_video_vae_fp16.safetensors' } },
  first: { class_type: 'LoadImage', inputs: { image: cyan(job.first) } },
  last: { class_type: 'LoadImage', inputs: { image: cyan(job.last) } },
  firstResized: resize(['first', 0]),
  lastResized: resize(['last', 0]),
  i2v: {
    class_type: 'MiniMaxH3ImageToVideo',
    inputs: {
      clip: ['clip', 0], vae: ['vae', 0],
      prompt: `${SHOT_PROMPT}${job.prompt}${COMMON_PROMPT}`,
      width: 768, height: 1344, length: job.frames,
      first_frame: ['firstResized', 0], last_frame: ['lastResized', 0]
    }
  },
  lora: {
    class_type: 'LoraLoaderModelOnly',
    inputs: { model: ['sage', 0], lora_name: 'Minimax_H3\\minimax_h3_fl2v_lightx2v_turbo_4step_v0.1_comfy.safetensors', strength_model: 0.75 }
  },
  guider: { class_type: 'BasicGuider', inputs: { model: useLora ? ['lora', 0] : ['sage', 0], conditioning: ['i2v', 0] } },
  scheduler: { class_type: 'BasicScheduler', inputs: { model: ['unet', 0], scheduler: 'simple', steps: useLora ? 4 : 20, denoise: 1 } },
  sampler: { class_type: 'KSamplerSelect', inputs: { sampler_name: 'res_multistep' } },
  noise: { class_type: 'RandomNoise', inputs: { noise_seed: seed } },
  sample: {
    class_type: 'SamplerCustomAdvanced',
    inputs: { noise: ['noise', 0], guider: ['guider', 0], sampler: ['sampler', 0], sigmas: ['scheduler', 0], latent_image: ['i2v', 1] }
  },
  decode: { class_type: 'VAEDecode', inputs: { samples: ['sample', 0], vae: ['vae', 0] } },
  save: { class_type: 'SaveImage', inputs: { images: ['decode', 0], filename_prefix: `${GEN_SUBDIR}/${name}/frame` } }
}

if (!useLora) delete prompt.lora

// 没有首帧/尾帧的任务（关键帧锚在中间、或用一段已有的帧做引导）。
// 用引导的任务里 first/last 只是告诉 finish.py 两端对应哪张关键帧，不作为首尾帧输入。
if (!job.first || job.guides) { delete prompt.first; delete prompt.firstResized; delete prompt.i2v.inputs.first_frame }
if (!job.last || job.guides) { delete prompt.last; delete prompt.lastResized; delete prompt.i2v.inputs.last_frame }

// 参考图（<Picture 1>…）：锚定的帧里缺的外观信息（比如一直闭眼时的瞳色）从参考图里拿。
// 首尾帧模型直接用于 ref2va 效果差不多，所以不用换模型，只把条件节点换成 ReferenceToVideo，锚定照旧叠在上面。
if (job.refs?.length) {
  prompt.audioVae = { class_type: 'VAELoader', inputs: { vae_name: 'minimax_h3_audio_vae_fp32.safetensors' } }
  const refInputs = {}
  for (const [i, r] of job.refs.entries()) {
    prompt[`ref${i}`] = { class_type: 'LoadImage', inputs: { image: cyan(r) } }
    refInputs[`ref_images.ref_image_${i}`] = [`ref${i}`, 0]
  }
  prompt.i2v = {
    class_type: 'MiniMaxH3ReferenceToVideo',
    inputs: {
      clip: ['clip', 0], vae: ['vae', 0], audio_vae: ['audioVae', 0],
      prompt: prompt.i2v.inputs.prompt,
      width: 768, height: 1344, length: job.frames, ref_image_size: 'match',
      ...refInputs
    }
  }
}

// 引导：把一张关键帧或一段已生成的帧（22、39… 帧）锚在任意位置（负数从末尾算起）。
// 给模型看一段连续的动作而不是一张静止的图，它才会接上原来的速度，而不是从静止开始。
let positive = ['i2v', 0]
for (const [i, g] of (job.guides ?? []).entries()) {
  // start 为负数时从那一段的末尾往前数
  const start = g.from && g.start < 0 ? readdirSync(`${COMFY_OUTPUT}/${g.from}`).filter(f => f.endsWith('.png')).length + g.start : g.start
  prompt[`guideImage${i}`] = g.image
    ? { class_type: 'LoadImage', inputs: { image: cyan(g.image) } }
    : {
        class_type: 'LoadImagesFromFolderKJ',
        inputs: { folder: `${COMFY_OUTPUT}/${g.from}`, width: 768, height: 1344, keep_aspect_ratio: 'crop', image_load_cap: g.count, start_index: start, include_subfolders: false }
      }
  prompt[`guideResized${i}`] = resize([`guideImage${i}`, 0])
  // repeat：把一张图重复成一小段定格（比如一次性状态的关键帧），让模型减速停进去、从静止慢慢起步
  if (g.repeat) {
    prompt[`guideRepeat${i}`] = { class_type: 'RepeatImageBatch', inputs: { image: [`guideResized${i}`, 0], amount: g.repeat } }
  }
  const guideImage = g.repeat ? [`guideRepeat${i}`, 0] : [`guideResized${i}`, 0]
  prompt[`guide${i}`] = {
    class_type: 'MiniMaxH3AddGuide',
    inputs: { positive, vae: ['vae', 0], latent: ['i2v', 1], image: guideImage, frame_idx: g.at }
  }
  positive = [`guide${i}`, 0]
}
prompt.guider.inputs.conditioning = positive

// ComfyUI 保存时会在已有文件之后接着编号，旧帧留在目录里就会和新帧混在一起。
// 所以先把上一次的结果移到 _history/<任务名>-<时间>，也方便之后在几次生成里挑最好的一版。
const outDir = `${COMFY_OUTPUT}/${name}`
if (existsSync(outDir)) {
  mkdirSync(`${COMFY_OUTPUT}/_history`, { recursive: true })
  renameSync(outDir, `${COMFY_OUTPUT}/_history/${name}-${new Date().toISOString().replace(/[:.]/g, '-')}`)
}

const started = Date.now()
const res = await fetch(`${COMFY}/prompt`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ prompt, client_id: 'claude-girl' })
})
const body = await res.json()
if (!res.ok || body.error) {
  console.error(JSON.stringify(body, null, 2))
  process.exit(1)
}
const id = body.prompt_id
console.log(`已提交 ${SKIN ? `[${SKIN}] ` : ''}${name}（seed ${seed}，${useLora ? '加速 LoRA 4 步' : '无 LoRA 20 步'}），prompt_id ${id}`)

for (;;) {
  await new Promise(r => setTimeout(r, 5000))
  const h = await (await fetch(`${COMFY}/history/${id}`)).json()
  const entry = h[id]
  if (!entry) continue
  const status = entry.status?.status_str
  if (status === 'error') {
    const msg = entry.status.messages?.find(m => m[0] === 'execution_error')?.[1]
    console.error(`失败：${msg?.exception_message ?? JSON.stringify(entry.status)}`)
    process.exit(1)
  }
  const images = entry.outputs?.save?.images ?? []
  if (entry.status?.completed) {
    console.log(`完成：${images.length} 帧，用时 ${Math.round((Date.now() - started) / 1000)} 秒，seed ${seed}`)
    console.log(`输出：ComfyUI/output/${images[0]?.subfolder ?? ''}`)
    // 记下任务信息，finish.py 据此知道两端分别对应哪张关键帧
    const dir = `${COMFY_OUTPUT}/${name}`
    writeFileSync(`${dir}/job.json`, JSON.stringify({ name, seed, lora: useLora, ...job }, null, 2))
    break
  }
}
