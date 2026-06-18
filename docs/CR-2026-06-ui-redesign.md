# CR-2026-06：cx-gui UI 改版

## 1. 背景

目前 `cx-gui` 已能完成帳號管理、狀態查詢、切換、scope 標記、備份匯入匯出等主要功能，但畫面仍偏向工程原型：上方 ribbon toolbar 過長、按鈕一次攤開、視窗寬度不易縮小，下方 log 區域預設佔用大量空間但平常沒有資訊。

本 CR 目標是調整 GUI 資訊架構與版面，不新增核心功能，不改 CLI 行為。改版後應讓「帳號清單與額度狀態」成為畫面主體，常用操作保留在第一層，低頻功能收進選單或 context action，log/activity 預設收合。

## 2. 目標

1. 移除或弱化目前過長的 ribbon toolbar。
2. 讓主表格佔據主要可視空間。
3. 讓視窗寬度可以縮小，top toolbar 不應依賴水平捲動。
4. 將常用功能與低頻功能分層。
5. 選取帳號後才啟用與該帳號相關的操作。
6. Log / Activity 預設收合，不再固定佔用下半部空間。
7. 保留 Windows Native / WSL / WSL distro target 選擇能力。
8. 不改變現有 CLI 指令、資料格式與備份格式。

## 3. 非目標

本次 CR 不處理以下事項：

1. 不重寫成其他 GUI framework。
2. 不改 `src/cx.py` 的核心帳號管理邏輯。
3. 不改 `cx status`、`cx best`、`cx export`、`cx import` 等 CLI 行為。
4. 不新增 Web UI。
5. 不新增資料庫。
6. 不要求深色模式。
7. 不要求一次完成完整產品視覺設計，第一階段以可用且清楚為主。

## 4. 現況問題

### 4.1 Ribbon 過長

目前 GUI 把 Account、Selection、Scope、Backup 等操作全部放在同一條 ribbon 裡，包含：

- Refresh
- Status
- Add Account
- Save Current
- Use Selected
- Best
- Status Selected
- Remove
- Work
- Personal
- Export All
- Export Selected
- Export Filtered
- Import
- Inspect

結果是 top area 太寬、需要水平捲動，且所有功能看起來同等重要。

### 4.2 Log 區域預設佔位過大

目前下方 `ScrolledText` log 區固定存在，透過 vertical `PanedWindow` 分割畫面。日常使用時 log 多半是空的，卻壓縮主表格高度。

### 4.3 主流程不夠集中

此工具最常見流程是：

1. 查看帳號與狀態。
2. 判斷哪個帳號適合使用。
3. 切換帳號。

目前這三件事被大量低頻功能包圍，使用者需要先理解整排按鈕。

## 5. 新版版面要求

建議新版版面如下：

```text
+-------------------------------------------------------------+
| cx Account Manager                                          |
+-------------------------------------------------------------+
| Environment [ Windows Native v ]       Refresh Status Best  |
|                                      Add  More v            |
+-------------------------------------------------------------+
| 選取 1 個帳號（Rank 1 · michaelpo）     Use Remove Work ... |
+-------------------------------------------------------------+
| Account Table                                                |
|                                                             |
| * | Rank | Alias | Scope | Email | Plan | 5h | 7d | Error   |
|                                                             |
+-------------------------------------------------------------+
| Activity / Log (optional)                         Show details |
+-------------------------------------------------------------+
```

### 5.1 Top toolbar

第一層只保留高頻功能：

- Environment dropdown
- Refresh
- Status
- Best
- Add
- More

`Environment` 左側顯示，支援現有 target：

- `Windows Native`
- `WSL`
- `WSL: <distro>`

不要再使用紅色粗體 `TARGET` 或 `ENVIRONMENT` 作為主視覺焦點。可用一般 label：

```text
Environment  [ Windows Native v ]
```

右側常用操作：

```text
Refresh | Status | Best | Add | More v
```

按鈕應使用單行文字，避免兩行文字與大型 icon 造成寬度膨脹。

### 5.2 More 選單

低頻功能收進 `More`：

```text
Save Current
Status Selected
---
Export All
Export Filtered
Import
Inspect Backup
---
Show Activity / Log
---
Help / Manual
```

若 `Help / Manual` 尚未實作，可以先不顯示或 disabled。

### 5.3 Contextual action bar

Top toolbar 下方新增 context action bar。

未選取帳號時：

```text
尚未選取帳號
```

帳號相關操作 disabled。

選取一個帳號時：

```text
選取 1 個帳號（Rank 1 · michaelpo）    Use Remove Work Personal Export
```

選取多個帳號時：

```text
選取 N 個帳號    Export Remove
```

多選時，若某操作只支援單一帳號，例如 `Use`、`Work`、`Personal`，應 hidden 或 disabled。

### 5.4 Account table

主表格應佔據主要空間。欄位保留：

- current marker
- Rank
- Alias
- Scope
- Email
- Plan
- 5h
- 7d
- Error

`5h` / `7d` 建議兩行顯示：

```text
3% used
06-18 23:58
```

目前帳號應比單一 `*` 更明顯，可使用：

- `Current` badge
- 淡色 row 標記
- 粗體 alias
- current column 圖示

第一階段可保留 `*`，但建議至少加 row tag 或 tooltip。

### 5.5 Log / Activity

Log 預設收合，底部只保留細條：

```text
Activity / Log (optional)                      Show details
平常可不顯示；僅在執行操作或發生錯誤時展開
```

需要 Log 的情境：

1. `Add Account` device auth 登入流程。
2. 匯入 / 匯出。
3. Inspect Backup / Backup List。
4. Codex 找不到、app-server timeout、token revoked、WSL path 等錯誤診斷。
5. 使用者手動展開查看最近操作。

自動展開規則：

- 發生錯誤時自動展開。
- Add Account 登入流程可使用獨立 LoginDialog 或自動展開 log。
- Refresh 成功不展開。
- Status 成功不展開，只更新表格。
- Best 成功不展開，只刷新表格並顯示 status message。
- Import / Export 成功可以只顯示 status message；失敗時展開。

展開後高度建議 160–220 px，並提供收合按鈕。

## 6. 實作建議

主要修改檔案：

```text
gui/cx_gui.py
```

建議將 `_build_ui()` 拆成小函式：

```python
def build_top_toolbar(self) -> None: ...
def build_context_action_bar(self) -> None: ...
def build_account_table(self) -> None: ...
def build_activity_panel(self) -> None: ...
def build_more_menu(self) -> None: ...
```

第一階段不要求移除所有舊 helper，但新版 top toolbar 不應依賴：

- `ribbon_canvas`
- ribbon horizontal scrollbar
- mousewheel horizontal scrolling
- 大量 `create_ribbon_group()` 分組

### 6.1 Selection state

新增 selection change handler：

```python
self.tree.bind("<<TreeviewSelect>>", self.on_selection_changed)
```

`on_selection_changed()` 應更新：

- selected count label
- selected alias / rank display
- Use button state
- Work / Personal button state
- Export button state
- Remove button state

### 6.2 More menu

可用 `tk.Menu` 或 `ttk.Menubutton` 實作。第一階段以穩定為主，不要求複雜樣式。

### 6.3 Log state

新增狀態：

```python
self.log_expanded = BooleanVar(value=False)
```

新增方法：

```python
def show_log_panel(self) -> None: ...
def hide_log_panel(self) -> None: ...
def toggle_log_panel(self) -> None: ...
def log_command_result(self, result: CommandResult, *, expand_on_error: bool = True) -> None: ...
```

## 7. 測試建議

若 GUI 測試不方便開視窗，可優先測純邏輯：

1. `CxRunner` target path 與 WSL command 既有測試應保留。
2. 新增 context action state 的單元測試，或將 state 判斷抽成純函式測試。
3. 新增 log expand policy 的純函式測試，例如：
   - returncode 0 不自動展開。
   - returncode != 0 自動展開。
   - Add login operation always expands 或使用 dialog。

不要求在 CI 真的啟動完整 Tk 視窗。

## 8. 驗收標準

### 8.1 畫面驗收

1. 啟動 `cx-gui` 後，不再看到長 ribbon toolbar。
2. Top toolbar 不再需要水平捲動。
3. 視窗縮到約 900px 寬時，常用操作仍可見。
4. 帳號表格佔據主要高度。
5. Log 預設收合。
6. 選取帳號後，context action bar 顯示帳號資訊與可用操作。
7. 未選取帳號時，Use / Remove / Work / Personal 不可執行。
8. More 選單可找到低頻功能。

### 8.2 功能驗收

1. Refresh 正常更新帳號清單。
2. Status 正常查詢並更新表格。
3. Best 正常切換最佳帳號並刷新表格。
4. Add Account 正常啟動登入流程。
5. Use 正常切換選取帳號。
6. Work / Personal 正常更新 scope。
7. Export Selected / Export All / Export Filtered 正常。
8. Import / Inspect Backup 正常。
9. 發生錯誤時 Log / Activity 可展開並看到錯誤。
10. 成功的日常操作不強制展開 Log。

### 8.3 回歸驗收

以下 CLI 行為不得受影響：

```bash
cx list
cx status
cx best
cx best --allow-blocked
cx use <alias>
cx add <alias>
cx save <alias>
cx scope <alias> work
cx scope <alias> personal
cx export
cx import
cx backup-list
cx remove <alias>
```

既有 tests 應全部通過。

## 9. 建議分階段

### Phase 1：版面重排

- Compact top toolbar
- Contextual action bar
- Account table 擴大
- Log 預設收合
- More menu 初版

### Phase 2：互動補強

- 多選狀態處理
- More / Export 下拉細化
- Error 時自動展開 Log
- Status message 整理

### Phase 3：細節優化

- 右鍵選單
- 快捷鍵
- Current account 顯示優化
- 表格欄寬與 row style 微調
- README GUI 截圖與說明更新

## 10. 完成後文件更新

完成後需更新：

- `README.md` 的 Windows GUI 章節。
- 若新增快捷鍵或右鍵選單，也需補到 README。
- 若 UI 截圖已存在，需替換為新版。
