; ============================================================================
; LENLU DLP - Modern Windows Application Installer Configuration
; Inno Setup 6.x Script
; ============================================================================

#define MyAppName "LENLU DLP"
#define MyAppVersion "2.0.0"
#define MyAppPublisher "LENLU DLP"
#define MyAppURL "https://github.com/lenluarun/lenlu-dlp"
#define MyAppSupportURL "https://github.com/lenluarun/lenlu-dlp/issues"
#define MyAppUpdatesURL "https://github.com/lenluarun/lenlu-dlp/releases/latest"
#define MyAppExeName "main_app.exe"
#define MyAppId "{{C8E6D3A0-584A-4835-964B-8348BEA8D49E}}"

[Setup]
; App Identity
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} v{#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppSupportURL}
AppUpdatesURL={#MyAppUpdatesURL}
AppCopyright=Copyright (C) 2026 LENLU DLP

; Version Information for Windows Properties
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription=Local-first terminal media downloader powered by yt-dlp
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}
VersionInfoVersion={#MyAppVersion}

; Installation Paths & Architecture
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=commandline

; Output Packaging
OutputDir=.
OutputBaseFilename=LENLU_DLP_Setup
Compression=lzma2/ultra64
SolidCompression=yes
SetupIconFile=..\landing\assets\icons\app_icon.ico
UninstallDisplayIcon={app}\app_icon.ico
UninstallDisplayName={#MyAppName}

; Modern UI & Process Management
WizardStyle=modern
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce

[Files]
; 1. Core Executable (PyInstaller bundle)
Source: "..\dist\main_app.exe"; DestDir: "{app}"; Flags: ignoreversion

; 2. Frontend Assets (GUI templates, terminal styles)
Source: "..\app\gui\*"; DestDir: "{app}\app\gui"; Flags: ignoreversion recursesubdirs createallsubdirs

; 3. Backend Source Logic (excluding bytecode cache)
Source: "..\app\backend\*"; DestDir: "{app}\app\backend"; Excludes: "*.pyc,__pycache__,__pycache__\*"; Flags: ignoreversion recursesubdirs createallsubdirs

; 4. System Assets & Config
Source: "..\landing\assets\icons\app_icon.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\requirements.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion

[Dirs]
; Dedicated local downloads workspace directory with user write permissions
Name: "{app}\downloads"; Permissions: users-modify

[Icons]
; Start Menu & Desktop Shortcuts
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\app_icon.ico"; Comment: "{#MyAppName} - Media Downloader for Developers"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\app_icon.ico"; Comment: "{#MyAppName} - Media Downloader for Developers"; Tasks: desktopicon

[Run]
; Launch option on completion
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

