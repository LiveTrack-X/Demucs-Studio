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
LanguageDetectionMethod=uilanguage
ShowLanguageDialog=yes
UsePreviousLanguage=no
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
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[CustomMessages]
english.ShortcutDescription=Separate vocals and instruments from audio and video.
korean.ShortcutDescription=오디오와 영상에서 보컬과 악기 음원을 분리합니다.

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; Flags: unchecked

[Files]
Source: "{#Payload}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Registry]
Root: HKCU; Subkey: "Software\Demucs Studio\Demucs Studio"; ValueType: string; ValueName: "language"; ValueData: "en"; Languages: english; Flags: createvalueifdoesntexist
Root: HKCU; Subkey: "Software\Demucs Studio\Demucs Studio"; ValueType: string; ValueName: "language"; ValueData: "ko"; Languages: korean; Flags: createvalueifdoesntexist

[Icons]
Name: "{group}\Demucs Studio"; Filename: "{app}\DemucsStudio.exe"; WorkingDir: "{app}"; Comment: "{cm:ShortcutDescription}"
Name: "{userdesktop}\Demucs Studio"; Filename: "{app}\DemucsStudio.exe"; WorkingDir: "{app}"; Comment: "{cm:ShortcutDescription}"; Tasks: desktopicon

[Run]
Filename: "{app}\DemucsStudio.exe"; WorkingDir: "{app}"; Description: "{cm:LaunchProgram,Demucs Studio}"; Flags: nowait postinstall skipifsilent
Filename: "{app}\DemucsStudio.exe"; WorkingDir: "{app}"; Flags: nowait skipifnotsilent; Check: RelaunchRequested

[Code]
function RelaunchRequested: Boolean;
begin
  Result := ExpandConstant('{param:RELAUNCH|0}') = '1';
end;
