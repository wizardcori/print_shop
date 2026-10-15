@echo off
chcp 65001 > nul
title PrintShopApp Packaging Script

echo ===================================================
echo   Starting PrintShopApp Distribution Build (PyInstaller)
echo ===================================================
echo.

if not exist .venv (
    echo [ERROR] Virtual environment (.venv) does not exist.
    echo Please run 'setup.bat' first.
    goto error_exit
)

echo [1/2] Activating virtual environment and ensuring PyInstaller is installed...
call .venv\Scripts\activate.bat
pip install pyinstaller > nul

echo.
echo [2/2] Building executable package (onedir mode)...
pyinstaller --noconsole --onedir --name "PrintShopApp" ^
    --add-data "LinkBox/templates;LinkBox/templates" ^
    --add-data "LinkShare/templates;LinkShare/templates" ^
    main_app.py

echo.
echo ===================================================
echo   Build complete! 
echo   Check the 'dist/PrintShopApp' folder for your executable.
echo ===================================================
echo.
pause
exit /b

:error_exit
echo.
echo [FAILED] Build terminated due to an error.
pause
exit /b