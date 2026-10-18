"""设置窗口：形象、窗口、动画、启动与更新。改了立即生效，不需要“确定”。

窗口只负责界面，具体怎么改由 PetApp 通过 SettingsBackend 提供（取值和设置函数成对出现）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

Toggle = tuple[Callable[[], bool], Callable[[bool], None]]


@dataclass
class SettingsBackend:
    version: str
    skins: list[tuple[str, str]]  # (名字, 显示名)
    skin: tuple[Callable[[], str], Callable[[str], None]]
    always_on_top: Toggle
    click_through: Toggle
    follow: Toggle | None  # 只有 Windows 有
    hide_in_fullscreen: Toggle
    switch_style: tuple[Callable[[], str], Callable[[str], None]]
    fidgets: Toggle
    autostart: Toggle
    check_updates: Toggle
    reset_geometry: Callable[[], None]
    open_data_folder: Callable[[], None]
    reload_config: Callable[[], None]


def _hint(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setStyleSheet("color: palette(placeholder-text); margin-left: 22px;")
    return label


class SettingsDialog(QDialog):
    def __init__(self, backend: SettingsBackend, icon: QIcon | None = None) -> None:
        super().__init__()
        self._b = backend
        self.setWindowTitle("Claude-Chan 设置")
        if icon:
            self.setWindowIcon(icon)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        self.setMinimumWidth(380)
        root = QVBoxLayout(self)

        # ---------- 形象 ----------
        box = QGroupBox("形象")
        lay = QHBoxLayout(box)
        self._skin_group = QButtonGroup(self)
        self._skin_buttons: dict[str, QRadioButton] = {}
        for name, label in backend.skins:
            b = QRadioButton(label)
            self._skin_group.addButton(b)
            self._skin_buttons[name] = b
            b.toggled.connect(lambda on, n=name: on and self._b.skin[1](n))
            lay.addWidget(b)
        lay.addStretch()
        root.addWidget(box)

        # ---------- 窗口 ----------
        box = QGroupBox("窗口")
        lay = QVBoxLayout(box)
        self._top = self._check(lay, "置顶", backend.always_on_top)
        self._through = self._check(lay, "鼠标穿透", backend.click_through)
        lay.addWidget(_hint("开启后点不到她，也拖不动；要关掉请从托盘图标的菜单打开设置。"))
        self._follow = None
        if backend.follow:
            self._follow = self._check(lay, "跟随 Claude 窗口", backend.follow)
            lay.addWidget(_hint("贴在 Claude 桌面版窗口的右下角，跟着窗口走；没开 Claude 时回到桌面原来的位置。"))
        self._fullscreen = self._check(lay, "有全屏窗口时自动隐藏", backend.hide_in_fullscreen)
        reset = QPushButton("重置位置和大小")
        reset.clicked.connect(backend.reset_geometry)
        lay.addWidget(reset, alignment=Qt.AlignmentFlag.AlignLeft)
        root.addWidget(box)

        # ---------- 动画 ----------
        box = QGroupBox("动画")
        lay = QVBoxLayout(box)
        lay.addWidget(QLabel("切换方式"))
        self._style_group = QButtonGroup(self)
        self._style_buttons: dict[str, QRadioButton] = {}
        for style, label, hint in (
            ("smooth", "流畅优先", "正在做的小动作和这一轮动作做完再切换；只有“等你确认”和“出错”会立刻切过去。"),
            ("responsive", "响应优先", "状态一变就立刻切换，最快，但偶尔会看到动作做到一半被打断。"),
        ):
            b = QRadioButton(label)
            self._style_group.addButton(b)
            self._style_buttons[style] = b
            b.toggled.connect(lambda on, s=style: on and self._b.switch_style[1](s))
            lay.addWidget(b)
            lay.addWidget(_hint(hint))
        self._fidgets = self._check(lay, "随机小动作（喝茶、扶发饰、看怀表……）", backend.fidgets)
        lay.addWidget(_hint("关掉后只保留眨眼。"))
        root.addWidget(box)

        # ---------- 启动与更新 ----------
        box = QGroupBox("启动与更新")
        lay = QVBoxLayout(box)
        self._autostart = self._check(lay, "开机自启", backend.autostart)
        self._updates = self._check(lay, "自动检查新版本", backend.check_updates)
        lay.addWidget(_hint("启动后和之后每天向 GitHub 查一次最新版本号，不上传任何信息。"))
        root.addWidget(box)

        # ---------- 底部 ----------
        row = QHBoxLayout()
        folder = QPushButton("打开数据文件夹")
        folder.setToolTip("设置、窗口位置和日志（log.txt）都在这里；高级设置写在 config.json")
        folder.clicked.connect(backend.open_data_folder)
        row.addWidget(folder)
        reload = QPushButton("重新加载 config.json")
        reload.clicked.connect(backend.reload_config)
        row.addWidget(reload)
        row.addStretch()
        row.addWidget(QLabel(f"v{backend.version}"))
        close = QPushButton("关闭")
        close.clicked.connect(self.close)
        row.addWidget(close)
        root.addLayout(row)
        self.refresh()

    def _check(self, lay: QVBoxLayout, text: str, toggle: Toggle) -> QCheckBox:
        c = QCheckBox(text)
        c.toggled.connect(toggle[1])
        lay.addWidget(c)
        return c

    def refresh(self) -> None:
        """按当前状态更新勾选（不触发设置）。"""
        b = self._b
        pairs: list[tuple[QWidget, bool]] = [
            (self._top, b.always_on_top[0]()),
            (self._through, b.click_through[0]()),
            (self._fullscreen, b.hide_in_fullscreen[0]()),
            (self._fidgets, b.fidgets[0]()),
            (self._autostart, b.autostart[0]()),
            (self._updates, b.check_updates[0]()),
        ]
        if self._follow and b.follow:
            pairs.append((self._follow, b.follow[0]()))
        following = bool(self._follow and b.follow and b.follow[0]())
        for skin, button in self._skin_buttons.items():
            pairs.append((button, skin == b.skin[0]()))
        for style, button in self._style_buttons.items():
            pairs.append((button, style == b.switch_style[0]()))
        for widget, value in pairs:
            widget.blockSignals(True)
            widget.setChecked(value)  # type: ignore[attr-defined]
            widget.blockSignals(False)
        self._top.setEnabled(not following)  # 跟随时层级由 Claude 窗口决定

    def present(self) -> None:
        self.refresh()
        self.show()
        self.raise_()
        self.activateWindow()
