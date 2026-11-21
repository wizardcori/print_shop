# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    [r'C:\1print_shop\PrintShopApp\src\UpdateService\main_app.py'],
    pathex=[r'C:\1print_shop\PrintShopApp', r'C:\1print_shop\PrintShopApp\src'],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name=f'PrintShopUpdateService',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=r'C:\1print_shop\PrintShopApp\src\UpdateService\version_info.txt',
)
