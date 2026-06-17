# cx

`cx` 是一個建立在 Codex CLI 之上的小工具，用來保存多個 Codex 帳號登入狀態，並且幫你快速判斷現在該切到哪一個帳號。

它適合這幾種情境：

- 你手上有多個 Codex 帳號，想要用別名整理起來
- 你會在公司帳號和私人帳號之間切換
- 你想先看各帳號的剩餘額度，再決定用哪個
- 你不想每次都重新登入或手動搬 `auth.json`

預設策略：

- 公司帳號 `work` 優先，私人帳號 `personal` 其次
- 同類型帳號之間，再比較 `5h` 和 `7d` 用量

## 使用前提

`cx` 不是獨立的登入工具，它是依賴 Codex CLI 運作的。

你需要先有：

- 已安裝 `codex` 指令
- 至少可以正常執行一次 `codex login`
- 如果要用 `cx add`，你的 Codex CLI 需要支援 `codex login --device-auth`

如果你還沒安裝 Codex CLI，可以先安裝它，再回來安裝 `cx`。
本文最後有附上安裝提醒。

## 30 秒快速開始

如果你已經安裝好 Codex CLI，可以直接照這個流程跑：

```bash
./install.sh
cx add company
cx add personal
cx scope company work
cx scope personal personal
cx status
cx best
```

這個流程做的事是：

- 安裝 `cx`
- 保存兩個帳號
- 標記哪個是公司帳號、哪個是私人帳號
- 查看目前排序
- 直接切到目前最適合的帳號

## 安裝

在 repo 目錄執行：

```bash
./install.sh
```

解除安裝：

```bash
./uninstall.sh
```

如果你要連保存的帳號資料一起刪除：

```bash
./uninstall.sh --purge-data
```

安裝完成後，`cx` 會放在：

```text
~/.local/bin/cx
```

主程式會安裝到：

```text
~/.local/share/cx/app/cx.py
```

如果 `~/.local/bin` 還沒有在 `PATH` 裡，`./install.sh` 會詢問你是否要把下面這行加到 `~/.profile`：

```bash
export PATH="$HOME/.local/bin:$PATH"
```

## 功能重點

- 把多個 Codex 帳號保存成別名
- 快速切換目前要使用的帳號
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

範例：

```bash
cx add company
cx add side-project
cx save temp-account
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
目前規則是先偏好 `work` 帳號，再比較 `5h` 和 `7d` 用量。

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

`cx use <alias>` 會把該帳號的憑證寫到 `~/.codex/auth.json`，之後你直接執行 `codex` 就會用那個帳號。

## 指令參考

### `cx add <alias>`

用 `codex login --device-auth` 登入新帳號，並把這個帳號保存成指定別名。

這裡的 `<alias>` 是你自己取的帳號別名，只是方便你辨識，不是 Codex 固定值。

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

把目前 `~/.codex/auth.json` 對應的登入狀態直接保存成一個別名。

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
* plus1
  plus2
  company
```

說明：

- `*` 代表目前選中的帳號

### `cx use <alias>`

切換目前使用的 Codex 帳號。

範例：

```bash
cx use plus1
cx use company
```

說明：

- 這會把該帳號的憑證寫到 `~/.codex/auth.json`
- 切換成功後，之後直接執行 `codex` 就會用這個帳號

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
- 查全部帳號時，會先優先 `work`，再比較 `5h` 剩餘額度與 `7d`
- 如果某個額度已經用滿，會把 reset 時間一起納入排序
- 查詢過程使用獨立暫存 `CODEX_HOME`
- 不會改掉你目前選中的帳號
- 不會輸出 token 內容

### `cx best`

自動找出目前最適合使用的帳號，並直接切換過去。
排序規則和 `cx status` 完全一致。
如果你有把帳號標成 `personal`，`cx best` 會優先選 `work` 帳號。
也就是說，預設情況下會先從公司帳號裡挑最適合的，再輪到私人帳號。

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

設定帳號類型。`work` 會在排序時優先於 `personal`。

範例：

```bash
cx scope pomichael personal
cx scope foya_co01 work
```

## 資料保存位置

- 帳號憑證：`~/.local/share/cx/accounts/<alias>/auth.json`
- 目前選中的帳號：`~/.local/share/cx/current`

## 解除安裝說明

- `./uninstall.sh` 只會移除 `~/.local/bin/cx` 和 `~/.local/share/cx/app`
- 已保存的帳號資料預設會保留
- 如果要連帳號資料一起刪除，使用 `./uninstall.sh --purge-data`

## 注意事項

- `cx status` 透過 `codex app-server` 查詢帳號資訊與 rate limit
- 本工具不會顯示 `auth.json` 內容，也不會顯示 access token
- `cx add` 需要你的本機 Codex CLI 支援 `codex login --device-auth`

## Codex CLI 安裝提醒

如果你還沒有 `codex` 指令，請先安裝 Codex CLI，再使用這個 repo 的 `./install.sh`。

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
3. 再回到這個 repo 執行 `./install.sh`
4. 最後用 `cx add` 或 `cx save` 把帳號收進來
