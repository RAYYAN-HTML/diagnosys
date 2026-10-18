@echo off
setlocal
set "DIAGNOSYS_PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%DIAGNOSYS_PYTHON%" set "DIAGNOSYS_PYTHON=C:\Users\USER\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if not exist "%DIAGNOSYS_PYTHON%" (
  echo Python was not found. Create the .venv environment and install the project first.
  pause
  exit /b 1
)
cd /d "%~dp0"
set "PYTHONPATH=%~dp0src;%PYTHONPATH%"
"%DIAGNOSYS_PYTHON%" -m diagnosys
pause
