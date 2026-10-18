"""桌宠窗口：透明、无边框、不在任务栏；拖动、Ctrl + 滚轮缩放、置顶、鼠标穿透，并记住这些状态。

点击穿透：启动时把所有关键帧的不透明区域取并集，缩到粗网格并向外扩一格，作为窗口形状
（setMask）。形状以外的区域点击会落到下面的窗口；三个平台行为一致，也没有逐帧开销。
"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Callable

from PIL import Image
from PySide6.QtCore import QPoint, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QGuiApplication, QImage, QPainter, QRegion
from PySide6.QtWidgets import QWidget

from .config import data_dir
from .engine.player import FramePlayer
from .profile import measure, note
from .model import DisplayTarget

ASPECT = 16 / 9
MIN_WIDTH = 120
MIN_VISIBLE = 80  # 窗口至少要有这么多像素露在某个屏幕里，否则认为保存的位置已失效
GRID_W, GRID_H = 64, 114


def build_hit_grid(keyframes: list[Path], log: Callable[[str], None]) -> list[list[bool]] | None:
    """所有关键帧不透明区域的并集（粗网格，向外扩一格，横向两格）。一张都读不到时返回 None（整窗可点）。"""
    solid = [[False] * GRID_W for _ in range(GRID_H)]
    ok = 0
    for path in keyframes:
        try:
            alpha = Image.open(path).convert("RGBA").getchannel("A").resize((GRID_W, GRID_H), Image.BILINEAR)
        except Exception as e:  # noqa: BLE001
            log(f"点击区域：读取 {path.name} 失败（{e}）")
            continue
        ok += 1
        px = alpha.load()
        for y in range(GRID_H):
            for x in range(GRID_W):
                if px[x, y] > 32:
                    solid[y][x] = True
    if not ok:
        log("点击区域：没有可用的关键帧，整个窗口都接收鼠标")
        return None
    grid = [[False] * GRID_W for _ in range(GRID_H)]
    for y in range(GRID_H):
        for x in range(GRID_W):
            if solid[y][x]:
                for dy in (-1, 0, 1):
                    for dx in (-2, -1, 0, 1, 2):  # 横向多扩一格，给左右摇晃留余量
                        if 0 <= x + dx < GRID_W and 0 <= y + dy < GRID_H:
                            grid[y + dy][x + dx] = True
    cells = sum(map(sum, grid))
    log(f"点击区域：{ok} 张关键帧，覆盖 {round(cells / (GRID_W * GRID_H) * 100)}% 的画面")
    return grid


def default_geometry(width_fraction: float) -> QRect:
    """默认宽度为主屏宽度的 width_fraction，按 9:16；太高时按工作区高度缩放。贴右下角。"""
    area = QGuiApplication.primaryScreen().availableGeometry()
    width = round(area.width() * width_fraction)
    height = round(width * ASPECT)
    if height > area.height():
        height = area.height()
        width = round(height / ASPECT)
    return QRect(area.right() - width + 1, area.bottom() - height + 1, width, height)


def visible_somewhere(r: QRect) -> bool:
    for screen in QGuiApplication.screens():
        inter = r.intersected(screen.availableGeometry())
        if inter.width() >= MIN_VISIBLE and inter.height() >= MIN_VISIBLE:
            return True
    return False


class PetWindow(QWidget):
    def __init__(
        self,
        player: FramePlayer,
        placeholder: QImage | None,
        hit_grid: list[list[bool]] | None,
        width_fraction: float,
        on_state_change: Callable[[], None],
        on_menu: Callable[[QPoint], None],
        on_open_debug: Callable[[], None],
    ) -> None:
        super().__init__()
        self._player = player
        self._placeholder = placeholder
        self._hit_grid = hit_grid
        self._hit_test = True
        self._width_fraction = width_fraction
        self._on_state_change = on_state_change
        self._on_menu = on_menu
        self._on_open_debug = on_open_debug
        self._quitting = False
        self._target: DisplayTarget | None = None
        self._char_region = QRegion()
        self._state_file = data_dir() / "window-state.json"
        self.state = {"bounds": None, "alwaysOnTop": True, "clickThrough": False}
        self._load_state()
        # 跟随模式（见 follower.py）：贴哪一侧、离边多远（物理像素，None 用默认）、跟随时的宽度
        self.state["follow"] = {"enabled": False, "anchor": "right", "gapX": None, "gapY": None, "width": None,
                                **(self.state.get("follow") or {})}
        self.on_moved: Callable[[], None] | None = None
        self.on_flags_applied: Callable[[], None] | None = None
        self.on_follow_reset: Callable[[], None] | None = None

        self.setWindowTitle("Claude-Chan")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.apply_flags()
        b = self.state["bounds"]
        rect = QRect(b["x"], b["y"], b["width"], b["height"]) if b else None
        self.setGeometry(rect if rect and visible_somewhere(rect) else default_geometry(width_fraction))

        self._save_timer = QTimer(self, singleShot=True, interval=500)
        self._save_timer.timeout.connect(self._save_state)
        self._sway_degrees, self._sway_period = 0.0, 5000.0
        player.frame_changed.connect(self.update)

    def set_sway(self, degrees: float, period_ms: float) -> None:
        self._sway_degrees, self._sway_period = degrees, max(500.0, period_ms)

    # ---------- 状态 ----------

    def _load_state(self) -> None:
        try:
            self.state.update(json.loads(self._state_file.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass

    @property
    def following(self) -> bool:
        return bool(self.state["follow"].get("enabled"))

    def remember_desktop_bounds(self) -> None:
        """进入跟随模式前记下桌面上的位置；跟随期间不再覆盖它。"""
        g = self.geometry()
        self.state["bounds"] = {"x": g.x(), "y": g.y(), "width": g.width(), "height": g.height()}

    def restore_desktop_bounds(self) -> None:
        b = self.state["bounds"]
        rect = QRect(b["x"], b["y"], b["width"], b["height"]) if b else None
        self.setGeometry(rect if rect and visible_somewhere(rect) else default_geometry(self._width_fraction))

    def _save_state(self) -> None:
        if not self.following:
            self.remember_desktop_bounds()
        try:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            self._state_file.write_text(json.dumps(self.state, indent=2), encoding="utf-8")
        except OSError:
            pass

    def persist(self, immediate: bool = False) -> None:
        if immediate:
            self._save_state()
        else:
            self._save_timer.start()
        self._on_state_change()

    def apply_flags(self) -> None:
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool | Qt.WindowType.NoDropShadowWindowHint
        if self.state["alwaysOnTop"] and not self.following:  # 跟随时的层级由宿主窗口决定
            flags |= Qt.WindowType.WindowStaysOnTopHint
        if self.state["clickThrough"]:
            flags |= Qt.WindowType.WindowTransparentForInput
        visible = self.isVisible()
        self.setWindowFlags(flags)
        if visible:
            self.show()
        if self.on_flags_applied:
            self.on_flags_applied()

    def set_always_on_top(self, on: bool) -> None:
        self.state["alwaysOnTop"] = on
        self.apply_flags()
        self.persist(immediate=True)

    def set_click_through(self, on: bool) -> None:
        """开启后窗口不接收任何鼠标事件（包括拖动），只能从托盘关闭。"""
        self.state["clickThrough"] = on
        self.apply_flags()
        self.persist(immediate=True)

    def set_hit_test(self, on: bool) -> None:
        self._hit_test = on
        self._apply_mask()

    def set_skin(self, placeholder: QImage | None, hit_grid: list[list[bool]] | None) -> None:
        """切换形象：换占位图和点击区域。"""
        if placeholder is not None:
            self._placeholder = placeholder
        self._hit_grid = hit_grid
        self._update_mask()

    def reset_geometry(self) -> None:
        if self.following and self.on_follow_reset:
            self.on_follow_reset()
            self.persist(immediate=True)
            return
        self.setGeometry(default_geometry(self._width_fraction))
        self.persist(immediate=True)

    def toggle_visible(self) -> None:
        self.setVisible(not self.isVisible())
        self.user_toggled = True  # 用户自己点的：全屏检测据此不再自动显示
        self._on_state_change()

    def set_target(self, t: DisplayTarget) -> None:
        self._target = t

    def prepare_quit(self) -> None:
        self._quitting = True
        self._save_state()

    # ---------- 点击区域 ----------

    def _update_mask(self) -> None:
        """窗口大小变化时重算角色轮廓的区域。"""
        self._char_region = self._character_region()
        self._apply_mask()

    def _apply_mask(self) -> None:
        """窗口形状 = 角色轮廓。setMask 既决定点击区域，也会裁掉形状以外的绘制（气泡是单独的窗口，见 bubble.py）。"""
        if not self._hit_test or self._hit_grid is None:
            self.clearMask()
            return
        self.setMask(QRegion(self._char_region))

    def _character_region(self) -> QRegion:
        region = QRegion()
        if self._hit_grid is None:
            return region
        # 画面按 contain 方式铺满窗口；窗口本身就是 9:16，所以直接按比例换算
        w, h = self.width(), self.height()
        for y, row in enumerate(self._hit_grid):
            top, bottom = y * h // GRID_H, (y + 1) * h // GRID_H
            x = 0
            while x < GRID_W:
                if not row[x]:
                    x += 1
                    continue
                start = x
                while x < GRID_W and row[x]:
                    x += 1
                left, right = start * w // GRID_W, x * w // GRID_W
                region = region.united(QRegion(left, top, right - left, bottom - top))
        return region

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt 的方法名
        self._update_mask()
        super().resizeEvent(event)
        if self.on_moved:
            self.on_moved()

    # ---------- 鼠标 ----------

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self.windowHandle():
            # 由系统原生处理拖动，跨不同 DPI 的屏幕也稳定
            self.windowHandle().startSystemMove()

    def moveEvent(self, event) -> None:  # noqa: N802
        self.persist()
        super().moveEvent(event)
        if self.on_moved:
            self.on_moved()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        self._on_open_debug()

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        self._on_menu(event.globalPos())

    def wheelEvent(self, event) -> None:  # noqa: N802
        """Ctrl + 滚轮缩放，保持 9:16，以底边中点为锚点（角色坐着，脚下不动）。"""
        if not event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            return
        g = self.geometry()
        area = (self.screen() or QGuiApplication.primaryScreen()).availableGeometry()
        max_width = int(min(area.width(), area.height() / ASPECT))
        factor = 1.08 if event.angleDelta().y() > 0 else 1 / 1.08
        width = round(min(max_width, max(MIN_WIDTH, g.width() * factor)))
        height = round(width * ASPECT)
        cx, bottom = g.x() + g.width() / 2, g.y() + g.height()
        self.setGeometry(round(cx - width / 2), bottom - height, width, height)
        self.persist()

    def showEvent(self, event) -> None:  # noqa: N802
        self._player.set_paused(False)
        super().showEvent(event)

    def hideEvent(self, event) -> None:  # noqa: N802
        self._player.set_paused(True)
        super().hideEvent(event)

    def closeEvent(self, event) -> None:  # noqa: N802
        # 关闭（Alt+F4）只是隐藏到托盘；真正退出走托盘菜单
        if self._quitting:
            event.accept()
            return
        event.ignore()
        self.hide()
        self._on_state_change()

    # ---------- 绘制 ----------

    def paintEvent(self, event) -> None:  # noqa: N802
        with measure("paint"):
            self._paint()
        note("窗口像素", self.width() * self.height() * self.devicePixelRatioF() ** 2 / 1e6)

    def _paint(self) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        p.fillRect(self.rect(), Qt.GlobalColor.transparent)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        target = QRectF(self.rect())
        current, fading, progress = self._player.frames()
        p.save()
        if self._sway_degrees:
            # 两条周期不成整数比的正弦叠加：一直在摇，但摆幅和节奏每次都不太一样
            t = time.monotonic() * 1000 / self._sway_period * 2 * math.pi
            angle = self._sway_degrees * (0.75 * math.sin(t) + 0.25 * math.sin(t / 1.618 + 1.3))
            p.translate(self.width() / 2, self.height() * 0.98)
            p.rotate(angle)
            p.translate(-self.width() / 2, -self.height() * 0.98)
        if current is None:
            if self._placeholder is not None:
                p.drawImage(target, self._placeholder)
        elif fading is not None:
            p.setOpacity(1 - progress)
            p.drawImage(target, fading)
            p.setOpacity(progress)
            p.drawImage(target, current)
            p.setOpacity(1)
        else:
            p.drawImage(target, current)
        p.restore()
        p.end()
