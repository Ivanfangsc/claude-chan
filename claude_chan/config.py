"""配置：默认值写在这里，用户只需在配置文件里写想覆盖的键。

配置文件和其他数据（窗口位置、形象选择、日志）都放在程序自己的 data 文件夹里：打包版是 ClaudeChan.exe 旁边的
data\\，从源码运行是仓库根目录的 data/。不往 %APPDATA% 之类的系统目录写任何东西，删掉程序文件夹就删干净了。
对象逐键合并；数组和其他值整体替换。
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

DEFAULT_CONFIG: dict[str, Any] = {
    "server": {"host": "127.0.0.1", "port": 47800},
    "window": {
        # 默认窗口宽度占主屏宽度的比例（首次启动或“重置位置和大小”时使用）
        "widthFraction": 0.25,
        # 角色周围的透明区域让点击穿透到下面的窗口
        "hitTest": True,
        # 同一屏幕上有全屏窗口（游戏、视频、演示）时自动隐藏，退出全屏后回来
        "hideInFullscreen": True,
        # 托盘里打开“跟随 Claude 窗口”后，贴着这些进程的主窗口（Claude 桌面版）
        "followProcesses": ["claude.exe"],
    },
    # 检查更新：启动 10 秒后和之后每天读一次 GitHub Releases 的最新版本，有新版本时托盘提示
    "updates": {"check": True, "repo": "Ivanfangsc/claude-chan"},
    # 调试面板（托盘菜单“打开调试面板”、双击桌宠）：从源码运行时总是可用，打包版默认隐藏，设为 true 打开
    "debugPanel": False,
    # 素材目录（包含 manifest.json）；None 表示使用内置素材
    "assetsDir": None,
    "animation": {
        # 以这些状态为目标时，立即交叉淡化离开当前 loop
        "highPriority": ["confirmation", "error"],
        # 离开这些状态的 loop 时不等这一轮播完
        "interruptibleLoops": ["idle", "drowsy"],
        # 交叉淡化时长；0 表示不打断 loop
        "crossfadeMs": 150,
        # 追赶高优先级目标时的播放速度，1 表示关闭
        "boostPlaybackRate": 1,
        # 所有片段的基础速度（调试面板的速度滑块改的就是它）
        "basePlaybackRate": 1,
        # error 在关键帧上停留的时长
        "oneshotHoldMs": 1000,
        # 衔接时跳过下一段的首帧（与上一段末帧相同），避免同一画面停两帧
        "skipSharedFrame": True,
        # 随机事件（打哈欠、看看四周……）：每播完一轮 loop，以这个概率改播一段事件
        "eventChance": 0.25,
        # 两次随机事件之间至少间隔
        "eventCooldownMs": 60_000,
        # 不触发这些组的随机事件（眨眼的组是 blink，其他动作默认是 fidget）
        "disabledEventGroups": [],
        # 整体轻轻左右摇晃（绕画面底部中点旋转，最大角度，0 关闭）；由两条周期不成整数比的正弦叠加，不会重复
        "swayDegrees": 0,
        "swayPeriodMs": 5000,
        # 切换方式（托盘菜单里可以改，选择保存在 data\app-state.json）：
        #   "smooth"     流畅优先：随机小动作和工作状态的 loop 播完再走，只有 highPriority（等你确认、出错）立即打断
        #   "responsive" 响应优先：小动作和所有 loop 都立即交叉淡化离开，最快，但偶尔会看到动作被掐断
        # 两种方式下 interruptibleLoops 里的状态（待机、打瞌睡）都一有动静就立即离开
        "switchStyle": "smooth",
        # 每一轮 loop 的播放速度在 1 ± 这个比例之间随机，呼吸节奏不会一成不变
        "loopRateJitter": 0.06,
    },
    "state": {
        "timing": {
            # PostToolUse 之后等这么久没有新的 PreToolUse，才切回 thinking
            "postToolDebounceMs": 800,
            # 这段时间内重复的工具失败不再播 error
            "errorDedupMs": 30_000,
            # 所有会话空闲且这么久没有任何事件 → drowsy
            "idleToDrowsyMs": 10 * 60_000,
            # 会话这么久没有事件 → 视为已结束并清理
            "sessionTimeoutMs": 30 * 60_000,
            # 停在 thinking 这么久没有任何事件 → 回到 idle。会话被回滚或中断时收不到 Stop，
            # 不处理的话它会一直显示 thinking，还会盖住别的会话的 complete
            "thinkingStaleMs": 5 * 60_000,
            # error 等待动画播出的最长时间（被更高优先级的会话挡住时）
            "latchMaxMs": 30_000,
            # Stop 之后保持 complete 的时长，然后自动回到 idle
            "completeHoldMs": 30_000,
            # Stop 时还有后台任务在跑：显示 waiting，最多等这么久（任务结束的通知没收到时兜底）
            "waitingMaxMs": 2 * 60 * 60_000,
        },
        "tools": {
            # 工具名：精确匹配，或写成 "/正则/标志"。按 confirm → read → write 的顺序匹配
            "confirm": ["AskUserQuestion", "ExitPlanMode"],
            "read": [
                "Read", "Grep", "Glob", "LS", "WebFetch", "WebSearch", "NotebookRead", "ToolSearch",
                "/^mcp__.*__(read|get|list|search|fetch|query)/i",
            ],
            "write": ["Edit", "MultiEdit", "Write", "NotebookEdit"],
            # 都没匹配上时的状态（包括 Bash）
            "default": "writing",
        },
        # 多会话汇总优先级，从高到低；同一组内取最近变化的会话
        "priority": [["confirmation"], ["error"], ["writing", "reading", "thinking"], ["complete"], ["waiting"], ["idle"], ["drowsy"]],
    },
}


def app_dir() -> Path:
    """程序所在的文件夹：打包版是 ClaudeChan.exe 所在目录，从源码运行是仓库根目录。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def data_dir() -> Path:
    """配置、窗口状态、日志等数据的目录（便携：跟着程序走）。"""
    return app_dir() / "data"


def config_path() -> Path:
    return data_dir() / "config.json"


def deep_merge(base: Any, over: Any) -> Any:
    """对象逐键合并；数组和其他值整体替换。"""
    if not isinstance(base, dict) or not isinstance(over, dict):
        return over
    out = dict(base)
    for k, v in over.items():
        out[k] = deep_merge(out[k], v) if k in out else v
    return out


def save_user_setting(keys: list[str], value: Any) -> None:
    """把一项设置写进 config.json：只改这一项，文件里其他手写的内容原样保留。
    文件存在但解析不了时不覆盖它（以免冲掉用户写到一半的内容），抛出 ValueError。"""
    path = config_path()
    data: dict[str, Any] = {}
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("config.json 的最外层不是对象")
    node = data
    for k in keys[:-1]:
        if not isinstance(node.get(k), dict):
            node[k] = {}
        node = node[k]
    node[keys[-1]] = value
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_config() -> tuple[dict[str, Any], str | None]:
    """读取并与默认值深度合并；文件有错时返回默认值和错误信息。"""
    defaults = copy.deepcopy(DEFAULT_CONFIG)
    path = config_path()
    if not path.exists():
        return defaults, None
    try:
        return deep_merge(defaults, json.loads(path.read_text(encoding="utf-8"))), None
    except Exception as e:  # noqa: BLE001 - 配置文件出错时照常启动
        return defaults, f"配置文件无法解析（{path}）：{e}"
