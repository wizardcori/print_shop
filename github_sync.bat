@echo off
chcp 65001 > nul

echo ==========================================
echo  GitHub Source Auto-Upload (with Error Check)
echo ==========================================

:: 1. Set the GitHub repository URL
set "REPO_URL=https://github.com/wizardcori/print_shop.git"
echo Repository URL: %REPO_URL%
if "%REPO_URL%"=="" (
    echo [ERROR] Repository URL cannot be empty.
    goto :error
)

:: 2. Initialize Git
if not exist .git (
    echo [INFO] Initializing Git repository...
    git init
    if errorlevel 1 goto :error
) else (
    echo [INFO] Git repository already exists.
)

:: 3. Set the default branch to master
echo [INFO] Setting branch to master...
git branch -M master
if errorlevel 1 goto :error

:: 4. Connect to remote repository
echo [INFO] Configuring remote repository...
git remote remove origin 2>nul
git remote add origin "%REPO_URL%"
if errorlevel 1 goto :error

:: 5. Stage all files
echo [INFO] Staging files (ignoring .gitignore entries)...
git add .
if errorlevel 1 goto :error

:: 6. Prompt for commit message
set /p "COMMIT_MSG=Enter commit message (Default: 'Update source'): "
if "%COMMIT_MSG%"=="" set "COMMIT_MSG=Update source"

:: 7. Commit changes
echo [INFO] Committing changes...
git commit -m "%COMMIT_MSG%"
:: Note: git commit might return an error if there are no changes to commit.
if errorlevel 1 (
    echo [WARNING] No changes to commit or commit failed. Continuing to push anyway...
)

:: 8. Push to GitHub
echo [INFO] Pushing to GitHub...
git push -u origin master
if errorlevel 1 goto :error

:: --- Success Section ---
echo ==========================================
echo [SUCCESS] Upload completed successfully!
echo ==========================================
goto :end

:: --- Error Section ---
:error
echo ==========================================
echo [FAIL] An error occurred during the process.
echo Please check the error messages above.
echo ==========================================

:end
pause
