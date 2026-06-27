# CR-012: Docker Auth Export Helper

Status: In Progress

## 1. Background

`cx` already supports `cx add`, `cx save`, and `cx export`, so a Codex CLI login can be saved as an alias and exported as a `.tar.gz` backup.

That is still heavier than needed for teammates who only need to:

1. complete one Codex device login,
2. produce one importable `cx` backup archive,
3. avoid installing Python, pipx, `cx`, and Codex CLI on the host.

This change request introduces a Docker-based auth export helper. The user only needs Docker. The container performs Codex device login, saves the account with `cx`, and writes `/out/<alias>.tar.gz` to a host-mounted output directory.

## 2. Goals

1. Provide a reusable base Docker image for auth export.
2. Provide a wrapper Dockerfile that can preset alias and optional expected email.
3. Run Codex device login at `docker run` time, not at `docker build` time.
4. Allow alias to be passed from the CLI.
5. Support an optional expected email guard.
6. Write the backup archive to a host-mounted `/out/<alias>.tar.gz`.
7. Avoid baking `auth.json` or any backup archive into the image.
8. Keep the flow compatible with future Docker Hub publishing.

## 3. Non-Goals

1. No GUI integration.
2. No background service.
3. No Backup Folder Sync integration.
4. No CI or GitHub Actions image publishing in this CR.
5. No private registry workflow design in this CR.
6. No real company email or auth payload committed to the repo.
7. No change to the `cx export` or `cx import` archive format.
8. No replacement of existing `pipx` or installer-based workflows.

## 4. Naming

Use this helper name:

```text
cx-auth-export
```

Reasoning:

1. `backup` is too broad.
2. `auth-gen` sounds like credential generation.
3. `auth-export` matches the real behavior: perform a real login, then export it as a `cx` backup.

## 5. Deliverables

Files:

```text
docker/auth-export/Dockerfile
docker/auth-export/Dockerfile.account
docker/auth-export/cx-auth-export-entrypoint.sh
.dockerignore
```

Roles:

1. `docker/auth-export/Dockerfile`: base image.
2. `docker/auth-export/Dockerfile.account`: wrapper image with preset alias and optional expected email.
3. `docker/auth-export/cx-auth-export-entrypoint.sh`: argument parsing, login flow, email guard, and export orchestration.
4. `.dockerignore`: keep `.git`, caches, build artifacts, virtual environments, and `out/` out of the build context.

Optional user-facing operations guide:

```text
docs/docker-auth-export.md
```

## 6. Image Design

### 6.1 Base Image

The base image must:

1. install Codex CLI,
2. install Python and the local `cx` package,
3. expose `cx-auth-export` as the default entrypoint,
4. contain no login state or account data.

Supported usage:

```bash
cx-auth-export <alias> [--email expected@example.com]
cx-auth-export [--email expected@example.com]
```

### 6.2 Wrapper Image

The wrapper image presets these values:

```text
CX_DEFAULT_ALIAS
CX_EXPECTED_EMAIL
```

The wrapper must not log in or create a backup during build.

`CX_DEFAULT_ALIAS` is required for the wrapper image and must be validated at build time.

### 6.3 Docker Hub Compatibility

To support future Docker Hub publishing:

1. the wrapper image must not assume every machine already has `cx-auth-export:latest`,
2. the wrapper must accept a configurable base image reference,
3. docs must cover both local-build and Docker Hub usage,
4. tags should be compatible with `latest` and `v<version>`.

Recommended pattern:

```dockerfile
ARG CX_AUTH_EXPORT_BASE_IMAGE=cx-auth-export:latest
FROM ${CX_AUTH_EXPORT_BASE_IMAGE}
```

## 7. Safety Rules

1. `docker build` must not run `codex login`.
2. `docker build` must not create or retain `auth.json`.
3. `docker build` must not create a backup archive.
4. `auth.json` may exist only inside the running container.
5. Output archives must be treated as sensitive login credentials.
6. Output archives must not be committed to git or shared publicly.
7. If a wrapper image includes a real expected email, that image should be distributed only through a private workflow.

## 8. Runtime Flow

### 8.1 Base Image Build

```bash
docker build -f docker/auth-export/Dockerfile -t cx-auth-export:latest .
```

### 8.2 Base Image Run with Alias

Bash / WSL / Linux / macOS:

```bash
mkdir -p out
docker run --rm -it \
  -v "$PWD/out:/out" \
  cx-auth-export:latest \
  foya3000
```

Expected behavior:

1. the container prompts for Codex device login,
2. the user completes login,
3. `cx add foya3000` saves the temporary login,
4. `cx export foya3000 -o /out/foya3000.tar.gz` produces the backup.

### 8.3 Base Image Run with Alias and Expected Email

```bash
docker run --rm -it \
  -v "$PWD/out:/out" \
  cx-auth-export:latest \
  foya3000 --email foya3000@example.com
```

Expected behavior:

1. login completes,
2. the helper reads the saved account email,
3. email comparison is done after `trim + lowercase` normalization,
4. export succeeds only when the normalized email matches,
5. mismatch aborts the flow and no final output archive is produced.

### 8.4 PowerShell / Windows Docker Desktop

Windows PowerShell should prefer `--mount` instead of `-v`.

```powershell
New-Item -ItemType Directory -Force -Path .\out | Out-Null

docker run --rm -it `
  --mount "type=bind,source=$((Resolve-Path .\out).Path),target=/out" `
  cx-auth-export:latest `
  foya3000
```

Notes:

1. Windows Docker Desktop must be in Linux containers mode.
2. Bash / WSL can continue to use `-v "$PWD/out:/out"`.
3. PowerShell should prefer `--mount` to avoid path, drive letter, and whitespace issues.

## 9. Wrapper Image Usage

### 9.1 Build

Recommended wrapper Dockerfile structure:

```dockerfile
ARG CX_AUTH_EXPORT_BASE_IMAGE=cx-auth-export:latest
FROM ${CX_AUTH_EXPORT_BASE_IMAGE}

ARG CX_DEFAULT_ALIAS
ARG CX_EXPECTED_EMAIL=

RUN if [ -z "$CX_DEFAULT_ALIAS" ]; then echo "CX_DEFAULT_ALIAS is required" >&2; exit 1; fi

ENV CX_DEFAULT_ALIAS="${CX_DEFAULT_ALIAS}"
ENV CX_EXPECTED_EMAIL="${CX_EXPECTED_EMAIL}"
```

Local build:

```bash
docker build -f docker/auth-export/Dockerfile -t cx-auth-export:latest .

docker build -f docker/auth-export/Dockerfile.account \
  --build-arg CX_AUTH_EXPORT_BASE_IMAGE=cx-auth-export:latest \
  --build-arg CX_DEFAULT_ALIAS=foya3000 \
  --build-arg CX_EXPECTED_EMAIL=foya3000@example.com \
  -t cx-auth-export:foya3000 .
```

Docker Hub-oriented build:

```bash
docker build -f docker/auth-export/Dockerfile.account \
  --build-arg CX_AUTH_EXPORT_BASE_IMAGE=<dockerhub-namespace>/cx-auth-export:latest \
  --build-arg CX_DEFAULT_ALIAS=foya3000 \
  --build-arg CX_EXPECTED_EMAIL=foya3000@example.com \
  -t cx-auth-export:foya3000 .
```

### 9.2 Run

Bash / WSL:

```bash
docker run --rm -it \
  -v "$PWD/out:/out" \
  cx-auth-export:foya3000
```

PowerShell / Windows:

```powershell
New-Item -ItemType Directory -Force -Path .\out | Out-Null

docker run --rm -it `
  --mount "type=bind,source=$((Resolve-Path .\out).Path),target=/out" `
  cx-auth-export:foya3000
```

Equivalent internal command:

```bash
cx-auth-export foya3000 --email foya3000@example.com
```

## 10. Entrypoint Rules

Interface:

```bash
cx-auth-export <alias> [--email expected@example.com]
cx-auth-export [--email expected@example.com]
```

Environment defaults:

```text
CX_DEFAULT_ALIAS
CX_EXPECTED_EMAIL
```

Rules:

1. CLI alias wins over `CX_DEFAULT_ALIAS`.
2. If neither exists, the helper must show usage and fail.
3. CLI `--email` wins over `CX_EXPECTED_EMAIL`.
4. If no expected email exists, export may proceed without restriction.
5. Email comparison must use normalized values.
6. Mismatch must fail while still showing the original expected and actual values in the error output.
7. Output must be written atomically through a temporary file in the same output directory.
8. If the final output file already exists, the helper must fail without overwriting it.
9. Temp output files must be cleaned up on failure or interruption.

## 11. Portability Notes

1. Linux / macOS / WSL: use bind mount with `-v`.
2. Windows PowerShell: prefer `--mount`.
3. Windows Docker Desktop must stay in Linux containers mode.
4. WSL testing has passed for base image build and non-interactive smoke tests.
5. Windows Docker Desktop testing has not yet been completed.

## 12. Validation Plan

### Phase 1: Files

1. `docker/auth-export/Dockerfile`
2. `docker/auth-export/Dockerfile.account`
3. `docker/auth-export/cx-auth-export-entrypoint.sh`
4. `.dockerignore`

### Phase 2: Base Image

Build:

```bash
docker build -f docker/auth-export/Dockerfile -t cx-auth-export:latest .
```

Help:

```bash
docker run --rm cx-auth-export:latest --help
```

Recommended non-interactive smoke test:

```bash
docker run --rm --entrypoint sh cx-auth-export:latest -c 'command -v codex >/dev/null && cx --help >/dev/null'
```

Actual interactive export:

```bash
mkdir -p out
docker run --rm -it -v "$PWD/out:/out" cx-auth-export:latest test-account
```

Expected email guard:

```bash
docker run --rm -it -v "$PWD/out:/out" cx-auth-export:latest test-account --email expected@example.com
```

### Phase 3: Wrapper Image

Successful wrapper build:

```bash
docker build -f docker/auth-export/Dockerfile.account \
  --build-arg CX_AUTH_EXPORT_BASE_IMAGE=cx-auth-export:latest \
  --build-arg CX_DEFAULT_ALIAS=test-account \
  --build-arg CX_EXPECTED_EMAIL=expected@example.com \
  -t cx-auth-export:test-account .
```

Missing alias must fail:

```bash
docker build -f docker/auth-export/Dockerfile.account \
  --build-arg CX_AUTH_EXPORT_BASE_IMAGE=cx-auth-export:latest \
  -t cx-auth-export:missing-alias .
```

### Phase 4: Docker Hub Follow-up

When a published image exists:

```bash
docker pull <dockerhub-namespace>/cx-auth-export:latest

docker run --rm <dockerhub-namespace>/cx-auth-export:latest --help

docker build -f docker/auth-export/Dockerfile.account \
  --build-arg CX_AUTH_EXPORT_BASE_IMAGE=<dockerhub-namespace>/cx-auth-export:latest \
  --build-arg CX_DEFAULT_ALIAS=test-account \
  -t cx-auth-export:test-account .
```

## 13. Acceptance Criteria

1. Base image builds successfully.
2. Base image `--help` works.
3. Wrapper image builds successfully when alias is supplied.
4. Wrapper image build fails when alias is omitted.
5. Final output file is never overwritten automatically.
6. Interrupted or failed export does not leave the final output filename behind.
7. Expected email comparison tolerates case and surrounding whitespace differences.
8. Docs include Bash / WSL and PowerShell usage.
9. Docs clearly state that Windows Docker Desktop still requires validation before this CR can be considered complete.

## 14. Current Validation Record

Current known state:

1. WSL build and smoke tests passed.
2. Base image `--help` passed under WSL.
3. `docker run --rm --entrypoint sh cx-auth-export:latest -lc 'codex --help >/dev/null && cx --help >/dev/null'` is not a reliable smoke test with the current Codex CLI because `codex --help` requires a TTY in this environment.
4. `docker run --rm --entrypoint sh cx-auth-export:latest -c 'command -v codex >/dev/null && cx --help >/dev/null'` passed under WSL.
5. Windows Docker Desktop remains untested at this time.
