"""路径规划与动画引擎（从 tests/graph.test.ts、tests/engine.test.ts 移植）。"""

import copy
import dataclasses
import itertools
import re
from pathlib import Path

import pytest

from claude_chan.config import DEFAULT_CONFIG
from claude_chan.engine.engine import Engine
from claude_chan.engine.graph import Graph
from claude_chan.engine.manifest import Clip, Manifest, validate_manifest
from claude_chan.model import DisplayTarget, FakeScheduler

ROOT = Path(__file__).resolve().parents[1]
REAL = Manifest.load(ROOT / "resources" / "assets" / "manifest.json")
# 测试基准：去掉 loop 变体（xxx-loop-2 等）和随机事件，每个状态只有一段 loop，结果可预测
BASE = dataclasses.replace(
    REAL, clips=[c for c in REAL.clips if c.type not in ("event", "direct") and not re.search(r"-loop-\d+$", c.id)]
)
WITH_VARIANTS = dataclasses.replace(
    BASE,
    clips=[*BASE.clips, Clip("idle-loop-2", "loop", "x.webp", "idle"), Clip("idle-loop-3", "loop", "y.webp", "idle")],
)

_seq = itertools.count(1)


def t(state: str, **extra) -> DisplayTarget:
    return DisplayTarget(state, next(_seq), **extra)


# ---------- manifest 与路径规划 ----------

GRAPH = Graph(BASE)


def ids(frm: str, to: str) -> list[str]:
    return [c.id for c in GRAPH.path(GRAPH.node_of_state(frm), GRAPH.node_of_state(to))]


def test_manifest_is_valid() -> None:
    assert validate_manifest(REAL) == []


def test_allows_loop_variants_but_requires_one() -> None:
    assert validate_manifest(WITH_VARIANTS) == []
    none = dataclasses.replace(BASE, clips=[c for c in BASE.clips if c.id != "thinking-loop"])
    assert "状态 thinking 至少需要一个 loop 片段" in validate_manifest(none)


def test_reports_missing_clips() -> None:
    broken = dataclasses.replace(BASE, clips=[c for c in BASE.clips if c.id != "writing-outro"])
    assert "状态 writing 需要一个回到 B 的 outro" in validate_manifest(broken)


def test_paths() -> None:
    assert GRAPH.node_of_state("idle") == "hub:A"
    assert ids("thinking", "writing") == ["thinking-outro", "hub-A-to-B", "writing-intro"]
    assert ids("reading", "writing") == ["reading-outro", "writing-intro"]
    assert ids("writing", "reading") == ["writing-outro", "reading-intro"]
    assert ids("writing", "idle") == ["writing-outro", "hub-B-to-A"]


def test_direct_transitions_take_the_short_way() -> None:
    """状态之间有直达过渡时，不再绕枢纽；没有直达的照旧走枢纽。"""
    direct = dataclasses.replace(BASE, clips=[
        *BASE.clips,
        Clip("thinking-to-writing", "direct", "d.avif", None, "thinking", "writing"),
        Clip("writing-to-reading", "direct", "e.avif", None, "writing", "reading"),
    ])
    assert validate_manifest(direct) == []
    g = Graph(direct)
    path = lambda a, b: [c.id for c in g.path(g.node_of_state(a), g.node_of_state(b))]
    assert path("thinking", "writing") == ["thinking-to-writing"]
    assert path("writing", "reading") == ["writing-to-reading"]
    assert path("writing", "thinking") == ["writing-outro", "hub-B-to-A", "thinking-intro"]
    assert path("thinking", "reading") == ["thinking-to-writing", "writing-to-reading"]  # 两段直达比绕枢纽三段短
    clip = direct.clips[-2]
    assert g.start_node(clip) == "state:thinking" and g.end_node(clip) == "state:writing"


def test_direct_must_join_loop_states() -> None:
    bad = dataclasses.replace(BASE, clips=[*BASE.clips, Clip("x", "direct", "x.avif", None, "thinking", "error")])
    assert any("直达过渡 x" in e for e in validate_manifest(bad))


def test_every_state_reaches_every_other() -> None:
    for a in BASE.states:
        for b in BASE.states:
            ids(a, b)


# ---------- 引擎 ----------


class FakePlayer:
    """同步的假播放器：finish() 表示当前段播到末帧。"""

    def __init__(self) -> None:
        self.on_clip_start = lambda _c: None
        self.on_stall = lambda: None
        self.next: Clip | None = None
        self.playing: Clip | None = None
        self.stalled = True
        self.played: list[str] = []
        self.crossfades: list[str] = []
        self.rate = 1.0

    def set_next(self, c: Clip | None) -> None:
        self.next = c
        if self.stalled and c:
            self._start_next()

    def crossfade_to(self, c: Clip) -> None:
        self.crossfades.append(c.id)
        self.next = None
        self._begin(c)

    def set_rate(self, r: float) -> None:
        self.rate = r

    def finish(self) -> None:
        if self.next:
            self._start_next()
            return
        self.playing = None
        self.stalled = True
        self.on_stall()

    def _start_next(self) -> None:
        c, self.next = self.next, None
        self._begin(c)

    def _begin(self, c: Clip) -> None:
        self.playing = c
        self.stalled = False
        self.played.append(c.id)
        self.on_clip_start(c)


class Rig:
    def __init__(self, manifest: Manifest = BASE, random=None, **overrides) -> None:
        cfg = {**copy.deepcopy(DEFAULT_CONFIG["animation"]), "interruptibleLoops": [], "loopRateJitter": 0, **overrides}
        self.clock = FakeScheduler()
        self.player = FakePlayer()
        self.acks: list[int] = []
        kwargs = {"random": random} if random else {}
        self.engine = Engine(
            Graph(manifest), self.player, cfg, self.acks.append, lambda _s: None, t("idle"), self.clock, **kwargs
        )
        self.engine.start()

    def run(self, n: int) -> list[str]:
        """连续 finish n 次，返回这期间开始播放的片段。"""
        start = len(self.player.played)
        for _ in range(n):
            self.player.finish()
        return self.player.played[start:]


def test_starts_on_idle_loop_and_keeps_looping() -> None:
    r = Rig()
    assert r.player.played == ["idle-loop"]
    assert r.run(2) == ["idle-loop", "idle-loop"]


def test_loop_variants_are_picked_independently() -> None:
    r = Rig(WITH_VARIANTS)
    played = [r.player.played[0], *r.run(60)]
    assert len(set(played)) == 3
    assert any(a == b for a, b in zip(played, played[1:]))  # 可以连着播同一段，不会严格交替


def test_switching_variants_does_not_crossfade() -> None:
    r = Rig(WITH_VARIANTS, interruptibleLoops=["idle"])
    r.run(5)
    assert r.player.crossfades == []


def test_keeps_chosen_variant_when_target_resent() -> None:
    calls = itertools.count()
    r = Rig(WITH_VARIANTS, random=lambda: (next(calls) % 2) / 2)
    chosen = r.player.next.id
    r.engine.set_target(t("idle"))
    r.engine.set_target(t("idle"))
    assert r.player.next.id == chosen


def test_finishes_current_loop_before_leaving() -> None:
    r = Rig()
    r.engine.set_target(t("thinking"))
    assert r.player.playing.id == "idle-loop"
    assert r.run(3) == ["thinking-intro", "thinking-loop", "thinking-loop"]


def test_plans_thinking_to_writing_through_both_hubs() -> None:
    r = Rig()
    r.engine.set_target(t("thinking"))
    r.run(2)
    r.engine.set_target(t("writing"))
    assert r.run(4) == ["thinking-outro", "hub-A-to-B", "writing-intro", "writing-loop"]


def test_follows_only_latest_target() -> None:
    r = Rig()
    r.engine.set_target(t("reading"))
    r.run(1)  # reading 路径上的 hub-A-to-B 开始
    r.engine.set_target(t("writing"))
    r.engine.set_target(t("thinking"))
    assert r.run(4) == ["hub-B-to-A", "thinking-intro", "thinking-loop", "thinking-loop"]


def test_crossfades_out_of_loop_for_high_priority() -> None:
    r = Rig()
    r.engine.set_target(t("writing"))
    r.run(3)
    r.engine.set_target(t("confirmation"))
    assert r.player.crossfades == ["writing-outro"]
    assert r.run(3) == ["hub-B-to-A", "confirmation-intro", "confirmation-loop"]


def test_crossfades_idle_straight_into_high_priority_intro() -> None:
    r = Rig()
    r.engine.set_target(t("error"))
    assert r.player.crossfades == ["error-intro"]


def test_leaves_interruptible_loops_immediately() -> None:
    r = Rig(interruptibleLoops=["idle", "drowsy"])
    r.engine.set_target(t("thinking"))
    assert r.player.crossfades == ["thinking-intro"]
    assert r.run(1) == ["thinking-loop"]
    r.engine.set_target(t("reading"))
    assert r.player.crossfades == ["thinking-intro"]  # thinking 不在列表里，等这一轮播完


def test_holds_oneshot_acks_then_leaves() -> None:
    r = Rig(crossfadeMs=0)
    done = t("error")
    r.engine.set_target(done)
    r.run(1)  # error-intro
    r.player.finish()  # 停在关键帧
    assert r.player.stalled and r.acks == []
    r.clock.advance(999)
    assert r.acks == []
    r.clock.advance(1)
    assert r.acks == [done.seq]
    r.engine.set_target(t("idle"))
    assert r.player.playing.id == "error-outro"
    assert r.run(1) == ["idle-loop"]


def test_still_holds_oneshot_when_target_moves_on() -> None:
    r = Rig(crossfadeMs=0)
    r.engine.set_target(t("error"))
    r.run(1)
    r.engine.set_target(t("thinking"))
    r.player.finish()
    assert r.player.stalled
    r.clock.advance(1000)
    assert r.player.playing.id == "error-outro"
    assert r.run(2) == ["thinking-intro", "thinking-loop"]


def test_sticky_error_stays_until_target_changes() -> None:
    r = Rig(crossfadeMs=0)
    r.engine.set_target(t("error", sticky=True))
    r.run(1)
    r.player.finish()
    r.clock.advance(60_000)
    assert r.player.stalled
    r.engine.set_target(t("thinking"))
    assert r.player.playing.id == "error-outro"
    assert r.run(2) == ["thinking-intro", "thinking-loop"]


def test_boosts_while_chasing_high_priority() -> None:
    r = Rig(boostPlaybackRate=2, crossfadeMs=0)
    r.engine.set_target(t("confirmation"))
    assert r.player.rate == 2
    r.run(2)
    assert r.player.rate == 1


@pytest.mark.parametrize("pair", list(itertools.permutations(["idle", "thinking", "writing", "error"], 2)))
def test_reaches_target_from_any_state(pair) -> None:
    a, b = pair
    r = Rig(crossfadeMs=0)
    r.engine.set_target(t(a, sticky=True))
    for _ in range(8):
        r.player.finish()
        r.clock.advance(1000)
    r.engine.set_target(t(b, sticky=True))
    for _ in range(8):
        r.player.finish()
        r.clock.advance(1000)
    assert r.engine.status().at_target


# ---------- 随机事件 ----------

WITH_EVENTS = dataclasses.replace(
    BASE,
    clips=[*BASE.clips, Clip("idle-yawn", "event", "yawn.avif", "idle"), Clip("idle-look", "event", "look.avif", "idle")],
)


def test_events_are_valid_only_on_loop_states() -> None:
    assert validate_manifest(WITH_EVENTS) == []
    bad = dataclasses.replace(BASE, clips=[*BASE.clips, Clip("error-x", "event", "x.avif", "error")])
    assert "事件 error-x 必须挂在一个 loop 状态上" in validate_manifest(bad)


def test_plays_an_event_by_chance_then_respects_cooldown() -> None:
    # random 恒为 0：概率判定总是通过，挑第一个事件
    r = Rig(WITH_EVENTS, random=lambda: 0.0, eventChance=0.5, eventCooldownMs=60_000)
    assert r.player.played == ["idle-loop"]  # 冷却从启动时开始算，刚启动不播事件
    assert r.run(3) == ["idle-loop", "idle-loop", "idle-loop"]
    r.clock.advance(60_000)
    # 冷却结束前下一轮已经排好了 loop；再下一轮才抽事件；事件后不连着再播事件
    assert r.run(3) == ["idle-loop", "idle-yawn", "idle-loop"]
    r.clock.advance(60_000)
    assert r.run(3) == ["idle-loop", "idle-look", "idle-loop"]  # 下一次换一个事件


def test_cooldown_restarts_when_state_changes() -> None:
    r = Rig(WITH_EVENTS, random=lambda: 0.0, eventChance=1, eventCooldownMs=60_000)
    r.clock.advance(60_000)
    r.engine.set_target(t("thinking"))
    r.engine.set_target(t("idle"))
    r.run(3)  # 回到 idle 的路上又经过了过渡片段
    assert "idle-yawn" not in r.run(5)


def test_never_plays_events_when_chance_is_zero() -> None:
    r = Rig(WITH_EVENTS, random=lambda: 0.0, eventChance=0)
    r.clock.advance(120_000)
    assert set(r.run(10)) == {"idle-loop"}


def test_switching_between_loop_and_event_does_not_crossfade() -> None:
    r = Rig(WITH_EVENTS, random=lambda: 0.0, eventChance=1, eventCooldownMs=0, interruptibleLoops=["idle"])
    r.run(4)
    assert r.player.crossfades == []


def test_events_can_be_interrupted() -> None:
    r = Rig(WITH_EVENTS, random=lambda: 0.0, eventChance=1, eventCooldownMs=0)
    assert r.player.playing.id == "idle-yawn"
    r.engine.set_target(t("thinking"))
    assert r.player.crossfades == ["thinking-intro"]
    assert r.engine.status().current == "thinking-intro"


def test_events_wait_when_not_interruptible() -> None:
    r = Rig(WITH_EVENTS, random=lambda: 0.0, eventChance=1, interruptibleEvents=False)
    r.engine.set_target(t("thinking"))
    assert r.player.crossfades == []
    assert r.run(1) == ["thinking-intro"]


# ---------- 按事件设置概率和冷却、loop 速度浮动 ----------

BLINKY = dataclasses.replace(
    BASE,
    clips=[
        *BASE.clips,
        Clip("idle-blink", "event", "blink.avif", "idle", chance=1.0, cooldown_ms=0, group="blink"),
        Clip("idle-yawn", "event", "yawn.avif", "idle", chance=1.0, cooldown_ms=60_000),
    ],
)


def test_event_groups_have_separate_cooldowns() -> None:
    # random 恒为 0：从第一个事件开始检查，概率 1 的事件必中
    r = Rig(BLINKY, random=lambda: 0.0)
    # 眨眼没有冷却，一启动就可以眨；打哈欠要等 60 秒；事件之间总隔着一轮 loop
    assert [r.player.played[0], *r.run(3)] == ["idle-blink", "idle-loop", "idle-blink", "idle-loop"]
    r.clock.advance(60_000)
    assert r.run(4) == ["idle-blink", "idle-loop", "idle-yawn", "idle-loop"]


def test_event_chance_per_clip() -> None:
    never = dataclasses.replace(BASE, clips=[*BASE.clips, Clip("idle-blink", "event", "b.avif", "idle", chance=0.0)])
    r = Rig(never, random=lambda: 0.0, eventChance=1.0)
    assert set(r.run(10)) == {"idle-loop"}  # 事件自己的概率优先于配置


def test_loop_rate_jitter() -> None:
    values = itertools.cycle([0.0, 0.999, 0.5])
    r = Rig(random=lambda: next(values), loopRateJitter=0.1)
    rates = set()
    for _ in range(6):
        r.player.finish()
        rates.add(round(r.player.rate, 3))
    assert len(rates) > 1 and all(0.9 <= x <= 1.1 for x in rates)


# ---------- 调试面板：手动触发事件、关闭事件组 ----------


def test_requested_event_plays_next_round_ignoring_cooldown() -> None:
    r = Rig(BLINKY, random=lambda: 0.0, eventChance=0)
    assert r.engine.request_event("idle-yawn")
    assert r.player.next.id == "idle-yawn"  # 当前这一轮 loop 播完就播
    assert r.run(1) == ["idle-yawn"]
    assert not r.engine.request_event("thinking-loop")  # 不是当前状态的事件


def test_request_dropped_when_state_changes() -> None:
    r = Rig(BLINKY, random=lambda: 0.0, eventChance=0, disabledEventGroups=["blink"])
    r.engine.request_event("idle-yawn")
    r.engine.set_target(t("thinking"))
    r.engine.set_target(t("idle"))
    assert "idle-yawn" not in r.run(8)


def test_disabled_groups_and_event_info() -> None:
    r = Rig(BLINKY, random=lambda: 0.0, disabledEventGroups=["blink"])
    assert "idle-blink" not in [r.player.played[0], *r.run(6)]
    info = {e.id: e for e in r.engine.events()}
    assert info["idle-blink"].disabled and info["idle-blink"].group == "blink"
    assert info["idle-yawn"].remaining_ms == 60_000  # 冷却从启动时开始算，时钟没走
    r.clock.advance(20_000)
    assert {e.id: e for e in r.engine.events()}["idle-yawn"].remaining_ms == 40_000


# ---------- 共用枢纽的状态（waiting 和 idle 都挂在枢纽 A 上） ----------

WITH_WAITING = dataclasses.replace(
    BASE,
    states={**BASE.states, "waiting": dataclasses.replace(BASE.states["idle"])},
    clips=[
        *[c for c in BASE.clips if c.state != "waiting"],
        Clip("waiting-loop", "loop", "idle.avif", "waiting"),
        Clip("waiting-watch", "event", "w.avif", "waiting", chance=1.0, cooldown_ms=0),
    ],
)


def test_switching_between_states_on_same_hub_does_not_crossfade() -> None:
    r = Rig(WITH_WAITING, random=lambda: 0.0, interruptibleLoops=["idle", "waiting"])
    assert validate_manifest(WITH_WAITING) == []
    r.engine.set_target(t("waiting"))
    assert r.player.crossfades == []  # 同一个枢纽，不算离开：不打断 idle 这一轮
    assert r.run(3) == ["waiting-watch", "waiting-loop", "waiting-watch"]
    r.engine.set_target(t("idle"))
    assert r.player.crossfades == []
    assert r.run(1) == ["idle-loop"]
    r.engine.set_target(t("thinking"))
    assert r.player.crossfades == ["thinking-intro"]  # 真正离开时照常交叉淡化
