@echo off
chcp 65001 > nul

echo ========================================================
echo Wi-Fi Management System - Python 3.11 Environment Setup
echo ========================================================

echo [1/3] Creating Python 3.11 virtual environment (.venv without pip)...
python -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)"
if errorlevel 1 (
    echo.
    echo [Error] Python 3.11 or higher is required.
    pause
    exit /b
)

:: --without-pip 옵션을 사용하여 멈춤 현상(ensurepip 버그) 우회
python -m venv .venv --without-pip
if errorlevel 1 (
    echo.
    echo [Error] Failed to create virtual environment (.venv).
    pause
    exit /b
)

echo [2/3] Activating virtual environment and installing pip & packages...
call .venv\Scripts\activate

:: get-pip.py를 통해 안전하게 pip 수동 설치
python -m ensurepip --default-pip >nul 2>&1
if errorlevel 1 (
    echo Downloading get-pip.py installer...
    python -c "import urllib.request; urllib.request.urlretrieve('https://bootstrap.pypa.io/get-pip.py', 'get-pip.py')"
    python get-pip.py
    if exist get-pip.py del get-pip.py
)

python -m pip install --upgrade pip
pip install PySide6 qrcode[pil] flask cryptography pyinstaller

echo [3/3] Creating required directories...
if not exist templates mkdir templates
if not exist fare mkdir fare

echo ========================================================
echo [Setup Complete!] Environment setup is finished.
echo You can now run run.bat to start the application.
echo ========================================================
pause