@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%.."

where py >nul 2>nul
if errorlevel 1 (
  python "%PROJECT_ROOT%\gui\cx_gui.py" %*
) else (
  py -3 "%PROJECT_ROOT%\gui\cx_gui.py" %*
)
