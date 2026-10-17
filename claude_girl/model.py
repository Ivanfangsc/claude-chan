"""各模块共用的数据类型和计时器接口。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Protocol

StateName = Literal["idle", "waiting", "thinking", "reading", "writing", "confirmation", "complete", "error", "drowsy"]
SessionSource = Literal["wsl", "windows", "unknown"]


@dataclass(frozen=True)
class DisplayTarget:
    """主逻辑下发给动画引擎的“目标状态”。"""

    state: str
    # 每次目标被重新设置时递增；引擎用它确认一次性状态已经播完
    seq: int
    # 一次性状态播完后不自动离开（StopFailure、手动固定）
    sticky: bool = False
    # confirmation 气泡用：项目名和来源
    project: str | None = None
    source: str | None = None
    session_id: str | None = None
    manual: bool = False


@dataclass
class EventInfo:
    """调试面板里的一行随机事件。"""

    id: str
    group: str
    chance: float
    cooldown_ms: float
    remaining_ms: float  # 冷却还剩多久，0 表示随时可能触发
    disabled: bool


@dataclass
class EngineStatus:
    node: str
    current: str | None
    next: str | None
    target: DisplayTarget | None
    holding: bool
    at_target: bool
    rate: float


@dataclass
class SessionView:
    """调试面板里的一行会话。"""

    id: str
    cwd: str
    source: str
    project: str
    base: str
    latch: str | None
    effective: str
    last_event: str
    last_event_at: float
    background: int = 0  # 还在跑的后台任务数


class Scheduler(Protocol):
    """计时器接口：应用里用 Qt 定时器实现，测试里用可手动推进的假时钟。时间单位都是毫秒。"""

    def now(self) -> float: ...

    def call_later(self, ms: float, fn: Callable[[], None]) -> Any: ...

    def cancel(self, handle: Any) -> None: ...


@dataclass
class FakeScheduler:
    """测试用：advance() 推进时间并按顺序触发到期的回调。"""

    time: float = 0
    _timers: list[tuple[float, int, Callable[[], None]]] = field(default_factory=list)
    _next_id: int = 0

    def now(self) -> float:
        return self.time

    def call_later(self, ms: float, fn: Callable[[], None]) -> int:
        self._next_id += 1
        self._timers.append((self.time + ms, self._next_id, fn))
        return self._next_id

    def cancel(self, handle: Any) -> None:
        self._timers = [t for t in self._timers if t[1] != handle]

    def advance(self, ms: float) -> None:
        end = self.time + ms
        while True:
            due = sorted(t for t in self._timers if t[0] <= end)
            if not due:
                break
            at, tid, fn = due[0]
            self._timers = [t for t in self._timers if t[1] != tid]
            self.time = at
            fn()
        self.time = end
