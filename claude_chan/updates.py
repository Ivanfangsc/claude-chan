"""检查更新：读 GitHub Releases 的最新版本，比当前新就通知托盘。

启动 10 秒后查一次，之后每天一次。只发一个 GET 请求，不上传任何信息；配置里 updates.check 设为 false 可以关掉。
仓库是私有的、没网、被限流时都静默失败，只记日志。
"""

from __future__ import annotations

import json
import re
from typing import Callable

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

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

    def __init__(self, repo: str, current: str, log: Callable[[str], None]) -> None:
        super().__init__()
        self._repo = repo
        self._current = current
        self._log = log
        self._net = QNetworkAccessManager(self)
        self._timer = QTimer(self, interval=DAY_MS)
        self._timer.timeout.connect(self.check)
        self.latest: tuple[str, str] | None = None

    def start(self) -> None:
        QTimer.singleShot(10_000, self.check)
        self._timer.start()

    def check(self) -> None:
        req = QNetworkRequest(QUrl(f"https://api.github.com/repos/{self._repo}/releases/latest"))
        req.setRawHeader(b"Accept", b"application/vnd.github+json")
        req.setRawHeader(b"User-Agent", f"claude-chan/{self._current}".encode())
        req.setTransferTimeout(15_000)
        reply = self._net.get(req)
        reply.finished.connect(lambda: self._done(reply))

    def _done(self, reply: QNetworkReply) -> None:
        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                self._log(f"检查更新失败：{reply.errorString()}")
                return
            data = json.loads(bytes(reply.readAll()).decode("utf-8"))
            tag, url = data.get("tag_name", ""), data.get("html_url", "")
            if is_newer(tag, self._current):
                if self.latest is None or self.latest[0] != tag:
                    self._log(f"有新版本：{tag}（当前 v{self._current}）")
                self.latest = (tag, url)
                self.available.emit(tag, url)
        except (ValueError, AttributeError) as e:
            self._log(f"检查更新失败：{e}")
        finally:
            reply.deleteLater()
