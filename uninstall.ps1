$ErrorActionPreference = "Stop"

$installRoot = Join-Path $env:LOCALAPPDATA "cx\app"
$binDir = Join-Path $env:LOCALAPPDATA "Programs\cx\bin"
$targetCmd = Join-Path $binDir "cx.cmd"
$targetGuiCmd = Join-Path $binDir "cx-gui.cmd"
$targetGuiPipxCmd = Join-Path $binDir "cx-gui-pipx.cmd"
$pipxGuiTarget = Join-Path $env:USERPROFILE ".local\bin\cx-gui.exe"
$pipxGuiLegacyTarget = Join-Path $env:USERPROFILE ".local\bin\cx-gui-pipx.exe"
$dataDir = Join-Path $env:LOCALAPPDATA "cx"
$purgeData = $false

if ($args -contains "--purge-data") {
    $purgeData = $true
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

function Remove-PathEntry {
    param(
        [string]$PathValue,
        [string]$Entry
    )

    $normalizedEntry = Normalize-PathForCompare $Entry
    $remaining = $PathValue -split ";" | Where-Object {
        -not [string]::IsNullOrWhiteSpace($_) -and
        (Normalize-PathForCompare $_) -ne $normalizedEntry
    }
    return ($remaining -join ";")
}

if (Test-Path $targetCmd) {
    Remove-Item -Force $targetCmd
}

if (Test-Path $targetGuiCmd) {
    Remove-Item -Force $targetGuiCmd
}

if (Test-Path $targetGuiPipxCmd) {
    Remove-Item -Force $targetGuiPipxCmd
}

if ((Test-Path $pipxGuiLegacyTarget) -and -not (Test-Path $pipxGuiTarget)) {
    Move-Item -Force -Path $pipxGuiLegacyTarget -Destination $pipxGuiTarget
    Write-Host "Restored pipx GUI launcher to $pipxGuiTarget"
}

if (Test-Path $installRoot) {
    Remove-Item -Recurse -Force $installRoot
}

if ($purgeData -and (Test-Path $dataDir)) {
    Remove-Item -Recurse -Force $dataDir
}

$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
$newUserPath = Remove-PathEntry -PathValue $userPath -Entry $binDir
if ($newUserPath -ne $userPath) {
    [Environment]::SetEnvironmentVariable("Path", $newUserPath, "User")
    Write-Host "Removed $binDir from your user PATH"
}

$newProcessPath = Remove-PathEntry -PathValue $env:Path -Entry $binDir
if ($newProcessPath -ne $env:Path) {
    $env:Path = $newProcessPath
    Write-Host "Removed $binDir from this PowerShell session"
}

Write-Host "Removed $targetCmd"
Write-Host "Removed $targetGuiCmd"
Write-Host "Removed $targetGuiPipxCmd"
Write-Host "Removed $installRoot"

if ($purgeData) {
    Write-Host "Removed $dataDir"
} else {
    Write-Host "Kept account data in $dataDir"
    Write-Host "Run .\uninstall.ps1 --purge-data if you also want to delete saved accounts."
}
