# -*- mode: python ; coding: utf-8 -*-
# PyInstaller onedir ビルド設定（OpenCV 同梱の安定性優先）

from pathlib import Path

block_cipher = None
root = Path(SPECPATH)

a = Analysis(
    [str(root / "launcher.py")],
    pathex=[str(root.parent)],
    binaries=[],
    datas=[],
    hiddenimports=[
        "color_correct",
        "color_correct.gui",
        "color_correct.analyze",
        "color_correct.apply_ps",
        "color_correct.apply_local",
        "color_correct.apply_psd",
        "windnd",
        "win32com",
        "win32com.client",
        "pythoncom",
        "pywintypes",
        "cv2",
        "numpy",
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
    [],
    exclude_binaries=True,
    name="ColorCorrect",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX は誤検知・起動失敗の原因になりやすい
    console=False,  # GUI アプリ（コンソール非表示）
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="ColorCorrect",
)
