@echo off
chcp 65001 > nul
title PrintShopApp Runner

echo ===================================================
echo   Starting PrintShopApp...
echo ===================================================
echo.

cd /d "%~dp0"
if exist "main_app.exe" goto run_exe
set "PYTHON_EXE=.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" goto missing_venv

echo [INFO] Starting main_app.py with the project virtual environment...
"%PYTHON_EXE%" main_app.py
if errorlevel 1 goto run_error

rem pause
exit /b

:run_exe
echo [INFO] Starting the packaged PrintShopApp executable...
"%~dp0main_app.exe"
if errorlevel 1 goto run_error
exit /b

:missing_venv
echo [ERROR] Virtual environment (.venv) does not exist.
echo Please run 'setup.bat' first to configure the environment.
goto error_exit

:run_error
echo.
echo [FAILED] PrintShopApp terminated with an error.
goto error_exit

:error_exit
echo.
echo [FAILED] Execution aborted.
pause
exit /b
