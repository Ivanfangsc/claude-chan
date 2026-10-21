"""用插件真实的气泡组件，渲染剧情里那次“等你确认”的气泡，存成透明 PNG 给宣传片用。

    uv run python promo-video/tools/bubble_png.py

内容走和桌宠一样的路径：PermissionRequest 事件 → describe() → content_of()；默认设置（不显示完整命令）。
按 2 倍像素渲染，镜头推近时也清楚。输出 promo-video/frames/bubble.png 和 bubble.json（尺寸、尾巴位置）。
"""

import json
import os
import sys
from dataclasses import replace
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")  # 离屏模式默认找不到系统字体
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtGui import QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from claude_chan.bubble import Bubble, content_of  # noqa: E402
from claude_chan.model import DisplayTarget  # noqa: E402
from claude_chan.state.ask import describe  # noqa: E402

OUT = ROOT / "promo-video" / "frames"
SCALE = 2
WIN_W, WIN_H = 345, 613  # 她的窗口大小（默认）

EVENT = {"hook_event_name": "PermissionRequest", "session_id": "story", "cwd": r"C:\work\shop-web",
         "tool_name": "Bash", "tool_input": {"command": "npm test -- login", "description": "Run login tests"}}
SAY = "改好了，跑一下测试确认。"  # Claude 在终端里的最后一句（story.json 里同一句）
TITLE = "登录页点了没反应，帮我看看"  # 会话标题：第一条提问


def main() -> None:
    app = QApplication.instance() or QApplication([])
    owner = QWidget()
    owner.setGeometry(300, 250, WIN_W, WIN_H)  # 离屏模式的虚拟屏幕很小，放在中间让气泡按正常规则摆在头顶
    owner.show()
    ask = replace(describe(EVENT), say=SAY)
    target = DisplayTarget("confirmation", 1, project="shop-web", ask=ask)
    content = content_of(target, TITLE, show_commands=False)
    bubble = Bubble(owner)
    bubble.show_content(content)
    app.processEvents()
    w, h = bubble.width(), bubble.height()
    img = QImage(w * SCALE, h * SCALE, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    img.setDevicePixelRatio(SCALE)
    p = QPainter(img)
    bubble.render(p, QPoint(0, 0))
    p.end()
    img.save(str(OUT / "bubble.png"))
    meta = {"w": w, "h": h, "scale": SCALE, "tailX": bubble._tail_x, "tail": bubble._tail,
            "dx": bubble.x() - owner.x(), "dy": bubble.y() - owner.y(), "content": content._asdict() if hasattr(content, "_asdict") else str(content)}
    (OUT / "bubble.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(meta)


if __name__ == "__main__":
    main()
