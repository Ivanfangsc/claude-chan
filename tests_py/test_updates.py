"""版本号比较，以及各处写的版本号一致。"""

import json
import tomllib
from pathlib import Path

from claude_chan import __version__
from claude_chan.updates import is_newer, parse_version

ROOT = Path(__file__).resolve().parent.parent


def test_parse_version():
    assert parse_version("v1.2.3") == (1, 2, 3)
    assert parse_version("1.10") == (1, 10)
    assert parse_version("nightly") is None


def test_is_newer():
    assert is_newer("v1.0.1", "1.0.0")
    assert is_newer("v1.10.0", "1.9.9")
    assert not is_newer("v1.0", "1.0.0")
    assert not is_newer("v0.9.0", "1.0.0")
    assert not is_newer("garbage", "1.0.0")


def test_versions_match():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    plugin = json.loads((ROOT / "plugin/.claude-plugin/plugin.json").read_text(encoding="utf-8"))["version"]
    assert __version__ == pyproject == plugin
