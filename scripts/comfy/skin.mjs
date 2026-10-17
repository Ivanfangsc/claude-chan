// 形象（皮肤）：环境变量 CLAUDE_GIRL_SKIN 为空是原版，chibi 是 Q 版。
// 不同形象的生成目录、青色关键帧的文件名、素材目录都分开，互不影响；标准帧（_canonical）在生成目录里，也各自独立。
export const SKIN = process.env.CLAUDE_GIRL_SKIN ?? ''
const suffix = SKIN ? `-${SKIN}` : ''
export const GEN_SUBDIR = `claude-girl-gen${suffix}` // ComfyUI output 下的生成目录
export const ASSETS_DIR = `resources/assets${suffix}` // 仓库里的素材目录
// ComfyUI input 里的青色关键帧：原版 claude-girl-<名字>-cyan-9x16.png，Q 版 claude-girl-chibi-<名字>-cyan-9x16.png
export const cyan = k => `claude-girl-${SKIN ? `${SKIN}-` : ''}${k}-cyan-9x16.png`
