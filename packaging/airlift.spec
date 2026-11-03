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
]

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "pytest", "IPython", "notebook", "pandas"],
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
            "CFBundleShortVersionString": "0.1.0",
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "12.0",
        },
    )
