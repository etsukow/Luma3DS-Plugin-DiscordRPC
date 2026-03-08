# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the 3DS Discord RPC client."""

block_cipher = None

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=[],
    datas=[
        # Bundle .env.example so the frozen app can reference default values.
        (".env.example", "."),
    ],
    hiddenimports=[
        "websocket",
        "pypresence",
        # Windows: winreg is a built-in but PyInstaller may miss it on cross-builds.
        "winreg",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="3DS-DiscordRPC",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    # Keep a console window so logs are visible; set to True to hide it.
    console=True,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

