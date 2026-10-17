"""Claude Code hook 事件 → 会话动作。纯函数，不含计时逻辑。

事件名和字段以官方文档为准：https://code.claude.com/docs/en/hooks
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from typing import Any, Literal

# 这些通知都表示 Claude 在等用户操作
WAITING_NOTIFICATIONS = {"permission_prompt", "elicitation_dialog", "elicitation_url_dialog", "agent_needs_input"}

ActionKind = Literal["base", "postTool", "toolFailure", "stop", "stopFailure", "end", "touch"]


@dataclass(frozen=True)
class Action:
    """
    - base：直接设置会话的基础状态；clear_latch 同时清除待播的 error（包括常驻的）
    - postTool：PostToolUse，防抖后回到 thinking
    - toolFailure：PostToolUseFailure，播一次 error（有去重），之后回到 thinking
    - stop：Stop，complete 保持一段时间后回到 idle
    - stopFailure：StopFailure，error 常驻，直到下一次 UserPromptSubmit
    - end：移除会话
    - touch：只刷新活跃时间
    """

    kind: ActionKind
    state: str | None = None
    clear_latch: bool = False


def map_event(e: dict[str, Any], tools: dict[str, Any]) -> Action:
    name = e.get("hook_event_name")
    if name == "SessionStart":
        return Action("base", "idle", clear_latch=True)
    if name == "UserPromptSubmit":
        return Action("base", "thinking", clear_latch=True)
    if name == "PreToolUse":
        return Action("base", tool_state(e.get("tool_name") or "", tools))
    if name == "PostToolUse":
        return Action("postTool")
    if name == "PostToolUseFailure":
        # is_interrupt：调用被中止而不是出错，不播 error
        return Action("postTool") if e.get("is_interrupt") is True else Action("toolFailure")
    if name == "PermissionRequest":
        return Action("base", "confirmation")
    if name == "PermissionDenied":
        return Action("base", "thinking")
    if name == "Notification":
        kind = e.get("notification_type")
        if kind in WAITING_NOTIFICATIONS:
            return Action("base", "confirmation")
        # 等待用户输入一段时间后触发；用户中断时 Stop 不会触发，靠它回到 idle
        if kind == "idle_prompt":
            return Action("base", "idle")
        return Action("touch")
    if name == "Stop":
        return Action("stop")
    if name == "StopFailure":
        return Action("stopFailure")
    if name == "SessionEnd":
        return Action("end")
    # SubagentStop、PreCompact 等：不改变状态
    return Action("touch")


def _matches(pattern: str, name: str) -> bool:
    m = re.fullmatch(r"/(.*)/([a-z]*)", pattern)
    if not m:
        return pattern == name
    flags = re.IGNORECASE if "i" in m.group(2) else 0
    try:
        return re.search(m.group(1), name, flags) is not None
    except re.error:
        return False


def tool_state(name: str, tools: dict[str, Any]) -> str:
    if any(_matches(p, name) for p in tools["confirm"]):
        return "confirmation"
    if any(_matches(p, name) for p in tools["read"]):
        return "reading"
    if any(_matches(p, name) for p in tools["write"]):
        return "writing"
    return tools["default"]


def source_of(cwd: str | None, platform: str = sys.platform) -> str:
    """桌宠在 Windows 上时，POSIX 路径只可能来自 WSL；在 macOS / Linux 上就是本机，不标来源。"""
    if not cwd:
        return "unknown"
    if re.match(r"^[A-Za-z]:[\\/]", cwd) or cwd.startswith("\\\\"):
        return "windows"
    if cwd.startswith("/") and platform == "win32":
        return "wsl"
    return "unknown"


def project_of(cwd: str | None) -> str:
    if not cwd:
        return "未知项目"
    parts = [p for p in re.split(r"[\\/]+", cwd) if p]
    return parts[-1] if parts else cwd
