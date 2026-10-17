"""调试面板：会话、引擎状态、手动切换目标、播放速度、全状态巡检、随机事件（手动触发、开关）、摇晃等动画参数、日志。"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSlider,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .model import DisplayTarget, EngineStatus, EventInfo, SessionView

SOURCE = {"wsl": "WSL", "windows": "Win"}
GROUP_LABEL = {"blink": "眨眼", "fidget": "其他随机事件"}


def euler_tour(nodes: list[str]) -> list[str]:
    """完全有向图上的欧拉回路：相邻两项恰好覆盖所有有序对 (a, b)，a ≠ b，用来巡检所有切换。"""
    if len(nodes) < 2:
        return list(nodes)
    out = {n: [m for m in nodes if m != n] for n in nodes}
    stack, path = [nodes[0]], []
    while stack:
        v = stack[-1]
        if out[v]:
            stack.append(out[v].pop(0))
        else:
            path.append(stack.pop())
    return path[::-1]


@dataclass
class DebugActions:
    force: Callable[[str, bool], None]
    auto: Callable[[], None]
    set_rate: Callable[[float], None]
    events: Callable[[], list[EventInfo]]  # 当前目标状态的随机事件
    request_event: Callable[[str], bool]  # 下一轮播放指定事件
    set_anim: Callable[[str, Any], None]  # 修改 config["animation"] 里的一项（只在本次运行有效）
    remove_session: Callable[[str], None] = lambda _sid: None  # 手动移除会话


class DebugWindow(QWidget):
    def __init__(self, states: list[str], groups: list[str], anim: dict[str, Any], actions: DebugActions) -> None:
        super().__init__()
        self.setWindowTitle("Claude-Chan 调试面板")
        self.resize(980, 820)
        self._actions = actions
        self._states = states
        self._tour: list[str] = []
        self._tour_index = 0
        self._engine: EngineStatus | None = None
        self._target: DisplayTarget | None = None

        root = QVBoxLayout(self)

        box = QGroupBox("显示")
        self._summary = QFormLayout(box)
        self._fields = {k: QLabel("—") for k in ("目标", "引擎节点", "当前片段", "下一段", "已到达目标", "播放速度")}
        for k, v in self._fields.items():
            v.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self._summary.addRow(k, v)
        root.addWidget(box)

        box = QGroupBox("会话")
        layout = QVBoxLayout(box)
        self._table = QTableWidget(0, 10)
        self._table.setHorizontalHeaderLabels(["会话", "来源", "项目", "显示", "基础状态", "待播", "后台任务", "最近事件", "距今", ""])
        self._table.verticalHeader().hide()
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setMaximumHeight(160)
        layout.addWidget(self._table)
        root.addWidget(box)

        box = QGroupBox("手动切换目标")
        layout = QVBoxLayout(box)
        row = QHBoxLayout()
        self._buttons: dict[str, QPushButton] = {}
        for s in states:
            b = QPushButton(s)
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, s=s: actions.force(s, self._sticky.isChecked()))
            row.addWidget(b)
            self._buttons[s] = b
        layout.addLayout(row)
        row = QHBoxLayout()
        self._sticky = QCheckBox("一次性状态常驻（不自动回到 idle）")
        row.addWidget(self._sticky)
        auto = QPushButton("恢复自动")
        auto.clicked.connect(actions.auto)
        row.addWidget(auto)
        row.addStretch()
        layout.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(QLabel("播放速度"))
        self._rate = QSlider(Qt.Orientation.Horizontal)
        self._rate.setRange(2, 16)  # ×0.25
        self._rate.setValue(4)
        self._rate_label = QLabel("1×")
        self._rate.valueChanged.connect(self._rate_changed)
        row.addWidget(self._rate)
        row.addWidget(self._rate_label)
        layout.addLayout(row)
        row = QHBoxLayout()
        self._tour_button = QPushButton("全状态两两切换巡检")
        self._tour_button.clicked.connect(self._toggle_tour)
        self._tour_label = QLabel("")
        row.addWidget(self._tour_button)
        row.addWidget(self._tour_label)
        row.addStretch()
        layout.addLayout(row)
        root.addWidget(box)

        root.addWidget(self._build_events(groups, anim))
        root.addWidget(self._build_motion(anim))

        box = QGroupBox("日志")
        layout = QVBoxLayout(box)
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(500)
        layout.addWidget(self._log)
        root.addWidget(box, stretch=1)

        self._tour_timer = QTimer(self, singleShot=True, interval=600)
        self._tour_timer.timeout.connect(self._tour_step)
        # 冷却倒计时随时间变化，单独定时刷新
        self._events_timer = QTimer(self, interval=500)
        self._events_timer.timeout.connect(self._refresh_events)
        self._events_timer.start()

    def _build_events(self, groups: list[str], anim: dict[str, Any]) -> QGroupBox:
        box = QGroupBox("随机事件（当前目标状态）")
        layout = QVBoxLayout(box)
        self._events = QTableWidget(0, 6)
        self._events.setHorizontalHeaderLabels(["事件", "组", "概率", "冷却", "剩余冷却", ""])
        self._events.verticalHeader().hide()
        self._events.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._events.setMaximumHeight(200)
        self._event_ids: list[str] = []
        layout.addWidget(self._events)
        row = QHBoxLayout()
        self._group_boxes: dict[str, QCheckBox] = {}
        disabled = anim.get("disabledEventGroups", [])
        for g in groups:
            c = QCheckBox(f"启用{GROUP_LABEL.get(g, g)}")
            c.setChecked(g not in disabled)
            c.toggled.connect(self._groups_changed)
            row.addWidget(c)
            self._group_boxes[g] = c
        row.addStretch()
        layout.addLayout(row)
        return box

    def _build_motion(self, anim: dict[str, Any]) -> QGroupBox:
        box = QGroupBox("动画参数（只在本次运行有效；要保留请写进 config.json）")
        form = QFormLayout(box)

        def slider(key: str, lo: int, hi: int, scale: float, fmt: Callable[[float], str]) -> QHBoxLayout:
            s = QSlider(Qt.Orientation.Horizontal)
            s.setRange(lo, hi)
            s.setValue(round(anim.get(key, 0) / scale))
            label = QLabel(fmt(s.value() * scale))
            label.setMinimumWidth(60)

            def changed(v: int) -> None:
                label.setText(fmt(v * scale))
                self._actions.set_anim(key, v * scale)

            s.valueChanged.connect(changed)
            row = QHBoxLayout()
            row.addWidget(s)
            row.addWidget(label)
            return row

        form.addRow("整体摇晃角度", slider("swayDegrees", 0, 30, 0.1, lambda v: f"{v:.1f}°"))
        form.addRow("摇晃周期", slider("swayPeriodMs", 4, 24, 500, lambda v: f"{v / 1000:.1f}s"))
        form.addRow("loop 速度浮动", slider("loopRateJitter", 0, 20, 0.01, lambda v: f"±{v:.0%}"))
        form.addRow("其他事件默认概率", slider("eventChance", 0, 20, 0.05, lambda v: f"{v:.0%}"))
        form.addRow("其他事件默认冷却", slider("eventCooldownMs", 0, 24, 5000, lambda v: f"{v / 1000:.0f}s"))
        return box

    # ---------- 数据更新 ----------

    def append_log(self, line: str) -> None:
        self._log.appendPlainText(line)

    def update_status(self, target: DisplayTarget, manual: bool, engine: EngineStatus | None) -> None:
        self._target, self._engine = target, engine
        who = f"（{target.project}）" if target.project and not manual else ""
        self._fields["目标"].setText(
            f"{target.state}{who}{'（常驻）' if target.sticky else ''} #{target.seq}{'［手动］' if manual else '［自动］'}"
        )
        if engine:
            self._fields["引擎节点"].setText(engine.node)
            self._fields["当前片段"].setText(engine.current or ("（停留在关键帧）" if engine.holding else "（停在末帧）"))
            self._fields["下一段"].setText(engine.next or "—")
            self._fields["已到达目标"].setText("是" if engine.at_target else "否")
            self._fields["播放速度"].setText(f"{engine.rate}×")
        for s, b in self._buttons.items():
            b.setChecked(s == target.state)
        self._maybe_advance_tour()

    def update_sessions(self, sessions: list[SessionView], shown_id: str | None) -> None:
        self._table.setRowCount(len(sessions))
        now = time.monotonic() * 1000
        for r, s in enumerate(sessions):
            ago = int((now - s.last_event_at) / 1000)
            cells = [s.id[:8], SOURCE.get(s.source, "?"), s.project, s.effective, s.base, s.latch or "—",
                     str(s.background) if s.background else "—", s.last_event,
                     f"{ago}s" if ago < 60 else f"{ago // 60}m{ago % 60}s"]
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if c == 2:
                    item.setToolTip(s.cwd)
                if c == 3 and s.id == shown_id:
                    item.setForeground(Qt.GlobalColor.darkRed)
                self._table.setItem(r, c, item)
            b = QPushButton("移除")
            b.setToolTip("从汇总里移除这个会话（比如回滚后残留的旧会话）；它再发事件会重新出现")
            b.clicked.connect(lambda _=False, sid=s.id: self._actions.remove_session(sid))
            self._table.setCellWidget(r, 9, b)

    def _refresh_events(self) -> None:
        if not self.isVisible():
            return
        events = self._actions.events()
        ids = [e.id for e in events]
        if ids != self._event_ids:
            self._event_ids = ids
            self._events.setRowCount(len(events))
            for r, e in enumerate(events):
                b = QPushButton("下一轮播放")
                b.clicked.connect(lambda _=False, i=e.id: self._actions.request_event(i))
                self._events.setCellWidget(r, 5, b)
        for r, e in enumerate(events):
            cells = [
                e.id,
                GROUP_LABEL.get(e.group, e.group),
                f"{e.chance:.0%}",
                f"{e.cooldown_ms / 1000:g}s",
                "已关闭" if e.disabled else (f"{e.remaining_ms / 1000:.0f}s" if e.remaining_ms else "就绪"),
            ]
            for c, text in enumerate(cells):
                self._events.setItem(r, c, QTableWidgetItem(text))
        self._events.resizeColumnsToContents()

    # ---------- 交互 ----------

    def _groups_changed(self) -> None:
        self._actions.set_anim("disabledEventGroups", [g for g, c in self._group_boxes.items() if not c.isChecked()])

    def _rate_changed(self, v: int) -> None:
        rate = v / 4
        self._rate_label.setText(f"{rate:g}×")
        self._actions.set_rate(rate)

    def _toggle_tour(self) -> None:
        if self._tour:
            self._tour = []
            self._tour_button.setText("全状态两两切换巡检")
            self._tour_label.setText("已停止")
            return
        self._tour = euler_tour(self._states)
        self._tour_index = 0
        self._tour_button.setText("停止巡检")
        self._tour_force()

    def _tour_force(self) -> None:
        s = self._tour[self._tour_index]
        self._tour_label.setText(f"{self._tour_index}/{len(self._tour) - 1}：→ {s}")
        self._actions.force(s, True)

    def _maybe_advance_tour(self) -> None:
        if not self._tour or self._tour_timer.isActive():
            return
        s = self._tour[self._tour_index]
        e, t = self._engine, self._target
        if t and t.state == s and e and e.at_target and e.target and e.target.state == s:
            self._tour_timer.start()  # 在目标上稍作停留，便于肉眼确认衔接

    def _tour_step(self) -> None:
        if not self._tour:
            return
        self._tour_index += 1
        if self._tour_index >= len(self._tour):
            self._tour_label.setText(f"完成：{len(self._tour) - 1} 次切换")
            self._tour = []
            self._tour_button.setText("全状态两两切换巡检")
            return
        self._tour_force()
