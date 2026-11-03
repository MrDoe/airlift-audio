#!/usr/bin/env python3
"""Release gate: fail if the build environment leaks CUDA into the bundle.

Executable manually or from CI before invoking PyInstaller.
"""

from __future__ import annotations

import subprocess
import sys


def main() -> int:
    import torch

    if torch.cuda.is_available():
        print(
            "ERROR: torch reports CUDA available. Build from a CPU-only wheel: "
            "pip install torch --index-url https://download.pytorch.org/whl/cpu",
            file=sys.stderr,
        )
        return 1

    leaked = subprocess.run(
        [sys.executable, "-m", "pip", "show", "nvidia-cudnn-cu12"],
        capture_output=True, text=True,
    )
    if leaked.returncode == 0 and "nvidia-cudnn-cu12" in leaked.stdout:
        print(
            "ERROR: nvidia-cudnn-cu12 is installed. PyInstaller's CUDA hook "
            "cannot bundle cuDNN 9.x split libraries; uninstall it.",
            file=sys.stderr,
        )
        return 1

    print(f"OK: torch {torch.__version__} is CPU-only, no cuDNN leakage.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
