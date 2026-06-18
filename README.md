# cx

`cx` 是一個建立在 Codex CLI 之上的小工具，用來保存多個 Codex 帳號登入狀態，並且幫你快速判斷現在該切到哪一個帳號。

目前這個分支先支援 CLI。
Linux / macOS / WSL 可以用 shell 腳本安裝，Windows 則支援原生 PowerShell 安裝。
UI 版不在這一版範圍內。

## 這次重大變更

- 新增原生 Windows PowerShell 支援，可直接用 `install.ps1` / `uninstall.ps1` 安裝與移除
- 新增 Windows 啟動包裝 `bin/cx.cmd`，讓 `cx` 可以在一般 `cmd` / PowerShell 環境執行
- 補齊 Windows 路徑與資料目錄處理，已保存帳號、暫存目錄、安裝位置都會落在 `%LOCALAPPDATA%`
- `cx status` 已對齊新版 Codex CLI 的 `codex app-server` 行為，並補上對應測試
- README 追加跨環境 auth 切換說明，明確區分 WSL 與 Windows 原生環境各自使用的 `auth.json`

它適合這幾種情境：

- 你手上有多個 Codex 帳號，想要用別名整理起來
- 你會在公司帳號和私人帳號之間切換
- 你想先看各帳號的剩餘額度，再決定用哪個
- 你不想每次都重新登入或手動搬 `auth.json`

預設策略：

- 先排除目前已被 `5h` 或 `7d` 額度卡住的帳號
- 可用的公司帳號 `work` 會排在可用的私人帳號 `personal` 前面
- 同一類型帳號之間，再綜合比較 `5h`、`7d` 的剩餘量與 reset 時間

## 使用前提

`cx` 不是獨立的登入工具，它是依賴 Codex CLI 運作的。

你需要先有：

- 已安裝 `codex` 指令
- 至少可以正常執行一次 `codex login`
- 如果要用 `cx add`，你的 Codex CLI 需要支援 `codex login --device-auth`

如果你還沒安裝 Codex CLI，可以先安裝它，再回來安裝 `cx`。
本文最後有附上安裝提醒。

## 30 秒快速開始

如果你已經安裝好 Codex CLI，可以直接照這個流程跑。

Linux / macOS / WSL：

```bash
./install.sh
cx add company
cx add personal
cx status
cx use company
```

Windows PowerShell：

```powershell
.\install.ps1
cx add company
cx add personal
cx status
cx use company
```

這個流程做的事是：

- 安裝 `cx`
- 保存兩個帳號
- `cx add` 期間會叫你在瀏覽器完成 Codex 的登入授權
- 查看目前排序
- 切到你現在要用的帳號

Linux / macOS / WSL 如果安裝後出現 `cx: command not found`，通常是 `~/.local/bin` 還沒進到 `PATH`。
`./install.sh` 會詢問你是否把設定加進 `~/.profile`；如果你有加，接著執行：

```bash
source ~/.profile
```

如果不想手動 `source`，重新登入 shell 也可以。

## 安裝

Linux / macOS / WSL：

```bash
./install.sh
```

Windows PowerShell：

```powershell
.\install.ps1
```

Linux / macOS / WSL 解除安裝：

```bash
./uninstall.sh
```

Windows PowerShell 解除安裝：

```powershell
.\uninstall.ps1
```

如果你要連保存的帳號資料一起刪除：

```bash
./uninstall.sh --purge-data
```

```powershell
.\uninstall.ps1 --purge-data
```

安裝完成後，`cx` 會放在：

```text
Linux / macOS / WSL: ~/.local/bin/cx
Windows: %LOCALAPPDATA%\Programs\cx\bin\cx.cmd
```

主程式會安裝到：

```text
Linux / macOS / WSL: ~/.local/share/cx/app/cx.py
Windows: %LOCALAPPDATA%\cx\app\cx.py
```

如果 `~/.local/bin` 還沒有在 `PATH` 裡，`./install.sh` 會詢問你是否要把下面這行加到 `~/.profile`：

```bash
export PATH="$HOME/.local/bin:$PATH"
```

## 功能重點

- 把多個 Codex 帳號保存成別名
- 快速切換目前要使用的帳號
- 匯出或匯入已保存帳號備份
- 一次查詢所有已保存帳號的狀態
- 查詢時不改動目前正在使用的帳號
- 可以把帳號標成 `work` 或 `personal`
- `cx best` 可以直接切到目前最適合的帳號

## 使用流程

### 情境 1：第一次把多個帳號整理進來

如果你有公司帳號、私人帳號，或多個不同方案的帳號，第一步通常是先把它們收進 `cx`。

做法有兩種：

- 還沒登入該帳號：用 `cx add <alias>`
- 已經先用 Codex CLI 登入好了：用 `cx save <alias>`
- 要搬到另一台機器：用 `cx export` 匯出，再用 `cx import` 匯入
- 不再需要某個已保存帳號：用 `cx remove <alias>`

範例：

```bash
cx add company
cx add side-project
cx save temp-account
cx export --output ~/Downloads/cx-backup.tar.gz
cx remove old-account
```

整理完之後，建議立刻標記哪些是公司帳號、哪些是私人帳號：

```bash
cx scope company work
cx scope side-project personal
cx scope temp-account personal
```

然後確認目前保存了哪些帳號：

```bash
cx list
```

### 情境 2：開始工作前，先看現在該用哪個帳號

如果你不確定現在哪個帳號剩最多額度，先跑：

```bash
cx status
```

`cx status` 會列出全部帳號，並依照目前推薦順序排序。  
目前規則會先看帳號是否可用；可用的 `work` 會先於可用的 `personal`，同一類型內再比較 `5h`、`7d` 的剩餘量與 reset 時間。

如果你想直接切到推薦第一名：

```bash
cx best
```

如果你只想看某一個帳號：

```bash
cx status company
```

### 情境 3：你已經知道要用哪個帳號，直接手動切換

有時候你不是要最省額度，而是明確知道這次要用哪個環境，例如要處理公司專案、或要用私人帳號做測試。這時直接切就好：

```bash
cx use company
cx current
codex
```

`cx use <alias>` 會把該帳號的憑證寫到 `CODEX_HOME/auth.json`，如果你沒有自訂 `CODEX_HOME`，預設就是 `~/.codex/auth.json`。之後你直接執行 `codex` 就會用那個帳號。

注意：

- `cx` 只會影響你目前這個執行環境看到的 `CODEX_HOME/auth.json`
- 如果你是在 WSL 內執行 `cx use`，它切換的是 WSL 內的 `~/.codex/auth.json`
- Windows 原生 VS Code 裡的 Codex 擴充功能，通常使用的是 Windows 那一側自己的登入狀態，不會跟著 WSL 內的 `cx use` 一起切換
- 反過來說，Windows PowerShell 版的 `cx` 也只會影響 Windows 那一側的 Codex CLI / auth 狀態
- 如果你是用 VS Code 的 Remote - WSL，把工作區連到 WSL，該視窗內若實際呼叫的是 WSL 裡的 `codex`，就會受到 WSL 這份 `auth.json` 影響

### 情境 4：把已保存帳號搬到另一台電腦

公司電腦先匯出：

```bash
cx export
cx export --output ~/Downloads/cx-backup.tar.gz
cx export michaelpo foya_co01
cx export --alias michaelpo,foya_co01
cx export --email michaelpo@example.com
```

把備份檔帶到另一台機器後再匯入：

```bash
cx backup-list ~/Downloads/cx-backup.tar.gz
cx import ~/Downloads/cx-backup.tar.gz
cx import ~/Downloads/cx-backup.tar.gz --email michaelpo@example.com
cx import ~/Downloads/cx-backup.tar.gz --set-current
```

預設如果本機已經有同名 alias，`cx import` 會直接停止並列出衝突帳號。  
你可以改用 `--skip-existing` 或 `--force` 決定怎麼處理。

## 指令參考

### `cx add <alias>`

用 `codex login --device-auth` 登入新帳號，並把這個帳號保存成指定別名。

這裡的 `<alias>` 是你自己取的帳號別名，只是方便你辨識，不是 Codex 固定值。
你可以隨便取名，但建議一看就知道這是什麼帳號，例如 `company`、`personal`、`client-a`、`side-project`。

執行時大致會經過這些步驟：

- 終端機會顯示一個登入網址，通常也會附一組 device code
- 你需要在瀏覽器打開那個網址
- 在瀏覽器登入你要保存的那個 Codex 帳號，必要時貼上 device code
- 瀏覽器授權完成後，回到終端機等待 `cx add` 自動收尾
- 成功後，該帳號會被保存成你指定的 `<alias>`

範例：

```bash
cx add plus1
cx add company
cx add --force plus1
```

說明：

- 第一次加入帳號時使用
- `--force` 會覆蓋原本同名的帳號資料
- 別名只允許英文字母、數字、底線 `_`、連字號 `-`

### `cx save <alias>`

把目前 `CODEX_HOME/auth.json` 對應的登入狀態直接保存成一個別名。

範例：

```bash
cx save plus1
cx save team2
cx save --force plus1
```

說明：

- 適合你已經先用 `codex` 登入好，再把當前帳號收進 `cx`
- `--force` 會覆蓋原本同名的帳號資料

### `cx list`

列出所有已保存的帳號別名。

範例：

```bash
cx list
cx ls
```

可能輸出：

```text
* plus1 [work]
  plus2 [personal]
  company [work]
```

說明：

- `*` 代表目前選中的帳號

### `cx export [alias...]`

把全部已保存帳號，或依 alias / email 篩選後，匯出成 `.tar.gz` 備份檔。

範例：

```bash
cx export
cx export michaelpo foya_co01
cx export --alias michaelpo,foya_co01
cx export --alias michaelpo --alias foya_co01
cx export --email michaelpo@example.com
cx export --alias work1 --email michaelpo@example.com
cx export --output ~/Downloads/cx-backup.tar.gz
```

說明：

- 不指定 alias 時會匯出全部帳號
- `--alias` 支援重複傳入，也支援用逗號分隔多個 alias
- `--email` 支援重複傳入，也支援用逗號分隔多個 email
- `--alias` 和 `--email` 可以同時使用；命中結果會做聯集
- `--email` 若命中多筆帳號，會全部匯出並列出命中項
- 預設輸出檔名類似 `cx-backup-20260618-231500.tar.gz`
- 備份內容包含各 alias 的 `auth.json`、`meta.json`、可選的 `current`，以及每個帳號的摘要資訊（例如 email、scope、plan）
- 不會包含目前正在使用的 `CODEX_HOME/auth.json`
- 備份檔內含敏感登入憑證，請妥善保管

### `cx import <archive>`

從 `.tar.gz` 備份檔匯入已保存帳號。

範例：

```bash
cx backup-list ./cx-backup.tar.gz
cx import ./cx-backup.tar.gz
cx import ./cx-backup.tar.gz --alias michaelpo,foya_co01
cx import ./cx-backup.tar.gz --email michaelpo@example.com
cx import ./cx-backup.tar.gz --skip-existing
cx import ./cx-backup.tar.gz --force --set-current
```

說明：

- `cx backup-list` 可以先查看備份裡有哪些帳號摘要，再決定要匯入哪些 alias / email
- `--alias` 支援重複傳入，也支援用逗號分隔多個 alias
- `--email` 支援重複傳入，也支援用逗號分隔多個 email
- `--alias` 和 `--email` 可以同時使用；命中結果會做聯集
- `--email` 若命中多筆帳號，會全部匯入並列出命中項
- 預設遇到同名 alias 會停止並列出衝突
- `--skip-existing` 會略過本機已存在的 alias
- `--force` 會覆蓋本機已存在的 alias
- `--set-current` 只會在目前選到的匯入集合包含備份中的 current alias 時恢復目前帳號標記
- 匯入時不會自動改寫目前正在使用的 `CODEX_HOME/auth.json`
- `--force` 和 `--skip-existing` 不能同時使用

### `cx backup-list <archive>`

查看備份檔裡包含哪些帳號摘要。

範例：

```bash
cx backup-list ./cx-backup.tar.gz
```

可能輸出：

```text
  company | company@example.com | work | business
* personal | me@example.com | personal | plus
```

說明：

- 會列出 alias、email、scope、plan
- `*` 代表這個 alias 是該備份中的 current 帳號
- 舊版備份若沒有帳號摘要，`cx backup-list` 會盡量從備份裡的 `auth.json` / `meta.json` 推導出摘要資訊

### `cx use <alias>`

切換目前使用的 Codex 帳號。

範例：

```bash
cx use plus1
cx use company
```

說明：

- 這會把該帳號的憑證寫到 `CODEX_HOME/auth.json`
- 切換成功後，之後直接執行 `codex` 就會用這個帳號
- 只會切換目前執行環境的 Codex CLI 憑證；不保證同步切到另一個作業系統環境或另一份 VS Code 擴充功能登入狀態

### `cx current`

顯示目前選中的帳號別名。

範例：

```bash
cx current
cx who
```

### `cx status [alias]`

查詢全部已保存帳號，或只查單一帳號的狀態與用量。
查全部時，會自動依照「現在最值得切換去用」的順序排序。

範例：

```bash
cx status
cx status plus1
```

可能輸出：

```text
* plus1
  Rank: #1 (best choice now)
  Scope: work
  Email: user1@example.com
  Plan: plus
  5h: 10% used | reset 2026-06-17 18:20
  7d: 31% used | reset 2026-06-22 09:00

  company
  Rank: #2
  Scope: work
  Email: user2@example.com
  Plan: business
  5h: 42% used | reset 2026-06-17 17:40
```

說明：

- `cx status` 會逐一讀取所有已保存帳號
- 可以用 `cx scope` 把帳號標成 `work` 或 `personal`
- 查全部帳號時，會先把目前可用的帳號排在已卡住的帳號前面
- 可用的 `work` 會排在可用的 `personal` 前面
- 排序會同時考慮 `5h` 與 `7d` 的剩餘量、reset 時間，以及 reset 是否快到了
- 額度已卡住的 `work` 不會排到可用的 `personal` 前面
- 查詢過程使用獨立暫存 `CODEX_HOME`
- 不會改掉你目前選中的帳號
- 不會輸出 token 內容

### `cx best`

自動找出目前最適合使用的帳號，並直接切換過去。
排序規則和 `cx status` 完全一致。
如果有可用的 `work` 帳號，`cx best` 會先從公司帳號裡挑。
只有公司帳號都被額度卡住時，可用的 `personal` 才會排到前面。

範例：

```bash
cx best
```

可能輸出：

```text
已切換到最佳帳號：plus1
Scope: work
Email: user1@example.com
Plan: plus
5h: 10% used | reset 2026-06-17 18:20
7d: 31% used | reset 2026-06-22 09:00
```

### `cx scope <alias> <work|personal>`

設定帳號類型。可用的 `work` 會在排序時優先於可用的 `personal`。

範例：

```bash
cx scope pomichael personal
cx scope foya_co01 work
```

### `cx remove <alias>`

刪除已保存的帳號憑證。預設會先要求確認。

範例：

```bash
cx remove old-account
cx remove --yes old-account
```

說明：

- 只會刪除 `cx` 的已保存帳號資料
- 如果刪除的是目前帳號，會一併清除 `cx` 的 current 標記
- 不會自動刪除 `CODEX_HOME/auth.json`，避免把你目前的 Codex CLI 登入狀態直接清掉

## 資料保存位置

- Linux / macOS / WSL
- 帳號憑證：`~/.local/share/cx/accounts/<alias>/auth.json`
- 目前選中的帳號：`~/.local/share/cx/current`
- 臨時查詢目錄：`~/.local/share/cx/tmp`
- Windows
- 帳號憑證：`%LOCALAPPDATA%\cx\accounts\<alias>\auth.json`
- 目前選中的帳號：`%LOCALAPPDATA%\cx\current`
- 臨時查詢目錄：`%LOCALAPPDATA%\cx\tmp`

## 解除安裝說明

- Linux / macOS / WSL 使用 `./uninstall.sh`
- Windows 使用 `.\uninstall.ps1`
- 已保存的帳號資料預設會保留
- 如果要連帳號資料一起刪除，使用 `--purge-data`

## 注意事項

- `cx status` 透過 `codex app-server` 查詢帳號資訊與 rate limit
- `cx status` 會使用 `cx` 專用資料目錄下的獨立暫存 `CODEX_HOME`
- 本工具不會顯示 `auth.json` 內容，也不會顯示 access token
- `cx add` 需要你的本機 Codex CLI 支援 `codex login --device-auth`
- 備份檔包含登入憑證，請不要放進 Git 或公開雲端空間

## 版本相容性

- 目前這個分支支援 CLI；UI 版留到下一版
- CLI 支援 Linux / macOS / WSL 與原生 Windows PowerShell
- `cx status` 目前相容 `codex app-server` 預設使用 `stdio://` 的新版 CLI
- 臨時 `CODEX_HOME` 會建立在 `cx` 自己的 `tmp` 目錄，避免新版 Codex 拒絕系統暫存路徑
- `cx export` / `cx import` 使用 Python 內建 `tarfile`，不依賴系統的 `tar` 指令

## Codex CLI 安裝提醒

如果你還沒有 `codex` 指令，請先安裝 Codex CLI，再執行這個 repo 的安裝腳本。

官方文件：

- Codex CLI overview: <https://developers.openai.com/codex/cli>
- Codex quickstart: <https://developers.openai.com/codex/quickstart>

官方文件目前提供的常見安裝方式包含：

```bash
curl -fsSL https://chatgpt.com/codex/install.sh | sh
```

你也可以依照官方文件改用 `npm` 或 `Homebrew` 安裝。

安裝順序建議是：

1. 先安裝 Codex CLI
2. 確認 `codex login` 可以正常使用
3. 再回到這個 repo 執行 `./install.sh` 或 `.\install.ps1`
4. 最後用 `cx add` 或 `cx save` 把帳號收進來
