@echo off
chcp 65001 > nul
setlocal

echo ==========================================
echo  Git Security File Check
echo ==========================================

if not exist ".git" (
    echo [ERROR] This folder is not a Git repository.
    exit /b 1
)

set "FOUND=0"

echo.
echo [1/3] Checking tracked and staged sensitive file names...
git ls-files --cached | findstr /i /r /c:"\.env" /c:"\.pem$" /c:"\.key$" /c:"\.pfx$" /c:"\.p12$" /c:"\.jks$" /c:"password" /c:"secret" /c:"credential" /c:"token" > "%TEMP%\git_security_names.txt"
if not errorlevel 1 (
    echo [WARNING] Sensitive-looking files are tracked by Git:
    type "%TEMP%\git_security_names.txt"
    set "FOUND=1"
) else (
    echo [OK] No sensitive file names found in Git tracking.
)

echo.
echo [2/3] Checking staged changes for secret patterns...
:: Check actual credential formats, not ordinary variable names such as password=None.
git grep --cached -n -I -E "(BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY|gh[pousr]_[A-Za-z0-9_=-]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{20,})" -- . 2>nul | findstr /v /i /c:"hbwifihb" > "%TEMP%\git_security_content.txt"
if not errorlevel 1 (
    echo [WARNING] Possible secrets found in staged content:
    type "%TEMP%\git_security_content.txt"
    set "FOUND=1"
) else (
    echo [OK] No common secret patterns found in staged content.
)

echo.
echo [3/3] Checking ignored secrets folder...
if exist "secrets" (
    git check-ignore -q -- secrets\cert.pem 2>nul
    if errorlevel 1 goto :secrets_not_ignored
    git check-ignore -q -- secrets\key.pem 2>nul
    if errorlevel 1 goto :secrets_not_ignored
    echo [OK] secrets folder is ignored by Git.
) else (
    echo [INFO] secrets folder does not exist.
)
goto :security_check_result

:secrets_not_ignored
        echo [WARNING] secrets\cert.pem or secrets\key.pem is not ignored.
        set "FOUND=1"

:security_check_result
echo.
if "%FOUND%"=="1" (
    echo [FAIL] Review the warnings before committing or pushing.
    del "%TEMP%\git_security_names.txt" "%TEMP%\git_security_content.txt" 2>nul
    exit /b 1
)

echo [PASS] No security issues were detected.
del "%TEMP%\git_security_names.txt" "%TEMP%\git_security_content.txt" 2>nul
exit /b 0
