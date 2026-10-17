@echo off
setlocal

cd /d "C:\1print_shop\PrintShopTests"

echo ========================================
echo PrintShop automated tests
echo ========================================
python -m unittest discover -v -p "test_*.py"
if errorlevel 1 (
    echo.
    echo Automated tests failed. Stopping before manual checks.
    pause
    exit /b 1
)

echo.
echo ========================================
echo PrintShop device test assistant
echo ========================================
python test_assistant.py
if errorlevel 1 (
    echo.
    echo Device test assistant finished with failures.
) else (
    echo.
    echo Device test assistant finished successfully.
)

pause
