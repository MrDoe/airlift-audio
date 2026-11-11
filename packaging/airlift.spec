# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Airlift Audio (one-folder build)."""

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
    "airlift.core.stems",
    "airlift.cli",
    "airlift.ui",
    "airlift.ui.main_window",
    "airlift.ui.player",
    "airlift.ui.stem_dialog",
    "airlift.ui.theme",
    "airlift.ui.worker",
]

# Build with a CPU-only torch wheel. PyInstaller's CUDA hook cannot resolve
# cuDNN 9.x's split .so files, so shipping a CUDA build breaks GPU inference
# (cudnnFinalize). The env guard below fails loud if CI drifts.
import torch as _torch

if _torch.cuda.is_available():
    raise SystemExit(
        "Refusing to build: torch reports CUDA available. Build with a CPU wheel "
        "(pip install torch --index-url https://download.pytorch.org/whl/cpu)."
    )

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={"torch": {"disable_cuda": True}},
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
        # CUDA payload, if a CUDA wheel ever leaks into the build env:
        "nvidia",
        "torch._C._cuda",
        # NOTE: do NOT exclude torch.cuda or torch.distributed — torch/__init__
        # and torch.utils.data import them unconditionally, and excluding them
        # raises ModuleNotFoundError at import time.
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
    name="Airlift Audio",
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
    name="Airlift Audio",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Airlift Audio.app",
        icon=str(icon) if icon.exists() else None,
        bundle_identifier="audio.airlift.app",
        info_plist={
            "CFBundleName": "Airlift Audio",
            "CFBundleDisplayName": "Airlift Audio",
            "CFBundleShortVersionString": "0.1.3",
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "12.0",
        },
    )
