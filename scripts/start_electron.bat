@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_electron.ps1"
exit /b %errorlevel%
