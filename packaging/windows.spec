# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


project_root = Path(SPECPATH).parent

a = Analysis(
    [str(project_root / "main_ui.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=[
        (str(project_root / "config_stream.yaml"), "."),
        (str(project_root / "sample_video"), "sample_video"),
    ],
    hiddenimports=["capture.screen_source.screenshot_win"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "capture.screen_source.screenshot_linux",
        "capture.screen_source.screenshot_mac",
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ESP32UDPScreenShareClient",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="ESP32UDPScreenShareClient",
)
