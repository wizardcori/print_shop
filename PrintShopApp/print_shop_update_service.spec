# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['C:/1print_shop/PrintShopApp/src/UpdateService/print_shop_update_service.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['win32timezone', 'win32service', 'win32serviceutil', 'win32event', 'servicemanager'],
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
    a.binaries,         # 👈 추가: 바이너리를 EXE 내부로 병합
    a.zipfiles,         # 👈 추가
    a.datas,            # 👈 추가: 데이터 파일들을 EXE 내부로 병합
    [],
    name='print_shop_update_service',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,       # 서비스 콘솔 출력 유지 여부 (필요시 False 가능)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version='version_info.txt', # 필요시 버전 리소스 연결
)
