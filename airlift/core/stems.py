"""Demucs stem separation: split a track into vocals and instrumental.

Demucs is optional. It is not bundled with the installers; the app looks for a
Python interpreter that can import it (see :func:`resolve_python`). Separation
runs in a subprocess so a crash or a cancel cannot take the GUI down, and so a
Demucs install in a different virtualenv works.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import soundfile as sf

from .apollo import CancelledError, resolve_device

Progress = Callable[[str, float], None]
CancelCheck = Callable[[], bool]

DEFAULT_MODEL = "htdemucs"
MODELS = ("htdemucs", "htdemucs_ft", "mdx_extra", "mdx_q")

# Demucs file stem -> human label used in the output file name.
STEM_LABELS = {
    "vocals": "vocals",
    "no_vocals": "instrumental",
    "drums": "drums",
    "bass": "bass",
    "other": "other",
}

_PERCENT = re.compile(r"(\d{1,3})%")
_AVAILABLE: dict[str, bool] = {}


class DemucsUnavailable(RuntimeError):
    """No Python interpreter with a working Demucs install was found."""


@dataclass
class StemOptions:
    model: str = DEFAULT_MODEL
    device: str = "auto"
    output_dir: Path | None = None
    four_stems: bool = False
    fmt: str = "wav"
    shifts: int = 1
    overlap: float = 0.25
    demucs_python: str | None = None


@dataclass
class StemResult:
    source: Path
    outputs: dict[str, Path] = field(default_factory=dict)
    model: str = DEFAULT_MODEL
    device: str = "cpu"
    elapsed: float = 0.0


def has_demucs(python: str) -> bool:
    """True when ``python -c "import demucs"`` succeeds (cached)."""
    if python in _AVAILABLE:
        return _AVAILABLE[python]
    if not Path(python).expanduser().is_file():
        _AVAILABLE[python] = False
        return False
    try:
        proc = subprocess.run(
            [python, "-c", "import demucs"],
            capture_output=True,
            timeout=30,
            check=False,
        )
        ok = proc.returncode == 0
    except (OSError, subprocess.SubprocessError):
        ok = False
    _AVAILABLE[python] = ok
    return ok


def resolve_python(explicit: str | None = None) -> str:
    """Find an interpreter that can run Demucs.

    Order: explicit argument, ``AIRLIFT_DEMUCS_PYTHON``, the current
    interpreter. Raises :class:`DemucsUnavailable` with install hints.
    """
    candidates = [
        explicit,
        os.environ.get("AIRLIFT_DEMUCS_PYTHON"),
    ]
    # In a PyInstaller bundle sys.executable is the GUI itself, not a Python
    # interpreter: `-c "import demucs"` would launch (and hang) the app.
    if not getattr(sys, "frozen", False):
        candidates.append(sys.executable)
    tried: list[str] = []
    for candidate in candidates:
        if not candidate:
            continue
        python = str(Path(candidate).expanduser())
        if python in tried:
            continue
        tried.append(python)
        if has_demucs(python):
            return python

    raise DemucsUnavailable(
        "Demucs is not available. Install it into this environment "
        '("pip install demucs", with a torchaudio that matches torch), or point '
        "AIRLIFT_DEMUCS_PYTHON (or --demucs-python) at a Python that already "
        "imports demucs. Tried: " + ", ".join(tried)
    )


def build_command(
    python: str, source: Path, work_dir: Path, options: StemOptions, device: str
) -> list[str]:
    """Demucs command line for one track."""
    command = [
        python,
        "-m",
        "demucs",
        "-n",
        options.model,
        "-d",
        device,
        "-o",
        str(work_dir),
    ]
    if not options.four_stems:
        command += ["--two-stems", "vocals"]
    if options.shifts > 1:
        command += ["--shifts", str(options.shifts)]
    if options.overlap != 0.25:
        command += ["--overlap", str(options.overlap)]
    command.append(str(source))
    return command


def unique_path(path: Path) -> Path:
    """Return ``path`` or ``name (2).ext`` / ``name (3).ext`` if taken."""
    if not path.exists():
        return path
    for index in range(2, 1000):
        candidate = path.with_name(f"{path.stem} ({index}){path.suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Could not find a free file name for {path}")


def _discover(work_dir: Path) -> dict[str, Path]:
    """Map Demucs' output stems to label -> path."""
    found: dict[str, Path] = {}
    for wav in sorted(work_dir.rglob("*.wav")):
        label = STEM_LABELS.get(wav.stem.lower())
        if label and label not in found:
            found[label] = wav
    return found


def _terminate(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def _read_stderr(proc: subprocess.Popen, chunks: list[bytes]) -> None:
    stream = proc.stderr
    if stream is None:
        return
    read = getattr(stream, "read1", stream.read)
    while True:
        try:
            chunk = read(4096)
        except (OSError, ValueError):
            return
        if not chunk:
            return
        chunks.append(chunk)


def _write_stem(src: Path, dst: Path, fmt: str) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "flac":
        data, rate = sf.read(src, always_2d=True, dtype="float32")
        peak = float(np.max(np.abs(data))) if data.size else 0.0
        if peak > 1.0:
            data = np.clip(data, -1.0, 1.0)
        sf.write(dst, data, rate, subtype="PCM_24")
    else:
        shutil.move(str(src), str(dst))


def separate_file(
    source: str | Path,
    options: StemOptions | None = None,
    *,
    progress: Progress | None = None,
    cancel: CancelCheck | None = None,
) -> StemResult:
    """Separate one file with Demucs and write the stems next to it.

    Two-stem mode (default) yields ``<name>.vocals.wav`` and
    ``<name>.instrumental.wav``; ``four_stems`` adds drums, bass and other.
    """
    options = options or StemOptions()
    source = Path(source).expanduser()
    if not source.is_file():
        raise FileNotFoundError(f"No such file: {source}")
    emit = progress or (lambda stage, fraction: None)
    started = time.time()

    emit("Checking Demucs", 0.02)
    python = resolve_python(options.demucs_python)
    device = resolve_device(options.device)

    with tempfile.TemporaryDirectory(prefix="airlift-demucs-") as tmp:
        work_dir = Path(tmp)
        command = build_command(python, source, work_dir, options, device)
        emit("Loading Demucs", 0.05)

        env = dict(os.environ)
        env["PYTHONUNBUFFERED"] = "1"
        kwargs: dict = {}
        if os.name == "posix":
            kwargs["start_new_session"] = True
        proc = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            env=env,
            **kwargs,
        )
        chunks: list[bytes] = []
        reader = threading.Thread(target=_read_stderr, args=(proc, chunks), daemon=True)
        reader.start()

        seen_pct = -1
        consumed = 0
        try:
            while proc.poll() is None:
                if cancel and cancel():
                    _terminate(proc)
                    raise CancelledError("Cancelled")
                if consumed < len(chunks):
                    text = b"".join(chunks[consumed:]).decode("utf-8", "replace")
                    consumed = len(chunks)
                    matches = _PERCENT.findall(text)
                    if matches:
                        pct = max(0, min(100, int(matches[-1])))
                        if pct != seen_pct:
                            seen_pct = pct
                            emit("Separating", 0.08 + 0.84 * pct / 100.0)
                time.sleep(0.1)
        finally:
            reader.join(timeout=2)

        stderr = b"".join(chunks).decode("utf-8", "replace")
        if proc.returncode != 0:
            tail = stderr.strip().splitlines()[-12:]
            detail = "\n".join(tail) or f"exit code {proc.returncode}"
            raise RuntimeError(f"Demucs failed: {detail}")

        emit("Writing stems", 0.94)
        found = _discover(work_dir)
        if "vocals" not in found:
            raise RuntimeError("Demucs finished but produced no vocals stem.")

        output_dir = Path(options.output_dir).expanduser() if options.output_dir else source.parent
        output_dir.mkdir(parents=True, exist_ok=True)

        outputs: dict[str, Path] = {}
        order = ["vocals", "instrumental", "drums", "bass", "other"]
        for label in order:
            src = found.get(label)
            if src is None:
                continue
            dst = unique_path(_output_name_in(output_dir, source, label, options.fmt))
            _write_stem(src, dst, options.fmt)
            outputs[label] = dst

    emit("Done", 1.0)
    return StemResult(
        source=source,
        outputs=outputs,
        model=options.model,
        device=device,
        elapsed=time.time() - started,
    )


def _output_name_in(folder: Path, source: Path, label: str, fmt: str) -> Path:
    ext = ".flac" if fmt == "flac" else ".wav"
    return folder / f"{source.stem}.{label}{ext}"
