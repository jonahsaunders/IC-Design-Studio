param([string]$Output = 'build/windows-evidence')
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
$evidence = [System.IO.Path]::GetFullPath((Join-Path $root $Output))
New-Item -ItemType Directory -Force $evidence | Out-Null
$setup = Get-ChildItem dist/installers/*Windows-x64-Setup.exe | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $setup) { throw 'Build the Windows installer first.' }
$install = Join-Path $evidence 'Installed App With Spaces'
function Wait-Checked([string]$Program,[string]$Arguments) {
    $p = Start-Process -FilePath $Program -ArgumentList $Arguments -PassThru
    if (-not $p.WaitForExit(120000)) { Stop-Process -Id $p.Id -Force; throw "$Program timed out" }
    if ($p.ExitCode -ne 0) { throw "$Program exited with $($p.ExitCode)" }
}
Wait-Checked $setup.FullName "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /DIR=`"$install`" /TASKS=`"desktopicon,associate`" /LOG=`"$evidence\install.log`""
$exe = Join-Path $install 'ICDesignStudio.exe'
if (-not (Test-Path $exe)) { throw 'Installed executable is missing.' }
foreach ($scale in @('1','1.5','2')) {
    $env:QT_SCALE_FACTOR = $scale
    Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
    Wait-Checked $exe "--release-test `"$evidence\dpi-$scale`""
    $report = Get-Content "$evidence\dpi-$scale\release-test.json" -Raw | ConvertFrom-Json
    if ($report.status -ne 'passed' -or -not $report.frozen) { throw 'Installed application probe failed.' }
}
Remove-Item Env:QT_SCALE_FACTOR -ErrorAction SilentlyContinue
$shortcut = Join-Path ([Environment]::GetFolderPath('Programs')) 'IC Design Studio\IC Design Studio.lnk'
if (-not (Test-Path $shortcut)) { throw 'Start menu shortcut is missing.' }
$shell = New-Object -ComObject WScript.Shell
if ($shell.CreateShortcut($shortcut).TargetPath -ne $exe) { throw 'Start menu shortcut points to the wrong executable.' }
$command = (Get-Item 'HKCU:\Software\Classes\ICDesignStudio.Project\shell\open\command').GetValue('')
if ($command -ne "`"$exe`" --project `"%1`"") { throw 'Project association command is incorrect.' }
Wait-Checked (Join-Path $install 'unins000.exe') "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /LOG=`"$evidence\uninstall.log`""
if (Test-Path $exe) { throw 'Uninstall left the application executable behind.' }
@{status='passed';installed=$true;shortcuts=$true;association=$true;dpi=@(100,150,200);simulation=$true;uninstalled=$true;signing='not configured'} | ConvertTo-Json | Set-Content "$evidence\windows-release.json"
