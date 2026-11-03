"""Style smoke tests (no audio required)."""

from __future__ import annotations


def test_theme_imports():
    from airlift.ui.theme import QSS

    assert "QProgressBar" in QSS


def test_app_usage():
    from airlift.app import USAGE

    assert "enhance" in USAGE


def test_ui_core_mocks():
    """The widget logic that doesn't need a display stays importable."""
    from airlift.core.apollo import describe_device, resolve_device

    assert resolve_device("cpu") == "cpu"
    assert describe_device("cpu") == "CPU"
