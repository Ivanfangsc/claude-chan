"""动画引擎：维护“显示状态”，按片段节奏追赶目标状态。

规则：
- intro / outro / transition 一旦开始必须播完；每段开始时按最新目标规划“下一段”，
  目标变化时只替换“下一段”，当前段不受影响。
- loop 和随机事件播完当前这一段再退出；目标在 highPriority 里、当前 loop 属于 interruptibleLoops，
  或 switchStyle 是 "responsive"（响应优先）时，立即交叉淡化到下一段。同一状态有多段 loop 变体时，每轮独立随机挑一段。
- 随机事件：停在某个状态时，每播完一轮 loop，按每个事件自己的概率（chance，默认 eventChance）决定要不要
  改播它；冷却（cooldownMs，默认 eventCooldownMs）按组计算，眨眼和其他动作互不影响。事件之后至少播一轮
  loop，也不连续重复同一个事件。事件和 loop 一样首尾是 K0。
- 每一轮 loop 的播放速度在 1 ± loopRateJitter 之间随机。
- 到达一次性状态后停留 oneshotHoldMs，然后确认（ack），再离开。
  目标仍是该状态（sticky）时就一直停在关键帧上。
"""

from __future__ import annotations

import random as _random
from typing import Any, Callable, Protocol

from ..model import DisplayTarget, EngineStatus, EventInfo, Scheduler
from .graph import Graph
from .manifest import Clip

REST = ("loop", "event")  # 停留在状态上时播放的片段类型，彼此切换不算离开状态


class PlayerLike(Protocol):
    # 播放器在片段开始和停住时回调引擎（由引擎在构造时设置）
    on_clip_start: Callable[[Clip], None]
    on_stall: Callable[[], None]

    def set_next(self, clip: Clip | None) -> None:
        """当前段播完后接着播的片段；播放器已停住时，准备好后立即开始。None 表示播完就停在末帧。"""

    def crossfade_to(self, clip: Clip) -> None:
        """立即交叉淡化到该片段。"""

    def set_rate(self, rate: float) -> None: ...


class Engine:
    def __init__(
        self,
        graph: Graph,
        player: PlayerLike,
        cfg: dict[str, Any],  # config["animation"]
        on_ack: Callable[[int], None],
        on_status: Callable[[EngineStatus], None],
        initial: DisplayTarget,
        clock: Scheduler,
        start_state: str = "idle",
        random: Callable[[], float] = _random.random,
    ) -> None:
        self._graph = graph
        self._player = player
        self._cfg = cfg
        self._on_ack = on_ack
        self._on_status = on_status
        self._clock = clock
        self._random = random
        self._node = graph.node_of_state(start_state)
        self._current: Clip | None = None
        self._next: Clip | None = None
        self._target = initial
        self._holding = False
        self._hold_done = True
        self._hold_seq: int | None = None
        self._hold_timer: Any = None
        self._crossfading = False
        self._acked_seq = -1
        self._rate = 1.0
        self._last_group_at: dict[str, float] = {}
        self._requested: Clip | None = None  # 调试面板手动指定的下一段事件
        # 冷却从启动和每次换状态时开始算：刚进入一个状态时先安静一会儿，不马上来大动作
        self._state_since = clock.now()
        self._last_event_id: str | None = None
        self._jitter = 1.0
        player.on_clip_start = self._handle_clip_start
        player.on_stall = self._handle_stall

    def start(self) -> None:
        self._replan()

    def set_target(self, t: DisplayTarget) -> None:
        if self._requested and self._requested.state != t.state:
            self._requested = None
        self._target = t
        self._replan()

    def set_config(self, cfg: dict[str, Any]) -> None:
        self._cfg = cfg
        self._replan()

    def status(self) -> EngineStatus:
        return EngineStatus(
            node=self._node,
            current=self._current.id if self._current else None,
            next=self._next.id if self._next else None,
            target=self._target,
            holding=self._holding,
            at_target=self._at_target(),
            rate=self._rate,
        )

    def events(self) -> list[EventInfo]:
        """当前目标状态的随机事件和各自的冷却（调试面板用）。"""
        state = self._target.state
        now = self._clock.now()
        disabled = self._cfg.get("disabledEventGroups", [])
        out = []
        for c in self._graph.rest_events(self._graph.node_of_state(state), state):
            group = c.group or "fidget"
            cooldown = self._cooldown(c)
            since = max(self._state_since, self._last_group_at.get(group, float("-inf")))
            out.append(EventInfo(c.id, group, self._chance(c), cooldown, max(0.0, cooldown - (now - since)), group in disabled))
        return out

    def request_event(self, clip_id: str) -> bool:
        """下一轮改播指定的事件（忽略概率和冷却）。事件不属于当前目标状态时返回 False。"""
        state = self._target.state
        clip = next((c for c in self._graph.rest_events(self._graph.node_of_state(state), state) if c.id == clip_id), None)
        if clip is None:
            return False
        self._requested = clip
        self._next = None  # 丢掉已经排好的这一轮，重新规划
        self._replan()
        return True

    def dispose(self) -> None:
        if self._hold_timer is not None:
            self._clock.cancel(self._hold_timer)

    # ---------- 播放器回调 ----------

    def _handle_clip_start(self, clip: Clip) -> None:
        self._current = clip
        self._node = self._graph.end_node(clip)
        if clip.type not in ("loop", "event"):
            self._state_since = self._clock.now()
        self._next = None
        if self._requested is clip:
            self._requested = None
        if clip.type == "event":
            self._last_group_at[clip.group or "fidget"] = self._clock.now()
            self._last_event_id = clip.id
        jitter = self._cfg.get("loopRateJitter", 0)
        self._jitter = 1 + jitter * (2 * self._random() - 1) if clip.type == "loop" and jitter else 1.0
        self._crossfading = False
        self._hold_done = not self._graph.is_oneshot(self._node)
        self._replan()

    def _handle_stall(self) -> None:
        self._current = None
        self._next = None
        if self._graph.is_oneshot(self._node) and not self._hold_done:
            self._holding = True
            here = self._graph.node_of_state(self._target.state) == self._node
            self._hold_seq = self._target.seq if here else None

            def hold_done() -> None:
                self._hold_timer = None
                self._holding = False
                self._hold_done = True
                if self._hold_seq is not None:
                    self._ack(self._hold_seq)
                self._replan()

            self._hold_timer = self._clock.call_later(self._cfg["oneshotHoldMs"], hold_done)
            self._emit()
            return
        self._replan()

    # ---------- 规划 ----------

    def _ack(self, seq: int) -> None:
        if seq == self._acked_seq:
            return
        self._acked_seq = seq
        self._on_ack(seq)

    def _plan(self, node: str) -> Clip | None:
        """从 node 出发朝目标走的下一段；None 表示停在原地（一次性状态停留）。"""
        if self._graph.is_oneshot(node) and not self._hold_done:
            return None
        tnode = self._graph.node_of_state(self._target.state)
        if node == tnode:
            # 这一轮已经挑好的 loop 变体或事件就不再换，避免每次重新规划都换一段
            if self._requested and self._requested.state == self._target.state:
                return self._requested
            if self._next and self._next.type in REST and self._next.state == self._target.state:
                return self._next
            event = self._pick_event(node)
            if event:
                return event
            return self._graph.rest_loop(node, self._target.state, self._random)
        path = self._graph.path(node, tnode)
        return path[0] if path else None

    def _pick_event(self, node: str) -> Clip | None:
        """这一轮要不要插入随机事件：按随机顺序逐个检查冷却，再按各自的概率抽签。事件之间至少隔一轮 loop。"""
        events = self._graph.rest_events(node, self._target.state)
        if not events or (self._current and self._current.type == "event"):
            return None
        # 上一次播的事件排到最后检查：其他事件优先，但它自己（比如眨眼）不会因此被排除
        pool = [c for c in events if c.id != self._last_event_id]
        start = int(self._random() * len(pool)) if pool else 0
        order = pool[start:] + pool[:start] + [c for c in events if c.id == self._last_event_id]
        now = self._clock.now()
        disabled = self._cfg.get("disabledEventGroups", [])
        for c in order:
            group = c.group or "fidget"
            if group in disabled:
                continue
            if now - max(self._state_since, self._last_group_at.get(group, float("-inf"))) < self._cooldown(c):
                continue
            if self._random() < self._chance(c):
                return c
        return None

    def _cooldown(self, c: Clip) -> float:
        return c.cooldown_ms if c.cooldown_ms is not None else self._cfg.get("eventCooldownMs", 60_000)

    def _chance(self, c: Clip) -> float:
        return c.chance if c.chance is not None else self._cfg.get("eventChance", 0)

    def _at_target(self) -> bool:
        t = self._target.state
        if self._current:
            return self._current.type in REST and self._current.state == t
        return self._node == self._graph.node_of_state(t)

    def _replan(self) -> None:
        if self._crossfading:
            self._emit()
            return
        t = self._target.state
        high = t in self._cfg["highPriority"]
        nxt: Clip | None = None

        if self._current:
            nxt = self._plan(self._node)
            cur = self._current
            # 在同一个节点上的 loop / 事件之间切换不算离开：同一状态的变体和事件，以及共用一个枢纽的状态
            # （比如 waiting 和 idle 都挂在枢纽 A 上、用同一段 loop），等这一轮播完直接接上，不交叉淡化
            leaving = (
                cur.type in REST
                and nxt is not None
                and not (nxt.type in REST and self._graph.end_node(nxt) == self._graph.end_node(cur))
            )
            urgent = (
                high
                or self._cfg.get("switchStyle") == "responsive"
                or (cur.type == "loop" and cur.state in self._cfg["interruptibleLoops"])
            )
            if leaving and urgent and self._cfg["crossfadeMs"] > 0 and nxt is not None:
                self._crossfading = True
                self._next = nxt
                self._apply_rate(high)
                self._player.crossfade_to(nxt)
                self._emit()
                return
        elif not self._holding:
            nxt = self._plan(self._node)
            # 停在一次性状态上时又来了同一状态的新目标：它已经在屏幕上了，直接确认
            if (
                nxt is None
                and self._hold_done
                and self._graph.is_oneshot(self._node)
                and self._graph.node_of_state(t) == self._node
            ):
                self._ack(self._target.seq)

        if (nxt.id if nxt else None) != (self._next.id if self._next else None):
            self._next = nxt
            self._player.set_next(nxt)
        self._apply_rate(high)
        self._emit()

    def _apply_rate(self, high: bool) -> None:
        boost = self._cfg["boostPlaybackRate"] if high and not self._at_target() else 1
        jitter = self._jitter if self._current and self._current.type == "loop" else 1.0
        rate = self._cfg["basePlaybackRate"] * boost * jitter
        if rate != self._rate:
            self._rate = rate
            self._player.set_rate(rate)

    def _emit(self) -> None:
        self._on_status(self.status())
