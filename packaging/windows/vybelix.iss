#define AppName "Vybelix"
#define AppVersion "0.1.0"
#define AppPublisher "Vybelix"
#define AppExeName "Vybelix.exe"
#define BuildDir AddBackslash(SourcePath) + "..\..\build\windows\dist-desktop\Vybelix"

[Setup]
AppId={{8B31A91D-20C6-4D7F-9EEF-EDFE1D1E2D87}}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\Programs\Vybelix
DefaultGroupName=Vybelix
UninstallDisplayIcon={app}\{#AppExeName}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
OutputDir=..\..\dist
OutputBaseFilename=Vybelix-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=vybelix.ico
CloseApplications=yes
Uninstallable=yes

[Tasks]
Name: "desktopicon"; Description: "Créer un raccourci sur le Bureau"; GroupDescription: "Raccourcis :"; Flags: unchecked

[Files]
Source: "redist\MicrosoftEdgeWebview2Setup.exe"; Flags: dontcopy noencryption
Source: "{#BuildDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Vybelix"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\Vybelix"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon
Name: "{group}\Désinstaller Vybelix"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Lancer Vybelix"; Flags: nowait postinstall skipifsilent

[Code]
const
  WebView2ClientGuid = '{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';

function HasWebView2RuntimeInHive(RootKey: Integer; const SubKey: String): Boolean;
var
  Version: String;
begin
  Result := RegQueryStringValue(RootKey, SubKey, 'pv', Version) and
    (Version <> '') and (Version <> '0.0.0.0');
end;

function IsWebView2RuntimeInstalled: Boolean;
var
  SubKey: String;
begin
  SubKey := 'SOFTWARE\Microsoft\EdgeUpdate\Clients\' + WebView2ClientGuid;
  Result := HasWebView2RuntimeInHive(HKLM32, SubKey) or
    HasWebView2RuntimeInHive(HKLM64, SubKey) or
    HasWebView2RuntimeInHive(HKCU32, SubKey) or
    HasWebView2RuntimeInHive(HKCU64, SubKey);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  Result := '';
  if IsWebView2RuntimeInstalled then
    Exit;

  try
    ExtractTemporaryFile('MicrosoftEdgeWebview2Setup.exe');
  except
    Result := 'Impossible de préparer le composant Microsoft WebView2. Relance le téléchargement de l’installateur Vybelix.';
    Exit;
  end;

  if not Exec(ExpandConstant('{tmp}\MicrosoftEdgeWebview2Setup.exe'),
    '/silent /install', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
  begin
    Result := 'Impossible de lancer l’installation du runtime Microsoft WebView2.';
    Exit;
  end;

  if (ResultCode <> 0) and (ResultCode <> 3010) then
  begin
    Result := 'L’installation de Microsoft WebView2 a échoué (code ' +
      IntToStr(ResultCode) + '). Vérifie la connexion Internet puis relance l’installation.';
    Exit;
  end;

  if not IsWebView2RuntimeInstalled then
    Result := 'Microsoft WebView2 ne semble pas installé. Vérifie la connexion Internet puis relance l’installation.';
end;
