@echo off
chcp 65001 > nul
setlocal

echo ========================================================
echo  1print_shop Project Google Drive Backup Started
echo ========================================================

:: Use the folder containing this batch file as the project root.
set "SRC_DIR=%~dp0"
:: Remove the trailing backslash so quoted paths are parsed correctly by Robocopy.
set "SRC_DIR=%SRC_DIR:~0,-1%"
set "DEST_DIR=G:\My Drive\1print_shop"

:: Folders regenerated during Python/PySide development and build output
set "EXCLUDE_DIRS=__pycache__ .venv venv env .git .idea .vscode build dist *.egg-info"

:: Files excluded from the backup: cache, logs, certificates/keys, and local databases
set "EXCLUDE_FILES=*.pyc *.pyo *.pyd *.log *.user *.db *.pem *.key"

echo.
echo Source path: %SRC_DIR%
echo Destination path: %DEST_DIR%
echo.

if not exist "G:\" (
    echo [ERROR] G: drive was not found. Make sure Google Drive is connected.
    pause
    exit /b 1
)

:: /E       Copy the complete folder structure, including empty folders
:: /XD      Excluded directories
:: /XF      Excluded files
:: /R:1     Retry failed operations once
:: /W:1     Wait one second between retries
:: /NP/NDL  Hide progress and directory listings
robocopy "%SRC_DIR%" "%DEST_DIR%" /E /XD %EXCLUDE_DIRS% /XF %EXCLUDE_FILES% /R:1 /W:1 /NP /NDL
set "ROBOCOPY_EXIT=%ERRORLEVEL%"

echo.
if %ROBOCOPY_EXIT% LEQ 7 (
    echo Backup completed. Robocopy exit code: %ROBOCOPY_EXIT%
) else (
    echo [ERROR] The backup encountered a problem. Robocopy exit code: %ROBOCOPY_EXIT%
)
echo ========================================================

rem pause
exit /b %ROBOCOPY_EXIT%
