// 实机片段的帧：按需加载、用完释放。绘制时缺哪一帧就记下来，渲染器等它们加载好再重画一次，
// 所以导出的每一帧都是完整的；预览时先画已经有的，下一帧补上。

let INDEX = {}
const cache = new Map() // key → ImageBitmap
const loading = new Map() // key → Promise
export const pending = new Set()
const MAX = 900

export async function init() {
  INDEX = await (await fetch('frames/index.json')).json()
}

export function info(clip) {
  const i = INDEX[clip]
  if (!i) throw new Error(`没有片段 ${clip}（先运行 tools/extract_frames.py）`)
  return i
}

const keyOf = (clip, i) => `${clip}/${String(i).padStart(4, '0')}`

// 片段在本地时间 lt（秒）时的那一帧；loop=true 时循环播放，否则停在末帧
export function frameAt(clip, lt, loop = true) {
  const { n, fps } = info(clip)
  let i = Math.floor(Math.max(0, lt) * fps)
  i = loop ? i % n : Math.min(i, n - 1)
  const key = keyOf(clip, i)
  const bmp = cache.get(key)
  if (bmp) {
    cache.delete(key) // 挪到最近使用
    cache.set(key, bmp)
    return bmp
  }
  pending.add(key)
  return null
}

function load(key) {
  if (cache.has(key)) return Promise.resolve()
  if (!loading.has(key)) {
    loading.set(key, fetch(`frames/${key}.webp`)
      .then(r => r.blob())
      .then(b => createImageBitmap(b))
      .then(bmp => {
        cache.set(key, bmp)
        loading.delete(key)
        while (cache.size > MAX) {
          const old = cache.keys().next().value
          cache.get(old).close()
          cache.delete(old)
        }
      }))
  }
  return loading.get(key)
}

export async function loadPending() {
  const keys = [...pending]
  pending.clear()
  await Promise.all(keys.map(load))
  return keys.length
}
