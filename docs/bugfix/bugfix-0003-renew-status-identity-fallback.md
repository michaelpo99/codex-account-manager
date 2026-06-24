# Bugfix: Renew 與 Status 在憑證失效或新版 auth payload 下無法顯示或比對 identity

Status: Proposed

## 1. 背景

在 `cx Account Manager` 4.5.4 的實測中，出現兩個彼此相關的問題：

第一，GUI 帳號列表中，某些帳號的線上狀態查詢失敗時，即使本機 `meta.json` 仍保存 `email` 與 `plan`，表格的 Email / Plan 欄位仍顯示空白。

第二，對同一帳號執行 `Renew` 時，Codex CLI 已完成登入，但 `cx renew <alias>` 後續仍失敗，錯誤為：

```text
新的登入結果無法識別 email，為避免覆寫錯帳號，已取消 renew。
```

這不是登入流程本身失敗，也不是 email 從本機資料中消失。實測 `meta.json` 仍可查到：

```json
{
  "scope": "work",
  "email": "user@example.com",
  "plan": "team"
}
```

核心問題是：目前程式把「線上 app-server 狀態查詢」與「本機已知 identity 顯示或比對」耦合過深。一旦線上狀態查詢失敗，或新版 Codex `auth.json` 不再直接包含 email，就會把 identity 當成不可得。

## 2. 影響範圍

本次 bugfix 針對：

```text
cx status
cx status --json
cx-gui account table
cx renew <alias>
```

GUI 本身理論上不需要大改，因為表格資料來自 `cx status --json`。只要 status JSON 在 error row 中仍包含 cached identity，GUI 表格就會自然顯示。

本次不處理：

```text
cx add <alias>
cx add <alias> --force
cx save <alias>
cx use <alias>
backup / import / export 格式
```

但若實作中新增共用 helper，不得改變上述指令原本的 identity 覆寫語意。

## 3. 問題一：Status error row 沒有使用 cached identity

### 3.1 現象

當 alias 的線上狀態查詢失敗時，`cx status --json` 仍會輸出該帳號，但 `email` 與 `plan` 是 `null`。GUI 因此在表格中顯示空白。

但本機檔案可能仍有 identity cache：

```text
~/.local/share/cx/accounts/<alias>/meta.json
%LOCALAPPDATA%\cx\accounts\<alias>\meta.json
```

### 3.2 根因

`read_status_for_alias()` 在 `request_app_server(auth_file)` 失敗時，直接回傳沒有 email / plan 的 `AccountStatus`，沒有先讀：

```python
read_cached_account_identity(alias)
```

### 3.3 正確行為

Status 應區分兩種資料來源：

```text
本機 identity cache：email / plan，可在狀態查詢失敗時繼續顯示。
線上 usage status：rate limit / reset time，需要線上狀態查詢成功才可取得。
```

當線上狀態查詢失敗時，應顯示 cached email / plan，同時保留 error 欄位。

### 3.4 修正方式

在 `read_status_for_alias()` 開頭讀取 cache：

```python
def read_status_for_alias(alias: str) -> AccountStatus:
    auth_file = account_auth_file(alias)
    scope = read_account_scope(alias)
    cached_email, cached_plan = read_cached_account_identity(alias)

    if not auth_file.exists():
        return AccountStatus(
            alias, scope,
            cached_email, cached_plan,
            None, None, None, None, None, None,
            "auth.json 不存在",
        )

    try:
        account_result, rate_result = request_app_server(auth_file)
    except CxError as exc:
        return AccountStatus(
            alias, scope,
            cached_email, cached_plan,
            None, None, None, None, None, None,
            str(exc),
        )
```

成功讀到 app-server 後，也應對 email / plan 做 fallback：

```python
email = account.get("email")
if not isinstance(email, str) or not email:
    email = cached_email

plan = account.get("planType") or rate_limits.get("planType")
if not isinstance(plan, str) or not plan:
    plan = cached_plan
```

只有線上回傳有效 email 時才更新 cache。

## 4. 問題二：Renew 對新登入 auth 只做靜態 email parse

### 4.1 現象

`cx renew <alias>` 執行 Codex device login 後，登入流程成功，但 `cx renew` 隨後失敗：

```text
新的登入結果無法識別 email，為避免覆寫錯帳號，已取消 renew。
```

### 4.2 根因

`cmd_renew()` 對舊 auth 使用 `read_account_email_with_fallback(alias, target_auth)`，可從 auth 靜態解析、app-server、或 meta cache 取得 email。

但對新登入暫存 auth 只做：

```python
new_email = read_auth_email(temp_auth)
```

這只會靜態解析 `auth.json`。若新版 Codex `auth.json` 不再直接包含 email，或 email 放在 parser 未支援的位置，`new_email` 會是 `None`，renew 直接取消。

### 4.3 正確行為

Renew 的安全設計仍然正確：覆寫前必須確認新舊 identity 一致。

但新登入 auth 的 identity 取得也應有 fallback：

```text
1. 優先從 auth.json 靜態解析 email。
2. 解析不到時，用暫存 CODEX_HOME/auth.json 啟動 app-server，查 account/read。
3. 若仍讀不到 email，才拒絕覆寫。
4. 若讀到 email，但與舊 email 不一致，仍必須拒絕覆寫。
```

### 4.4 最小修正方式

將 `cmd_renew()` 中的新 auth email 讀取改為：

```python
new_email = read_auth_email_with_fallback(temp_auth)
if not new_email:
    raise CxError("新的登入結果無法識別 email，為避免覆寫錯帳號，已取消 renew。")
```

但請注意：既有 `read_auth_email_from_app_server()` 目前使用 `request_app_server()`，而 `request_app_server()` 會同時要求 `account/read` 與 `account/rateLimits/read`。Renew identity gate 只需要 `account/read`。

若 `account/read` 成功但 `account/rateLimits/read` 失敗，不應阻止 identity 判斷。因此建議新增更精準的 helper。

## 5. 建議新增 helper：只讀 account identity

建議在 `src/cx.py` 新增 helper，避免 renew identity gate 依賴 rate limit endpoint。

建議方向：

```python
def request_account_read(auth_file: Path, timeout_sec: float = 15.0) -> dict[str, Any] | None:
    """Use codex app-server with the supplied auth file and return account/read result only."""
    ...
```

或：

```python
def read_auth_identity_from_app_server(auth_file: Path) -> tuple[str | None, str | None]:
    ...
```

行為：

1. 建立暫存 `CODEX_HOME`。
2. 複製指定 `auth.json` 到暫存 home。
3. 啟動 `codex app-server`。
4. 送出 initialize / initialized / `account/read`。
5. 只等待 `account/read` 結果。
6. 若 `account/read` 回傳 error，回傳 `None` 或 raise `CxError`，由呼叫端決定 fallback。
7. 清理暫存目錄與 subprocess。

## 6. 問題三：不要讓 renew 成功後的 cache 回寫清掉既有 identity

### 6.1 風險

目前 `cache_account_identity_from_auth(alias, auth_file)` 會靜態解析 auth，然後把結果寫回 `meta.json`。若新版 `auth.json` 靜態解析不到 email / plan，可能把既有的 `meta.json` email / plan 移除。

但這個 helper 目前不只 `renew` 使用，`cx add` 與 `cx save` 也會直接呼叫。若把 helper 全域改成「parse 失敗就保留舊 cache」，可能讓 `save --force` 或其他覆寫流程留下不屬於新 auth 的舊 identity。

### 6.2 正確行為

Cache 更新應採保守且情境化策略：

```text
renew 成功後：若已驗證 new_email，至少應保留或更新 email，不得因靜態 parser 失敗而把既有 email 清空。
renew 成功後：plan 若能從可信來源取得則更新，否則保留既有 plan。
add / save：不得因沿用舊 alias 的 meta cache 而把舊 identity 混到新 auth。
```

不要因為 parser 未跟上新版 auth payload，就清除已知 identity；也不要把這條規則不加區分地套到所有寫入流程。

### 6.3 修正方式

不要直接把 `cache_account_identity_from_auth()` 改成全域保留舊 cache 的語意。

建議二選一：

```text
A. 新增 renew 專用 cache helper，明確接受已驗證的 new_email 與可選 plan。
B. 保留既有 helper 語意，另外在 renew 成功後顯式 merge cache，而不是再次只依賴 auth 靜態 parser。
```

例如：

```python
cache_account_identity(
    alias,
    email=new_email,
    plan=verified_plan_or_cached_plan,
)
```

若後續實作有 app-server identity helper，也可在 renew 成功後直接用已驗證的 `new_email` 寫入 cache，避免再次依賴 auth 靜態 parser。

## 7. 實作檔案

主要修改：

```text
src/cx.py
```

建議補測試：

```text
tests/test_cli_renew.py
tests/test_status_app_server.py
tests/test_json_output.py
```

## 8. 測試案例

### 8.1 Status error row 顯示 cached identity

對某 alias 準備 `meta.json`：

```json
{
  "scope": "work",
  "email": "user@example.com",
  "plan": "team"
}
```

並 mock `request_app_server()` 讓它 raise `CxError("status failed")`。

期望：

```python
status = read_status_for_alias("company")
assert status.email == "user@example.com"
assert status.plan == "team"
assert status.error == "status failed"
```

### 8.2 `cx status --json` 在 error row 輸出 cached identity

期望 JSON 輸出包含：

```json
{
  "alias": "company",
  "scope": "work",
  "email": "user@example.com",
  "plan": "team",
  "error": "status failed"
}
```

### 8.3 Missing auth 也保留 cached identity

若 `auth.json` 不存在，但 `meta.json` 有 email / plan，status 應回傳：

```text
email=user@example.com
plan=team
error=auth.json 不存在
```

### 8.4 Renew 新 auth 靜態 parse 失敗但 app-server 可讀 email 時成功

舊帳號 cached identity：

```text
email=user@example.com
```

新登入暫存 auth 靜態解析不到 email，但 mock app-server account/read 回傳：

```json
{
  "account": {
    "email": "user@example.com",
    "planType": "team"
  }
}
```

期望：

```text
cx renew company 成功
accounts/company/auth.json 被更新
meta.json 至少保留或更新 email=user@example.com
若有可信 plan 來源，可更新為 plan=team；若沒有，至少不得把既有 plan 清空
若 company 是 current alias，CODEX_HOME/auth.json 同步更新
```

### 8.5 Renew 新 auth app-server email 不一致時拒絕覆寫

舊 email：

```text
old@example.com
```

新 app-server email：

```text
new@example.com
```

期望：

```text
cx renew company 失敗
錯誤訊息包含「登入帳號不一致」
accounts/company/auth.json 不被覆寫
```

### 8.6 Renew 成功後不因靜態 parser 失敗清空既有 cache

既有 `meta.json` 有 email / plan。新 auth 靜態 parser 解析不到 email / plan，但 renew 已透過 fallback 驗證 identity。

期望：

```text
meta.json 仍保留有效 email
plan 若無新可信來源，仍保留原 plan
```

### 8.7 不得把 renew 專用 cache merge 語意外溢到 add / save

準備一個既有 alias，其 `meta.json` 含舊 email / plan，再模擬 `save --force` 或等價覆寫流程寫入另一份無法靜態 parse identity 的 auth。

期望：

```text
不得因重用 renew 的 cache merge 邏輯而把舊 alias identity 混到新的 auth
```

## 9. 驗收標準

完成後必須符合：

1. 線上狀態查詢失敗的帳號在 GUI 表格仍顯示本機 cached email / plan。
2. `cx status --json` 的 error row 仍包含 cached email / plan。
3. `cx renew <alias>` 在登入成功後，若 app-server 可識別新登入 email，應可完成 renew。
4. `cx renew <alias>` 仍必須拒絕新舊 email 不一致的情況。
5. 不得把 `cx add --force` 當作 renew 的修法。
6. 不得移除 renew 的同帳號 identity gate。
7. 不得因新版 auth payload 靜態解析不到 email / plan 就清空 renew 目標 alias 的既有 identity cache。
8. 不得把 renew 專用 cache merge 語意誤套到 `add`、`save` 或其他覆寫流程。
9. 不改變 backup archive 格式。
10. 所有既有測試通過。
11. 新增測試覆蓋本文件第 8 節案例。

## 10. 建議實作流程

若要在本 repo 直接實作，建議從 `master` 開新分支：

```bash
git checkout master
git pull --ff-only
git checkout -b fix/renew-status-identity-fallback
```

完成修改後先執行測試：

```bash
python -m unittest discover -s tests
```

如果專案環境有 pytest，也可以再執行：

```bash
python -m pytest
```

確認 working tree：

```bash
git status
git diff -- src/cx.py tests/test_cli_renew.py tests/test_status_app_server.py tests/test_json_output.py
```

提交：

```bash
git add src/cx.py tests
git commit -m "fix: use cached identity for renew and status fallbacks"
git push -u origin fix/renew-status-identity-fallback
```

最後建立 PR：

```bash
gh pr create --base master --head fix/renew-status-identity-fallback --title "fix: use cached identity for renew and status fallbacks" --body "Fix renew/status identity fallback handling when Codex auth payload no longer exposes email directly or status checks fail."
```

PR 內容必須包含：

```text
Summary
- status error rows now retain cached email/plan
- renew can validate new login identity via fallback instead of static auth parse only
- renew no longer clears verified identity cache just because the static parser cannot extract email/plan

Tests
- python -m unittest discover -s tests
- python -m pytest  # if available
```

## 11. 注意事項

1. 不要在文件或測試 fixture 中放入真實 email 或真實憑證內容。
2. 不要把線上狀態查詢失敗視為帳號 identity 不存在。
3. Status 查詢失敗時，usage / reset time 可以是 `None`；email / plan 應盡量來自 cache。
4. Renew 的 identity gate 是安全功能，不可移除。
5. 若新增 app-server helper，需確保 subprocess 清理與暫存 `CODEX_HOME` 清理完整。
6. 測試應覆蓋「新 auth 只能透過 fallback 辨識 identity」與「cache merge 不外溢到 add/save」兩種風險。
