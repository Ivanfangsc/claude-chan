"""枢纽图与路径规划。

节点是 "hub:A" 这样的枢纽和 "state:thinking" 这样的状态，边是 intro / outro / transition / direct 片段。
direct 是两个状态之间的直达过渡（不经过枢纽），路径按片段数最短，有直达就走直达。
loop 不是边，它让显示停留在节点上。
"""

from __future__ import annotations

import random as _random
from collections import deque
from typing import Callable

from .manifest import Clip, Manifest


def hub_node(h: str) -> str:
    return f"hub:{h}"


def state_node(s: str) -> str:
    return f"state:{s}"


class Graph:
    def __init__(self, m: Manifest) -> None:
        self._m = m
        self._edges: dict[str, list[tuple[Clip, str]]] = {}
        for c in m.clips:
            if c.type == "intro":
                frm, to = hub_node(c.frm or ""), self.node_of_state(c.state or "")
            elif c.type == "outro":
                frm, to = self.node_of_state(c.state or ""), hub_node(c.to or "")
            elif c.type == "transition":
                frm, to = hub_node(c.frm or ""), hub_node(c.to or "")
            elif c.type == "direct":
                frm, to = self.node_of_state(c.frm or ""), self.node_of_state(c.to or "")
            else:
                continue
            self._edges.setdefault(frm, []).append((c, to))

    def node_of_state(self, state: str) -> str:
        """状态所在的节点；at_hub 状态（idle）就是它的枢纽。"""
        s = self._m.states.get(state)
        if s is None:
            raise KeyError(f"未知状态：{state}")
        return hub_node(s.hub) if s.at_hub else state_node(state)

    def end_node(self, clip: Clip) -> str:
        """片段播完后所处的节点。loop 和事件停在它所属状态的节点上。"""
        if clip.type in ("loop", "event", "intro"):
            return self.node_of_state(clip.state or "")
        if clip.type == "direct":
            return self.node_of_state(clip.to or "")
        return hub_node(clip.to or "")

    def start_node(self, clip: Clip) -> str:
        """片段开始时所处的节点。"""
        if clip.type in ("loop", "event", "outro"):
            return self.node_of_state(clip.state or "")
        if clip.type == "direct":
            return self.node_of_state(clip.frm or "")
        return hub_node(clip.frm or "")

    def rest_loop(self, node: str, target_state: str, random: Callable[[], float] = _random.random) -> Clip | None:
        """在节点上停留时播放的 loop（idle 的 loop 挂在枢纽 A 上）；一次性状态和枢纽 B 返回 None。

        一个状态可以有多段 loop 变体（同一段 loop 在不同位置眨眼的版本），每轮独立随机挑一段，可以重复：
        不重复的话两段变体会严格交替，眨眼又变成固定间隔。
        """
        if self.node_of_state(target_state) != node:
            return None
        loops = [c for c in self._m.clips if c.type == "loop" and c.state == target_state]
        return loops[int(random() * len(loops))] if loops else None

    def rest_events(self, node: str, target_state: str) -> list[Clip]:
        """停在该状态时可以随机插入的事件（首尾帧与 loop 相同，中间是别的动作）。"""
        if self.node_of_state(target_state) != node:
            return []
        return [c for c in self._m.clips if c.type == "event" and c.state == target_state]

    def path(self, frm: str, to: str) -> list[Clip]:
        """BFS 最短路径，返回沿途片段；frm == to 时返回空列表。"""
        if frm == to:
            return []
        prev: dict[str, tuple[str, Clip]] = {}
        queue = deque([frm])
        seen = {frm}
        while queue:
            n = queue.popleft()
            for clip, nxt in self._edges.get(n, []):
                if nxt in seen:
                    continue
                seen.add(nxt)
                prev[nxt] = (n, clip)
                if nxt == to:
                    out: list[Clip] = []
                    cur = to
                    while cur != frm:
                        cur, c = prev[cur]
                        out.insert(0, c)
                    return out
                queue.append(nxt)
        raise ValueError(f"没有从 {frm} 到 {to} 的路径")

    def is_oneshot(self, node: str) -> bool:
        if not node.startswith("state:"):
            return False
        s = self._m.states.get(node[6:])
        return s is not None and s.kind == "oneshot"
