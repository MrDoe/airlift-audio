from __future__ import annotations

from airlift.cli import build_parser


def test_enhance_defaults():
    args = build_parser().parse_args(["enhance", "song.wav"])
    assert args.shelf == 2.5
    assert args.format == "wav"
    assert args.chunk_seconds == 6.0
    assert args.device == "auto"


def test_compare_defaults():
    args = build_parser().parse_args(["compare", "a.wav", "b.wav"])
    assert args.seconds == 40.0
    assert args.block == 8.0
