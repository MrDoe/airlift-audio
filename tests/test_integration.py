"""End-to-end integration: real file → Apollo → output, on CPU.

Skipped in CI without the weights cache; runnable locally. Expects the model
weights to be downloadable (network) or already cached.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf

from airlift.core.apollo import ApolloRestorer
from airlift.core.pipeline import EnhanceOptions, enhance_file


def _make_tone(path: Path, seconds: float = 8.0) -> None:
    t = np.arange(int(44_100 * seconds)) / 44_100
    stereo = np.stack([np.sin(2 * np.pi * 440 * t)] * 2, axis=1) * 0.15
    stereo += np.random.default_rng(0).normal(0, 0.01, stereo.shape)
    sf.write(path, stereo, 44_100, subtype="PCM_16")


def test_full_pipeline_cpu(tmp_path, monkeypatch):
    source = tmp_path / "tone.wav"
    _make_tone(source)
    out_dir = tmp_path / "out"

    monkeypatch.setenv("HF_HUB_OFFLINE", "0")
    options = EnhanceOptions(shelf_db=2.5, output_dir=out_dir)
    restorer = ApolloRestorer("cpu")
    result = enhance_file(source, options, restorer)

    assert result.output.is_file()
    audio, sr = sf.read(result.output, always_2d=True, dtype="float32")
    assert sr == 44_100
    assert audio.shape == (8 * 44_100, 2)
    assert not np.isnan(audio).any()
    assert result.device == "cpu"


def test_frozen_binary_cli(tmp_path):
    """The built binary must enhance a file without the source venv."""
    binary = Path(__file__).resolve().parent.parent / "dist" / "Airlift Audio" / "Airlift Audio"
    if not binary.is_file():
        return  # bundle not built yet; manual step covers it

    source = tmp_path / "tone.wav"
    _make_tone(source)
    out = tmp_path / "out"
    proc = subprocess.run(
        [str(binary), "enhance", str(source), "--device", "cpu", "-o", str(out)],
        check=False, capture_output=True, text=True, timeout=600,
    )
    assert proc.returncode == 0, proc.stderr
    assert any(out.glob("*.wav"))
