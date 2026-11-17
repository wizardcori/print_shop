@echo off
chcp 65001 > nul
set "SOURCE_DIR=%~dp0"
cd /d "%SOURCE_DIR%"

:: 1. 가상환경 Python 및 VersionManager 경로 설정
set "PYTHON_PATH="
for %%i in ("%SOURCE_DIR%\..\..\.venv\Scripts\python.exe") do set "PYTHON_PATH=%%~fi"
if not exist "%PYTHON_PATH%" set "PYTHON_PATH=python"

set "VERSION_MANAGER_PATH="
for %%i in ("%SOURCE_DIR%\..\Common\version_manager.py") do set "VERSION_MANAGER_PATH=%%~fi"

echo ========================================================
echo  [1/5] 버전 자동 증가 처리 중...
echo ========================================================

:: 1. 버전 관리 스크립트 실행 (버전 증가 및 파일 갱신)
"%PYTHON_PATH%" "%VERSION_MANAGER_PATH%" patch --dir "."

:: 2. 갱신된 version.txt 파일에서 새 버전 읽어오기
set "NEW_VERSION="
if exist "version.txt" (
    set /p NEW_VERSION=<version.txt
)

if "%NEW_VERSION%"=="" (
    echo [오류] 버전 업데이트에 실패했습니다. 경로를 확인하세요.
    pause
    exit /b
)

echo [성공] 업그레이드된 버전: %NEW_VERSION% (version.txt, version.py 반영 완료)


:: 2. 가상환경 PyInstaller 경로 설정
set "PYINST_PATH="
for %%i in ("%SOURCE_DIR%\..\..\.venv\Scripts\pyinstaller.exe") do set "PYINST_PATH=%%~fi"
if not exist "%PYINST_PATH%" (
    for %%i in ("%SOURCE_DIR%\venv\Scripts\pyinstaller.exe") do set "PYINST_PATH=%%~fi"
)
echo [알림] 빌드 도구 경로: %PYINST_PATH%

:: 3. 관리자 권한 체크
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [오류] 관리자 권한이 필요합니다. 우클릭 후 [관리자 권한으로 실행]해주세요.
    pause
    exit /b
)

:: 4. PyInstaller로 실행 파일(.exe) 빌드
echo [2/5] print_shop_update_service.py 실행 파일 빌드 중...
"%PYINST_PATH%" --onefile --clean --hidden-import=win32timezone --hidden-import=win32service --hidden-import=win32serviceutil --hidden-import=win32event --hidden-import=servicemanager print_shop_update_service.py

if not exist "dist\print_shop_update_service.exe" (
    echo [오류] EXE 빌드에 실패했습니다. PyInstaller 설치 상태를 확인하세요.
    pause
    exit /b
)

:: 5. 설치 폴더 설정 및 파일 복사
set "INSTALL_DIR=C:\Program Files\PrintShopApp"
echo [3/5] 설치 폴더 생성 및 파일 복사 중 (%INSTALL_DIR%)...
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"

:: 기존 서비스 실행 중이면 중지
"%INSTALL_DIR%\print_shop_update_service.exe" stop >nul 2>&1
timeout /t 2 /nobreak >nul

copy /y "dist\print_shop_update_service.exe" "%INSTALL_DIR%\"
if exist "PrintShopApp.exe" copy /y "PrintShopApp.exe" "%INSTALL_DIR%\"

:: 6. 서비스 등록 및 시작
echo [4/5] 윈도우 서비스 등록 및 시작 중...
cd /d "%INSTALL_DIR%"
print_shop_update_service.exe remove >nul 2>&1
print_shop_update_service.exe install
print_shop_update_service.exe start

:: 7. 상태 점검
echo [5/5] 서비스 상태 점검:
sc query PSUpdateService

echo ========================================================
echo  [완료] 버전 %NEW_VERSION% 로 배포 및 서비스 등록이 완료되었습니다!
echo ========================================================
pause
