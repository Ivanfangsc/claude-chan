"""从本机的会话记录（hook 事件里的 transcript_path，JSONL）读两样东西给气泡用：
- Claude 最后说的一句话（发出请求之前的说明，比如“依赖装坏了，我先删掉重装”）；
- 会话标题：记录开头的 custom-title（和桌面版侧边栏的标题一样）；没有的话用这个会话里你问的第一句话。

读不到（WSL 的路径、文件不存在）就返回 None。会话记录可能有几十 MB，只从末尾往前分块读、最多读 MAX_TAIL，
开头只读 HEAD_LINES 行。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterator

CHUNK = 512 * 1024
MAX_TAIL = 4 * 1024 * 1024
HEAD_LINES = 400
# 会话被压缩后接着进行时，系统插进来的摘要（不是用户自己问的）
CONTINUED = ("This session is being continued", "This conversation is being continued")


def _text_of(msg: dict[str, Any]) -> str:
    content = msg.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text")
    return ""


def _clean(s: str) -> str:
    s = re.sub(r"[`*_#>]+", "", s)
    return re.sub(r"\s+", " ", s).strip()


def _path(p: str | None) -> Path | None:
    if not p or p.startswith("/"):  # WSL 的路径在 Windows 上读不到
        return None
    path = Path(p)
    return path if path.is_file() else None


def _is_tool_result(o: dict[str, Any]) -> bool:
    content = (o.get("message") or {}).get("content")
    return isinstance(content, list) and any(isinstance(c, dict) and c.get("type") == "tool_result" for c in content)


def _is_real_prompt(o: dict[str, Any]) -> bool:
    """用户自己打的话：不是工具结果，也不是系统插进来的内容（isMeta、压缩摘要、以 < 开头的标签）。"""
    if o.get("type") != "user" or o.get("isMeta") or o.get("isCompactSummary") or _is_tool_result(o):
        return False
    text = _text_of(o.get("message") or {}).strip()
    return bool(text) and not text.startswith("<") and not text.startswith(CONTINUED)


def _lines_from_end(path: Path) -> Iterator[str]:
    """从文件末尾往前一行一行地给出，最多读 MAX_TAIL。"""
    with path.open("rb") as f:
        f.seek(0, 2)
        pos = f.tell()
        stop = max(0, pos - MAX_TAIL)
        rest = b""
        while pos > stop:
            step = min(CHUNK, pos - stop)
            pos -= step
            f.seek(pos)
            block = f.read(step) + rest
            lines = block.split(b"\n")
            if pos > stop:
                rest, lines = lines[0], lines[1:]  # 第一段可能是半行，留到下一块拼上
            for raw in reversed(lines):
                if raw.strip():
                    yield raw.decode("utf-8", errors="ignore")


def last_assistant_text(transcript: str | None) -> str | None:
    """会话记录里 Claude 最后一段文字（发出请求前说的话）；在那之后你又说了话就返回 None。"""
    path = _path(transcript)
    if not path:
        return None
    try:
        for line in _lines_from_end(path):
            try:
                o = json.loads(line)
            except ValueError:
                continue
            if o.get("type") == "assistant":
                text = _clean(_text_of(o.get("message") or {}))
                if text:
                    return text
            elif _is_real_prompt(o):
                return None
    except OSError:
        return None
    return None


def session_title(transcript: str | None) -> str | None:
    """会话标题：开头的 custom-title；没有就用你问的第一句话。"""
    path = _path(transcript)
    if not path:
        return None
    first: str | None = None
    try:
        with path.open(encoding="utf-8", errors="ignore") as f:
            for k, line in enumerate(f):
                if k >= HEAD_LINES:
                    break
                try:
                    o = json.loads(line)
                except ValueError:
                    continue
                if o.get("type") == "custom-title" and o.get("customTitle"):
                    return str(o["customTitle"])
                if first is None and _is_real_prompt(o):
                    first = _clean(_text_of(o.get("message") or {}))
    except OSError:
        return None
    return first
