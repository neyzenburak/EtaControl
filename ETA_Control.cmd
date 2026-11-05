@echo off
cd /d "%~dp0"
if not exist "%~dp0.venv\Scripts\python.exe" (
  echo Once KURULUM.ps1 dosyasini calistirin.
  pause
  exit /b 1
)
"%~dp0.venv\Scripts\python.exe" -m etacontrol
if errorlevel 1 pause
