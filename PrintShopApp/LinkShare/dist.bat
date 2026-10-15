@echo off
chcp 65001 > nul

setlocal
echo ========================================================
echo   Wi-Fi Management System - Packaging (.venv / Python 3.11)
echo ========================================================

if not exist .venv (
    echo [Error] Virtual environment (.venv) not found. Please run setup.bat first.
    pause
    exit /b
)

echo [1/2] Cleaning up previous build files...
if exist build rmdir /s /q build
if exist wifi_full_app.spec del wifi_full_app.spec

echo [2/2] Building executable with PyInstaller inside .venv...
call .venv\Scripts\activate
pyinstaller --noconsole --onedir --add-data "templates;templates" wifi_full_app.py

echo ========================================================
echo Packaging complete!
echo Output folder: .\dist\wifi_full_app\
echo * Note: Ensure the 'templates' folder is included when distributing.
echo ========================================================
pause