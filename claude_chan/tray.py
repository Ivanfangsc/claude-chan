"""托盘图标与菜单（右键桌宠弹出的也是同一个菜单）。"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QPoint, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from . import autostart
from .model import DisplayTarget
from .window import PetWindow


class PetTray:
    def __init__(
        self,
        icon: QIcon,
        pet: PetWindow,
        open_debug: Callable[[], None] | None,
        reload_config: Callable[[], None],
        open_config_folder: Callable[[], None],
        quit_app: Callable[[], None],
        skins: list[tuple[str, str]] | None = None,
        current_skin: Callable[[], str] = lambda: "adult",
        switch_skin: Callable[[str], None] = lambda _name: None,
        follow: tuple[Callable[[], bool], Callable[[bool], None]] | None = None,
        version: str = "",
        switch_style: tuple[Callable[[], str], Callable[[str], None]] | None = None,
    ) -> None:
        self._pet = pet
        self._menu = QMenu()
        # 第一行：版本号；有新版本时变成可点的“下载新版本”
        self._version = version
        self._update_url = ""
        self._about = self._menu.addAction(f"Claude-Chan v{version}" if version else "Claude-Chan")
        self._about.setEnabled(False)
        self._about.triggered.connect(lambda: self._update_url and QDesktopServices.openUrl(QUrl(self._update_url)))
        self._menu.addSeparator()
        self._current_skin = current_skin
        self._skin_actions: dict[str, QAction] = {}
        self._show = self._check("显示桌宠", pet.toggle_visible)
        self._top = self._check("置顶", lambda: pet.set_always_on_top(self._top.isChecked()))
        self._through = self._check("鼠标穿透", lambda: pet.set_click_through(self._through.isChecked()))
        self._follow_state = follow[0] if follow else None
        self._follow = (self._check("跟随 Claude 窗口", lambda: follow[1](self._follow.isChecked()) or self.refresh())
                        if follow else None)
        self._menu.addSeparator()
        if open_debug:  # 发布版默认没有调试面板
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
        # 切换方式：流畅优先（小动作播完再走）/ 响应优先（立即切走）
        self._style_state = switch_style[0] if switch_style else None
        self._style_actions: dict[str, QAction] = {}
        if switch_style:
            menu = self._menu.addMenu("切换方式")
            for style, label in (("smooth", "流畅优先：动作做完再切换"), ("responsive", "响应优先：立即切换")):
                action = menu.addAction(label)
                action.setCheckable(True)
                action.triggered.connect(lambda _=False, s=style: switch_style[1](s))
                self._style_actions[style] = action
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
        if self._style_state:
            for style, action in self._style_actions.items():
                action.setChecked(style == self._style_state())

    def popup(self, pos: QPoint) -> None:
        self.refresh()
        self._menu.popup(pos)

    def show_target(self, t: DisplayTarget) -> None:
        who = f"（{t.project}）" if t.project and not t.manual else ""
        self._tray.setToolTip(f"Claude-Chan · {t.state}{who}")

    def show_update(self, tag: str, url: str) -> None:
        """有新版本：菜单第一行变成下载入口；同一个版本只弹一次通知。"""
        first = self._update_url != url
        self._update_url = url
        self._about.setText(f"有新版本 {tag}，点击下载（当前 v{self._version}）")
        self._about.setEnabled(True)
        if first:
            self._tray.showMessage("Claude-Chan 有新版本", f"{tag} 已发布，右键托盘图标可以打开下载页。")

    def hide(self) -> None:
        self._tray.hide()
