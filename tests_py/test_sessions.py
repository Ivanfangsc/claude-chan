"""事件映射与多会话汇总（从 tests/sessions.test.ts 移植）。"""

import copy

import pytest

from claude_chan.config import DEFAULT_CONFIG
from claude_chan.model import DisplayTarget, FakeScheduler
from claude_chan.state.mapper import Action, map_event, project_of, source_of, tool_state
from claude_chan.state.sessions import SessionStore

CFG = copy.deepcopy(DEFAULT_CONFIG["state"])
TOOLS = CFG["tools"]


class Harness:
    def __init__(self) -> None:
        self.clock = FakeScheduler()
        self.targets: list[DisplayTarget] = []
        seq = iter(range(1, 10_000))
        self.store = SessionStore(copy.deepcopy(CFG), lambda: next(seq), self.targets.append, self.clock)

    def send(self, sid: str, name: str, **extra) -> None:
        self.store.handle({"hook_event_name": name, "session_id": sid, "cwd": "/home/me/proj-a", **extra})

    def state(self) -> str:
        return self.store.target().state

    def history(self) -> list[str]:
        """去掉连续重复后的目标状态序列"""
        out: list[str] = []
        for t in self.targets:
            if not out or out[-1] != t.state:
                out.append(t.state)
        return out

    def advance(self, ms: float) -> None:
        self.clock.advance(ms)


@pytest.fixture
def h() -> Harness:
    return Harness()


# ---------- mapper ----------


def test_maps_tools_including_regex_and_default() -> None:
    assert tool_state("Read", TOOLS) == "reading"
    assert tool_state("Edit", TOOLS) == "writing"
    assert tool_state("Bash", TOOLS) == "writing"
    assert tool_state("AskUserQuestion", TOOLS) == "confirmation"
    assert tool_state("mcp__github__get_issue", TOOLS) == "reading"


def test_maps_notifications_by_type() -> None:
    n = lambda kind: map_event({"hook_event_name": "Notification", "notification_type": kind}, TOOLS)  # noqa: E731
    assert n("permission_prompt") == Action("base", "confirmation")
    assert n("elicitation_dialog") == Action("base", "confirmation")
    assert n("idle_prompt") == Action("base", "idle")
    assert n("auth_success") == Action("touch")


def test_interrupted_tool_calls_do_not_play_error() -> None:
    assert map_event({"hook_event_name": "PostToolUseFailure", "is_interrupt": True}, TOOLS) == Action("postTool")
    assert map_event({"hook_event_name": "PostToolUseFailure", "is_interrupt": False}, TOOLS) == Action("toolFailure")


def test_detects_source_and_project() -> None:
    assert source_of("/home/me/proj", "win32") == "wsl"
    assert source_of("/mnt/c/work/proj", "win32") == "wsl"
    assert source_of("/Users/me/proj", "darwin") == "unknown"  # macOS 上就是本机
    assert source_of("C:\\Users\\me\\proj") == "windows"
    assert source_of("d:/code/proj") == "windows"
    assert project_of("C:\\Users\\me\\claude-girl\\") == "claude-girl"
    assert project_of("/home/me/proj-a") == "proj-a"


# ---------- sessions ----------


def test_follows_a_basic_turn(h: Harness) -> None:
    h.send("s1", "SessionStart")
    assert h.state() == "idle"
    h.send("s1", "UserPromptSubmit")
    assert h.state() == "thinking"
    h.send("s1", "PreToolUse", tool_name="Read")
    assert h.state() == "reading"
    h.send("s1", "PostToolUse", tool_name="Read")
    h.advance(799)
    assert h.state() == "reading"
    h.advance(1)
    assert h.state() == "thinking"
    h.send("s1", "Stop")
    assert h.state() == "complete"
    h.store.ack(h.targets[-1].seq)  # 动画播完也不会提前离开 complete
    assert h.state() == "complete"


def test_complete_holds_then_returns_to_idle(h: Harness) -> None:
    h.send("s1", "UserPromptSubmit")
    h.send("s1", "Stop")
    h.advance(29_999)
    assert h.state() == "complete"
    h.advance(1)
    assert h.state() == "idle"


def test_second_stop_restarts_the_complete_timer(h: Harness) -> None:
    h.send("s1", "Stop")
    h.advance(20_000)
    h.send("s1", "Stop")
    h.advance(20_000)
    assert h.state() == "complete"
    h.advance(10_000)
    assert h.state() == "idle"


def test_new_prompt_leaves_complete_immediately(h: Harness) -> None:
    h.send("s1", "Stop")
    h.send("s1", "UserPromptSubmit")
    assert h.state() == "thinking"
    h.advance(30_000)
    assert h.state() == "thinking"  # 旧的 complete 计时器不会把它拉回 idle


def test_debounces_rapid_tool_calls(h: Harness) -> None:
    h.send("s1", "UserPromptSubmit")
    for i in range(10):
        h.send("s1", "PreToolUse", tool_name="Edit" if i % 2 else "Read")
        h.advance(100)
        h.send("s1", "PostToolUse")
        h.advance(500)
    assert h.history() == ["thinking"] + ["writing" if i % 2 else "reading" for i in range(10)]
    h.advance(300)
    assert h.history()[-1] == "thinking"


def test_error_plays_once_per_failure_burst(h: Harness) -> None:
    h.send("s1", "UserPromptSubmit")
    h.send("s1", "PostToolUseFailure", tool_name="Bash")
    assert h.state() == "error"
    err_seq = h.targets[-1].seq
    # Claude 立刻又调了工具：error 仍然先显示，直到动画确认
    h.send("s1", "PreToolUse", tool_name="Edit")
    assert h.state() == "error"
    h.store.ack(err_seq)
    assert h.state() == "writing"
    h.advance(10_000)
    h.send("s1", "PostToolUseFailure")
    assert h.state() == "thinking"  # 30 秒内重复，不再播
    h.advance(20_000)
    h.send("s1", "PostToolUseFailure")
    assert h.state() == "error"


def test_drops_unacknowledged_error_after_latch_max(h: Harness) -> None:
    h.send("s1", "UserPromptSubmit")
    h.send("s1", "PostToolUseFailure")
    assert h.state() == "error"
    h.advance(30_000)
    assert h.state() == "thinking"


def test_stop_failure_error_stays_until_next_prompt(h: Harness) -> None:
    h.send("s1", "UserPromptSubmit")
    h.send("s1", "StopFailure")
    t = h.targets[-1]
    assert (t.state, t.sticky) == ("error", True)
    h.store.ack(t.seq)
    # 常驻到下一次提问；但 30 分钟没有事件时按会话结束清理（两条规则里清理优先）
    h.advance(29 * 60_000)
    h.store.sweep()
    assert h.state() == "error"
    h.send("s1", "UserPromptSubmit")
    assert h.state() == "thinking"


def test_idle_prompt_returns_to_idle_after_interrupt(h: Harness) -> None:
    h.send("s1", "UserPromptSubmit")
    h.send("s1", "PreToolUse", tool_name="Edit")
    h.send("s1", "Notification", notification_type="idle_prompt")
    assert h.state() == "idle"


def test_aggregates_by_priority_and_shows_who_is_waiting(h: Harness) -> None:
    h.send("a", "PreToolUse", tool_name="Edit", cwd="/home/me/alpha")
    h.send("b", "SessionStart", cwd="C:\\code\\beta")
    t = h.store.target()
    assert (t.state, t.project) == ("writing", "alpha")
    h.send("b", "PermissionRequest", tool_name="Bash", cwd="C:\\code\\beta")
    t = h.store.target()
    assert (t.state, t.project, t.source) == ("confirmation", "beta", "windows")
    h.send("b", "PostToolUse", cwd="C:\\code\\beta")
    h.advance(800)
    # b 回到 thinking，比 a 的 writing 更新，同一优先级组里取最新的
    t = h.store.target()
    assert (t.state, t.project) == ("thinking", "beta")


def test_prefers_working_sessions_over_completion(h: Harness) -> None:
    h.send("a", "PreToolUse", tool_name="Read")
    h.send("b", "Stop")
    assert h.state() == "reading"


def test_gets_drowsy_after_quiet_minutes_and_wakes(h: Harness) -> None:
    h.send("s1", "SessionStart")
    h.advance(599_000)
    h.store.sweep()
    assert h.state() == "idle"
    h.advance(1_000)
    h.store.sweep()
    assert h.state() == "drowsy"
    h.send("s2", "SessionStart")
    assert h.state() == "idle"


def test_not_drowsy_while_working(h: Harness) -> None:
    h.send("s1", "PreToolUse", tool_name="Bash")
    h.advance(700_000)
    h.store.sweep()
    assert h.state() == "writing"


def test_removes_sessions_on_end_and_timeout(h: Harness) -> None:
    h.send("a", "PreToolUse", tool_name="Edit")
    h.send("b", "PreToolUse", tool_name="Read")
    h.send("a", "SessionEnd")
    assert [s.id for s in h.store.list()] == ["b"]
    h.advance(1_800_000)
    h.store.sweep()
    assert h.store.list() == []


# ---------- 等待后台任务 ----------

BASH_BG = "Command running in background with ID: bx1. Output is being written to: C:\tmp\bx1.output"
AGENT_BG = "Async agent launched successfully.\nagentId: a9f (internal ID)\noutput_file: C:\tmp\a9f.output"


def notify(task_id: str) -> str:
    return f"<task-notification>\n<task-id>{task_id}</task-id>\n<status>completed</status>\n</task-notification>"


def test_stop_with_background_task_waits_until_notification(h: Harness) -> None:
    h.send("s1", "UserPromptSubmit", prompt="跑一下")
    h.send("s1", "PreToolUse", tool_name="Bash", tool_input={"run_in_background": True})
    h.send("s1", "PostToolUse", tool_name="Bash", tool_response=BASH_BG)
    h.send("s1", "Stop")
    assert h.state() == "waiting"
    h.advance(60 * 60_000)
    assert h.state() == "waiting"  # 不会像 complete 那样 30 秒后回到 idle
    h.send("s1", "UserPromptSubmit", prompt=notify("bx1"))  # 任务结束，Claude 被唤醒
    assert h.state() == "thinking"
    h.send("s1", "Stop")
    assert h.state() == "complete"


def test_user_prompt_does_not_finish_background_tasks(h: Harness) -> None:
    h.send("s1", "PostToolUse", tool_name="Agent", tool_response={"content": [{"type": "text", "text": AGENT_BG}]})
    h.send("s1", "Stop")
    h.send("s1", "UserPromptSubmit", prompt="顺便问一下别的")
    h.send("s1", "Stop")
    assert h.state() == "waiting"
    assert h.store.list()[0].background == 1
    h.send("s1", "UserPromptSubmit", prompt=notify("a9f") + notify("unknown"))
    h.send("s1", "Stop")
    assert h.state() == "complete"


def test_waiting_gives_up_after_max_and_survives_sweep(h: Harness) -> None:
    h.send("s1", "PostToolUse", tool_name="Bash", tool_response=BASH_BG)
    h.send("s1", "Stop")
    h.advance(CFG["timing"]["sessionTimeoutMs"] + 1)
    h.store.sweep()
    assert h.state() == "waiting"  # 会话超时按 waitingMaxMs 算
    h.advance(CFG["timing"]["waitingMaxMs"])
    assert h.store.list()[0].base == "idle" and h.store.list()[0].background == 0
    assert h.state() == "drowsy"  # 这么久没有任何事件，idle 直接变成打瞌睡


def test_complete_outranks_waiting(h: Harness) -> None:
    h.send("s1", "PostToolUse", tool_name="Bash", tool_response=BASH_BG)
    h.send("s1", "Stop")
    h.send("s2", "Stop")
    assert h.state() == "complete"
    h.advance(CFG["timing"]["completeHoldMs"])
    assert h.state() == "waiting"


def test_stale_thinking_session_falls_back_to_idle(h: Harness) -> None:
    # 会话 s1 在工具调用后被回滚：停在 thinking，再也收不到 Stop
    h.send("s1", "PreToolUse", tool_name="Bash")
    h.send("s1", "PostToolUse", tool_name="Bash")
    h.advance(1000)
    # 回滚后的新会话 s2 正常结束
    h.send("s2", "UserPromptSubmit", prompt="继续")
    h.send("s2", "Stop")
    assert h.state() == "thinking"  # 旧会话盖住了 complete
    h.advance(CFG["timing"]["thinkingStaleMs"])
    h.send("s2", "Stop")
    h.store.sweep()
    assert h.state() == "complete"


def test_long_tool_call_is_not_stale(h: Harness) -> None:
    h.send("s1", "PreToolUse", tool_name="Bash")  # 跑很久的命令：writing，期间没有事件
    h.advance(CFG["timing"]["thinkingStaleMs"] * 2)
    h.store.sweep()
    assert h.state() == "writing"


def test_remove_session_manually(h: Harness) -> None:
    h.send("old", "PreToolUse", tool_name="Read")
    h.send("new", "Stop")
    assert h.state() == "reading"
    assert h.store.remove("old") and not h.store.remove("old")
    assert h.state() == "complete"
    h.send("old", "PreToolUse", tool_name="Read")  # 再发事件会重新出现
    assert h.state() == "reading"
