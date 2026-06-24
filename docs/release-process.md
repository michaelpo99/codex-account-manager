# Release Process

The package version source of truth is:

```python
src/cx_account_manager/__init__.py
__version__ = "X.Y.Z"
```

A GitHub Release should be created only when `__version__` changes. The release tag must be `v<version>`, for example `v4.5.2`, and the release target must be the exact commit where that version first appears.

## Create releases from version commits

From the repository root, run a dry run first:

```powershell
.\scripts\create_github_releases_from_version_commits.ps1 -Since 33de9d4c2f415636ff955c37dc6db1764f4a9726 -DryRun
```

If the output is correct, create the missing GitHub Releases:

```powershell
.\scripts\create_github_releases_from_version_commits.ps1 -Since 33de9d4c2f415636ff955c37dc6db1764f4a9726
```

The script uses `gh release view` to skip releases that already exist and `gh release create` for missing releases.

Release notes are generated from the commit subjects between the previous version commit and the current version commit. The script filters low-signal subjects such as merge commits, plain `release X.Y.Z`, and routine docs/test/chore messages, then writes the remaining meaningful subjects into the release body.

If you want to refresh the body of an existing GitHub Release with regenerated notes, use:

```powershell
.\scripts\create_github_releases_from_version_commits.ps1 -Since 33de9d4c2f415636ff955c37dc6db1764f4a9726 -UpdateExisting -DryRun
.\scripts\create_github_releases_from_version_commits.ps1 -Since 33de9d4c2f415636ff955c37dc6db1764f4a9726 -UpdateExisting
```

## Requirements

Install and authenticate GitHub CLI first:

```powershell
gh auth login
gh auth status
```

The script must be run inside a git checkout of this repository because it uses `git log` and `git show` to locate version commits.

## Rules for agents

- Do not create a release for a normal code-only commit.
- Do create or propose a release when `src/cx_account_manager/__init__.py` `__version__` changes.
- Use `-DryRun` before creating releases.
- Do not commit GitHub credentials or tokens.
