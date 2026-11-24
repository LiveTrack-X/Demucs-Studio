#ifndef DownloadEntries
  #error Build with package-release.ps1 to embed version-specific URLs and SHA-256 digests.
#endif

[Setup]
AppId=DemucsStudioOnline
AppName={cm:OnlineSetupName}
AppVersion={#AppVersion}
AppPublisher=LiveTrack-X
VersionInfoVersion={#AppVersion}
CreateAppDir=no
Uninstallable=no
PrivilegesRequired=lowest
SetupArchitecture=x64
SetupIconFile=..\DemucsStudio.ico
OutputBaseFilename=DemucsStudio-OnlineSetup-x64
DisableReadyPage=yes
DisableFinishedPage=yes
CloseApplications=no
WizardStyle=modern
LanguageDetectionMethod=uilanguage
ShowLanguageDialog=yes
UsePreviousLanguage=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[CustomMessages]
english.OnlineSetupName=Demucs Studio Online Setup
korean.OnlineSetupName=Demucs Studio 온라인 설치
english.DownloadTitle=Downloading Demucs Studio
korean.DownloadTitle=Demucs Studio 다운로드
english.DownloadDetail=Downloading and verifying the installation files.
korean.DownloadDetail=설치 파일을 내려받고 무결성을 확인합니다.
english.LaunchError=Could not start the installer. %1
korean.LaunchError=설치 프로그램을 시작할 수 없습니다. %1
english.ExitError=The installer exited with code %1.
korean.ExitError=설치 프로그램이 종료되었습니다 (코드 %1).

[Code]
var
  DownloadPage: TDownloadWizardPage;

procedure InitializeWizard;
begin
  DownloadPage := CreateDownloadPage(CustomMessage('DownloadTitle'), CustomMessage('DownloadDetail'), nil);
  DownloadPage.ShowBaseNameInsteadOfUrl := True;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Arguments, Directory: String;
  Status, I: Integer;
  WasVisible: Boolean;
begin
  Result := '';
  DownloadPage.Clear;
  #include DownloadEntries
  DownloadPage.Show;
  try
    try
      DownloadPage.Download;
    except
      Result := DownloadPage.LastBaseNameOrUrl + #13#10 + GetExceptionMessage;
    end;
  finally
    DownloadPage.Hide;
  end;
  if Result <> '' then Exit;

  Arguments := '/SP- /NORESTART /LANG=' + ActiveLanguage;
  if WizardSilent then Arguments := Arguments + ' /VERYSILENT /SUPPRESSMSGBOXES';
  Directory := ExpandConstant('{param:DIR|}');
  if (Directory <> '') and (Pos('"', Directory) = 0) then
    Arguments := Arguments + ' /DIR="' + Directory + '"';
  for I := 1 to ParamCount do
    if CompareText(ParamStr(I), '/NOICONS') = 0 then Arguments := Arguments + ' /NOICONS';
  WasVisible := WizardForm.Visible;
  WizardForm.Hide;
  try
    if not Exec(ExpandConstant('{tmp}\DemucsStudio-Setup-x64.exe'), Arguments,
                ExpandConstant('{tmp}'), SW_SHOWNORMAL, ewWaitUntilTerminated, Status) then
      Result := FmtMessage(CustomMessage('LaunchError'), [SysErrorMessage(Status)])
    else if Status <> 0 then
      Result := FmtMessage(CustomMessage('ExitError'), [IntToStr(Status)]);
  finally
    if WasVisible then WizardForm.Show;
  end;
end;
