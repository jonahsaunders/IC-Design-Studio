#ifndef AppVersion
  #error AppVersion must be passed to ISCC
#endif
#define AppName "IC Design Studio"
#if !FileExists("..\..\dist\ICDesignStudio\_internal\icstudio\assets\runtime\ngspice\ngspice.exe")
  #error Stage and verify NGSpice before compiling the installer (build-windows.bat).
#endif
#if !FileExists("..\..\dist\ICDesignStudio\_internal\icstudio\assets\pdks\collection.json")
  #error The bundled simulation PDK collection is missing.
#endif
[Setup]
AppId={{65CC59BF-792E-47B1-A540-9F67063181FC}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=IC Design Studio contributors
DefaultDirName={localappdata}\Programs\ICDesignStudio
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\..\dist\installers
OutputBaseFilename=IC-Design-Studio-{#AppVersion}-Windows-x64-Setup
SetupIconFile=..\..\icstudio\assets\app.ico
UninstallDisplayIcon={app}\ICDesignStudio.exe
LicenseFile=..\..\LICENSE
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
ChangesAssociations=yes
[Tasks]
Name: desktopicon; Description: "Create a desktop shortcut"; Flags: unchecked
Name: associate; Description: "Open .icproj files with IC Design Studio"; Flags: unchecked
[Files]
Source: "..\..\dist\ICDesignStudio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\ICDesignStudio.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\ICDesignStudio.exe"; Tasks: desktopicon
[Registry]
Root: HKA; Subkey: "Software\Classes\icstudio"; ValueType: string; ValueData: "URL:IC Design Studio invitation"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\icstudio"; ValueType: string; ValueName: "URL Protocol"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\icstudio\DefaultIcon"; ValueType: string; ValueData: "{app}\ICDesignStudio.exe,0"
Root: HKA; Subkey: "Software\Classes\icstudio\shell\open\command"; ValueType: string; ValueData: """{app}\ICDesignStudio.exe"" --join ""%1"""
Root: HKA; Subkey: "Software\Classes\.icproj\OpenWithProgids"; ValueType: string; ValueName: "ICDesignStudio.Project"; ValueData: ""; Flags: uninsdeletevalue; Tasks: associate
Root: HKA; Subkey: "Software\Classes\ICDesignStudio.Project"; ValueType: string; ValueData: "IC Design Studio project"; Flags: uninsdeletekey; Tasks: associate
Root: HKA; Subkey: "Software\Classes\ICDesignStudio.Project\DefaultIcon"; ValueType: string; ValueData: "{app}\ICDesignStudio.exe,0"; Tasks: associate
Root: HKA; Subkey: "Software\Classes\ICDesignStudio.Project\shell\open\command"; ValueType: string; ValueData: """{app}\ICDesignStudio.exe"" --project ""%1"""; Tasks: associate
[Run]
Filename: "{app}\ICDesignStudio.exe"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent
