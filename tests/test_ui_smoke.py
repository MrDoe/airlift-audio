"""Style smoke tests (no audio required)."""

from __future__ import annotations


def test_theme_imports():
    from airlift.ui.theme import QSS

    assert "QProgressBar" in QSS


def test_app_usage():
    from airlift.app import USAGE

    assert "enhance" in USAGE
    assert "separate" in USAGE


def test_stem_ui_imports():
    from airlift.ui.stem_dialog import StemDialog
    from airlift.ui.worker import StemWorker

    assert hasattr(StemDialog, "stems_ready")
    assert hasattr(StemWorker, "cancel")


def test_ui_helpers():
    from airlift.ui.main_window import PRESETS, StatusChip, _fmt_duration

    assert _fmt_duration(0) == "0:00"
    assert _fmt_duration(72.6) == "1:12"
    assert PRESETS["Restore"] == (2.5, 9_000)
    assert hasattr(StatusChip, "set_state")


def test_ui_core_mocks():
    """The widget logic that doesn't need a display stays importable."""
    from airlift.core.apollo import describe_device, resolve_device

    assert resolve_device("cpu") == "cpu"
    assert describe_device("cpu") == "CPU"
