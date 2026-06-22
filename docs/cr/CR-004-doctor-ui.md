# CR-004: cx doctor GUI 整合

Status: Completed

Recommended release version after implementation: 3.1.0

## 1. 背景

`cx doctor` 已提供 CLI 環境診斷能力，可輸出目前環境的 system、paths、accounts、codex、wsl 等資訊，並支援 `--json` 與 `--skip-app-server`。

目前這個能力主要服務 PowerShell / shell 使用者。對 `cx-gui` 使用者來說，遇到 Windows Native / WSL / `CODEX_HOME` / Codex CLI / app-server 問題時，仍需要離開 GUI 手動執行 `cx doctor`，這和 GUI 的定位不一致。

本 CR 目標是把 `cx doctor` 整合進 GUI，讓使用者可以在 `More` 選單中執行診斷、查看結果，並複製一份安全報告給 AI agent 或維護者。

## 2. 目標

1. 在 `cx-gui` 的 `More` 選單加入 doctor 相關操作。
2. 針對目前選取的 `Auth Environment` 執行 doctor。
3. 顯示簡單 Doctor dialog，讓使用者不用讀 raw JSON。
4. 提供 `Copy Report`，方便貼給 AI agent 或維護者。
5. 預設不輸出 token、raw `auth.json`、email、完整 auth payload。
6. 不在 GUI 啟動時自動跑 doctor，避免啟動變慢。
7. 不改變既有 `cx doctor` CLI 基本行為。

## 3. 非目標

本次 CR 不做以下事項：

1. 不自動修復環境。
2. 不自動安裝 Codex CLI。
3. 不自動登入 Codex。
4. 不自動修改 PATH。
5. 不在 GUI 啟動時自動執行 full doctor。
6. 不新增遠端 doctor 或跨機器診斷。
7. 不在 Phase 1 新增 `cx doctor --json` 的 `checks[]` 結構。
8. 不要求第一版做複雜圖表或額外視覺設計。

## 4. 使用者流程

### 4.1 一般診斷

1. 使用者開啟 `cx-gui`。
2. 在上方 `Auth Environment` 選擇 `Windows Native` 或 `WSL: <distro>`。
3. 開啟 `More` 選單。
4. 點選 `Run Doctor`。
5. GUI 背景執行：

```bash
cx doctor --json
```

6. 顯示 Doctor dialog。
7. 使用者可按 `Copy Report` 複製人類可讀的脫敏報告。

### 4.2 快速診斷

當使用者只想快速檢查路徑與環境，不想等待 app-server：

1. 開啟 `More`。
2. 點選 `Run Quick Doctor`。
3. GUI 背景執行：

```bash
cx doctor --json --skip-app-server
```

4. 顯示 Doctor dialog。

### 4.3 複製報告

`Copy Report` 行為需明確：

1. 若已有最近一次 doctor 結果，直接複製該結果的文字報告。
2. 若尚未有 doctor 結果，自動執行 quick doctor，成功後複製報告。
3. 複製完成後，狀態列顯示：

```text
Doctor report copied to clipboard
```

## 5. More 選單需求

在現有 `More` 選單加入 doctor 相關項目。

Phase 1 建議結構：

```text
Save Current
Details Selected
---
Export All
Export Filtered
Import
Inspect Backup
---
Run Doctor
Run Quick Doctor
Copy Doctor Report
---
Show Activity / Log
Open Data Folder
---
Help / Manual
```

說明：

- `Run Doctor`：執行 `cx doctor --json`。
- `Run Quick Doctor`：執行 `cx doctor --json --skip-app-server`。
- `Copy Doctor Report`：複製最近一次 doctor 結果；若沒有結果，先跑 quick doctor。

若選單太長，可以將 `Copy Doctor Report` 放進 Doctor dialog；但 Phase 1 至少需要 `Run Doctor` 與 `Run Quick Doctor`。

## 6. Doctor Dialog

### 6.1 Dialog 內容

Doctor dialog 應包含：

- Target / Auth Environment。
- Result summary：`OK` / `Warning` / `Error`。
- System section。
- Paths section。
- Codex section。
- Accounts section。
- WSL section。
- Warnings / Errors list。

建議版面：

```text
CX Doctor

Target: Windows Native
Result: OK / Warning / Error

[System] OK
  OS: Windows
  Python: 3.12.x
  cx script: ...

[Paths] OK / Warning
  data dir: exists
  accounts dir: exists
  CODEX_HOME: ...
  auth.json: exists, parse ok

[Codex] OK / Warning / Error
  executable: ...
  version: ...
  app-server: ok / error / skipped

[Accounts] OK / Warning
  saved accounts: 4
  current alias: set

[WSL] OK / Skipped / Warning
  available: yes/no
  distro count: 2

Warnings / Errors
  - ...

[Copy Report] [Close]
```

Phase 1 不需要 `Copy JSON` 或 `Show Raw Output` 按鈕。

### 6.2 狀態顯示

狀態應使用文字標籤，不只依賴顏色：

```text
OK
Warning
Error
Skipped
```

顏色可以輔助：

- OK：綠色或一般文字。
- Warning：橘色或黃色。
- Error：紅色。
- Skipped：灰色。

### 6.3 Severity 推導

目前 CLI `ok` 定義為 `not errors`，所以有 warnings 時仍可能 `ok=true`。GUI 顯示應自行推導：

- 有 `errors`：`Error`
- 沒有 `errors` 但有 `warnings`：`Warning`
- 沒有 `errors` 也沒有 `warnings`：`OK`

## 7. Copy Report

### 7.1 目的

`Copy Report` 產生一份可以直接貼給 AI agent 或維護者的文字報告。

它應比 raw JSON 易讀，也比 Activity / Log 更乾淨。

### 7.2 建議格式

```text
cx doctor report
Target: Windows Native
Result: OK

[System]
OS: Windows
Python: 3.12.x
cx script: %LOCALAPPDATA%\cx\app\cx.py
WSL: no

[Paths]
data dir: %LOCALAPPDATA%\cx
accounts dir: exists
CODEX_HOME: %USERPROFILE%\.codex
auth.json: exists, parse ok

[Codex]
CX_CODEX_BIN: not set
executable: %APPDATA%\npm\codex.cmd
version: codex 0.x.x
app-server: ok

[Accounts]
saved accounts: 4
current alias: set

[WSL]
checked: yes
available: yes
distro count: 2

Warnings:
- none

Errors:
- none
```

### 7.3 基本脫敏

Phase 1 只做基本路徑脫敏，不做複雜安全掃描。

建議規則：

- Windows:
  - `C:\Users\<user>` 改為 `%USERPROFILE%`
  - `%LOCALAPPDATA%` 下路徑顯示成 `%LOCALAPPDATA%\...`
  - `%APPDATA%` 下路徑顯示成 `%APPDATA%\...`
- Linux / WSL:
  - `/home/<user>` 改成 `~`

禁止輸出：

- token
- raw `auth.json`
- email
- cookie
- authorization header
- access token
- refresh token

目前 CLI doctor 已避免輸出 token 與 email。GUI copy report 仍應在格式化後做基本字串脫敏，避免未來 doctor 新增欄位時不小心外洩。

## 8. Activity / Log 整合

Phase 1 行為：

- `Run Doctor` 進行中，status bar 顯示 `Running doctor...`。
- doctor 成功時，顯示 dialog，不強制展開 Activity。
- doctor warning / error 時，仍顯示 dialog，可選擇展開 Activity。
- JSON parse 失敗時，將 stdout / stderr 寫入 Activity，展開 Activity，並顯示 messagebox：

```text
Doctor output was not valid JSON. See Activity for details.
```

Phase 1 不需要 `Show Raw Output` 按鈕。

## 9. 延後項目

以下項目延後到 Phase 2 或 Phase 3：

- `Copy JSON`
- `Show Raw Output`
- 敏感字串安全掃描
- `cx doctor --json` 新增 optional `checks[]`
- GUI 改用 `checks[]` 畫狀態表
- 更完整的 doctor result 視覺設計

## 10. 實作建議

主要檔案：

```text
src/cx_account_manager/gui_app.py
```

可能新增測試：

```text
tests/test_gui_doctor.py
```

### 10.1 建議新增 GUI 方法

```python
def run_doctor(self, *, skip_app_server: bool = False) -> None: ...
def on_doctor_loaded(self, result: CommandResult) -> None: ...
def show_doctor_dialog(self, report: dict[str, object], raw_output: str, raw_error: str) -> None: ...
def format_doctor_report_for_clipboard(self, report: dict[str, object]) -> str: ...
def redact_doctor_report_text(self, text: str) -> str: ...
def copy_doctor_report(self) -> None: ...
def doctor_severity(self, report: dict[str, object]) -> str: ...
```

### 10.2 執行命令

針對目前 target 執行：

```python
self.run_background("Running doctor", ["doctor", "--json"], self.on_doctor_loaded, timeout=30)
```

Quick doctor：

```python
self.run_background("Running quick doctor", ["doctor", "--json", "--skip-app-server"], self.on_doctor_loaded, timeout=15)
```

## 11. 測試建議

### 11.1 純函式測試

優先測不需要開 Tk 視窗的函式：

1. `format_doctor_report_for_clipboard()`。
2. `redact_doctor_report_text()`。
3. `doctor_severity()`。

### 11.2 Mock GUI command result

可建立 fake `CommandResult`：

- returncode 0 + valid JSON。
- returncode 1 + valid JSON with errors。
- returncode 0 + invalid JSON。
- returncode 124 + timeout stderr。

### 11.3 驗收手測

```powershell
cx-gui
```

手動驗證：

1. More > Run Quick Doctor。
2. More > Run Doctor。
3. Copy Report。
4. JSON parse 失敗時，不 crash 且 Activity 顯示 raw output。
5. Windows Native / WSL: distro 都能執行對應環境的 doctor。

## 12. README 更新需求

完成後更新 `README.md` 的 Windows GUI 章節，補充：

- `More > Run Doctor`：執行目前 Auth Environment 的診斷。
- `More > Run Quick Doctor`：跳過 app-server，較快。
- `Copy Doctor Report`：產生可貼給 AI agent / 維護者的脫敏報告。

並在 `GUI 目前覆蓋` 清單中加入：

```text
- 可從 More 執行 cx doctor，並複製環境診斷報告
```

## 13. 驗收標準

### 13.1 功能驗收

1. `More` 選單可看到 `Run Doctor`。
2. `Run Doctor` 執行目前 Auth Environment 的 `cx doctor --json`。
3. `Run Quick Doctor` 執行 `cx doctor --json --skip-app-server`。
4. Doctor dialog 可顯示 OK / Warning / Error。
5. Doctor dialog 可顯示 system / paths / accounts / codex / wsl sections。
6. `Copy Report` 可複製人類可讀報告。
7. JSON parse 失敗時，不 crash，Activity 顯示 raw output。
8. doctor timeout 時，不 crash，Activity 或 dialog 顯示 timeout。
9. 執行 doctor 不改變 current alias 或 `auth.json`。

### 13.2 安全驗收

1. Copy Report 不包含 token。
2. Copy Report 不包含 raw `auth.json`。
3. Copy Report 不包含 email。
4. Copy Report 不包含 access token / refresh token。
5. Copy Report 對使用者 home path 做基本脫敏。

### 13.3 回歸驗收

1. Refresh / Details / Best / Add / Use / Export / Import 功能不受影響。
2. Activity / Log 展開收合仍正常。
3. Context action bar 仍根據 selection 正確啟用 / 停用。
4. CLI `cx doctor` 行為不受 GUI 改動影響。
5. 既有 tests 通過。

## 14. 分階段

### Phase 1: 最小可用 Doctor UI

- More 加 `Run Doctor`、`Run Quick Doctor`。
- 執行 doctor 後顯示 dialog。
- Dialog 顯示 sections 與 warnings / errors。
- 支援 Copy Report。
- README 補 GUI doctor 說明。
- 建議 release version: `3.1.0`。

### Phase 2: 複製與安全性補強

- Copy JSON。
- 敏感字串檢查。
- Raw Output / Activity 整合。

### Phase 3: CLI JSON 補強

- `cx doctor --json` 新增 optional `checks[]`。
- GUI 改用 `checks[]` 畫狀態表。
- 補 tests。

## 15. 完成定義

完成後，GUI 使用者遇到環境問題時，不需要離開 GUI。可以直接：

```text
More > Run Doctor > Copy Report
```

然後把報告貼給 AI agent 或維護者。報告應足以判斷常見問題：

- Windows Native / WSL 目標是否正確。
- Python 與 cx 執行位置。
- Codex CLI 是否找得到。
- `CODEX_HOME` / `auth.json` 狀態。
- saved accounts 與 current alias 狀態。
- app-server 是否可用。

整個流程不得暴露登入憑證或 token。
