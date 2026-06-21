# CR-007: CLI renew 重新登入既有 alias

Status: Completed

## 1. 背景

目前 `cx add <alias> --force` 可以強制覆寫已保存帳號，但它的語意是「以指定 alias 保存這次登入結果」，不會檢查這次登入的帳號是否與原 alias 代表的帳號一致。

當某個 alias 的 OAuth token revoked、expired、或 app-server 回傳 401 時，使用者通常只是想重新登入同一個帳號並更新 token。若使用 `remove` 後再 `add`，或直接用 `add --force`，都有兩個風險：

1. alias 打錯時可能新增或覆寫錯誤 alias。
2. 瀏覽器登入錯 account 時，可能把 alias 改成另一個帳號。

本 CR 新增一個保守、安全的 CLI 指令，用來重新登入既有 alias，並在覆寫前確認新舊帳號 identity 一致。

## 2. 目標

1. 新增 CLI 指令：

```bash
cx renew <alias>
```

2. `renew` 只允許針對已存在的單一 alias 執行。
3. `renew` 必須重新執行 Codex device login，取得新的 `auth.json`。
4. 覆寫既有 alias 前，必須比對舊 auth 與新 auth 代表同一個 account。
5. 第一版 identity gate 以 `email` 為必要比對條件。
6. 若 alias 不存在、舊 auth 無法解析 email、新 auth 無法解析 email、或新舊 email 不一致，必須拒絕覆寫。
7. `renew` 成功時必須保留該 alias 既有 metadata，例如 `scope`。
8. 若該 alias 是 current alias，`renew` 成功後必須同步更新目前 active `CODEX_HOME/auth.json`。
9. `renew` 應使用和 `add` 相同的登入流程與暫存 `CODEX_HOME` 機制。
10. `renew` 的錯誤訊息必須清楚指出失敗原因，避免使用者誤以為已更新 token。

## 3. 非目標

本 CR 不做以下事項：

1. 不改變 `cx add` 的既有語意。
2. 不移除 `cx add --force`。
3. 不讓 `renew` 支援多 alias。
4. 不讓 `renew` 支援 `--force`。
5. 不新增遠端服務或新的授權流程。
6. 不改 backup archive 格式。
7. 不要求立即新增 GUI；GUI 另由 CR-008 規範。
8. 不把 account identity cache 正式寫入 `meta.json`，除非實作時另行確認不會破壞 `scope` 讀寫相容性。

## 4. 指令規格

### 4.1 Usage

```bash
cx renew <alias>
```

範例：

```bash
cx renew company
cx renew foya_co01
```

### 4.2 行為摘要

```text
cx renew <alias>

1. 驗證 alias 格式。
2. 確認 accounts/<alias>/auth.json 存在。
3. 從既有 auth.json 解析 old_email。
4. 建立暫時 CODEX_HOME。
5. 執行 codex login --device-auth。
6. 登入完成後，從暫時 CODEX_HOME/auth.json 解析 new_email。
7. 比對 old_email 與 new_email。
8. email 一致才覆寫 accounts/<alias>/auth.json。
9. 若 alias 是 current alias，同步覆寫 CODEX_HOME/auth.json。
10. 清理暫存目錄。
```

### 4.3 成功訊息

建議輸出：

```text
已更新帳號 token：company
Email: user@example.com
```

若該 alias 是 current alias，追加：

```text
已同步更新目前 Codex 帳號。
```

### 4.4 失敗條件與錯誤訊息

alias 不存在：

```text
找不到帳號 `company`；renew 只支援已存在的 alias。
```

舊 auth 不存在：

```text
找不到帳號 `company` 的既有 auth.json，無法 renew。
```

舊 auth 解析不到 email：

```text
帳號 `company` 的既有 auth.json 無法識別 email，為避免覆寫錯帳號，已取消 renew。
```

新 auth 解析不到 email：

```text
新的登入結果無法識別 email，為避免覆寫錯帳號，已取消 renew。
```

新舊 email 不一致：

```text
登入帳號不一致，已取消 renew。
Alias: company
Expected: old@example.com
Actual: new@example.com
```

Codex login 失敗：

```text
`codex login --device-auth` 失敗，退出碼 <code>
```

### 4.5 不支援 `--force`

`renew` 的核心價值是「安全覆寫」。因此第一版不提供：

```bash
cx renew <alias> --force
```

若使用者明確想把 alias 改成另一個帳號，應使用既有指令：

```bash
cx add <alias> --force
```

這樣可讓兩個操作保持清楚分工：

```text
add --force = 我知道我要用這次登入結果覆寫 alias，不要求同一帳號。
renew      = 我只想更新既有 alias 的 token，而且必須是同一帳號。
```

## 5. Identity 比對規則

### 5.1 第一版必要條件

第一版以 email 作為 hard gate：

```text
old_email 必須存在
new_email 必須存在
old_email == new_email
```

不符合任一條件即拒絕覆寫。

### 5.2 未來擴充

若未來確認 Codex auth payload 中存在更穩定的 account id，可將 identity extraction 擴充為：

```text
preferred identity: account id / subject id
fallback identity: email
```

但本 CR 第一版不要求使用尚未確認穩定性的欄位，避免誤判。

## 6. Current alias 同步規則

若 `read_current_alias()` 等於 renew 目標 alias，成功覆寫 saved account 後，必須同步 active auth：

```text
accounts/<alias>/auth.json -> CODEX_HOME/auth.json
```

理由：使用者 renew 目前正在使用的帳號時，預期 renew 完成後立刻恢復可用。如果只更新 saved copy，不更新 active `CODEX_HOME/auth.json`，接下來執行 Codex CLI 仍可能使用舊 token。

若 current alias 不是 renew 目標 alias，則不改 active `CODEX_HOME/auth.json`。

## 7. Metadata 保留規則

`renew` 成功時只覆寫：

```text
accounts/<alias>/auth.json
```

不得刪除或重建整個 alias directory，以避免遺失：

```text
accounts/<alias>/meta.json
```

尤其 `scope` 必須保留。

## 8. 實作建議

### 8.1 抽出共用登入 helper

目前 `cmd_add()` 內部已包含 device login、暫存 `CODEX_HOME`、讀取 temp auth、清理暫存目錄等流程。建議抽出 helper，供 `cmd_add()` 與 `cmd_renew()` 共用。

建議函式方向：

```python
def login_to_temp_auth(alias: str, *, temp_prefix: str) -> Path:
    ...
```

或：

```python
def run_device_login_to_temp_home(alias: str, *, temp_prefix: str) -> tuple[Path, Path]:
    ...
```

實作時需確保 temp directory 在 finally 中清理。

### 8.2 抽出 identity helper

現有程式已有從 auth bytes 解析 `email` / `plan` 的 helper。建議新增明確語意的 wrapper：

```python
def read_auth_email(auth_file: Path) -> str | None:
    ...
```

或：

```python
def read_auth_identity(auth_file: Path) -> AuthIdentity:
    ...
```

若使用 dataclass，第一版可只包含：

```python
@dataclass
class AuthIdentity:
    email: str | None
```

### 8.3 Parser 與 manual

`MANUAL_COMMANDS` 應新增：

```python
("renew", "cx renew <alias>")
```

`build_parser()` 應新增 subparser：

```python
renew_parser = subparsers.add_parser("renew", help="Re-login and safely update an existing account token")
renew_parser.add_argument("alias")
renew_parser.set_defaults(func=cmd_renew)
```

## 9. 測試規格

至少新增或更新以下測試：

1. `cx renew missing_alias`：alias 不存在時失敗，不建立新目錄。
2. 舊 auth email 與新 auth email 相同：成功覆寫 `accounts/<alias>/auth.json`。
3. 舊 auth email 與新 auth email 不同：失敗，不覆寫舊 auth。
4. 舊 auth 無 email：失敗，不覆寫。
5. 新 auth 無 email：失敗，不覆寫。
6. renew 成功時保留 `meta.json` / `scope`。
7. renew 目標是 current alias：成功後同步更新 `CODEX_HOME/auth.json`。
8. renew 目標不是 current alias：成功後不改 active `CODEX_HOME/auth.json`。
9. Codex login 失敗：失敗，不覆寫。
10. `cx manual` 內容包含 `renew`。

測試應避免真的呼叫 Codex CLI。可用 monkeypatch 或 fixture 模擬 device login 產生暫時 `auth.json`。

## 10. 驗收條件

1. 使用者可執行 `cx renew <alias>` 重新登入既有 alias。
2. alias 不存在時，不會新增 alias。
3. 登入錯 email 時，不會覆寫原本 alias。
4. 登入同 email 時，會更新該 alias 的 token。
5. 原本的 `scope` 保留。
6. 目標 alias 是 current alias 時，active auth 同步更新。
7. `cx add` / `cx add --force` / `cx save` 既有行為不變。
8. `cx manual` 顯示 renew 指令。
9. 測試通過：

```bash
python -m pytest
ruff check .
```

## 11. 風險與取捨

### 11.1 以 email 作為 identity gate 的限制

email 通常足以避免大多數「登入錯帳號」問題，但它不是所有系統中最嚴格的 account id。若未來 Codex auth payload 提供穩定 account id，應優先改用 account id。

### 11.2 unknown email 採拒絕策略

若舊 auth 或新 auth 解析不到 email，第一版採拒絕覆寫。這可能讓少數特殊 auth payload 無法 renew，但比誤覆寫帳號安全。

使用者仍可在確認風險後使用：

```bash
cx add <alias> --force
```

### 11.3 不支援多選

CLI `renew` 不支援多 alias。原因是每個 alias 都需要互動式登入與人工確認瀏覽器帳號，多 alias 會讓流程混亂，也容易把錯誤登入結果套到錯 alias。
