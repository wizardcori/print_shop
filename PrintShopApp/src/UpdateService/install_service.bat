@echo off
setlocal enabledelayedexpansion
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo Requesting Administrator privileges...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

echo ========================================================
echo  Windows Service and Registry Batch Cleanup Script
echo ========================================================
echo.

:: Define service names and registry path variables
set "SVC2=PrintShopUpdateService"
set "SVC3=PythonApp"
set "SVC4=PSUpdaterService"
set "SVC5=print_shop_update_service"

set "SVC1_REG=HKLM\SYSTEM\CurrentControlSet\Services\!SVC1!"
set "SVC2_REG=HKLM\SYSTEM\CurrentControlSet\Services\!SVC2!"
set "SVC3_REG=HKLM\SYSTEM\CurrentControlSet\Services\!SVC3!"
set "SVC4_REG=HKLM\SYSTEM\CurrentControlSet\Services\!SVC4!"
set "SVC5_REG=HKLM\SYSTEM\CurrentControlSet\Services\!SVC5!"
set "Config_REG=HKLM\SOFTWARE\PSUpdateService"

:: ==========================================
:: Phase 0: Terminate Running Processes (Prevent File Lock / Access Denied)
:: ==========================================
echo [Phase 0] Terminating running processes...
echo --------------------------------------------------------
taskkill /f /im "PrintShopApp.exe" >nul 2>&1
taskkill /f /im "python.exe" >nul 2>&1
timeout /t 2 /nobreak >nul
echo   - Process termination completed.
echo --------------------------------------------------------

:: ==========================================
:: Phase 1: Stop and Delete Services (sc queryex + qc)
:: ==========================================
echo [Phase 1] Stopping and deleting services...
echo --------------------------------------------------------

for %%S in (!SVC1! !SVC2! !SVC3! !SVC4! !SVC5!) do (
    echo [Target Service] %%S
    
    :: Use both queryex and qc to rigorously verify if the service actually exists
    sc.exe queryex "%%S" >nul 2>&1
    set "Q_ERR=!errorlevel!"
    
    sc.exe qc "%%S" >nul 2>&1
    set "QC_ERR=!errorlevel!"
    
    if !Q_ERR! equ 0 (
        if !QC_ERR! equ 0 (
            echo   - Service verified active/installed. Stopping and deleting...
            sc.exe stop "%%S" >nul 2>&1
            timeout /t 2 /nobreak >nul
            sc.exe delete "%%S" >nul 2>&1
            echo   - Successfully deleted service: %%S
        ) else (
            echo   - Service does not exist or already removed.
        )
    ) else (
        echo   - Service does not exist or already removed.
    )
    echo --------------------------------------------------------
)

:: ==========================================
:: Phase 2: Registry Cleanup (reg delete)
:: ==========================================
echo [Phase 2] Cleaning up registry keys...
echo --------------------------------------------------------

:: Check and delete SVC1 Registry Key
echo [Target Registry] !SVC1_REG!
reg query "!SVC1_REG!" >nul 2>&1
if !errorlevel! equ 0 (
    reg delete "!SVC1_REG!" /f >nul 2>&1
    echo   - Registry key found. Successfully deleted.
) else (
    echo   - Registry key does not exist. Skipping deletion.
)
echo --------------------------------------------------------

:: Check and delete SVC2 Registry Key
echo [Target Registry] !SVC2_REG!
reg query "!SVC2_REG!" >nul 2>&1
if !errorlevel! equ 0 (
    reg delete "!SVC2_REG!" /f >nul 2>&1
    echo   - Registry key found. Successfully deleted.
) else (
    echo   - Registry key does not exist. Skipping deletion.
)
echo --------------------------------------------------------

:: Check and delete SVC3 Registry Key
echo [Target Registry] !SVC3_REG!
reg query "!SVC3_REG!" >nul 2>&1
if !errorlevel! equ 0 (
    reg delete "!SVC3_REG!" /f >nul 2>&1
    echo   - Registry key found. Successfully deleted.
) else (
    echo   - Registry key does not exist. Skipping deletion.
)
echo --------------------------------------------------------

:: Check and delete SVC4 Registry Key
echo [Target Registry] !SVC4_REG!
reg query "!SVC4_REG!" >nul 2>&1
if !errorlevel! equ 0 (
    reg delete "!SVC4_REG!" /f >nul 2>&1
    echo   - Registry key found. Successfully deleted.
) else (
    echo   - Registry key does not exist. Skipping deletion.
)
echo --------------------------------------------------------

:: Check and delete SVC5 Registry Key
echo [Target Registry] !SVC5_REG!
reg query "!SVC5_REG!" >nul 2>&1
if !errorlevel! equ 0 (
    reg delete "!SVC5_REG!" /f >nul 2>&1
    echo   - Registry key found. Successfully deleted.
) else (
    echo   - Registry key does not exist. Skipping deletion.
)
echo --------------------------------------------------------

:: Check and delete Config Registry Key
echo [Target Registry] Config: !Config_REG!
reg query "!Config_REG!" >nul 2>&1
if !errorlevel! equ 0 (
    reg delete "!Config_REG!" /f >nul 2>&1
    echo   - Configuration registry key found. Successfully deleted.
) else (
    echo   - Configuration registry key does not exist. Skipping deletion.
)
echo --------------------------------------------------------

echo.
echo All cleanup tasks completed successfully.
pause