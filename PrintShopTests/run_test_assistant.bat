@echo off
setlocal

cd /d "C:\1print_shop\PrintShopTests"
python test_assistant.py

if errorlevel 1 (
    echo.
    echo Test assistant finished with failures.
) else (
    echo.
    echo Test assistant finished successfully.
)

pause
