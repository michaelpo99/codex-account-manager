@echo off
setlocal
set SCRIPT_DIR=%~dp0
for %%I in ("%SCRIPT_DIR%..") do set PROJECT_ROOT=%%~fI
set "CX_APP=%PROJECT_ROOT%\src\cx.py"

if not exist "%CX_APP%" (
  echo cx: cannot find "%CX_APP%". 1>&2
  exit /b 1
)

where py >nul 2>nul
if not errorlevel 1 (
  py -3 "%CX_APP%" %*
  exit /b %errorlevel%
)

for /f "delims=" %%P in ('where python 2^>nul') do (
  echo %%P | findstr /I "\\WindowsApps\\python.exe" >nul
  if errorlevel 1 (
    "%%P" "%CX_APP%" %*
    exit /b %errorlevel%
  )
)

for /f "delims=" %%P in ('where python3 2^>nul') do (
  echo %%P | findstr /I "\\WindowsApps\\python3.exe" >nul
  if errorlevel 1 (
    "%%P" "%CX_APP%" %*
    exit /b %errorlevel%
  )
)

for /f "delims=" %%D in ('dir /b /ad "%LOCALAPPDATA%\Programs\Python\Python*" 2^>nul') do (
  if exist "%LOCALAPPDATA%\Programs\Python\%%D\python.exe" (
    "%LOCALAPPDATA%\Programs\Python\%%D\python.exe" "%CX_APP%" %*
    exit /b %errorlevel%
  )
)

echo cx: Python 3 was not found. Install Python 3 from python.org or winget. 1>&2
exit /b 1
