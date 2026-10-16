@echo off
chcp 65001 > nul

setlocal
cd /d "%~dp0.."
echo ========================================================
echo   Starting Wi-Fi Management System (.venv / Python 3.11)
echo ========================================================

if exist main_app.exe (
    echo [INFO] Starting the packaged PrintShopApp executable...
    main_app.exe
    exit /b
)

if not exist .venv (
    echo [Error] Virtual environment (.venv) not found. Please run setup.bat first.
    pause
    exit /b
)

call .venv\Scripts\activate
python main_app.py

rem pause
