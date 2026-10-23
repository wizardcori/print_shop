@echo off
chcp 65001 > nul
title PrintShopApp Runner

rem Always run the application elevated. The shortcut already contains the
rem RunAs flag, but this also covers direct execution of admin_run.bat.
fltmc >nul 2>&1
if errorlevel 1 (
    echo [INFO] Administrator permission is required. Requesting UAC approval...
    powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%ComSpec%' -Verb RunAs -ArgumentList '/c ""%~f0""'"
    exit /b
)

echo ===================================================
echo   Starting PrintShopApp...
echo ===================================================
echo.
echo [INFO] Administrator privileges confirmed.
echo [INFO] Admin launcher: %~f0

cd /d "%~dp0"
set "MODE=development"
if exist ".env" for /f "usebackq tokens=1,* delims==" %%A in (".env") do if /i "%%A"=="MODE" set "MODE=%%B"
for /f %%D in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd"') do set "PRINT_LOG_DATE=%%D"
set "PRINT_LOG=%~dp0data\log\printer\%PRINT_LOG_DATE%_PRINT.LOG"
if not exist "%~dp0data\log\printer" mkdir "%~dp0data\log\printer"
if not exist "%PRINT_LOG%" type nul > "%PRINT_LOG%"
echo [INFO] Printer log initialized: %PRINT_LOG%
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" "%~dp0src\create_admin_shortcut.py"
) else if exist "main_app.exe" (
    powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "& { $p = Join-Path '%~dp0src' 'create_admin_shortcut.py'; if (Get-Command py -ErrorAction SilentlyContinue) { py $p } }"
)
if exist "main_app.exe" goto run_exe
set "PYTHON_EXE=.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" goto missing_venv

echo [INFO] Starting main_app.py with the project virtual environment...
set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
"%PYTHON_EXE%" "%~dp0src\main_app.py" %*
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" (
    echo.
    echo [ERROR] PrintShopApp terminated with error code %EXIT_CODE%.
    pause
    exit /b %EXIT_CODE%
)
exit /b 0

:run_exe
echo [INFO] Starting the packaged PrintShopApp executable...
start "PrintShopApp" "%~dp0main_app.exe"
echo [INFO] PrintShopApp process started in background.
goto open_today_print_log

:open_today_print_log
for /f %%D in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd"') do set "PRINT_LOG_DATE=%%D"
set "PRINT_LOG=%~dp0data\log\printer\%PRINT_LOG_DATE%_PRINT.LOG"
set "KLOGG=C:\APPD\klogg-22.06.0.1289\klogg_portable.exe"
echo [INFO] Printer log directory: %~dp0data\log
echo [INFO] Waiting for printer log: %PRINT_LOG%
for /l %%N in (1,1,60) do (
    if exist "%PRINT_LOG%" goto show_today_print_log
    timeout /t 1 /nobreak > nul
)
echo [WARN] Today's printer log was not created yet.
echo [WARN] Verify that integrated printer logging is configured.
exit /b 0

:show_today_print_log
echo [INFO] Printer log file: %PRINT_LOG%
if /i not "%MODE%"=="development" exit /b 0
if not exist "%KLOGG%" (
    echo [WARN] Klogg executable not found: %KLOGG%
    exit /b 0
)
tasklist /FI "IMAGENAME eq klogg_portable.exe" | find /I "klogg_portable.exe" > nul
if not errorlevel 1 (
    echo [INFO] Klogg is already running. Skipping new launch.
    exit /b 0
)
echo [INFO] Launching Klogg: %KLOGG% "%PRINT_LOG%"
start "Klogg Printer Log" "%KLOGG%" "%PRINT_LOG%"
if errorlevel 1 (
    echo [ERROR] Failed to start Klogg.
) else (
    echo [INFO] Klogg launch command completed successfully.
)

exit /b 0

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
