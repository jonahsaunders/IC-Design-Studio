# Run from an x64 Python 3.12 environment with requirements-build.txt installed.
param([switch]$SkipBuild)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
function Run-Checked([string]$Program, [string[]]$Arguments) {
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program exited with $LASTEXITCODE" }
}
if (-not $SkipBuild) {
    Run-Checked python @('scripts/stage_windows_ngspice.py','--ensure')
    Run-Checked python @('scripts/check_simulation_assets.py')
    $env:ICSTUDIO_TEST_NGSPICE = (Resolve-Path 'icstudio/assets/runtime/ngspice/ngspice.exe').Path
    $vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
    if (Test-Path $vswhere) {
        $vs = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
        if ($vs) {
            Import-Module "$vs\Common7\Tools\Microsoft.VisualStudio.DevShell.dll"
            Enter-VsDevShell -VsInstallPath $vs -SkipAutomaticLocation -DevCmdArguments '-arch=x64 -host_arch=x64'
            Set-Location $root
        }
    }
    Run-Checked python @('scripts/build_native.py')
    Run-Checked python @('-m','unittest','discover','-s','tests','-p','test_*.py')
    Run-Checked python @('scripts/package.py')
}
$version = (& python -c 'from icstudio import __version__; print(__version__)').Trim()
Run-Checked python @('scripts/check_simulation_assets.py','--bundle','dist/ICDesignStudio/_internal','--runtime')
Run-Checked python @('scripts/release_archives.py','--output','dist/installers')
Copy-Item "dist/installers/IC-Design-Studio-$version-Source.zip" 'dist/ICDesignStudio/' -Force
Copy-Item LICENSE,README.md,THIRD_PARTY_NOTICES.md 'dist/ICDesignStudio/' -Force
$iscc = (Get-Command ISCC.exe -ErrorAction SilentlyContinue).Source
if (-not $iscc) { $iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" }
if (-not (Test-Path $iscc)) { throw 'Install Inno Setup 6 from https://jrsoftware.org/isinfo.php, then rerun with -SkipBuild.' }
Run-Checked $iscc @("/DAppVersion=$version",'packaging/windows/installer.iss')
Compress-Archive -Path 'dist/ICDesignStudio' -DestinationPath "dist/installers/IC-Design-Studio-$version-Windows-x64-Portable.zip" -Force
Get-ChildItem dist/installers -File | Where-Object { $_.Extension -in '.zip','.exe' } | Get-FileHash -Algorithm SHA256 | ForEach-Object { "$($_.Hash.ToLower())  $(Split-Path $_.Path -Leaf)" } | Set-Content dist/installers/SHA256SUMS-Windows.txt
