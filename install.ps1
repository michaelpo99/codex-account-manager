param(
    [switch]$NoPathUpdate
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$InstallRoot = Join-Path $env:LOCALAPPDATA "cx\app"
$BinDir = Join-Path $env:LOCALAPPDATA "Programs\cx\bin"
$TargetSrc = Join-Path $InstallRoot "cx.py"
$TargetCmd = Join-Path $BinDir "cx.cmd"
$OldTargetCmd = Join-Path $env:USERPROFILE ".local\bin\cx.cmd"

New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null
New-Item -ItemType Directory -Force -Path $BinDir | Out-Null

Copy-Item -Force -Path (Join-Path $ScriptDir "src\cx.py") -Destination $TargetSrc

$cmd = @"
@echo off
setlocal
set "CX_APP=$TargetSrc"

if not exist "%CX_APP%" (
  echo cx: cannot find "%CX_APP%". Re-run install.ps1. 1>&2
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

echo cx: Python 3 was not found. Install Python 3 from python.org or winget, then rerun install.ps1. 1>&2
exit /b 1
"@

Set-Content -Path $TargetCmd -Value $cmd -Encoding ASCII

Write-Host "Installed cx to $TargetCmd"

if ((Test-Path $OldTargetCmd) -and ($OldTargetCmd -ne $TargetCmd)) {
    Remove-Item -Force $OldTargetCmd
    Write-Host "Removed old launcher at $OldTargetCmd"
}

$hasPython = $false
if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 --version >$null 2>$null
    if ($LASTEXITCODE -eq 0) {
        $hasPython = $true
    }
}

if (-not $hasPython) {
    $pythonCommands = @()
    $pythonCommands += Get-Command python -All -ErrorAction SilentlyContinue
    $pythonCommands += Get-Command python3 -All -ErrorAction SilentlyContinue
    foreach ($pythonCommand in $pythonCommands) {
        if ($pythonCommand.Source -and ($pythonCommand.Source -notmatch "\\WindowsApps\\python3?\.exe$")) {
            $hasPython = $true
            break
        }
    }
}

if (-not $hasPython) {
    $localPython = Get-ChildItem -Path (Join-Path $env:LOCALAPPDATA "Programs\Python") -Filter "python.exe" -Recurse -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -match "\\Python\\Python[0-9]+\\python\.exe$" } |
        Select-Object -First 1
    if ($localPython) {
        $hasPython = $true
    }
}

if (-not $hasPython) {
    Write-Warning "Python 3 was not found. Install Python 3 from python.org or winget before running cx."
}

function Normalize-PathForCompare {
    param([string]$Value)
    if ([string]::IsNullOrWhiteSpace($Value)) {
        return $null
    }
    $expanded = [Environment]::ExpandEnvironmentVariables($Value.Trim().Trim('"')).TrimEnd("\")
    try {
        return [IO.Path]::GetFullPath($expanded)
    } catch {
        return $expanded
    }
}

$pathParts = [Environment]::GetEnvironmentVariable("Path", "User") -split ";"
$normalizedBinDir = Normalize-PathForCompare $BinDir
$hasPath = $pathParts | Where-Object { (Normalize-PathForCompare $_) -eq $normalizedBinDir }

if (-not $hasPath) {
    if ($NoPathUpdate) {
        Write-Host "$BinDir is not in your user PATH."
        Write-Host "Add it manually, or run install.ps1 without -NoPathUpdate."
    } else {
        $currentPath = [Environment]::GetEnvironmentVariable("Path", "User")
        $newPath = if ([string]::IsNullOrWhiteSpace($currentPath)) { $BinDir } else { "$currentPath;$BinDir" }
        [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
        $env:Path = "$env:Path;$BinDir"
        Write-Host "Added $BinDir to your user PATH."
        Write-Host "Open a new PowerShell window if cx is not found in this session."
    }
}
