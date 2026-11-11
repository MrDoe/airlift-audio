"""Headless CLI for Airlift Audio (no Qt import)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

from . import APP_NAME, __version__
from .core.apollo import ApolloRestorer, describe_device, resolve_device
from .core.audio import (
    SAMPLE_RATE,
    apply_shelf,
    band_labels,
    band_levels,
    decode,
    make_ab_clip,
    measure_lufs,
)
from .core.pipeline import AUDIO_SUFFIXES, EnhanceOptions, enhance_file
from .core.stems import (
    DEFAULT_MODEL,
    MODELS,
    DemucsUnavailable,
    StemOptions,
    resolve_python,
    separate_file,
)


def _collect(paths: list[str]) -> list[Path]:
    found: list[Path] = []
    for raw in paths:
        path = Path(raw).expanduser()
        if path.is_dir():
            for candidate in sorted(path.rglob("*")):
                if candidate.suffix.lower() in AUDIO_SUFFIXES and candidate.is_file():
                    found.append(candidate)
        elif path.is_file():
            found.append(path)
        else:
            print(f"skip: {path} (not found)", file=sys.stderr)
    return found


def _print_bands(before: dict[str, float], after: dict[str, float]) -> None:
    print(f"\n{'band':>10} {'before':>8} {'after':>8} {'delta':>8}")
    for label in band_labels():
        b, a = before.get(label), after.get(label)
        if b is None or a is None:
            continue
        print(f"{label:>10} {b:8.1f} {a:8.1f} {a - b:+8.1f}")


def cmd_enhance(args: argparse.Namespace) -> int:
    files = _collect(args.files)
    if not files:
        print("No audio files found.", file=sys.stderr)
        return 2

    restorer = ApolloRestorer(args.device, checkpoint=args.checkpoint)
    print(f"{APP_NAME} {__version__}")
    print(f"device: {describe_device(restorer.device)}")
    restorer.load(lambda stage, fraction: print(
        f"\r{stage} {fraction*100:3.0f}%", end="", flush=True))
    print()

    options = EnhanceOptions(
        shelf_db=args.shelf,
        shelf_freq=args.shelf_freq,
        fmt=args.format,
        output_dir=Path(args.output_dir).expanduser() if args.output_dir else None,
        chunk_seconds=args.chunk_seconds,
        overlap_seconds=args.overlap_seconds,
        pad_seconds=args.pad_seconds,
        batch_size=args.batch_size,
    )

    failures = 0
    for index, path in enumerate(files, 1):
        print(f"\n[{index}/{len(files)}] {path.name}")

        def progress(stage: str, fraction: float) -> None:
            if not args.quiet:
                print(f"\r  {stage:<12} {fraction*100:3.0f}%", end="", flush=True)

        try:
            result = enhance_file(path, options, restorer, progress=progress)
        except KeyboardInterrupt:
            print("\nCancelled.")
            return 130
        except Exception as exc:  # noqa: BLE001 — per-file failures must not abort the batch
            failures += 1
            print(f"\n  failed: {exc}", file=sys.stderr)
            continue
        print(f"\r  wrote {result.output}  ({result.elapsed:.1f}s)          ")
        _print_bands(result.before, result.after)
        print(f"  peak {result.peak:.1f} dBFS  rms {result.rms:.1f} dBFS")

    return 1 if failures else 0


def cmd_compare(args: argparse.Namespace) -> int:
    original_path = Path(args.original).expanduser()
    enhanced_path = Path(args.enhanced).expanduser()
    if not original_path.is_file() or not enhanced_path.is_file():
        print("Both files must exist.", file=sys.stderr)
        return 2

    original, _ = decode(original_path)
    enhanced, _ = decode(enhanced_path)
    if args.shelf:
        enhanced = apply_shelf(enhanced, args.shelf_freq, args.shelf)

    if not args.no_loudness_match:
        lufs_original = measure_lufs(original_path)
        lufs_enhanced = measure_lufs(enhanced_path)
        if lufs_original is not None and lufs_enhanced is not None:
            gain = 10 ** ((lufs_original - lufs_enhanced) / 20.0)
            enhanced = enhanced * gain
            print(f"loudness: {lufs_original:.1f} vs {lufs_enhanced:.1f} LUFS "
                  f"→ matched ({20*np.log10(gain):+.1f} dB)")

    clip = make_ab_clip(
        original, enhanced,
        start_seconds=args.start, seconds=args.seconds,
        block_seconds=args.block, repeats=args.repeats,
    )
    out = Path(args.out).expanduser() if args.out else enhanced_path.with_name(
        enhanced_path.stem + ".AB.wav"
    )
    sf.write(out, clip, SAMPLE_RATE, subtype="PCM_24")
    print(f"A/B clip: {out}  ({len(clip)/SAMPLE_RATE:.1f}s)")

    _print_bands(band_levels(original), band_levels(enhanced))
    return 0


def cmd_devices(_args: argparse.Namespace) -> int:
    import torch

    print(f"torch {torch.__version__}")
    print(f"cuda available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"  {torch.cuda.get_device_name(0)}")
    mps = getattr(torch.backends, "mps", None)
    print(f"mps available: {bool(mps and mps.is_available())}")
    print(f"auto selects: {resolve_device('auto')}")
    return 0


def cmd_separate(args: argparse.Namespace) -> int:
    files = _collect(args.files)
    if not files:
        print("No audio files found.", file=sys.stderr)
        return 2

    try:
        python = resolve_python(args.demucs_python)
        device = resolve_device(args.device)
    except (DemucsUnavailable, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(f"{APP_NAME} {__version__}")
    print(f"demucs: {python}")
    print(f"device: {describe_device(device)}")

    options = StemOptions(
        model=args.model,
        device=args.device,
        output_dir=Path(args.output_dir).expanduser() if args.output_dir else None,
        four_stems=args.four_stems,
        fmt=args.format,
        shifts=args.shifts,
        overlap=args.overlap,
        demucs_python=python,
    )

    failures = 0
    for index, path in enumerate(files, 1):
        print(f"\n[{index}/{len(files)}] {path.name}")

        def progress(stage: str, fraction: float) -> None:
            if not args.quiet:
                print(f"\r  {stage:<12} {fraction*100:3.0f}%", end="", flush=True)

        try:
            result = separate_file(path, options, progress=progress)
        except KeyboardInterrupt:
            print("\nCancelled.")
            return 130
        except Exception as exc:  # noqa: BLE001 — keep the batch alive
            failures += 1
            print(f"\n  failed: {exc}", file=sys.stderr)
            continue
        for label, output in result.outputs.items():
            print(f"\r  wrote {output}  ({label})                    ")
        print(f"  {result.elapsed:.1f}s on {describe_device(result.device)}")

    return 1 if failures else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="airlift-cli", description="Local AI music restoration (Apollo)."
    )
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    enhance = sub.add_parser("enhance", help="restore one or more files/folders")
    enhance.add_argument("files", nargs="+")
    enhance.add_argument("--shelf", type=float, default=2.5,
                         help="high-shelf boost in dB (0 disables; default 2.5)")
    enhance.add_argument("--shelf-freq", type=float, default=9_000,
                         help="shelf corner frequency in Hz (default 9000)")
    enhance.add_argument("--format", choices=["wav", "flac"], default="wav")
    enhance.add_argument("-o", "--output-dir", default=None)
    enhance.add_argument("--device", default="auto",
                         choices=["auto", "cpu", "cuda", "mps"])
    enhance.add_argument("--checkpoint", default=None)
    enhance.add_argument("--chunk-seconds", type=float, default=6.0)
    enhance.add_argument("--overlap-seconds", type=float, default=1.0)
    enhance.add_argument("--pad-seconds", type=float, default=1.0)
    enhance.add_argument("--batch-size", type=int, default=2)
    enhance.add_argument("--quiet", action="store_true")
    enhance.set_defaults(func=cmd_enhance)

    compare = sub.add_parser("compare", help="render an A/B clip")
    compare.add_argument("original")
    compare.add_argument("enhanced")
    compare.add_argument("-o", "--out", default=None)
    compare.add_argument("--start", type=float, default=0.0)
    compare.add_argument("--seconds", type=float, default=40.0)
    compare.add_argument("--block", type=float, default=8.0)
    compare.add_argument("--repeats", type=int, default=1)
    compare.add_argument("--shelf", type=float, default=0.0)
    compare.add_argument("--shelf-freq", type=float, default=9_000)
    compare.add_argument("--no-loudness-match", action="store_true")
    compare.set_defaults(func=cmd_compare)

    devices = sub.add_parser("devices", help="show torch device availability")
    devices.set_defaults(func=cmd_devices)

    separate = sub.add_parser(
        "separate", help="split tracks into vocals + instrumental (Demucs)"
    )
    separate.add_argument("files", nargs="+")
    separate.add_argument("--model", choices=list(MODELS), default=DEFAULT_MODEL)
    separate.add_argument("--device", default="auto",
                          choices=["auto", "cpu", "cuda", "mps"])
    separate.add_argument("-o", "--output-dir", default=None)
    separate.add_argument("--four-stems", action="store_true",
                          help="also write drums, bass and other")
    separate.add_argument("--format", choices=["wav", "flac"], default="wav")
    separate.add_argument("--shifts", type=int, default=1,
                          help="more shifts = better quality, slower (default 1)")
    separate.add_argument("--overlap", type=float, default=0.25)
    separate.add_argument("--demucs-python", default=None,
                          help="interpreter that can import demucs")
    separate.add_argument("--quiet", action="store_true")
    separate.set_defaults(func=cmd_separate)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
