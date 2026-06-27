# Docker Auth Export

This guide shows how to use the Docker-based `cx-auth-export` helper to create a `cx` backup archive without installing Python, pipx, or `cx` on the host.

## Requirements

1. Docker must be available.
2. Windows Docker Desktop must be in Linux containers mode.
3. Treat every exported `.tar.gz` file as a sensitive login credential.
4. WSL smoke tests have passed; Windows Docker Desktop still needs real-machine validation.

## Build the Base Image

```bash
docker build -f docker/auth-export/Dockerfile -t cx-auth-export:latest .
```

## Run the Base Image with Alias

Bash / WSL / Linux / macOS:

```bash
mkdir -p out
docker run --rm -it \
  -v "$PWD/out:/out" \
  cx-auth-export:latest \
  foya3000
```

PowerShell / Windows:

```powershell
New-Item -ItemType Directory -Force -Path .\out | Out-Null

docker run --rm -it `
  --mount "type=bind,source=$((Resolve-Path .\out).Path),target=/out" `
  cx-auth-export:latest `
  foya3000
```

## Run the Base Image with Alias and Expected Email

Bash / WSL / Linux / macOS:

```bash
mkdir -p out
docker run --rm -it \
  -v "$PWD/out:/out" \
  cx-auth-export:latest \
  foya3000 --email foya3000@example.com
```

PowerShell / Windows:

```powershell
New-Item -ItemType Directory -Force -Path .\out | Out-Null

docker run --rm -it `
  --mount "type=bind,source=$((Resolve-Path .\out).Path),target=/out" `
  cx-auth-export:latest `
  foya3000 --email foya3000@example.com
```

The helper compares email after trimming whitespace and lowercasing both values.

## Build the Wrapper Image

Local base image:

```bash
docker build -f docker/auth-export/Dockerfile.account \
  --build-arg CX_AUTH_EXPORT_BASE_IMAGE=cx-auth-export:latest \
  --build-arg CX_DEFAULT_ALIAS=foya3000 \
  --build-arg CX_EXPECTED_EMAIL=foya3000@example.com \
  -t cx-auth-export:foya3000 .
```

Remote base image from Docker Hub:

```bash
docker build -f docker/auth-export/Dockerfile.account \
  --build-arg CX_AUTH_EXPORT_BASE_IMAGE=<dockerhub-namespace>/cx-auth-export:latest \
  --build-arg CX_DEFAULT_ALIAS=foya3000 \
  --build-arg CX_EXPECTED_EMAIL=foya3000@example.com \
  -t cx-auth-export:foya3000 .
```

`CX_DEFAULT_ALIAS` is required. Wrapper image build fails if it is missing.

## Run the Wrapper Image

Bash / WSL / Linux / macOS:

```bash
mkdir -p out
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

## Notes

1. If `/out/<alias>.tar.gz` already exists, the helper fails instead of overwriting it.
2. The archive is written through a temporary file and renamed only after export succeeds.
3. Do not commit exported archives to git.
4. Do not publish exported archives or send them through public channels.
