#define AppName "Studio Sync"
#define AppVersion "0.2.0"
#define AppPublisher "Betha Sistemas"

[Setup]
AppId={{CBE18FCB-095D-4BBA-AC35-7CF8588E7591}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\Studio Sync
DefaultGroupName=Studio Sync
OutputDir=..\..\release
OutputBaseFilename=StudioSync-Windows-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
Source: "..\..\dist\StudioSync.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\Studio Sync"; Filename: "{app}\StudioSync.exe"
Name: "{autodesktop}\Studio Sync"; Filename: "{app}\StudioSync.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na área de trabalho"; GroupDescription: "Atalhos adicionais:"

[Run]
Filename: "{app}\StudioSync.exe"; Description: "Abrir Studio Sync"; Flags: nowait postinstall skipifsilent
