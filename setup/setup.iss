[Setup]
AppName=LENLU DLP
AppVersion=1.0
DefaultDirName={pf}\LENLU DLP
DefaultGroupName=LENLU DLP
OutputDir=.
OutputBaseFilename=LENLU_DLP_Setup
Compression=lzma
SolidCompression=yes
PrivilegesRequired=admin
; SetupIconFile=..\assets\icons\app_icon.ico

[Files]
; The Main Executable (Relative to the setup/ folder)
Source: "..\dist\LENLU_DLP.exe"; DestDir: "{app}"; Flags: ignoreversion

; The Frontend files (Relative to the setup/ folder)
Source: "..\src\index.html"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\src\local_host.html"; DestDir: "{app}"; Flags: ignoreversion

; The Icon file (Relative to the setup/ folder)
Source: "..\assets\icons\app_icon.ico"; DestDir: "{app}"; Flags: ignoreversion

[Dirs]
; Auto-create the downloads directory in the app folder
Name: "{app}\downloads"

[Icons]
; Desktop shortcut to start the app
Name: "{userdesktop}\LENLU DLP"; Filename: "{app}\LENLU_DLP.exe"; IconFilename: "{app}\app_icon.ico"
Name: "{group}\LENLU DLP"; Filename: "{app}\LENLU_DLP.exe"; IconFilename: "{app}\app_icon.ico"

[Run]
; Launch the app immediately after installation
Filename: "{app}\LENLU_DLP.exe"; Description: "Launch LENLU DLP"; Flags: nowait postinstall skipifsilent
