"""Stem separation plumbing that does not need Demucs installed."""

from __future__ import annotations

import pytest

from airlift.core.stems import (
    DEFAULT_MODEL,
    STEM_LABELS,
    StemOptions,
    build_command,
    unique_path,
)


def test_two_stem_command(tmp_path):
    source = tmp_path / "song.wav"
    cmd = build_command("python3", source, tmp_path / "work", StemOptions(), "cpu")
    assert cmd[:3] == ["python3", "-m", "demucs"]
    assert cmd[cmd.index("-n") + 1] == DEFAULT_MODEL
    assert cmd[cmd.index("-d") + 1] == "cpu"
    assert "--two-stems" in cmd
    assert cmd[cmd.index("--two-stems") + 1] == "vocals"
    assert cmd[-1] == str(source)


def test_four_stem_command_drops_two_stems(tmp_path):
    options = StemOptions(four_stems=True, shifts=4, overlap=0.5)
    cmd = build_command("python3", tmp_path / "song.wav", tmp_path, options, "cuda")
    assert "--two-stems" not in cmd
    assert cmd[cmd.index("--shifts") + 1] == "4"
    assert cmd[cmd.index("--overlap") + 1] == "0.5"


def test_defaults():
    options = StemOptions()
    assert options.model == DEFAULT_MODEL
    assert options.device == "auto"
    assert options.fmt == "wav"
    assert options.shifts == 1


def test_unique_path(tmp_path):
    target = tmp_path / "song.vocals.wav"
    assert unique_path(target) == target
    target.write_bytes(b"x")
    assert unique_path(target) == tmp_path / "song.vocals (2).wav"


def test_stem_labels():
    assert STEM_LABELS["no_vocals"] == "instrumental"
    assert STEM_LABELS["vocals"] == "vocals"
    assert {"drums", "bass", "other"} <= set(STEM_LABELS)


def test_frozen_bundle_does_not_use_itself_as_python(monkeypatch):
    """A PyInstaller binary is not a Python: never probe sys.executable."""
    from airlift.core import stems

    monkeypatch.delenv("AIRLIFT_DEMUCS_PYTHON", raising=False)
    monkeypatch.setattr(stems.sys, "frozen", True, raising=False)
    monkeypatch.setattr(stems, "has_demucs", lambda python: False)

    with pytest.raises(stems.DemucsUnavailable) as exc:
        stems.resolve_python(None)
    assert str(stems.sys.executable) not in str(exc.value)


def test_resolve_python_rejects_missing_explicit_path(tmp_path):
    from airlift.core import stems

    missing = tmp_path / "nope" / "python"
    with pytest.raises(stems.DemucsUnavailable) as exc:
        stems.resolve_python(str(missing))
    assert str(missing) in str(exc.value)
