# Codex Instructions

This repository builds `cx`, a Codex CLI account manager.

When a task involves `cx` commands, account switching, account status, backup/import/export, Windows installation, or the GUI:

- Treat `cx manual` as the command reference for user-facing `cx` behavior.
- If `cx` is installed in the current environment, run `cx manual --lang zh-TW` or `cx manual --lang en` when command details are needed.
- On Windows, if `cx` is not on PATH, try the installed launcher directly:
  `& "$env:LOCALAPPDATA\Programs\cx\bin\cx.cmd" manual --lang zh-TW`
- If the installed launcher is unavailable but this repo is checked out, try the repo launcher:
  `.\bin\cx.cmd manual --lang zh-TW`
- If both launchers are unavailable, run `.\install.ps1` first, then retry `cx manual --lang zh-TW`.
- If `cx` still cannot run, read `src/cx.py` and `docs/codex-account-manager-spec.md`, especially the `cx manual` section, before inventing commands.
- Prefer generating actual `cx` commands over vague instructions.
- Do not assume WSL, Windows Native, and VS Code extension auth states are shared; `cx use` only switches the current environment's `CODEX_HOME/auth.json`.

Release handling:

- The package version source of truth is `src/cx_account_manager/__init__.py` `__version__`.
- If `__version__` changes, treat that commit as a release commit and automatically create the matching GitHub Release.
- Release versions must use `MAJOR.MINOR.PATCH`, for example `4.5.2`.
- GitHub Release tags must use `v<version>`, for example `v4.5.2`.
- The GitHub Release target must be the exact commit where that version first appears in `__version__`.
- Never create a release only because ordinary code changed; require a version bump.
- Before creating a release, check whether it already exists and skip existing releases.
- Prefer using `scripts/create_github_releases_from_version_commits.ps1` with `-DryRun` first, then without `-DryRun`.
- Standard release flow:
  1. Ensure `gh` is available on `PATH`.
  2. Run `.\scripts\create_github_releases_from_version_commits.ps1 -DryRun`.
  3. If the dry run looks correct, run `.\scripts\create_github_releases_from_version_commits.ps1`.
  4. If needed, set `-Since <commit-sha>` to backfill from a specific commit.
- Do not commit GitHub tokens, credentials, or machine-specific release configuration.
