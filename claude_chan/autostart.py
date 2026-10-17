"""开机自启：Windows 写注册表 Run 键，macOS 写 LaunchAgent，Linux 写 ~/.config/autostart。"""

from __future__ import annotations

import os
import shlex
import sys
from pathlib import Path

APP_ID = "claude-chan"


def launch_command() -> list[str]:
    """打包后直接启动可执行文件；开发时用当前 Python 运行模块。"""
    if getattr(sys, "frozen", False):
        return [sys.executable]
    return [sys.executable, "-m", "claude_chan"]


def _mac_plist() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"com.{APP_ID}.plist"


def _linux_desktop() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "autostart" / f"{APP_ID}.desktop"


def is_enabled() -> bool:
    if sys.platform == "win32":
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
                winreg.QueryValueEx(key, APP_ID)
                return True
        except OSError:
            return False
    if sys.platform == "darwin":
        return _mac_plist().exists()
    return _linux_desktop().exists()


def set_enabled(on: bool) -> None:
    cmd = launch_command()
    if sys.platform == "win32":
        import subprocess
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE
        ) as key:
            if on:
                # 开发时用 pythonw 启动，避免开机弹出命令行窗口
                exe = cmd[0].replace("python.exe", "pythonw.exe") if cmd[0].endswith("python.exe") else cmd[0]
                winreg.SetValueEx(key, APP_ID, 0, winreg.REG_SZ, subprocess.list2cmdline([exe, *cmd[1:]]))
            else:
                try:
                    winreg.DeleteValue(key, APP_ID)
                except OSError:
                    pass
        return
    if sys.platform == "darwin":
        plist = _mac_plist()
        if not on:
            plist.unlink(missing_ok=True)
            return
        args = "".join(f"<string>{a}</string>" for a in cmd)
        plist.parent.mkdir(parents=True, exist_ok=True)
        plist.write_text(
            f'<?xml version="1.0" encoding="UTF-8"?>\n<plist version="1.0"><dict>'
            f"<key>Label</key><string>com.{APP_ID}</string>"
            f"<key>ProgramArguments</key><array>{args}</array>"
            f"<key>RunAtLoad</key><true/></dict></plist>\n"
        )
        return
    desktop = _linux_desktop()
    if not on:
        desktop.unlink(missing_ok=True)
        return
    desktop.parent.mkdir(parents=True, exist_ok=True)
    desktop.write_text(f"[Desktop Entry]\nType=Application\nName=Claude-Chan\nExec={shlex.join(cmd)}\nX-GNOME-Autostart-enabled=true\n")
