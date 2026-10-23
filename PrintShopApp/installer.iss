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

[Files]
Source: "{#SourceDir}\dist\PrintShopApp\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "{#SourceDir}\data\sound\approval_sounds\*.wav"; DestDir: "{app}\data\sound\approval_sounds"; Flags: ignoreversion

[Icons]
Name: "{group}\PrintShopApp"; Filename: "{app}\PrintShopApp.exe"
Name: "{commondesktop}\PrintShopApp"; Filename: "{app}\PrintShopApp.exe"; Tasks: desktopicon
Name: "{userstartup}\PrintShopApp"; Filename: "{app}\PrintShopApp.exe"; Tasks: startupicon

[Tasks]
Name: "desktopicon"; Description: "바탕 화면에 바로가기 만들기"; GroupDescription: "추가 아이콘:"
Name: "startupicon"; Description: "Windows 시작 시 PrintShopApp 자동 실행"; GroupDescription: "추가 아이콘:"; Flags: unchecked

[Run]
Filename: "{app}\PrintShopApp.exe"; Description: "PrintShopApp 실행"; Flags: postinstall nowait skipifsilent runascurrentuser
