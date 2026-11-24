#ifndef AppVersion
  #error Supply AppVersion from demucs_gui/version.py with package-release.ps1
#endif
#ifndef Payload
  #define Payload "..\dist\DemucsStudio"
#endif

[Setup]
AppId={{587F2DE6-C25B-42AB-936C-3AE7B175A01D}
AppName=Demucs Studio
AppVersion={#AppVersion}
VersionInfoVersion={#AppVersion}
AppPublisher=LiveTrack-X
DefaultDirName={localappdata}\Programs\DemucsStudio
DefaultGroupName=Demucs Studio
DisableProgramGroupPage=yes
AllowNoIcons=yes
PrivilegesRequired=lowest
SetupArchitecture=x64
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
SetupIconFile=..\DemucsStudio.ico
UninstallDisplayIcon={app}\DemucsStudio.exe
OutputDir=..\build\release
OutputBaseFilename=DemucsStudio-Setup-x64
Compression=lzma2/max
LZMANumBlockThreads=6
SolidCompression=yes
#ifdef Split
DiskSpanning=yes
DiskSliceSize=1950000000
SlicesPerDisk=1
#endif
SetupMutex=DemucsStudioSetup-587F2DE6
CloseApplications=yes
CloseApplicationsFilter=DemucsStudio.exe
RestartApplications=no

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; Flags: unchecked

[Files]
Source: "{#Payload}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Demucs Studio"; Filename: "{app}\DemucsStudio.exe"; WorkingDir: "{app}"
Name: "{userdesktop}\Demucs Studio"; Filename: "{app}\DemucsStudio.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\DemucsStudio.exe"; WorkingDir: "{app}"; Description: "Demucs Studio 실행"; Flags: nowait postinstall skipifsilent
Filename: "{app}\DemucsStudio.exe"; WorkingDir: "{app}"; Flags: nowait skipifnotsilent; Check: RelaunchRequested

[Code]
function RelaunchRequested: Boolean;
begin
  Result := ExpandConstant('{param:RELAUNCH|0}') = '1';
end;
