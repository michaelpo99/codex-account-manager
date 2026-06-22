# Bugfix: renew 在 token 失效且缺少 email cache 時無法執行

Status: Proposed

## 1. 問題描述

`cx renew <alias>` 的安全設計會先確認既有 alias 的身份，再允許新的登入結果覆寫 token。現在身份確認主要依賴舊 `auth.json` 內的 `email` 欄位；若舊 `auth.json` 沒有 email，程式會嘗試透過 app server 讀 account email。

當 token 已失效或被 revoke 時，app server fallback 也會失敗。若舊 `auth.json` 本身沒有 email cache，renew 就會回報既有 auth 無法識別 email，導致使用者無法用 renew 修復過期 token。

這不是帳號真的沒有 email，而是本機 alias 缺少可離線比對的身份資料。

## 2. 影響

- token 失效後，部分 alias 無法 renew。
- 使用者可能被迫刪除 alias 後重新 add，增加打錯 alias 或登入錯帳號的風險。
- `cx renew` 的安全目標是正確的，但目前缺少穩定的 identity cache，造成 token 失效後進入死局。

## 3. 預期行為

`cx renew <alias>` 應在 token 已失效時仍能安全確認舊 alias identity，只要系統曾經在 token 有效時讀到過該 alias 的 email。

舊帳號 email 的來源順序應為：

1. 既有 `accounts/<alias>/auth.json` 內可解析的 email。
2. app server 查到的 account email。
3. `accounts/<alias>/meta.json` 內保存的 email cache。

新的登入結果仍必須能識別 email，且必須與舊 alias 的 email 一致，才允許覆寫 token。

## 4. 修正方向

### 4.1 在 meta.json 保存 identity cache

當系統成功取得 alias email 時，應寫入：

```json
{
  "scope": "work",
  "email": "user@example.com",
  "plan": "..."
}
```

可寫入時機包括：

- `cx add <alias>` 成功後。
- `cx save <alias>` 成功後。
- `cx status` / GUI refresh 成功從 app server 取得 account email 時。
- `cx renew <alias>` 成功後。
- 匯入備份時若備份 summary 有 email。

### 4.2 renew 使用 meta email fallback

`cmd_renew()` 讀取 old email 時，若 `auth.json` 與 app server 都無法提供 email，應 fallback 到 `meta.json` 的 email。

若三者都無法取得 email，仍應拒絕 renew，避免覆寫錯帳號。

### 4.3 保留 meta.json 既有欄位

目前 `write_account_scope()` 只寫 `{ "scope": ... }`，可能覆蓋未來的 email / plan cache。此 bugfix 必須同時修正 meta merge 行為：更新 scope 時不得刪除 email、plan 或其他已知 metadata。

## 5. 不做的事

- 不放寬 renew 的 email 一致性檢查。
- 不新增 `renew --force`。
- 不在不知道舊 identity 的情況下覆寫 alias。
- 不把 email 存進 active `CODEX_HOME/auth.json`。

## 6. 驗收標準

- 已有 `meta.json.email` 的 alias，即使舊 token 失效、app server 查不到 email，仍可進入 renew 流程。
- 新登入 email 與 `meta.json.email` 不一致時，renew 必須拒絕覆寫。
- `cx scope <alias> <work|personal>` 不會刪除 `meta.json.email`。
- `cx add` / `cx save` / `cx renew` 成功後，能盡量保存或更新 `meta.json.email`。
- GUI Renew 行為同步受益，無需 GUI 自行繞過 CLI 檢查。
