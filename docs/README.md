# Docs Layout

This repository keeps long-form project documents in `docs/`.

Naming rules:

- Base specification keeps a plain name without `CR`: `codex-account-manager-spec.md`
- Documented change requests use ordered IDs so sequence is obvious: `CR-001-...md`, `CR-002-...md`
- Supporting notes can use descriptive lowercase kebab-case names without a CR number

Current structure:

- `codex-account-manager-spec.md`: original product and command specification
- `CR-001-ui-redesign.md`: completed GUI redesign change request
- `CR-002-python-packaging.md`: second documented change request for Python packaging
- `CR-003-cx-doctor.md`: proposed `cx doctor` change request

Files intentionally kept at the repository root:

- `README.md`: repo entrypoint for users
- `AGENTS.md`: agent instructions for Codex
