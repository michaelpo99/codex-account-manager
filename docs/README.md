# Docs Layout

This repository keeps long-form project documents in `docs/`.

Naming rules:

- Base specification keeps a plain name without `CR`: `codex-account-manager-spec.md`
- Documented change requests live under `docs/cr/` and keep ordered IDs: `docs/cr/CR-001-...md`, `docs/cr/CR-002-...md`
- Bug fix notes live under `docs/bugfix/` and use ordered IDs: `docs/bugfix/bugfix-0001-...md`, `docs/bugfix/bugfix-0002-...md`, `docs/bugfix/bugfix-0003-...md`
- Supporting notes can use descriptive lowercase kebab-case names at the `docs/` root

Current structure:

- `codex-account-manager-spec.md`: original product and command specification
- `cr/CR-001-ui-redesign.md`: completed GUI redesign change request
- `cr/CR-002-python-packaging.md`: completed Python packaging change request
- `cr/CR-003-cx-doctor.md`: completed `cx doctor` change request
- `cr/CR-004-doctor-ui.md`: completed GUI integration for `cx doctor`
- `cr/CR-005-enterprise-light-theme.md`: completed Enterprise Light visual refresh with `ttkbootstrap` and `ttk` fallback
- `cr/CR-006-auto-refresh-settings.md`: completed GUI auto refresh and settings persistence
- `cr/CR-007-cli-renew.md`: completed CLI renew change request
- `cr/CR-008-gui-renew-and-toolbar.md`: completed GUI renew and toolbar change request
- `cr/CR-009-gui-update-check.md`: completed GUI update check change request
- `cr/CR-010-left-based-usage-display.md`: proposed left-based usage display for status and GUI
- `cr/CR-011-backup-folder-sync.md`: completed Backup Folder Sync and safe automatic import change request
- `cr/CR-012-docker-auth-export.md`: proposed Docker Auth Export Helper change request
- `docker-auth-export.md`: user-facing Docker Auth Export usage guide
- `bugfix/bugfix-0001-login-dialog-device-code-copy.md`: completed fix for Add Account device code copy and Ctrl+C behavior
- `bugfix/bugfix-0002-renew-missing-email-cache.md`: completed fix for renew failure when expired tokens cannot reveal the old account email
- `bugfix/bugfix-0003-renew-status-identity-fallback.md`: proposed fix for status fallback display and renew identity fallback under newer auth payloads
- `release-process.md`: GitHub Release rules and helper script usage

Files intentionally kept at the repository root:

- `README.md`: repo entrypoint for users
- `AGENTS.md`: agent instructions for Codex

Status tracking:

- Each CR or bugfix document keeps its own `Status:` line as the source of truth.
- Supported values are `Proposed`, `In Progress`, `Completed`, and `Blocked`.
- Use `python scripts/docs_status.py --mode check` to see a cross-platform summary in PowerShell or WSL.
- Use `python scripts/docs_status.py --mode index` to print a Markdown table of the current CR and bugfix status list.
