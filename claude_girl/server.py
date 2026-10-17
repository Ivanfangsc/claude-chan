"""只监听本机的 HTTP 服务，接收 Claude Code 的 http hook。

响应体会被 Claude Code 当作 hook 输出解析，所以永远立即返回 200 和 "{}"（无任何决策字段），
保证桌宠不会影响 PermissionRequest / PreToolUse 的结果。服务跑在后台线程里，
收到的事件通过 Qt 信号交给主线程处理。
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable

from PySide6.QtCore import QObject, Signal

MAX_BODY = 1024 * 1024


class HookServer(QObject):
    event_received = Signal(dict)
    message = Signal(str)

    def __init__(self, host: str, port: int, state_provider: Callable[[], Any]) -> None:
        super().__init__()
        self._host, self._port = host, port
        # 在后台线程里被调用：只读快照，不修改状态
        self._state_provider = state_provider
        self._httpd: ThreadingHTTPServer | None = None

    def start(self) -> None:
        server = self

        class Handler(BaseHTTPRequestHandler):
            def _reply(self, status: int, body: Any = None) -> None:
                data = json.dumps({} if body is None else body, ensure_ascii=False).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self) -> None:  # noqa: N802 - http.server 的方法名
                # 浏览器发来的请求都带 Origin；hook 不带。拒绝网页借用户浏览器伪造事件
                if self.headers.get("Origin"):
                    return self._reply(403, {"error": "forbidden"})
                if self.path == "/health":
                    return self._reply(200, {"ok": True})
                if self.path == "/state":
                    return self._reply(200, server._state_provider())
                self._reply(404, {"error": "not found"})

            def do_POST(self) -> None:  # noqa: N802
                if self.headers.get("Origin"):
                    return self._reply(403, {"error": "forbidden"})
                if self.path != "/event":
                    return self._reply(404, {"error": "not found"})
                length = int(self.headers.get("Content-Length") or 0)
                if length > MAX_BODY:
                    return self._reply(413, {"error": "too large"})
                raw = self.rfile.read(length)
                self._reply(200)
                try:
                    event = json.loads(raw.decode("utf-8"))
                except ValueError:
                    server.message.emit("收到无法解析的事件，已忽略")
                    return
                if not isinstance(event, dict) or not isinstance(event.get("hook_event_name"), str):
                    server.message.emit("事件缺少 hook_event_name，已忽略")
                    return
                server.event_received.emit(event)

            def log_message(self, *_args: Any) -> None:
                pass  # 不在控制台打印每个请求

        try:
            self._httpd = ThreadingHTTPServer((self._host, self._port), Handler)
        except OSError as e:
            self.message.emit(f"端口 {self._port} 无法监听，收不到 hook 事件：{e}")
            return
        self._httpd.daemon_threads = True
        threading.Thread(target=self._httpd.serve_forever, name="hook-server", daemon=True).start()
        self.message.emit(f"HTTP 服务已启动：http://{self._host}:{self._port}/event")

    def stop(self) -> None:
        if self._httpd:
            self._httpd.shutdown()
            self._httpd.server_close()
