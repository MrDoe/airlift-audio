"""One-file enhancement pipeline shared by the GUI and the CLI."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

from .apollo import ApolloRestorer, CancelledError
from .audio import (
    SAMPLE_RATE,
    apply_shelf,
    band_levels,
    decode,
    peak_dbfs,
    rms_dbfs,
    write_audio,
)

Progress = Callable[[str, float], None]
CancelCheck = Callable[[], bool]

AUDIO_SUFFIXES = {
    ".wav", ".flac", ".mp3", ".m4a", ".aac", ".ogg", ".oga", ".opus", ".aiff", ".aif",
}


@dataclass
class EnhanceOptions:
    shelf_db: float = 2.5
    shelf_freq: float = 9_000.0
    fmt: str = "wav"
    output_dir: Path | None = None
    chunk_seconds: float = 6.0
    overlap_seconds: float = 1.0
    pad_seconds: float = 1.0
    batch_size: int = 2


@dataclass
class EnhanceResult:
    source: Path
    output: Path
    duration: float
    source_sample_rate: int
    device: str
    before: dict[str, float] = field(default_factory=dict)
    after: dict[str, float] = field(default_factory=dict)
    peak: float = 0.0
    rms: float = 0.0
    clipped: int = 0
    elapsed: float = 0.0


def output_path(source: Path, options: EnhanceOptions) -> Path:
    stem = source.stem
    suffix = ".enhanced.air" if options.shelf_db else ".enhanced"
    ext = ".flac" if options.fmt == "flac" else ".wav"
    folder = options.output_dir or source.parent
    return Path(folder) / f"{stem}{suffix}{ext}"


def enhance_file(
    source: Path,
    options: EnhanceOptions,
    restorer: ApolloRestorer,
    *,
    progress: Progress | None = None,
    cancel: CancelCheck | None = None,
) -> EnhanceResult:
    started = time.time()
    source = Path(source)
    emit = progress or (lambda stage, fraction: None)

    emit("Reading", 0.02)
    audio, meta = decode(source)
    if cancel and cancel():
        raise CancelledError("Cancelled")
    before = band_levels(audio)

    emit("Restoring", 0.05)
    restored = restorer.restore(
        audio,
        chunk_seconds=options.chunk_seconds,
        overlap_seconds=options.overlap_seconds,
        pad_seconds=options.pad_seconds,
        batch_size=options.batch_size,
        progress=lambda stage, fraction: emit(stage, 0.05 + 0.85 * fraction),
        cancel=cancel,
    )

    if options.shelf_db:
        emit("Adding air", 0.92)
        restored = apply_shelf(restored, options.shelf_freq, options.shelf_db)

    out = output_path(source, options)
    emit("Writing", 0.96)
    clipped = write_audio(out, restored, options.fmt)
    after = band_levels(restored)

    return EnhanceResult(
        source=source,
        output=out,
        duration=len(restored) / SAMPLE_RATE,
        source_sample_rate=meta["source_sample_rate"],
        device=restorer.device,
        before=before,
        after=after,
        peak=peak_dbfs(restored),
        rms=rms_dbfs(restored),
        clipped=clipped,
        elapsed=time.time() - started,
    )
