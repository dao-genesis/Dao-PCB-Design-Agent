"""dao_platform (KiCad 跨平台本源矩阵) — 三系统归一契约测试。"""
from __future__ import annotations

from pathlib import Path

import pytest

from kicad_origin.origin import dao_platform as dp


def test_normalize_os():
    assert dp.normalize_os("Windows") == "windows"
    assert dp.normalize_os("Win32") == "windows"
    assert dp.normalize_os("Darwin") == "macos"
    assert dp.normalize_os("Linux") == "linux"
    assert dp.normalize_os("") in ("linux", "windows", "macos", "unknown")


@pytest.mark.parametrize("os_name,root_parts", [
    ("linux", (".local", "share", "kicad")),
    ("windows", ("Documents", "KiCad")),
    ("macos", ("Documents", "KiCad")),
])
def test_user_root_matrix(os_name, root_parts, tmp_path):
    spec = dp.spec_for(os_name)
    assert spec.os == os_name
    assert spec.kicad_user_root(tmp_path) == tmp_path.joinpath(*root_parts)


def test_detect_version_default_and_highest(tmp_path):
    spec = dp.spec_for("linux")
    assert spec.detect_version(tmp_path) == dp.DEFAULT_KICAD_VERSION
    root = spec.kicad_user_root(tmp_path)
    for v in ("8.0", "9.0", "10.0"):
        (root / v).mkdir(parents=True)
    (root / "not-a-version").mkdir()
    assert spec.detect_version(tmp_path) == "10.0"  # 数值序, 非字典序


@pytest.mark.parametrize("os_name", ["linux", "windows", "macos"])
def test_plugin_dir_matrix(os_name, tmp_path, monkeypatch):
    monkeypatch.delenv("KICAD_USER_PLUGIN_DIR", raising=False)
    spec = dp.spec_for(os_name)
    d = spec.plugin_dir(home=tmp_path)
    assert d == spec.kicad_user_root(tmp_path) / dp.DEFAULT_KICAD_VERSION / "scripting" / "plugins"


def test_plugin_dir_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("KICAD_USER_PLUGIN_DIR", str(tmp_path / "custom"))
    for os_name in ("linux", "windows", "macos"):
        assert dp.spec_for(os_name).plugin_dir() == tmp_path / "custom"


def test_native_live_delegates_to_matrix(monkeypatch):
    from kicad_origin.origin import native_live
    monkeypatch.delenv("KICAD_USER_PLUGIN_DIR", raising=False)
    assert native_live._user_plugin_dir() == dp.current().plugin_dir()
    monkeypatch.setenv("KICAD_USER_PLUGIN_DIR", "/tmp/x-plugins")
    assert native_live._user_plugin_dir() == Path("/tmp/x-plugins")


def test_current_is_real_machine():
    spec = dp.current()
    assert spec.os in ("linux", "windows", "macos")
    d = spec.as_dict()
    assert d["plugin_dir"].endswith("plugins")
