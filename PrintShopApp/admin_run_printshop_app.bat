@echo off
chcp 65001 > nul
title PrintShopApp Administrator Launcher

cd /d "%~dp0"
echo [INFO] Calling PrintShopApp administrator launcher...
call "%~dp0admin_run.bat"
set "EXIT_CODE=%errorlevel%"
echo [INFO] PrintShopApp administrator launcher finished: exit_code=%EXIT_CODE%
exit /b %EXIT_CODE%
