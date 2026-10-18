"""等你确认时，Claude 具体想做什么：从 hook 事件里取出给气泡看的内容。纯函数。

字段以官方文档为准：https://code.claude.com/docs/en/hooks
- PermissionRequest：tool_name + tool_input（命令、文件、网址……）
- PreToolUse AskUserQuestion：问题和选项；ExitPlanMode：计划
- Notification：elicitation 时 message 是 MCP 服务器写的说明；permission_prompt 的 message 是固定的一句，没有新信息
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

COMMAND_TOOLS = {"Bash", "PowerShell"}
EDIT_TOOLS = {"Edit", "MultiEdit"}


@dataclass(frozen=True)
class Ask:
    verb: str  # 标题行：等你确认 / 想问你 / 计划写好了 / 等你填写
    text: str | None = None  # 主体：问题原文、计划标题、命令说明、MCP 的说明
    detail: str | None = None  # 等宽小字：文件和改动行数、网址、工具名
    command: str | None = None  # 完整命令（设置里允许时才显示）
    options: tuple[str, ...] = ()  # 问题的选项
    say: str | None = None  # Claude 在请求之前说的最后一句话（从会话记录读，见 transcript.py）


def _base(path: str | None) -> str:
    return re.split(r"[\\/]", path or "")[-1] or (path or "")


def _diff_counts(old: str, new: str) -> tuple[int, int]:
    added = removed = 0
    for line in difflib.ndiff(old.splitlines(), new.splitlines()):
        if line.startswith("+ "):
            added += 1
        elif line.startswith("- "):
            removed += 1
    return added, removed


def _tool_ask(tool: str, inp: dict[str, Any]) -> Ask:
    if tool in COMMAND_TOOLS:
        desc = (inp.get("description") or "").strip() or None
        return Ask("等你确认", text=desc or "想运行一条命令", command=(inp.get("command") or "").strip() or None)
    if tool in EDIT_TOOLS:
        edits = inp.get("edits") if tool == "MultiEdit" else [inp]
        a = r = 0
        for ed in edits or []:
            da, dr = _diff_counts(ed.get("old_string") or "", ed.get("new_string") or "")
            a, r = a + da, r + dr
        return Ask("等你确认", text="想修改文件", detail=f"{_base(inp.get('file_path'))}  +{a} −{r}")
    if tool == "Write":
        n = len((inp.get("content") or "").splitlines())
        return Ask("等你确认", text="想写入文件", detail=f"{_base(inp.get('file_path'))}  {n} 行")
    if tool == "NotebookEdit":
        return Ask("等你确认", text="想修改笔记本", detail=_base(inp.get("notebook_path")))
    if tool == "WebFetch":
        host = urlparse(inp.get("url") or "").netloc or inp.get("url")
        return Ask("等你确认", text="想打开网页", detail=host)
    if tool == "WebSearch":
        return Ask("等你确认", text="想上网搜索", detail=inp.get("query"))
    if tool.startswith("mcp__"):
        parts = tool.split("__")
        server = parts[1] if len(parts) > 1 else tool
        name = parts[2] if len(parts) > 2 else ""
        return Ask("等你确认", text=f"想用 {server} 的工具", detail=name or None)
    return Ask("等你确认", text=f"想用 {tool}")


def _plan_ask(inp: dict[str, Any]) -> Ask:
    plan = inp.get("plan") or ""
    lines = [ln.strip() for ln in plan.splitlines() if ln.strip()]
    title = next((ln.lstrip("#").strip() for ln in lines if ln.startswith("#")), lines[0] if lines else None)
    steps = sum(1 for ln in lines if re.match(r"^(\d+[.)]|[-*])\s", ln))
    return Ask("计划写好了", text=title or "等你过目", detail=f"{steps} 步" if steps else None)


def _question_ask(inp: dict[str, Any]) -> Ask:
    qs = inp.get("questions") or []
    if not qs:
        return Ask("想问你")
    q = qs[0]
    opts = tuple(o.get("label", "") for o in q.get("options") or [] if o.get("label"))
    more = f"（共 {len(qs)} 个问题）" if len(qs) > 1 else ""
    return Ask("想问你", text=(q.get("question") or "") + more, options=opts)


def describe(e: dict[str, Any]) -> Ask | None:
    """这个事件让会话进入“等你确认”时，给气泡的内容；不是这类事件或没有新信息时返回 None。"""
    name = e.get("hook_event_name")
    tool = e.get("tool_name") or ""
    inp = e.get("tool_input") if isinstance(e.get("tool_input"), dict) else {}
    if name in ("PermissionRequest", "PreToolUse"):
        if tool == "AskUserQuestion":
            return _question_ask(inp)
        if tool == "ExitPlanMode":
            return _plan_ask(inp)
        if name == "PermissionRequest":
            return _tool_ask(tool, inp)
        return None
    if name == "Notification":
        kind = e.get("notification_type")
        msg = (e.get("message") or "").strip() or None
        if kind in ("elicitation_dialog", "elicitation_url_dialog"):
            return Ask("等你填写", text=msg)
        if kind == "agent_needs_input":
            return Ask("等你回复", text=msg)
    return None
