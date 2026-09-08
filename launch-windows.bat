@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  py -3 -m venv .venv
  if errorlevel 1 goto failure
  .venv\Scripts\python.exe -m pip install -r requirements.txt
  if errorlevel 1 goto failure
)
.venv\Scripts\python.exe main.py %*
if errorlevel 1 goto failure
exit /b 0
:failure
echo Setup or startup failed. Install 64-bit Python 3.12 and see README.md.
pause
exit /b 1
