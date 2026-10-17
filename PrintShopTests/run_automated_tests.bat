@echo off
setlocal

cd /d "C:\1print_shop\PrintShopTests"
python -m unittest -v test_automated.py

if errorlevel 1 (
    echo.
    echo Automated tests failed.
) else (
    echo.
    echo Automated tests passed.
)

pause
