# CR-008: GUI renew 與主工具列調整

Status: Completed

## 1. 背景

CR-007 定義了 CLI `cx renew <alias>`，用來安全地重新登入既有 alias，並在覆寫前確認新舊 account identity 一致。

GUI 目前已有 Add、Save Current、Use、Remove、Work、Personal、Export、Import、Details 等操作。主畫面表格已顯示 alias、scope、email、plan、rank、5h / 7d 用量與錯誤狀態；因此 `Details` 作為主工具列按鈕的資訊價值下降。

另一方面，`Import` 是搬機、備份還原與初始化環境時常用的入口，目前放在 `More` 裡，對新使用者不夠明顯。本 CR 調整 GUI 操作配置，並新增單一 alias 的 Renew 操作。

## 2. 目標

1. GUI 新增 Renew 操作，呼叫 CLI：

```bash
cx renew <alias>
```

2. Renew 只支援單選，不支援多選。
3. Renew 必須放在右鍵選單。
4. Renew 可放在 selected account 的 contextual action bar，但不得放在支援多選的批次流程中。
5. 主工具列移除 `Details` 按鈕，改放進 `More`。
6. 主工具列新增 `Import` 按鈕，讓匯入備份更容易被找到。
7. `More` 裡仍保留 Details / Details Selected 入口。
8. GUI 不自行實作 account identity 比對；identity gate 由 CLI `cx renew` 負責。
9. Renew login dialog 應沿用 Add 的 device login output 顯示能力，包括 URL 與 device code 複製。
10. Renew 成功後刷新帳號列表。

## 3. 非目標

本 CR 不做以下事項：

1. 不修改 CR-007 的 CLI renew 語意。
2. 不讓 Renew 支援多選。
3. 不讓 GUI 直接解析或修改 `auth.json`。
4. 不新增批次 renew。
5. 不新增自動 renew。
6. 不改 ranking / best 邏輯。
7. 不改 backup archive 格式。
8. 不移除 `cx status` 或 Details 功能，只調整入口位置。
9. 不讓 GUI 在 renew 失敗後自動 fallback 成 `add --force`。

## 4. 操作配置

### 4.1 主工具列建議配置

目前主工具列建議調整為：

```text
Refresh | Best | Add | Import | More
```

調整理由：

1. `Refresh` 是資料重載入口，保留。
2. `Best` 是高頻決策入口，保留。
3. `Add` 是新增帳號入口，保留。
4. `Import` 是備份還原與搬機入口，應提升能見度。
5. `Details` 與主表格資訊重疊，移入 `More`。

### 4.2 More 選單建議配置

建議：

```text
Save Current
Details
Details Selected
---
Export All
Export Filtered
Inspect Backup
---
Run Doctor
Run Quick Doctor
Copy Doctor Report
---
Settings...
---
Show Activity / Log
Open Data Folder
---
Help / Manual
```

說明：

1. `Import` 從 `More` 移到主工具列。
2. `Details` 從主工具列移到 `More`。
3. `Details Selected` 保留在 `More`，方便需要原始 CLI output 時使用。
4. Backup 相關操作仍集中在 More，但 Import 因為常用與初始化價值較高，拉出來。

### 4.3 Selected account contextual action bar

目前 contextual action bar 建議調整為：

```text
Use | Renew | Remove | Work | Personal | Export
```

Renew 放在 `Use` 與 `Remove` 之間，理由：

1. Renew 是針對「已選帳號」的修復操作，與 Use / Remove 同層。
2. Renew 不適合藏在 More，因為 token revoked 時使用者會先看到該帳號錯誤狀態，接著需要直接修復。
3. Renew 不應放在主工具列，因為主工具列偏向全域操作，而 Renew 必須依賴單一選取 alias。
4. Renew 放在 Remove 旁邊是可接受的，但應避免誤按造成困惑；建議按鈕文字清楚標成 `Renew`，並在確認 dialog 中明確說明會重新登入該 alias。

若空間不足，替代方案是 contextual action bar 不放 Renew，只放右鍵選單。但第一版建議放 contextual action bar，因為它是修復 token 問題的主要入口。

### 4.4 右鍵選單

右鍵選單建議：

```text
Use
Renew
Details
Mark as Work
Mark as Personal
---
Export Selected
Remove
```

多選時：

1. `Renew` disabled，或不顯示。
2. `Use` disabled，或不顯示，因為 Use 也只適合單選。
3. `Export Selected` / `Remove` 可維持多選支援。
4. Work / Personal 可維持多選支援，若既有實作已支援。

建議採用 disabled 而非完全隱藏，讓使用者知道此功能存在但只支援單選。

## 5. Renew GUI 流程

### 5.1 單選檢查

使用者按 Renew 時：

```text
if selected_alias_count == 0:
    show info: Select one account first.
    return

if selected_alias_count > 1:
    show info: Renew supports one account at a time.
    return
```

### 5.2 確認 dialog

執行前必須確認：

```text
Renew `<alias>` in Auth Environment: <environment>?

This will open Codex device login and update the saved token only if the logged-in account matches the existing alias.

[Renew] [Cancel]
```

如果目前 selected row 有 email，可在 dialog 中顯示：

```text
Expected email: user@example.com
```

此 email 只作提示，不作 GUI 端比對依據。真正比對由 CLI 完成。

### 5.3 執行 CLI

Renew 執行：

```bash
cx renew <alias>
```

在 WSL target 時，沿用既有 `CxRunner` 的 target command 包裝。

在 Windows Native target 時，若需要 Codex executable，沿用 Add 的 `ensure_windows_codex_bin()` 檢查。

### 5.4 Login dialog

目前 `LoginDialog` 會組出 `cx add [--force] <alias>`，並顯示 device login output。Renew 應重用這個 dialog，但需要將 command mode 參數化。

建議修改方向：

```python
class LoginDialog:
    def __init__(..., command: str, alias: str, force: bool = False, ...):
        ...
```

Add 使用：

```python
LoginDialog(..., command="add", alias=alias, force=force, ...)
```

Renew 使用：

```python
LoginDialog(..., command="renew", alias=alias, force=False, ...)
```

`start()` 內組 command：

```python
args = [self.command]
if self.command == "add" and self.force:
    args.append("--force")
args.append(self.alias)
```

Renew 不應出現 force。

### 5.5 成功與失敗後處理

Renew exit code 為 0：

1. 關閉 busy 狀態。
2. 設定 post refresh status：

```text
Renewed <alias>
```

3. 執行 `refresh_accounts()`。

Renew exit code 非 0：

1. 不刷新或可刷新一次；建議不強制刷新，避免掩蓋 log 中錯誤。
2. Status 顯示：

```text
Renew failed
```

3. Activity / Log 中保留 CLI output。
4. 不提供自動 fallback 到 `add --force`。

## 6. 多選規則

Renew 不支援多選，原因：

1. 每個 alias 都需要一次獨立的互動式 device login。
2. 瀏覽器登入過程中，使用者需要確認正在登入哪個 account。
3. 多選 renew 容易造成「登入結果對應到哪個 alias」的混淆。
4. token 修復通常是針對單一 revoked alias，不是批次操作。

GUI 必須在以下地方落實：

1. contextual action bar：多選時 Renew disabled。
2. 右鍵選單：多選時 Renew disabled。
3. handler：即使 UI 狀態錯誤，也要在 function 內再次檢查 selected count。

## 7. UI 狀態與 tooltip

Renew 按鈕 tooltip 建議：

```text
Re-login and update the selected alias only if the account matches.
```

Import 按鈕 tooltip 建議：

```text
Import accounts from a cx backup archive.
```

Details 在 More 中 tooltip 可省略；若保留，建議：

```text
Show raw CLI status details in Activity.
```

## 8. 錯誤呈現

Renew 失敗的主要錯誤來源應由 CLI 輸出，例如：

1. alias 不存在。
2. 新舊 email 不一致。
3. 新登入結果無法解析 email。
4. `codex login --device-auth` 失敗。

GUI 不應把這些錯誤轉成過度簡化的 generic messagebox。建議：

1. LoginDialog output 保留完整 CLI stdout/stderr。
2. 主畫面 status 只顯示 `Renew failed`。
3. 若 login dialog 已關閉，Activity / Log 也應保留指令結果。

## 9. 實作建議

### 9.1 新增 handler

建議新增：

```python
def renew_selected(self) -> None:
    aliases = self.selected_aliases()
    if not aliases:
        messagebox.showinfo(APP_TITLE, "Select one account first.", parent=self.root)
        return
    if len(aliases) != 1:
        messagebox.showinfo(APP_TITLE, "Renew supports one account at a time.", parent=self.root)
        return
    alias = aliases[0]
    ...
```

### 9.2 LoginDialog callback

可新增：

```python
def on_renew_done(self, exit_code: int) -> None:
    try:
        self.login_dialog_active = False
        if exit_code == 0:
            self.post_refresh_status = f"Renewed {alias}"
            self.refresh_accounts()
        else:
            self.set_busy("Renew failed")
    finally:
        self.end_busy()
```

實作時注意 callback 需要知道 alias，可用 closure 或將 alias 存在 instance field。

### 9.3 busy / auto refresh

Renew 期間必須：

1. 設定 busy。
2. 停止或 skip auto refresh。
3. 避免同時執行 Add / Use / Import / Export。
4. Renew dialog 未完成前，`login_dialog_active = True`。

這與 Add 現有流程一致。

### 9.4 Import 按鈕重用既有 handler

主工具列新增 Import 時，應直接呼叫既有：

```python
self.import_backup
```

不得複製一份新的 import 流程。

### 9.5 Details 移動

主工具列移除 Details button，但 `refresh_status_all` handler 保留，供 More 裡的 Details 呼叫。

## 10. 測試規格

至少新增或更新以下測試。若目前 GUI 測試不足，可先以可測函式與 preview mode 測試為主。

1. `LoginDialog` command mode 為 `add` 時，仍組出 `cx add [--force] <alias>`。
2. `LoginDialog` command mode 為 `renew` 時，組出 `cx renew <alias>`，且不帶 `--force`。
3. 未選帳號時按 Renew，顯示提示且不執行 CLI。
4. 多選帳號時按 Renew，顯示提示且不執行 CLI。
5. 單選帳號時按 Renew，確認後呼叫 `cx renew <alias>`。
6. Renew 成功後 refresh accounts。
7. Renew 失敗後顯示 `Renew failed`，不 fallback 到 `add --force`。
8. contextual action bar 多選時 Renew disabled。
9. 右鍵選單多選時 Renew disabled 或不顯示。
10. 主工具列包含 Import，不包含 Details。
11. More 選單包含 Details / Details Selected，不包含 Import。

## 11. 驗收條件

1. GUI 可針對單一 selected alias 執行 Renew。
2. Renew 執行的是 CLI `cx renew <alias>`。
3. Renew 不支援多選，且 UI 與 handler 都有防護。
4. Renew 可從右鍵選單使用。
5. Renew 可從 selected account contextual action bar 使用。
6. Details 從主工具列移到 More。
7. Import 從 More 移到主工具列。
8. Add / Save Current / Use / Remove / Scope / Export / Import 既有行為不變。
9. Renew 失敗時，CLI 錯誤訊息可在 login dialog 或 Activity / Log 中看到。
10. 測試通過：

```bash
python -m pytest
ruff check .
```

## 12. 風險與取捨

### 12.1 Renew 放在 Remove 旁邊的風險

Renew 和 Remove 都是 selected alias 的操作，但 Remove 是破壞性操作，Renew 是修復性操作。把 Renew 放在 Remove 旁邊可以提高可見度，但要避免誤解。建議排序為：

```text
Use | Renew | Remove
```

而不是：

```text
Use | Remove | Renew
```

這樣 Renew 更接近 Use，語意上是「讓這個帳號恢復可用」，Remove 則保留在較後方。

### 12.2 Details 移入 More 的取捨

主表格已顯示主要狀態，Details 對一般使用者較低頻。但 Details 對 debug 仍有價值，所以不移除，只移到 More。

### 12.3 Import 拉出主工具列的取捨

Import 不是每天都用，但它是新環境設定、搬機、還原時的關鍵入口。相較 Details，它更值得放在主工具列。

### 12.4 GUI 不做 identity gate

GUI 若自行解析 auth 或比對 email，會造成 CLI / GUI 邏輯分裂。第一版應讓 GUI 單純呼叫 `cx renew <alias>`，所有安全規則集中在 CLI。
