"""检测前台窗口是否在某个屏幕上全屏（游戏、视频、演示）。只在 Windows 上实现，其他平台总是返回 False。

全屏窗口盖住整个屏幕（包括任务栏）；普通的最大化窗口只盖住工作区，不算全屏。桌面本身（Progman / WorkerW）也不算。
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

Rect = tuple[int, int, int, int]  # left, top, right, bottom

_IGNORED_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"}


def covers(window: Rect, monitor: Rect) -> bool:
    """窗口是否盖住整个屏幕。"""
    return window[0] <= monitor[0] and window[1] <= monitor[1] and window[2] >= monitor[2] and window[3] >= monitor[3]


if sys.platform == "win32":
    _user32 = ctypes.windll.user32

    class _MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]

    def _monitor(hwnd: int) -> tuple[int, Rect] | None:
        mon = _user32.MonitorFromWindow(wintypes.HWND(hwnd), 2)  # MONITOR_DEFAULTTONEAREST
        info = _MONITORINFO()
        info.cbSize = ctypes.sizeof(_MONITORINFO)
        if not mon or not _user32.GetMonitorInfoW(mon, ctypes.byref(info)):
            return None
        r = info.rcMonitor
        return mon, (r.left, r.top, r.right, r.bottom)

    def fullscreen_over(own_hwnd: int) -> bool:
        """前台窗口是否在桌宠所在的屏幕上全屏（前台窗口是桌宠自己时返回 False）。"""
        fg = _user32.GetForegroundWindow()
        if not fg or fg == own_hwnd:
            return False
        name = ctypes.create_unicode_buffer(64)
        _user32.GetClassNameW(wintypes.HWND(fg), name, 64)
        if name.value in _IGNORED_CLASSES:
            return False
        fg_mon, own_mon = _monitor(fg), _monitor(own_hwnd)
        if not fg_mon or not own_mon or fg_mon[0] != own_mon[0]:
            return False
        r = wintypes.RECT()
        if not _user32.GetWindowRect(wintypes.HWND(fg), ctypes.byref(r)):
            return False
        return covers((r.left, r.top, r.right, r.bottom), fg_mon[1])

else:

    def fullscreen_over(own_hwnd: int) -> bool:  # noqa: ARG001
        return False
