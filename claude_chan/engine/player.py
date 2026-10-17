"""逐帧播放器：用 Pillow 解码动画 AVIF，按 24fps 推进，窗口每次重绘时取当前帧。

切换片段只是换一个帧序列，所以天然无缝，不需要双缓冲和预加载等待：
- set_next 时就打开下一段并解出起始帧；当前段播完的下一个节拍直接换过去。
- 每段末帧 = 下一段首帧，所以下一段从第 2 帧开始（skipSharedFrame），节奏保持 1 帧 / 帧时长。
- 播完而下一段还没定时停在末帧，通知引擎（on_stall）；之后 set_next 立即开始。
- 交叉淡化：两段同时推进，绘制时按进度混合。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PIL import Image
from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QImage

from ..profile import measure
from .manifest import Clip


def clip_path(assets: Path, clip: Clip) -> Path:
    """clip.file 是素材目录下的相对路径；绝对路径（切换形象时的变身动画）原样使用。"""
    return assets / clip.file


def to_qimage(im: Image.Image) -> QImage:
    """转成预乘透明度的 QImage：Qt 绘制时走最快的路径（平滑缩放到窗口大小约 0.2 ms）。

    实测每帧：AVIF 解码约 6 ms，转换约 3 ms。缩放交给 Qt 绘制时做，比先用 Pillow 缩放快得多（约 8 ms）。
    """
    rgba = im.convert("RGBa")  # Pillow 的 RGBa 就是预乘透明度
    data = rgba.tobytes()
    q = QImage(data, rgba.width, rgba.height, rgba.width * 4, QImage.Format.Format_RGBA8888_Premultiplied)
    # QImage 不持有 data 的所有权：把字节挂在 QImage 上保持存活，省掉一次 4 MB 的复制
    q._data = data  # type: ignore[attr-defined]
    return q


@dataclass
class _Track:
    """一段正在播放（或准备好）的片段。"""

    clip: Clip
    image: Image.Image
    index: int
    frame: QImage

    @property
    def count(self) -> int:
        return getattr(self.image, "n_frames", 1)

    def at_end(self) -> bool:
        return self.index >= self.count - 1

    def step(self) -> None:
        self.index += 1
        self.image.seek(self.index)
        self.frame = to_qimage(self.image)


class FramePlayer(QObject):
    """实现引擎的 PlayerLike 接口。frame_changed 通知窗口重绘。"""

    frame_changed = Signal()

    def __init__(self, assets: Path, fps: float, cfg: dict, log: Callable[[str], None]) -> None:
        super().__init__()
        self.on_clip_start: Callable[[Clip], None] = lambda _c: None
        self.on_stall: Callable[[], None] = lambda: None
        self._assets = assets
        self._fps = fps
        self._cfg = cfg
        self._log = log
        self._rate = 1.0
        self._current: _Track | None = None
        self._next: _Track | None = None
        self._stalled = True
        # 交叉淡化：旧的一段继续推进，直到淡出结束
        self._fading: _Track | None = None
        self._fade_start = 0.0
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.timeout.connect(self._tick)
        self._last_tick = 0.0
        self._last_hitch_log = 0.0
        self._paused = False

    # ---------- 引擎接口 ----------

    def set_next(self, clip: Clip | None) -> None:
        if clip is None:
            self._next = None
            return
        start = 1 if self._cfg["skipSharedFrame"] and self._current else 0
        self._next = self._open(clip, start)
        if self._stalled and self._next:
            self._switch()

    def crossfade_to(self, clip: Clip) -> None:
        track = self._open(clip, 0)
        if track is None:
            return
        self._fading = self._current
        self._fade_start = time.monotonic()
        self._next = None
        self._current = track
        self._stalled = False
        self._ensure_running()
        self.frame_changed.emit()
        self.on_clip_start(clip)

    def set_rate(self, rate: float) -> None:
        self._rate = rate
        if self._timer.isActive():
            self._timer.setInterval(self._interval())

    def set_config(self, cfg: dict) -> None:
        self._cfg = cfg

    def set_paused(self, paused: bool) -> None:
        """窗口隐藏时暂停：不解码、不推进，省 CPU。恢复后从暂停的那一帧接着播。"""
        if paused == self._paused:
            return
        self._paused = paused
        if paused:
            self._timer.stop()
        elif self._current and (not self._stalled or self._next or self._fading):
            self._ensure_running()

    @property
    def has_next(self) -> bool:
        return self._next is not None

    def set_assets(self, assets: Path) -> None:
        """切换形象：之后打开的片段从新的素材目录读取（正在播放和已经准备好的不受影响）。"""
        self._assets = assets

    # ---------- 窗口取帧 ----------

    def frames(self) -> tuple[QImage | None, QImage | None, float]:
        """(当前帧, 正在淡出的旧帧, 淡入进度 0–1)。"""
        cur = self._current.frame if self._current else None
        if not self._fading:
            return cur, None, 1.0
        progress = min(1.0, (time.monotonic() - self._fade_start) * 1000 / max(1, self._cfg["crossfadeMs"]))
        return cur, self._fading.frame, progress

    # ---------- 内部 ----------

    def _open(self, clip: Clip, start: int) -> _Track | None:
        path = clip_path(self._assets, clip)
        try:
            image = Image.open(path)
            start = min(start, getattr(image, "n_frames", 1) - 1)
            image.seek(start)
            return _Track(clip, image, start, to_qimage(image))
        except Exception as e:  # noqa: BLE001 - 素材出错时记日志并停在当前帧
            self._log(f"打开片段 {clip.id} 失败（{path.name}）：{e}")
            return None

    def _interval(self) -> int:
        return max(1, round(1000 / (self._fps * self._rate)))

    def _ensure_running(self) -> None:
        if not self._timer.isActive() and not self._paused:
            self._last_tick = time.monotonic()
            self._timer.start(self._interval())

    def _switch(self) -> None:
        track, self._next = self._next, None
        if track is None:
            return
        self._current = track
        self._stalled = False
        self._ensure_running()
        self.frame_changed.emit()
        self.on_clip_start(track.clip)

    def _tick(self) -> None:
        with measure("tick"):
            self._tick_inner()

    def _tick_inner(self) -> None:
        now = time.monotonic()
        gap = (now - self._last_tick) * 1000
        if gap > 2.5 * self._interval() and now - self._last_hitch_log > 1:
            self._last_hitch_log = now
            self._log(f"卡顿：两帧间隔 {gap:.0f}ms（{self._current.clip.id if self._current else '-'}）")
        self._last_tick = now

        if self._fading:
            if not self._fading.at_end():
                self._fading.step()
            if (now - self._fade_start) * 1000 >= self._cfg["crossfadeMs"]:
                self._fading = None

        cur = self._current
        if cur is None:
            return
        if not cur.at_end():
            cur.step()
            self.frame_changed.emit()
        elif self._next:
            self._switch()
        elif not self._stalled:
            # 播完了但下一段还没定：停在末帧
            self._stalled = True
            self.on_stall()
            if self._stalled and not self._fading:
                self._timer.stop()
