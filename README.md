# cx

`cx` 是一個簡單的命令列工具，用來保存多個 Codex 帳號登入狀態，並且用一個指令查出所有已註冊帳號的用量狀態。

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

## 指令

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

## 常見流程

第一次整理帳號：

```bash
cx add plus1
cx add plus2
cx add company
cx scope plus1 personal
cx scope plus2 personal
cx scope company work
cx list
```

查看全部帳號狀態：

```bash
cx status
```

直接切到目前最值得用的帳號：

```bash
cx best
cx current
codex
```

或手動選一個剩餘額度比較多的帳號來用：

```bash
cx use plus2
cx current
codex
```

如果你已經先手動登入過 `codex`：

```bash
codex login
cx save plus3
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
