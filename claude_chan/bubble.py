"""等你确认时她头顶的气泡：一个独立的小窗口（不受她窗口大小的限制），挂在她的窗口上（Qt 的 owner），
始终在她上面一层。

排版（从上到下）：标题行（项目标签 + 等你确认 / 想问你……，后面跟会话标题）、Claude 的一句话、
等宽小字的具体内容（文件和改动行数、网址、命令）、问题的选项、底部“另外 N 个会话也在等你”。
字太多时：宽度固定（跟她的大小一起缩放），一句话最多两行，等宽内容一行、省略中间，选项最多两行、
放不下的显示成“+N”。鼠标悬停时展开显示全文；点击发出 clicked（由 PetApp 跳回对应的会话）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

from PySide6.QtCore import QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QGuiApplication, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

BG = QColor("#fffdf9")
BORDER = QColor("#e2d8c8")
TAG_BG = QColor("#fae2d6")
TAG_FG = QColor("#8a3a1e")
HEAD = QColor("#8a8279")
MAIN = QColor("#2b2622")
DETAIL_BG = QColor("#f3eee6")
DETAIL_FG = QColor("#5f574f")
ADD = QColor("#3f8a4a")
DEL = QColor("#c04a3a")
CHIP = QColor("#d9cfbf")

# Claude 的话不如工具自带的说明有用时（只是泛泛一句），以这些开头的不作为补充显示
_CJK = re.compile(r"[一-鿿]")
GENERIC = ("想运行一条命令", "想修改文件", "想写入文件", "想修改笔记本", "想打开网页", "想上网搜索", "想用 ")


@dataclass
class BubbleContent:
    tag: str  # 项目名
    verb: str  # 等你确认 / 想问你 / 计划写好了 …
    title: str | None  # 会话标题（桌面版侧边栏标题，或 CLI 会话里问的第一句话）
    main: str  # 主体的一句话
    detail: str | None  # 等宽小字
    options: tuple[str, ...]
    others: int


def content_of(target, title: str | None, show_commands: bool) -> BubbleContent | None:  # noqa: ANN001
    ask = target.ask
    if ask is None:
        return None
    asks_user = ask.verb in ("想问你", "计划写好了", "等你填写", "等你回复")
    say = ask.say
    # 会话是中文的（看标题），Claude 这句却是英文的（干活时的过程说明常常是英文）：不用它，免得气泡里中英混杂
    if say and title and _CJK.search(title) and not _CJK.search(say):
        say = None
    ask = replace(ask, say=say)
    if asks_user or not ask.say:
        main = ask.text or ask.say or ask.verb
        detail = ask.detail or (ask.command if show_commands else None)
    else:
        main = ask.say
        extra = ask.text if ask.text and not ask.text.startswith(GENERIC) else None
        detail = ask.detail or (ask.command if show_commands else extra)
    return BubbleContent(target.project or "", ask.verb, title, main, detail, tuple(ask.options), target.others_waiting)


def _wrap(text: str, fm: QFontMetricsF, width: float, max_lines: int) -> list[str]:
    """按宽度折行（中文逐字、英文尽量在空格处断开），超过 max_lines 时最后一行末尾加“…”。"""
    lines: list[str] = []
    cur = ""
    for token in re.findall(r"[A-Za-z0-9_./\-]+|\s+|.", text):
        if fm.horizontalAdvance(cur + token) <= width:
            cur += token
            continue
        if cur.strip():
            lines.append(cur.rstrip())
        cur = token.lstrip()
        while fm.horizontalAdvance(cur) > width:  # 一个词比整行还长：硬断开
            k = len(cur)
            while k > 1 and fm.horizontalAdvance(cur[:k]) > width:
                k -= 1
            lines.append(cur[:k])
            cur = cur[k:]
    if cur.strip():
        lines.append(cur.rstrip())
    if len(lines) > max_lines:
        last = lines[max_lines - 1]
        while last and fm.horizontalAdvance(last + "…") > width:
            last = last[:-1]
        lines = lines[: max_lines - 1] + [last + "…"]
    return lines


class Bubble(QWidget):
    clicked = Signal()

    def __init__(self, owner: QWidget) -> None:
        super().__init__(owner, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._owner = owner
        self._content: BubbleContent | None = None
        self._expanded = False
        self._scale = 1.0
        self._tail = "down"  # 尾巴指向：down（她在下面）/ left / right
        self._layout: dict | None = None
        # 她移动、缩放时跟着走
        self._follow = QTimer(self, interval=150)
        self._follow.timeout.connect(self._place)

    # ---------- 对外 ----------

    def show_content(self, content: BubbleContent | None) -> None:
        if content is None or not self._owner.isVisible():
            self._content = None
            self._follow.stop()
            self.hide()
            return
        changed = content != self._content
        self._content = content
        if changed:
            self._expanded = False
        self._relayout()
        if not self.isVisible():
            self.show()
        self._follow.start()

    # ---------- 排版 ----------

    def _fonts(self) -> tuple[QFont, QFont, QFont]:
        s = self._scale
        head = QFont("Microsoft YaHei UI")
        head.setPixelSize(max(11, round(12 * s)))
        main = QFont("Microsoft YaHei UI")
        main.setPixelSize(max(12, round(14.5 * s)))
        mono = QFont("Consolas")
        mono.setPixelSize(max(11, round(12.5 * s)))
        return head, main, mono

    def _relayout(self) -> None:
        c = self._content
        if c is None:
            return
        self._scale = max(0.85, min(1.35, self._owner.width() / 360))
        s = self._scale
        width = round(300 * s)
        pad = 12 * s
        inner = width - pad * 2
        head_f, main_f, mono_f = self._fonts()
        hfm, mfm, cfm = QFontMetricsF(head_f), QFontMetricsF(main_f), QFontMetricsF(mono_f)
        y = pad
        lay: dict = {"width": width, "pad": pad, "fonts": (head_f, main_f, mono_f)}
        # 标题行
        tag_w = hfm.horizontalAdvance(c.tag) + 14 * s if c.tag else 0
        head_text = c.verb + (f" · {c.title}" if c.title else "")
        head_text = hfm.elidedText(head_text, Qt.TextElideMode.ElideRight, inner - tag_w - 6 * s)
        lay["head"] = (y, hfm.height() + 4 * s, tag_w, head_text)
        y += hfm.height() + 4 * s + 6 * s
        # 主体
        main_lines = _wrap(c.main, mfm, inner, 8 if self._expanded else 2)
        lay["main"] = (y, mfm.height() * 1.35, main_lines)
        y += len(main_lines) * mfm.height() * 1.35
        # 等宽内容
        if c.detail:
            y += 6 * s
            # 有中文的内容（“等 4 个文件”）用正常字体，等宽字体给中文留的间距太宽
            if re.search(r"[　-鿿]", c.detail):
                mono_f = head_f
                cfm = hfm
                lay["fonts"] = (head_f, main_f, head_f)
            if self._expanded:
                det = _wrap(c.detail, cfm, inner - 16 * s, 6)
            else:
                det = [cfm.elidedText(c.detail, Qt.TextElideMode.ElideMiddle, inner - 16 * s)]
            h = len(det) * cfm.height() * 1.3 + 8 * s
            lay["detail"] = (y, h, det)
            y += h
        # 选项
        if c.options:
            y += 8 * s
            rows: list[list[str]] = [[]]
            x = 0.0
            chip_h = hfm.height() + 6 * s
            opts = list(c.options)
            max_rows = 4 if self._expanded else 2
            for k, o in enumerate(opts):
                w = hfm.horizontalAdvance(o) + 20 * s
                if x + w > inner and rows[-1]:
                    if len(rows) == max_rows:
                        rest = len(opts) - k
                        rows[-1].append(f"+{rest}")
                        break
                    rows.append([])
                    x = 0.0
                rows[-1].append(o)
                x += w + 6 * s
            lay["chips"] = (y, chip_h, rows)
            y += len(rows) * (chip_h + 6 * s) - 6 * s
        # 另外几个会话
        if c.others:
            y += 6 * s
            lay["others"] = (y, hfm.height(), f"另外 {c.others} 个会话也在等你")
            y += hfm.height()
        y += pad
        lay["height"] = round(y)
        self._layout = lay
        self._place()
        self.update()

    def _place(self) -> None:
        if not self._layout:
            return
        if not self._owner.isVisible():
            self.hide()
            return
        tail = round(9 * self._scale)
        w, h = self._layout["width"], self._layout["height"]
        g = self._owner.frameGeometry()
        screen = (self._owner.screen() or QGuiApplication.primaryScreen()).availableGeometry()
        head_y = g.top() + round(g.height() * 0.1)  # 她头顶大约在窗口上方 10% 处
        x = g.center().x() - w // 2
        y = head_y - h - tail
        self._tail = "down"
        if y < screen.top():  # 上面放不下：放到侧面，和头顶平齐
            y = max(screen.top(), head_y - h // 3)
            if g.left() - w - tail >= screen.left():
                x, self._tail = g.left() - w - tail + round(g.width() * 0.12), "right"
            else:
                x, self._tail = g.right() + tail - round(g.width() * 0.12), "left"
        x = max(screen.left(), min(screen.right() - w - tail, x))
        full_w = w + (tail if self._tail in ("left", "right") else 0)
        full_h = h + (tail if self._tail == "down" else 0)
        ox = tail if self._tail == "left" else 0
        if self._tail == "left":
            x -= tail
        self._box = QRectF(ox + 0.5, 0.5, w - 1, h - 1)
        self._tail_x = g.center().x() - x
        geo = QRect(x, y, full_w, full_h)
        if self.geometry() != geo:
            self.setGeometry(geo)

    # ---------- 绘制 ----------

    def paintEvent(self, _event) -> None:  # noqa: N802
        lay, c = self._layout, self._content
        if not lay or not c:
            return
        s = self._scale
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        box = self._box
        path = QPainterPath()
        path.addRoundedRect(box, 12 * s, 12 * s)
        t = 9 * s
        if self._tail == "down":
            cx = max(box.left() + 20 * s, min(box.right() - 20 * s, self._tail_x))
            tri = QPainterPath()
            tri.moveTo(cx - t, box.bottom() - 1)
            tri.lineTo(cx, box.bottom() + t)
            tri.lineTo(cx + t, box.bottom() - 1)
            path = path.united(tri)
        elif self._tail in ("left", "right"):
            ty = box.top() + 28 * s
            tri = QPainterPath()
            if self._tail == "right":
                tri.moveTo(box.right() - 1, ty - t); tri.lineTo(box.right() + t, ty); tri.lineTo(box.right() - 1, ty + t)
            else:
                tri.moveTo(box.left() + 1, ty - t); tri.lineTo(box.left() - t, ty); tri.lineTo(box.left() + 1, ty + t)
            path = path.united(tri)
        p.fillPath(path, BG)
        p.setPen(QPen(BORDER, 1))
        p.drawPath(path)

        head_f, main_f, mono_f = lay["fonts"]
        pad = lay["pad"]
        left = box.left() + pad
        inner = box.width() - pad * 2
        # 标题行
        y, h, tag_w, head_text = lay["head"]
        p.setFont(head_f)
        if c.tag:
            r = QRectF(left, y, tag_w, h)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(TAG_BG)
            p.drawRoundedRect(r, 6 * s, 6 * s)
            p.setPen(TAG_FG)
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, c.tag)
        p.setPen(HEAD)
        p.drawText(QRectF(left + tag_w + 6 * s, y, inner - tag_w, h), Qt.AlignmentFlag.AlignVCenter, head_text)
        # 主体
        y, lh, lines = lay["main"]
        p.setFont(main_f)
        p.setPen(MAIN)
        for k, ln in enumerate(lines):
            p.drawText(QRectF(left, y + k * lh, inner, lh), Qt.AlignmentFlag.AlignVCenter, ln)
        # 等宽内容
        if "detail" in lay:
            y, h, det = lay["detail"]
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(DETAIL_BG)
            p.drawRoundedRect(QRectF(left, y, inner, h), 6 * s, 6 * s)
            p.setFont(mono_f)
            fm = QFontMetricsF(mono_f)
            lh = fm.height() * 1.3
            for k, ln in enumerate(det):
                rect = QRectF(left + 8 * s, y + 4 * s + k * lh, inner - 16 * s, lh)
                m = re.search(r"\+(\d+) −(\d+)$", ln)
                if m:  # 改动行数：加的绿色、删的红色
                    head = ln[: m.start()]
                    p.setPen(DETAIL_FG)
                    p.drawText(rect, Qt.AlignmentFlag.AlignVCenter, head)
                    x = rect.left() + fm.horizontalAdvance(head)
                    p.setPen(ADD)
                    p.drawText(QRectF(x, rect.top(), 200, lh), Qt.AlignmentFlag.AlignVCenter, f"+{m.group(1)}")
                    x += fm.horizontalAdvance(f"+{m.group(1)} ")
                    p.setPen(DEL)
                    p.drawText(QRectF(x, rect.top(), 200, lh), Qt.AlignmentFlag.AlignVCenter, f"−{m.group(2)}")
                else:
                    p.setPen(DETAIL_FG)
                    p.drawText(rect, Qt.AlignmentFlag.AlignVCenter, ln)
        # 选项
        if "chips" in lay:
            y, ch, rows = lay["chips"]
            p.setFont(head_f)
            fm = QFontMetricsF(head_f)
            for r_i, row in enumerate(rows):
                x = left
                for o in row:
                    w = fm.horizontalAdvance(o) + 20 * s
                    rect = QRectF(x, y + r_i * (ch + 6 * s), w, ch)
                    p.setPen(QPen(CHIP, 1))
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    p.drawRoundedRect(rect, ch / 2, ch / 2)
                    p.setPen(MAIN)
                    p.drawText(rect, Qt.AlignmentFlag.AlignCenter, o)
                    x += w + 6 * s
        if "others" in lay:
            y, h, txt = lay["others"]
            p.setFont(head_f)
            p.setPen(HEAD)
            p.drawText(QRectF(left, y, inner, h), Qt.AlignmentFlag.AlignVCenter, txt)
        p.end()

    # ---------- 鼠标 ----------

    def enterEvent(self, _event) -> None:  # noqa: N802
        if not self._expanded:
            self._expanded = True
            self._relayout()

    def leaveEvent(self, _event) -> None:  # noqa: N802
        if self._expanded:
            self._expanded = False
            self._relayout()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
