#define AppName "Infoscava"

[Setup]
AppName={#AppName}
AppVersion=1.4.5
AppPublisher=Muhammed Shafin P
AppPublisherURL=https://github.com/hejhdiss
AppSupportURL=https://github.com/hejhdiss/Infoscava/issues
AppUpdatesURL=https://github.com/hejhdiss/Infoscava/releases
DefaultDirName={autopf}\{#AppName}
DisableDirPage=no
DefaultGroupName={#AppName}
AllowNoIcons=yes
LicenseFile=LICENSE.txt
OutputBaseFilename=Infoscava_Installer
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\u.ico


[Files]
Source: "Infoscava.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "main\*"; DestDir: "{app}\main"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "LICENSE.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "icon.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "u.ico"; DestDir: "{app}"; Flags: ignoreversion


[Icons]
Name: "{group}\Infoscava"; Filename: "{app}\Infoscava.exe"; WorkingDir: "{app}"; IconFilename: "{app}\icon.ico"
Name: "{group}\{cm:UninstallProgram,Infoscava}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Infoscava"; Filename: "{app}\Infoscava.exe"; WorkingDir: "{app}"; IconFilename: "{app}\icon.ico"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Run]
Filename: "{app}\Infoscava.exe"; Description: "{cm:LaunchProgram,Infoscava}"; Flags: nowait postinstall skipifsilent

[Registry]
Root: HKCR; Subkey: "*\shell\Infoscava"; ValueType: string; ValueName: ""; ValueData: "Open with Infoscava"; Flags: uninsdeletekey
Root: HKCR; Subkey: "*\shell\Infoscava"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\icon.ico"
Root: HKCR; Subkey: "*\shell\Infoscava\command"; ValueType: string; ValueName: ""; ValueData: """{app}\Infoscava.exe"" ""%1"""


[UninstallDelete]
Type: filesandordirs; Name: "{app}"
Type: dirifempty; Name: "{autoprograms}\{#AppName}"

[Messages]
SetupAppTitle=Infoscava Installer
