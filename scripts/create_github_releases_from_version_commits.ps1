param(
  [string] $Repo = "michaelpo99/codex-account-manager",
  [string] $Since = "",
  [switch] $DryRun
)

$ErrorActionPreference = "Stop"
$VersionFile = "src/cx_account_manager/__init__.py"
$VersionPattern = '__version__\s*=\s*["''](?<version>\d+\.\d+\.\d+)["'']'

function Require-Command {
  param([string] $Name)
  if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
    throw "Required command not found: $Name"
  }
}

function Get-VersionAtCommit {
  param([string] $Commit)

  $content = git show "$Commit`:$VersionFile" 2>$null
  if ($LASTEXITCODE -ne 0 -or -not $content) {
    return $null
  }

  $text = $content -join "`n"
  $match = [regex]::Match($text, $VersionPattern)
  if (-not $match.Success) {
    return $null
  }
  return $match.Groups["version"].Value
}

function Test-GitHubReleaseExists {
  param(
    [string] $Tag,
    [string] $RepoFullName
  )

  $previousErrorActionPreference = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try {
    $null = gh release view $Tag --repo $RepoFullName 2>$null
    return $LASTEXITCODE -eq 0
  }
  catch {
    return $false
  }
  finally {
    $ErrorActionPreference = $previousErrorActionPreference
  }
}

Require-Command git
Require-Command gh

git rev-parse --is-inside-work-tree *> $null
if ($LASTEXITCODE -ne 0) {
  throw "Run this script inside the codex-account-manager git repository."
}

$range = "HEAD"
if ($Since.Trim()) {
  git cat-file -e "$Since^{commit}"
  if ($LASTEXITCODE -ne 0) {
    throw "Since commit not found: $Since"
  }
  $range = "$Since..HEAD"
}

$commits = @(git log --reverse --format=%H $range -- $VersionFile)
if ($commits.Count -eq 0) {
  Write-Host "No version-file commits found."
  exit 0
}

$lastVersion = $null
if ($Since.Trim()) {
  $lastVersion = Get-VersionAtCommit $Since
}

$releaseCandidates = @()
$seenVersions = @{}

foreach ($commit in $commits) {
  $version = Get-VersionAtCommit $commit
  if (-not $version) {
    continue
  }

  if ($version -eq $lastVersion) {
    continue
  }

  $lastVersion = $version
  if ($seenVersions.ContainsKey($version)) {
    continue
  }

  $seenVersions[$version] = $true
  $releaseCandidates += [pscustomobject]@{
    Version = $version
    Tag = "v$version"
    Sha = $commit
  }
}

if ($releaseCandidates.Count -eq 0) {
  Write-Host "No new version changes found."
  exit 0
}

foreach ($candidate in $releaseCandidates) {
  if (Test-GitHubReleaseExists -Tag $candidate.Tag -RepoFullName $Repo) {
    Write-Host "Skip existing release $($candidate.Tag)"
    continue
  }

  $notes = "Release $($candidate.Tag)`n`nTarget commit: $($candidate.Sha)`nVersion source: $VersionFile"
  if ($DryRun) {
    Write-Host "Would create release $($candidate.Tag) at $($candidate.Sha)"
    continue
  }

  Write-Host "Creating release $($candidate.Tag) at $($candidate.Sha)"
  gh release create $candidate.Tag `
    --repo $Repo `
    --target $candidate.Sha `
    --title $candidate.Tag `
    --notes $notes
}
