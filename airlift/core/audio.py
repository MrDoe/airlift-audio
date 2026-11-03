"""Core audio plumbing: decode, write, EQ, and measurement."""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly, sosfilt

SAMPLE_RATE = 44_100

# Octave-ish analysis bands; labels double as table keys.
BAND_EDGES = [0, 100, 250, 500, 1_000, 2_000, 4_000, 6_000, 8_000,
              10_000, 12_000, 14_000, 16_000, 18_000, 20_000, 22_050]


def band_labels() -> list[str]:
    return [f"{a/1000:g}-{b/1000:g}k" for a, b in zip(BAND_EDGES, BAND_EDGES[1:])]


def ffmpeg_exe() -> str | None:
    """Locate ffmpeg: PATH first, then the bundled imageio-ffmpeg binary."""
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def _decode_ffmpeg(path: Path) -> tuple[np.ndarray, int]:
    exe = ffmpeg_exe()
    if not exe:
        raise RuntimeError(
            "Could not decode this file. Install ffmpeg or use WAV/FLAC/MP3."
        )
    with tempfile.TemporaryDirectory(prefix="airlift-decode-") as td:
        wav = Path(td) / "decoded.wav"
        subprocess.run(
            [exe, "-v", "error", "-y", "-i", str(path), "-vn",
             "-ar", str(SAMPLE_RATE), "-ac", "2", "-c:a", "pcm_f32le", str(wav)],
            check=True,
        )
        data, sr = sf.read(wav, always_2d=True, dtype="float32")
    return data, sr


def _resample(x: np.ndarray, sr_in: int, sr_out: int) -> np.ndarray:
    if sr_in == sr_out:
        return x
    from math import gcd

    g = gcd(sr_in, sr_out)
    return resample_poly(x, sr_out // g, sr_in // g, axis=0).astype(np.float32)


def decode(path: str | Path, sample_rate: int = SAMPLE_RATE) -> tuple[np.ndarray, dict]:
    """Decode any supported file to (samples, 2) float32 at `sample_rate`.

    Tries libsndfile first (WAV/FLAC/OGG/MP3), falls back to ffmpeg for
    containers libsndfile cannot read (M4A/AAC/Opus in some builds).
    """
    path = Path(path)
    try:
        data, sr = sf.read(str(path), always_2d=True, dtype="float32")
    except Exception:
        data, sr = _decode_ffmpeg(path)

    source_sr = int(sr)
    source_channels = int(data.shape[1])
    if data.shape[1] == 1:
        data = np.repeat(data, 2, axis=1)
    elif data.shape[1] > 2:
        data = data[:, :2]

    if sr != sample_rate:
        data = _resample(data, sr, sample_rate)

    peak = float(np.max(np.abs(data))) if data.size else 0.0
    if peak > 1.0:  # defensive: some float masters exceed full scale
        data = (data / peak * 0.999).astype(np.float32)
        peak = 0.999

    meta = {
        "source_sample_rate": source_sr,
        "source_channels": source_channels,
        "sample_rate": sample_rate,
        "duration": len(data) / sample_rate,
        "peak_dbfs": 20 * np.log10(peak + 1e-12),
    }
    return data, meta


def write_audio(path: str | Path, audio: np.ndarray, fmt: str = "wav") -> int:
    """Write float audio; returns number of clipped samples for PCM output."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    clipped = 0
    if fmt == "flac":
        peak = float(np.max(np.abs(audio))) if audio.size else 0.0
        if peak > 1.0:
            clipped = int(np.count_nonzero(np.abs(audio) > 1.0))
            audio = np.clip(audio, -1.0, 1.0)
        sf.write(path, audio, SAMPLE_RATE, subtype="PCM_24")
    else:
        sf.write(path, audio, SAMPLE_RATE, subtype="FLOAT")
    return clipped


def high_shelf_sos(freq: float, gain_db: float, q: float = 0.7) -> np.ndarray:
    """RBJ high-shelf biquad used to compensate Apollo's high-frequency tilt."""
    amp = 10 ** (gain_db / 40.0)
    w0 = 2 * np.pi * freq / SAMPLE_RATE
    alpha = np.sin(w0) / (2 * q)
    cosw = np.cos(w0)
    sqrt_amp = np.sqrt(amp)
    b0 = amp * ((amp + 1) + (amp - 1) * cosw + 2 * sqrt_amp * alpha)
    b1 = -2 * amp * ((amp - 1) + (amp + 1) * cosw)
    b2 = amp * ((amp + 1) + (amp - 1) * cosw - 2 * sqrt_amp * alpha)
    a0 = (amp + 1) - (amp - 1) * cosw + 2 * sqrt_amp * alpha
    a1 = 2 * ((amp - 1) - (amp + 1) * cosw)
    a2 = (amp + 1) - (amp - 1) * cosw - 2 * sqrt_amp * alpha
    return np.array([[b0 / a0, b1 / a0, b2 / a0, 1.0, a1 / a0, a2 / a0]])


def apply_shelf(audio: np.ndarray, freq: float, gain_db: float) -> np.ndarray:
    sos = high_shelf_sos(freq, gain_db)
    out = np.empty_like(audio)
    for ch in range(audio.shape[1]):
        out[:, ch] = sosfilt(sos, audio[:, ch])
    return out


def band_levels(audio: np.ndarray) -> dict[str, float]:
    """Long-term average band energy in dB relative to 1-8 kHz."""
    mono = audio.mean(axis=1) if audio.ndim > 1 else audio
    win, hop = 8192, 4096
    if mono.size < win:
        mono = np.pad(mono, (0, win - mono.size))
    frames = np.lib.stride_tricks.sliding_window_view(mono, win)[::hop] * np.hanning(win)
    power = (np.abs(np.fft.rfft(frames, axis=1)) ** 2).mean(axis=0)
    freqs = np.fft.rfftfreq(win, 1 / SAMPLE_RATE)
    ref = power[(freqs >= 1_000) & (freqs < 8_000)].sum()
    if ref <= 0:
        return {}
    out: dict[str, float] = {}
    for label, (a, b) in zip(band_labels(), zip(BAND_EDGES, BAND_EDGES[1:])):
        mask = (freqs >= a) & (freqs < b)
        out[label] = float(10 * np.log10(power[mask].sum() / ref + 1e-15))
    return out


def measure_lufs(path: str | Path) -> float | None:
    """EBU R128 integrated loudness via ffmpeg (None if unavailable)."""
    exe = ffmpeg_exe()
    if not exe:
        return None
    proc = subprocess.run(
        [exe, "-hide_banner", "-nostats", "-i", str(path),
         "-af", "ebur128=peak=true", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    tail = proc.stderr[proc.stderr.rfind("Summary:"):]
    match = re.search(r"I:\s*(-?\d+(?:\.\d+)?)\s*LUFS", tail)
    return float(match.group(1)) if match else None


def peak_dbfs(audio: np.ndarray) -> float:
    return float(20 * np.log10(np.max(np.abs(audio)) + 1e-12))


def rms_dbfs(audio: np.ndarray) -> float:
    return float(20 * np.log10(np.sqrt(np.mean(audio ** 2)) + 1e-12))


def make_ab_clip(
    original: np.ndarray,
    enhanced: np.ndarray,
    *,
    start_seconds: float = 0.0,
    seconds: float = 40.0,
    block_seconds: float = 8.0,
    repeats: int = 1,
    crossfade_seconds: float = 0.04,
) -> np.ndarray:
    """Alternate 8 s original / 8 s enhanced blocks for blind-ish A/B listening."""
    start = int(start_seconds * SAMPLE_RATE)
    length = int(seconds * SAMPLE_RATE)
    a = original[start:start + length]
    b = enhanced[start:start + length]
    n = min(len(a), len(b))
    if n == 0:
        return np.zeros((0, 2), dtype=np.float32)
    a, b = a[:n], b[:n]

    block = max(1, int(block_seconds * SAMPLE_RATE))
    fade = min(int(crossfade_seconds * SAMPLE_RATE), block // 4)
    blocks = max(1, n // block)
    pieces = []
    for _ in range(max(1, repeats)):
        for i in range(blocks):
            for source in (a, b):
                seg = source[i * block:(i + 1) * block].copy()
                if fade and len(seg) > 2 * fade:
                    ramp = np.linspace(0, 1, fade, dtype=np.float32)[:, None]
                    seg[:fade] *= np.sqrt(ramp)
                    seg[-fade:] *= np.sqrt(ramp[::-1])
                pieces.append(seg)
    clip = np.concatenate(pieces, axis=0)
    peak = float(np.max(np.abs(clip)))
    if peak > 0.999:
        clip *= 0.999 / peak
    return clip
