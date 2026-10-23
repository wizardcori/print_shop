@echo off
chcp 65001 > nul
title PrintShopApp Launcher

cd /d "%~dp0"
echo [INFO] Calling PrintShopApp standard launcher...
call "%~dp0run.bat"
set "EXIT_CODE=%errorlevel%"
echo [INFO] PrintShopApp standard launcher finished: exit_code=%EXIT_CODE%
exit /b %EXIT_CODE%
