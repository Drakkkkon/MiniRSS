#define MyAppName "MiniRSS"
#define MyAppVersion "1.4.1"
#define MyAppPublisher "Drakkkkon"
#define MyAppExeName "MiniRSS.exe"

[Setup]
AppId={{D3A8D5D1-7D2C-4C92-9E74-6A5E4D2F1B91}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\MiniRSS
DefaultGroupName=MiniRSS
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64
OutputDir=release
OutputBaseFilename=MiniRSS_Setup_{#MyAppVersion}_x64
SetupIconFile=assets\minirss.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
Uninstallable=yes
VersionInfoVersion=1.4.1.0
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription=MiniRSS installer
VersionInfoProductName=MiniRSS
MinVersion=10.0

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Дополнительные ярлыки:"; Flags: checkedonce
Name: "startmenuicon"; Description: "Создать ярлык в меню «Пуск»"; GroupDescription: "Дополнительные ярлыки:"; Flags: checkedonce

[Files]
Source: "dist\MiniRSS.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\MiniRSS"; Filename: "{app}\{#MyAppExeName}"; Tasks: startmenuicon
Name: "{autodesktop}\MiniRSS"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Запустить MiniRSS"; Flags: postinstall nowait skipifsilent

[UninstallDelete]
; Пользовательские настройки в %APPDATA%\MiniRSS сохраняются при удалении приложения.
