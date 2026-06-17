$ErrorActionPreference = "Stop"

$installRoot = Join-Path $env:LOCALAPPDATA "cx\app"
$binDir = Join-Path $env:LOCALAPPDATA "Programs\cx\bin"
$targetCmd = Join-Path $binDir "cx.cmd"
$dataDir = Join-Path $env:LOCALAPPDATA "cx"
$purgeData = $false

if ($args -contains "--purge-data") {
    $purgeData = $true
}

if (Test-Path $targetCmd) {
    Remove-Item -Force $targetCmd
}

if (Test-Path $installRoot) {
    Remove-Item -Recurse -Force $installRoot
}

if ($purgeData -and (Test-Path $dataDir)) {
    Remove-Item -Recurse -Force $dataDir
}

Write-Host "Removed $targetCmd"
Write-Host "Removed $installRoot"

if ($purgeData) {
    Write-Host "Removed $dataDir"
} else {
    Write-Host "Kept account data in $dataDir"
    Write-Host "Run .\uninstall.ps1 --purge-data if you also want to delete saved accounts."
}
