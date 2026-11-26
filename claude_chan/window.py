"""桌宠窗口：透明、无边框、不在任务栏；拖动、Ctrl + 滚轮缩放、置顶、鼠标穿透、悬停变透明，并记住这些状态。

点击穿透：启动时把所有关键帧的不透明区域取并集，缩到粗网格并向外扩一格，作为窗口形状
（setMask）。形状以外的区域点击会落到下面的窗口；三个平台行为一致，也没有逐帧开销。
"""

from __future__ import annotations

import json
import sys
import math
import time
from pathlib import Path
from typing import Callable

from PIL import Image
from PySide6.QtCore import QPoint, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QImage, QLinearGradient, QPainter, QRegion
from PySide6.QtWidgets import QWidget

from . import follow
from .config import data_dir
from .engine.player import FramePlayer
from .profile import measure, note
from .model import DisplayTarget

ASPECT = 16 / 9
HALF_FADE = 0.14  # 半身时下沿渐隐的高度（占窗口高度）
MIN_WIDTH = 120
MIN_VISIBLE = 80  # 窗口至少要有这么多像素露在某个屏幕里，否则认为保存的位置已失效
GRID_W, GRID_H = 64, 114
# 悬停变透明：鼠标在她身上停这么久后变淡、点击落到下面的窗口；移开后恢复
HOVER_DWELL_MS = 600
HOVER_OPACITY = 0.25
HOVER_FADE_MS = 150
HOVER_POLL_MS = 50


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


def default_geometry(width_fraction: float, aspect: float = ASPECT) -> QRect:
    """默认宽度为主屏宽度的 width_fraction，按 aspect（高 / 宽）；太高时按工作区高度缩放。贴右下角。"""
    area = QGuiApplication.primaryScreen().availableGeometry()
    width = round(area.width() * width_fraction)
    height = round(width * aspect)
    if height > area.height():
        height = area.height()
        width = round(height / aspect)
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
        half_crop: float,
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
        self._half_crop = half_crop
        self._width_fraction = width_fraction
        self._on_state_change = on_state_change
        self._on_menu = on_menu
        self._on_open_debug = on_open_debug
        self._quitting = False
        self._target: DisplayTarget | None = None
        self._char_region = QRegion()
        self._state_file = data_dir() / "window-state.json"
        # half：半身，只画每帧上面 half_crop 那一截（头到膝上），窗口跟着变矮，同样大小下占地更少
        self.state = {"bounds": None, "alwaysOnTop": True, "clickThrough": False, "half": False, "hoverFade": False}
        self._load_state()
        # 跟随模式（见 follower.py）：贴哪一侧、离边多远（物理像素，None 用默认）、跟随时的宽度
        self.state["follow"] = {"enabled": False, "anchor": "right", "gapX": None, "gapY": None, "width": None,
                                **(self.state.get("follow") or {})}
        self.on_moved: Callable[[], None] | None = None
        self.on_flags_applied: Callable[[], None] | None = None
        self.on_follow_reset: Callable[[], None] | None = None

        # 悬停变透明：_faded 表示现在是否淡出且不接收鼠标；_opacity 是画的时候乘上的不透明度，向目标渐变
        self._faded = False
        self._opacity = 1.0
        self._dwell_timer = QTimer(self, singleShot=True, interval=HOVER_DWELL_MS)
        self._dwell_timer.timeout.connect(self._dwell_done)
        self._poll_timer = QTimer(self, interval=HOVER_POLL_MS)
        self._poll_timer.timeout.connect(self._poll_cursor)
        self._fade_timer = QTimer(self, interval=16)
        self._fade_timer.timeout.connect(self._step_fade)
        self.setMouseTracking(True)  # 不按键移动也收到 mouseMoveEvent（见 _arm_dwell）

        self.setWindowTitle("Claude-Chan")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.apply_flags()
        b = self.state["bounds"]
        rect = QRect(b["x"], b["y"], b["width"], b["height"]) if b else None
        self.setGeometry(rect if rect and visible_somewhere(rect) else default_geometry(width_fraction, self.aspect()))

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
        self._unfade(animate=False)  # 重建窗口会丢掉临时的穿透，先回到正常状态
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

    def set_hover_fade(self, on: bool) -> None:
        self.state["hoverFade"] = on
        if not on:
            self._dwell_timer.stop()
            self._unfade()
        self.persist(immediate=True)

    # ---------- 悬停变透明 ----------

    def _cursor_on_character(self) -> bool:
        local = self.mapFromGlobal(QCursor.pos())
        region = self._char_region if self._hit_test and self._hit_grid is not None else QRegion(self.rect())
        return region.contains(local)

    def _dwell_done(self) -> None:
        if (self.state.get("hoverFade") and not self.state["clickThrough"] and self.isVisible()
                and not QGuiApplication.mouseButtons() and self._cursor_on_character()):
            self._faded = True
            self._set_input_transparent(True)
            self._poll_timer.start()
            self._fade_timer.start()

    def _poll_cursor(self) -> None:
        """淡出期间窗口收不到鼠标事件，只能轮询光标位置：离开她的轮廓就恢复。"""
        if not self._cursor_on_character():
            self._unfade()

    def _unfade(self, animate: bool = True) -> None:
        self._poll_timer.stop()
        if self._faded:
            self._faded = False
            if not self.state["clickThrough"]:
                self._set_input_transparent(False)
        if animate:
            self._fade_timer.start()
        else:
            self._fade_timer.stop()
            self._opacity = 1.0
            self.update()

    def _set_input_transparent(self, on: bool) -> None:
        # 只改原生窗口的标志，不重建窗口（setWindowFlags 会重建、闪一下）
        handle = self.windowHandle()
        if handle is not None:
            handle.setFlag(Qt.WindowType.WindowTransparentForInput, on)
            self.update()  # Windows 的分层窗口要重绘一次，系统才按新标志判断点击落在哪

    def _step_fade(self) -> None:
        target = HOVER_OPACITY if self._faded else 1.0
        step = (1.0 - HOVER_OPACITY) * 16 / HOVER_FADE_MS
        self._opacity = min(target, self._opacity + step) if self._opacity < target else max(target, self._opacity - step)
        if self._opacity == target:
            self._fade_timer.stop()
        self.update()

    def _arm_dwell(self) -> None:
        if (self.state.get("hoverFade") and not self.state["clickThrough"] and not self._faded
                and not self._dwell_timer.isActive()):
            self._dwell_timer.start()

    # 不能只靠 enterEvent：淡出期间窗口收不到鼠标消息，Qt 以为鼠标一直在她身上，下次移上来就不再发 enter。
    # 所以鼠标在她身上移动（开了 mouseTracking）也会开始计时。
    def enterEvent(self, event) -> None:  # noqa: N802
        self._arm_dwell()
        super().enterEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if not event.buttons():
            self._arm_dwell()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._dwell_timer.stop()
        super().leaveEvent(event)

    def set_hit_test(self, on: bool) -> None:
        self._hit_test = on
        self._apply_mask()

    def set_skin(self, placeholder: QImage | None, hit_grid: list[list[bool]] | None, half_crop: float) -> None:
        """切换形象：换占位图、点击区域；半身时按新形象的裁剪线调整高度。"""
        if placeholder is not None:
            self._placeholder = placeholder
        self._hit_grid = hit_grid
        old = self.crop()
        self._half_crop = half_crop
        if self.crop() != old:
            self._fit_height()
        self._update_mask()

    # ---------- 半身 ----------

    def crop(self) -> float:
        """每帧从上往下画多少（1 = 全身）。"""
        return self._half_crop if self.state.get("half") else 1.0

    def aspect(self) -> float:
        """窗口的高 / 宽。"""
        return ASPECT * self.crop()

    def head_fraction(self) -> float:
        """她头顶在窗口里的高度比例（气泡摆在这上面）：全身时约 10%。"""
        return 0.1 / self.crop()

    def set_half(self, on: bool) -> None:
        if on == bool(self.state.get("half")):
            return
        self.state["half"] = on
        self._fit_height()
        self._update_mask()
        self.update()
        self.persist(immediate=True)
        self._on_state_change()

    def _fit_height(self) -> None:
        """宽度不变、底边不动，按当前比例改高度。"""
        g = self.geometry()
        height = round(g.width() * self.aspect())
        self.setGeometry(g.x(), g.y() + g.height() - height, g.width(), height)

    def reset_geometry(self) -> None:
        if self.following and self.on_follow_reset:
            self.on_follow_reset()
            self.persist(immediate=True)
            return
        self.setGeometry(default_geometry(self._width_fraction, self.aspect()))
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
        # 窗口宽度对应整帧宽度；高度对应整帧上面 crop 那一截（全身时就是整帧），按比例换算
        w, h = self.width(), self.height()
        rows = min(GRID_H, math.ceil(GRID_H * self.crop()))
        full_h = h / self.crop()
        for y, row in enumerate(self._hit_grid[:rows]):
            top, bottom = round(y * full_h / GRID_H), min(h, round((y + 1) * full_h / GRID_H))
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
        self._dwell_timer.stop()  # 在操作她，不要变透明
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
        """Ctrl + 滚轮缩放，保持比例，以底边中点为锚点（角色坐着，脚下不动）。"""
        if not event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            return
        if self._dwell_timer.isActive():
            self._dwell_timer.start()  # 正在缩放，重新计时
        g = self.geometry()
        area = (self.screen() or QGuiApplication.primaryScreen()).availableGeometry()
        max_width = int(min(area.width(), area.height() / self.aspect()))
        factor = 1.08 if event.angleDelta().y() > 0 else 1 / 1.08
        width = round(min(max_width, max(MIN_WIDTH, g.width() * factor)))
        height = round(width * self.aspect())
        cx, bottom = g.x() + g.width() / 2, g.y() + g.height()
        self.setGeometry(round(cx - width / 2), bottom - height, width, height)
        self.persist()

    def nativeEvent(self, event_type, message):  # noqa: N802
        # 置顶时也排在任务栏下面：重叠时任务栏盖住她，不是她盖住任务栏
        if (sys.platform == "win32" and event_type == b"windows_generic_MSG"
                and self.state["alwaysOnTop"] and not self.following):
            from ctypes import wintypes
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == 0x0046:  # WM_WINDOWPOSCHANGING
                follow.stay_below_taskbar(msg.lParam)
        return super().nativeEvent(event_type, message)

    def showEvent(self, event) -> None:  # noqa: N802
        self._player.set_paused(False)
        super().showEvent(event)

    def hideEvent(self, event) -> None:  # noqa: N802
        self._dwell_timer.stop()
        self._unfade(animate=False)
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
        crop = self.crop()
        current, fading, progress = self._player.frames()

        def draw(img: QImage) -> None:
            # 半身：只取每帧上面 crop 那一截
            p.drawImage(target, img, QRectF(0, 0, img.width(), img.height() * crop))

        p.save()
        p.setOpacity(self._opacity)
        if self._sway_degrees:
            # 两条周期不成整数比的正弦叠加：一直在摇，但摆幅和节奏每次都不太一样；绕整帧的底边转（半身时在窗口下方）
            t = time.monotonic() * 1000 / self._sway_period * 2 * math.pi
            angle = self._sway_degrees * (0.75 * math.sin(t) + 0.25 * math.sin(t / 1.618 + 1.3))
            pivot = self.height() / crop * 0.98
            p.translate(self.width() / 2, pivot)
            p.rotate(angle)
            p.translate(-self.width() / 2, -pivot)
        if current is None:
            if self._placeholder is not None:
                draw(self._placeholder)
        elif fading is not None:
            p.setOpacity(self._opacity * (1 - progress))
            draw(fading)
            p.setOpacity(self._opacity * progress)
            draw(current)
            p.setOpacity(self._opacity)
        else:
            draw(current)
        p.restore()
        if crop < 1:
            # 半身的下沿渐隐，不是一刀切
            top = self.height() * (1 - HALF_FADE)
            fade = QLinearGradient(0, top, 0, self.height())
            fade.setColorAt(0, QColor(0, 0, 0, 255))
            fade.setColorAt(1, QColor(0, 0, 0, 0))
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
            p.fillRect(QRectF(0, top, self.width(), self.height() - top), fade)
        p.end()
