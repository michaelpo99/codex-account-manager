# Windows 快速安裝與帳號匯入

本文件給資訊人員使用，適用於 Windows 11 乾淨環境，尚未安裝 Python、pipx、Codex CLI、`cx` 的情境。

假設帳號交換檔已放在 Windows 下載資料夾：

```text
C:\Users\<你的Windows帳號>\Downloads\cx-company-backup.tar.gz
```

以下指令請在 PowerShell 執行。

## 1. 安裝

```powershell
# 安裝 Python 3.12。
# 若 py -3 --version 已可正常顯示版本，這行不用執行。
winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements

# 安裝 Git。
# 若 git --version 已可正常顯示版本，這行不用執行。
winget install -e --id Git.Git --accept-package-agreements --accept-source-agreements

# 安裝 OpenAI Codex CLI。
# 若 codex --version 已可正常顯示版本，這行不用執行。
powershell -ExecutionPolicy Bypass -c "irm https://chatgpt.com/codex/install.ps1 | iex"

# 安裝 pipx，用來隔離安裝 Python CLI 工具。
# 若 pipx --version 已可正常顯示版本，這行不用執行。
py -3 -m pip install --user pipx

# 將 pipx 的執行檔路徑加入使用者 PATH。
# 若 pipx、cx、cx-gui 已可直接執行，這行不用執行。
py -3 -m pipx ensurepath

# 安裝 cx-account-manager 與 GUI modern theme。
# [gui] 會一併安裝 modern theme 需要的 ttkbootstrap。
# 若已安裝過 cx-account-manager，這行不要重複執行；請改看下面的補裝指令。
py -3 -m pipx install "git+https://github.com/michaelpo99/codex-account-manager.git[gui]"
```

如果之前已經安裝過 `cx-account-manager`，但 GUI 仍是傳統 Tk 外觀，補裝 theme：

```powershell
# 只在已安裝 cx-account-manager、但缺 modern theme 時需要。
py -3 -m pipx inject cx-account-manager ttkbootstrap
```

重新開一個 PowerShell 後確認：

```powershell
codex --version
cx --version
cx-gui
```

## 2. 用指令匯入帳號交換檔

```powershell
# 匯入下載資料夾中的帳號交換檔。
# --skip-existing 表示本機若已有同名 alias，就保留本機資料，不覆蓋。
cx import "$env:USERPROFILE\Downloads\cx-company-backup.tar.gz" --skip-existing

# 確認已匯入的帳號。
cx list

# 查詢帳號狀態與建議排序。
cx status
```

若確定要用交換檔覆蓋本機同名 alias，將 `--skip-existing` 改成 `--force`。不確定時不要用 `--force`。

`cx backup-list` 只用於事先檢視交換檔內容，不是必要步驟。

## 3. 用 GUI 匯入帳號交換檔

```powershell
cx-gui
```

GUI 操作：

```text
1. 上方 Auth Environment 選 Windows Native。
2. 點主工具列的 Import。
3. 選擇 Downloads 裡的 cx-company-backup.tar.gz 匯入。
4. 匯入完成後按 Refresh。
5. 要切換帳號時，選取帳號後按 Use。
6. 不確定要用哪個帳號時，按 Best。
```

`Inspect Backup` 只是檢視交換檔內容，非必要步驟。

## 4. 常見狀況

如果 `cx-gui` 找不到指令，通常是 PATH 尚未更新；關閉 PowerShell 後重新開啟再試。

如果 `codex` 找不到指令，請重新執行 Codex CLI 安裝那一行。

如果公司電腦限制 `winget` 或安裝來源，請改由 IT 預先安裝 Python 3.12、Git 與 Codex CLI。