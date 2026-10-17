"""目标状态的唯一出口：自动目标（来自会话汇总）+ 调试面板的手动覆盖。"""

from __future__ import annotations

from typing import Callable

from ..model import DisplayTarget


class TargetHub:
    def __init__(
        self,
        next_seq: Callable[[], int],
        emit: Callable[[DisplayTarget], None],
        # 自动目标的 error 播完时调用（接到会话汇总上）
        on_auto_ack: Callable[[int], None] = lambda _seq: None,
    ) -> None:
        self._next_seq = next_seq
        self._emit = emit
        self._on_auto_ack = on_auto_ack
        self._auto = DisplayTarget("idle", next_seq())
        self._manual: DisplayTarget | None = None
        self._last: DisplayTarget | None = None

    def current(self) -> DisplayTarget:
        return self._manual or self._auto

    def is_manual(self) -> bool:
        return self._manual is not None

    def set_auto(self, t: DisplayTarget) -> None:
        self._auto = t
        self._publish()

    def force(self, state: str, sticky: bool = False) -> None:
        self._manual = DisplayTarget(state, self._next_seq(), sticky=sticky, manual=True, project="debug")
        self._publish()

    def clear_manual(self) -> None:
        self._manual = None
        self._publish()

    def ack(self, seq: int) -> None:
        if self._manual and self._manual.seq == seq:
            if not self._manual.sticky:
                self.clear_manual()
            return
        self._on_auto_ack(seq)

    def _publish(self) -> None:
        t = self.current()
        if self._last and self._last.seq == t.seq:
            return
        self._last = t
        self._emit(t)
