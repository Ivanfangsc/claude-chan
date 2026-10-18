"""托盘图标与菜单（右键桌宠弹出的也是同一个菜单）。

菜单只放常用的：版本号（有新版本时变成下载入口）、显示桌宠、设置、退出。其余选项都在设置窗口里。
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QPoint, QUrl
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from .model import DisplayTarget
from .window import PetWindow


class PetTray:
    def __init__(
        self,
        icon: QIcon,
        pet: PetWindow,
        open_settings: Callable[[], None],
        quit_app: Callable[[], None],
        open_debug: Callable[[], None] | None = None,
        version: str = "",
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
        self._show = self._menu.addAction("显示桌宠")
        self._show.setCheckable(True)
        self._show.triggered.connect(pet.toggle_visible)
        self._menu.addAction("设置…", open_settings)
        if open_debug:  # 发布版默认没有调试面板
            self._menu.addAction("打开调试面板", open_debug)
        self._menu.addSeparator()
        self._menu.addAction("退出", quit_app)
        self._menu.aboutToShow.connect(self.refresh)

        self._tray = QSystemTrayIcon(icon)
        self._tray.setContextMenu(self._menu)
        self._tray.setToolTip("Claude-Chan")
        self._tray.activated.connect(self._activated)
        self._tray.show()
        self.refresh()

    def _activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:  # 左键单击
            self._pet.toggle_visible()

    def refresh(self) -> None:
        self._show.setChecked(self._pet.isVisible())

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
