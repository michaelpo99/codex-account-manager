# CR-010: Backup Folder Sync 與安全自動匯入

Status: Proposed

## 1. 背景

`cx` 目前已支援手動備份與匯入：

```bash
cx export [alias...] [--alias ...] [--email ...] [-o PATH]
cx import <archive> [--alias ...] [--email ...] [--force|--skip-existing] [--set-current]
cx backup-list <archive>
```

目前備份格式為 `tar.gz`，內含 `manifest.json`、`accounts/<alias>/auth.json`，以及可選的 `accounts/<alias>/meta.json`。目前 `BACKUP_VERSION = 2`，manifest 已包含整包備份時間 `createdAt` 與每個 account 的 alias、email、scope、plan 摘要。

新的需求是讓使用者可指定一個備份同步目錄，例如 Google Drive for desktop、rclone mount、GCS FUSE、或其他雲端同步工具掛載出來的本機目錄。`codex-account-manager` 定時掃描該目錄中的備份檔，當發現同一個 email 有明確較新的帳號備份時自動匯入；若本機沒有該 email，則自動新增；若版本未更新或更舊，則跳過。

本 CR 採「本機同步目錄」設計，不直接整合 Google Drive API 或 Google Cloud Storage API。這可避免在本工具中管理額外雲端 OAuth、service account、refresh token、API quota、網路重試與跨平台憑證儲存問題。

## 2. 目標

1. 新增 Backup Folder Sync 功能。
2. 使用者可在 GUI 設定同步目錄位置。
3. 使用者可在 GUI 設定檢查間隔時間。
4. 同步目錄與 interval 必須持久化到既有 `gui-settings.json`。
5. GUI 啟動時必須還原上次設定。
6. Sync 預設關閉，不應在升級後自動啟用。
7. 支援掃描指定目錄下的 `*.tar.gz` 備份檔。
8. 新增備份格式 v3，加入 per-account sync metadata，用於可靠判斷新舊。
9. 保持讀取 v1/v2 備份檔的能力。
10. 當 remote v3 備份與本機同 email 帳號相比明確較新時，自動覆蓋本機帳號。
11. 當 remote v3 備份對應 email 在本機不存在時，自動新增帳號。
12. 當 remote 版本未更新、相同、較舊、或無法安全判斷時跳過。
13. 覆蓋前必須建立本機 rollback backup。
14. Sync 執行時不得與登入、renew、手動 import/export、refresh 等背景操作重疊。
15. 所有 import、skip、warning、error 都必須寫入 GUI Activity log。

## 3. 非目標

本 CR 不做以下事項：

1. 不直接整合 Google Drive API。
2. 不直接整合 Google Cloud Storage API。
3. 不實作雲端上傳或自動 export 到雲端目錄。
4. 不實作即時 filesystem watcher；第一版只做 interval polling。
5. 不處理多使用者同時寫入同一帳號備份的完整衝突合併。
6. 不加入備份加密功能。
7. 不改 Codex `auth.json` 的內容格式。
8. 不把 sync 設為預設開啟。
9. 不讓 v1/v2 舊備份在預設情況下自動覆蓋既有帳號。
10. 不移除既有 `cx import` alias-based 行為。

## 4. 名詞與判斷基準

### 4.1 Local account

本機已保存於 `DATA_DIR/accounts/<alias>/` 的帳號資料。

### 4.2 Remote account

同步目錄中某個備份檔內的 account entry。

### 4.3 Identity key

Sync 的主要比對鍵是 email，不是 alias。

既有 `cx import` 以 alias 判斷衝突；Backup Folder Sync 必須改用 email 找到本機既有帳號。若 remote alias 與 local alias 不同，預設應保留 local alias，避免破壞使用者本機操作習慣。

### 4.4 Backup revision

v3 備份中的 per-account 版本值。第一版使用 UTC ISO-8601 timestamp：

```text
2026-06-25T23:00:00Z
```

此欄位必須用於判斷 remote 是否比 local 新。

### 4.5 Auth hash

`auth.json` bytes 的 SHA-256 digest，格式：

```text
sha256:<hex>
```

此欄位用於判斷相同 revision 下內容是否一致，也可輔助避免重複匯入。

## 5. 備份格式 v3

### 5.1 版本常數

將目前：

```python
BACKUP_VERSION = 2
```

升級為：

```python
BACKUP_VERSION = 3
SUPPORTED_BACKUP_VERSIONS = {1, 2, 3}
```

不得再使用下列寫法限制支援版本：

```python
if version not in {1, BACKUP_VERSION}:
    raise CxError(...)
```

應改為：

```python
if version not in SUPPORTED_BACKUP_VERSIONS:
    raise CxError(...)
```

### 5.2 manifest.json v3 建議格式

```json
{
  "version": 3,
  "createdAt": "2026-06-25T23:00:00Z",
  "aliases": ["work-main"],
  "accounts": [
    {
      "alias": "work-main",
      "email": "user@example.com",
      "scope": "work",
      "plan": "pro",
      "backupRevision": "2026-06-25T23:00:00Z",
      "authHash": "sha256:...",
      "sourceHost": "desktop-a"
    }
  ],
  "current": "work-main"
}
```

### 5.3 欄位規則

`version`：必填，v3 固定為 `3`。

`createdAt`：必填，整包備份建立時間。v1/v2 相容時可作為弱版本來源，但不應作為可靠 per-account 版本。

`accounts[].backupRevision`：v3 必填，per-account 版本。第一版可與 export 時間相同。

`accounts[].authHash`：v3 必填，以 `accounts/<alias>/auth.json` bytes 計算 SHA-256。

`accounts[].sourceHost`：v3 選填，只用於 log 與除錯。

### 5.4 舊備份相容

`read_backup_manifest()` 必須繼續讀取 v1/v2。

v1/v2 備份沒有可靠 per-account `backupRevision` 與 `authHash`。因此 Sync 對 v1/v2 的預設策略是：

```text
本機沒有同 email：可新增
本機已有同 email：跳過，不自動覆蓋
```

若未來需要，可加入進階選項 `allow_legacy_overwrite`，但本 CR 預設必須為 `false`。

## 6. 本機 meta.json 擴充

本機 `accounts/<alias>/meta.json` 應保留既有欄位並新增 sync metadata：

```json
{
  "scope": "work",
  "email": "user@example.com",
  "plan": "pro",
  "backupRevision": "2026-06-25T23:00:00Z",
  "authHash": "sha256:...",
  "lastSyncSource": "G:\\My Drive\\codex-backups\\cx-backup-20260625-230000.tar.gz",
  "lastSyncAt": "2026-06-25T23:05:00Z"
}
```

既有 `write_account_meta()` 目前只處理 `scope`、`email`、`plan`。實作時可選擇：

1. 擴充 `write_account_meta()` 支援 optional sync fields。
2. 或新增 `write_account_sync_meta()`，只更新 sync metadata，避免影響既有語意。

建議採第 2 種，以降低既有 add/save/renew/import 行為被誤改的風險。

## 7. GUI settings 設計

### 7.1 持久化位置

沿用既有 `gui-settings.json`，不得新增第二份 GUI 設定檔。

Windows 預設：

```text
%LOCALAPPDATA%\cx\gui-settings.json
```

非 Windows 預設：

```text
~/.local/share/cx/gui-settings.json
```

### 7.2 JSON schema

在既有 settings 中新增 `backup_sync`：

```json
{
  "target": "WSL: Ubuntu-22.04",
  "auto_refresh": {
    "enabled": false,
    "interval_seconds": 300
  },
  "backup_sync": {
    "enabled": false,
    "directory": "",
    "interval_seconds": 300,
    "import_new_accounts": true,
    "overwrite_existing_accounts": true,
    "allow_legacy_overwrite": false,
    "rollback_before_overwrite": true
  }
}
```

### 7.3 預設值

```text
backup_sync.enabled = false
backup_sync.directory = ""
backup_sync.interval_seconds = 300
backup_sync.import_new_accounts = true
backup_sync.overwrite_existing_accounts = true
backup_sync.allow_legacy_overwrite = false
backup_sync.rollback_before_overwrite = true
```

### 7.4 Interval 規則

沿用 Auto Refresh 的保守範圍：

```text
Minimum: 60 seconds
Maximum: 3600 seconds
Default: 300 seconds
Unit: seconds
Type: integer only
```

`0` 視為停用 Backup Sync，不代表 0 秒同步。

### 7.5 Settings Dialog UI

既有 Settings dialog 目前已有 Auto Refresh 設定。本 CR 建議擴充為兩段：

```text
Settings

Auto Refresh
[ ] Enable auto refresh
Interval: ( ) 1 min ( ) 2 min ( ) 5 min ( ) 10 min ( ) Custom [300] seconds

Backup Sync
[ ] Enable backup folder sync
Folder: [ G:\My Drive\codex-backups             ] [Browse...]
Interval: ( ) 1 min ( ) 2 min ( ) 5 min ( ) 10 min ( ) Custom [300] seconds
[x] Import new accounts
[x] Overwrite existing accounts only when remote v3 is newer
[x] Create rollback backup before overwrite
[ ] Allow legacy v1/v2 backups to overwrite existing accounts

[Save] [Cancel]
```

`Allow legacy v1/v2 backups to overwrite existing accounts` 必須預設關閉，且 UI 文案應明確提示風險。

## 8. Sync 判斷規則

### 8.1 掃描規則

1. 只掃描使用者設定目錄的第一層 `*.tar.gz`。
2. 不遞迴子目錄。
3. 忽略暫存檔，例如副檔名不是 `.tar.gz` 的檔案。
4. 無法開啟、manifest 無法解析、不支援版本、缺少必要檔案時，記錄 warning 後跳過。
5. 同一個 email 在多個備份檔出現時，選擇可安全判斷的最新 remote account。
6. email 無法識別時跳過，不得自動匯入。

### 8.2 v3 remote 對 v3 local

```text
remote.backupRevision > local.backupRevision：覆蓋
remote.backupRevision == local.backupRevision 且 authHash 相同：跳過
remote.backupRevision == local.backupRevision 但 authHash 不同：跳過並警告
remote.backupRevision < local.backupRevision：跳過
```

### 8.3 v3 remote 對 v2 local 或無 sync metadata local

允許自動覆蓋，但必須滿足全部條件：

1. email 明確相同。
2. remote 是 v3。
3. remote 有合法 `backupRevision`。
4. remote 有合法 `authHash`，或可從 archive 中的 `auth.json` 重新計算。
5. GUI 設定 `overwrite_existing_accounts = true`。
6. 覆蓋前成功建立 rollback backup。

此規則用於平滑升級：使用者從舊版本機資料升級後，可讓 v3 備份補上本機 sync metadata。

### 8.4 v1/v2 remote 對 local

預設規則：

```text
本機沒有同 email：新增
本機已有同 email：跳過
```

若未來實作 `allow_legacy_overwrite = true`，也只能在以下條件都成立時覆蓋：

1. email 明確相同。
2. remote `manifest.createdAt` 可解析。
3. local 沒有 `backupRevision`。
4. 覆蓋前成功建立 rollback backup。
5. Activity log 明確寫出這是 legacy overwrite。

第一版可先不開放 legacy overwrite 的實際覆蓋行為，只保留 settings schema 與 UI disabled/help text。

### 8.5 新增帳號 alias 規則

當 remote email 本機不存在時：

1. 優先使用 remote alias。
2. 若 remote alias 已被本機其他 email 使用，產生不衝突 alias。
3. 建議格式：

```text
<remote-alias>-sync
<remote-alias>-sync-2
```

4. 新增後寫入 meta，包括 email、plan、scope、backupRevision、authHash、lastSyncSource、lastSyncAt。

### 8.6 覆蓋帳號 alias 規則

當 remote email 本機已存在時：

1. 使用本機既有 alias。
2. 不因 remote alias 不同而更名。
3. 只覆蓋該 local alias 的 `auth.json` 與必要 meta 欄位。
4. `scope` 預設保留本機值；除非本機沒有 scope，才採用 remote scope。
5. `plan`、`email`、`backupRevision`、`authHash`、`lastSyncSource`、`lastSyncAt` 可更新。

## 9. Rollback 設計

### 9.1 目的

自動覆蓋的是登入憑證，錯誤覆蓋會讓使用者難以追蹤。因此覆蓋前必須建立 rollback backup。

### 9.2 位置

建議位置：

```text
DATA_DIR/rollback/
```

範例：

```text
%LOCALAPPDATA%\cx\rollback\cx-rollback-20260625-230500-user_example_com.tar.gz
```

### 9.3 內容

rollback 可複用既有 export 格式，至少包含即將被覆蓋的 local alias。

### 9.4 失敗處理

若 rollback 建立失敗：

1. 不得覆蓋。
2. 記錄 error。
3. GUI 不彈出反覆干擾的 messagebox；只寫 Activity log 與 status。

## 10. CLI 設計

Backup Sync 邏輯應放在 CLI 可測試層，GUI 只負責設定與排程。

### 10.1 新增指令

建議新增：

```bash
cx sync-check --dir PATH [--json]
cx sync-import --dir PATH [--apply] [--json]
```

### 10.2 sync-check

`sync-check` 只掃描與產生計畫，不寫入本機帳號。

輸出應包含：

```text
would-import-new
would-overwrite
skip-same-version
skip-older
skip-legacy-existing
skip-missing-email
skip-invalid-archive
error
```

JSON 模式範例：

```json
{
  "directory": "G:\\My Drive\\codex-backups",
  "actions": [
    {
      "action": "would-overwrite",
      "email": "user@example.com",
      "localAlias": "work-main",
      "remoteAlias": "work-main",
      "archive": "cx-backup-20260625-230000.tar.gz",
      "reason": "remote v3 backupRevision is newer"
    }
  ],
  "warnings": []
}
```

### 10.3 sync-import

`sync-import` 執行匯入。

建議第一版要求明確 `--apply`，避免誤執行：

```bash
cx sync-import --dir "G:\My Drive\codex-backups" --apply
```

不帶 `--apply` 時只輸出提示，或等同 dry-run。

### 10.4 GUI 呼叫方式

GUI 定時器可呼叫：

```bash
cx sync-import --dir <configured-dir> --apply --json
```

解析 JSON 後寫入 Activity log，必要時 refresh accounts。

## 11. GUI 排程設計

### 11.1 排程

仿照 Auto Refresh 使用 `root.after()`。

狀態欄文字範例：

```text
Ready · Backup sync off
Ready · Backup sync every 5 min; next 23:10:00
Backup sync skipped; app is busy
Backup sync imported 1, skipped 4
```

### 11.2 防重疊

Backup Sync tick 時，如果以下任一條件成立，應跳過並重新排程：

1. `busy_count > 0`
2. `login_dialog_active == true`
3. auto refresh 正在執行
4. update check 正在執行
5. 另一個 backup sync 正在執行

### 11.3 失敗處理

1. 目錄不存在：記錄 warning，保持設定，不自動清空。
2. 目錄無權限：記錄 error。
3. 沒有備份檔：記錄 concise log，不彈窗。
4. 單一備份損壞：跳過該檔，繼續處理其他檔。
5. 多次失敗不得連續彈出 messagebox。

## 12. 安全與風險

### 12.1 敏感資料

備份檔包含 Codex `auth.json`，屬高敏感資料。同步目錄若位於雲端，安全性取決於使用者的雲端帳號、裝置加密、同步工具與資料夾分享權限。

本 CR 不加密備份，因此文件與 UI 應提醒：不要把備份同步目錄分享給不可信任對象。

### 12.2 舊備份風險

v1/v2 缺少可靠 per-account 版本資訊。不能只因檔案出現在同步目錄或 mtime 較新就覆蓋本機帳號。

### 12.3 同步衝突

Google Drive、rclone 或其他同步工具可能產生 conflict copy 或延遲同步。Sync 必須以 manifest metadata 與 authHash 判斷，不得只依賴檔案修改時間。

### 12.4 同 email 多 alias

如果本機已有多個 alias 對應同一 email，第一版應跳過並警告，不自動選擇其中一個覆蓋。這代表本機資料已不符合 email 唯一假設。

## 13. 執行計畫

### Phase 1: 資料模型與備份格式

1. 新增 `SUPPORTED_BACKUP_VERSIONS = {1, 2, 3}`。
2. 將 `BACKUP_VERSION` 升為 3。
3. 新增 SHA-256 helper，用於計算 `authHash`。
4. 修改 `cmd_export()`，在 v3 manifest 的每個 account summary 加入 `backupRevision`、`authHash`、可選 `sourceHost`。
5. 修改 `validate_backup_summary()`，接受 v1/v2 無 sync metadata，也驗證 v3 sync metadata。
6. 修改 `read_backup_manifest()`，支援 v1/v2/v3。
7. 新增或擴充 local meta helper，以保存 `backupRevision`、`authHash`、`lastSyncSource`、`lastSyncAt`。

驗收：

```bash
cx export -o /tmp/cx-v3.tar.gz
cx backup-list /tmp/cx-v3.tar.gz
```

必須可正常列出帳號。v1/v2 測試 fixture 仍可被 `backup-list` 讀取。

### Phase 2: Sync planner

1. 新增掃描目錄 helper，只讀第一層 `*.tar.gz`。
2. 新增 archive inspection helper，不直接寫入本機。
3. 新增 email-based local account lookup。
4. 新增 sync planner，輸出 action plan。
5. 處理同 email 多 remote 備份，選出最新可用 v3。
6. 處理同 email 多 local alias，跳過並 warning。
7. 實作 v3/v3、v3/v2-local、v1/v2 remote 的判斷規則。
8. 新增 `cx sync-check --dir PATH [--json]`。

驗收：

```bash
cx sync-check --dir ./test-backups --json
```

必須只輸出計畫，不改本機資料。

### Phase 3: Sync importer 與 rollback

1. 新增 rollback directory helper。
2. 覆蓋前匯出 local alias 到 rollback tar.gz。
3. 新增 sync apply function。
4. 新增 `cx sync-import --dir PATH --apply [--json]`。
5. 新增新帳號 alias collision 解決規則。
6. 覆蓋同 email 帳號時保留 local alias。
7. 覆蓋成功後寫入 sync metadata。
8. 任何 rollback 失敗時不得覆蓋。

驗收：

```bash
cx sync-import --dir ./test-backups --apply --json
cx list
```

覆蓋前必須建立 rollback，且 import 後 meta 內有 `backupRevision` 與 `authHash`。

### Phase 4: GUI settings 與排程

1. 擴充 `SettingsDialogResult`，加入 backup sync 欄位。
2. 擴充 Settings dialog UI。
3. 新增 `load_backup_sync_settings()`。
4. 新增 `save_backup_sync_settings()`。
5. 新增 interval normalize helper，或抽出共用 helper 避免與 Auto Refresh 重複。
6. 新增 `schedule_backup_sync()`、`cancel_backup_sync()`、`reset_backup_sync_timer()`、`on_backup_sync_tick()`。
7. 忙碌、登入中、其他背景工作執行時跳過。
8. GUI 呼叫 CLI sync-import，解析 JSON，寫入 Activity log。
9. Sync 成功 import 後 refresh account list。

驗收：

1. 設定目錄與 interval 後關閉 GUI，再開啟仍保留設定。
2. Sync disabled 時不排程。
3. Sync enabled 但目錄不存在時不 crash。
4. Login dialog 開啟時 sync tick 會跳過。
5. Sync 匯入後 GUI 列表更新。

### Phase 5: 文件與回歸測試

1. 更新 README 或 manual，說明 Backup Folder Sync。
2. 補充備份目錄安全警告。
3. 補充 v1/v2/v3 相容行為。
4. 新增單元測試或 fixture 測試。
5. 執行 docs status check。

建議測試指令：

```bash
python scripts/docs_status.py --mode check
python -m pytest
```

若專案尚未有 pytest 測試架構，至少新增可由 CLI 執行的 fixture smoke test。

## 14. 測試案例

### 14.1 Export / manifest

1. v3 export 產生 `version: 3`。
2. v3 accounts entry 含 `backupRevision`。
3. v3 accounts entry 含合法 `authHash`。
4. `authHash` 與 archive 內 `auth.json` bytes 一致。

### 14.2 Backup list compatibility

1. v1 fixture 可讀。
2. v2 fixture 可讀。
3. v3 fixture 可讀。
4. version 999 應報不支援。
5. manifest 缺少 aliases 應報錯。

### 14.3 Sync planner

1. 本機無 email，remote v3：would-import-new。
2. 本機有 email，remote v3 newer：would-overwrite。
3. 本機有 email，remote v3 same revision same hash：skip-same-version。
4. 本機有 email，remote v3 same revision different hash：skip-conflict。
5. 本機有 email，remote v3 older：skip-older。
6. 本機無 email，remote v2：would-import-new。
7. 本機有 email，remote v2：skip-legacy-existing。
8. remote 無 email：skip-missing-email。
9. 本機同 email 多 alias：skip-local-ambiguous。
10. 多個 remote 同 email：選最新 v3。

### 14.4 Sync import

1. 新 email 可新增帳號。
2. remote alias collision 時產生不衝突 alias。
3. 同 email 覆蓋時保留 local alias。
4. 覆蓋前建立 rollback。
5. rollback 建立失敗時不覆蓋。
6. import 後 meta 寫入 sync metadata。

### 14.5 GUI settings

1. 預設 backup sync disabled。
2. 設定目錄持久化。
3. interval 持久化。
4. interval 小於 60 clamp 或拒絕。
5. interval 大於 3600 clamp 或拒絕。
6. settings JSON 損毀時 GUI 不 crash，回到預設值。

### 14.6 GUI schedule

1. enabled=false 時不排程。
2. enabled=true 且 directory 有效時排程。
3. busy 時跳過並重新排程。
4. login dialog active 時跳過並重新排程。
5. sync import 成功後 refresh accounts。
6. sync error 不連續彈出 messagebox。

## 15. 驗收標準

本 CR 完成時需滿足：

1. `cx export` 預設產生 v3 備份。
2. `cx backup-list` 可讀 v1/v2/v3。
3. `cx sync-check` 可在不寫入本機資料下產生 sync plan。
4. `cx sync-import --apply` 可依 email 新增或覆蓋帳號。
5. remote v3 可安全覆蓋 local v2 或無 sync metadata 的同 email 帳號。
6. remote v1/v2 預設不覆蓋既有帳號。
7. 覆蓋前必定建立 rollback。
8. GUI 可設定 backup sync directory 與 interval。
9. GUI 設定會持久化到既有 `gui-settings.json`。
10. GUI 啟動後會還原 backup sync 設定。
11. GUI sync 不會與其他背景操作重疊。
12. 所有 sync 結果可在 Activity log 追蹤。

## 16. 建議實作順序

建議不要先做 GUI。先完成 CLI 層，否則 GUI debug 會干擾資料格式與同步規則。

推薦順序：

1. v3 manifest 與 v1/v2/v3 read compatibility。
2. sync-check dry-run planner。
3. rollback + sync-import apply。
4. GUI settings persistence。
5. GUI interval scheduler。
6. 文件與測試 fixture。

## 17. 開放問題

1. v3 `backupRevision` 第一版是否只用 export time，或需要額外保存 token 取得時間？第一版建議用 export time。
2. 本機同 email 多 alias 時是否永遠跳過？第一版建議跳過並 warning。
3. legacy overwrite 是否要提供 UI？第一版可先不提供，或提供但預設關閉並加風險提示。
4. 是否需要清理舊 rollback？第一版可先不自動清理，後續再加 retention policy。
5. 是否需要支援 recursive folder scan？第一版不建議。
