param([string]$Output = 'build/windows-evidence')
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
$evidence = [System.IO.Path]::GetFullPath((Join-Path $root $Output))
New-Item -ItemType Directory -Force $evidence | Out-Null
$version = (python -c 'from icstudio import __version__; print(__version__)').Trim()
if ($LASTEXITCODE -ne 0) { throw 'Could not resolve the application version.' }
$commit = (git rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Could not resolve the source commit.' }
$setupPath = "dist/installers/IC-Design-Studio-$version-Windows-x64-Setup.exe"
if (-not (Test-Path $setupPath)) { throw "Build the exact Windows installer first: $setupPath" }
$setup = Get-Item $setupPath
$setupSha256 = (Get-FileHash $setup.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
$probes = @()
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
    try { Wait-Checked $exe "--release-test `"$evidence\dpi-$scale`"" }
    catch {
        $failedReport = "$evidence\dpi-$scale\release-test.json"
        if (Test-Path $failedReport) { Get-Content $failedReport -Raw | Write-Output }
        throw
    }
    $report = Get-Content "$evidence\dpi-$scale\release-test.json" -Raw | ConvertFrom-Json
    if ($report.status -ne 'passed' -or $report.frozen -ne $true -or $report.version -ne $version -or $report.build.commit -ne $commit -or $report.build.dirty -ne $false) { throw 'Installed application probe does not match the exact clean build.' }
    $probes += $report
}
Remove-Item Env:QT_SCALE_FACTOR -ErrorAction SilentlyContinue
python scripts/verify_packaged_vga.py --executable "$exe" --output "$evidence/vga"
if ($LASTEXITCODE -ne 0) { throw 'Installed Windows VGA qualification failed.' }
$shortcut = Join-Path ([Environment]::GetFolderPath('Programs')) 'IC Design Studio\IC Design Studio.lnk'
if (-not (Test-Path $shortcut)) { throw 'Start menu shortcut is missing.' }
$shell = New-Object -ComObject WScript.Shell
if ($shell.CreateShortcut($shortcut).TargetPath -ne $exe) { throw 'Start menu shortcut points to the wrong executable.' }
$command = (Get-Item 'HKCU:\Software\Classes\ICDesignStudio.Project\shell\open\command').GetValue('')
if ($command -ne "`"$exe`" --project `"%1`"") { throw 'Project association command is incorrect.' }
$invitationCommand = (Get-Item 'HKCU:\Software\Classes\icstudio\shell\open\command').GetValue('')
if ($invitationCommand -ne "`"$exe`" --join `"%1`"") { throw 'Invitation protocol command is incorrect.' }
Wait-Checked (Join-Path $install 'unins000.exe') "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /LOG=`"$evidence\uninstall.log`""
if (Test-Path $exe) { throw 'Uninstall left the application executable behind.' }
if (Test-Path 'HKCU:\Software\Classes\icstudio') { throw 'Uninstall left the invitation protocol registered.' }
if ((Get-FileHash $setup.FullName -Algorithm SHA256).Hash.ToLowerInvariant() -ne $setupSha256) { throw 'Installer changed during acceptance execution.' }
@{status='passed';version=$version;commit=$commit;installer=$setup.Name;installer_sha256=$setupSha256;probes=$probes;installed=$true;shortcuts=$true;association=$true;dpi=@(100,150,200);simulation=$true;vga=(Get-Content "$evidence/vga/probe/vga-test.json" -Raw | ConvertFrom-Json);uninstalled=$true;signing='not configured'} | ConvertTo-Json -Depth 30 | Set-Content "$evidence\windows-release.json"
