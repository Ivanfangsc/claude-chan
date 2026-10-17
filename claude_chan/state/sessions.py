"""按 session_id 记录每个会话的状态，处理防抖、error、去重、超时，并汇总成一个目标。

每个会话有一个“基础状态”（idle / waiting / thinking / reading / writing / confirmation / complete），
外加一个可选的“待播 error”（latch）。latch 优先显示，直到动画引擎确认播完（ack）或超过
latchMaxMs。这样即使 Claude 立刻又开始调用工具，error 也一定会播一次。
complete 是普通的基础状态：Stop 后保持 completeHoldMs，再自动回到 idle。

后台任务：Claude 启动的后台命令、后台子代理，工具返回里带着任务编号；任务结束时，Claude 会被一条
带 <task-id> 的通知唤醒（经由 UserPromptSubmit）。两边按编号对账。Stop 时还有没结束的任务，
显示 waiting（Claude 还会自己继续，不需要用户），而不是 complete。waitingMaxMs 兜底。
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from ..model import DisplayTarget, Scheduler, SessionView
from .mapper import map_event, project_of, source_of

# 工具返回里的后台任务编号（Claude Code 的输出格式，变了就只能靠 waitingMaxMs 兜底）
_BACKGROUND_STARTED = [
    re.compile(r"running in background with ID: ([\w-]+)"),  # Bash run_in_background
    re.compile(r"Async agent launched[\s\S]*?agentId: ([\w-]+)"),  # 后台子代理
]
_BACKGROUND_DONE = re.compile(r"<task-id>([\w-]+)</task-id>")


@dataclass
class _Latch:
    seq: int
    sticky: bool
    timer: Any = None
    state: str = "error"


@dataclass
class _Session:
    id: str
    cwd: str
    source: str
    project: str
    base: str
    base_seq: int
    changed_at: float
    last_event_at: float
    last_event: str = ""
    last_error_at: float = -math.inf
    latch: _Latch | None = None
    post_timer: Any = None
    complete_timer: Any = None  # complete / waiting 到时回到 idle
    background: set[str] = field(default_factory=set)  # 还没结束的后台任务编号


@dataclass
class SessionStore:
    cfg: dict[str, Any]  # config["state"]
    next_seq: Callable[[], int]
    on_change: Callable[[DisplayTarget], None]
    clock: Scheduler
    log: Callable[[str], None] = lambda _msg: None
    _sessions: dict[str, _Session] = field(default_factory=dict)
    _last_any_event_at: float = 0
    _idle_seq: int = 0
    _drowsy_seq: int | None = None

    def __post_init__(self) -> None:
        self._last_any_event_at = self.clock.now()
        self._idle_seq = self.next_seq()

    @property
    def _timing(self) -> dict[str, Any]:
        return self.cfg["timing"]

    def set_config(self, cfg: dict[str, Any]) -> None:
        self.cfg = cfg
        self._recompute()

    def handle(self, e: dict[str, Any]) -> None:
        now = self.clock.now()
        self._last_any_event_at = now
        sid = e.get("session_id") or "unknown"
        action = map_event(e, self.cfg["tools"])
        label = e.get("hook_event_name", "?")
        for extra in ("tool_name", "notification_type"):
            if e.get(extra):
                label += f" {e[extra]}"

        if action.kind == "end":
            s = self._sessions.get(sid)
            if s:
                self._remove(s)
            self.log(f"{self._tag(s, e)} {label} → 移除会话")
            self._recompute()
            return

        s = self._sessions.get(sid) or self._create(sid, e.get("cwd"))
        cwd = e.get("cwd")
        if cwd and cwd != s.cwd:
            s.cwd, s.source, s.project = cwd, source_of(cwd), project_of(cwd)
        s.last_event_at = now
        s.last_event = label
        note = self._track_background(s, e)

        if action.kind == "base":
            self._cancel_post(s)
            if action.clear_latch:
                self._clear_latch(s)
            self._set_base(s, action.state or "idle")
        elif action.kind == "postTool":
            self._cancel_post(s)
            ms = self._timing["postToolDebounceMs"]

            def back_to_thinking() -> None:
                s.post_timer = None
                self._set_base(s, "thinking")
                self._recompute()

            s.post_timer = self.clock.call_later(ms, back_to_thinking)
            note = f"（{ms}ms 后回到 thinking）"
        elif action.kind == "toolFailure":
            self._cancel_post(s)
            self._set_base(s, "thinking")
            if now - s.last_error_at < self._timing["errorDedupMs"]:
                note = f"（{round(self._timing['errorDedupMs'] / 1000)} 秒内重复失败，不再播 error）"
            else:
                s.last_error_at = now
                self._set_latch(s, sticky=False)
        elif action.kind == "stop":
            self._cancel_post(s)
            held = "waiting" if s.background else "complete"
            self._set_base(s, held)
            if s.complete_timer is not None:  # 连续两次 Stop：重新计时
                self.clock.cancel(s.complete_timer)
            ms = self._timing["waitingMaxMs" if held == "waiting" else "completeHoldMs"]

            def back_to_idle() -> None:
                s.complete_timer = None
                if s.base == held:
                    s.background.clear()
                    self._set_base(s, "idle")
                    self._recompute()

            s.complete_timer = self.clock.call_later(ms, back_to_idle)
            if held == "waiting":
                note += f"（还有 {len(s.background)} 个后台任务，等它们结束；最多 {round(ms / 60_000)} 分钟）"
            else:
                note += f"（{round(ms / 1000)} 秒后回到 idle）"
        elif action.kind == "stopFailure":
            self._cancel_post(s)
            self._set_base(s, "idle")
            self._set_latch(s, sticky=True)

        self.log(f"{self._tag(s, e)} {label} → {self._effective(s)}{note}")
        self._recompute()

    def remove(self, sid: str) -> bool:
        """手动移除一个会话（调试面板用，比如回滚后残留的旧会话）。它之后再发事件会作为新会话重新出现。"""
        s = self._sessions.get(sid)
        if s is None:
            return False
        self._remove(s)
        self.log(f"{self._tag(s)} 手动移除会话")
        self._recompute()
        return True

    def ack(self, seq: int) -> None:
        """动画引擎播完了 error。"""
        for s in self._sessions.values():
            if s.latch and s.latch.seq == seq and not s.latch.sticky:
                self._clear_latch(s)
                s.changed_at = self.clock.now()
                self._recompute()
                return

    def _track_background(self, s: _Session, e: dict[str, Any]) -> str:
        """记录后台任务的开始和结束，返回日志备注。"""
        name = e.get("hook_event_name")
        if name == "PostToolUse":
            response = e.get("tool_response")
            text = response if isinstance(response, str) else json.dumps(response, ensure_ascii=False)
            for pattern in _BACKGROUND_STARTED:
                m = pattern.search(text or "")
                if m:
                    s.background.add(m.group(1))
                    return f"［后台任务 {m.group(1)} 开始，共 {len(s.background)} 个］"
        elif name == "UserPromptSubmit":
            done = [t for t in _BACKGROUND_DONE.findall(e.get("prompt") or "") if t in s.background]
            s.background.difference_update(done)
            if done:
                return f"［后台任务 {'、'.join(done)} 结束，还剩 {len(s.background)} 个］"
        return ""

    def sweep(self) -> None:
        """定时调用：清理超时会话、检查 drowsy。"""
        now = self.clock.now()
        for s in list(self._sessions.values()):
            stale = self._timing.get("thinkingStaleMs", 5 * 60_000)
            if s.base == "thinking" and not s.latch and now - s.last_event_at >= stale:
                self._set_base(s, "idle")
                self.log(f"{self._tag(s)} {round(stale / 60_000)} 分钟停在 thinking 没有事件（可能被回滚或中断），回到 idle")
            # 在等后台任务的会话可能很久没有事件，按 waitingMaxMs 算
            timeout = self._timing["waitingMaxMs" if s.base == "waiting" else "sessionTimeoutMs"]
            if now - s.last_event_at >= timeout:
                self.log(f"{self._tag(s)} {round(timeout / 60_000)} 分钟没有事件，清理会话")
                self._remove(s)
        self._recompute()

    def list(self) -> list[SessionView]:
        return [
            SessionView(
                id=s.id,
                cwd=s.cwd,
                source=s.source,
                project=s.project,
                base=s.base,
                latch=f"error{'（常驻）' if s.latch.sticky else ''}" if s.latch else None,
                effective=self._effective(s),
                last_event=s.last_event,
                last_event_at=s.last_event_at,
                background=len(s.background),
            )
            for s in self._sessions.values()
        ]

    def target(self) -> DisplayTarget:
        """按优先级汇总所有会话。"""
        priority: list[list[str]] = self.cfg["priority"]

        def rank(state: str) -> int:
            return next((i for i, group in enumerate(priority) if state in group), len(priority))

        best: _Session | None = None
        for s in self._sessions.values():
            if best is None:
                best = s
                continue
            d = rank(self._effective(s)) - rank(self._effective(best))
            if d < 0 or (d == 0 and s.changed_at > best.changed_at):
                best = s

        state = self._effective(best) if best else "idle"
        quiet = self.clock.now() - self._last_any_event_at >= self._timing["idleToDrowsyMs"]
        if state == "idle" and quiet:
            if self._drowsy_seq is None:
                self._drowsy_seq = self.next_seq()
            return DisplayTarget("drowsy", self._drowsy_seq)
        self._drowsy_seq = None
        if best is None:
            return DisplayTarget("idle", self._idle_seq)
        return DisplayTarget(
            state,
            best.latch.seq if best.latch else best.base_seq,
            sticky=bool(best.latch and best.latch.sticky),
            project=best.project,
            source=best.source,
            session_id=best.id,
        )

    def dispose(self) -> None:
        for s in list(self._sessions.values()):
            self._remove(s)

    # ---------- 内部 ----------

    def _recompute(self) -> None:
        self.on_change(self.target())

    def _create(self, sid: str, cwd: str | None) -> _Session:
        now = self.clock.now()
        s = _Session(
            id=sid,
            cwd=cwd or "",
            source=source_of(cwd),
            project=project_of(cwd),
            base="idle",
            base_seq=self.next_seq(),
            changed_at=now,
            last_event_at=now,
        )
        self._sessions[sid] = s
        return s

    def _remove(self, s: _Session) -> None:
        self._cancel_post(s)
        if s.complete_timer is not None:
            self.clock.cancel(s.complete_timer)
        self._clear_latch(s)
        self._sessions.pop(s.id, None)

    def _effective(self, s: _Session) -> str:
        return s.latch.state if s.latch else s.base

    def _set_base(self, s: _Session, state: str) -> None:
        if s.base == state:
            return
        if s.complete_timer is not None:
            self.clock.cancel(s.complete_timer)
            s.complete_timer = None
        s.base = state
        s.base_seq = self.next_seq()
        s.changed_at = self.clock.now()

    def _set_latch(self, s: _Session, sticky: bool) -> None:
        self._clear_latch(s)
        latch = _Latch(seq=self.next_seq(), sticky=sticky)
        if not sticky:

            def expire() -> None:
                if s.latch is latch:
                    s.latch = None
                    s.changed_at = self.clock.now()
                    self._recompute()

            latch.timer = self.clock.call_later(self._timing["latchMaxMs"], expire)
        s.latch = latch
        s.changed_at = self.clock.now()

    def _clear_latch(self, s: _Session) -> None:
        if s.latch and s.latch.timer is not None:
            self.clock.cancel(s.latch.timer)
        s.latch = None

    def _cancel_post(self, s: _Session) -> None:
        if s.post_timer is not None:
            self.clock.cancel(s.post_timer)
        s.post_timer = None

    def _tag(self, s: _Session | None = None, e: dict[str, Any] | None = None) -> str:
        e = e or {}
        source = s.source if s else source_of(e.get("cwd"))
        project = s.project if s else project_of(e.get("cwd"))
        label = {"wsl": "WSL", "windows": "Win"}.get(source, "?")
        sid = (s.id if s else e.get("session_id") or "")[:6]
        return f"[{label}·{project}·{sid}]"
