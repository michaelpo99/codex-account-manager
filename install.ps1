param(
    [switch]$NoPathUpdate
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$InstallRoot = Join-Path $env:LOCALAPPDATA "cx\app"
$InstallGuiDir = Join-Path $InstallRoot "gui"
$InstallPackageDir = Join-Path $InstallRoot "cx_account_manager"
$BinDir = Join-Path $env:LOCALAPPDATA "Programs\cx\bin"
$TargetSrc = Join-Path $InstallRoot "cx.py"
$TargetRanking = Join-Path $InstallRoot "cx_ranking.py"
$TargetCmd = Join-Path $BinDir "cx.cmd"
$TargetGui = Join-Path $InstallGuiDir "cx_gui.py"
$TargetGuiCmd = Join-Path $BinDir "cx-gui.cmd"
$TargetGuiPipxCmd = Join-Path $BinDir "cx-gui-pipx.cmd"
$OldTargetCmd = Join-Path $env:USERPROFILE ".local\bin\cx.cmd"
$PipxGuiTarget = Join-Path $env:USERPROFILE ".local\bin\cx-gui.exe"
$PipxGuiLegacyTarget = Join-Path $env:USERPROFILE ".local\bin\cx-gui-pipx.exe"

New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null
New-Item -ItemType Directory -Force -Path $InstallGuiDir | Out-Null
New-Item -ItemType Directory -Force -Path $InstallPackageDir | Out-Null
New-Item -ItemType Directory -Force -Path $BinDir | Out-Null

Copy-Item -Force -Path (Join-Path $ScriptDir "src\cx.py") -Destination $TargetSrc
Copy-Item -Force -Path (Join-Path $ScriptDir "src\cx_ranking.py") -Destination $TargetRanking
Copy-Item -Force -Path (Join-Path $ScriptDir "gui\cx_gui.py") -Destination $TargetGui
Copy-Item -Force -Recurse -Path (Join-Path $ScriptDir "src\cx_account_manager\*") -Destination $InstallPackageDir

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

$guiCmd = @"
@echo off
setlocal
set "CX_GUI_APP=$TargetGui"

if not exist "%CX_GUI_APP%" (
  echo cx-gui: cannot find "%CX_GUI_APP%". Re-run install.ps1. 1>&2
  exit /b 1
)

where py >nul 2>nul
if not errorlevel 1 (
  py -3 "%CX_GUI_APP%" %*
  exit /b %errorlevel%
)

for /f "delims=" %%P in ('where python 2^>nul') do (
  echo %%P | findstr /I "\\WindowsApps\\python.exe" >nul
  if errorlevel 1 (
    "%%P" "%CX_GUI_APP%" %*
    exit /b %errorlevel%
  )
)

for /f "delims=" %%P in ('where python3 2^>nul') do (
  echo %%P | findstr /I "\\WindowsApps\\python3.exe" >nul
  if errorlevel 1 (
    "%%P" "%CX_GUI_APP%" %*
    exit /b %errorlevel%
  )
)

for /f "delims=" %%D in ('dir /b /ad "%LOCALAPPDATA%\Programs\Python\Python*" 2^>nul') do (
  if exist "%LOCALAPPDATA%\Programs\Python\%%D\python.exe" (
    "%LOCALAPPDATA%\Programs\Python\%%D\python.exe" "%CX_GUI_APP%" %*
    exit /b %errorlevel%
  )
)

echo cx-gui: Python 3 was not found. Install Python 3 from python.org or winget, then rerun install.ps1. 1>&2
exit /b 1
"@

Set-Content -Path $TargetGuiCmd -Value $guiCmd -Encoding ASCII

if (Test-Path $PipxGuiTarget) {
    Move-Item -Force -Path $PipxGuiTarget -Destination $PipxGuiLegacyTarget
    Write-Host "Moved pipx GUI launcher to $PipxGuiLegacyTarget so cx-gui uses the installed Windows launcher"
}

$pipxGuiCompatibilityTarget = if (Test-Path $PipxGuiLegacyTarget) { $PipxGuiLegacyTarget } else { $PipxGuiTarget }

$guiPipxCmd = @"
@echo off
setlocal
set "CX_GUI_PIPX=$pipxGuiCompatibilityTarget"

if not exist "%CX_GUI_PIPX%" (
  echo cx-gui-pipx: cannot find "%CX_GUI_PIPX%". Install or restore the pipx version first. 1>&2
  exit /b 1
)

"%CX_GUI_PIPX%" %*
exit /b %errorlevel%
"@

Set-Content -Path $TargetGuiPipxCmd -Value $guiPipxCmd -Encoding ASCII

Write-Host "Installed cx to $TargetCmd"
Write-Host "Installed cx GUI to $TargetGuiCmd"
if (Test-Path $pipxGuiCompatibilityTarget) {
    Write-Host "Installed pipx GUI compatibility launcher to $TargetGuiPipxCmd"
}

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

$hasGuiTheme = $false
$guiThemeInstallCommand = ""
if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('ttkbootstrap') else 1)" >$null 2>$null
    $guiThemeInstallCommand = "py -3 -m pip install ttkbootstrap"
    if ($LASTEXITCODE -eq 0) {
        $hasGuiTheme = $true
    }
}

if (-not $hasGuiTheme) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCommand -and ($pythonCommand.Source -notmatch "\\WindowsApps\\python\.exe$")) {
        & python -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('ttkbootstrap') else 1)" >$null 2>$null
        if (-not $guiThemeInstallCommand) {
            $guiThemeInstallCommand = "python -m pip install ttkbootstrap"
        }
        if ($LASTEXITCODE -eq 0) {
            $hasGuiTheme = $true
        }
    }
}

if (-not $hasGuiTheme) {
    $canPrompt = $Host.Name -eq "ConsoleHost" -and -not [Console]::IsInputRedirected
    if ($canPrompt -and $guiThemeInstallCommand) {
        $reply = Read-Host "Optional GUI theme package not installed. Install ttkbootstrap now? [Y/n]"
        if ([string]::IsNullOrWhiteSpace($reply) -or $reply -match "^[Yy](?:[Ee][Ss])?$") {
            Invoke-Expression $guiThemeInstallCommand
            if ($LASTEXITCODE -eq 0) {
                $hasGuiTheme = $true
            } else {
                Write-Warning "ttkbootstrap installation did not complete successfully."
            }
        }
    }
    if (-not $hasGuiTheme) {
        $hintCommand = if ($guiThemeInstallCommand) { $guiThemeInstallCommand } else { "python -m pip install ttkbootstrap" }
        Write-Host "Optional GUI theme package not installed. To enable the modern theme, run:"
        Write-Host $hintCommand
    }
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

function Prioritize-PathEntry {
    param(
        [string]$PathValue,
        [string]$Entry
    )

    $normalizedEntry = Normalize-PathForCompare $Entry
    $remaining = @()
    foreach ($part in ($PathValue -split ";")) {
        if ([string]::IsNullOrWhiteSpace($part)) {
            continue
        }
        if ((Normalize-PathForCompare $part) -eq $normalizedEntry) {
            continue
        }
        $remaining += $part
    }
    if ($remaining.Count -eq 0) {
        return $Entry
    }
    return "$Entry;$($remaining -join ';')"
}

$pathParts = [Environment]::GetEnvironmentVariable("Path", "User") -split ";"
$processPathParts = $env:Path -split ";"
$normalizedBinDir = Normalize-PathForCompare $BinDir
$hasPath = $pathParts | Where-Object { (Normalize-PathForCompare $_) -eq $normalizedBinDir }
$hasProcessPath = $processPathParts | Where-Object { (Normalize-PathForCompare $_) -eq $normalizedBinDir }

if ($NoPathUpdate) {
    if (-not $hasPath) {
        Write-Host "$BinDir is not in your user PATH."
        Write-Host "Add it manually, or run install.ps1 without -NoPathUpdate."
    }
} else {
    $currentPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $newPath = Prioritize-PathEntry -PathValue $currentPath -Entry $BinDir
    [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
    if ($hasPath) {
        Write-Host "Moved $BinDir to the front of your user PATH."
    } else {
        Write-Host "Added $BinDir to the front of your user PATH."
    }
}

if ($NoPathUpdate) {
    if (-not $hasProcessPath) {
        $env:Path = Prioritize-PathEntry -PathValue $env:Path -Entry $BinDir
        Write-Host "Added $BinDir to the front of this PowerShell session."
    }
} else {
    $env:Path = Prioritize-PathEntry -PathValue $env:Path -Entry $BinDir
    if ($hasProcessPath) {
        Write-Host "Moved $BinDir to the front of this PowerShell session."
    } else {
        Write-Host "Added $BinDir to the front of this PowerShell session."
    }
}

if ($NoPathUpdate -and -not $hasPath) {
    Write-Host "You can run cx and cx-gui now in this session, but open a new PowerShell window only after adding it to PATH."
}
