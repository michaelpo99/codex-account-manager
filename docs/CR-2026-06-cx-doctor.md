# CR-2026-06：新增 `cx doctor` 環境診斷指令

## 1. 背景

`cx` 的主要風險通常不是單一 Python bug，而是執行環境差異。使用者可能在 Windows Native、WSL、指定 WSL distro、PowerShell、VS Code、Codex CLI 等不同環境之間切換。若發生問題，AI agent 或維護者需要先知道：

- 使用者在哪個 OS / shell 下執行。
- Python 是否可用。
- `cx` 實際執行的是哪份程式。
- `codex` 是否找得到。
- `CX_CODEX_BIN` 是否設定。
- `CODEX_HOME` 指向哪裡。
- `auth.json` 是否存在。
- `cx` data dir 是否存在。
- 已保存帳號數量。
- `codex app-server` 是否能啟動並回應。
- WSL distro 是否可偵測。

目前這些資料需要人工或 AI agent 指示使用者逐項查詢。`cx doctor` 的目標不是取代 AI agent，而是產生一份標準化、脫敏、可貼給 AI agent 或維護者的環境快照。

## 2. 目標

1. 新增 CLI 指令：

```bash
cx doctor
```

2. 輸出目前環境診斷資訊。
3. 預設輸出人類可讀格式。
4. 支援 JSON 輸出，方便 GUI 或 AI agent 解析：

```bash
cx doctor --json
```

5. 預設不得輸出 token、完整 `auth.json`、cookie、access token、refresh token 等敏感資訊。
6. 診斷失敗時不應直接 crash；應列出該項檢查失敗與原因。
7. 回傳碼應能反映診斷結果：
   - 0：沒有發現阻斷性問題。
   - 1：發現 warning 或 error。
   - 2：發生命令本身不可恢復錯誤。

## 3. 非目標

本次 CR 不做以下事項：

1. 不自動修復環境。
2. 不自動安裝 Codex CLI。
3. 不自動修改 PATH。
4. 不自動登入 Codex。
5. 不讀出或顯示 `auth.json` 原始內容。
6. 不要求 doctor 能判斷所有 Codex CLI 版本差異。
7. 不要求 GUI 第一階段一定接入 doctor。

## 4. 指令設計

### 4.1 基本用法

```bash
cx doctor
```

輸出範例：

```text
cx doctor

[System]
  OS: Windows 11
  Python: 3.12.4 (C:\Users\...\python.exe)
  cx script: C:\Users\...\cx.py
  data dir: C:\Users\...\AppData\Local\cx

[Codex]
  codex executable: C:\Users\...\AppData\Roaming\npm\codex.cmd
  CX_CODEX_BIN: not set
  codex version: 0.x.x
  app-server: ok

[Auth]
  CODEX_HOME: C:\Users\...\.codex
  auth.json: exists
  saved accounts: 4
  current alias: michaelpo

[WSL]
  wsl.exe: found
  distros: Ubuntu-22.04, Debian

Result: OK
```

### 4.2 JSON 輸出

```bash
cx doctor --json
```

輸出結構建議：

```json
{
  "ok": true,
  "warnings": [],
  "errors": [],
  "system": {
    "os": "Windows",
    "platform": "Windows-...",
    "python_version": "3.12.4",
    "python_executable": "C:\\...\\python.exe",
    "cx_script": "C:\\...\\cx.py"
  },
  "paths": {
    "data_dir": "C:\\...\\AppData\\Local\\cx",
    "accounts_dir_exists": true,
    "codex_home": "C:\\...\\.codex",
    "auth_json_exists": true
  },
  "codex": {
    "cx_codex_bin": null,
    "executable": "C:\\...\\codex.cmd",
    "version": "0.x.x",
    "app_server": {
      "ok": true,
      "error": null
    }
  },
  "accounts": {
    "count": 4,
    "current": "michaelpo",
    "aliases": ["michaelpo", "foya_co01", "pomichael"]
  },
  "wsl": {
    "available": true,
    "distros": ["Ubuntu-22.04", "Debian"]
  }
}
```

注意：`aliases` 是否輸出可討論。若擔心 alias 敏感，提供 `--redact` 模式隱藏 alias。

## 5. 選項設計

建議支援：

```bash
cx doctor [--json] [--redact] [--skip-app-server] [--target TARGET]
```

### 5.1 `--json`

輸出 JSON，不輸出人類格式。

### 5.2 `--redact`

脫敏輸出。建議規則：

- Email 類資訊若未來要輸出，預設或 redact 模式都不要輸出完整 email。
- Alias 可顯示為 `alias#1`、`alias#2`，或只顯示帳號數量。
- 路徑可保留，但避免顯示 token。
- `auth.json` 僅輸出 exists / missing / permissions，不輸出內容。

第一階段可讓 `--redact` 隱藏 aliases，只顯示 count。

### 5.3 `--skip-app-server`

跳過 `codex app-server` 健康檢查。適合只想快速看路徑與環境，不想啟動 Codex app-server。

### 5.4 `--target TARGET`

預留選項，未必第一階段完成。未來可支援：

```bash
cx doctor --target windows
cx doctor --target wsl
cx doctor --target "WSL: Ubuntu-22.04"
```

第一階段可以不實作 `--target`，但 parser 可先保留或延後。

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

可用：

- `os.name`
- `sys.platform`
- `platform.platform()`
- `platform.python_version()`
- `sys.executable`
- `Path(__file__).resolve()`
- 既有 `is_wsl()` 函式

### 6.2 cx data dir

檢查：

- `DATA_DIR`
- `ACCOUNTS_DIR`
- `CURRENT_FILE`
- `LOCK_FILE`
- `TEMP_DIR`
- 目錄是否存在
- accounts 數量
- current alias

不要輸出帳號 auth 檔內容。

### 6.3 CODEX_HOME 與 auth.json

檢查：

- `CODEX_HOME`
- `CODEX_AUTH_FILE`
- `auth.json` exists / missing
- 檔案大小是否大於 0
- 權限是否明顯過寬（Linux/macOS 可檢查 mode；Windows 可先不嚴格）

不要讀出 token。若需要確認 JSON 格式，可只嘗試 parse 並回報 parse ok / parse failed，不輸出內容。

### 6.4 Codex executable

使用現有邏輯：

- `find_codex_executable()`
- `codex_executable()`
- `CX_CODEX_BIN`
- Windows extra path candidates

檢查：

- 是否找得到 codex。
- 實際找到的 executable path。
- 若找不到，列出建議：
  - 安裝 Codex CLI。
  - 確認 PATH。
  - Windows 可設定 `CX_CODEX_BIN`。

### 6.5 Codex version

嘗試執行：

```bash
codex --version
```

或若版本指令不支援，記錄 failure，但不視為阻斷性錯誤。

執行需有 timeout，例如 5 秒。

### 6.6 app-server 健康檢查

此項可能較慢，建議 timeout 10–15 秒。

第一階段可選擇簡化：

- 若目前 `CODEX_AUTH_FILE` 存在，呼叫既有 `request_app_server(CODEX_AUTH_FILE)`。
- 成功則 app-server ok。
- 失敗則記錄 error。

注意：

- 不應改變目前帳號。
- 既有 `request_app_server()` 使用 temp `CODEX_HOME`，原則上適合 doctor 使用。
- 若使用者指定 `--skip-app-server`，跳過此檢查。

### 6.7 WSL 檢查

在 Windows Native 環境下：

- 檢查 `wsl.exe` 是否存在。
- 執行 `wsl.exe -l -q` 或等價命令取得 distro 清單。
- 解析可用 distro。

在 WSL 內：

- 標示目前在 WSL。
- 嘗試輸出 distro name，可讀 `/etc/os-release` 或 `WSL_DISTRO_NAME`。

若 WSL 不存在，不一定是 error；若使用者只用 Windows Native，這只是 info 或 warning。

## 7. 結果分級

每個檢查項目應產生 status：

- `ok`
- `warning`
- `error`
- `skipped`

建議定義：

### 7.1 Error

會阻止主要功能使用的問題：

- 找不到 `codex`。
- `CODEX_HOME/auth.json` 不存在，且使用者正在查目前帳號。
- `DATA_DIR` 無法建立或不可寫。
- app-server 無法啟動且 status / best 需要它。

### 7.2 Warning

不一定阻止使用，但可能造成困擾：

- `cx` 沒有任何 saved accounts。
- current alias 指向不存在帳號。
- `auth.json` 權限過寬。
- `codex --version` 查不到。
- WSL 不存在但目前不是 WSL 使用者。
- 找到多個可能的 codex executable。

### 7.3 OK

正常。

## 8. 實作建議

主要修改：

```text
src/cx.py
```

可視情況新增：

```text
src/cx_doctor.py
```

建議不要讓 `src/cx.py` 再變更肥大。若程式碼超過簡單 helper，建議新增 `src/cx_doctor.py`，包含：

```python
@dataclass
class DoctorCheck:
    name: str
    status: str
    message: str
    details: dict[str, Any]

@dataclass
class DoctorReport:
    ok: bool
    warnings: list[str]
    errors: list[str]
    sections: dict[str, Any]
```

但第一階段也可用 dict 實作，避免過度設計。

### 8.1 Parser

在 `build_parser()` 新增：

```python
p_doctor = sub.add_parser("doctor", help="diagnose cx, Codex CLI, and environment setup")
p_doctor.add_argument("--json", action="store_true")
p_doctor.add_argument("--redact", action="store_true")
p_doctor.add_argument("--skip-app-server", action="store_true")
p_doctor.set_defaults(func=cmd_doctor)
```

### 8.2 Manual

更新 `MANUAL_COMMANDS`：

```python
("doctor", "cx doctor [--json] [--redact] [--skip-app-server]")
```

更新 `cx manual --lang zh-TW` 與 `--lang en` 內容，說明 doctor 用途。

### 8.3 JSON helper

沿用現有 `print_json()`。

### 8.4 Timeout

外部命令需 timeout，避免 doctor 卡住：

- `codex --version`: 5 秒
- `wsl.exe -l -q`: 5 秒
- app-server check: 10–15 秒

## 9. 脫敏要求

禁止輸出：

- access token
- refresh token
- session token
- cookie
- raw `auth.json`
- authorization header
- 完整 JSON auth payload

允許輸出：

- 檔案是否存在。
- 檔案大小。
- 檔案權限。
- 路徑。
- codex executable path。
- accounts count。
- current alias（若未使用 `--redact`）。

`--redact` 時建議：

- 不輸出 alias list。
- current alias 改成 `set` / `not set`。
- email 若未來加入，一律遮蔽成 `m***@domain` 或不顯示。

## 10. 測試需求

新增測試檔：

```text
tests/test_doctor.py
```

測試建議：

1. `cmd_doctor --json` 輸出合法 JSON。
2. JSON 包含 `system`、`paths`、`codex`、`accounts` 等 key。
3. 找不到 codex 時，不 crash，回傳 warning/error。
4. `--redact` 不輸出 alias list。
5. `--skip-app-server` 不呼叫 app-server。
6. `cx manual` 包含 doctor 指令。
7. 外部命令 timeout 時有合理錯誤訊息。

測試中應 mock：

- `find_codex_executable()`
- `subprocess.run()`
- `request_app_server()`
- filesystem paths

避免測試依賴真實 Codex CLI 或真實 WSL。

## 11. 驗收標準

### 11.1 CLI 驗收

以下指令可執行：

```bash
cx doctor
cx doctor --json
cx doctor --redact
cx doctor --skip-app-server
cx manual --lang zh-TW
cx manual --lang en
```

### 11.2 行為驗收

1. 沒有 Codex CLI 時，doctor 能輸出明確 error，不產生 traceback。
2. 沒有 saved accounts 時，doctor 能輸出 warning，不視為 fatal。
3. 沒有 `auth.json` 時，doctor 能輸出 warning 或 error，但不 crash。
4. 有 `auth.json` 且 app-server 正常時，doctor 顯示 app-server ok。
5. app-server timeout 時，doctor 顯示 app-server error，並結束。
6. `--json` 輸出可被 `json.loads()` 解析。
7. `--redact` 不輸出 alias list 或敏感內容。
8. 執行 doctor 不改變目前 `CODEX_HOME/auth.json`。
9. 執行 doctor 不切換 current alias。
10. 執行 doctor 不新增、不刪除、不覆蓋帳號資料。

### 11.3 回歸驗收

以下既有指令行為不得受影響：

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

## 12. README 更新需求

新增一節：

```markdown
## 環境診斷：cx doctor
```

內容說明：

- `cx doctor` 用於產生標準化環境快照。
- 它不會輸出 token 或 `auth.json` 原文。
- 發生問題時，可把 `cx doctor --redact` 結果貼給 AI agent 或維護者。
- 若不想啟動 app-server，可用 `cx doctor --skip-app-server`。

範例：

```bash
cx doctor --redact
```

## 13. GUI 連動建議

第一階段 GUI 不一定要接入 doctor。

第二階段可在 GUI `More` 選單加入：

```text
Run Doctor
Copy Doctor Report
```

其中：

- `Run Doctor` 顯示 doctor 結果在 Activity / Log。
- `Copy Doctor Report` 執行 `cx doctor --redact` 並複製到剪貼簿。

## 14. 建議分階段

### Phase 1：CLI doctor

- 新增 `cx doctor`
- 支援人類格式與 `--json`
- 基本檢查 system / paths / codex / accounts
- 支援 `--skip-app-server`
- 加 tests

### Phase 2：安全與脫敏

- 補強 `--redact`
- 檢查 auth.json 權限
- 改善 app-server 錯誤分類
- README 補完整用法

### Phase 3：GUI 整合

- GUI More 選單加入 Run Doctor
- 可複製 doctor report
- 錯誤時提示使用者附上 doctor report

## 15. 完成定義

本 CR 完成時，使用者遇到環境問題，可以執行：

```bash
cx doctor --redact
```

並將輸出貼給 AI agent 或維護者。報告應足以判斷常見問題：

- Codex CLI 是否找得到。
- Python / cx 執行位置。
- Windows Native 或 WSL 環境。
- CODEX_HOME 與 auth.json 狀態。
- cx data dir 與 saved accounts 狀態。
- app-server 是否可用。

整個過程不得暴露登入憑證或 token。
