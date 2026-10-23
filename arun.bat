@echo off
chcp 65001 > nul
title PrintShop Launcher

echo ===================================================
echo   Starting PrintShop...
echo ===================================================
echo.

call "%~dp0PrintShopApp\run.bat" %*
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo [FAILED] PrintShop terminated with error code %EXIT_CODE%.
    exit /b %EXIT_CODE%
)

echo.
echo [OK] PrintShop launcher completed.
exit /b 0
