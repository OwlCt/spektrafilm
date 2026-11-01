#define AppVersion "0.3.4"

[Setup]
AppId={{A7B3E1C4-6D20-4F5A-9C11-0B7E4C2A91D8}
AppName=Spektrafilm
AppVersion={#AppVersion}
AppPublisher=spektrafilm
DefaultDirName={autopf}\Spektrafilm
DefaultGroupName=Spektrafilm
DisableProgramGroupPage=yes
OutputDir=..\..\dist
OutputBaseFilename=Spektrafilm-windows-x64-setup
SetupIconFile=..\..\dist\Spektrafilm\spektrafilm.ico
UninstallDisplayIcon={app}\spektrafilm.ico
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
WizardStyle=modern

[Files]
Source: "..\..\dist\Spektrafilm\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Spektrafilm"; Filename: "{app}\runtime\pythonw.exe"; Parameters: """{app}\launch.pyw"""; IconFilename: "{app}\spektrafilm.ico"; WorkingDir: "{app}"
Name: "{autodesktop}\Spektrafilm"; Filename: "{app}\runtime\pythonw.exe"; Parameters: """{app}\launch.pyw"""; IconFilename: "{app}\spektrafilm.ico"; WorkingDir: "{app}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop icon"; GroupDescription: "Additional icons:"
