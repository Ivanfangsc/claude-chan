"""点气泡时跳回发出请求的那个会话（只在 Windows 上实现）。

- 桌面版的会话：Claude 桌面版把每个会话的元数据存在 %APPDATA%\\Claude\\claude-code-sessions\\…\\local_*.json，
  里面有对应的 Claude Code 会话编号（cliSessionId / priorCliSessionIds）和侧边栏标题。找到后用
  claude://claude.ai/epitaxy/<local 编号> 打开，桌面版会直接切到这个会话（这个链接格式没有公开文档，
  桌面版改了就退回到只把 Claude 窗口切到前面）。
- 命令行（CLI）的会话：收事件时由连接查出发送方的进程（hook_pid），顺着父进程往上找第一个有窗口的程序
  （Windows Terminal、VS Code、命令行窗口），点气泡时把它切到前面。Windows Terminal 的多个标签页没法指定。
- WSL 的事件经过虚拟网络过来，查不到进程，退回到把 Windows Terminal 切到前面。
"""

from __future__ import annotations

import ctypes
import json
import os
import sys
import time
from ctypes import wintypes
from pathlib import Path

if sys.platform == "win32":
    _user32 = ctypes.windll.user32
    _kernel32 = ctypes.windll.kernel32
    _iphlpapi = ctypes.windll.iphlpapi

    class _TcpRow(ctypes.Structure):
        _fields_ = [("state", wintypes.DWORD), ("local_addr", wintypes.DWORD), ("local_port", wintypes.DWORD),
                    ("remote_addr", wintypes.DWORD), ("remote_port", wintypes.DWORD), ("pid", wintypes.DWORD)]

    class _ProcEntry(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
                    ("szExeFile", ctypes.c_wchar * 260)]

    _EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def _port(v: int) -> int:
        return ((v & 0xFF) << 8) | ((v >> 8) & 0xFF)

    def pid_of_client(client_port: int, server_port: int) -> int:
        """本机 TCP 连接里，从 client_port 连到 server_port 的那一端属于哪个进程；找不到返回 0。"""
        size = wintypes.DWORD(0)
        _iphlpapi.GetExtendedTcpTable(None, ctypes.byref(size), False, 2, 4, 0)  # AF_INET，TCP_TABLE_OWNER_PID_CONNECTIONS
        buf = ctypes.create_string_buffer(size.value + 4096)
        size = wintypes.DWORD(len(buf))
        if _iphlpapi.GetExtendedTcpTable(buf, ctypes.byref(size), False, 2, 4, 0) != 0:
            return 0
        n = ctypes.cast(buf, ctypes.POINTER(wintypes.DWORD))[0]
        rows = ctypes.cast(ctypes.addressof(buf) + 4, ctypes.POINTER(_TcpRow * n)).contents
        for r in rows:
            if _port(r.local_port) == client_port and _port(r.remote_port) == server_port:
                return int(r.pid)
        return 0

    def _process_table() -> dict[int, tuple[int, str]]:
        snap = _kernel32.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
        out: dict[int, tuple[int, str]] = {}
        if snap in (0, -1):
            return out
        try:
            e = _ProcEntry()
            e.dwSize = ctypes.sizeof(_ProcEntry)
            ok = _kernel32.Process32FirstW(snap, ctypes.byref(e))
            while ok:
                out[e.th32ProcessID] = (e.th32ParentProcessID, e.szExeFile.lower())
                ok = _kernel32.Process32NextW(snap, ctypes.byref(e))
        finally:
            _kernel32.CloseHandle(snap)
        return out

    def _windows_of(pid: int) -> list[int]:
        found: list[int] = []

        @_EnumProc
        def visit(hwnd, _lparam):  # noqa: ANN001
            p = wintypes.DWORD()
            _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
            if p.value == pid and _user32.IsWindowVisible(hwnd) and not _user32.GetWindow(hwnd, 4) \
                    and _user32.GetWindowTextLengthW(hwnd) > 0:
                found.append(int(hwnd))
            return True

        _user32.EnumWindows(visit, 0)
        return found

    def window_of_process(pid: int) -> int:
        """从这个进程往上找，第一个有主窗口的祖先进程的窗口（终端、VS Code……）。"""
        table = _process_table()
        seen = set()
        while pid and pid not in seen and len(seen) < 12:
            seen.add(pid)
            wins = _windows_of(pid)
            if wins:
                return wins[0]
            pid = table.get(pid, (0, ""))[0]
        return 0

    def window_of_exe(names: tuple[str, ...]) -> int:
        """这些程序（小写的 exe 名）的第一个主窗口。"""
        table = _process_table()
        for pid, (_ppid, exe) in table.items():
            if exe in names:
                wins = _windows_of(pid)
                if wins:
                    return wins[0]
        return 0

    def activate(hwnd: int) -> bool:
        if not hwnd:
            return False
        if _user32.IsIconic(hwnd):
            _user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        return bool(_user32.SetForegroundWindow(hwnd))

else:

    def pid_of_client(client_port: int, server_port: int) -> int:  # noqa: ARG001
        return 0

    def window_of_process(pid: int) -> int:  # noqa: ARG001
        return 0

    def window_of_exe(names: tuple[str, ...]) -> int:  # noqa: ARG001
        return 0

    def activate(hwnd: int) -> bool:  # noqa: ARG001
        return False


# ---------- 桌面版的会话 ----------

_cache: tuple[float, dict[str, tuple[str, str]]] = (0.0, {})


def _desktop_dir() -> Path:
    return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "Claude" / "claude-code-sessions"


def desktop_sessions(root: Path | None = None, ttl: float = 5.0) -> dict[str, tuple[str, str]]:
    """Claude Code 会话编号 → (桌面版会话编号, 侧边栏标题)。几秒内重复调用用缓存。"""
    global _cache
    now = time.monotonic()
    if root is None and now - _cache[0] < ttl:
        return _cache[1]
    out: dict[str, tuple[str, str]] = {}
    base = root or _desktop_dir()
    if base.is_dir():
        for f in base.glob("*/*/local_*.json"):
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            local, title = d.get("sessionId"), d.get("title") or ""
            if not local:
                continue
            for cli in [d.get("cliSessionId"), *(d.get("priorCliSessionIds") or [])]:
                if isinstance(cli, str):
                    out[cli] = (local, title)
    if root is None:
        _cache = (now, out)
    return out


def open_desktop_session(local_id: str) -> bool:
    try:
        os.startfile(f"claude://claude.ai/epitaxy/{local_id}")  # type: ignore[attr-defined]
        return True
    except (OSError, AttributeError):
        return False
