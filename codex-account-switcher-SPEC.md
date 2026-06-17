# Codex CLI 多帳號切換與用量查詢工具規格

## 1. 專案目的

製作一個在 WSL／Linux 下使用的命令列工具 `cx`，用來管理多個 Codex CLI 帳號。

主要需求：

1. 每個帳號只需要登入一次。
2. 可以替帳號設定簡短代號，例如 `plus1`、`plus2`、`company`。
3. 可以快速查看所有帳號的 Codex 用量。
4. 可以選擇目前要使用的帳號。
5. 切換帳號後，盡量保留原本 Codex CLI 的本機交談紀錄與 `resume` 能力。
6. 不把 Token、密碼或完整登入資料顯示在畫面上。
7. 操作方式要簡單，適合日常頻繁切換。

預期操作：

```bash
cx add plus1
cx add plus2
cx usage
cx use plus2
cx
cx resume --last
```

---

## 2. 執行環境

主要環境：

- Windows 11
- WSL2
- Ubuntu
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
- `codex resume`
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
│   │   └── auth.json
│   ├── plus2/
│   │   └── auth.json
│   └── company/
│       └── auth.json
├── current
└── lock
```

權限要求：

```text
~/.local/share/cx                 700
~/.local/share/cx/accounts        700
各帳號目錄                        700
auth.json                         600
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
5. 執行 `codex login status` 做基本確認。
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

切換帳號後應可嘗試：

```bash
cx resume --last
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

可以選擇顯示 Email 與方案，但不得因此讓整個指令變慢太多。若需要連線查詢，應放在 `cx usage`，`cx list` 儘量只讀本機資料。

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

### 4.5 `cx usage [alias]`

用途：

- 沒有 alias：查看全部帳號用量。
- 有 alias：只查看指定帳號。

範例：

```bash
cx usage
cx usage plus1
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

範例輸出：

```text
* plus1
  Email: user1@example.com
  Plan: plus
  5 小時視窗
    已用：42%
    剩餘：58%
    重置：2026-06-17 18:20
  7 天視窗
    已用：71%
    剩餘：29%
    重置：2026-06-22 09:00

  company
  Email: user2@example.com
  Plan: business
  5 小時視窗
    已用：10%
    剩餘：90%
    重置：2026-06-17 17:40
```

時間應轉換為本機時區。

若 App Server 回傳欄位不同，程式應：

1. 容忍缺少欄位。
2. 顯示可取得的資料。
3. 不因一個未知欄位而崩潰。
4. 保留 `--debug` 模式方便檢查，但 debug 仍不得顯示 Token。

### 4.6 `cx remove <alias>`

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

### 4.7 `cx login <alias>`

用途：重新登入或更新某帳號的登入憑證。

等同重新執行：

```bash
cx add --force <alias>
```

### 4.8 `cx doctor`

檢查項目：

- `codex` 是否存在
- `python3` 是否存在
- `codex app-server --help` 是否可執行
- `~/.codex` 權限
- cx 資料目錄權限
- 各帳號 `auth.json` 是否存在
- `auth.json` 是否為 `600`
- `current` 所指帳號是否存在

不得顯示 Token。

### 4.9 其他參數直接轉交 Codex

當第一個參數不是 cx 自有子命令時，直接執行 Codex CLI。

例如：

```bash
cx
cx resume
cx resume --last
cx --help
cx exec "分析這個專案"
```

行為：

1. 確認已有目前帳號。
2. 確認目前帳號憑證已同步至 `~/.codex/auth.json`。
3. 執行：
   ```bash
   exec codex "$@"
   ```

因此：

```bash
cx resume --last
```

等同：

```bash
codex resume --last
```

但執行前會先確保使用正確帳號。

---

## 5. App Server 通訊需求

Codex App Server 使用 stdin/stdout 傳送 JSON 訊息。

程式至少要完成：

1. 啟動：
   ```bash
   codex app-server
   ```
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
codex-account-switcher/
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
│   └── test_usage_parser.py
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

### 安全

- 輸出不含 `access_token`
- 輸出不含 `refresh_token`
- debug 輸出也不含 Token
- auth.json 權限錯誤時會警告或修正

---

## 10. 驗收條件

完成後，以下流程必須成功：

```bash
cx doctor
cx add plus1
cx add plus2
cx list
cx usage
cx use plus1
cx current
cx
```

進入 Codex 後建立一個 Session，退出並切換：

```bash
cx use plus2
cx resume
```

至少應能看到原本本機 Session，或在文件中清楚說明目前 Codex 版本的限制。

另外：

```bash
cx usage
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
4. 先完成 `doctor`、`add`、`list`、`use`、`current`。
5. 再完成 `usage`。
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
