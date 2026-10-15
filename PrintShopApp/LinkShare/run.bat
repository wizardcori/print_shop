@echo off
chcp 65001 > nul

setlocal
echo ========================================================
echo   Starting Wi-Fi Management System (.venv / Python 3.11)
echo ========================================================

if not exist .venv (
    echo [Error] Virtual environment (.venv) not found. Please run setup.bat first.
    pause
    exit /b
)

call .venv\Scripts\activate
python wifi_full_app.py

pause