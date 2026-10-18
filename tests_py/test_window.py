"""桌宠窗口的形状：点击区域和 confirmation 气泡（离屏模式，不弹出真实窗口）。"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from claude_chan.model import DisplayTarget
from claude_chan.window import GRID_H, GRID_W, PetWindow


class StubPlayer(QObject):
    frame_changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.paused: list[bool] = []

    def frames(self):
        return None, None, 1.0

    def set_paused(self, paused: bool) -> None:
        self.paused.append(paused)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(app, tmp_path, monkeypatch):
    monkeypatch.setattr("claude_chan.window.data_dir", lambda: tmp_path)
    # 只有下半部分是“角色”，头顶那块是透明区域
    grid = [[y > GRID_H // 2 for _ in range(GRID_W)] for y in range(GRID_H)]
    w = PetWindow(StubPlayer(), None, grid, 0.25, lambda: None, lambda _p: None, lambda: None)
    w.resize(450, 800)
    w.show()  # 窗口显示时才会触发 resizeEvent、算出窗口形状（离屏模式，不会真的弹出）
    QApplication.processEvents()
    yield w
    w.prepare_quit()
    w.close()


def test_mask_follows_character(window) -> None:
    mask = window.mask()
    assert mask.contains(window.rect().center() + window.rect().center() * 0.5)  # 下半部分
    assert not mask.contains(window.rect().topLeft() + window.rect().center() * 0.2)  # 头顶透明区域


def test_player_pauses_while_hidden(window) -> None:
    window._player.paused.clear()
    window.hide()
    window.show()
    assert window._player.paused == [True, False]  # 隐藏时暂停，显示时恢复


def test_fullscreen_covers() -> None:
    from claude_chan.fullscreen import covers

    monitor = (0, 0, 1920, 1080)
    assert covers((0, 0, 1920, 1080), monitor)  # 全屏
    assert covers((-8, -8, 1928, 1088), monitor)  # 带隐藏边框的全屏
    assert not covers((0, 0, 1920, 1040), monitor)  # 最大化：没有盖住任务栏
