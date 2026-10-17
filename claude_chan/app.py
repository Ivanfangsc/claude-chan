"""入口：把会话汇总、动画引擎、窗口、托盘、HTTP 服务和调试面板连起来。

    uv run claude-chan            # 或 python -m claude_chan
    uv run claude-chan --debug    # 同时打开调试面板
"""

from __future__ import annotations

import itertools
import json
import sys
import time
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QIcon, QImage
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication

from . import __version__, logfile
from .config import config_path, data_dir, load_config
from .debug import DebugActions, DebugWindow
from .engine.engine import Engine
from .engine.graph import Graph
from .engine.manifest import Manifest, validate_manifest
from . import profile
from .engine.player import FramePlayer
from .follower import Follower
from .fullscreen import fullscreen_over
from .model import DisplayTarget, EngineStatus
from .server import HookServer
from .state.sessions import SessionStore
from .state.target import TargetHub
from .tray import PetTray
from .updates import UpdateChecker
from .window import PetWindow, build_hit_grid

INSTANCE_KEY = "claude-chan-pet"


class QtScheduler:
    """Scheduler 接口的 Qt 实现：一次性定时器，可取消。时间单位毫秒。"""

    def __init__(self) -> None:
        self._timers: set[QTimer] = set()

    def now(self) -> float:
        return time.monotonic() * 1000

    def call_later(self, ms: float, fn: Callable[[], None]) -> QTimer:
        timer = QTimer(singleShot=True)
        self._timers.add(timer)

        def fire() -> None:
            self._timers.discard(timer)
            fn()

        timer.timeout.connect(fire)
        timer.start(max(0, round(ms)))
        return timer

    def cancel(self, handle: Any) -> None:
        if isinstance(handle, QTimer):
            handle.stop()
            self._timers.discard(handle)


# 形象（皮肤）：名字 → (显示名, resources 下的素材目录)。素材目录里有 manifest.json 的才能选
SKINS = {"adult": ("原版", "assets"), "chibi": ("Q 版", "assets-chibi")}


def resource_root() -> Path:
    """仓库根目录；打包后是解压目录。"""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[1]


class PetApp:
    def __init__(self, app: QApplication, open_debug: bool) -> None:
        self.app = app
        self.config, config_error = load_config()
        self.clock = QtScheduler()
        self.log_lines: list[str] = []
        profile.set_logger(self.log)
        self.debug: DebugWindow | None = None
        self.engine_status: EngineStatus | None = None
        root = resource_root()
        if config_error:
            self.log(config_error)
        self._app_state_file = data_dir() / "app-state.json"
        saved = self._load_app_state().get("skin", "adult")
        self.skin = saved if saved in self.available_skins() else "adult"
        self.assets, self.manifest = self._load_skin(self.skin)
        self._grids: dict[str, list[list[bool]] | None] = {}  # 各形象的点击区域，启动时算好，切换时不卡

        seq = itertools.count(1)
        next_seq = lambda: next(seq)  # noqa: E731
        self._next_seq = next_seq
        self.targets = TargetHub(next_seq, self._on_target, lambda s: self.sessions.ack(s))
        self.sessions = SessionStore(self.config["state"], next_seq, self._on_auto_target, self.clock, self.log)

        self.player = FramePlayer(self.assets, self.manifest.fps, self.config["animation"], self.log)
        self.window = PetWindow(
            self.player,
            self._placeholder(self.assets, self.manifest),
            self._grid(self.skin),
            self.config["window"]["widthFraction"],
            on_state_change=lambda: self.tray.refresh() if hasattr(self, "tray") else None,
            on_menu=lambda pos: self.tray.popup(pos),
            on_open_debug=self.open_debug,
        )
        self.window.set_sway(self.config["animation"]["swayDegrees"], self.config["animation"]["swayPeriodMs"])
        self.engine = self._make_engine()
        self.follower = Follower(self.window, self.config["window"].get("followProcesses", ["claude.exe"]), self.log)
        self.tray = PetTray(
            QIcon(str(root / "resources" / "icon.png")),
            self.window,
            open_debug=self.open_debug,
            reload_config=self.reload_config,
            open_config_folder=lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(config_path().parent))),
            quit_app=self.quit,
            skins=[(name, SKINS[name][0]) for name in self.available_skins()],
            current_skin=lambda: self.skin,
            switch_skin=self.switch_skin,
            follow=(lambda: self.follower.enabled, self.follower.set_enabled) if self.follower.available else None,
            version=__version__,
        )

        updates = self.config.get("updates", {})
        self.updates = UpdateChecker(updates.get("repo", "Ivanfangsc/claude-chan"), __version__, self.log)
        self.updates.available.connect(self.tray.show_update)
        if updates.get("check", True):
            self.updates.start()

        self.server = HookServer(self.config["server"]["host"], self.config["server"]["port"], self.snapshot)
        self.server.event_received.connect(self.sessions.handle)
        self.server.message.connect(self.log)
        self.server.start()

        self.sweeper = QTimer(interval=1000)
        self.sweeper.timeout.connect(self.sessions.sweep)
        self.sweeper.timeout.connect(self._check_fullscreen)
        self.sweeper.timeout.connect(self.follower.poll)
        self.sweeper.start()
        self._fullscreen_hidden = False
        self.sessions.sweep()

        self.window.show()
        self.engine.start()
        if open_debug:
            self.open_debug()

    # ---------- 形象 ----------

    def available_skins(self) -> list[str]:
        return [name for name in SKINS if (self._skin_dir(name) / "manifest.json").exists()]

    def _skin_dir(self, name: str) -> Path:
        if name == "adult" and self.config["assetsDir"]:
            return Path(self.config["assetsDir"])
        return resource_root() / "resources" / SKINS[name][1]

    def _load_skin(self, name: str) -> tuple[Path, Manifest]:
        assets = self._skin_dir(name)
        manifest = Manifest.load(assets / "manifest.json")
        for problem in validate_manifest(manifest):
            self.log(f"manifest（{SKINS[name][0]}）：{problem}")
        return assets, manifest

    def _placeholder(self, assets: Path, manifest: Manifest) -> QImage | None:
        kf = manifest.states["idle"].keyframe
        return QImage(str(assets / kf)) if kf else None

    def _hit_grid(self, assets: Path, manifest: Manifest, extra: list[Path] | None = None) -> list[list[bool]] | None:
        if not self.config["window"]["hitTest"]:
            return None
        images = [assets / k for k in manifest.keyframes()]
        # export_frames.py 生成的所有片段所有帧的并集；没有时只用关键帧（动作大的随机事件可能被裁掉）
        if (assets / "hitmask.png").exists():
            images.append(assets / "hitmask.png")
        return build_hit_grid(images + (extra or []), self.log)

    def _grid(self, name: str) -> list[list[bool]] | None:
        if name not in self._grids:
            assets, manifest = (self.assets, self.manifest) if name == self.skin else self._load_skin(name)
            self._grids[name] = self._hit_grid(assets, manifest)
        return self._grids[name]

    def _make_engine(self) -> Engine:
        return Engine(
            Graph(self.manifest),
            self.player,
            self.config["animation"],
            on_ack=self.targets.ack,
            on_status=self._on_engine_status,
            initial=self._shown(self.targets.current()),
            clock=self.clock,
        )

    def _load_app_state(self) -> dict[str, Any]:
        try:
            return json.loads(self._app_state_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _save_app_state(self) -> None:
        try:
            self._app_state_file.parent.mkdir(parents=True, exist_ok=True)
            self._app_state_file.write_text(json.dumps({"skin": self.skin}), encoding="utf-8")
        except OSError as e:
            self.log(f"保存形象选择失败：{e}")

    def switch_skin(self, name: str) -> None:
        """切换形象：立即换成新形象的素材和引擎，交叉淡化到新形象的 idle loop，再照常走向当前的目标状态。
        （以前先回到 idle、等这一轮播完再播变身动画，点一下要等十几秒，去掉了。）"""
        if name == self.skin or name not in self.available_skins():
            return
        self.log(f"切换形象：{SKINS[self.skin][0]} → {SKINS[name][0]}")
        self.engine.dispose()
        self.assets, self.manifest = self._load_skin(name)
        self.skin = name
        self._save_app_state()
        self.player.set_assets(self.assets)
        self.window.set_skin(self._placeholder(self.assets, self.manifest), self._grid(name))
        self.engine = self._make_engine()  # 接管播放器的回调
        idle = next((c for c in self.manifest.clips if c.type == "loop" and c.state == "idle"), None)
        if idle:
            self.player.crossfade_to(idle)  # 新引擎从这段 idle loop 出发规划
        else:
            self.engine.start()
        self.log(f"已切换到{SKINS[name][0]}")
        if hasattr(self, "tray"):
            self.tray.refresh()

    # ---------- 全屏时让开 ----------

    def _check_fullscreen(self) -> None:
        """同一屏幕上有全屏窗口时自动隐藏（隐藏时播放器暂停），退出全屏后回来。
        只收回自己藏起来的：用户在这期间自己点了显示或隐藏，就按用户的来。"""
        if not self.config["window"].get("hideInFullscreen", True):
            return
        if self.follower.attached:
            # 贴着 Claude 窗口时层级跟着宿主，全屏窗口自然会盖住她；之前因全屏藏起来的，交给跟随去管
            self._fullscreen_hidden = False
            return
        if getattr(self.window, "user_toggled", False):
            self.window.user_toggled = False
            self._fullscreen_hidden = False
            return
        if self._fullscreen_hidden:
            if not fullscreen_over(int(self.window.winId())):
                self._fullscreen_hidden = False
                self.window.show()
                self.log("全屏窗口已退出，桌宠回来了")
        elif self.window.isVisible() and fullscreen_over(int(self.window.winId())):
            self._fullscreen_hidden = True
            self.window.hide()
            self.log("检测到全屏窗口，桌宠先隐藏")

    # ---------- 目标与状态 ----------

    def _shown(self, t: DisplayTarget) -> DisplayTarget:
        """素材里没有的状态（比如某个形象还没做 waiting）按 idle 显示。"""
        return t if t.state in self.manifest.states else replace(t, state="idle")

    def _on_auto_target(self, t: DisplayTarget) -> None:
        self.targets.set_auto(t)
        self._refresh_debug()

    def _on_target(self, t: DisplayTarget) -> None:
        who = f"（{t.project}）" if t.project and not t.manual else ""
        self.log(f"目标 → {t.state}{who}{'［常驻］' if t.sticky else ''}{'［手动］' if t.manual else ''} #{t.seq}")
        t = self._shown(t)
        if hasattr(self, "engine"):
            self.engine.set_target(t)
        if hasattr(self, "window"):
            self.window.set_target(t)
        if hasattr(self, "tray"):
            self.tray.show_target(t)

    def _on_engine_status(self, s: EngineStatus) -> None:
        self.engine_status = s
        self._refresh_debug()

    def snapshot(self) -> dict[str, Any]:
        """GET /state 的内容（在 HTTP 线程里调用，只读）。"""
        return {
            "target": asdict(self.targets.current()),
            "manual": self.targets.is_manual(),
            "engine": asdict(self.engine_status) if self.engine_status else None,
            "sessions": [asdict(s) for s in self.sessions.list()],
            "log": self.log_lines[-200:],
        }

    # ---------- 日志与调试面板 ----------

    def log(self, msg: str) -> None:
        line = f"{time.strftime('%H:%M:%S')} {msg}"
        self.log_lines.append(line)
        del self.log_lines[:-200]
        print(line, flush=True)
        logfile.write(msg)
        if self.debug:
            self.debug.append_log(line)

    def open_debug(self) -> None:
        if self.debug is None:
            groups = sorted({c.group or "fidget" for c in self.manifest.clips if c.type == "event"})
            self.debug = DebugWindow(
                list(self.manifest.states),
                groups,
                self.config["animation"],
                DebugActions(
                    force=self.targets.force,
                    auto=self.targets.clear_manual,
                    set_rate=self._set_rate,
                    events=lambda: self.engine.events(),
                    request_event=self._request_event,
                    set_anim=self._set_anim,
                    remove_session=lambda sid: (self.sessions.remove(sid), self._refresh_debug()),
                ),
            )
            for line in self.log_lines:
                self.debug.append_log(line)
        self._refresh_debug()
        self.debug.show()
        self.debug.raise_()
        self.debug.activateWindow()

    def _refresh_debug(self) -> None:
        if not self.debug or not self.debug.isVisible():
            return
        target = self.targets.current()
        self.debug.update_status(target, self.targets.is_manual(), self.engine_status)
        self.debug.update_sessions(self.sessions.list(), None if target.manual else target.session_id)

    def _request_event(self, clip_id: str) -> bool:
        ok = self.engine.request_event(clip_id)
        self.log(f"调试：下一轮播放 {clip_id}" if ok else f"调试：{clip_id} 不属于当前目标状态")
        return ok

    def _set_anim(self, key: str, value) -> None:
        anim = self.config["animation"]
        anim[key] = value
        self.player.set_config(anim)
        self.engine.set_config(anim)
        self.window.set_sway(anim["swayDegrees"], anim["swayPeriodMs"])

    def _set_rate(self, rate: float) -> None:
        self.config["animation"]["basePlaybackRate"] = rate
        self.engine.set_config(self.config["animation"])

    # ---------- 托盘操作 ----------

    def reload_config(self) -> None:
        config, error = load_config()
        if error:
            self.log(error)
            return
        server_changed = config["server"] != self.config["server"]
        self.config = config
        self.sessions.set_config(config["state"])
        self.player.set_config(config["animation"])
        self.engine.set_config(config["animation"])
        self.window.set_sway(config["animation"]["swayDegrees"], config["animation"]["swayPeriodMs"])
        self.window.set_hit_test(config["window"]["hitTest"])
        self.log(f"已重新加载配置：{config_path()}{'（server 的修改需要重启桌宠才生效）' if server_changed else ''}")

    def quit(self) -> None:
        self.log("退出")
        self.window.prepare_quit()
        self.server.stop()
        self.tray.hide()
        self.app.quit()


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("claude-chan")
    app.setApplicationVersion(__version__)
    app.setQuitOnLastWindowClosed(False)  # 桌宠窗口关闭时只是隐藏到托盘

    # 只运行一个实例：再次启动时通知已有的实例显示桌宠并打开调试面板
    probe = QLocalSocket()
    probe.connectToServer(INSTANCE_KEY)
    if probe.waitForConnected(300):
        probe.write(b"show")
        probe.waitForBytesWritten(300)
        return
    logfile.setup(data_dir() / "log.txt")
    logfile.write(f"===== 启动 Claude-Chan v{__version__} =====")
    QLocalServer.removeServer(INSTANCE_KEY)
    instance = QLocalServer()
    instance.listen(INSTANCE_KEY)

    pet = PetApp(app, open_debug="--debug" in sys.argv)

    def on_second_instance() -> None:
        conn = instance.nextPendingConnection()
        if conn:
            conn.close()
        pet.window.show()
        pet.open_debug()

    instance.newConnection.connect(on_second_instance)
    sys.exit(app.exec())
