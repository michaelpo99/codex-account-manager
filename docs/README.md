# Docs Layout

This repository keeps long-form project documents in `docs/`.

Naming rules:

- Base specification keeps a plain name without `CR`: `codex-account-manager-spec.md`
- Documented change requests use ordered IDs so sequence is obvious: `CR-001-...md`, `CR-002-...md`
- Supporting notes can use descriptive lowercase kebab-case names without a CR number

Current structure:

- `codex-account-manager-spec.md`: original product and command specification
- `CR-001-ui-redesign.md`: completed GUI redesign change request
- `CR-002-python-packaging.md`: completed Python packaging change request
- `CR-003-cx-doctor.md`: completed `cx doctor` change request
- `CR-004-doctor-ui.md`: completed GUI integration for `cx doctor`
- `CR-005-enterprise-light-theme.md`: completed Enterprise Light visual refresh with `ttkbootstrap` and `ttk` fallback
- `CR-006-auto-refresh-settings.md`: completed GUI auto refresh and settings persistence
- `CR-007-cli-renew.md`: completed CLI renew change request
- `CR-008-gui-renew-and-toolbar.md`: completed GUI renew and toolbar change request
- `CR-009-gui-update-check.md`: completed GUI update check change request
- `release-process.md`: GitHub Release rules and helper script usage

Bug fix notes:

- `bugfix-login-dialog-device-code-copy.md`: completed fix for Add Account device code copy and Ctrl+C behavior

Files intentionally kept at the repository root:

- `README.md`: repo entrypoint for users
- `AGENTS.md`: agent instructions for Codex
