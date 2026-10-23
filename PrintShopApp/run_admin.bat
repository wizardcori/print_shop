@echo off
chcp 65001 > nul
title PrintShopApp Administrator Launcher (Compatibility)

cd /d "%~dp0"
echo [INFO] Redirecting legacy run_admin.bat to admin_run.bat...
call "%~dp0admin_run.bat"
set "EXIT_CODE=%errorlevel%"
echo [INFO] Legacy administrator launcher finished: exit_code=%EXIT_CODE%
exit /b %EXIT_CODE%
