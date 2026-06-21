# CR-009: GUI 新版本檢查與提醒

Status: Proposed

## 1. 背景

`cx-gui` 目前沒有主動提醒使用者是否已有新版本。當 CLI / GUI 修復 bug 或新增功能後，使用者可能仍長時間停留在舊版，導致已修復問題反覆出現。

本 CR 新增 GUI 的新版本檢查機制。此功能只做提醒，不自動下載、不自動安裝、不阻塞使用者操作。

## 2. 目標

1. GUI 啟動後，不立刻檢查新版本。
2. GUI 開啟至少 10 秒後，才可執行第一次版本檢查。
3. 每次版本檢查之間至少間隔 8 小時。
4. 檢查必須在背景執行，不得阻塞 UI thread。
5. 有新版本時，在 GUI 中提示使用者。
6. 沒有新版本時，不彈出提示。
7. 檢查失敗時，不彈出錯誤 messagebox，只在 Activity / Log 或 status 中留下低干擾訊息。
8. 使用者可關閉或延後此次新版本提醒。
9. 第一版只提醒，不自動更新。
10. 版本檢查狀態需寫入 GUI settings，避免每次開啟 GUI 都重複檢查。

## 3. 非目標

本 CR 不做以下事項：

1. 不自動下載新版。
2. 不自動執行 `pipx upgrade`、`install.ps1` 或 `install.sh`。
3. 不強迫使用者更新。
4. 不在 CLI `cx` 中新增 update check。
5. 不在 GUI 啟動時立即呼叫網路。
6. 不在檢查失敗時反覆彈窗。
7. 不把 update check 和 Auto Refresh 綁在一起。
8. 不檢查 Codex CLI 本身的新版本，只檢查 `cx-account-manager`。

## 4. 版本來源

第一版建議使用 GitHub Releases 作為版本來源。

建議檢查：

```text
https://api.github.com/repos/michaelpo99/codex-account-manager/releases/latest
```

取回 JSON 後讀取：

```text
tag_name
html_url
name
published_at
body
```

若專案尚未使用 GitHub Releases，可改用以下替代來源，但必須在實作前二選一，不要同時混用：

```text
方案 A：GitHub Releases latest
方案 B：raw VERSION / pyproject metadata endpoint
```

第一版建議採方案 A。

## 5. Timing 規則

### 5.1 首次檢查延遲

GUI 啟動後至少等待：

```text
10 seconds
```

才可開始檢查。

目的：

1. 避免 GUI 一開啟就打網路。
2. 避免啟動畫面、初次 refresh、doctor 或 settings load 同時競爭資源。
3. 讓主畫面先可用。

### 5.2 最小檢查間隔

每次版本檢查之間至少間隔：

```text
8 hours
```

計算依據使用 wall-clock time。建議儲存 UTC ISO timestamp。

```json
{
  "update_check": {
    "last_checked_at": "2026-06-21T11:00:00Z"
  }
}
```

若目前時間距離 `last_checked_at` 未滿 8 小時，啟動時不檢查。

### 5.3 檢查中狀態

同一時間只能有一個 update check。

若前一個 update check 尚未完成，後續觸發應直接略過。

## 6. Settings JSON 格式

擴充既有 GUI settings，不另開新檔。

建議格式：

```json
{
  "target": "WSL: Ubuntu-22.04",
  "auto_refresh": {
    "enabled": false,
    "interval_seconds": 300
  },
  "update_check": {
    "enabled": true,
    "last_checked_at": null,
    "last_seen_version": null,
    "dismissed_version": null,
    "last_error_at": null
  }
}
```

欄位說明：

```text
enabled             是否啟用版本檢查，第一版預設 true
last_checked_at     上次實際檢查時間
last_seen_version   上次從遠端看到的最新版本
dismissed_version   使用者已關閉提醒的版本
last_error_at       最近一次檢查失敗時間，只做低干擾記錄
```

相容性要求：

1. 舊 settings 沒有 `update_check` 時，使用預設值。
2. settings JSON 損毀時，不可導致 GUI crash。
3. 儲存 `update_check` 時，不得覆蓋既有 `target`、`auto_refresh` 或未來 settings 欄位。

## 7. Version 比較規則

本專案版本來源為 `cx_account_manager.__version__`。

遠端版本通常來自 release `tag_name`，可能格式為：

```text
v4.2.1
4.2.1
```

比較前應 normalize：

```text
strip leading v / V
strip whitespace
```

第一版只需要支援標準 semantic version：

```text
MAJOR.MINOR.PATCH
```

若遠端 tag 無法解析為 semantic version：

1. 不顯示新版本提示。
2. 在 Activity / Log 留下低干擾訊息。
3. 更新 `last_checked_at`，避免短時間內反覆檢查同一個壞資料。

若本機版本無法解析，也採同樣策略。

## 8. UI 提醒設計

### 8.1 提醒位置

不建議使用啟動時 messagebox。

建議在主畫面 status / top notice 顯示非阻塞提示：

```text
New version available: 4.3.0   [Open Release] [Dismiss]
```

或：

```text
Update available: cx-account-manager 4.3.0
```

### 8.2 Open Release

按下 `Open Release` 時，使用系統瀏覽器開啟 release URL。

### 8.3 Dismiss

按下 `Dismiss` 時，寫入：

```json
{
  "update_check": {
    "dismissed_version": "4.3.0"
  }
}
```

同一版本不再提醒。

若之後遠端版本變成 `4.3.1`，則可再次提醒。

### 8.4 沒有新版

沒有新版時不彈窗、不新增 top notice。

可在 Activity / Log 記錄：

```text
Update check: already up to date.
```

但不必顯示在主要 status bar。

### 8.5 檢查失敗

失敗時不彈窗。

可在 Activity / Log 記錄：

```text
Update check failed: <reason>
```

主畫面 status 不應長時間停留在錯誤狀態，避免看起來像核心功能故障。

## 9. 網路與 timeout 規則

第一版使用 Python standard library，避免新增 dependency。

建議：

```python
urllib.request.urlopen(url, timeout=5)
```

timeout 建議：

```text
5 seconds
```

要求：

1. 必須設定 timeout。
2. 必須在 background thread 執行。
3. 不得阻塞 UI thread。
4. HTTP error、network error、JSON parse error 都應被捕捉。
5. 檢查失敗仍應寫入 `last_checked_at`，避免 GUI 每次啟動都立即重試。

## 10. 手動檢查入口

建議在 `More` 選單新增：

```text
Check for Updates
```

手動檢查行為：

1. 不受 8 小時間隔限制。
2. 仍須 background thread。
3. 仍須 timeout。
4. 若已是最新版，可顯示 messagebox 或 status：

```text
You are running the latest version.
```

5. 若檢查失敗，手動檢查可以顯示較明確的 messagebox，因為這是使用者主動要求。

自動檢查與手動檢查的差異：

```text
自動檢查：低干擾，不彈錯誤視窗，受 8 小時間隔限制。
手動檢查：可顯示結果，無 8 小時間隔限制。
```

## 11. 與 Auto Refresh 的關係

Update check 不應使用 Auto Refresh timer。

原因：

1. Auto Refresh 是帳號狀態刷新。
2. Update check 是版本資訊查詢。
3. 兩者頻率、錯誤處理與 UI 提醒不同。

但兩者都要遵守 GUI busy 原則：

1. 若 GUI 正在執行 Add / Renew / Import / Export / Doctor 等操作，自動 update check 可延後。
2. 手動 Check for Updates 可允許執行，但應避免與其他 blocking dialog 衝突。

## 12. 實作建議

### 12.1 常數

建議新增：

```python
UPDATE_CHECK_STARTUP_DELAY_SECONDS = 10
UPDATE_CHECK_MIN_INTERVAL_SECONDS = 8 * 60 * 60
UPDATE_CHECK_TIMEOUT_SECONDS = 5
UPDATE_CHECK_LATEST_RELEASE_URL = "https://api.github.com/repos/michaelpo99/codex-account-manager/releases/latest"
```

### 12.2 啟動排程

GUI 初始化完成後：

```python
self.root.after(UPDATE_CHECK_STARTUP_DELAY_SECONDS * 1000, self.maybe_check_for_updates)
```

`maybe_check_for_updates()`：

```text
1. settings.update_check.enabled must be true
2. no update check currently running
3. now - last_checked_at >= 8 hours
4. GUI not in critical busy operation, or defer shortly
5. start background worker
```

### 12.3 背景 worker

背景 worker 只做：

```text
1. fetch latest release JSON
2. parse latest version and release URL
3. compare with local version
4. return structured result to UI thread
```

UI 更新必須透過 `root.after(...)` 回主 thread。

### 12.4 structured result

建議 dataclass：

```python
@dataclass
class UpdateCheckResult:
    ok: bool
    latest_version: str | None = None
    release_url: str | None = None
    error: str | None = None
    is_newer: bool = False
```

## 13. 測試規格

至少新增或更新以下測試：

1. 啟動後不會立即檢查，需等待 10 秒 callback。
2. `last_checked_at` 未滿 8 小時時，自動檢查略過。
3. `last_checked_at` 超過 8 小時時，自動檢查可執行。
4. 手動檢查不受 8 小時間隔限制。
5. 版本比較支援 `v4.3.0` 與 `4.3.0`。
6. 遠端版本大於本機版本時，顯示 update notice。
7. 遠端版本等於或小於本機版本時，不顯示 notice。
8. `dismissed_version` 等於 latest version 時，不顯示 notice。
9. 網路錯誤時不彈自動錯誤 messagebox。
10. settings 儲存 update_check 時，不覆蓋其他 settings。
11. JSON 損毀時 GUI 不 crash。

## 14. 驗收條件

1. 開啟 GUI 後至少 10 秒才可能檢查新版本。
2. 自動檢查間隔至少 8 小時。
3. 有新版本時，GUI 顯示非阻塞提示。
4. 沒有新版本時，不打擾使用者。
5. 自動檢查失敗時，不彈 messagebox。
6. 使用者可 dismiss 某個版本，該版本不再提醒。
7. `More` 選單提供 `Check for Updates`。
8. 手動檢查可立即執行，且會明確回報結果。
9. 不新增第三方 dependency。
10. 測試通過：

```bash
python -m pytest
ruff check .
```

## 15. 風險與取捨

### 15.1 預設啟用的取捨

第一版建議預設啟用 update check，因為它只在 GUI 啟動 10 秒後執行，且至少 8 小時一次，干擾低。

若未來使用者需要完全離線或公司網路限制，可在 Settings 中加入關閉選項。

### 15.2 不自動更新

自動更新跨平台風險較高，尤其目前專案同時支援 pipx、install.sh、install.ps1、WSL 與 Windows native。第一版只提醒是較安全的選擇。

### 15.3 release source 依賴

若 GitHub Releases 尚未建立，版本檢查會沒有資料。這種情況應視為「無法判斷」，不應打擾使用者。

### 15.4 檢查失敗也更新 last_checked_at

這會讓短暫網路問題後，GUI 不會在 8 小時內自動重試。取捨是降低干擾與避免反覆打網路。使用者仍可用 `Check for Updates` 手動重試。
