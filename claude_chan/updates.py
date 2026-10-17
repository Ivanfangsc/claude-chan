"""检查更新：读 GitHub Releases 的最新版本，比当前新就通知托盘。

启动 10 秒后查一次，之后每天一次。只发一个 GET 请求，不上传任何信息；配置里 updates.check 设为 false 可以关掉。
仓库是私有的、没网、被限流时都静默失败，只记日志。

请求用 Python 自己的 urllib 在后台线程里发，不用 Qt 的 QNetworkAccessManager：HTTP 服务（http.server → http.client）
已经加载了 Python 自带的 OpenSSL，Qt 联网时又会加载它自己的同名 OpenSSL，两套混在一个进程里会把内存弄坏，
表现为过一会儿在解码动画时崩溃（实测稳定复现）。
"""

from __future__ import annotations

import json
import re
import threading
import urllib.request
from typing import Callable

from PySide6.QtCore import QObject, QTimer, Signal

DAY_MS = 24 * 60 * 60 * 1000


def parse_version(text: str) -> tuple[int, ...] | None:
    """'v1.2.3' / '1.2' → (1, 2, 3) / (1, 2)；认不出来返回 None。"""
    m = re.fullmatch(r"\s*v?(\d+(?:\.\d+)*)\s*", text or "")
    return tuple(int(x) for x in m.group(1).split(".")) if m else None


def is_newer(latest: str, current: str) -> bool:
    a, b = parse_version(latest), parse_version(current)
    if a is None or b is None:
        return False
    n = max(len(a), len(b))
    return a + (0,) * (n - len(a)) > b + (0,) * (n - len(b))


class UpdateChecker(QObject):
    available = Signal(str, str)  # 新版本号，下载页地址
    _finished = Signal(object)  # 后台线程的结果：(成功, 数据或错误信息)，由 Qt 排队交回主线程

    def __init__(self, repo: str, current: str, log: Callable[[str], None]) -> None:
        super().__init__()
        self._repo = repo
        self._current = current
        self._log = log
        self._busy = False
        self._timer = QTimer(self, interval=DAY_MS)
        self._timer.timeout.connect(self.check)
        self._finished.connect(self._done)
        self.latest: tuple[str, str] | None = None

    def start(self) -> None:
        QTimer.singleShot(10_000, self.check)
        self._timer.start()

    def check(self) -> None:
        if self._busy:
            return
        self._busy = True
        threading.Thread(target=self._fetch, name="update-check", daemon=True).start()

    def _fetch(self) -> None:
        req = urllib.request.Request(
            f"https://api.github.com/repos/{self._repo}/releases/latest",
            headers={"Accept": "application/vnd.github+json", "User-Agent": f"claude-chan/{self._current}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                self._finished.emit((True, json.loads(resp.read().decode("utf-8"))))
        except Exception as e:  # noqa: BLE001 - 没网、404、限流、超时都只记日志
            self._finished.emit((False, str(e)))

    def _done(self, result: tuple[bool, object]) -> None:
        self._busy = False
        ok, data = result
        if not ok or not isinstance(data, dict):
            self._log(f"检查更新失败：{data}")
            return
        tag, url = data.get("tag_name", ""), data.get("html_url", "")
        if is_newer(tag, self._current):
            if self.latest is None or self.latest[0] != tag:
                self._log(f"有新版本：{tag}（当前 v{self._current}）")
            self.latest = (tag, url)
            self.available.emit(tag, url)
