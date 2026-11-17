@echo off
chcp 65001 > nul

net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [경고] 관리자 권한이 필요합니다!
    echo 우클릭 후 '관리자 권한으로 실행'을 다시 해주세요.
    pause
    exit /b
)

cd /d %~dp0

:MENU
cls
echo ==================================================
echo   PrintShop Update Service 관리 도구
echo ==================================================
echo   1. 서비스 등록 (Install)
echo   2. 서비스 시작 (Start)
echo   3. 서비스 중지 (Stop)
echo   4. 서비스 재시작 (Restart)
echo   5. 서비스 제거 (Remove)
echo   6. 서비스 상태 확인 (Status)
echo   7. 종료 (Exit)
echo ==================================================
set /p choice="원하는 작업의 번호를 입력하세요 (1-7): "

if "%choice%"=="1" goto INSTALL
if "%choice%"=="2" goto START
if "%choice%"=="3" goto STOP
if "%choice%"=="4" goto RESTART
if "%choice%"=="5" goto REMOVE
if "%choice%"=="6" goto STATUS
if "%choice%"=="7" exit

echo 잘못된 입력입니다. 다시 선택해주세요.
pause
goto MENU

:INSTALL
echo.
echo [서비스 등록 중...]
..\..\.venv\Scripts\python.exe print_shop_update_service.py install

sc create PSUpdaterService binPath= "C:\1print_shop\PrintShopApp\.venv\Scripts\Python.exe --C:\1print_shop\PrintShopApp\src\UpdateService\print_shop_update_service.py" DisplayName= "PSUpdaterService" start= auto


echo.
pause
goto MENU

:START
echo.
echo [서비스 시작 중...]
..\..\.venv\Scripts\python.exe print_shop_update_service.py start
echo.
pause
goto MENU

:STOP
echo.
echo [서비스 중지 중...]
..\..\.venv\Scripts\python.exe print_shop_update_service.py stop
echo.
pause
goto MENU

:RESTART
echo.
echo [서비스 재시작 중...]
..\..\.venv\Scripts\python.exe print_shop_update_service.py restart
echo.
pause
goto MENU

:REMOVE
echo.
echo [서비스 제거 중...]
..\..\.venv\Scripts\python.exe print_shop_update_service.py remove
echo.
pause
goto MENU

:STATUS
echo.
echo [서비스 상태 확인]
sc query PSUpdaterService
echo.
pause
goto MENU