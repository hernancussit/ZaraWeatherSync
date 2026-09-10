; Script de instalación Inno Setup 6 para ZaraWeatherSync
; Permite generar el asistente interactivo de instalación (ZaraWeatherSync_Setup.exe)

#define MyAppName "ZaraWeatherSync"
#define MyAppVersion "1.2.3"
#define MyAppPublisher "Hernan Cussit"
#define MyAppURL "https://github.com/hernancussit/ZaraWeatherSync"
#define MyAppExeName "ZaraWeatherSync.exe"

[Setup]
; Identificador de la aplicación
AppId={{D37E8A10-A9C3-4811-9E2B-0FE1B3B9D924}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} v{#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases

; Ubicación de instalación
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes

; Soporte flexible para instalación como Usuario o Administrador
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog commandline

; Directorio y nombre de salida
OutputDir=..\dist
OutputBaseFilename=ZaraWeatherSync_Setup
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}

; Compresión optimizada
Compression=lzma2/ultra64
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
DisableProgramGroupPage=yes

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\assets\icon.ico"; DestDir: "{app}\assets"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\assets\icon.ico"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\assets\icon.ico"; Tasks: desktopicon
Name: "{autoprograms}\Desinstalar {#MyAppName}"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: files; Name: "{app}\update.bat"
