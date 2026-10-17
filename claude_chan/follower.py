"""跟随模式：找到 Claude 桌面版的主窗口就贴上去，找不到就回到桌面上原来的位置（后台任务照样能看）。

- 宿主移动、缩放：跟着走（follow.HostHooks 的回调里直接挪）。
- 宿主最小化、隐藏：一起藏起来；恢复后回来。
- 拖动桌宠：记住相对宿主的位置（贴哪一侧、离边多远），以后都按这个位置跟随。
- 宿主关掉：回到桌面原位，之后每秒找一次，Claude 重新打开就再贴上去。
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QTimer

from . import follow
from .window import ASPECT, MIN_WIDTH, PetWindow

DEFAULT_GAP_X, DEFAULT_GAP_Y = 12, 140  # 逻辑像素：贴右边，底下留出输入框的高度
DEFAULT_HEIGHT_FRACTION = 0.4  # 第一次跟随时，桌宠高度占宿主窗口高度的比例


class Follower:
    def __init__(self, window: PetWindow, processes: list[str], log: Callable[[str], None]) -> None:
        self.window = window
        self.processes = processes
        self.log = log
        self.host = 0
        self.hidden_by_host = False
        self._moving = False  # 正在由自己挪窗口（这时的 moveEvent 不算用户拖动）
        self._expect: tuple[int, int] | None = None
        self._hooks = follow.HostHooks(self._on_event) if follow.AVAILABLE else None
        self._settle = QTimer(singleShot=True, interval=300)
        self._settle.timeout.connect(self.sync)
        window.on_moved = self._on_moved
        window.on_flags_applied = self.sync
        window.on_follow_reset = self._reset
        if self.enabled:
            self.poll()

    # ---------- 开关 ----------

    @property
    def available(self) -> bool:
        return self._hooks is not None

    @property
    def enabled(self) -> bool:
        return self.available and self.window.following

    @property
    def attached(self) -> bool:
        return bool(self.host)

    def set_enabled(self, on: bool) -> None:
        if not self.available or on == self.window.following:
            return
        if on:
            self.window.remember_desktop_bounds()
        self.window.state["follow"]["enabled"] = on
        self.window.apply_flags()
        if on:
            self.log("跟随 Claude 窗口：开")
            self.poll()
        else:
            self._release()
            self.log("跟随 Claude 窗口：关，回到桌面")
        self.window.persist(immediate=True)

    # ---------- 宿主 ----------

    def poll(self) -> None:
        """每秒一次：宿主没了就放开，没有宿主就找一个。"""
        if not self.enabled:
            return
        if self.host and not follow.alive(self.host):
            self.log("Claude 窗口关了，回到桌面")
            self._release()
        if not self.host:
            host = follow.find_host(self.processes)
            if not host:
                return
            self._attach(host)
        self.sync()

    def _attach(self, host: int) -> None:
        self.host = host
        assert self._hooks
        self._hooks.attach(host)
        st = self.window.state["follow"]
        if not st.get("width"):
            f = follow.frame(host)
            if f:
                dpr = self.window.devicePixelRatioF() or 1
                st["width"] = max(MIN_WIDTH, round((f[3] - f[1]) / dpr * DEFAULT_HEIGHT_FRACTION / ASPECT))
        self._resize_to(st["width"])
        self.log("找到 Claude 窗口，贴上去了")

    def _release(self) -> None:
        if self._hooks:
            self._hooks.detach()
        pet = self._pet()
        if pet:
            follow.set_owner(pet, 0)
        self.host = 0
        self._expect = None
        self.window.restore_desktop_bounds()
        if self.hidden_by_host:
            self.hidden_by_host = False
            self.window.show()

    def _reset(self) -> None:
        """“重置位置和大小”：回到默认的贴法。"""
        st = self.window.state["follow"]
        st.update({"anchor": "right", "gapX": None, "gapY": None, "width": None})
        if self.host:
            self._attach(self.host)
            self.sync()

    def _on_event(self, event: int) -> None:
        if event in (follow.EVENT_OBJECT_DESTROY, follow.EVENT_OBJECT_HIDE):
            pet = self._pet()
            if pet:
                follow.set_owner(pet, 0)  # 宿主没了先解除关系，下次 poll 再决定
        self.sync()

    # ---------- 位置 ----------

    def _pet(self) -> int:
        return int(self.window.winId()) if self.window.windowHandle() else 0

    def _resize_to(self, width: int) -> None:
        width = max(MIN_WIDTH, int(width))
        self._moving = True
        try:
            self.window.resize(width, round(width * ASPECT))
        finally:
            self._moving = False

    def _gaps(self) -> tuple[str, int, int]:
        st = self.window.state["follow"]
        dpr = self.window.devicePixelRatioF() or 1
        gx = st.get("gapX")
        gy = st.get("gapY")
        return (st.get("anchor") or "right",
                round(DEFAULT_GAP_X * dpr) if gx is None else int(gx),
                round(DEFAULT_GAP_Y * dpr) if gy is None else int(gy))

    def sync(self) -> None:
        """按宿主现在的位置摆好桌宠；宿主不在屏幕上就一起藏起来。"""
        if not self.host or not self.enabled:
            return
        if not follow.shown(self.host):
            if self.window.isVisible():
                self.hidden_by_host = True
                self.window.hide()
            return
        if self.hidden_by_host:
            self.hidden_by_host = False
            self.window.show()
        pet = self._pet()
        host_frame = follow.frame(self.host)
        pet_rect = follow.window_rect(pet) if pet else None
        if not pet or not host_frame or not pet_rect:
            return
        follow.set_owner(pet, self.host)  # 改窗口标志会重建原生窗口，owner 要重新设
        anchor, gx, gy = self._gaps()
        x, y = follow.place(host_frame, (pet_rect[2] - pet_rect[0], pet_rect[3] - pet_rect[1]), anchor, gx, gy)
        if (x, y) != (pet_rect[0], pet_rect[1]):
            self._expect = (x, y)
            self._moving = True
            try:
                follow.move(pet, x, y)
            finally:
                self._moving = False

    def _on_moved(self) -> None:
        """桌宠的位置或大小变了：不是自己挪的，就是用户拖动或缩放了，记下新的相对位置。"""
        if not self.host or self._moving or not self.enabled:
            return
        pet = self._pet()
        pet_rect = follow.window_rect(pet) if pet else None
        host_frame = follow.frame(self.host)
        if not pet_rect or not host_frame or (pet_rect[0], pet_rect[1]) == self._expect:
            return
        anchor, gx, gy = follow.offsets(host_frame, pet_rect)
        st = self.window.state["follow"]
        st.update({"anchor": anchor, "gapX": gx, "gapY": gy, "width": self.window.width()})
        self._expect = None
        self._settle.start()  # 拖完再按宿主边界收一下
