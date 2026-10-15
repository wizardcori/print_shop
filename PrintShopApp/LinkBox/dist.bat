@echo off
chcp 65001 > nul
title LinkBox PyInstaller Builder

if not exist .venv goto error_venv
if not exist cert.pem goto error_ssl
if not exist key.pem goto error_ssl

echo [1/3] Activating virtual environment...
call .venv\Scripts\activate.bat

echo [2/3] Installing PyInstaller...
pip install pyinstaller > nul 2>&1

echo [3/3] Building HTTPS executable (please wait)...
pyinstaller --noconsole --onefile --name="LinkBox" --add-data "templates;templates" --add-data "cert.pem;." --add-data "key.pem;." linkbox_app.py

echo.
echo ===================================================
echo   Build complete! 
echo   Check the 'dist' folder for 'LinkBox.exe'.
echo ===================================================
pause
exit /b

:error_venv
echo [ERROR] Virtual environment (.venv) not found. Run setup.bat first.
pause
exit /b

:error_ssl
echo [ERROR] SSL certificate files (cert.pem / key.pem) are missing. Run setup.bat first.
pause
exit /b