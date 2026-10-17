# Claude-Chan

Windows 桌面桌宠：根据 Claude Code 的实时工作状态（思考、读文件、写代码、等你确认、完成、报错、打瞌睡），让 Claude-Chan 播放对应的动画。WSL 里的 CLI、Windows 里的 CLI 和 Claude Desktop 可以同时连接同一个桌宠。

```
Claude Code（WSL / PowerShell / Desktop）
   │  插件：type "http" hook，POST 每个事件
   ▼
127.0.0.1:47800/event ──► 桌宠主进程：按会话记录状态 → 按优先级汇总 → 目标状态
                                                              │
                          桌宠窗口：动画引擎沿枢纽图规划路径，无缝播放透明视频 ◄──┘
```

- [安装](#安装)
- [Claude Code 插件](#claude-code-插件)
- [WSL 网络配置](#wsl-网络配置)
- [使用](#使用)
- [状态规则](#状态规则)
- [素材与替换](#素材与替换)
- [素材生成（ComfyUI）](#素材生成comfyui)
- [配置项](#配置项)
- [调试工具](#调试工具)
- [开发](#开发)
- [已知限制](#已知限制)

## 安装

桌宠用 Python + PySide6（Qt）编写，不含浏览器内核。实测内存约 100 MB，CPU 约 27% 单核。代码可以在 Windows、macOS、Linux 上运行，目前只在 Windows 上测试过。

**素材**：把素材放到 `resources/assets/` 下，得到 `keyframes/` 和 `videos/` 两个目录（`manifest.json` 已在仓库里）。素材不进 git。桌宠播放的是 `videos/` 下的动画 AVIF；同名的 webm 是生成时的原始文件（见[素材生成](#素材生成comfyui)）。

### 打包版（推荐）

需要 [uv](https://docs.astral.sh/uv/)：

```powershell
uv sync
uv run pyinstaller claude-chan.spec --noconfirm
```

得到 `dist\ClaudeChan\` 目录（约 170 MB，其中素材约 90 MB，只打包 manifest 里用到的素材）。把整个目录放到固定的位置（比如 `%LOCALAPPDATA%\Programs\ClaudeChan`），运行里面的 `ClaudeChan.exe`。

### 直接运行

```powershell
uv sync
uv run claude-chan            # 加 --debug 同时打开调试面板
```

### 然后

1. 在托盘菜单里勾选 **开机自启**：Windows 写注册表 Run 键（直接运行时用 pythonw 启动，不弹命令行窗口），macOS 写 LaunchAgent，Linux 写 `~/.config/autostart`。插件的 hook 在桌宠没开时每次最多等 0.2 秒（见[下文](#桌宠没开时会怎样)），所以建议让桌宠一直开着。
2. 按下一节安装 Claude Code 插件。

## Claude Code 插件

插件只做一件事：通过 `type: "http"` 的 hook，把 Claude Code 的事件 POST 到 `http://127.0.0.1:47800/event`。三个入口的配置完全一样，不依赖任何 shell 环境。

这个仓库本身就是一个 marketplace（`.claude-plugin/marketplace.json`），插件在 `plugin/` 目录下。直接从 GitHub 添加即可；开发时也可以把本地的仓库目录当 marketplace 添加，本地目录形式会原地加载插件，修改 `plugin/` 下的文件不需要重新安装。

### Windows（PowerShell 里的 CLI 和 Claude Desktop）

```powershell
claude plugin marketplace add Ivanfangsc/claude-chan
claude plugin install claude-chan@claude-chan
```

Claude Desktop 和 Windows 上的 CLI 共用 `~/.claude` 配置，装一次两边都生效，已经打开的 Desktop 会话也会立即开始发送事件。可以在输入框的 **+ → Plugins** 中确认插件已启用（只对本地会话生效，云端会话不加载本地插件）。

### WSL

```bash
claude plugin marketplace add Ivanfangsc/claude-chan
claude plugin install claude-chan@claude-chan
```

WSL 需要先完成[网络配置](#wsl-网络配置)。

### 验证插件是否生效

打开调试面板（托盘菜单，或双击桌宠），在任意入口里让 Claude 读一个文件。调试面板的“会话”表里会出现这个会话，来源显示为 WSL 或 Win，日志里能看到 `UserPromptSubmit`、`PreToolUse Read`、`Stop` 等事件。

需要看 Claude Code 这一侧时，用 `claude --debug-file <文件>` 启动，日志里会有 `HTTP hook POST to http://127.0.0.1:47800/event`；出现 `cancelled` 说明桌宠没有在 0.2 秒内响应。

### 更新和卸载

> 从旧名字 `claude-girl` 升级：先 `claude plugin uninstall claude-girl@claude-girl` 和 `claude plugin marketplace remove claude-girl`，再按上面安装 `claude-chan`，否则两个插件会各发一遍事件。改名只改了对外的名字：数据目录仍是 `%APPDATA%\claude-girl`，原来的设置照常生效。

```bash
claude plugin marketplace update claude-chan   # 拉取插件的新版本
claude plugin uninstall claude-chan@claude-chan
claude plugin marketplace remove claude-chan
```

会话里也可以用 `/plugin` 管理，用 `/reload-plugins` 重新加载。

### 桌宠没开时会怎样

HTTP hook 会阻塞等待响应，而且不支持后台异步（`async` 只对 command hook 有效）。在 Windows 上连接一个没人监听的端口约 2 秒后才被拒绝，WSL 的 mirrored 网络里则是直接丢包，所以 hook 的超时设得很短：

- `timeout` 是 **0.2 秒**。桌宠开着时响应只需几毫秒，没有影响。
- 桌宠没开时，每个 hook 最多等 0.2 秒；一次工具调用有 PreToolUse 和 PostToolUse 两个 hook，也就是多等约 0.4 秒。失败只记在 Claude Code 的调试日志里，界面上不显示错误。

### 与原始需求说明不一致、以官方文档为准的地方

- **SessionStart 不支持 HTTP hook**（只支持 command 和 mcp_tool），Claude Code 会直接跳过。插件因此不注册 SessionStart；会话在收到它的第一个事件（通常是 `UserPromptSubmit`）时自动创建。
- 除了 `permission_prompt`，通知类型 `elicitation_dialog`、`elicitation_url_dialog`、`agent_needs_input` 也表示在等你操作，都映射为 confirmation。插件不设 Notification 的 matcher，所有通知都发送，由桌宠决定如何处理。
- 用户中断（按 Esc）时 **Stop 不会触发**，桌宠靠 `Notification: idle_prompt` 把会话切回 idle。
- `PostToolUseFailure` 带 `is_interrupt: true` 表示调用被中止而不是出错，不播 error。
- `PermissionDenied` 只在 auto 模式拒绝工具调用时触发。
- hook 的 `timeout` 单位是秒，可以写小数。
- 响应体会被 Claude Code 当作 hook 输出解析。桌宠对所有请求都返回 `{}`，不会影响权限判断。
- 如果你在任何一级 settings 里设置了 `allowedHttpHookUrls`，需要把 `http://127.0.0.1:47800/event` 加进去，否则 hook 不会执行。

## WSL 网络配置

WSL 需要开启 mirrored 网络，这样 WSL 里的 `127.0.0.1` 就是 Windows 的 `127.0.0.1`。在 Windows 的 `%USERPROFILE%\.wslconfig` 里写：

```ini
[wsl2]
networkingMode=mirrored
```

然后在 PowerShell 里执行 `wsl --shutdown`，再重新打开 WSL。检查（桌宠开着时，在 WSL 里执行）：

```bash
wslinfo --networking-mode                # mirrored
curl http://127.0.0.1:47800/health       # {"ok":true}
```

## 使用

**桌宠本体**

| 操作 | 效果 |
|---|---|
| 左键拖动角色 | 移动窗口 |
| Ctrl + 滚轮 | 缩放，保持 9:16，脚下位置不变 |
| 右键 | 弹出菜单（与托盘菜单相同） |
| 双击 | 打开调试面板 |
| 点击角色周围的透明区域 | 穿透到下面的窗口 |

**托盘菜单**：显示桌宠、置顶、鼠标穿透、跟随 Claude 窗口（仅 Windows）、打开调试面板、重新加载配置、打开配置文件夹、重置位置和大小、形象（原版 / Q 版）、开机自启、退出。左键单击托盘图标显示或隐藏桌宠，鼠标悬停显示当前状态。

- **鼠标穿透**打开后窗口不接收任何鼠标事件（包括拖动），只能从托盘关闭。
- 关闭窗口（Alt+F4）只是隐藏到托盘，**退出**才会真正退出。
- **跟随 Claude 窗口**（仅 Windows，默认关）：贴在 Claude 桌面版主窗口的右下角，窗口移动、缩放时跟着走（监听宿主进程的窗口事件，不轮询）；桌宠的 owner 设为宿主窗口，层级紧贴在它上面，别的窗口挡住 Claude 时也一起挡住，所以跟随时“置顶”不可选；Claude 最小化时一起隐藏。拖动桌宠会记住贴哪一侧、离边多远，“重置位置和大小”回到默认贴法。找不到 Claude 窗口（没开或关掉了）时回到桌面上原来的位置，照常显示状态，每秒找一次，Claude 打开后自动贴上去。要贴的程序见配置 `window.followProcesses`。
- 位置、大小、置顶、穿透、跟随（开关和相对位置）保存在 `%APPDATA%\claude-girl\window-state.json`。保存的位置不在任何屏幕上时（比如拔掉了副屏）自动回到默认位置：主屏右下角，宽度为屏幕的 1/4。
- 只运行一个实例。再次启动时会显示已有的桌宠并打开调试面板。

## 状态规则

### 事件 → 会话状态

| 事件 | 会话状态 |
|---|---|
| `UserPromptSubmit` | thinking（同时清除常驻的 error） |
| `PreToolUse` | 按工具映射表：只读工具 → reading；写入工具 → writing；等待用户的工具（`AskUserQuestion`、`ExitPlanMode`）→ confirmation；其他（包括 Bash）→ writing |
| `PostToolUse` | 800ms 内没有新的 PreToolUse 才切回 thinking，避免连续调用工具时来回抽搐 |
| `PermissionRequest`；`Notification` 的 `permission_prompt` 等 | confirmation |
| `PostToolUseFailure` | 播一次 error，之后回到 thinking；30 秒内的重复失败只记日志 |
| `StopFailure` | error 常驻，直到下一次 `UserPromptSubmit` |
| `Stop` | complete，保持 30 秒后自动回到 idle；期间有新事件就立即切换。如果 Claude 还有后台任务在跑（后台命令、后台子代理），改为 waiting：Claude 会在任务结束后自己继续，不需要你操作。按任务编号对账（工具返回里的编号 ↔ 任务结束通知里的 `<task-id>`），最多等 2 小时。waiting 和 idle 共用枢纽 A 的关键帧和 loop（两者之间切换不用过渡、不交叉淡化），只是大约每 20 秒拿出怀表看一次时间（事件 `event-waiting-watch`）|
| `Notification` 的 `idle_prompt` | idle（用户中断后的兜底） |
| `SessionEnd` | 移除会话 |

- **error 一定会播出**：error 会一直保留，直到动画确认播完（最多等 30 秒）。所以即使失败后 Claude 立刻又调用了工具，error 也会播一次。
- **drowsy**：所有会话都空闲（或没有会话）并且 10 分钟没有任何事件时进入，收到任何事件就醒来。
- 会话 30 分钟没有事件视为已结束并清理（包括常驻的 error）。

### 多会话汇总

每个事件都带 `session_id` 和 `cwd`，桌宠按会话分别记录，最终显示优先级最高的那个：

confirmation > error > 工作中（writing / reading / thinking）> complete > idle > drowsy

同一组里显示最近变化的会话。来源按 `cwd` 判断：以 `/` 开头的来自 WSL，以盘符开头的来自 Windows。显示 confirmation 时，头顶气泡显示是哪个项目在等（`cwd` 的最后一级目录名）。

### 动画

- 枢纽 A（坐着，书合上）就是 idle；枢纽 B（书摊开）只是过渡姿势。thinking、confirmation、complete、error、drowsy 挂在 A 上，reading、writing 挂在 B 上。
- 切换状态时在枢纽图上找最短路径，按顺序播放沿途片段。例如 thinking → writing 依次播 thinking 退出、A→B、writing 进入、writing 循环。
- intro、outro、过渡一旦开始必须播完；loop 播完这一轮再离开。以下几种情况会用约 150ms 的交叉淡化立即离开：目标是 confirmation 或 error；当前是 idle 或 drowsy 的 loop（一有动静就“回过神来”）；当前在播随机事件。
- **loop 变体**：一个状态可以有多段 loop（`idle-loop`、`idle-loop-2`……），每轮随机换一段，不连续重复同一段。
- **随机事件**：停在某个状态时，每播完一轮 loop，以 25% 的概率改播一段该状态的事件（比如 idle 打哈欠、张望，thinking 敲下巴，drowsy 惊醒），两次事件之间至少隔 60 秒。事件和 loop 一样首尾是该状态的关键帧，播完自然回到 loop。
- 衔接无缝：逐帧解码 AVIF 画到窗口上，换片段只是换一个帧序列，下一段在当前段播完前就准备好了，不会出现空帧或闪烁。每段末帧等于下一段首帧，所以下一段从第 2 帧开始播，避免同一画面停两帧。

## 素材与替换

素材全部是 9:16 透明素材，由 `resources/assets/manifest.json` 描述，代码里不写死任何文件名。

**形象**：每个形象是一套独立的素材目录，结构完全相同——原版 `resources/assets/`，Q 版（冷脸萌三头身）`resources/assets-chibi/`。托盘菜单“形象”里切换，选择保存在数据目录的 `app-state.json`。切换时先回到 idle，这一轮播完后播变身动画（manifest 的 `switch` 字段登记，首帧是本形象的 idle、末帧是目标形象的 idle），变身一开始就换成新形象的动画引擎，播完无缝接上；切换期间照常接收事件，切完显示最新的状态。Q 版的 error 是专属的“抱头蹲防”。

- 关键帧 PNG（1026×1824）：每个状态和两个枢纽各一张。它们用于启动时的占位画面，以及计算点击穿透的命中区域。
- 透明动画 AVIF（540×960，24fps），manifest 里登记的就是它们；同名的 VP9 + Alpha WebM（774×1376）是生成时的原始文件，用 `scripts/export_frames.py` 转换：
  - `transition`：枢纽之间的过渡（A→B、B→A）
  - `intro` / `outro`：从枢纽进入状态、从状态回到枢纽
  - `loop`：状态循环（idle 的循环挂在枢纽 A 上）；同一状态可以有多段变体
  - `event`：随机事件，首尾帧与所属状态的 loop 相同，中间是别的动作

**衔接要求**：intro 的末帧 = loop 的首帧 = loop 的末帧 = outro 的首帧（都等于该状态的关键帧）；outro 和过渡的末帧 = 枢纽帧。播放器会跳过下一段的首帧，因为它与上一段的末帧相同。

### manifest 格式

```jsonc
{
  "fps": 24, "width": 774, "height": 1376,
  "hubs": { "A": { "keyframe": "keyframes/...png" }, "B": { "keyframe": "..." } },
  "states": {
    "idle":     { "hub": "A", "kind": "loop", "atHub": true, "keyframe": "..." },  // 状态就是枢纽本身
    "thinking": { "hub": "A", "kind": "loop", "keyframe": "..." },
    "error":    { "hub": "A", "kind": "oneshot", "keyframe": "..." }             // 没有 loop，停在关键帧上
  },
  "clips": [
    { "id": "hub-A-to-B", "type": "transition", "from": "A", "to": "B", "file": "videos/transitions/..." },
    { "id": "thinking-intro", "type": "intro", "state": "thinking", "from": "A", "file": "..." },
    { "id": "thinking-outro", "type": "outro", "state": "thinking", "to": "A", "file": "..." },
    { "id": "thinking-loop", "type": "loop", "state": "thinking", "file": "..." },
    { "id": "thinking-loop-2", "type": "loop", "state": "thinking", "file": "..." },   // 变体
    { "id": "event-thinking-tap", "type": "event", "state": "thinking", "file": "..." } // 随机事件
  ]
}
```

启动时会校验 manifest：每个 loop 状态至少有一个 loop 片段，非枢纽状态都有 intro 和 outro，事件只能挂在 loop 状态上，引用的状态和枢纽都存在。有问题时显示在调试面板日志里。状态名必须是这 8 个之一：idle、thinking、reading、writing、confirmation、complete、error、drowsy。

### 替换素材

- **只换某几段视频**：用同名的 webm 覆盖原始文件，运行 `export_frames.py` 更新 AVIF，然后重启桌宠；打包版需要重新打包。
- **不重新打包**：把整套素材（包括 `manifest.json`）放到任意文件夹，在配置里设置 `"assetsDir": "D:\\my-assets"`，然后重启桌宠。
- **检查新做的 loop**：用下面的脚本检查倒放（回文）、静止帧、首尾是否对齐、和相邻片段的衔接、速度突变：

  ```powershell
  uv run python scripts/analyze_loop.py                           # 检查 manifest 里的所有 loop 和随机事件
  uv run python scripts/analyze_loop.py 新文件.webm --as writing   # 检查还没放进去的新文件
  ```

## 素材生成（ComfyUI）

`scripts/comfy/` 通过 ComfyUI 的 API 调用 MiniMax H3 首尾帧工作流批量生成素材，全程无人值守。

方法的完整说明（为什么首尾同一帧的 loop 会有循环感、持续动作的 loop 怎么做、过渡和随机动作怎么两端带着动作接上、踩过的坑）见 [docs/animation-pipeline.md](docs/animation-pipeline.md)；本节是脚本用法。
所有脚本都按环境变量 `CLAUDE_GIRL_SKIN` 区分形象（空为原版，`chibi` 为 Q 版）：生成目录（`claude-girl-gen[-chibi]`）、青色关键帧的文件名（`claude-girl-[chibi-]<名字>-cyan-9x16.png`）、素材目录（`resources/assets[-chibi]`）都分开。

关键帧用 Qwen Image 2.1 编辑（`qwen_edit.mjs`，参考图 + 文字写清姿势；同时给原版关键帧当参考的话，模型不照搬姿势反而改人物大小），
选定的候选用 `place_keyframe.py` 以书堆为模板对齐到 idle 关键帧，存青色版和透明版：

```powershell
node scripts/comfy/qwen_edit.mjs chibi-thinking --count 3
uv run python scripts/comfy/place_keyframe.py <候选图> thinking --skin chibi
$env:CLAUDE_GIRL_SKIN="chibi"; node scripts/comfy/sway.mjs idle thinking   # 之后的流程和原版一样
```

```powershell
node scripts/comfy/generate.mjs --list                  # 所有任务
node scripts/comfy/sway.mjs thinking reading           # 持续动作的 loop：生成两段 → 拼成一圈 → 抠图 → 检测
node scripts/comfy/batch.mjs T-hub-A-to-B T-reading-hub-to-state   # 过渡：生成 → 拼接抠图 → 检测 → 脸部检查图
node scripts/comfy/insert.mjs idle-yawn thinking-tap    # 插入式随机动作：生成 → 插进 loop → 抠图 → 检测
D:/comfy/.venv/Scripts/python.exe scripts/export_frames.py   # webm → AVIF，并更新点击区域 hitmask.png（所有片段所有帧的并集）
```

- **任务定义**在 `jobs.mjs`：持续动作的 loop（`<状态>-M` / `<状态>-MB`，见下）、idle 的眨眼版本（`idle-MK<n>`）、随机事件（`e-<名字>`，5 秒，按秒写剧本）、过渡（`t-<文件名>`，2–3 秒）。旧的 K0 → K0 loop（`<状态>-L`、`<状态>-Q`）保留但不再使用。
- **持续动作的 loop**：首尾帧都是同一张关键帧时，模型会“离开关键帧再回来”，两端速度降到接近零，每一圈都像低头再抬头，循环感很强，提示词和事后提速都救不回来。改为：
  1. `<状态>-M`（124 帧）：不给首尾帧，用 `MiniMaxH3AddGuide` 把关键帧锚在第 61 帧，前后都是持续的动作，经过关键帧时不停下；
  2. `<状态>-MB`（90 帧）：把 M 里关键帧之后的 22 帧锚在开头、之前的 22 帧锚在结尾，让模型生成中间的衔接。给模型看的是一段连续的动作而不是一张图，接缝处速度能接上；
  3. `assemble_loop.py` 在引导重叠的范围里找跳变最小的接缝，拼成从关键帧开始、回到关键帧的一圈（5.75 秒），和过渡、随机事件照常衔接。
  **过渡**（`T-<文件名>`，124 帧）也这样做：开头 22 帧锚住出发节点 loop 的开头，结尾 22 帧锚住到达节点 loop 的结尾，所以经过同一张关键帧的片段都是“像 loop 结尾那样到达、像 loop 开头那样离开”，切换状态时动作不停。枢纽 B 上没有状态，另做了一段不播放的参考 loop（`hubB`）给经过它的过渡用。error 是一次性状态，那一端仍然锚单张关键帧。
  **随机动作**（`E-<事件>`，158 帧）插在 loop 的第 at 帧后面：开头锚住第 at-21 到 at 帧，结尾锚住第 at+1 到 at+22 帧，中间约 4.75 秒按剧本做动作；`assemble_loop.py --insert` 插回 loop，得到“摇一会儿 → 做动作 → 接着摇”的 10.5 秒一段，首尾仍是关键帧，作为 event 登记。
  眨眼也用同样的办法：在拼好的 loop 里挑一段，两端用原来的帧锚住，只重新生成中间约 1.2 秒（`assemble_loop.py <状态> --blink <n>`），得到只多一次眨眼的变体。不要把眨眼做成单独的随机事件：事件从静止的关键帧开始，眨眼时摇晃会停下。
- **生成**：768×1344，20 步，不用加速 LoRA（`--lora` 可以打开，快约 3 倍，但动作幅度更大、结尾更容易偏离关键帧）。所有提示词都带“单一连续镜头、全身入画”和“表情与第一帧一致、嘴唇闭合”的约束。每次生成前，旧结果会移到 `_history/`，方便挑选。
- **拼接**（`finish.py`）：
  - 剪掉首尾多余的静止帧；
  - 每张关键帧只选一个视频里的“标准帧”，所有片段的端点都在 8 帧内平滑对齐到它，所以衔接处像素完全一致（不直接用关键帧原图，因为生成画面比原图略软，直接替换会在衔接时“闪一下变清晰”）；
  - 从青色背景抠图、去除青色溢色，输出 774×1376 的 VP9 + Alpha；
- **自动重试**：`finish.py` 检测到切镜头（模型偶尔会切到脸部特写）或背景漂移（长片段背景会慢慢变灰）时返回退出码 3，`batch.mjs` 自动换随机种子重新生成，最多 3 次。
- **经验**：10 秒（243 帧）的片段即使写了详细剧本，背景也会漂成灰色，所以所有片段都用 5 秒以内；K0 → K1 → K0 两段拼接的两段动作幅度无法控制一致；首尾相同的 K0 → K0 两端会减速（见上），所以 loop 改用关键帧在中间的做法。

## 配置项

配置文件是 `%APPDATA%\claude-girl\config.json`（托盘菜单“打开配置文件夹”）。文件里只需要写想覆盖的键，其余用默认值。对象会逐键合并，**数组会整体替换**。修改后在托盘点“重新加载配置”，只有 `server` 的修改需要重启桌宠。

例：让桌宠 1 分钟没事件就打瞌睡，并把 `Bash` 算作读文件：

```json
{
  "state": {
    "timing": { "idleToDrowsyMs": 60000 },
    "tools": { "read": ["Read", "Grep", "Glob", "LS", "WebFetch", "WebSearch", "Bash"] }
  }
}
```

| 键 | 默认值 | 说明 |
|---|---|---|
| `server.host` | `"127.0.0.1"` | HTTP 服务监听地址 |
| `server.port` | `47800` | HTTP 服务端口。修改后要同步修改 `plugin/hooks/hooks.json` 里的 URL（HTTP hook 的 URL 不支持环境变量） |
| `window.widthFraction` | `0.25` | 默认窗口宽度占主屏宽度的比例（首次启动和“重置位置和大小”时使用） |
| `window.hitTest` | `true` | 角色周围的透明区域让点击穿透 |
| `window.hideInFullscreen` | `true` | 同一屏幕上有全屏窗口（游戏、视频、演示）时自动隐藏，退出全屏后回来；桌宠隐藏时停止解码，不占 CPU。跟随 Claude 窗口时不用它（层级跟着宿主，全屏窗口自然会盖住） |
| `window.followProcesses` | `["claude.exe"]` | “跟随 Claude 窗口”贴着这些进程的主窗口（进程名，不分大小写）；想贴终端可加 `windowsterminal.exe` |
| `assetsDir` | `null` | 外部素材目录（包含 `manifest.json`），`null` 为内置素材 |
| `animation.highPriority` | `["confirmation", "error"]` | 以这些状态为目标时，立即交叉淡化离开当前 loop |
| `animation.interruptibleLoops` | `["idle", "drowsy"]` | 离开这些状态的 loop 时不等这一轮播完 |
| `animation.crossfadeMs` | `150` | 交叉淡化时长；`0` 表示不打断 loop，总是等这一轮播完 |
| `animation.boostPlaybackRate` | `1` | 追赶高优先级目标时的播放速度，例如 `2`；`1` 为关闭 |
| `animation.basePlaybackRate` | `1` | 所有片段的基础速度（调试面板的速度滑块改的就是它） |
| `animation.oneshotHoldMs` | `1000` | error 在关键帧上停留的时长 |
| `animation.skipSharedFrame` | `true` | 衔接时跳过下一段的首帧（与上一段末帧相同），避免同一画面停两帧 |
| `animation.eventChance` | `0.25` | 每播完一轮 loop 改播随机事件的概率（manifest 里事件自己写了 `chance` 时以它为准）；`0` 关闭 |
| `animation.eventCooldownMs` | `60000` | 同一组随机事件之间至少间隔（事件自己写了 `cooldownMs` 时以它为准）；启动和每次换状态时重新计时 |
| `animation.disabledEventGroups` | `[]` | 不触发这些组的随机事件：`"blink"` 为眨眼，`"fidget"` 为其他动作（没写 `group` 的事件） |
| `animation.interruptibleEvents` | `true` | 随机事件播放中可以随时离开（交叉淡化） |
| `animation.loopRateJitter` | `0.06` | 每一轮 loop 的播放速度在 1 ± 这个比例之间随机 |
| `animation.swayDegrees` | `0` | 绘制时整体左右摇晃的最大角度（绕画面底部中点旋转）；`0` 关闭 |
| `animation.swayPeriodMs` | `5000` | 摇晃的周期（叠加一条周期约 1.6 倍的正弦，不会完全重复） |
| `state.timing.postToolDebounceMs` | `800` | PostToolUse 之后等这么久没有新的 PreToolUse 才回到 thinking |
| `state.timing.errorDedupMs` | `30000` | 这段时间内重复的工具失败不再播 error |
| `state.timing.idleToDrowsyMs` | `600000` | 空闲这么久没有任何事件后打瞌睡 |
| `state.timing.sessionTimeoutMs` | `1800000` | 会话这么久没有事件就清理 |
| `state.timing.thinkingStaleMs` | `300000` | 会话停在 thinking 这么久没有任何事件就回到 idle（会话被回滚或中断时收不到 Stop，不处理会一直显示 thinking，还会盖住别的会话的 complete） |
| `state.timing.latchMaxMs` | `30000` | error 等待动画播出的最长时间（被更高优先级的会话挡住时） |
| `state.timing.completeHoldMs` | `30000` | 任务完成（Stop）后保持 complete 的时长，然后自动回到 idle |
| `state.timing.waitingMaxMs` | `7200000` | Stop 时还有后台任务在跑，waiting 最多保持这么久（没收到任务结束的通知时兜底） |
| `state.tools.confirm` | `["AskUserQuestion", "ExitPlanMode"]` | 映射为 confirmation 的工具 |
| `state.tools.read` | `["Read", "Grep", "Glob", "LS", "WebFetch", "WebSearch", "NotebookRead", "ToolSearch", "/^mcp__.*__(read\|get\|list\|search\|fetch\|query)/i"]` | 映射为 reading 的工具 |
| `state.tools.write` | `["Edit", "MultiEdit", "Write", "NotebookEdit"]` | 映射为 writing 的工具 |
| `state.tools.default` | `"writing"` | 都没匹配上的工具（包括 Bash） |
| `state.priority` | `[["confirmation"], ["error"], ["writing", "reading", "thinking"], ["complete"], ["waiting"], ["idle"], ["drowsy"]]` | 多会话汇总优先级，从高到低，同组内取最近变化的会话 |

工具名可以写精确名字，也可以写成 `"/正则/标志"`。匹配顺序是 confirm → read → write → default。

## 调试工具

**调试面板**（托盘菜单或双击桌宠）：会话表（来源、项目、显示状态、基础状态、待播的一次性状态、后台任务数、最近事件；每行可以手动“移除”残留的会话）、引擎状态（当前片段、下一段、是否到达目标）、最近 200 条日志、手动切换目标状态的按钮、播放速度滑块、“全状态两两切换巡检”（一次覆盖 8 个状态之间的全部 56 种切换），当前状态的随机事件表（组、概率、冷却和剩余冷却，每个事件都可以“下一轮播放”手动触发；按组开关眨眼和其他事件），以及摇晃、loop 速度浮动、事件默认概率和冷却的滑块（只在本次运行有效）。

**模拟 hook 事件**（桌宠开着时）：

```powershell
node scripts/simulate.mjs basic          # 一轮完整对话
node scripts/simulate.mjs rapid-tools    # 快速连续调用 20 次工具，测试防抖
node scripts/simulate.mjs multi          # WSL 和 Windows 三个会话并发，其中一个等权限
node scripts/simulate.mjs fail-burst     # 连续失败，只播一次 error
node scripts/simulate.mjs stop-failure   # error 常驻到下一次提问
node scripts/simulate.mjs interrupt      # 中断后靠 idle_prompt 回到 idle
node scripts/simulate.mjs confirm-tool   # AskUserQuestion
node scripts/simulate.mjs end            # 清掉所有模拟会话
```

发送单个任意事件（在 Git Bash 或 WSL 里执行；Windows PowerShell 5.1 会吃掉参数里 JSON 的双引号）：

```bash
node scripts/simulate.mjs raw PreToolUse '{"tool_name":"Bash"}'
```

可选参数：`--speed 2`（加速）、`--url http://127.0.0.1:47800/event`。

**HTTP 接口**：`GET /health` 检查服务是否在运行；`GET /state` 返回完整状态快照（会话、目标、引擎、日志）。带 `Origin` 头的请求（来自浏览器网页）一律拒绝。

## 开发

```powershell
uv run pytest                                    # 单元测试（路径规划、动画引擎、随机事件、事件映射、多会话汇总）
$env:CLAUDE_GIRL_PROFILE=1; uv run claude-chan   # 每 10 秒在日志里输出各步骤的平均耗时
uv run pyinstaller claude-chan.spec --noconfirm  # 打包到 dist/ClaudeChan/
```

```
.claude-plugin/marketplace.json   marketplace
plugin/                           Claude Code 插件（hooks.json）
claude_girl/                      桌宠
  app.py                          入口：把各模块连起来
  window.py / tray.py / debug.py  桌宠窗口、托盘、调试面板
  follow.py / follower.py         跟随 Claude 窗口（Win32 窗口事件与 owner；找宿主、贴角、记住相对位置）
  fullscreen.py                   全屏检测
  server.py                       HTTP 服务（后台线程，经 Qt 信号交给主线程）
  engine/                         动画引擎（engine）、路径规划（graph）、逐帧播放器（player）、manifest
  state/                          事件映射（mapper）、会话与汇总（sessions）、目标状态（target）
tests_py/                         单元测试（pytest）
resources/assets/                 素材与 manifest.json
scripts/                          simulate.mjs、analyze_loop.py、export_frames.py
scripts/comfy/                    素材生成：jobs.mjs、skin.mjs、generate.mjs、batch.mjs、sway.mjs、insert.mjs、assemble_loop.py、finish.py、contact.py、qwen_edit.mjs、place_keyframe.py
claude-chan.spec                  PyInstaller 打包配置
```

`scripts/` 下的 `.mjs` 脚本不依赖任何 npm 包，用 Node 18+ 直接运行。

## 已知限制

- 每段 loop 只有 5 秒，重复播放时仍有一定循环感；loop 变体和随机事件可以缓解。
- 透明区域的点击穿透用的是所有关键帧轮廓的并集，比角色当前姿势略大一些。
- 打包出的程序没有代码签名，首次运行时 Windows SmartScreen 可能会提示。
- 修改端口时需要同时修改 `hooks.json` 里的 URL。

## 许可

- **代码和文档**：[MIT](LICENSE)。
- **角色素材**（`resources/` 下的关键帧、动画、图标，以及发布包里的同一套素材）：[CC BY 4.0](ASSETS-LICENSE.md)，署名即可自由使用、修改，包括商用。
- 素材全部由 AI 生成（Qwen Image 2.1 编辑关键帧，MiniMax H3 生成动画），再经人工挑选和后期处理，见 [docs/animation-pipeline.md](docs/animation-pipeline.md)。
- "Claude" 是 Anthropic, PBC 的商标。本项目是**非官方的同人作品**，与 Anthropic 没有关联，也未经其认可；上述许可不包含任何商标权利。
