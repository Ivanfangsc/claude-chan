"""把打包好的 dist/ClaudeChan/ 压成发布用的 zip，并打印大小和 SHA256（写进 Release 说明，方便用户校验）。

    uv run pyinstaller claude-chan.spec --noconfirm
    uv run python scripts/package_release.py        # → dist/ClaudeChan-v<版本>-windows.zip

只在本地生成文件，不上传。
"""

import hashlib
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from claude_chan import __version__  # noqa: E402

SRC = ROOT / "dist" / "ClaudeChan"
DST = ROOT / "dist" / f"ClaudeChan-v{__version__}-windows.zip"


def main() -> None:
    exe = SRC / "ClaudeChan.exe"
    if not exe.exists():
        sys.exit(f"没有找到 {exe}，先运行 uv run pyinstaller claude-chan.spec --noconfirm")
    for need in ("LICENSE", "ASSETS-LICENSE.md"):
        if not (SRC / "_internal" / need).exists() and not (SRC / need).exists():
            sys.exit(f"打包目录里缺少 {need}，检查 claude-chan.spec 的 datas")
    # data 是本机运行打包版时留下的设置和日志，不能发出去（用户解压覆盖时会盖掉自己的设置）
    files = sorted(p for p in SRC.rglob("*") if p.is_file() and p.relative_to(SRC).parts[0] != "data")
    with zipfile.ZipFile(DST, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in files:
            # 解压后得到一个 ClaudeChan 文件夹
            z.write(p, Path("ClaudeChan") / p.relative_to(SRC))
    digest = hashlib.sha256(DST.read_bytes()).hexdigest()
    print(f"{DST.name}  {DST.stat().st_size / 1e6:.0f} MB  {len(files)} 个文件")
    print(f"SHA256  {digest}")


if __name__ == "__main__":
    main()
