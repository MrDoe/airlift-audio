# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Airlift Audio — CUDA variant (GPU-enabled bundle).

Built with a CUDA torch wheel (e.g. ~/.venvs/airlift-dev, torch 2.15.0+cu132).
Unlike the CPU spec, this keeps the nvidia/* payload and requires CUDA.
Output folder is "Airlift Audio CUDA" so it coexists with the CPU bundle.
"""

import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent
ASSETS = ROOT / "airlift" / "assets"
APOLLO = ROOT / "airlift" / "third_party" / "apollo"

datas = [
    (str(ASSETS), "airlift/assets"),
    (str(APOLLO), "airlift/third_party/apollo"),
]

hiddenimports = [
    "look2hear",
    "look2hear.models",
    "look2hear.models.apollo",
    "look2hear.models.base_model",
    "omegaconf",
    "omegaconf.base",
    "omegaconf.dictconfig",
    "omegaconf.listconfig",
    "platformdirs",
    "imageio_ffmpeg",
    "soundfile",
    "scipy.signal",
    "PySide6.QtMultimedia",
    # Airlift's own subpackages: launcher.py only imports airlift.app, so
    # PyInstaller's static analysis never sees core/cli/ui.
    "airlift.core",
    "airlift.core.apollo",
    "airlift.core.audio",
    "airlift.core.pipeline",
    "airlift.cli",
    "airlift.ui",
    "airlift.ui.main_window",
    "airlift.ui.player",
    "airlift.ui.theme",
    "airlift.ui.worker",
]

# CUDA build: require a CUDA-capable torch. If this fires, you invoked the
# wrong spec (use packaging/airlift.spec with a CPU-only wheel instead).
import torch as _torch

if not _torch.cuda.is_available():
    raise SystemExit(
        "Refusing CUDA build: torch reports no CUDA. Build with a CUDA wheel "
        "(e.g. ~/.venvs/airlift-dev) or use packaging/airlift.spec for CPU."
    )

# Pin GPU libs from the same prefix as torch. airlift-dev carries an
# airlift-shared.pth exposing an older venv (audio-enhance, torch 2.8/cu12)
# on sys.path; PyInstaller's nvidia.* hooks can otherwise collect stale
# libraries (e.g. libnccl.so.2 2.27.3, missing ncclCommResume) instead of the
# ones torch 2.15+cu132 requires. User-supplied binaries win TOC dedup, so
# these explicit pins take precedence over hook entries.
#
# The nvidia/cu13 mega-package (libnvrtc et al.) has NO PyInstaller hook, so
# its libraries only enter via binary-dependency analysis (DT_NEEDED). Files
# loaded with dlopen at runtime — notably libnvrtc-builtins.so, which
# libnvrtc requires in its own directory for torch.compile/Inductor kernels
# — are silently dropped without this pin.
_SITE = Path(_torch.__file__).resolve().parent.parent
_PINNED_LIB_DIRS: tuple[tuple[str, str], ...] = (
    ("nvidia/nccl/lib", "nvidia/nccl/lib"),  # NCCL (undefined-symbol risk)
    ("nvidia/cu13/lib", "nvidia/cu13/lib"),  # CUDA toolkit inc. NVRTC
)
_cuda_binaries: list[tuple[str, str]] = []
for _src_rel, _dst in _PINNED_LIB_DIRS:
    _found = sorted((_SITE / _src_rel).glob("lib*.so*"))
    _cuda_binaries.extend((str(p), _dst) for p in _found)
if not any("libnccl.so" in Path(s).name for s, _ in _cuda_binaries):
    raise SystemExit(f"CUDA build: no libnccl found under {_SITE}")
if not any("libnvrtc-builtins" in Path(s).name for s, _ in _cuda_binaries):
    raise SystemExit(f"CUDA build: no libnvrtc-builtins found under {_SITE}")

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT)],
    binaries=_cuda_binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "pytest",
        "IPython",
        "notebook",
        "pandas",
        "torchvision",
        "torchaudio",
        # NOTE: do NOT exclude nvidia / torch._C._cuda / torch.cuda /
        # torch.distributed here — the GPU bundle needs all of them.
        # torch/__init__ and torch.utils.data import torch.cuda and
        # torch.distributed unconditionally; excluding them raises
        # ModuleNotFoundError at import time.
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

icon = ASSETS / ("icon.ico" if sys.platform == "win32" else "icon.icns")
icon_arg = str(icon) if icon.exists() else None

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Airlift Audio CUDA",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=icon_arg,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Airlift Audio CUDA",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Airlift Audio CUDA.app",
        icon=str(icon) if icon.exists() else None,
        bundle_identifier="audio.airlift.app.cuda",
        info_plist={
            "CFBundleName": "Airlift Audio CUDA",
            "CFBundleDisplayName": "Airlift Audio CUDA",
            "CFBundleShortVersionString": "0.1.0",
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "12.0",
        },
    )
