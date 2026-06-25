# Windows 多版本安裝與 launcher 疑難排除

Windows 上可以同時存在 `pipx` 版與 `install.ps1` 版。這不是帳號資料問題，而是命令列實際執行到不同 launcher，且 launcher 背後讀取的 Python 套件位置也不同。

## 原理

`pipx` 版通常會建立：

```text
%USERPROFILE%\.local\bin\cx.exe
%USERPROFILE%\.local\bin\cx-gui.exe
```

這些檔案只是 launcher，實際 Python 套件在 pipx 自己管理的 venv，例如：

```text
%USERPROFILE%\.local\share\pipx\venvs\cx-account-manager\
```

`install.ps1` 版通常會建立：

```text
%LOCALAPPDATA%\Programs\cx\bin\cx.cmd
%LOCALAPPDATA%\Programs\cx\bin\cx-gui.cmd
```

這些檔案同樣只是 launcher，實際程式檔在：

```text
%LOCALAPPDATA%\cx\app\
```

因此，`pipx upgrade cx-account-manager` 只會更新 pipx 管理的 venv，不會更新 `%LOCALAPPDATA%\cx\app\` 內由 `install.ps1` 複製出來的程式。反過來，重新執行 `install.ps1` 也不會更新 pipx venv。

如果 PowerShell 的 PATH 先找到 `install.ps1` 版 launcher，即使 pipx 已經升級成功，執行 `cx-gui` 仍可能看到舊版 GUI。

## 檢查目前實際執行哪一份

在 PowerShell 執行：

```powershell
Get-Command cx -All | Format-Table CommandType, Source, Version -AutoSize
Get-Command cx-gui -All | Format-Table CommandType, Source, Version -AutoSize
```

PowerShell 會執行第一筆結果。若第一筆是：

```text
%LOCALAPPDATA%\Programs\cx\bin\cx-gui.cmd
```

代表目前預設使用 `install.ps1` 版。若第一筆是：

```text
%USERPROFILE%\.local\bin\cx-gui.exe
```

代表目前預設使用 pipx 版。

## 檢查兩邊版本

檢查 `install.ps1` 版：

```powershell
Select-String "$env:LOCALAPPDATA\cx\app\cx_account_manager\__init__.py" -Pattern "__version__" -ErrorAction SilentlyContinue
```

檢查 pipx 版：

```powershell
pipx runpip cx-account-manager show cx-account-manager

& "$env:USERPROFILE\.local\share\pipx\venvs\cx-account-manager\Scripts\python.exe" -c "import cx_account_manager; print(cx_account_manager.__version__); print(cx_account_manager.__file__)"
```

如果 GUI 顯示的版本和 `pipx runpip` 顯示的版本不同，通常代表目前執行到的不是 pipx 版 launcher。

## 以 pipx 為準

如果希望之後都用 pipx 管理安裝與升級，請移除 `install.ps1` 版 launcher：

```powershell
.\uninstall.ps1
```

不要加 `--purge-data`，除非確定要連本機 `cx` 資料一起刪除，包括已保存的帳號、rollback 備份、GUI 設定與其他產出檔案。

執行後重新開 PowerShell，再確認：

```powershell
Get-Command cx -All
Get-Command cx-gui -All
pipx runpip cx-account-manager show cx-account-manager
cx --version
```

如果 `cx` 或 `cx-gui` 找不到，先確認 pipx 的 bin 目錄已加入 PATH：

```powershell
py -m pipx ensurepath
```

然後重新開 PowerShell。

## 以 install.ps1 為準

如果希望使用 repo 內的 Windows launcher，請不要期待 `pipx upgrade` 會更新這份程式。更新方式是切到新的 tag 或 branch 後重新執行 installer：

```powershell
git fetch --tags
git checkout v4.5.3
.\install.ps1 -InstallWindowsLauncher
```

重新開 PowerShell 後確認：

```powershell
Get-Command cx-gui -All
cx --version
```

## 建議

一般使用者建議二選一，不要長期混用兩套安裝方式。

若只是把 `cx` 當工具使用，建議用 pipx，因為升級與解除安裝較乾淨。

若正在開發或測試這個 repo，使用 `install.ps1` 也可以，但要知道它和 pipx 是兩套獨立安裝狀態。
