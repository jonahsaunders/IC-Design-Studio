@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
if errorlevel 1 goto failure
py -3.12 --version >nul 2>&1
if errorlevel 1 goto fallback
py -3.12 scripts\benchmark_windows.py %*
goto result
:fallback
py -3 scripts\benchmark_windows.py %*
:result
if errorlevel 1 goto failure
exit /b 0
:failure
echo Benchmark setup or execution failed. See the specific error above and README.md.
echo If the py command is unavailable, install 64-bit Python 3.12 with the Python launcher.
pause
exit /b 1
