param(
  [string] $Repo = "michaelpo99/codex-account-manager",
  [string] $Since = "",
  [switch] $DryRun,
  [switch] $UpdateExisting
)

$ErrorActionPreference = "Stop"
$VersionFile = "src/cx_account_manager/__init__.py"
$VersionPattern = '__version__\s*=\s*["''](?<version>\d+\.\d+\.\d+)["'']'
$ConventionalPrefixPattern = '^(?<prefix>feat|fix|docs|chore|test|refactor|perf|ci|build)(\([^)]+\))?:\s*'
$LowSignalPatterns = @(
  '^Merge\b',
  '^release\s+v?\d+\.\d+\.\d+$',
  '^bump\s+version\b'
)

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

function Get-PreviousVersionCommit {
  param([string] $Commit)

  $previous = @(git log --format=%H "$Commit^" -- $VersionFile)
  if ($previous.Count -eq 0) {
    return $null
  }
  return $previous[0]
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

function Get-CommitEntriesInRange {
  param(
    [string] $StartCommit,
    [string] $EndCommit
  )

  $range = $EndCommit
  if ($StartCommit) {
    $range = "$StartCommit..$EndCommit"
  }
  $entries = New-Object System.Collections.ArrayList
  foreach ($line in @(git log --reverse --format='%H%x09%s' $range)) {
    if (-not $line) {
      continue
    }
    $parts = $line -split "`t", 2
    if ($parts.Count -lt 2) {
      continue
    }
    [void]$entries.Add([pscustomobject]@{
      Sha = $parts[0]
      Subject = $parts[1]
    })
  }
  return @($entries.ToArray())
}

function Normalize-CommitSubject {
  param([string] $Subject)

  $text = $Subject.Trim()
  if (-not $text) {
    return $null
  }

  $match = [regex]::Match($text, $ConventionalPrefixPattern, [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
  if ($match.Success) {
    $text = $text.Substring($match.Length).Trim()
  }

  if (-not $text) {
    return $null
  }

  return ($text.Substring(0, 1).ToUpperInvariant() + $text.Substring(1))
}

function Test-LowSignalCommitSubject {
  param([string] $Subject)

  $prefixMatch = [regex]::Match($Subject.Trim(), $ConventionalPrefixPattern, [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
  if ($prefixMatch.Success) {
    $prefix = $prefixMatch.Groups["prefix"].Value.ToLowerInvariant()
    if ($prefix -in @("docs", "test", "chore", "ci", "build")) {
      return $true
    }
  }

  foreach ($pattern in $LowSignalPatterns) {
    if ($Subject -match $pattern) {
      return $true
    }
  }
  return $false
}

function Test-DocsOnlyCommit {
  param([string] $Commit)

  $paths = @(git show --pretty=format: --name-only $Commit)
  if ($paths.Count -eq 0) {
    return $false
  }

  foreach ($path in $paths) {
    $trimmed = $path.Trim()
    if (-not $trimmed) {
      continue
    }
    if ($trimmed.StartsWith("docs/")) {
      continue
    }
    if ($trimmed -like "*.md") {
      continue
    }
    if (-not $trimmed.StartsWith("docs/")) {
      return $false
    }
  }

  return $true
}

function Select-MeaningfulCommitSubjects {
  param([object[]] $Entries)

  $preferred = New-Object System.Collections.Generic.List[string]
  $fallback = New-Object System.Collections.Generic.List[string]
  $seen = @{}

  foreach ($entry in $Entries) {
    $subject = [string]$entry.Subject
    $normalized = Normalize-CommitSubject $subject
    if (-not $normalized) {
      continue
    }

    if (-not $seen.ContainsKey($normalized)) {
      $seen[$normalized] = $true
      $fallback.Add($normalized)
    }

    if (Test-LowSignalCommitSubject $subject) {
      continue
    }

    if (Test-DocsOnlyCommit $entry.Sha) {
      continue
    }

    if (-not $preferred.Contains($normalized)) {
      $preferred.Add($normalized)
    }
  }

  if ($preferred.Count -gt 0) {
    return @($preferred)
  }
  return @($fallback)
}

function Build-ReleaseNotes {
  param(
    [string] $Tag,
    [string] $Version,
    [string] $TargetCommit,
    [string] $PreviousCommit,
    [string] $PreviousVersion
  )

  $subjects = Select-MeaningfulCommitSubjects (Get-CommitEntriesInRange -StartCommit $PreviousCommit -EndCommit $TargetCommit)
  $lines = New-Object System.Collections.Generic.List[string]
  $lines.Add("Release $Tag")
  $lines.Add("")

  if ($PreviousVersion) {
    $lines.Add("Changes since v$PreviousVersion")
  }
  else {
    $lines.Add("Changes in this release")
  }

  if ($subjects.Count -gt 0) {
    foreach ($subject in $subjects) {
      $lines.Add("- $subject")
    }
  }
  else {
    $lines.Add("- Version update to $Version")
  }

  $lines.Add("")
  $lines.Add("Commit range")
  if ($PreviousCommit -and $PreviousVersion) {
    $lines.Add("- Previous version commit: $PreviousCommit (v$PreviousVersion)")
  }
  elseif ($PreviousCommit) {
    $lines.Add("- Previous version commit: $PreviousCommit")
  }
  else {
    $lines.Add("- Previous version commit: repository start")
  }
  $lines.Add("- Target commit: $TargetCommit")
  $lines.Add("")
  $lines.Add("Version source")
  $lines.Add("- $VersionFile")
  return ($lines -join "`n")
}

function Write-Utf8NoBomFile {
  param(
    [string] $Path,
    [string] $Content
  )

  $encoding = New-Object System.Text.UTF8Encoding($false)
  [System.IO.File]::WriteAllText($Path, $Content, $encoding)
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
  $previousCommit = Get-PreviousVersionCommit $commit
  $previousVersion = $null
  if ($previousCommit) {
    $previousVersion = Get-VersionAtCommit $previousCommit
  }
  $releaseCandidates += [pscustomobject]@{
    Version = $version
    Tag = "v$version"
    Sha = $commit
    PreviousCommit = $previousCommit
    PreviousVersion = $previousVersion
  }
}

if ($releaseCandidates.Count -eq 0) {
  Write-Host "No new version changes found."
  exit 0
}

foreach ($candidate in $releaseCandidates) {
  $notes = Build-ReleaseNotes `
    -Tag $candidate.Tag `
    -Version $candidate.Version `
    -TargetCommit $candidate.Sha `
    -PreviousCommit $candidate.PreviousCommit `
    -PreviousVersion $candidate.PreviousVersion

  $notesFile = Join-Path $env:TEMP "$($candidate.Tag)-release-notes.md"
  Write-Utf8NoBomFile -Path $notesFile -Content $notes

  try {
    $exists = Test-GitHubReleaseExists -Tag $candidate.Tag -RepoFullName $Repo
    if ($exists -and -not $UpdateExisting) {
      Write-Host "Skip existing release $($candidate.Tag)"
      continue
    }

    if ($DryRun) {
      if ($exists) {
        Write-Host "Would update existing release $($candidate.Tag) at $($candidate.Sha)"
      }
      else {
        Write-Host "Would create release $($candidate.Tag) at $($candidate.Sha)"
      }
      Write-Host "----- BEGIN NOTES $($candidate.Tag) -----"
      Write-Host $notes
      Write-Host "----- END NOTES $($candidate.Tag) -----"
      continue
    }

    if ($exists) {
      Write-Host "Updating existing release $($candidate.Tag) at $($candidate.Sha)"
      gh release edit $candidate.Tag `
        --repo $Repo `
        --title $candidate.Tag `
        --notes-file $notesFile
      continue
    }

    Write-Host "Creating release $($candidate.Tag) at $($candidate.Sha)"
    gh release create $candidate.Tag `
      --repo $Repo `
      --target $candidate.Sha `
      --title $candidate.Tag `
      --notes-file $notesFile
  }
  finally {
    Remove-Item -LiteralPath $notesFile -ErrorAction SilentlyContinue
  }
}
