"""轻量性能统计：设置环境变量 CLAUDE_GIRL_PROFILE=1 时，每 10 秒在日志里写一行各步骤的平均耗时。"""

from __future__ import annotations

import os
import time
from collections import defaultdict
from contextlib import contextmanager
from typing import Callable, Iterator

ENABLED = os.environ.get("CLAUDE_GIRL_PROFILE") == "1"
_totals: dict[str, float] = defaultdict(float)
_counts: dict[str, int] = defaultdict(int)
_last_report = time.monotonic()
_log: Callable[[str], None] = print


def set_logger(log: Callable[[str], None]) -> None:
    global _log
    _log = log


@contextmanager
def measure(name: str) -> Iterator[None]:
    if not ENABLED:
        yield
        return
    start = time.perf_counter()
    try:
        yield
    finally:
        _totals[name] += (time.perf_counter() - start) * 1000
        _counts[name] += 1
        _maybe_report()


def note(name: str, value: float) -> None:
    if ENABLED:
        _totals[name] += value
        _counts[name] += 1


def _maybe_report() -> None:
    global _last_report
    now = time.monotonic()
    if now - _last_report < 10:
        return
    span = now - _last_report
    parts = [f"{k} {(_totals[k] / _counts[k]):.1f}ms×{_counts[k] / span:.0f}/s" for k in sorted(_totals)]
    _log("性能：" + "，".join(parts))
    _totals.clear()
    _counts.clear()
    _last_report = now
