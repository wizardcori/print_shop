# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    [r'main_app.py'],
    pathex=[r'.', r'C:/1a/PrintShopApp', r'C:/1a/PrintShopApp/src'],
    binaries=[],
    datas=[(r'C:/1a/PrintShopApp/src/LinkBox/templates', 'LinkBox/templates'), (r'C:/1a/PrintShopApp/src/LinkShare/web/templates', 'LinkShare/web/templates'), (r'C:/1a/PrintShopApp/.env.feature.runtime', '.')],
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
    name=f'PrintShopApp',
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
    uac_admin=False,
    icon=None,
    version=r'version_info.txt',
)
