# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['src/main_app.py'],
    pathex=['.', 'src'],
    binaries=[('C:/Espressif/tools/python/python311.dll', '.'), ('C:/Espressif/tools/python/vcruntime140.dll', '.'), ('C:/Espressif/tools/python/vcruntime140_1.dll', '.')],
    datas=[('LinkBox/templates', 'LinkBox/templates'), ('LinkShare/templates', 'LinkShare/templates'), ('.env.feature.runtime', '.'), ('LinkBox/src/ui', 'LinkBox/src/ui')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['LinkBox.src.printer_monitor_service'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='PrintShopApp',
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
    name='PrintShopApp',
)
