from __future__ import annotations

import numpy as np
import pytest
import soundfile as sf

from airlift.core.audio import (
    SAMPLE_RATE,
    apply_shelf,
    band_labels,
    band_levels,
    decode,
    make_ab_clip,
)
from airlift.core.pipeline import EnhanceOptions, output_path


def test_band_levels_reference_is_zero():
    rng = np.random.default_rng(0)
    audio = rng.normal(0, 0.1, (SAMPLE_RATE * 2, 2)).astype(np.float32)
    levels = band_levels(audio)
    assert set(levels) == set(band_labels())
    # 1-8 kHz is the reference, so its octave bands sum to 0 dB.
    one_to_eight = [value for label, value in levels.items()
                    if 1_000 <= float(label.split("-")[0]) * 1_000 < 8_000]
    total = 10 * np.log10(sum(10 ** (value / 10) for value in one_to_eight))
    assert abs(total) < 0.01


def test_shelf_raises_high_band():
    rng = np.random.default_rng(1)
    audio = rng.normal(0, 0.05, (SAMPLE_RATE * 2, 2)).astype(np.float32)
    before = band_levels(audio)
    after = band_levels(apply_shelf(audio, 9_000, 6.0))
    assert after["10-12k"] - before["10-12k"] > 3.0
    assert abs(after["1-2k"] - before["1-2k"]) < 1.0


def test_make_ab_clip_alternates():
    original = np.full((SAMPLE_RATE, 2), 0.2, dtype=np.float32)
    enhanced = np.full((SAMPLE_RATE, 2), -0.2, dtype=np.float32)
    clip = make_ab_clip(original, enhanced, seconds=1.0, block_seconds=0.25)
    block = int(0.25 * SAMPLE_RATE)
    mids = [clip[i * block + block // 2, 0] for i in range(len(clip) // block)]
    signs = [1 if value > 0 else -1 for value in mids]
    assert signs == [1, -1, 1, -1, 1, -1, 1, -1]


def test_decode_resamples_to_44k(tmp_path):
    t = np.arange(int(48_000 * 0.5)) / 48_000
    stereo = np.stack([np.sin(2 * np.pi * 440 * t)] * 2, axis=1) * 0.2
    path = tmp_path / "in48.wav"
    sf.write(path, stereo, 48_000, subtype="PCM_16")

    audio, meta = decode(path)
    assert audio.shape[1] == 2
    assert meta["source_sample_rate"] == 48_000
    assert abs(len(audio) / SAMPLE_RATE - 0.5) < 0.01


def test_output_naming(tmp_path):
    source = tmp_path / "song.wav"
    source.write_bytes(b"")
    raw = output_path(source, EnhanceOptions(shelf_db=0.0))
    air = output_path(source, EnhanceOptions(shelf_db=2.5))
    flac = output_path(source, EnhanceOptions(shelf_db=2.5, fmt="flac"))
    assert raw.name == "song.enhanced.wav"
    assert air.name == "song.enhanced.air.wav"
    assert flac.name == "song.enhanced.air.flac"


# -- edge cases -----------------------------------------------------------


def test_band_levels_empty_short():
    """Silent/sparse audio must not raise; just return a dict."""
    audio = np.zeros((1_000, 2), dtype=np.float32)
    levels = band_levels(audio)
    assert isinstance(levels, dict)


def test_band_levels_all_bands_present():
    rng = np.random.default_rng(2)
    audio = rng.normal(0, 0.3, (SAMPLE_RATE * 3, 2)).astype(np.float32)
    levels = band_levels(audio)
    assert set(levels) == set(band_labels())
    assert all(isinstance(v, float) for v in levels.values())


def test_shelf_zero_gain_is_near_passthrough():
    rng = np.random.default_rng(3)
    audio = rng.normal(0, 0.2, (SAMPLE_RATE, 2)).astype(np.float32)
    out = apply_shelf(audio, 9_000, 0.0)
    assert out.shape == audio.shape
    assert np.allclose(out, audio, atol=3e-2)


def test_make_ab_clip_short_input():
    """A clip asked from beyond the end must still return audio."""
    audio = np.full((SAMPLE_RATE, 2), 0.1, dtype=np.float32)
    clip = make_ab_clip(audio, audio, start_seconds=0.9, seconds=0.5)
    assert len(clip) > 0
    assert clip.shape[1] == 2


def test_make_ab_clip_clips_loud():
    loud = np.full((SAMPLE_RATE * 2, 2), 3.0, dtype=np.float32)
    clip = make_ab_clip(loud, loud, seconds=2.0, block_seconds=1.0)
    assert float(np.max(np.abs(clip))) <= 0.999


def test_decode_raises_for_missing_file(tmp_path):
    with pytest.raises((FileNotFoundError, RuntimeError, OSError)):
        decode(tmp_path / "nope.wav")
