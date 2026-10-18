"""等你确认的气泡：从事件取内容、读会话记录、找桌面版的会话、排版。"""

import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtGui import QFont, QFontMetricsF
from PySide6.QtWidgets import QApplication

from claude_chan.bubble import _wrap, content_of
from claude_chan.jump import desktop_sessions
from claude_chan.model import DisplayTarget, FakeScheduler
from claude_chan.state.ask import Ask, describe
from claude_chan.state.sessions import SessionStore
from claude_chan.state.transcript import last_assistant_text, session_title


def ev(name, **kw):
    return {"hook_event_name": name, "session_id": "s1", "cwd": "C:\\work\\my-app", **kw}


# ---------- 事件 → 内容 ----------

def test_command_uses_claude_description():
    a = describe(ev("PermissionRequest", tool_name="Bash",
                    tool_input={"command": "rm -rf node_modules", "description": "Remove node_modules"}))
    assert a.verb == "等你确认" and a.text == "Remove node_modules" and a.command == "rm -rf node_modules"


def test_edit_counts_lines():
    a = describe(ev("PermissionRequest", tool_name="Edit", tool_input={
        "file_path": "C:\\work\\src\\login.py", "old_string": "a\nb\nc", "new_string": "a\nB\nc\nd"}))
    assert a.detail == "login.py  +2 −1"


def test_question_has_options():
    a = describe(ev("PreToolUse", tool_name="AskUserQuestion", tool_input={"questions": [
        {"question": "用哪个框架？", "options": [{"label": "React"}, {"label": "Vue"}]}]}))
    assert a.verb == "想问你" and a.text == "用哪个框架？" and a.options == ("React", "Vue")


def test_plan_title_and_steps():
    a = describe(ev("PreToolUse", tool_name="ExitPlanMode", tool_input={"plan": "# 重构登录\n1. 拆函数\n2. 补测试"}))
    assert a.verb == "计划写好了" and a.text == "重构登录" and a.detail == "2 步"


def test_permission_notification_has_no_new_info():
    assert describe(ev("Notification", notification_type="permission_prompt", message="Claude needs your permission")) is None


def test_mcp_tool():
    a = describe(ev("PermissionRequest", tool_name="mcp__github__create_issue", tool_input={}))
    assert a.text == "想用 github 的工具" and a.detail == "create_issue"


# ---------- 会话记录 ----------

def test_transcript_last_words_and_first_prompt(tmp_path):
    f = tmp_path / "t.jsonl"
    rows = [
        {"type": "user", "message": {"role": "user", "content": "<command-name>/clear</command-name>"}},
        {"type": "user", "message": {"role": "user", "content": "帮我把登录模块重构一下"}},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "先看看代码。"}]}},
        {"type": "user", "message": {"content": [{"type": "tool_result", "content": "..."}]}},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "依赖装坏了，**我先删掉重装**。"},
                                                      {"type": "tool_use", "name": "Bash"}]}},
    ]
    f.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    assert last_assistant_text(str(f)) == "依赖装坏了，我先删掉重装。"
    assert session_title(str(f)) == "帮我把登录模块重构一下"
    assert last_assistant_text("/home/me/t.jsonl") is None  # WSL 路径读不到


# ---------- 会话里记住、离开时清掉 ----------

def test_store_keeps_ask_until_leaving_confirmation():
    clock = FakeScheduler()
    seq = iter(range(1, 1000))
    targets = []
    cfg = {"timing": {"postToolDebounceMs": 800, "errorDedupMs": 30000, "idleToDrowsyMs": 600000,
                      "sessionTimeoutMs": 1800000, "latchMaxMs": 30000, "completeHoldMs": 30000, "waitingMaxMs": 7200000},
           "tools": {"confirm": ["AskUserQuestion", "ExitPlanMode"], "read": ["Read"], "write": ["Edit"], "default": "writing"},
           "priority": [["confirmation"], ["error"], ["writing", "reading", "thinking"], ["complete"], ["waiting"], ["idle"], ["drowsy"]]}
    store = SessionStore(cfg, lambda: next(seq), targets.append, clock)
    store.handle(ev("PermissionRequest", tool_name="Edit", tool_input={"file_path": "a.py", "old_string": "", "new_string": "x"}))
    assert targets[-1].state == "confirmation" and targets[-1].ask.detail == "a.py  +1 −0"
    store.handle(ev("Notification", notification_type="permission_prompt"))  # 没有新信息：保留
    assert targets[-1].ask.detail == "a.py  +1 −0"
    store.handle(ev("PostToolUse", tool_name="Edit"))
    clock.advance(1000)
    assert targets[-1].state == "thinking" and targets[-1].ask is None


# ---------- 桌面版的会话 ----------

def test_desktop_sessions_maps_cli_ids(tmp_path):
    d = tmp_path / "a" / "b"
    d.mkdir(parents=True)
    (d / "local_x.json").write_text(json.dumps({"sessionId": "local_x", "title": "重构登录", "cliSessionId": "cli-2",
                                                "priorCliSessionIds": ["cli-1"]}), encoding="utf-8")
    m = desktop_sessions(tmp_path)
    assert m["cli-1"] == ("local_x", "重构登录") and m["cli-2"] == ("local_x", "重构登录")


# ---------- 气泡排版 ----------

@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_wrap_clamps_with_ellipsis(app):
    fm = QFontMetricsF(QFont("Microsoft YaHei UI", 12))
    lines = _wrap("测试里有三个用例依赖旧的时间格式，我打算统一改成 ISO 8601，再把相关的快照文件一起更新。" * 2, fm, 200, 2)
    assert len(lines) == 2 and lines[-1].endswith("…")
    assert all(fm.horizontalAdvance(ln) <= 200 for ln in lines)


def test_content_prefers_claude_words_and_hides_commands():
    ask = Ask("等你确认", text="Remove node_modules", command="rm -rf node_modules", say="依赖装坏了，我先删掉重装。")
    t = DisplayTarget("confirmation", 1, project="my-app", ask=ask)
    c = content_of(t, None, show_commands=False)
    assert c.main == "依赖装坏了，我先删掉重装。" and c.detail == "Remove node_modules"
    assert content_of(t, None, show_commands=True).detail == "rm -rf node_modules"


def test_english_narration_skipped_in_chinese_session():
    ask = Ask("等你确认", text="想修改文件", detail="a.py  +1 −0", say="Adding the settings submenu.")
    t = DisplayTarget("confirmation", 1, project="my-app", ask=ask)
    assert content_of(t, "重构登录", show_commands=False).main == "想修改文件"
    assert content_of(t, "Refactor login", show_commands=False).main == "Adding the settings submenu."


def test_options_are_not_listed():
    ask = Ask("想问你", text="用哪个框架？", options=("React", "Vue", "Svelte"))
    c = content_of(DisplayTarget("confirmation", 1, project="my-app", ask=ask), None, show_commands=False)
    assert c.main == "用哪个框架？" and c.detail == "3 个选项，点这里去回答"
