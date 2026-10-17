"""日志文件：程序文件夹下的 data\\log.txt。打包后的程序没有控制台，出了问题只能看这里。

- 超过 1 MB 时把旧的改名为 log.1.txt（只留一份），不会无限增长；
- 未捕获的异常（主线程和其他线程）连同调用栈写进去，程序突然退出时能查到原因。
"""

from __future__ import annotations

import sys
import threading
import time
import traceback
from pathlib import Path

MAX_BYTES = 1_000_000

_path: Path | None = None


def setup(path: Path) -> None:
    global _path
    _path = path
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size > MAX_BYTES:
            path.replace(path.with_name(path.stem + ".1" + path.suffix))
    except OSError:
        pass

    def on_exception(exc_type, exc, tb) -> None:  # noqa: ANN001
        write("未捕获的异常：\n" + "".join(traceback.format_exception(exc_type, exc, tb)).rstrip())
        sys.__excepthook__(exc_type, exc, tb)

    def on_thread_exception(args: threading.ExceptHookArgs) -> None:
        name = args.thread.name if args.thread else "?"
        write(f"线程 {name} 未捕获的异常：\n"
              + "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)).rstrip())

    sys.excepthook = on_exception
    threading.excepthook = on_thread_exception


def write(msg: str) -> None:
    """追加一行（带日期时间）。写不进去时静默忽略，不能因为日志影响桌宠。"""
    if _path is None:
        return
    try:
        with _path.open("a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
    except OSError:
        pass
