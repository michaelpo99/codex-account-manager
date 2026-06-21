# CR-006: GUI Auto Refresh 與 Settings 記憶

Status: Completed

## 1. 背景

`cx-gui` 目前可以手動按 `Refresh` 重新載入帳號清單與額度狀態。使用者希望新增定時 refresh 功能，讓帳號列表能自動更新，並且每次啟動 GUI 時記住上次設定。

目前 GUI 已有設定檔機制，會將 Auth Environment / target 存在 `gui-settings.json`。本 CR 目標是在不影響核心帳號管理功能的前提下，擴充 GUI settings，新增 Auto Refresh 設定與 Settings dialog。

## 2. 目標

1. 新增 GUI Auto Refresh 功能。
2. Auto Refresh 預設關閉。
3. 使用者可在 GUI 設定是否啟用 Auto Refresh。
4. 使用者可設定 refresh interval，但必須有合理下限，不能設定成毫秒級或過短秒數。
5. 每次啟動 GUI 時，還原上次 Auto Refresh 設定。
6. 儲存 target / Auth Environment 時，不得覆蓋其他 GUI settings。
7. Auto Refresh 執行時不得與其他背景操作重疊。
8. Auto Refresh 失敗時不得反覆彈出干擾性 messagebox。

## 3. 非目標

本 CR 不做以下事項：

1. 不改 `cx status` CLI 行為。
2. 不改 `cx best` / ranking 邏輯。
3. 不改帳號資料格式。
4. 不改 backup / import / export 格式。
5. 不新增遠端服務。
6. 不做毫秒級 refresh。
7. 不讓 Auto Refresh 成為預設開啟功能。
8. 不在第一版加入複雜排程，例如只在工作時間 refresh。

## 4. 副作用與限制

Auto Refresh 不是單純重畫畫面。GUI refresh 目前會執行：

```bash
cx status --json
```

而 `cx status` 會針對已保存帳號讀取狀態，並可能呼叫 Codex app-server。因此 interval 太短會造成以下副作用：

1. 頻繁啟動 Codex CLI / app-server。
2. 多帳號時增加 CPU 與 subprocess 成本。
3. 可能造成 refresh 重疊。
4. 忙碌狀態可能干擾使用者按 `Use`、`Add`、`Export` 等操作。
5. token revoked、app-server timeout 等錯誤可能被反覆觸發。
6. 5h / 7d 額度本身不需要秒級更新，過短 interval 沒有明顯資訊價值。

因此本功能必須保守設計。

## 5. Interval 規則

### 5.1 預設值

```text
Auto Refresh: off
Default interval when enabled: 300 seconds
```

### 5.2 合法範圍

```text
Minimum: 60 seconds
Maximum: 3600 seconds
Unit: seconds
Type: integer only
```

### 5.3 Presets

建議提供 presets：

```text
1 min
2 min
5 min
10 min
```

對應：

```text
60
120
300
600
```

### 5.4 非法輸入處理

1. 小於 60：clamp 成 60，並提示 `Minimum auto refresh interval is 60 seconds.`
2. 大於 3600：clamp 成 3600，並提示 `Maximum auto refresh interval is 3600 seconds.`
3. 小數：拒絕儲存，提示 `Interval must be a whole number of seconds.`
4. 非數字：拒絕儲存。
5. 空白：回到預設值 300。
6. `0`：視為停用 Auto Refresh，不代表 0 秒 refresh。

## 6. Settings 設計

### 6.1 Settings 入口

在 `More` 選單新增：

```text
Settings...
```

建議位置：

```text
Run Doctor
Run Quick Doctor
Copy Doctor Report
---
Settings...
Show Activity / Log
Open Data Folder
---
Help / Manual
```

### 6.2 第一版 Settings dialog

第一版 Settings dialog 只需要處理 Auto Refresh，不要把範圍擴張到 theme、doctor、activity 等進階設定。

建議畫面：

```text
Settings

Auto Refresh
[ ] Enable auto refresh

Interval
( ) 1 min
( ) 2 min
( ) 5 min
( ) 10 min
( ) Custom: [ 300 ] seconds

Minimum interval: 60 seconds.
Auto refresh is skipped while another operation is running.

[Save] [Cancel]
```

### 6.3 主畫面狀態顯示

主畫面不建議放完整設定 controls，以免 top bar 變擠。

建議在 status bar 或 Activity strip 顯示：

```text
Ready · Auto refresh off
Ready · Auto refresh every 5 min · next 14:38
Refreshing... · Auto refresh paused while busy
```

## 7. Settings JSON 格式

目前 GUI settings 檔已存在，應擴充而非另開新檔。

建議格式：

```json
{
  "target": "WSL: Ubuntu-22.04",
  "auto_refresh": {
    "enabled": false,
    "interval_seconds": 300
  }
}
```

未來可擴充：

```json
{
  "target": "WSL: Ubuntu-22.04",
  "auto_refresh": {
    "enabled": false,
    "interval_seconds": 300
  },
  "activity": {
    "expand_on_error": true
  },
  "theme": {
    "name": "enterprise-light",
    "show_missing_theme_hint": true
  }
}
```

但本 CR 第一版只要求 `target` 與 `auto_refresh`。

## 8. 相容性要求

舊設定檔可能只有：

```json
{
  "target": "WSL: Ubuntu-22.04"
}
```

讀取時必須相容：

```text
auto_refresh.enabled = false
auto_refresh.interval_seconds = 300
```

若設定檔 JSON 損毀，應回到預設值，不 crash。

## 9. 重要實作要求：不得覆蓋其他 settings

目前若儲存 target 時直接寫入：

```json
{"target": "..."}
```

未來會覆蓋 auto refresh 設定。

因此必須新增通用 settings 讀寫 helper：

```python
def load_gui_settings(self) -> dict[str, object]: ...
def save_gui_settings(self, settings: dict[str, object]) -> None: ...
def update_gui_setting(self, key: str, value: object) -> None: ...
```

`save_target_setting()` 應改成：

```python
settings = self.load_gui_settings()
settings["target"] = target
self.save_gui_settings(settings)
```

Auto Refresh 設定也應使用同一套 helper。

## 10. Auto Refresh 行為規格

### 10.1 啟動時

GUI 啟動時：

1. 讀取 `gui-settings.json`。
2. 還原 target。
3. 還原 auto refresh enabled / interval。
4. 若 enabled，排程下一次 refresh。
5. 不要在還原後立刻額外觸發第二次 refresh；GUI 原本啟動時的初次 refresh 已足夠。

### 10.2 防重疊

Auto Refresh tick 時：

```text
if auto refresh disabled: return
if GUI busy_count > 0: skip this tick
if Add Account login dialog is active: skip this tick
if another refresh is running: skip this tick
otherwise: refresh_accounts()
```

Auto Refresh 不應 queue 多個 refresh。

若 busy 中 skip，status 顯示：

```text
Auto refresh skipped while busy
```

不要彈 messagebox。

### 10.3 排程方式

建議「完成後再排下一次」，不要固定每 N 秒硬觸發。

建議邏輯：

```text
start refresh
finish refresh
schedule next refresh after interval_seconds
```

若使用 `root.after()`，需記錄 after id：

```python
self.auto_refresh_after_id: str | None = None
```

並提供：

```python
def schedule_auto_refresh(self) -> None: ...
def cancel_auto_refresh(self) -> None: ...
def reset_auto_refresh_timer(self) -> None: ...
def on_auto_refresh_tick(self) -> None: ...
```

### 10.4 手動 Refresh 與 Auto Refresh

使用者手動按 `Refresh`：

1. 立即 refresh。
2. 取消已排程的 auto refresh timer。
3. 手動 refresh 完成後，重新從 interval 開始計時。

避免手動 refresh 後馬上又被 auto refresh 觸發。

### 10.5 Target 切換

使用者切換 Auth Environment：

1. 儲存 target。
2. 立即 refresh 目前 target。
3. 重設 auto refresh timer。

### 10.6 Busy 操作

以下操作期間，Auto Refresh 應 skip：

- Add Account / LoginDialog active
- Use Selected
- Best
- Scope update
- Remove
- Export
- Import
- Inspect Backup
- Doctor
- Manual

原則：只要 `busy_count > 0`，Auto Refresh 不執行。

## 11. GUI 狀態與提示

### 11.1 狀態列

狀態列應能顯示：

```text
Auto refresh off
Auto refresh every 5 min
Next auto refresh 14:38
Auto refresh skipped while busy
Auto refresh failed
```

不要每次成功 auto refresh 都寫大量 Activity / Log。成功時更新 status 即可。

### 11.2 Activity / Log

Auto Refresh 成功：

- 不自動展開 Activity。
- 不必寫完整 log。

Auto Refresh 失敗：

- 可寫簡短錯誤到 Activity。
- 不要反覆 messagebox。
- 若連續失敗，可只更新最後一次錯誤時間。

## 12. 建議新增欄位與方法

### 12.1 CxGui 欄位

```python
self.auto_refresh_enabled = BooleanVar(value=False)
self.auto_refresh_interval_seconds = 300
self.auto_refresh_after_id: str | None = None
self.auto_refresh_in_progress = False
self.login_dialog_active = False
```

`auto_refresh_in_progress` 可以避免非 busy_count 場景下重疊。若 `busy_count` 已足夠，也可以不新增，但建議保留獨立旗標，讓邏輯清楚。

### 12.2 方法

```python
def load_gui_settings(self) -> dict[str, object]: ...
def save_gui_settings(self, settings: dict[str, object]) -> None: ...
def load_auto_refresh_settings(self) -> None: ...
def save_auto_refresh_settings(self) -> None: ...
def open_settings_dialog(self) -> None: ...
def apply_auto_refresh_settings(self, enabled: bool, interval_seconds: int) -> None: ...
def normalize_auto_refresh_interval(self, value: object) -> tuple[int, str | None]: ...
def schedule_auto_refresh(self) -> None: ...
def cancel_auto_refresh(self) -> None: ...
def reset_auto_refresh_timer(self) -> None: ...
def on_auto_refresh_tick(self) -> None: ...
def refresh_accounts(self, *, reason: str = "manual") -> None: ...
```

`refresh_accounts()` 可加 `reason`，例如：

```python
refresh_accounts(reason="manual")
refresh_accounts(reason="auto")
refresh_accounts(reason="target_changed")
```

這樣 callback 可決定 status message 與 log 行為。

## 13. SettingsDialog 建議

可新增：

```python
class SettingsDialog(simpledialog.Dialog): ...
```

輸入結果：

```python
@dataclass
class GuiSettingsResult:
    auto_refresh_enabled: bool
    auto_refresh_interval_seconds: int
```

或簡單使用 tuple：

```python
(bool, int)
```

但為了可讀性，建議 dataclass。

## 14. 測試需求

### 14.1 純函式測試

新增或修改：

```text
tests/test_gui_settings.py
```

測試：

1. 舊 settings 只有 target 時，auto refresh 回到預設值。
2. settings JSON 損毀時回到預設值。
3. interval 小於 60 時 normalize 成 60。
4. interval 大於 3600 時 normalize 成 3600。
5. interval 300 合法。
6. interval 0 代表 disabled。
7. 儲存 target 時不覆蓋 auto_refresh。
8. 儲存 auto_refresh 時不覆蓋 target。

### 14.2 GUI 邏輯測試

可 mock `root.after` 與 `refresh_accounts`：

1. Auto refresh disabled 時不 schedule。
2. Auto refresh enabled 時 schedule。
3. Busy 中 tick 會 skip。
4. Tick 不會 queue 多個 refresh。
5. 手動 refresh 會 reset timer。

### 14.3 手動驗收

1. 開啟 GUI。
2. More > Settings。
3. 啟用 Auto Refresh，設定 1 min。
4. 關閉 GUI，再開啟，確認設定保留。
5. 輸入 5 秒，確認被調整成 60 秒或拒絕。
6. 輸入 0，確認 Auto Refresh 關閉。
7. Auto Refresh 啟用時，等待觸發刷新。
8. 執行 Add / Use / Export 時，確認 Auto Refresh 不插入執行。
9. 切換 Auth Environment 後，確認 timer 重設。

## 15. README 更新需求

完成後更新 `README.md` 的 Windows GUI 章節：

1. 說明 `More > Settings...`。
2. 說明 Auto Refresh 預設關閉。
3. 說明最小 interval 60 秒。
4. 說明 Auto Refresh 忙碌中會 skip，不會 queue。
5. 說明設定會記錄在 GUI settings。

## 16. 驗收標準

### 16.1 功能驗收

1. GUI 有 `More > Settings...`。
2. Settings dialog 可啟用 / 停用 Auto Refresh。
3. Settings dialog 可設定 interval。
4. interval 最小 60 秒。
5. 啟用 Auto Refresh 後會定期 refresh。
6. 忙碌中 Auto Refresh 不執行。
7. 不會發生多個 Auto Refresh 重疊。
8. 關閉 GUI 後重開，設定仍保留。
9. 儲存 target 不會覆蓋 Auto Refresh 設定。
10. 儲存 Auto Refresh 不會覆蓋 target。

### 16.2 回歸驗收

1. 手動 Refresh 正常。
2. Details / Best / Add / Use / Remove / Export / Import / Doctor 不受影響。
3. Activity / Log 行為不受影響。
4. CLI 不受影響。
5. 既有 tests 通過。

### 16.3 安全與穩定驗收

1. Auto Refresh 不會毫秒級觸發。
2. Auto Refresh 不會在 login dialog 中插入 refresh。
3. Auto Refresh 不會在 busy operation 中 queue。
4. Auto Refresh error 不會反覆彈 messagebox。
5. Auto Refresh 不會改變 current alias。

## 17. 建議分階段

### Phase 1：Settings storage refactor

- 新增通用 settings load/save helper。
- `save_target_setting()` 改成不覆蓋其他 settings。
- 讀取舊 settings 相容。

### Phase 2：Settings dialog

- More > Settings...
- Auto Refresh enabled / interval controls。
- interval normalize / validation。

### Phase 3：Auto Refresh engine

- root.after 排程。
- 防重疊。
- busy skip。
- manual refresh reset timer。
- target change reset timer。

### Phase 4：文件與測試

- tests/test_gui_settings.py。
- README 更新。
- 手動 smoke test。

## 18. 完成定義

完成後，使用者可以在 GUI 中設定 Auto Refresh，並且每次啟動保留上次設定。Auto Refresh 應保守、可控、不干擾其他操作，並且 interval 不允許短到造成 Codex CLI / app-server 被過度輪詢。
