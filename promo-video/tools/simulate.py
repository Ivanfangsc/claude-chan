"""用插件真实的会话汇总和动画引擎，算出剧情里她会在什么时间播哪一段。

    uv run python promo-video/tools/simulate.py [种子] [用户点允许的秒数]

剧情是一串 Claude Code 会发来的 hook 事件（STORY），按时间喂给 SessionStore → TargetHub → Engine，
和桌宠里完全一样；播放器换成按片段帧数计时的假播放器，记下每段的开始时间、片段和播放速度。
输出 promo-video/src/story.json，宣传片按它逐帧播放，所以片中她的反应就是桌宠真实会做的。
随机小动作用固定种子，换种子会得到另一种同样真实的结果。
"""

import json
import random
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from claude_chan.config import DEFAULT_CONFIG  # noqa: E402
from claude_chan.engine.engine import Engine  # noqa: E402
from claude_chan.engine.graph import Graph  # noqa: E402
from claude_chan.engine.manifest import Manifest  # noqa: E402
from claude_chan.model import FakeScheduler  # noqa: E402
from claude_chan.state.sessions import SessionStore  # noqa: E402
from claude_chan.state.target import TargetHub  # noqa: E402

ASSETS = ROOT / "resources" / "assets"
OUT = ROOT / "promo-video" / "src" / "story.json"
FPS = 24
CWD = r"C:\work\shop-web"


def ev(name, **kw):
    return {"hook_event_name": name, "session_id": "story", "cwd": CWD, **kw}


def tool(name, **inp):
    return {"tool_name": name, "tool_input": inp}


# 剧情：(秒, hook 事件, 终端里多出来的一行)。终端行是 [种类, 文字...]，story.js 照着画；None 表示不发 hook / 不加行。
READS = [("Read", "src/pages/Login.tsx", "Read 84 lines"), ("Search", "handleSubmit", "Found 3 files"),
         ("Read", "src/components/LoginForm.tsx", "Read 112 lines"), ("Read", "src/api/auth.ts", "Read 46 lines"),
         ("Read", "src/components/Button.tsx", "Read 38 lines"), ("Read", "src/hooks/useAuth.ts", "Read 61 lines"),
         ("Search", "onSubmit", "Found 5 files"), ("Read", "src/pages/Login.test.tsx", "Read 70 lines"),
         ("Read", "src/api/client.ts", "Read 52 lines"), ("Read", "src/router.tsx", "Read 33 lines"),
         ("Read", "src/components/Input.tsx", "Read 41 lines")]
EDITS = [("src/components/LoginForm.tsx", 3, 1), ("src/api/auth.ts", 5, 2), ("src/components/Button.tsx", 1, 1),
         ("src/hooks/useAuth.ts", 4, 0), ("src/pages/Login.tsx", 2, 2), ("src/api/auth.ts", 1, 1),
         ("src/components/LoginForm.tsx", 6, 3), ("src/pages/Login.test.tsx", 18, 0),
         ("src/hooks/useAuth.ts", 2, 1), ("src/components/LoginForm.tsx", 1, 1), ("src/api/auth.ts", 3, 0),
         ("src/pages/Login.test.tsx", 4, 2)]
TEST = "npm test -- login"
def build(approve_at: float):
    out = [(3.2, ev("UserPromptSubmit", prompt="登录页点了没反应，帮我看看"), ["you", "登录页点了没反应，帮我看看"]),
           (5.6, None, ["say", "我先看看登录页相关的代码。"])]
    t = 6.4
    for kind, arg, res in READS:
        name = "Grep" if kind == "Search" else "Read"
        inp = {"pattern": arg} if name == "Grep" else {"file_path": arg}
        out.append((t, ev("PreToolUse", **tool(name, **inp)), ["tool", kind, arg]))
        out.append((t + 0.3, ev("PostToolUse", **tool(name, **inp)), ["result", res]))
        t += 0.55
    out.append((t, None, ["say", "找到原因了：表单没有绑定提交事件，按钮点了只是个普通按钮。我来修一下。"]))
    t = max(t + 0.4, 13.0)
    for f, a, r in EDITS:
        out.append((t, ev("PreToolUse", **tool("Edit", file_path=f, old_string="x", new_string="y")), ["tool", "Update", f]))
        out.append((t + 0.35, ev("PostToolUse", **tool("Edit", file_path=f)), ["result", f"Updated with {a} additions and {r} removals"]))
        t += 0.65
    out.append((t, None, ["say", "改好了，跑一下测试确认。"]))
    t += 0.8
    bash = tool("Bash", command=TEST, description="Run login tests")
    out.append((t, ev("PreToolUse", **bash), None))
    out.append((t + 0.1, ev("PermissionRequest", **bash), ["ask", TEST, "Run login tests"]))
    out += [
        (approve_at, None, ["approve"]),
        (approve_at + 0.2, None, ["tool", "Bash", TEST]),
        (approve_at + 2.6, ev("PostToolUse", **tool("Bash", command=TEST)), ["result", "PASS  4 tests passed"]),
        (approve_at + 4.0, ev("Stop"), ["say", "修好了：表单现在会正常提交，测试全部通过。"]),
    ]
    return out, t + 0.1


# 用户刷视频没注意到，过了一阵子才点气泡回到终端、选“允许”。她在“等你确认”里待满冷却时间才可能做小动作
APPROVE_AT = 118.0
AFTER = 30.0  # 允许之后再模拟多久


def durations() -> dict[str, float]:
    m = json.loads((ASSETS / "manifest.json").read_text(encoding="utf-8"))
    return {c["id"]: Image.open(ASSETS / c["file"]).n_frames / FPS for c in m["clips"]}


class TimedPlayer:
    """按片段长度计时的播放器：片段播完由时钟触发，和真实播放器一样回调引擎。"""

    def __init__(self, clock: FakeScheduler, dur: dict[str, float]) -> None:
        self.clock, self.dur = clock, dur
        self.on_clip_start = lambda _c: None
        self.on_stall = lambda: None
        self.next = None
        self.playing = None
        self.rate = 1.0
        self.timer = None
        self.started = 0.0  # 当前段开始的时刻（毫秒）
        self.pos = 0.0  # 速度变化前已经播到的片段内时间（秒）
        self.log: list[dict] = []

    def set_next(self, c) -> None:
        self.next = c
        if self.playing is None and c:
            self._start_next()

    def crossfade_to(self, c) -> None:
        self.next = None
        self._begin(c, xfade=True)

    def set_rate(self, r: float) -> None:
        if self.playing is not None:
            self.pos += (self.clock.now() - self.started) / 1000 * self.rate
            self.started = self.clock.now()
        self.rate = r
        if self.log:
            self.log[-1]["rates"].append([round(self.clock.now() / 1000, 4), r])
        self._schedule()

    def _schedule(self) -> None:
        if self.timer is not None:
            self.clock.cancel(self.timer)
        if self.playing is None:
            return
        left = max(0.0, self.dur[self.playing.id] - self.pos) / self.rate
        self.timer = self.clock.call_later(left * 1000, self._finish)

    def _finish(self) -> None:
        self.timer = None
        if self.next:
            self._start_next()
            return
        self.playing = None
        self.on_stall()

    def _start_next(self) -> None:
        c, self.next = self.next, None
        self._begin(c)

    def _begin(self, c, xfade: bool = False) -> None:
        self.playing, self.started, self.pos = c, self.clock.now(), 0.0
        self.log.append({"t": round(self.clock.now() / 1000, 4), "clip": c.id, "xfade": xfade,
                         "rates": [[round(self.clock.now() / 1000, 4), self.rate]]})
        self.on_clip_start(c)
        self._schedule()


def run(seed: int, approve_at: float = APPROVE_AT) -> tuple[list[dict], list, float, float]:
    story, ask_at = build(approve_at)
    end = approve_at + AFTER
    random.seed(seed)
    dur = durations()
    clock = FakeScheduler()
    seq = iter(range(1, 10**6))
    next_seq = lambda: next(seq)  # noqa: E731
    player = TimedPlayer(clock, dur)
    holder: dict = {}
    targets = TargetHub(next_seq, lambda t: holder["engine"].set_target(t) if "engine" in holder else None,
                        lambda s: sessions.ack(s))
    sessions = SessionStore(DEFAULT_CONFIG["state"], next_seq, targets.set_auto, clock, lambda _m: None)
    engine = Engine(Graph(Manifest.load(ASSETS / "manifest.json")), player, DEFAULT_CONFIG["animation"],
                    on_ack=targets.ack, on_status=lambda _s: None, initial=targets.current(), clock=clock,
                    random=random.random)
    holder["engine"] = engine
    engine.start()
    t = 0.0
    events = list(story)
    while t < end:
        while events and events[0][0] <= t + 1e-9:
            e = events.pop(0)[1]
            if e:
                sessions.handle(e)
        t = round(t + 0.05, 4)
        clock.advance(50)
        if abs(t - round(t)) < 1e-9:
            sessions.sweep()
    return player.log, story, ask_at, end


def main() -> None:
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    approve = float(sys.argv[2]) if len(sys.argv) > 2 else APPROVE_AT
    log, story, ask_at, end = run(seed, approve)
    for e in log:
        print(f"{e['t']:6.2f}  {e['clip']:28s} {'交叉淡化' if e['xfade'] else ''} 速度 {e['rates'][-1][1]:.3f}")
    ui = [{"t": round(t, 3), "line": line} for t, _e, line in story if line]
    OUT.write_text(json.dumps({"seed": seed, "end": end, "askAt": round(ask_at, 3), "approveAt": approve,
                               "clips": log, "ui": ui}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"写入 {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
