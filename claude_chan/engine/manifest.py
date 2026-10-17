"""manifest.json 的读取与校验。代码里所有素材文件名都来自 manifest。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Clip:
    id: str
    type: str  # intro / loop / event / outro / transition
    file: str
    state: str | None = None  # intro / loop / outro 所属状态
    frm: str | None = None  # intro、transition 的起点枢纽（manifest 里的 "from"）
    to: str | None = None  # outro、transition 的终点枢纽
    # 随机事件的可选参数（不写时用配置里的 eventChance / eventCooldownMs）
    chance: float | None = None  # 每播完一轮 loop 触发的概率
    cooldown_ms: float | None = None  # 同组事件之间至少间隔
    group: str | None = None  # 冷却按组计算：眨眼一组，打哈欠、张望这类动作一组（默认 "fidget"）


@dataclass(frozen=True)
class StateDef:
    hub: str
    kind: str  # loop / oneshot
    at_hub: bool = False  # 状态就是枢纽本身（idle = 枢纽 A），没有 intro / outro
    keyframe: str | None = None


@dataclass(frozen=True)
class Manifest:
    fps: float
    width: int
    height: int
    hubs: dict[str, dict[str, Any]]
    states: dict[str, StateDef]
    clips: list[Clip]

    @staticmethod
    def from_dict(d: dict[str, Any]) -> Manifest:
        return Manifest(
            fps=d["fps"],
            width=d["width"],
            height=d["height"],
            hubs=d["hubs"],
            states={
                k: StateDef(v["hub"], v["kind"], v.get("atHub", False), v.get("keyframe")) for k, v in d["states"].items()
            },
            clips=[
                Clip(
                    c["id"], c["type"], c["file"], c.get("state"), c.get("from"), c.get("to"),
                    c.get("chance"), c.get("cooldownMs"), c.get("group"),
                )
                for c in d["clips"]
            ],
        )

    @staticmethod
    def load(path: Path) -> Manifest:
        return Manifest.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def keyframes(self) -> list[str]:
        """所有状态和枢纽的关键帧（去重）。"""
        out = [s.keyframe for s in self.states.values() if s.keyframe]
        out += [h["keyframe"] for h in self.hubs.values() if h.get("keyframe")]
        return list(dict.fromkeys(out))


def validate_manifest(m: Manifest) -> list[str]:
    """返回问题列表；空列表表示 manifest 完整可用。"""
    errors: list[str] = []
    if not m.fps > 0:
        errors.append("fps 必须为正数")
    seen: set[str] = set()
    for c in m.clips:
        if c.id in seen:
            errors.append(f"片段 id 重复：{c.id}")
        seen.add(c.id)
        if c.state and c.state not in m.states:
            errors.append(f"片段 {c.id} 引用了未知状态 {c.state}")
        for h in (c.frm, c.to):
            if h and h not in m.hubs:
                errors.append(f"片段 {c.id} 引用了未知枢纽 {h}")
        if c.type == "transition" and not (c.frm and c.to):
            errors.append(f"过渡片段 {c.id} 缺少 from / to")
        if c.type == "event" and (not c.state or c.state not in m.states or m.states[c.state].kind != "loop"):
            errors.append(f"事件 {c.id} 必须挂在一个 loop 状态上")

    def find(state: str, kind: str) -> list[Clip]:
        return [c for c in m.clips if c.state == state and c.type == kind]

    for name, s in m.states.items():
        if s.hub not in m.hubs:
            errors.append(f"状态 {name} 的枢纽 {s.hub} 不存在")
        if s.kind == "loop" and not find(name, "loop"):
            errors.append(f"状态 {name} 至少需要一个 loop 片段")
        if s.at_hub:
            continue
        intro, outro = find(name, "intro"), find(name, "outro")
        if len(intro) != 1 or intro[0].frm != s.hub:
            errors.append(f"状态 {name} 需要一个从 {s.hub} 出发的 intro")
        if len(outro) != 1 or outro[0].to != s.hub:
            errors.append(f"状态 {name} 需要一个回到 {s.hub} 的 outro")
    return errors
