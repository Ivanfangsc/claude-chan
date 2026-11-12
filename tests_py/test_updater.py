"""一键更新：找安装包、换文件脚本（真的用 PowerShell 跑一遍）、启动时收尾。"""

import subprocess
import sys

import pytest

from claude_chan.updater import Asset, find_asset, finish_previous, swap_script

RELEASE = {
    "tag_name": "v9.9.9",
    "assets": [
        {"name": "notes.txt", "browser_download_url": "https://github.com/x/y/releases/download/v9.9.9/notes.txt"},
        {"name": "ClaudeChan-v9.9.9-windows.zip", "size": 123, "digest": "sha256:abc",
         "browser_download_url": "https://github.com/x/y/releases/download/v9.9.9/ClaudeChan-v9.9.9-windows.zip"},
    ],
}


def test_find_asset():
    a = find_asset(RELEASE)
    assert a == Asset("v9.9.9", RELEASE["assets"][1]["browser_download_url"], 123, "abc")
    assert find_asset({"tag_name": "v1", "assets": []}) is None
    # 不是 github.com 的下载地址不要
    bad = {"tag_name": "v1", "assets": [{"name": "a-windows.zip", "browser_download_url": "https://evil.example/a-windows.zip"}]}
    assert find_asset(bad) is None


def test_finish_previous(tmp_path):
    assert finish_previous(tmp_path) is None
    (tmp_path / "update").mkdir()
    (tmp_path / "update" / "result.txt").write_text("ok v9.9.9", encoding="utf-8-sig")
    assert finish_previous(tmp_path) == (True, "v9.9.9")
    assert not (tmp_path / "update").exists()


def _install(tmp_path):
    """假的安装目录：旧版文件 + data；data/update 里放好解压出来的新版。"""
    install = tmp_path / "安装 目录"  # 中文和空格：脚本要能处理
    (install / "_internal").mkdir(parents=True)
    (install / "ClaudeChan.exe").write_text("old")
    (install / "_internal" / "lib.dll").write_text("old")
    (install / "data").mkdir()
    (install / "data" / "config.json").write_text("{}")
    work = install / "data" / "update"
    (work / "ClaudeChan" / "_internal").mkdir(parents=True)
    (work / "ClaudeChan" / "ClaudeChan.exe").write_text("new")
    (work / "ClaudeChan" / "_internal" / "lib.dll").write_text("new")
    (work / "ClaudeChan" / "_internal" / "added.txt").write_text("new")
    return install, work


def _run(install, work):
    script = work / "swap.ps1"
    script.write_text(swap_script(install, work / "ClaudeChan", work / "old", work / "result.txt",
                                  999_999, "v9.9.9", launch=False), encoding="utf-8-sig")
    subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script)],
                   check=True, timeout=60, capture_output=True)


@pytest.mark.skipif(sys.platform != "win32", reason="换文件脚本是 PowerShell")
def test_swap_replaces_everything_but_data(tmp_path):
    install, work = _install(tmp_path)
    _run(install, work)
    assert (install / "ClaudeChan.exe").read_text() == "new"
    assert (install / "_internal" / "lib.dll").read_text() == "new"
    assert (install / "_internal" / "added.txt").exists()
    assert (install / "data" / "config.json").read_text() == "{}"
    assert not (work / "old").exists()
    assert finish_previous(install / "data") == (True, "v9.9.9")


@pytest.mark.skipif(sys.platform != "win32", reason="换文件脚本是 PowerShell")
def test_swap_rolls_back_when_a_file_is_locked(tmp_path):
    install, work = _install(tmp_path)
    with open(install / "_internal" / "lib.dll"):  # 占着不放：_internal 挪不走
        _run(install, work)
    assert (install / "ClaudeChan.exe").read_text() == "old"
    assert (install / "_internal" / "lib.dll").read_text() == "old"
    assert not (install / "_internal" / "added.txt").exists()
    ok, detail = finish_previous(install / "data")
    assert not ok and detail.startswith("v9.9.9")
