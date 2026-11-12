#!/usr/bin/env python3
"""Render the README screenshots headlessly with deterministic demo data.

    python scripts/make_screenshots.py [--out docs]

Qt runs on its offscreen platform, so no display is needed. Queue rows, band
levels and peaks are synthesized — nothing here loads the Apollo model.
"""

from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
FILES = {
    "midnight-runner.wav": 42.0,
    "dust-and-echo.wav": 35.0,
    "tape-hymn.wav": 27.0,
}


def _demo_audio(seconds: float, seed: int, *, restored: bool) -> np.ndarray:
    """A harmonic tone cluster with a lossy top end; `restored` brings it back."""
    from airlift.core.audio import SAMPLE_RATE, apply_shelf

    rng = np.random.default_rng(seed)
    n = int(seconds * SAMPLE_RATE)
    t = np.arange(n) / SAMPLE_RATE
    mono = np.zeros(n, dtype=np.float64)
    for harmonic, gain in enumerate((0.22, 0.13, 0.08, 0.05), start=1):
        mono += gain * np.sin(2 * np.pi * 110.0 * harmonic * t + seed)
    noise = rng.normal(0, 0.03, (n, 2))
    stereo = np.stack([mono, mono * 0.9], axis=1).astype(np.float32) + noise.astype(
        np.float32
    )

    cutoff = 16_000 if restored else 5_500
    spectrum = np.fft.rfft(stereo, axis=0)
    freqs = np.fft.rfftfreq(n, 1 / SAMPLE_RATE)
    rolloff = 1.0 / (1.0 + (freqs / cutoff) ** 4)
    stereo = np.fft.irfft(spectrum * rolloff[:, None], n=n, axis=0).astype(np.float32)
    if restored:
        stereo = apply_shelf(stereo, 9_000, 2.5).astype(np.float32)

    peak = float(np.max(np.abs(stereo))) or 1.0
    return (stereo / peak * 0.85).astype(np.float32)


def _write(path: Path, audio: np.ndarray) -> Path:
    import soundfile as sf

    from airlift.core.audio import SAMPLE_RATE

    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, audio, SAMPLE_RATE, subtype="PCM_16")
    return path


def _fill_queue(window, demo_dir: Path) -> None:
    """Queue the demo files and fake one finished job so the bands render."""
    from airlift.core.audio import band_levels, peak_dbfs, rms_dbfs
    from airlift.core.pipeline import EnhanceResult

    window._add_paths([demo_dir / name for name in FILES])
    window._set_status(1, "Processing", "Restoring · 45%")
    bar = window._row_progress(1)
    if bar:
        bar.setValue(45)

    source = demo_dir / next(iter(FILES))
    enhanced = _demo_audio(FILES[source.name], 1, restored=True)
    output = _write(demo_dir / f"{source.stem}.enhanced.air.wav", enhanced)
    window.results[str(source)] = EnhanceResult(
        source=source,
        output=output,
        duration=FILES[source.name],
        source_sample_rate=44_100,
        device="cpu",
        before=band_levels(_demo_audio(FILES[source.name], 1, restored=False)),
        after=band_levels(enhanced),
        peak=peak_dbfs(enhanced),
        rms=rms_dbfs(enhanced),
        clipped=0,
        elapsed=14.6,
    )
    window._set_status(0, "Done", str(output))
    done_bar = window._row_progress(0)
    if done_bar:
        done_bar.setValue(100)
    window._update_queue_ui()


def _spin(app, milliseconds: int) -> None:
    """Pump the event loop so media metadata reaches the transport widgets."""
    from PySide6.QtTest import QTest

    for _ in range(milliseconds // 50):
        QTest.qWait(50)
        app.processEvents()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(ROOT / "docs"), help="output folder")
    args = parser.parse_args()

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    # Keep the throwaway QSettings away from the developer's real config.
    os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="airlift-shot-")

    from PySide6.QtWidgets import QApplication

    from airlift import APP_NAME, ORG_NAME
    from airlift.ui.main_window import MainWindow
    from airlift.ui.theme import apply_theme

    demo_dir = Path(tempfile.mkdtemp(prefix="airlift-demo-"))
    for seed, (name, seconds) in enumerate(FILES.items(), start=1):
        _write(demo_dir / name, _demo_audio(seconds, seed, restored=False))

    app = QApplication([])
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORG_NAME)
    apply_theme(app)

    window = MainWindow()
    window.resize(1280, 800)
    window.show()
    app.processEvents()
    _fill_queue(window, demo_dir)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    def report(label: str) -> None:
        player = window.player
        print(
            f"  {label}: {player.badge.text()} {player.time_label.text()} · "
            f"{player.status.text()} · play={player.play_button.isEnabled()} "
            f"seek={player.slider.isVisible()}"
        )

    window.table.selectRow(0)
    window._show_detail(0)
    _spin(app, 900)
    report("enhanced row")
    main_shot = out / "screenshot.png"
    window.grab().save(str(main_shot))

    # One transport for every row — this is the state that used to hide it.
    window.table.selectRow(2)
    _spin(app, 900)
    report("pending row")
    transport_shot = out / "screenshot-transport.png"
    window.grab().save(str(transport_shot))

    print(f"wrote {main_shot}")
    print(f"wrote {transport_shot}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
