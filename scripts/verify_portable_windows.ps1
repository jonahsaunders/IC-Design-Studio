param([Parameter(Mandatory=$true)][string]$Package,[string]$Project='', [switch]$Full)
$ErrorActionPreference = 'Stop'
$packageRoot = (Resolve-Path $Package).Path
$python = Join-Path $packageRoot 'python/python.exe'
$test = Join-Path $packageRoot 'app/tests/gui_native_migration.py'
if (-not (Test-Path $python)) { throw 'Select the extracted portable Windows package.' }
$evidence = Join-Path $packageRoot 'Native acceptance with spaces café'
$arguments = @($test, '--require-windows', '--evidence', $evidence)
if ($Project) { $arguments += @('--project', (Resolve-Path $Project).Path) }
if ($Full) { $arguments += '--full' }
& $python @arguments
if ($LASTEXITCODE -ne 0) { throw 'Native migration acceptance failed; inspect the console and run artifacts.' }
$report = Get-Content (Join-Path $evidence 'native-migration.json') -Raw | ConvertFrom-Json
if ($report.status -ne 'passed' -or -not $report.native_windows) { throw 'The report does not establish Windows execution.' }
Write-Host "Windows acceptance passed. Evidence: $evidence"
$workflowTest = Join-Path $packageRoot 'app/tests/gui_native_workflows.py'
$workflowEvidence = Join-Path $packageRoot 'Native workflows with spaces café'
& $python $workflowTest '--require-windows' '--evidence' $workflowEvidence
if ($LASTEXITCODE -ne 0) { throw 'Graphical native workflow acceptance failed.' }
$workflowReport = Get-Content (Join-Path $workflowEvidence 'native-workflows.json') -Raw | ConvertFrom-Json
if ($workflowReport.status -ne 'passed' -or -not $workflowReport.native_windows) { throw 'Graphical workflow report does not establish Windows execution.' }
Write-Host "Graphical native workflows passed. Evidence: $workflowEvidence"
