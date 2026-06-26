# CR-012: Docker Auth Export Helper

Status: Proposed

## 1. 背景

`cx` 的日常安裝方式需要使用者處理 Python、pipx、Codex CLI、PATH 與平台差異。對主要開發者或長期使用者而言可以接受，但對只需要協助完成一次手機驗證、產生帳號備份檔的同事來說不夠友善。

實際情境：某個 Codex 帳號綁定特定同事的手機。該同事不需要長期使用 `cx`，只需要完成 Codex device login，並產出一個可交給維護者匯入的 `cx` 備份檔。

本 CR 目標是提供 Docker 化的 auth export helper，讓同事不需要安裝 Python / pipx / `cx`，也不需要在 host 保留 Codex login 狀態。Docker container 啟動後執行 Codex device login，登入完成後用 `cx` 建立 alias 並匯出 `.tar.gz` 備份檔到 host 掛載的 `/out` 目錄。

## 2. 目標

1. 新增通用 Docker auth export image。
2. 新增專用 account wrapper image 的 Dockerfile。
3. 通用 image 不固定 alias，不固定 email。
4. alias 必須可在 `docker run` 時以參數指定。
5. expected email 為 optional，有指定才比對，未指定則不限制。
6. 專用 wrapper image 可在通用 image 之上設定預設 alias 與 expected email。
7. 不在 image build 階段登入。
8. 不把 `auth.json`、備份檔或任何登入憑證 bake 進 image。
9. 備份檔只輸出到 host 掛載的 `/out`。
10. container 建議以 `--rm` 一次性執行，結束後不保留 container 內登入狀態。

## 3. 非目標

本 CR 不做以下事項：

1. 不支援 GUI。
2. 不支援長駐 service。
3. 不支援 Backup Folder Sync。
4. 不把 image 推送到 registry。
5. 不新增 GitHub Actions 自動 build image。
6. 不把真實公司 email 或個人 email 固定寫進公開 repo。
7. 不處理備份檔加密。
8. 不取代一般 `pipx` / installer 安裝流程。

## 4. 命名

Docker helper 名稱使用：

```text
cx-auth-export
```

理由：

1. `backup` 太泛用，容易和一般資料備份混淆。
2. `auth-gen` 聽起來像產生或偽造 auth，不精確。
3. `auth-export` 較準確：透過正式 Codex device login 取得登入狀態，再匯出為 `cx` 備份檔。

## 5. 檔案位置

新增：

```text
docker/auth-export/Dockerfile
docker/auth-export/Dockerfile.account
docker/auth-export/cx-auth-export-entrypoint.sh
.dockerignore
```

`docker/auth-export/Dockerfile` 是通用 base image。

`docker/auth-export/Dockerfile.account` 是第二層 wrapper image，用 build args 設定預設 alias / expected email。

`docker/auth-export/cx-auth-export-entrypoint.sh` 是 container entrypoint，負責參數解析、執行 `cx add`、email guard、以及 `cx export`。

`.dockerignore` 避免把 `.git`、venv、cache、build 產物與 out 目錄帶入 build context。

## 6. 通用 image 行為

### 6.1 Build

```bash
docker build -f docker/auth-export/Dockerfile -t cx-auth-export .
```

### 6.2 Run：只指定 alias

```bash
docker run --rm -it \
  -v "$PWD/out:/out" \
  cx-auth-export \
  foya3000
```

行為：

1. 要求使用者完成 Codex device login。
2. 將登入結果保存為 alias `foya3000`。
3. 不比對 email。
4. 匯出 `/out/foya3000.tar.gz`。

### 6.3 Run：指定 alias 與 expected email

```bash
docker run --rm -it \
  -v "$PWD/out:/out" \
  cx-auth-export \
  foya3000 --email foya3000@example.com
```

行為：

1. 要求使用者完成 Codex device login。
2. 將登入結果保存為 alias `foya3000`。
3. 讀取保存後的 meta email。
4. 若 email 符合 expected email，匯出 `/out/foya3000.tar.gz`。
5. 若 email 不符合，停止，且不產生備份檔。

## 7. 專用 wrapper image 行為

### 7.1 Build

```bash
docker build -f docker/auth-export/Dockerfile.account \
  --build-arg CX_DEFAULT_ALIAS=foya3000 \
  --build-arg CX_EXPECTED_EMAIL=foya3000@example.com \
  -t cx-auth-export:foya3000 .
```

注意：真實公司 email 不應固定寫進公開 repo。若 image 會分享給指定同事使用，應由私人 build 指令、私有 wrapper Dockerfile、或內部 registry 管理。

### 7.2 Run

```bash
docker run --rm -it \
  -v "$PWD/out:/out" \
  cx-auth-export:foya3000
```

行為等同於在通用 image 執行：

```bash
cx-auth-export foya3000 --email foya3000@example.com
```

但同事不需要手動輸入 alias 或 email。

## 8. 安全規則

1. `docker build` 不得執行 `codex login`。
2. `docker build` 不得產生或保存 `auth.json`。
3. `docker build` 不得產生帳號備份檔。
4. `auth.json` 只允許存在於一次性 running container 內。
5. 輸出的 `.tar.gz` 備份檔視同登入憑證。
6. 備份檔不得提交到 git。
7. 備份檔不得放到公開聊天室、公開 issue、公開 artifact 或不可信雲端。
8. image 可以公開，但專用 wrapper image 若包含公司 email，建議只在內部流通。

## 9. Entry point 規格

entrypoint 支援：

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

1. 若 CLI 參數提供 alias，優先使用參數 alias。
2. 若 CLI 參數未提供 alias，使用 `CX_DEFAULT_ALIAS`。
3. 若兩者都沒有，報錯。
4. 若 CLI 參數提供 `--email`，優先使用該 email。
5. 若 CLI 參數未提供 `--email`，使用 `CX_EXPECTED_EMAIL`。
6. 若沒有 expected email，不做 email 限制。
7. email mismatch 時不得產生備份檔。

## 10. 執行計畫

### Phase 1: Docker files

1. 新增 `docker/auth-export/Dockerfile`。
2. 新增 `docker/auth-export/Dockerfile.account`。
3. 新增 `docker/auth-export/cx-auth-export-entrypoint.sh`。
4. 新增 `.dockerignore`。

### Phase 2: 本機驗證

驗證通用 image：

```bash
docker build -f docker/auth-export/Dockerfile -t cx-auth-export .
docker run --rm cx-auth-export --help
```

驗證 Codex CLI 與 cx 都存在：

```bash
docker run --rm cx-auth-export sh -lc 'codex --help >/dev/null && cx --help >/dev/null'
```

驗證實際 auth export：

```bash
mkdir -p out
docker run --rm -it -v "$PWD/out:/out" cx-auth-export test-account
```

驗證 expected email guard：

```bash
docker run --rm -it -v "$PWD/out:/out" cx-auth-export test-account --email expected@example.com
```

### Phase 3: 專用 wrapper image 驗證

```bash
docker build -f docker/auth-export/Dockerfile.account \
  --build-arg CX_DEFAULT_ALIAS=test-account \
  --build-arg CX_EXPECTED_EMAIL=expected@example.com \
  -t cx-auth-export:test-account .

docker run --rm -it -v "$PWD/out:/out" cx-auth-export:test-account
```

## 11. 驗收標準

1. 通用 image 可 build。
2. 通用 image `--help` 可顯示用法。
3. 通用 image 可用參數 alias 執行。
4. expected email 未指定時不限制 email。
5. expected email 指定且符合時會匯出 `/out/<alias>.tar.gz`。
6. expected email 指定但不符合時，不會產生備份檔。
7. wrapper image 可在通用 image 之上設定預設 alias / expected email。
8. repo 不包含真實 auth 憑證或備份檔。
9. `.dockerignore` 排除 `out` 與常見 build/cache 目錄。

## 12. 開放問題

1. 是否要提供 PowerShell wrapper，讓非技術同事不用輸入 Docker 指令？
2. 是否要提供 `docker save` / `docker load` 的交付流程文件？
3. 是否要推到 GHCR private registry？第一版不建議。
4. 是否要 pin Codex CLI 版本？第一版先用 npm latest，穩定後可 pin。
5. 是否要提供備份檔加密？不在本 CR 範圍內。
