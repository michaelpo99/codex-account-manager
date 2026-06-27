# CR-012: Docker Auth Export Helper

Status: Proposed

## 1. 背景

`cx` 目前提供 `cx add`、`cx save`、`cx export` 等能力，可把 Codex CLI 帳號保存成 alias，並匯出成 `.tar.gz` 備份檔。

但對部分同事來說，以下門檻仍然偏高：

1. host 需要安裝 Python、pipx、`cx`、Codex CLI。
2. host 需要保留 Codex login 狀態。
3. 若只是要產生一份可匯入的帳號備份檔，完整安裝整套工具太重。

本 CR 目標是提供 Docker 化的 auth export helper，讓使用者只需要有 Docker，就能在暫時性的 container 內完成 Codex device login，接著用 `cx` 建立 alias 並匯出 `.tar.gz` 備份檔到 host 掛載的 `/out` 目錄。

## 2. 目標

1. 提供通用的 Docker auth export image。
2. 提供可預先設定 alias / expected email 的 wrapper image Dockerfile。
3. container 在 `docker run` 時執行 Codex device login。
4. alias 可在 `docker run` 時由 CLI 參數指定。
5. expected email 為 optional guard，可用來避免登入錯誤帳號。
6. 匯出結果必須落到 host 掛載的 `/out/<alias>.tar.gz`。
7. `docker build` 過程不得產生或保存登入狀態。
8. container 預設使用 `--rm` 的一次性使用模式。
9. 規格需兼顧未來發佈到 Docker Hub 的使用情境。

## 3. 非目標

本 CR 不包含：

1. 不新增 GUI。
2. 不新增常駐背景服務。
3. 不整合 Backup Folder Sync。
4. 不在本 CR 內處理 GitHub Actions / CI 自動 build。
5. 不在本 CR 內處理公司私有 registry 權限管理。
6. 不把真實公司 email 或任何 `auth.json` 寫入 repo。
7. 不修改既有 `cx export` / `cx import` 格式。
8. 不取代 `pipx` / installer 安裝流程；這是額外提供的交付方式。

## 4. 名稱

Docker helper 名稱使用：

```text
cx-auth-export
```

命名說明：

1. `backup` 太泛，不夠明確。
2. `auth-gen` 容易誤解成憑證生成器。
3. `auth-export` 較準確：透過正式 Codex device login 取得登入狀態，再匯出為 `cx` 備份檔。

## 5. 交付內容

新增：

```text
docker/auth-export/Dockerfile
docker/auth-export/Dockerfile.account
docker/auth-export/cx-auth-export-entrypoint.sh
.dockerignore
```

說明：

1. `docker/auth-export/Dockerfile`：通用 base image。
2. `docker/auth-export/Dockerfile.account`：第二層 wrapper image，用 build args 設定預設 alias / expected email。
3. `docker/auth-export/cx-auth-export-entrypoint.sh`：container entrypoint，負責參數解析、執行 `cx add`、email guard、以及 `cx export`。
4. `.dockerignore`：避免把 `.git`、venv、cache、build 產物與 `out` 目錄帶入 build context。

## 6. Image 設計

### 6.1 Base image

base image 職責：

1. 安裝 Codex CLI。
2. 安裝 Python 與本 repo 的 `cx` 套件。
3. 內建 `cx-auth-export` entrypoint。
4. 不包含任何登入狀態或帳號資料。

base image 必須支援：

```bash
cx-auth-export <alias> [--email expected@example.com]
cx-auth-export [--email expected@example.com]
```

### 6.2 Wrapper image

wrapper image 是選配，用來預填：

```text
CX_DEFAULT_ALIAS
CX_EXPECTED_EMAIL
```

wrapper image 只是把預設值包進環境變數，不得在 build 階段做 login 或產生 backup。

### 6.3 Docker Hub 相容性

考量未來要把 image 發佈到 Docker Hub，規格需滿足：

1. base image 不應依賴本機固定 tag 名稱，例如硬寫 `FROM cx-auth-export:latest` 後假設每台機器都先手動 build 過。
2. wrapper image 應支援用 build arg 指定 base image，例如：

```dockerfile
ARG CX_AUTH_EXPORT_BASE_IMAGE=cx-auth-export:latest
FROM ${CX_AUTH_EXPORT_BASE_IMAGE}
```

3. 文件需同時說明：
   - 本機 build base image 的流程。
   - 從 Docker Hub 直接拉 base image 的流程。
4. tag 策略至少要能對應：
   - `latest`
   - `v<version>`
5. 若未來提供公開 image，repo 與文件不得包含真實公司 email。

## 7. 安全限制

1. `docker build` 不得執行 `codex login`。
2. `docker build` 不得產生或保存 `auth.json`。
3. `docker build` 不得產生帳號備份檔。
4. `auth.json` 只可存在於 running container 的暫時目錄。
5. `.tar.gz` 備份檔必須被視為敏感憑證，不可提交到 git。
6. `.tar.gz` 備份檔不得出現在 issue、artifact、公開分享連結或公開 repo。
7. 若使用 wrapper image，真實公司 email 只能來自私有 build 流程、私有 Dockerfile、或私有 registry 管理。

## 8. 執行流程

### 8.1 Base image build

```bash
docker build -f docker/auth-export/Dockerfile -t cx-auth-export:latest .
```

### 8.2 Base image run：只給 alias

```bash
docker run --rm -it \
  -v "$PWD/out:/out" \
  cx-auth-export:latest \
  foya3000
```

預期流程：

1. container 顯示 Codex device login 提示。
2. 使用者完成登入。
3. `cx add foya3000` 保存暫時登入結果。
4. `cx export foya3000 -o /out/foya3000.tar.gz` 產生備份檔。

### 8.3 Base image run：alias + expected email

```bash
docker run --rm -it \
  -v "$PWD/out:/out" \
  cx-auth-export:latest \
  foya3000 --email foya3000@example.com
```

預期流程：

1. container 顯示 Codex device login 提示。
2. 使用者完成登入。
3. entrypoint 讀取登入後 account meta email。
4. 若 email 符合 expected email，才輸出 `/out/foya3000.tar.gz`。
5. 若 email 不符，必須中止，且不得輸出備份檔。

## 9. Wrapper image 使用方式

### 9.1 Build

建議 wrapper Dockerfile 支援：

```dockerfile
ARG CX_AUTH_EXPORT_BASE_IMAGE=cx-auth-export:latest
FROM ${CX_AUTH_EXPORT_BASE_IMAGE}

ARG CX_DEFAULT_ALIAS
ARG CX_EXPECTED_EMAIL=

ENV CX_DEFAULT_ALIAS="${CX_DEFAULT_ALIAS}"
ENV CX_EXPECTED_EMAIL="${CX_EXPECTED_EMAIL}"
```

本機 build 範例：

```bash
docker build -f docker/auth-export/Dockerfile \
  -t cx-auth-export:latest .

docker build -f docker/auth-export/Dockerfile.account \
  --build-arg CX_AUTH_EXPORT_BASE_IMAGE=cx-auth-export:latest \
  --build-arg CX_DEFAULT_ALIAS=foya3000 \
  --build-arg CX_EXPECTED_EMAIL=foya3000@example.com \
  -t cx-auth-export:foya3000 .
```

若未來 base image 已發布到 Docker Hub，則可改用：

```bash
docker build -f docker/auth-export/Dockerfile.account \
  --build-arg CX_AUTH_EXPORT_BASE_IMAGE=<dockerhub-namespace>/cx-auth-export:latest \
  --build-arg CX_DEFAULT_ALIAS=foya3000 \
  --build-arg CX_EXPECTED_EMAIL=foya3000@example.com \
  -t cx-auth-export:foya3000 .
```

### 9.2 Run

```bash
docker run --rm -it \
  -v "$PWD/out:/out" \
  cx-auth-export:foya3000
```

等價於在 base image 中執行：

```bash
cx-auth-export foya3000 --email foya3000@example.com
```

## 10. Entry point 規格

entrypoint 介面：

```bash
cx-auth-export <alias> [--email expected@example.com]
cx-auth-export [--email expected@example.com]
```

環境變數：

```text
CX_DEFAULT_ALIAS
CX_EXPECTED_EMAIL
```

規則：

1. 若 CLI 提供 alias，優先使用 CLI alias。
2. 若 CLI 未提供 alias，改用 `CX_DEFAULT_ALIAS`。
3. 若兩者都沒有，應顯示 usage 並失敗。
4. 若 CLI 提供 `--email`，優先使用 CLI email。
5. 若 CLI 未提供 `--email`，可使用 `CX_EXPECTED_EMAIL`。
6. 若沒有 expected email，允許直接匯出。
7. email mismatch 必須中止，且不得留下輸出檔。

## 11. 可攜性與權限

1. 需要考慮 Linux / macOS / Windows + Docker Desktop / WSL 的掛載路徑差異。
2. 文件至少要提供 Bash 與 PowerShell 兩套範例。
3. 需避免在 Linux / WSL 上把 `/out` 產物寫成 host 不易清理的 root 擁有檔案。
4. 若第一版暫不處理 UID/GID 映射，文件必須明確記錄限制。

PowerShell 範例：

```powershell
New-Item -ItemType Directory -Force -Path .\out | Out-Null
docker run --rm -it `
  -v "${PWD}\out:/out" `
  cx-auth-export:latest `
  foya3000
```

Bash 範例：

```bash
mkdir -p out
docker run --rm -it \
  -v "$PWD/out:/out" \
  cx-auth-export:latest \
  foya3000
```

## 12. 驗證方式

### Phase 1: Docker files

1. 新增 `docker/auth-export/Dockerfile`。
2. 新增 `docker/auth-export/Dockerfile.account`。
3. 新增 `docker/auth-export/cx-auth-export-entrypoint.sh`。
4. 新增 `.dockerignore`。

### Phase 2: Base image 驗證

build：

```bash
docker build -f docker/auth-export/Dockerfile -t cx-auth-export:latest .
```

help：

```bash
docker run --rm cx-auth-export:latest --help
```

驗證 Codex CLI 與 `cx` 存在：

```bash
docker run --rm --entrypoint sh cx-auth-export:latest -lc 'codex --help >/dev/null && cx --help >/dev/null'
```

驗證實際 auth export：

```bash
mkdir -p out
docker run --rm -it -v "$PWD/out:/out" cx-auth-export:latest test-account
```

驗證 expected email guard：

```bash
docker run --rm -it -v "$PWD/out:/out" cx-auth-export:latest test-account --email expected@example.com
```

### Phase 3: Wrapper image 驗證

```bash
docker build -f docker/auth-export/Dockerfile.account \
  --build-arg CX_AUTH_EXPORT_BASE_IMAGE=cx-auth-export:latest \
  --build-arg CX_DEFAULT_ALIAS=test-account \
  --build-arg CX_EXPECTED_EMAIL=expected@example.com \
  -t cx-auth-export:test-account .

docker run --rm -it -v "$PWD/out:/out" cx-auth-export:test-account
```

### Phase 4: Docker Hub 驗證

若未來發佈到 Docker Hub，至少驗證：

```bash
docker pull <dockerhub-namespace>/cx-auth-export:latest

docker run --rm <dockerhub-namespace>/cx-auth-export:latest --help

docker build -f docker/auth-export/Dockerfile.account \
  --build-arg CX_AUTH_EXPORT_BASE_IMAGE=<dockerhub-namespace>/cx-auth-export:latest \
  --build-arg CX_DEFAULT_ALIAS=test-account \
  -t cx-auth-export:test-account .
```

## 13. 驗收條件

1. base image 可成功 build。
2. base image `--help` 可正常顯示 usage。
3. base image 可接受 CLI alias 並完成匯出。
4. 未提供 expected email 時，可直接匯出。
5. expected email 正確時，會輸出 `/out/<alias>.tar.gz`。
6. expected email 不符時，流程失敗，且不輸出備份檔。
7. wrapper image 可正確傳入預設 alias / expected email。
8. repo 與 image build 過程不包含任何 `auth.json`。
9. `.dockerignore` 有排除 `out` 與常見 build/cache 目錄。
10. 文件包含 Bash 與 PowerShell 操作範例。
11. 規格不依賴「本機一定先有 `cx-auth-export:latest`」這種隱含前提。

## 14. 開放問題

1. 是否要提供 PowerShell wrapper，讓非技術同事不用直接輸入 Docker 指令？
2. 是否要提供 `docker save` / `docker load` 的交付文件，方便離線傳遞？
3. Docker Hub 發佈時，是否需要同時推 `latest` 與 `v<version>` tag？
4. 是否要 pin Codex CLI 版本，而不是永遠使用 npm 最新版？
5. Linux / WSL 的 host 檔案權限問題，是要在 image 內處理，還是先在文件中明示限制？
