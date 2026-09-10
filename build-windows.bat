@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe py -3.12 -m venv .venv
if errorlevel 1 goto failure
call .venv\Scripts\activate.bat
python -m pip install -r requirements-build.txt
if errorlevel 1 goto failure
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_windows.ps1
if errorlevel 1 goto failure
exit /b 0
:failure
echo Build failed. See the error above and docs\WINDOWS_RELEASE.md.
exit /b 1
