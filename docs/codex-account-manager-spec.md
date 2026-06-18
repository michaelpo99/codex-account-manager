# Codex CLI 多帳號切換與用量查詢工具規格

## 1. 專案目的

製作一個在 Linux / macOS / WSL / Windows PowerShell 下使用的命令列工具 `cx`，用來管理多個 Codex CLI 帳號。

主要需求：

1. 每個帳號只需要登入一次。
2. 可以替帳號設定簡短代號，例如 `plus1`、`plus2`、`company`。
3. 可以快速查看所有帳號的 Codex 用量。
4. 可以選擇目前要使用的帳號。
5. 切換帳號後，盡量保留原本 Codex CLI 的本機交談紀錄與環境資料。
6. 不把 Token、密碼或完整登入資料顯示在畫面上。
7. 操作方式要簡單，適合日常頻繁切換。

預期操作：

```bash
cx add plus1
cx add plus2
cx status
cx use plus2
cx current
cx manual
```

---

## 2. 執行環境

主要環境：

- Windows 11 / PowerShell
- WSL2
- Ubuntu
- macOS
- Bash
- 已安裝 Codex CLI
- `codex` 指令已在 `PATH` 中
- Python 3 可用

工具本身可以使用：

- Bash
- Python 3 標準函式庫

優先不要增加額外的 Python 套件相依。

---

## 3. 核心設計

### 3.1 共用 Codex 本機工作資料

預設 Codex CLI 仍使用：

```text
~/.codex
```

目的是保留：

- 本機 Session
- 交談歷史
- Codex 設定
- 專案信任狀態
- 其他 Codex CLI 本機資料

多帳號工具只管理登入憑證，不應任意刪除或重建 `~/.codex`。

### 3.2 各帳號登入資料分開保存

建議目錄：

```text
~/.local/share/cx/
├── accounts/
│   ├── plus1/
│   │   ├── auth.json
│   │   └── meta.json
│   ├── plus2/
│   │   ├── auth.json
│   │   └── meta.json
│   └── company/
│       ├── auth.json
│       └── meta.json
├── current
├── lock
└── tmp/
```

權限要求：

```text
~/.local/share/cx                 700
~/.local/share/cx/accounts        700
各帳號目錄                        700
auth.json                         600
meta.json                         600
~/.local/share/cx/tmp             700
```

`auth.json` 是登入憑證，不得輸出內容，不得提交到 Git。

### 3.3 切換帳號的方式

MVP 採用「切換目前 `~/.codex/auth.json`」的方式。

執行：

```bash
cx use plus1
```

時：

1. 確認 `plus1` 存在。
2. 將 `accounts/plus1/auth.json` 原子性複製到：
   ```text
   ~/.codex/auth.json
   ```
3. 檔案權限設為 `600`。
4. 將目前帳號代號寫到：
   ```text
   ~/.local/share/cx/current
   ```
5. 更新 `current` 標記。
6. 不顯示 Token。

原子性複製建議：

1. 先複製到暫存檔。
2. 設定權限。
3. 使用 `mv` 取代正式檔案。

切換時應使用 `flock` 或其他鎖定方式，避免兩個切換操作同時改寫檔案。

### 3.4 交談延續

因為所有帳號仍共用：

```text
~/.codex
```

所以本機 Session 與歷史資料會保留。

切換帳號後若要驗證共享的本機 Session，可直接嘗試：

```bash
codex resume --last
```

但需在文件中明確說明：

- 跨帳號 Resume 屬於盡力支援。
- 不同帳號若屬於不同 Workspace、方案或模型權限，可能無法完整延續。
- 工具不能保證 OpenAI 未來版本仍允許跨帳號載入同一 Session。
- 即使對話無法 Resume，專案檔案、Git 狀態與工作目錄仍然存在。

---

## 4. 指令介面

### 4.1 `cx add <alias>`

用途：新增一個帳號。

範例：

```bash
cx add plus1
```

流程：

1. 驗證 alias。
2. alias 只允許：
   ```text
   英文字母、數字、底線、連字號
   ```
3. 若 alias 已存在，拒絕覆蓋，除非使用：
   ```bash
   cx add --force plus1
   ```
4. 使用獨立暫存 `CODEX_HOME` 執行登入：
   ```bash
   codex login --device-auth
   ```
5. 暫存環境應設定為使用檔案型認證儲存。
6. 登入成功後，將產生的 `auth.json` 複製到帳號目錄。
7. 清除暫存目錄。
8. 不要自動切換目前帳號，除非文件明確定義會切換。

建議登入時顯示：

```text
請在瀏覽器中確認登入的是 plus1 對應的 ChatGPT 帳號。
```

不要要求使用者將密碼或 Token 貼到命令列。

### 4.2 `cx list`

別名：

```bash
cx ls
```

用途：列出已保存帳號。

範例輸出：

```text
  company
* plus1
  plus2
```

`*` 表示目前帳號。

可以選擇顯示 Email 與方案，但不得因此讓整個指令變慢太多。若需要連線查詢，應放在 `cx status`，`cx list` 儘量只讀本機資料。

### 4.3 `cx use <alias>`

用途：切換目前帳號。

範例：

```bash
cx use company
```

成功輸出：

```text
目前 Codex 帳號：company
```

錯誤情況：

- alias 不存在
- auth.json 不存在
- auth.json 權限不安全
- `~/.codex` 無法寫入
- Codex CLI 未安裝

### 4.4 `cx current`

別名：

```bash
cx who
```

輸出目前帳號代號。

若沒有設定：

```text
目前尚未選擇帳號。
```

### 4.5 `cx status [alias]`

用途：

- 沒有 alias：查看全部帳號狀態、用量與推薦排序。
- 有 alias：只查看指定帳號狀態與用量，不顯示排序。

範例：

```bash
cx status
cx status plus1
```

查詢方式：

- 使用 Codex 官方 CLI 所提供的 App Server。
- 呼叫：
  ```text
  account/read
  account/rateLimits/read
  ```
- 每個帳號應在獨立暫存 `CODEX_HOME` 中查詢。
- 不要為了查用量而改動目前的 `~/.codex/auth.json`。
- 查詢結束後清除暫存目錄。
- 單一帳號查詢失敗，不應中止其他帳號查詢。
- 查全部帳號時，應依照「現在最適合使用」排序並顯示 Rank。

範例輸出：

```text
* plus1
  Rank: #1 (best choice now)
  Scope: work
  Email: user1@example.com
  Plan: plus
  5h: 42% used | reset 2026-06-17 18:20
  7d: 71% used | reset 2026-06-22 09:00

  company
  Rank: #2
  Scope: work
  Email: user2@example.com
  Plan: business
  5h: 10% used | reset 2026-06-17 17:40
```

時間應轉換為本機時區。

若 App Server 回傳欄位不同，程式應：

1. 容忍缺少欄位。
2. 顯示可取得的資料。
3. 不因一個未知欄位而崩潰。
4. 保留 `--debug` 模式方便檢查，但 debug 仍不得顯示 Token。

排序規則：

1. 先分狀態：
   ```text
   usable accounts > blocked accounts > error accounts
   ```
2. `usable` 定義：
   ```text
   5h used < 100 且 7d used < 100
   ```
3. `blocked` 定義：
   ```text
   5h used >= 100 或 7d used >= 100
   ```
4. 在 `usable` 帳號中：
   ```text
   work > personal
   ```
5. 同樣都是 `work`，或同樣都是 `personal` 時，用 `5h` 與 `7d` 的有效剩餘量排序。
6. 有效剩餘量需同時考慮目前剩餘百分比與 reset 遠近：
   ```text
   remaining = 100 - used_percent
   reset_proximity = clamp(1 - seconds_until_reset / window_seconds, 0, 1)
   effective_remaining = remaining + (100 - remaining) * reset_proximity
   ```
   `5h` 使用 5 小時視窗，`7d` 使用 7 天視窗。
7. `5h` 與 `7d` 的有效剩餘量應用瓶頸型分數合併，避免其中一個額度很低卻被另一個額度掩蓋。建議使用幾何分數：
   ```text
   score = 5h_effective ^ 0.62 * 7d_effective ^ 0.38
   ```
8. `blocked` 帳號排序時，先比較能重新可用的時間。若 `5h` 與 `7d` 同時 blocked，應使用兩者中較晚的 reset 時間作為 unblock 時間。
9. 額度已卡住的 `work` 不應排在可用的 `personal` 前面。

### 4.6 `cx best`

用途：依照 `cx status` 的完整排序規則，切換到目前 Rank #1 的帳號。

行為：

- 不接受 alias。
- 若沒有已保存帳號，顯示提示並回傳 0。
- 若所有帳號都無法讀取狀態，回傳非零並顯示錯誤。
- 應使用和 `cx status` 完全相同的排序規則。
- 切換成功後輸出選中的 alias、scope、email、plan 與可取得的用量資訊。

### 4.7 `cx scope <alias> <work|personal>`

用途：設定保存帳號的用途類型，影響 `cx status` 與 `cx best` 排序。

行為：

- `work` 表示公司或工作帳號。
- `personal` 表示私人帳號。
- 未設定時，預設應視為 `work`，符合「公司帳號可用時先用公司」的日常工作流。
- 可用的 `work` 應排在可用的 `personal` 前面。
- 額度已卡住的 `work` 不應排在可用的 `personal` 前面。

### 4.8 `cx remove <alias>`

用途：刪除保存的帳號憑證。

範例：

```bash
cx remove plus2
```

預設需要互動確認：

```text
確定刪除 plus2 的本機登入資料？[y/N]
```

支援：

```bash
cx remove --yes plus2
```

若刪除的是目前帳號：

- 清除 `current`。
- 不要自動刪除 `~/.codex/auth.json`，或應在規格中明確定義行為。
- 建議 MVP 保留 `~/.codex/auth.json`，但提醒目前標記已清除。

### 4.9 `cx export [alias...]`

用途：匯出全部或指定 alias 的本機登入資料。

範例：

```bash
cx export
cx export plus1 company
cx export --output ~/Downloads/cx-backup.tar.gz
```

行為：

- 產生單一 `.tar.gz` 備份檔。
- 內容包含：
  - `accounts/<alias>/auth.json`
  - `accounts/<alias>/meta.json`（若存在）
  - `current`（只有目前帳號也在匯出範圍內時才包含）
  - `manifest.json`
- 不包含：
  - `~/.codex/auth.json`
  - `tmp/`
  - `lock`
- 備份檔權限應為 `600`。
- 備份檔包含敏感登入憑證，不得提交到 Git。

### 4.10 `cx import <archive>`

用途：從備份檔還原全部或部分本機登入資料。

範例：

```bash
cx import ./cx-backup.tar.gz
cx import ./cx-backup.tar.gz --skip-existing
cx import ./cx-backup.tar.gz --force --set-current
```

行為：

- 預設若本機已存在同名 alias，直接停止並列出衝突。
- `--skip-existing`：略過已存在的 alias。
- `--force`：覆蓋已存在的 alias。
- `--set-current`：恢復備份中的 `current` 標記。
- 匯入時不得自動改寫 `~/.codex/auth.json`。
- `--force` 與 `--skip-existing` 不可同時使用。
- 必須驗證備份內容結構、alias 格式與必要檔案是否存在。

### 4.11 `cx manual`

用途：輸出一份以目前程式支援行為為準的操作手冊，內容同時給人與 AI 代理參考。

範例：

```bash
cx manual
cx manual --lang en
cx manual --format markdown
```

行為：

- 預設輸出繁體中文 Markdown。
- `--lang` 支援 `zh-TW` 與 `en`。
- `--format` 目前只支援 `markdown`。
- 不需要已登入帳號。
- 不讀取 app-server。
- 不修改任何本機帳號資料。
- 手冊內容必須以程式目前支援的子命令為準，不動態依賴 README 或本規格文件。

---

## 5. App Server 通訊需求

Codex App Server 使用 stdin/stdout 傳送 JSON 訊息。

程式至少要完成：

1. 啟動：
   ```bash
   codex app-server
   ```

補充：

- 以目前實作為準，`codex app-server` 直接使用預設 `stdio://` transport。
- 查詢各帳號狀態時，臨時 `CODEX_HOME` 應建立在 `~/.local/share/cx/tmp`，不要使用 `/tmp`。
2. 傳送 initialize。
3. 傳送 initialized。
4. 傳送：
   ```text
   account/read
   ```
5. 傳送：
   ```text
   account/rateLimits/read
   ```
6. 解析對應 request id 的回覆。
7. 設定逾時，例如 20～30 秒。
8. 正常終止子程序。
9. 若子程序未結束，強制終止。
10. 忽略無法解析的非 JSON 訊息，但在 `--debug` 可顯示摘要。

請先用目前安裝的 Codex CLI 驗證實際協定與欄位名稱，不要完全假設欄位永遠固定。

---

## 6. 安全要求

### 必須做到

- 不記錄密碼。
- 不要求使用者貼 Token。
- 不輸出 `auth.json` 內容。
- 不在錯誤訊息中輸出 Access Token 或 Refresh Token。
- `auth.json` 權限設為 `600`。
- 帳號資料目錄權限設為 `700`。
- 暫存目錄使用安全方式建立，例如：
  ```bash
  mktemp -d
  ```
- 程式結束時清除暫存資料。
- 使用 `trap` 處理中斷與異常退出。
- `.gitignore` 必須排除測試產生的憑證與暫存資料。

### 不支援

MVP 不需要支援：

- 同一時間在多個 Shell 中執行不同帳號的 Codex CLI。
- Windows 原生 PowerShell。
- GUI 帳號切換。
- 自動破解或繞過使用量限制。
- 從瀏覽器 Cookie 擷取登入資料。
- 從其他帳號偷取或匯入 Token。

文件中應提醒：此工具只用於管理使用者有權使用的帳號。

---

## 7. 建議專案結構

```text
codex-account-manager/
├── README.md
├── SPEC.md
├── LICENSE
├── .gitignore
├── bin/
│   └── cx
├── src/
│   └── cx.py
├── tests/
│   ├── test_alias.py
│   ├── test_account_store.py
│   ├── test_switch.py
│   ├── test_status_parser.py
│   └── test_status_sort.py
└── fixtures/
    ├── account_read.json
    └── rate_limits.json
```

建議架構：

- `bin/cx`
  - 很薄的 Bash 啟動器
  - 尋找 Python
  - 呼叫 `src/cx.py`
- `src/cx.py`
  - CLI 參數解析
  - 帳號管理
  - 權限檢查
  - App Server 查詢
  - 格式化輸出

也可全部寫成單一 Python 程式，但仍應保持模組化。

---

## 8. 安裝方式

預期支援：

```bash
./install.sh
```

安裝到：

```text
~/.local/bin/cx
```

若 `~/.local/bin` 不在 PATH，安裝程式應提示加入：

```bash
export PATH="$HOME/.local/bin:$PATH"
```

不要自動修改 `.bashrc`，除非提供明確選項：

```bash
./install.sh --update-path
```

---

## 9. 測試需求

至少包含以下測試。

### Alias 驗證

合法：

```text
plus1
company-account
work_01
```

不合法：

```text
../test
a/b
空字串
含空白
含 shell 特殊字元
```

### 帳號儲存

- 建立帳號目錄
- 權限為 `700`
- auth.json 權限為 `600`
- 已存在時不覆蓋
- `--force` 可安全覆蓋

### 切換

- 原子性替換 `~/.codex/auth.json`
- current 正確更新
- alias 不存在時不破壞目前登入
- 複製失敗時不留下半成品

### 用量解析

使用固定 fixture 測試：

- 一個視窗
- 兩個視窗
- 缺少 Plan
- 缺少 Email
- 缺少重置時間
- 未知欄位
- App Server 回傳 error
- 逾時
- 某一帳號失敗，其他帳號仍可顯示

### 狀態排序

使用固定時間測試：

- `7d` 已滿的 `work` 不應排在可用的 `work` 前面。
- 可用的 `work` 應排在可用的 `personal` 前面，即使 `personal` 的 reset 較近。
- 可用的 `personal` 應排在 `5h` 或 `7d` 已滿的 `work` 前面。
- 同一 scope 內，`5h` 剩餘較少但很快 reset 的帳號，可以排在剩餘較多但 reset 很晚的帳號前面。
- 同一 scope 內，`7d` 剩餘很少且 reset 很遠的帳號，應被瓶頸分數降權。
- blocked 帳號之間，應優先選較早重新可用的帳號。

### 安全

- 輸出不含 `access_token`
- 輸出不含 `refresh_token`
- debug 輸出也不含 Token
- auth.json 權限錯誤時會警告或修正

---

## 10. 驗收條件

完成後，以下流程必須成功：

```bash
cx add plus1
cx add plus2
cx list
cx status
cx use plus1
cx current
cx manual
cx export --output ./cx-backup.tar.gz
cx import ./cx-backup.tar.gz --skip-existing
```

另外：

```bash
cx status
```

必須做到：

- 不開啟互動式 Codex。
- 不修改目前選中的帳號。
- 不輸出 Token。
- 某個帳號失敗時仍顯示其他帳號。
- 回傳非零狀態碼的規則要合理且記錄在 README。

---

## 11. README 應包含

README 至少說明：

1. 工具用途。
2. 安裝方式。
3. 第一次加入帳號。
4. 切換帳號。
5. 查看用量。
6. Resume 的限制。
7. 憑證保存位置。
8. 如何移除帳號。
9. 如何完整解除安裝。
10. 安全注意事項。
11. 已知限制。
12. Codex CLI 版本相容性。

---

## 12. Codex 實作指示

請依以下順序執行：

1. 先檢查本機：
   ```bash
   codex --version
   codex login --help
   codex app-server --help
   ```
2. 驗證目前版本的登入資料位置。
3. 驗證 App Server 實際 JSON-RPC 或 JSONL 格式。
4. 先完成 `add`、`list`、`use`、`current`。
5. 再完成 `status`。
6. 寫測試。
7. 寫安裝程式與 README。
8. 用假資料測試解析器。
9. 最後才用真實帳號做整合測試。
10. 不要把任何真實 `auth.json` 加入 Git。

開發過程中，若實際 Codex CLI 行為與本規格不同：

- 以本機實測為準。
- 將差異記錄在 README 的「版本相容性」。
- 不要為了符合規格而使用不安全的 Token 操作。
- 不確定時先保留安全且簡單的行為。
