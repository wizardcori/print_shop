@echo off
chcp 65001 > nul
title LinkBox Launcher

if not exist .venv goto error_no_venv
if not exist cert.pem goto error_no_ssl
if not exist key.pem goto error_no_ssl

call .venv\Scripts\activate.bat
python linkbox_app.py
pause
exit /b

:error_no_venv
echo [ERROR] Virtual environment (.venv) not found. Run setup.bat first.
pause
exit /b

:error_no_ssl
echo [ERROR] SSL certificate files (cert.pem / key.pem) not found. Run setup.bat first.
pause
exit /b