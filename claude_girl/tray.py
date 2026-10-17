"""托盘图标与菜单（右键桌宠弹出的也是同一个菜单）。"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QPoint
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from . import autostart
from .model import DisplayTarget
from .window import PetWindow


class PetTray:
    def __init__(
        self,
        icon: QIcon,
        pet: PetWindow,
        open_debug: Callable[[], None],
        reload_config: Callable[[], None],
        open_config_folder: Callable[[], None],
        quit_app: Callable[[], None],
        skins: list[tuple[str, str]] | None = None,
        current_skin: Callable[[], str] = lambda: "adult",
        switch_skin: Callable[[str], None] = lambda _name: None,
        follow: tuple[Callable[[], bool], Callable[[bool], None]] | None = None,
    ) -> None:
        self._pet = pet
        self._menu = QMenu()
        self._current_skin = current_skin
        self._skin_actions: dict[str, QAction] = {}
        self._show = self._check("显示桌宠", pet.toggle_visible)
        self._top = self._check("置顶", lambda: pet.set_always_on_top(self._top.isChecked()))
        self._through = self._check("鼠标穿透", lambda: pet.set_click_through(self._through.isChecked()))
        self._follow_state = follow[0] if follow else None
        self._follow = (self._check("跟随 Claude 窗口", lambda: follow[1](self._follow.isChecked()) or self.refresh())
                        if follow else None)
        self._menu.addSeparator()
        self._menu.addAction("打开调试面板", open_debug)
        self._menu.addAction("重新加载配置", reload_config)
        self._menu.addAction("打开配置文件夹", open_config_folder)
        self._menu.addAction("重置位置和大小", pet.reset_geometry)
        if skins and len(skins) > 1:
            menu = self._menu.addMenu("形象")
            for name, label in skins:
                action = menu.addAction(label)
                action.setCheckable(True)
                action.triggered.connect(lambda _=False, n=name: switch_skin(n))
                self._skin_actions[name] = action
        self._autostart = self._check("开机自启", lambda: autostart.set_enabled(self._autostart.isChecked()))
        self._menu.addSeparator()
        self._menu.addAction("退出", quit_app)
        self._menu.aboutToShow.connect(self.refresh)

        self._tray = QSystemTrayIcon(icon)
        self._tray.setContextMenu(self._menu)
        self._tray.setToolTip("Claude-Chan")
        self._tray.activated.connect(self._activated)
        self._tray.show()
        self.refresh()

    def _check(self, text: str, handler: Callable[[], None]) -> QAction:
        action = self._menu.addAction(text)
        action.setCheckable(True)
        action.triggered.connect(handler)
        return action

    def _activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:  # 左键单击
            self._pet.toggle_visible()

    def refresh(self) -> None:
        """窗口状态变化后同步勾选状态。"""
        state = self._pet.state
        self._show.setChecked(self._pet.isVisible())
        self._top.setChecked(state["alwaysOnTop"])
        following = bool(self._follow_state and self._follow_state())
        self._top.setEnabled(not following)  # 跟随时层级由 Claude 窗口决定
        if self._follow:
            self._follow.setChecked(following)
        self._through.setChecked(state["clickThrough"])
        self._autostart.setChecked(autostart.is_enabled())
        for name, action in self._skin_actions.items():
            action.setChecked(name == self._current_skin())

    def popup(self, pos: QPoint) -> None:
        self.refresh()
        self._menu.popup(pos)

    def show_target(self, t: DisplayTarget) -> None:
        who = f"（{t.project}）" if t.project and not t.manual else ""
        self._tray.setToolTip(f"Claude-Chan · {t.state}{who}")

    def hide(self) -> None:
        self._tray.hide()
