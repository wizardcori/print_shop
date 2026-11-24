# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    [r'C:\1print_shop\PrintShopApp\src\BuildManagerApp\main_app.py'],
    pathex=[r'C:\\1print_shop\\PrintShopApp', r'C:\\1print_shop\\PrintShopApp\\src', r'C:\\1print_shop\\PrintShopApp\\src\\build_script'],
    binaries=[],
    datas=[],
    hiddenimports=['env_ui_helper', 'build_script.env_ui_helper', 'packaging_service', 'build_script.packaging_service', 'spec_builder', 'build_script.spec_builder', 'target_config_io', 'build_script.target_config_io', 'version_service', 'build_script.version_service'],
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
    name=f'PrintShopBuildManagerApp',
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
    version=r'C:\1print_shop\PrintShopApp\src\BuildManagerApp\version_info.txt',
)
