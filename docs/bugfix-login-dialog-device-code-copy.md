# Bugfix: Add Account 登入視窗 device code 複製失效

Status: Proposed

## 1. 問題描述

在 `cx-gui` 使用 `Add` / `Add Account` 新增帳號時，GUI 會開啟登入視窗，並顯示 Codex CLI 的 device auth output。

目前畫面可看到：

```text
Open this link in your browser and sign in to your account
https://auth.openai.com/codex/device

Enter this one-time code ...
V9MH-WCQ48 [複製]
```

但實際操作有問題：

1. 點擊 code 本身，例如 `V9MH-WCQ48`，沒有複製效果。
2. 點擊 `[複製]` 的可點範圍很小，使用者不容易判斷是否點到。
3. 使用滑鼠選取 code 後，按 `Ctrl+C` 無法可靠複製。
4. 視窗上方雖顯示 `Copied code: ...`，但使用者仍可能無法從剪貼簿貼出 code。
5. 目前 device code 複製體驗不符合登入流程的重要性，容易造成 Add Account 卡住。

## 2. 影響範圍

影響功能：

```text
cx-gui > Add Account > LoginDialog
```

不影響：

```text
cx add <alias>
cx save <alias>
cx status
cx best
cx doctor
backup / import / export
```

## 3. 目前推測原因

目前 `LoginDialog.append()` 會解析 Codex CLI output，並偵測：

- URL
- device code

偵測到 URL 時，GUI 會加 hyperlink tag。

偵測到 device code 時，GUI 目前是：

1. 先把 code 本體插入 `ScrolledText`。
2. 再另外插入 ` [複製]`。
3. 只有 ` [複製]` 文字有 copy tag 與 click binding。

因此使用者點 code 本體不會觸發複製。若使用者選取文字後按 `Ctrl+C`，也可能因為 `ScrolledText` 的 readonly / focus / binding 狀態而無法可靠複製。

## 4. 設計原則

本 bugfix 不應把 Codex CLI output 改成 GUI 流程的硬性依賴。

正確原則：

```text
Codex CLI raw output 永遠照原樣顯示。
Parser 只做輔助 UI，不控制登入流程。
Parser 失敗時，不影響使用者閱讀 raw output。
Parser 失敗時，不視為 Add Account 失敗。
```

也就是：

- 可以 parse URL / device code。
- 可以用 parse 結果提供 Copy Code / Open Browser。
- 但不能因為 parse 失敗就中止登入流程。
- 不能隱藏 raw output。
- 不能只顯示重組後的 GUI 文字而不保留原始輸出。

## 5. 修正目標

### 5.1 最小必要修正

1. Device code 本體也必須可點擊複製。
2. `[複製]` 仍可點擊複製。
3. 點擊 code 或 `[複製]` 後，剪貼簿應包含純 code，例如：

```text
V9MH-WCQ48
```

4. 狀態列顯示：

```text
Copied code: V9MH-WCQ48
```

5. 使用者選取 log 文字後，`Ctrl+C` 應能複製選取內容。
6. 修正不應影響 Codex CLI raw output 顯示。

### 5.2 建議 UX 補強

在 raw output 上方新增一個 device auth helper panel。

建議畫面：

```text
Add Account: abc

Open this link:
[ https://auth.openai.com/codex/device        ] [Open Browser]

Enter this code:
[ V9MH-WCQ48                                  ] [Copy Code]

This code expires in 15 minutes. Never share this code.

Raw output
------------------------------------------------------------
<原始 Codex CLI output>
```

說明：

- URL 欄位使用 readonly `ttk.Entry`。
- Code 欄位使用 readonly `ttk.Entry`。
- `Copy Code` 按鈕直接複製 code。
- `Open Browser` 按鈕開啟 URL。
- 若 parser 尚未偵測到 URL / code，欄位可留空，按鈕 disabled。
- raw output 仍完整保留。

此項屬於建議補強；若想快速修 bug，可以先只做 5.1。

## 6. 實作規格

主要修改檔案：

```text
src/cx_account_manager/gui_app.py
```

主要 class：

```text
LoginDialog
```

### 6.1 修正 inline copy tag

目前插入 device code 的邏輯應調整為：

```python
# before: only [複製] is tagged
self.output.insert("end", clean_text[start:end])
self.output.insert("end", " [複製]", ("copy", tag))

# after: code and [複製] are both tagged
self.output.insert("end", clean_text[start:end], ("copy", tag))
self.output.insert("end", " [複製]", ("copy", tag))
self.output.tag_bind(tag, "<Button-1>", lambda _event, code=value: self.copy_code(code))
```

注意：

- tag 應套用在 code 本體與 `[複製]`。
- 游標進入 code 本體或 `[複製]` 時都應顯示 hand cursor。
- 不要改變 raw output 的文字內容，除非是附加 `[複製]`。

### 6.2 支援 Ctrl+C 複製選取文字

為 `self.output` 加入 binding：

```python
self.output.bind("<Control-c>", self.copy_selected_output)
self.output.bind("<Control-C>", self.copy_selected_output)
```

新增方法：

```python
def copy_selected_output(self, _event=None) -> str:
    try:
        selected = self.output.get("sel.first", "sel.last")
    except TclError:
        return "break"
    self.copy_text_to_clipboard(selected)
    self.status_var.set("Copied selected text")
    return "break"
```

### 6.3 集中 clipboard 操作

新增 helper：

```python
def copy_text_to_clipboard(self, text: str) -> None:
    self.parent.clipboard_clear()
    self.parent.clipboard_append(text)
    self.parent.update_idletasks()
```

`copy_code()` 改成：

```python
def copy_code(self, code: str) -> None:
    self.copy_text_to_clipboard(code.strip())
    self.status_var.set(f"Copied code: {code.strip()}")
```

理由：

- 使用 root / parent clipboard 比只使用 Toplevel clipboard 更穩定。
- 統一 clipboard 行為，未來 URL、doctor report、raw output 都可重用。

### 6.4 可選：新增 device auth helper panel

若實作 5.2，新增狀態：

```python
self.device_url_var = StringVar()
self.device_code_var = StringVar()
```

新增 UI：

```python
self.device_panel = ttk.Frame(...)
self.device_url_entry = ttk.Entry(..., textvariable=self.device_url_var, state="readonly")
self.device_code_entry = ttk.Entry(..., textvariable=self.device_code_var, state="readonly")
self.open_browser_button = ttk.Button(..., command=self.open_device_url)
self.copy_code_button = ttk.Button(..., command=self.copy_current_device_code)
```

在 `append()` 偵測 URL 時：

```python
self.device_url_var.set(url)
self.open_browser_button.configure(state="normal")
```

在 `append()` 偵測 code 時：

```python
self.device_code_var.set(code)
self.copy_code_button.configure(state="normal")
```

輔助方法：

```python
def open_device_url(self) -> None:
    url = self.device_url_var.get().strip()
    if url:
        webbrowser.open(url)


def copy_current_device_code(self) -> None:
    code = self.device_code_var.get().strip()
    if code:
        self.copy_code(code)
```

## 7. Parser 安全界線

本 bugfix 可以使用既有 regex parser：

```text
URL_RE
DEVICE_CODE_RE
DEVICE_CODE_TOKEN_RE
```

但必須遵守：

1. Parser 只影響輔助 UI。
2. Parser 失敗不影響 raw output。
3. Parser 失敗不改變 command returncode。
4. Parser 失敗不觸發 error dialog。
5. Parser 不應嘗試解讀 token、auth.json 或任何登入憑證。
6. Parser 不應把 device code 寫入 repo、log file 或帳號資料。

## 8. 測試需求

新增或修改測試：

```text
tests/test_gui_login_dialog.py
```

若現有 GUI 測試架構不方便開 Tk 視窗，可先抽出純函式測試。

### 8.1 建議抽出純函式

可將 output span 偵測抽成：

```python
@dataclass(frozen=True)
class LoginOutputSpan:
    start: int
    end: int
    value: str
    kind: str  # "url" or "code"


def detect_login_output_spans(text: str) -> list[LoginOutputSpan]: ...
```

測試：

1. 可偵測 `https://auth.openai.com/codex/device`。
2. 可偵測 `V9MH-WCQ48`。
3. 可偵測含 `one-time code` 前綴的 code。
4. 不重複偵測重疊 code。

### 8.2 GUI 行為測試

若可建立 Tk 測試：

1. 呼叫 `LoginDialog.append()` 輸入含 code 的文字。
2. 確認 code 本體有 copy tag。
3. 確認 `[複製]` 有 copy tag。
4. 模擬點擊 copy tag 後，clipboard 是 code。
5. 選取 output 文字後，呼叫 `copy_selected_output()`，clipboard 是選取文字。

### 8.3 手動驗收

手動驗收步驟：

1. 執行 `cx-gui`。
2. 按 `Add`。
3. 輸入 alias。
4. 等 Codex CLI 顯示 device auth code。
5. 點 code 本體，確認剪貼簿可貼出 code。
6. 點 `[複製]`，確認剪貼簿可貼出 code。
7. 選取 code，按 `Ctrl+C`，確認剪貼簿可貼出選取文字。
8. 若有 helper panel，按 `Copy Code`，確認剪貼簿可貼出 code。
9. 若有 helper panel，按 `Open Browser`，確認開啟 device auth URL。
10. 完成登入後，Add Account 流程仍正常刷新帳號列表。

## 9. 驗收標準

### 9.1 功能驗收

1. Device code 本體可點擊複製。
2. `[複製]` 可點擊複製。
3. 選取文字後 `Ctrl+C` 可複製。
4. `copy_code()` 複製純 code，不包含 `[複製]`。
5. 複製後 status 顯示 `Copied code: <code>`。
6. raw output 仍完整顯示。
7. parser 失敗不會讓登入流程失敗。
8. Codex CLI output 文案改變時，最多影響輔助按鈕，不影響 raw output 與登入流程。

### 9.2 回歸驗收

1. `cx-gui` 可正常啟動。
2. `Add Account` 可正常開啟 LoginDialog。
3. `Cancel` 可中止登入 subprocess。
4. 登入成功後仍會 refresh accounts。
5. `Refresh`、`Details`、`Best`、`Use`、`Export`、`Import` 不受影響。
6. Enterprise Light / ttkbootstrap / ttk fallback 不受影響。

### 9.3 安全驗收

1. 不記錄 device code 到 repo。
2. 不記錄 device code 到帳號資料。
3. 不顯示或複製 token、auth.json、cookie。
4. 不把 device code 傳給任何遠端服務。
5. 仍保留 Codex CLI 原本的 phishing warning。

## 10. 建議實作順序

### Phase 1：低風險修復

1. Code 本體套用 copy tag。
2. `[複製]` 繼續可用。
3. 支援 output 選取後 `Ctrl+C`。
4. 集中 clipboard helper。
5. 補測試或至少補手動驗收。

### Phase 2：登入輔助區

1. 新增 URL readonly entry + Open Browser。
2. 新增 Code readonly entry + Copy Code。
3. parser 成功時更新欄位。
4. parser 失敗時保持欄位空白，但 raw output 照常顯示。

## 11. 完成定義

完成後，使用者在 Add Account login dialog 看到 device code 時，至少有三種可靠複製方式：

1. 點擊 code 本體。
2. 點擊 `[複製]` 或 `Copy Code`。
3. 選取文字後按 `Ctrl+C`。

且上述修正不得讓 Codex CLI output parsing 成為登入流程的硬性依賴。
