# CR-003: 新增 `cx doctor` 環境診斷指令

Status: Completed

## 1. 背景

`cx` 常見問題多半不是單一程式錯誤，而是執行環境不同造成的落差。例如 Windows Native、WSL、PowerShell、VS Code、不同 `CODEX_HOME`、不同 `codex` 安裝位置，都可能讓使用者以為自己切了帳號，但實際影響的是另一個環境。

目前排查這類問題時，需要人工逐項詢問：

- 目前在哪個 OS / shell 執行。
- Python 與 `cx` 實際路徑。
- `CODEX_HOME` 指向哪裡。
- `auth.json` 是否存在。
- `cx` data dir 是否存在。
- 已保存帳號數量與目前 alias。
- `codex` 是否找得到。
- `codex app-server` 是否可用。

`cx doctor` 的目標是產生一份標準化、脫敏、可貼給 AI agent 或維護者的環境快照。

## 2. 目標

新增 CLI 指令：

```bash
cx doctor
```

第一版只做「目前環境」診斷，不跨環境、不自動修復、不嘗試切換帳號。

需求：

1. 預設輸出人類可讀格式。
2. 支援 JSON 輸出：

```bash
cx doctor --json
```

3. 支援跳過較慢的 app-server 檢查：

```bash
cx doctor --skip-app-server
```

4. 預設不得輸出 token、完整 `auth.json`、cookie、access token、refresh token 等敏感資訊。
5. 診斷項目失敗時不應直接 crash，應列出該項失敗與原因。
6. 執行 `doctor` 不得改變 `CODEX_HOME/auth.json`、current alias、accounts 目錄或備份資料。

## 3. 非目標

本 CR 不做以下事項：

1. 不自動修復環境。
2. 不自動安裝 Codex CLI。
3. 不自動修改 PATH。
4. 不自動登入 Codex。
5. 不讀出或顯示 `auth.json` 原始內容。
6. 不新增 `--target` 跨環境診斷。
7. 不在第一版整合 GUI。
8. 不要求判斷所有 Codex CLI 版本差異。

## 4. 指令設計

第一版支援：

```bash
cx doctor [--json] [--skip-app-server]
```

暫不支援：

```bash
cx doctor --target ...
cx doctor --redact
```

原因：第一版預設就應該足夠安全，不需要靠 `--redact` 才避免敏感資訊外洩。若未來真的需要輸出 alias list、email 或更完整路徑，再另外設計 `--verbose` 或 `--include-aliases`。

## 5. 輸出內容

### 5.1 Human output

範例：

```text
cx doctor

[System]
  OS: Windows
  Platform: Windows-...
  Python: 3.12.10 (C:\Users\...\python.exe)
  cx script: D:\ai_prj\codex-account-manager\src\cx.py
  WSL: no

[Paths]
  data dir: C:\Users\...\AppData\Local\cx
  accounts dir: exists
  temp dir: exists
  CODEX_HOME: C:\Users\...\.codex
  auth.json: exists, parse ok

[Accounts]
  saved accounts: 4
  current alias: set

[Codex]
  CX_CODEX_BIN: not set
  executable: C:\Users\...\AppData\Roaming\npm\codex.cmd
  version: 0.x.x
  app-server: ok

[WSL]
  wsl.exe: found
  distros: 2

Result: OK
```

### 5.2 JSON output

範例：

```json
{
  "ok": true,
  "warnings": [],
  "errors": [],
  "system": {
    "os": "Windows",
    "platform": "Windows-...",
    "python_version": "3.12.10",
    "python_executable": "C:\\...\\python.exe",
    "cx_script": "D:\\...\\src\\cx.py",
    "is_wsl": false
  },
  "paths": {
    "data_dir": "C:\\...\\AppData\\Local\\cx",
    "accounts_dir_exists": true,
    "temp_dir_exists": true,
    "codex_home": "C:\\...\\.codex",
    "auth_json_exists": true,
    "auth_json_parse_ok": true
  },
  "accounts": {
    "count": 4,
    "current_alias_set": true
  },
  "codex": {
    "cx_codex_bin": null,
    "executable": "C:\\...\\codex.cmd",
    "version": "0.x.x",
    "app_server": {
      "checked": true,
      "ok": true,
      "error": null
    }
  },
  "wsl": {
    "checked": true,
    "available": true,
    "distro_count": 2
  }
}
```

第一版 JSON 不輸出 alias list，不輸出 email，不輸出 `auth.json` 內容。

## 6. 檢查項目

### 6.1 System

檢查：

- OS name
- platform string
- Python version
- Python executable
- current working directory
- `cx` script path
- 是否在 WSL 中執行

可使用：

- `os.name`
- `sys.platform`
- `platform.platform()`
- `platform.python_version()`
- `sys.executable`
- `Path(__file__).resolve()`
- 既有 `is_wsl()` 函式

### 6.2 cx paths

檢查：

- `DATA_DIR`
- `ACCOUNTS_DIR`
- `CURRENT_FILE`
- `TEMP_DIR`
- 目錄是否存在
- 目錄是否可讀
- 必要時檢查是否可寫，但不要建立測試檔

### 6.3 CODEX_HOME 與 auth.json

檢查：

- `CODEX_HOME`
- `CODEX_AUTH_FILE`
- `auth.json` exists / missing
- 檔案大小是否大於 0
- JSON 是否可 parse

限制：

- 不輸出 `auth.json` 原文。
- 不輸出 token、cookie、authorization header。
- 權限檢查可延後；第一版只在 Linux/macOS 容易判斷時提供 warning。

### 6.4 Accounts

檢查：

- saved accounts count
- current alias 是否設定
- current alias 是否對應到已保存帳號

輸出限制：

- 第一版不輸出完整 alias list。
- `current alias` 在 human output 可以顯示為 `set` / `not set`。
- JSON 使用 `current_alias_set: true/false`。

### 6.5 Codex executable

使用既有邏輯：

- `find_codex_executable()`
- `codex_executable()`
- `CX_CODEX_BIN`
- Windows extra path candidates

檢查：

- 是否找得到 `codex`。
- 找到的 executable path。
- 若找不到，列出明確 error 與建議。

### 6.6 Codex version

嘗試執行：

```bash
codex --version
```

要求：

- timeout 5 秒。
- 失敗時記錄 warning，不視為 blocking error。
- 不因版本查詢失敗中斷整份 doctor report。

### 6.7 app-server

第一版保留 app-server 檢查，但允許跳過：

```bash
cx doctor --skip-app-server
```

檢查方式：

- 若目前 `CODEX_AUTH_FILE` 存在，呼叫既有 `request_app_server(CODEX_AUTH_FILE, timeout_sec=10)`。
- 成功則 app-server ok。
- 失敗則記錄 error。
- 若 `--skip-app-server`，輸出 checked=false / skipped。

注意：

- 不應改變目前帳號。
- 不應切換 current alias。
- 不應把 app-server 回傳中的敏感內容輸出。

### 6.8 WSL

在 Windows Native 環境下：

- 檢查 `wsl.exe` 是否存在。
- 若存在，執行 `wsl.exe --list --quiet`。
- 只輸出 distro count，不輸出 distro names。

在 WSL 內：

- 標示目前在 WSL。
- 可使用 `WSL_DISTRO_NAME` 判斷是否有 distro name，但第一版不需要輸出完整名稱。

WSL 不存在不是 error。

## 7. 結果分級與回傳碼

每個檢查項目可產生：

- `ok`
- `warning`
- `error`
- `skipped`

回傳碼：

- `0`: 沒有 blocking error。允許存在 warning。
- `1`: 發現 blocking error，例如找不到 `codex`、data dir 無法讀取、app-server 檢查失敗。
- `2`: `doctor` 指令本身發生不可恢復錯誤。

這樣設計可避免單純 warning 讓 shell / CI 誤判整體失敗。

## 8. 實作建議

主要修改：

```text
src/cx.py
```

若 helper 明顯變多，可新增：

```text
src/cx_doctor.py
```

建議第一版先用 dict 組 report，避免為單一指令建立過多抽象。若後續 GUI 要共用，再考慮 dataclass。

### 8.1 Parser

在 `build_parser()` 新增：

```python
doctor_parser = subparsers.add_parser("doctor", help="Diagnose cx, Codex CLI, and environment setup")
doctor_parser.add_argument("--json", action="store_true")
doctor_parser.add_argument("--skip-app-server", action="store_true")
doctor_parser.set_defaults(func=cmd_doctor)
```

### 8.2 Manual

更新 `cx manual --lang zh-TW` 與 `--lang en`，加入：

```bash
cx doctor [--json] [--skip-app-server]
```

說明：

- 用於產生目前環境診斷快照。
- 不輸出 token 或 `auth.json` 原文。
- 若只想看路徑與環境，可加 `--skip-app-server`。

### 8.3 Timeout

外部命令必須設定 timeout：

- `codex --version`: 5 秒
- `wsl.exe --list --quiet`: 5 秒
- app-server: 10 秒

## 9. 測試需求

新增測試檔：

```text
tests/test_doctor.py
```

測試建議：

1. `cx doctor --json` 輸出合法 JSON。
2. JSON 包含 `system`、`paths`、`codex`、`accounts`、`wsl`。
3. 找不到 `codex` 時不 crash，回傳 `1`。
4. 沒有 saved accounts 時輸出 warning，但可回傳 `0`。
5. `--skip-app-server` 不呼叫 `request_app_server()`。
6. `cx manual` 包含 doctor 指令。
7. 外部命令 timeout 時有合理 warning 或 error。
8. 輸出不包含測試用假 token 字串。

測試中應 mock：

- `find_codex_executable()`
- `subprocess.run()`
- `request_app_server()`
- filesystem paths

避免測試依賴真實 Codex CLI、真實 app-server 或真實 WSL。

## 10. 驗收標準

CLI 驗收：

```bash
cx doctor
cx doctor --json
cx doctor --skip-app-server
cx manual --lang zh-TW
cx manual --lang en
```

行為驗收：

1. 沒有 Codex CLI 時，doctor 能輸出明確 error，不產生 traceback。
2. 沒有 saved accounts 時，doctor 能輸出 warning，不視為 fatal。
3. 沒有 `auth.json` 時，doctor 能輸出 warning 或 error，但不 crash。
4. `--json` 輸出可被 `json.loads()` 解析。
5. `--skip-app-server` 不啟動 app-server。
6. 執行 doctor 不改變目前 `CODEX_HOME/auth.json`。
7. 執行 doctor 不切換 current alias。
8. 執行 doctor 不新增、不刪除、不覆蓋帳號資料。

回歸驗收：

```bash
cx list
cx status
cx best
cx best --allow-blocked
cx use <alias>
cx add <alias>
cx save <alias>
cx export
cx import
cx backup-list
```

既有 tests 應全部通過。

## 11. README 更新

新增一節：

```markdown
## 環境診斷：cx doctor
```

內容說明：

- `cx doctor` 用於產生標準化環境快照。
- 它不會輸出 token 或 `auth.json` 原文。
- 發生環境問題時，可把 `cx doctor --json --skip-app-server` 或一般輸出貼給 AI agent / 維護者。
- 若不想啟動 app-server，可用 `cx doctor --skip-app-server`。

## 12. 分階段

### Phase 1：CLI doctor

- 新增 `cx doctor`
- 支援 human output
- 支援 `--json`
- 支援 `--skip-app-server`
- 基本檢查 system / paths / auth / codex / accounts / WSL count
- 更新 manual
- 加 tests

### Phase 2：GUI 整合

本 CR 不要求 Phase 2 一起完成。未來可在 GUI `More` 選單加入：

```text
Run Doctor
Copy Doctor Report
```

## 13. 完成定義

本 CR 完成時，使用者遇到環境問題，可以執行：

```bash
cx doctor
```

報告應足以判斷常見問題：

- Codex CLI 是否找得到。
- Python / cx 執行位置。
- Windows Native 或 WSL 環境。
- `CODEX_HOME` 與 `auth.json` 狀態。
- cx data dir 與 saved accounts 狀態。
- app-server 是否可用。

整個過程不得暴露登入憑證或 token。
