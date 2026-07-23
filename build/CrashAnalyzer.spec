# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = []
hiddenimports += collect_submodules('uvicorn')


a = Analysis(
    ['C:\\Users\\alexanderm\\Desktop\\Crash_Analyzer\\build\\entry.py'],
    pathex=['C:\\Users\\alexanderm\\Desktop\\Crash_Analyzer'],
    binaries=[],
    datas=[('C:\\Users\\alexanderm\\Desktop\\Crash_Analyzer\\src\\web', 'src/web'), ('C:\\Users\\alexanderm\\Desktop\\Crash_Analyzer\\src\\kb', 'src/kb'), ('C:\\Users\\alexanderm\\Desktop\\Crash_Analyzer\\VERSION', '.')],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='CrashAnalyzer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['C:\\Users\\alexanderm\\Desktop\\Crash_Analyzer\\build\\CrashAnalyzer.ico'],
)
