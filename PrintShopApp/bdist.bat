@echo off
chcp 65001 > nul
title PrintShopApp Packaging Script

echo ===================================================
echo   Starting PrintShopApp Distribution Build (PyInstaller)
echo ===================================================
echo.

if not exist ".venv\Scripts\python.exe" goto error_exit

echo [1/2] Activating virtual environment and ensuring PyInstaller is installed...
".venv\Scripts\python.exe" -m pip install pyinstaller > nul

echo.
echo [2/2] Building executable package (onedir mode)...
".venv\Scripts\pyinstaller.exe" --noconsole --onedir --noconfirm --name "PrintShopApp" --add-binary "C:\Espressif\tools\python\python311.dll;." --add-binary "C:\Espressif\tools\python\vcruntime140.dll;." --add-binary "C:\Espressif\tools\python\vcruntime140_1.dll;." --add-data "LinkBox/templates;LinkBox/templates" --add-data "LinkShare/templates;LinkShare/templates" main_app.py

echo.
echo ===================================================
echo   Build complete! 
echo   Check the 'dist/PrintShopApp' folder for your executable.
echo ===================================================
echo.

set "ISCC="
for /f "delims=" %%I in ('where iscc 2^>nul') do set "ISCC=%%I"
if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not defined ISCC goto install_inno
echo [3/3] Creating Windows installer...
if not exist installer mkdir installer
set "SETUP_NAME=PrintShopApp_Setup"
if exist "installer\%SETUP_NAME%.exe" del /f /q "installer\%SETUP_NAME%.exe" > nul 2>&1
if exist "installer\%SETUP_NAME%.exe" set "SETUP_NAME=PrintShopApp_Setup_%RANDOM%"
"%ISCC%" /DSourceDir="%CD%" /DOutputBaseFilename="%SETUP_NAME%" installer.iss
if errorlevel 1 goto error_exit
echo Installer created: installer\%SETUP_NAME%.exe
goto done

:install_inno
echo [INFO] Inno Setup compiler was not found. Installing Inno Setup...
where winget > nul 2>&1
if errorlevel 1 goto no_inno
winget install --id JRSoftware.InnoSetup --exact --silent --accept-source-agreements --accept-package-agreements
if errorlevel 1 goto no_inno
set "PATH=%PATH%;%ProgramFiles(x86)%\Inno Setup 6;%ProgramFiles%\Inno Setup 6"
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not defined ISCC goto no_inno
echo [3/3] Creating Windows installer...
if not exist installer mkdir installer
set "SETUP_NAME=PrintShopApp_Setup"
if exist "installer\%SETUP_NAME%.exe" del /f /q "installer\%SETUP_NAME%.exe" > nul 2>&1
if exist "installer\%SETUP_NAME%.exe" set "SETUP_NAME=PrintShopApp_Setup_%RANDOM%"
"%ISCC%" /DSourceDir="%CD%" /DOutputBaseFilename="%SETUP_NAME%" installer.iss
if errorlevel 1 goto error_exit
echo Installer created: installer\%SETUP_NAME%.exe
goto done

:no_inno
echo [WARNING] Inno Setup compiler (ISCC.exe) was not found.
echo Portable build is ready in dist\PrintShopApp.
echo Install Inno Setup and run bdist.bat again for the installer.

:done
pause
exit /b

:error_exit
echo.
echo [FAILED] Build terminated due to an error.
pause
exit /b
