param([switch]$VerifyOnly)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
function Run-Checked([string]$Program, [string[]]$Arguments) {
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program exited with $LASTEXITCODE" }
}
if ($VerifyOnly) {
    Run-Checked python @('scripts/ci_windows_native_identity.py', '--verify')
    exit 0
}
$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
if (-not (Test-Path $vswhere)) { throw 'Visual Studio locator is missing.' }
$vs = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $vs) { throw 'Visual Studio C++ tools are missing.' }
Import-Module "$vs\Common7\Tools\Microsoft.VisualStudio.DevShell.dll"
Enter-VsDevShell -VsInstallPath $vs -SkipAutomaticLocation -DevCmdArguments '-arch=x64 -host_arch=x64'
Set-Location $root
$compiler = (Get-Command cl.exe -ErrorAction Stop).Source
Run-Checked python @('scripts/build_native.py')
Run-Checked python @('-c', 'from icstudio.native_core import load_native_core; assert load_native_core() is not None, "Built Windows native core could not be loaded"')
Run-Checked python @('scripts/ci_windows_native_identity.py', '--compiler', $compiler)
