"""一键更新（只用于打包版）：下载 Release 里的 zip → 校验 → 解压到 data/update → 退出，由一个 PowerShell 脚本换文件再启动。

程序运行时 exe 和 _internal 里的 dll 都被占着，自己换不了自己，所以换文件交给一个独立的脚本：
等本进程退出 → 把安装目录里除 data 以外的东西挪进 data/update/old → 把新版挪进来 → 启动新版。
中途出错就按记录原样挪回去再启动旧版。结果写进 data/update/result.txt，下次启动时读出来通知，并删掉 data/update。

data（设置、窗口位置、日志）全程不动。下载和解压在后台线程里用 urllib / zipfile 做（不用 Qt 联网，原因见 updates.py）。
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import threading
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, Signal

EXE = "ClaudeChan.exe"
TOP = "ClaudeChan"  # zip 里的顶层文件夹


@dataclass(frozen=True)
class Asset:
    tag: str
    url: str
    size: int
    sha256: str | None  # GitHub 给的 digest；老的 Release 可能没有


def find_asset(release: dict) -> Asset | None:
    """Release 里的 Windows 包：名字以 -windows.zip 结尾的那个。"""
    for a in release.get("assets") or []:
        name = a.get("name", "")
        url = a.get("browser_download_url", "")
        if name.endswith("-windows.zip") and url.startswith("https://github.com/"):
            digest = a.get("digest") or ""
            sha = digest[7:] if digest.startswith("sha256:") else None
            return Asset(release.get("tag_name", ""), url, int(a.get("size") or 0), sha)
    return None


def install_dir() -> Path | None:
    """打包版的安装目录；从源码运行时没有（不自动更新）。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return None


def _ps(s: str) -> str:
    """PowerShell 单引号字符串。"""
    return "'" + s.replace("'", "''") + "'"


def swap_script(install: Path, staged: Path, old: Path, result: Path, pid: int, tag: str, launch: bool = True) -> str:
    """换文件的 PowerShell 脚本：等 pid 退出 → 旧的挪进 old → 新的挪进来 → 启动；失败就挪回去启动旧版。"""
    return f"""$ErrorActionPreference = 'Stop'
$install = {_ps(str(install))}
$staged = {_ps(str(staged))}
$old = {_ps(str(old))}
$result = {_ps(str(result))}
try {{ Wait-Process -Id {pid} -Timeout 60 }} catch {{}}
Start-Sleep -Milliseconds 800
$moved = @(); $placed = @()
try {{
    New-Item -ItemType Directory -Force -Path $old | Out-Null
    foreach ($item in Get-ChildItem -LiteralPath $install -Force) {{
        if ($item.Name -eq 'data') {{ continue }}
        Move-Item -LiteralPath $item.FullName -Destination (Join-Path $old $item.Name)
        $moved += $item.Name
    }}
    foreach ($item in Get-ChildItem -LiteralPath $staged -Force) {{
        Move-Item -LiteralPath $item.FullName -Destination (Join-Path $install $item.Name)
        $placed += $item.Name
    }}
    Set-Content -LiteralPath $result -Encoding UTF8 -Value 'ok {tag}'
    Remove-Item -LiteralPath $old -Recurse -Force -ErrorAction SilentlyContinue  # 旧版有几百 MB，换好就删
}} catch {{
    $err = "$_"
    foreach ($n in $placed) {{
        try {{ Move-Item -LiteralPath (Join-Path $install $n) -Destination (Join-Path $staged $n) }} catch {{}}
    }}
    foreach ($n in $moved) {{
        try {{ Move-Item -LiteralPath (Join-Path $old $n) -Destination (Join-Path $install $n) }} catch {{}}
    }}
    Set-Content -LiteralPath $result -Encoding UTF8 -Value "failed {tag} $err"
}}
""" + (f"Start-Process -FilePath (Join-Path $install {_ps(EXE)}) -WorkingDirectory $install\n" if launch else "")


def finish_previous(data: Path) -> tuple[bool, str] | None:
    """启动时调用：上次更新的结果 (成功, 说明)，并删掉 data/update。没有更新过返回 None。"""
    work = data / "update"
    if not work.exists():
        return None
    result = work / "result.txt"
    out: tuple[bool, str] | None = None
    if result.exists():
        text = result.read_text(encoding="utf-8-sig", errors="replace").strip()
        kind, _, rest = text.partition(" ")
        out = (kind == "ok", rest)
    shutil.rmtree(work, ignore_errors=True)
    return out


class Updater(QObject):
    progress = Signal(int)  # 下载进度 0–100
    ready = Signal()  # 下载、校验、解压都好了，可以 apply()
    failed = Signal(str)

    def __init__(self, data: Path, log: Callable[[str], None]) -> None:
        super().__init__()
        self._data = data
        self._log = log
        self._busy = False
        self._asset: Asset | None = None

    @property
    def busy(self) -> bool:
        return self._busy

    @property
    def work(self) -> Path:
        return self._data / "update"

    def start(self, asset: Asset) -> None:
        if self._busy:
            return
        self._busy = True
        self._asset = asset
        threading.Thread(target=self._run, args=(asset,), name="update-download", daemon=True).start()

    def _run(self, asset: Asset) -> None:
        try:
            self._prepare(asset)
        except Exception as e:  # noqa: BLE001 - 没网、校验失败、磁盘满都只报失败
            shutil.rmtree(self.work, ignore_errors=True)
            self._busy = False
            self.failed.emit(str(e))
            return
        self.ready.emit()

    def _prepare(self, asset: Asset) -> None:
        shutil.rmtree(self.work, ignore_errors=True)
        self.work.mkdir(parents=True)
        zpath = self.work / "package.zip"
        self._log(f"下载新版本 {asset.tag}：{asset.url}")
        req = urllib.request.Request(asset.url, headers={"User-Agent": "claude-chan-updater"})
        h = hashlib.sha256()
        done, last = 0, -1
        with urllib.request.urlopen(req, timeout=30) as resp, open(zpath, "wb") as f:
            total = asset.size or int(resp.headers.get("Content-Length") or 0)
            while chunk := resp.read(1 << 20):
                f.write(chunk)
                h.update(chunk)
                done += len(chunk)
                pct = done * 100 // total if total else 0
                if pct != last:
                    last = pct
                    self.progress.emit(pct)
        if asset.size and done != asset.size:
            raise RuntimeError(f"下载不完整（{done} / {asset.size} 字节）")
        if asset.sha256 and h.hexdigest() != asset.sha256.lower():
            raise RuntimeError("校验失败（SHA256 不一致）")
        with zipfile.ZipFile(zpath) as z:
            names = z.namelist()
            if f"{TOP}/{EXE}" not in names or any(n.split("/")[0] != TOP or ".." in n.split("/") for n in names):
                raise RuntimeError("安装包内容不对")
            z.extractall(self.work)
        zpath.unlink()
        self._log(f"新版本 {asset.tag} 已下载并解压")

    def apply(self) -> bool:
        """启动换文件的脚本（它会等本进程退出）。返回 True 后调用方应立即退出程序。"""
        install = install_dir()
        if install is None or self._asset is None:
            return False
        script = self.work / "swap.ps1"
        # PowerShell 5.1 按系统代码页读没有 BOM 的脚本，路径里有中文就会乱，所以写带 BOM 的 UTF-8
        script.write_text(swap_script(install, self.work / TOP, self.work / "old", self.work / "result.txt",
                                      os.getpid(), self._asset.tag), encoding="utf-8-sig")
        subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-WindowStyle", "Hidden", "-File", str(script)],
            # 不能用 DETACHED_PROCESS：PowerShell 没有控制台会直接退出（返回 0、什么也不做）
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW,
            close_fds=True,
        )
        self._log(f"开始更新到 {self._asset.tag}，退出程序")
        return True

