# PyInstaller 打包配置：uv run pyinstaller claude-chan.spec --noconfirm
# 输出 dist/ClaudeChan/ClaudeChan.exe（目录形式：启动快，开机自启的路径固定）。
import json
import shutil
import sys
from pathlib import Path

# 重新打包会清空 dist/ClaudeChan/：先把里面的 data（设置、窗口位置、日志）挪开，打包完再放回去
_DATA, _KEEP = Path("dist/ClaudeChan/data"), Path("build/data-keep")
if _DATA.is_dir():
    shutil.rmtree(_KEEP, ignore_errors=True)
    _KEEP.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(_DATA), str(_KEEP))

# 每个形象（resources/assets、resources/assets-chibi …）只打包 manifest 里用到的素材（关键帧、AVIF、变身动画）；
# 生成时的 webm 原始文件和被淘汰的片段不打包
datas = [("resources/icon.png", "resources"), ("LICENSE", "."), ("ASSETS-LICENSE.md", ".")]
for assets in sorted(Path("resources").glob("assets*")):
    if not (assets / "manifest.json").exists():
        continue
    manifest = json.loads((assets / "manifest.json").read_text(encoding="utf-8"))
    files = {c["file"] for c in manifest["clips"]}
    files |= {s["keyframe"] for s in manifest["states"].values() if s.get("keyframe")}
    files |= {h["keyframe"] for h in manifest["hubs"].values() if h.get("keyframe")}
    files |= {"manifest.json"} | ({"hitmask.png"} if (assets / "hitmask.png").exists() else set())
    datas += [(str(assets / f), str((assets / f).parent)) for f in sorted(files)]

# 桌宠只用 QtCore / QtGui / QtWidgets / QtNetwork，用 CPU 光栅绘制。这些库是插件顺带引进来的，用不上
UNUSED = ("opengl32sw", "Qt6Quick", "Qt6Qml", "Qt6Pdf", "Qt6VirtualKeyboard", "Qt6OpenGL", "qpdf", "qtvirtualkeyboard")

a = Analysis(
    ["claude_chan/__main__.py"],
    pathex=["."],
    datas=datas,
    excludes=["tkinter", "numpy", "av", "PyInstaller"],
)
a.binaries = [b for b in a.binaries if not any(name in Path(b[0]).name for name in UNUSED)]

# OpenSSL 一定用 Python 自带的那份：在 Git Bash 里打包时，PATH 上 Git 的 mingw64\bin 也有同名的 libssl / libcrypto，
# PyInstaller 会挑中它们，Python 的 _ssl 加载不了，检查更新就连不上 https
_PY_DLLS = Path(sys.base_prefix) / "DLLs"
_OPENSSL = {"libssl-3-x64.dll", "libcrypto-3-x64.dll"}
a.binaries = [
    (dest, str(_PY_DLLS / Path(dest).name), kind) if Path(dest).name.lower() in _OPENSSL and (_PY_DLLS / Path(dest).name).exists()
    else (dest, src, kind)
    for dest, src, kind in a.binaries
]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="ClaudeChan", icon="resources/icon.png", console=False)
coll = COLLECT(exe, a.binaries, a.datas, name="ClaudeChan")

if _KEEP.is_dir():
    shutil.move(str(_KEEP), str(_DATA))
