#ifndef Payload
  #error Payload must name the tested standalone payload directory
#endif
#ifndef OutputDir
  #error OutputDir must name an external build directory
#endif
#ifndef AppVersion
  #error AppVersion must match package metadata
#endif
[Setup]
AppId={{D87B676D-DC50-4E39-8DC4-120A9303E77B}
AppName=Millionaire
AppVersion={#AppVersion}
DefaultDirName={autopf}\Millionaire
DefaultGroupName=Millionaire
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
Compression=lzma2
SolidCompression=yes
OutputBaseFilename=millionaire-{#AppVersion}-windows-x64
OutputDir={#OutputDir}
UninstallDisplayName=Millionaire
CloseApplications=yes
RestartApplications=no

[Files]
Source: "{#Payload}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Dirs]
Name: "{commonappdata}\Millionaire"; Permissions: admins-full system-full
Name: "{commonappdata}\Millionaire-Status"; Permissions: users-readexec admins-full system-full

[Icons]
Name: "{group}\Millionaire Controller"; Filename: "{app}\MillionaireTray.exe"; WorkingDir: "{app}"
Name: "{commondesktop}\Millionaire"; Filename: "{app}\MillionaireTray.exe"; WorkingDir: "{app}"
Name: "{commonstartup}\Millionaire"; Filename: "{app}\MillionaireTray.exe"; WorkingDir: "{app}"

[Run]
Filename: "{app}\MillionaireTray.exe"; Flags: nowait runasoriginaluser

[UninstallRun]
Filename: "{app}\MillionaireTray.exe"; Parameters: "--quit"; Flags: runhidden waituntilterminated; RunOnceId: "QuitMillionaireTray"
Filename: "{app}\runtime\python.exe"; Parameters: "-m quantide.cli service stop"; Flags: runhidden waituntilterminated; RunOnceId: "StopMillionaireService"
Filename: "{app}\runtime\python.exe"; Parameters: "-m quantide.cli service uninstall"; Flags: runhidden waituntilterminated; RunOnceId: "UninstallMillionaireService"

[Code]
var
  ServiceInstallFailed: Boolean;

function GetCustomSetupExitCode(): Integer;
begin
  if ServiceInstallFailed then Result := 10 else Result := 0;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ExitCode: Integer;
begin
  Result := '';
  if FileExists(ExpandConstant('{app}\MillionaireTray.exe')) then
    if not Exec(ExpandConstant('{app}\MillionaireTray.exe'), '--quit', '',
      SW_HIDE, ewWaitUntilTerminated, ExitCode) then begin
      Result := 'Unable to close the existing tray controller.';
      Exit;
    end;
  if FileExists(ExpandConstant('{app}\runtime\python.exe')) then
    if not Exec(ExpandConstant('{app}\runtime\python.exe'),
      '-m quantide.cli service stop', '', SW_HIDE, ewWaitUntilTerminated, ExitCode) then
      Result := 'Unable to stop the existing service. Stop it before upgrading.'
    else if ExitCode <> 0 then
      Result := 'The existing service could not be stopped. Check its service logs.';
end;

procedure RunServiceChecked(Action: String);
var
  ExitCode: Integer;
begin
  if not Exec(ExpandConstant('{app}\runtime\python.exe'),
    '-m quantide.cli service ' + Action, '', SW_HIDE, ewWaitUntilTerminated, ExitCode) then
    RaiseException('Unable to execute service command: ' + Action);
  if ExitCode <> 0 then
    RaiseException('Service command failed: ' + Action + '. Check the service logs.');
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then begin
    ServiceInstallFailed := True;
    RunServiceChecked('install');
    RunServiceChecked('start');
    ServiceInstallFailed := False;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    if not UninstallSilent then
      if MsgBox('Delete all Millionaire settings, account databases and market data?',
        mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(ExpandConstant('{commonappdata}\Millionaire'), True, True, True);
end;
