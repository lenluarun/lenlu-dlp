


[Setup]
; ============================================================================
; LENLU DLP - Windows Application Installer Configuration
; ============================================================================
AppName=LENLU DLP
AppVersion=1.0
DefaultDirName={pf}\LENLU DLP
DefaultGroupName=LENLU DLP
OutputDir=.
OutputBaseFilename=LENLU_DLP_Setup
Compression=lzma
SolidCompression=yes
SetupIconFile=..\landing\assets\icons\app_icon.ico

; Admin privileges are required to write to Program Files and manage system processes
PrivilegesRequired=admin

[Files]
; 1. THE CORE EXECUTABLE
; This is the result of: pyinstaller --noconsole --onefile --add-data "app/gui;app/gui" --add-data "app/backend;app/backend" app/backend/main_app.py
Source: "..\dist\main_app.exe"; DestDir: "{app}"; Flags: ignoreversion

; 2. THE FRONTEND ASSETS
; Bundles the standalone app folder containing the index.html
Source: "..\app\gui\*"; DestDir: "{app}\app\gui"; Flags: ignoreversion recursesubdirs createallsubdirs

; 3. THE BACKEND SOURCE
; Bundles the source logic to ensure the executable has access to the FastAPI app
Source: "..\app\backend\*"; DestDir: "{app}\app\backend"; Flags: ignoreversion recursesubdirs createallsubdirs

; 4. SYSTEM ASSETS
Source: "..\landing\assets\icons\app_icon.ico"; DestDir: "{app}"; Flags: ignoreversion

[Dirs]
; Create a dedicated downloads folder in the installation directory
Name: "{app}\downloads"

[Icons]
; High-visibility shortcuts for the user
Name: "{userdesktop}\LENLU DLP"; Filename: "{app}\main_app.exe"; IconFilename: "{app}\app_icon.ico"
Name: "{group}\LENLU DLP"; Filename: "{app}\main_app.exe"; IconFilename: "{app}\app_icon.ico"

[Run]
; Automatically launch the application after a successful installation
Filename: "{app}\main_app.exe"; Description: "Launch LENLU DLP Media Terminal"; Flags: nowait postinstall skipifsilent
