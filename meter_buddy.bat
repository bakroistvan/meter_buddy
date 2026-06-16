@echo off
setlocal

set "ROOT=%~dp0"

where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  py -3 "%ROOT%tools\meter_buddy.py" %*
  exit /b %ERRORLEVEL%
)

where python >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  python "%ROOT%tools\meter_buddy.py" %*
  exit /b %ERRORLEVEL%
)

echo Python was not found. Install Python 3 and try again.
exit /b 1

