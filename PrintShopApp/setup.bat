@echo off
chcp 65001 > nul
title PrintShopApp Environment Setup Script

set "SETUP_NO_PAUSE="
if /i "%~1"=="nopause" set "SETUP_NO_PAUSE=1"

echo ===================================================
echo   Starting PrintShopApp (Python 3.11) Environment Setup
echo ===================================================
echo.

set "PYTHON_CMD="
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import sys; exit(0 if sys.version_info[:2] == (3, 11) else 1)" > nul 2>&1
    if not errorlevel 1 set "PYTHON_CMD=.venv\Scripts\python.exe"
)
if not defined PYTHON_CMD (
    python -c "import sys; exit(0 if sys.version_info[:2] == (3, 11) else 1)" > nul 2>&1
    if not errorlevel 1 set "PYTHON_CMD=python"
)
if not defined PYTHON_CMD if exist "C:\Espressif\tools\python\python.exe" (
    "C:\Espressif\tools\python\python.exe" -c "import sys; exit(0 if sys.version_info[:2] == (3, 11) else 1)" > nul 2>&1
    if not errorlevel 1 set "PYTHON_CMD=C:\Espressif\tools\python\python.exe"
)
if not defined PYTHON_CMD if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" -c "import sys; exit(0 if sys.version_info[:2] == (3, 11) else 1)" > nul 2>&1
    if not errorlevel 1 set "PYTHON_CMD=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
)
if not defined PYTHON_CMD if exist "C:\Program Files\Python311\python.exe" (
    "C:\Program Files\Python311\python.exe" -c "import sys; exit(0 if sys.version_info[:2] == (3, 11) else 1)" > nul 2>&1
    if not errorlevel 1 set "PYTHON_CMD=C:\Program Files\Python311\python.exe"
)
if not defined PYTHON_CMD (
    echo [ERROR] Python 3.11 is required, but a different version was found or Python is not recognized.
    echo Please ensure Python 3.11 is installed and added to your system PATH.
    goto error_exit
)

echo [1/5] Python 3.11 verification complete.
echo.

if exist .venv goto skip_venv
echo [2/5] Creating Python 3.11 virtual environment (.venv)...
"%PYTHON_CMD%" -m venv .venv
echo Virtual environment created.
goto check_packages

:skip_venv
echo [2/5] Existing virtual environment (.venv) found. Skipping.

:check_packages
echo.
echo [3/5] Checking package installation status...
call .venv\Scripts\activate.bat

python -c "import PySide6, Flask, qrcode, requests, pytest, pywinauto, win32api, win32con, win32event, psutil, pywin32, PyGithub, PIL, cryptography, winrt.windows.foundation, winrt.windows.networking.connectivity, winrt.windows.networking.networkoperators" > nul 2>&1
if %errorlevel% equ 0 goto skip_pip

echo [INFO] Installing required packages (including pytest, pywinauto)...
python -m pip install --upgrade pip > nul
pip install PySide6 colorlog Flask requests qrcode[pil] nicegui waitress PyMuPDF pywin32 PyGithub Pillow cryptography psutil pytest pywinauto winrt-Windows.Foundation winrt-Windows.Networking.Connectivity winrt-Windows.Networking.NetworkOperators
echo Package installation complete.
goto check_ssl

:skip_pip
echo [INFO] Required packages are already installed. Skipping installation.

:check_ssl
echo.
echo [4/5] Checking SSL certificates for HTTPS (LinkBox)...
if exist ..\secrets\cert.pem if exist ..\secrets\key.pem goto skip_ssl

echo [INFO] Generating self-signed SSL certificates via Python for LinkBox...
if not exist ..\secrets mkdir ..\secrets
python -c "from cryptography import x509; from cryptography.x509.name import Name; from cryptography.hazmat.primitives import hashes; from cryptography.hazmat.primitives.asymmetric import rsa; from cryptography.hazmat.primitives import serialization; import datetime; priv_key = rsa.generate_private_key(public_exponent=65537, key_size=2048); subj = x509.Name([x509.NameAttribute(x509.oid.NameOID.COMMON_NAME, 'PrintShopServer')]); cert = x509.CertificateBuilder().subject_name(subj).issuer_name(subj).public_key(priv_key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(datetime.datetime.now(datetime.timezone.utc)).not_valid_after(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=365)).sign(priv_key, hashes.SHA256()); open(r'..\secrets\cert.pem', 'wb').write(cert.public_bytes(serialization.Encoding.PEM)); open(r'..\secrets\key.pem', 'wb').write(priv_key.private_bytes(encoding=serialization.Encoding.PEM, format=serialization.PrivateFormat.PKCS8, encryption_algorithm=serialization.NoEncryption()))"
echo SSL certificates generated successfully in the project secrets folder.
goto check_libreoffice

:skip_ssl
echo [INFO] SSL certificates already exist. Skipping.

:check_libreoffice
echo.
echo [INFO] Checking LibreOffice installation...
if exist "C:\Program Files\LibreOffice\program\soffice.exe" (
    echo [INFO] LibreOffice가 이미 설치되어 있습니다. (경로 확인됨)
    goto create_folder
)
if exist "C:\Program Files (x86)\LibreOffice\program\soffice.exe" (
    echo [INFO] LibreOffice가 이미 설치되어 있습니다. (32비트 경로 확인됨)
    goto create_folder
)

:: winget을 통한 설치 여부 확인
winget list --id TheDocumentFoundation.LibreOffice --exact >nul 2>&1
if %errorlevel% equ 0 (
    echo [INFO] LibreOffice가 이미 설치되어 있습니다. (winget 확인됨)
    goto create_folder
)

REM 1. winget을 이용한 LibreOffice 자동 설치 (선택사항)
echo LibreOffice가 감지되지 않았습니다. 설치를 진행합니다...
winget install TheDocumentFoundation.LibreOffice --accept-source-agreements --accept-package-agreements

:create_folder
echo.
echo [5/5] Checking and creating project directories (templates, fare, LinkBox_Files)...
if not exist LinkBox\templates mkdir LinkBox\templates
if not exist LinkShare\templates mkdir LinkShare\templates
if not exist LinkBox\LinkBox_Files mkdir LinkBox\LinkBox_Files
if not exist LinkShare\fare mkdir LinkShare\fare

echo.
echo ===================================================
echo   PrintShopApp environment setup is complete!
echo   You can run 'run.bat' to start the program.
echo ===================================================
echo.
if not defined SETUP_NO_PAUSE pause
exit /b

:error_exit
echo.
echo [FAILED] Setup terminated due to an error.
if not defined SETUP_NO_PAUSE pause
exit /b