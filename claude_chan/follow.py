"""跟随宿主窗口（Claude 桌面版）：贴在窗口的一角，窗口移动、缩放时跟着走，被别的窗口挡住时一起被挡，最小化时一起藏起来。

只在 Windows 上实现。做法参考 GPT-Niang：
- 跟随：SetWinEventHook 监听宿主进程的窗口移动事件，在回调里直接挪窗口；不用定时器轮询，否则会拖在后面。
- 层级：把桌宠的 owner 设为宿主窗口，桌宠就始终紧贴在宿主上面一层，别的窗口盖住宿主时也盖住桌宠。
  跨进程的 owner 被销毁时，Windows 不会销毁桌宠的窗口（实测）；保险起见宿主隐藏或销毁时先解除 owner。

坐标都是物理像素（Qt 6 默认 Per-Monitor DPI 感知，和 Win32 一致）。
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from typing import Callable

Rect = tuple[int, int, int, int]  # left, top, right, bottom


def place(host: Rect, size: tuple[int, int], anchor: str, gap_x: int, gap_y: int) -> tuple[int, int]:
    """桌宠左上角的位置：横向贴 anchor 一侧的边，离边 gap_x；纵向离宿主底边 gap_y。限制在宿主窗口内。"""
    left, top, right, bottom = host
    w, h = size
    x = right - gap_x - w if anchor == "right" else left + gap_x
    y = bottom - gap_y - h
    x = max(left, min(right - w, x))
    y = max(top, min(bottom - h, y))
    return x, y


def offsets(host: Rect, pet: Rect) -> tuple[str, int, int]:
    """反过来：由桌宠当前的位置算出贴哪一侧、离边多远（拖动后记住位置用）。"""
    left, top, right, bottom = host
    cx = (pet[0] + pet[2]) / 2
    anchor = "right" if cx >= (left + right) / 2 else "left"
    gap_x = right - pet[2] if anchor == "right" else pet[0] - left
    return anchor, max(0, gap_x), max(0, bottom - pet[3])


if sys.platform == "win32":
    _user32 = ctypes.windll.user32
    _kernel32 = ctypes.windll.kernel32
    _dwmapi = ctypes.windll.dwmapi

    _user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    _user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
    _user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
    _user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]

    GWLP_HWNDPARENT = -8
    GWL_EXSTYLE = -20
    WS_EX_TOOLWINDOW = 0x80
    DWMWA_EXTENDED_FRAME_BOUNDS = 9
    DWMWA_CLOAKED = 14
    OBJID_WINDOW = 0
    # 系统事件：前台切换、拖动开始/结束、最小化开始/结束；对象事件：销毁、显示、隐藏、位置变化
    EVENT_SYSTEM_FOREGROUND, EVENT_SYSTEM_MINIMIZEEND = 0x0003, 0x0017
    EVENT_OBJECT_DESTROY, EVENT_OBJECT_LOCATIONCHANGE = 0x8001, 0x800B
    EVENT_OBJECT_HIDE = 0x8003

    _WinEventProc = ctypes.WINFUNCTYPE(None, wintypes.HANDLE, wintypes.DWORD, wintypes.HWND, ctypes.c_long,
                                       ctypes.c_long, wintypes.DWORD, wintypes.DWORD)
    _EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def _process_name(hwnd: int) -> tuple[int, str]:
        pid = wintypes.DWORD()
        _user32.GetWindowThreadProcessId(wintypes.HWND(hwnd), ctypes.byref(pid))
        h = _kernel32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return pid.value, ""
        try:
            buf = ctypes.create_unicode_buffer(260)
            n = wintypes.DWORD(260)
            if not _kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)):
                return pid.value, ""
            return pid.value, buf.value.rsplit("\\", 1)[-1].lower()
        finally:
            _kernel32.CloseHandle(h)

    def _cloaked(hwnd: int) -> bool:
        v = wintypes.DWORD()
        return _dwmapi.DwmGetWindowAttribute(wintypes.HWND(hwnd), DWMWA_CLOAKED, ctypes.byref(v), 4) == 0 and v.value != 0

    def shown(hwnd: int) -> bool:
        """宿主是否正在屏幕上：存在、可见、没最小化、没被系统隐藏（虚拟桌面切走时是 cloaked）。"""
        return bool(_user32.IsWindow(hwnd) and _user32.IsWindowVisible(hwnd) and not _user32.IsIconic(hwnd)
                    and not _cloaked(hwnd))

    def alive(hwnd: int) -> bool:
        return bool(hwnd and _user32.IsWindow(hwnd) and _user32.IsWindowVisible(hwnd))

    def frame(hwnd: int) -> Rect | None:
        """窗口看得见的边框（不含 Win10/11 四周看不见的缩放边）。"""
        r = wintypes.RECT()
        if _dwmapi.DwmGetWindowAttribute(wintypes.HWND(hwnd), DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(r),
                                         ctypes.sizeof(r)) != 0:
            if not _user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(r)):
                return None
        return r.left, r.top, r.right, r.bottom

    def window_rect(hwnd: int) -> Rect | None:
        r = wintypes.RECT()
        if not _user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(r)):
            return None
        return r.left, r.top, r.right, r.bottom

    def find_host(processes: list[str]) -> int:
        """这些进程的主窗口：顶层、没有 owner、有标题、不是工具窗口、可见。优先选没最小化的里面最大的。"""
        wanted = {p.lower() for p in processes}
        found: list[tuple[int, int, int]] = []  # (没最小化, 面积, hwnd)

        @_EnumProc
        def visit(hwnd, _lparam):  # noqa: ANN001
            if not _user32.IsWindowVisible(hwnd) or _user32.GetWindow(hwnd, 4):  # GW_OWNER
                return True
            if _user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW:
                return True
            if _user32.GetWindowTextLengthW(hwnd) == 0 or _process_name(hwnd)[1] not in wanted:
                return True
            r = frame(hwnd) or (0, 0, 0, 0)
            iconic = bool(_user32.IsIconic(hwnd))
            found.append((0 if iconic else 1, (r[2] - r[0]) * (r[3] - r[1]), int(hwnd)))
            return True

        _user32.EnumWindows(visit, 0)
        return max(found)[2] if found else 0

    def set_owner(pet: int, owner: int) -> bool:
        _user32.SetWindowLongPtrW(pet, GWLP_HWNDPARENT, owner)
        return _user32.GetWindowLongPtrW(pet, GWLP_HWNDPARENT) == owner

    def move(pet: int, x: int, y: int) -> None:
        # 只改位置：不改大小、不改层级、不激活
        _user32.SetWindowPos(wintypes.HWND(pet), None, x, y, 0, 0, 0x0001 | 0x0004 | 0x0010)

    class HostHooks:
        """监听一个窗口的移动、显示隐藏、最小化、销毁；回调在主线程（Qt 的消息循环）里执行。"""

        def __init__(self, on_event: Callable[[int], None]) -> None:
            self._on_event = on_event
            self._proc = _WinEventProc(self._callback)  # 必须保留引用，否则回调会被回收
            self._hooks: list[int] = []
            self.host = 0

        def attach(self, host: int) -> None:
            self.detach()
            self.host = host
            pid = wintypes.DWORD()
            _user32.GetWindowThreadProcessId(wintypes.HWND(host), ctypes.byref(pid))
            for first, last in ((EVENT_SYSTEM_FOREGROUND, EVENT_SYSTEM_MINIMIZEEND),
                                (EVENT_OBJECT_DESTROY, EVENT_OBJECT_LOCATIONCHANGE)):
                h = _user32.SetWinEventHook(first, last, None, self._proc, pid.value, 0, 0)  # WINEVENT_OUTOFCONTEXT
                if h:
                    self._hooks.append(h)

        def detach(self) -> None:
            for h in self._hooks:
                _user32.UnhookWinEvent(h)
            self._hooks.clear()
            self.host = 0

        def _callback(self, _hook, event, hwnd, obj, _child, _thread, _time) -> None:  # noqa: ANN001
            if hwnd == self.host and obj == OBJID_WINDOW:
                try:
                    self._on_event(event)
                except Exception:  # noqa: BLE001 - 回调里抛出的异常会弄乱消息循环
                    pass

    AVAILABLE = True

else:
    AVAILABLE = False
