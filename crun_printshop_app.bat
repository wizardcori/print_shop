@echo off
chcp 65001 > nul
title PrintShopApp Runner

echo ===================================================
echo   Starting PrintShopApp...
echo ===================================================
echo.

call "%~dp0PrintShopApp\run.bat" %*
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo [FAILED] PrintShopApp terminated with error code %EXIT_CODE%.
    exit /b %EXIT_CODE%
)

echo.
echo [OK] PrintShopApp finished successfully.
exit /b 0
