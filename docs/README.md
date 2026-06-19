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
- `CR-005-enterprise-light-theme.md`: proposed Enterprise Light visual refresh with `ttkbootstrap` and `ttk` fallback

Files intentionally kept at the repository root:

- `README.md`: repo entrypoint for users
- `AGENTS.md`: agent instructions for Codex
