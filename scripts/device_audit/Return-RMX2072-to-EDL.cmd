@echo off
setlocal
if not defined RMX_PY set "RMX_PY=python"
for /f %%I in ('powershell.exe -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmmss-fff"') do set "RMX_STAMP=%%I"
set "RMX_REPORT=%TEMP%\rmx2072-edl\return-%RMX_STAMP%.json"
"%RMX_PY%" "%~dp0usb_edl_return.py" --mode command --output "%RMX_REPORT%" %*
set "RMX_RESULT=%ERRORLEVEL%"
echo Return log: "%RMX_REPORT%"
exit /b %RMX_RESULT%
