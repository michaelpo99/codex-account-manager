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
- When making a user-visible release-worthy change, remind the user to consider bumping `src/cx_account_manager/__init__.py` `__version__`.
