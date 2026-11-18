[Setup]
AppId={{B6D24C2D-5C3A-4D72-9C3E-7A11C4F09B2D}}
AppName=PrintShopApp
AppVersion=1.0.0
DefaultDirName={autopf}\PrintShopApp
DefaultGroupName=PrintShopApp
OutputDir={#SourceDir}\installer
#ifndef OutputBaseFilename
#define OutputBaseFilename "PrintShopApp_Setup"
#endif
OutputBaseFilename={#OutputBaseFilename}
Compression=lzma
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
UninstallDisplayIcon={app}\PrintShopApp.exe
CloseApplications=yes
RestartApplications=no

[Files]
; 💡 dist 폴더 바로 아래에 생성된 단일 실행 파일 및 버전 파일 복사
Source: "{#SourceDir}\dist\PrintShopApp\PrintShopApp.exe"; DestDir: "{app}"; Flags: ignoreversion

; 기타 리소스 및 서브 서비스 파일 복사
Source: "src\init_data\sound\approval_sounds\*.wav"; DestDir: "{app}\data\sound\approval_sounds"; Flags: ignoreversion
Source: "src\LinkBox\templates\*"; DestDir: "{app}\LinkBox\templates"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "src\LinkShare\web\templates\*"; DestDir: "{app}\LinkShare\web\templates"; Flags: ignoreversion recursesubdirs createallsubdirs

; 💡 서비스 빌드가 수행되는 src\UpdateService\dist 폴더 경로 직접 지정
Source: "{#SourceDir}\dist\PrintShopUpdateService\PrintShopUpdateService.exe"; DestDir: "{app}\UpdateService"; Flags: ignoreversion

[Icons]
Name: "{group}\PrintShopApp"; Filename: "{app}\PrintShopApp.exe"
Name: "{commondesktop}\PrintShopApp"; Filename: "{app}\PrintShopApp.exe"; Tasks: desktopicon
Name: "{commonstartup}\PrintShopApp"; Filename: "{app}\PrintShopApp.exe"; Tasks: startupicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"
Name: "startupicon"; Description: "Automatically run PrintShopApp at Windows startup"; GroupDescription: "Additional icons:"; Flags: unchecked

[Run]
Filename: "{app}\PrintShopApp.exe"; Description: "Launch PrintShopApp"; Flags: postinstall nowait skipifsilent runascurrentuser

[Code]
// 설치 시작 전 실행 중인 프로세스와 서비스를 완전히 중지 및 삭제
function InitializeSetup(): Boolean;
var
  ResultCode: Integer;
begin
  Exec('net', 'stop print_shop_update_service', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Sleep(1000);
  
  Exec('taskkill', '/f /im print_shop_update_service.exe', '', SW_HIDE, ewNoWait, ResultCode);
  Exec('taskkill', '/f /im PrintShopUpdateService.exe', '', SW_HIDE, ewNoWait, ResultCode);  
  Exec('taskkill', '/f /im PrintShopApp.exe', '', SW_HIDE, ewNoWait, ResultCode);
  Sleep(1000);
  
  Exec('sc', 'delete print_shop_update_service', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Exec('sc', 'delete PrintShopUpdateService', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);  
  Sleep(1000);

  Result := True;
end;

// 파일 복사 직전(ssInstall 단계)에 프로세스를 한 번 더 확실히 종료
procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
  AppDir, ServiceExe, ServiceDisplayName, VerFilePath, ServiceVersion: String;
  AnsiVersion: AnsiString;
  CmdParams: String;
begin
  if CurStep = ssInstall then
  begin
    Exec('taskkill', '/f /im print_shop_update_service.exe', '', SW_HIDE, ewNoWait, ResultCode);
    Exec('taskkill', '/f /im PrintShopUpdateService.exe', '', SW_HIDE, ewNoWait, ResultCode);
    Exec('taskkill', '/f /im python.exe', '', SW_HIDE, ewNoWait, ResultCode); // 파이썬 기반 서비스 프로세스 방어용
    Sleep(1000);
  end;

  if CurStep = ssPostInstall then
  begin
    AppDir := ExpandConstant('{app}');
    ServiceExe := AppDir + '\UpdateService\PrintShopUpdateService.exe';

    // 1. 기본 버전 값 설정
    ServiceVersion := '1.2.0';

    // 2. 버전 파일 읽기 시도
    VerFilePath := AppDir + '\UpdateService\version.txt';
    if FileExists(VerFilePath) then
    begin
      if LoadStringFromFile(VerFilePath, AnsiVersion) then
      begin
        ServiceVersion := Trim(String(AnsiVersion));
      end;
    end;

    // 3. 서비스 표시 이름 설정
    ServiceDisplayName := 'PrintShop Updater & Watchdog Service v' + ServiceVersion;

    // 4. Windows 서비스 등록
    CmdParams := 'create PrintShopUpdateService binPath= "' + ServiceExe + '" start= auto DisplayName= "' + ServiceDisplayName + '"';
    Exec('sc', CmdParams, '', SW_HIDE, ewWaitUntilTerminated, ResultCode);

    // 5. 서비스 시작
    Exec('net', 'start PrintShopUpdateService', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end;
end;