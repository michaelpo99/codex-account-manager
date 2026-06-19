# CR-005: Enterprise Light GUI 視覺升級

Status: Proposed

## 1. 背景

`cx-gui` 已完成第一階段資訊架構改版：主畫面以帳號表格為核心，低頻功能收進 `More`，並加入 contextual action bar、Activity / Log 收合、右鍵選單與快捷鍵。功能結構已接近可交付內部使用者的工具。

但目前視覺仍偏向標準 Tk / ttk 預設風格。配色、按鈕、間距、表格行距、狀態標籤與 dialog 造型仍較陽春，容易讓使用者感覺像工程原型，而不是穩定的內部桌面工具。

本 CR 目標是以 `Enterprise Light` 風格升級 GUI 視覺層，優先採用 `ttkbootstrap`，但必須保留純 `ttk` fallback。此改版只處理視覺、樣式、字體、間距、色彩與元件狀態，不改核心功能、不改 CLI 行為、不改帳號資料格式。

## 2. 設計方向

採用原型：

```text
Enterprise Light + ttkbootstrap + fallback to ttk
```

設計目標：

```text
乾淨、穩定、正式、像公司內部管理工具，不像 hobby Tkinter 範例程式。
```

非目標：

```text
炫技、動畫、多彩、重度 dashboard、完全重寫 GUI framework。
```

## 3. 目標

1. 使用 `ttkbootstrap` 提供現代 light theme。
2. 若 `ttkbootstrap` 不存在，GUI 仍能用原本 `ttk` 啟動。
3. 建立統一的 theme tokens，包括色彩、字體、間距、行高、狀態色。
4. 改善 top bar、context action bar、account table、activity drawer、doctor dialog、message dialog 的視覺層級。
5. 保留現有 GUI 功能與事件流程。
6. 不影響 `cx` CLI、`cx doctor`、帳號儲存、status/best/ranking、backup/import/export。
7. 不要求第一版支援 dark mode，但架構應允許未來加入。

## 4. 非目標

本次 CR 不做以下事項：

1. 不改用 PySide6 / Qt。
2. 不改用 CustomTkinter。
3. 不重寫 GUI 流程。
4. 不改 CLI 指令與資料格式。
5. 不新增網路服務。
6. 不把 `ttkbootstrap` 設為 GUI 啟動的硬性條件。
7. 不要求動畫效果。
8. 不要求 icon pack 第一版完成。
9. 不要求完整 dark mode。

## 5. 套件策略

### 5.1 優先套件

使用：

```text
ttkbootstrap
```

建議版本：

```text
ttkbootstrap>=1.10,<2
```

### 5.2 fallback 原則

`ttkbootstrap` 必須是「視覺增強」，不是「啟動必要條件」。

GUI 啟動時：

1. 嘗試 import `ttkbootstrap`。
2. 成功時使用 `ttkbootstrap.Window` 與 Enterprise Light theme。
3. 失敗時回到 `tkinter.Tk` + 目前 ttk styles。
4. fallback 時不得 crash。
5. fallback 時可在 Activity / Log 或 status 顯示：

```text
Theme: standard ttk fallback
```

不要在 fallback 時跳 messagebox，避免干擾一般使用。

本 CR 中的 fallback 定義為：

```text
GUI 必須能在沒有 ttkbootstrap 的環境啟動，並盡量用純 ttk 套用 Enterprise Light 的顏色、字體與間距。
若特定 ttkbootstrap-only 效果無法用 ttk 表現，應降級成標準 ttk 外觀，而不是讓啟動或操作失敗。
```

也就是說，fallback 不是另一套功能模式；所有既有 GUI 行為都必須維持，只是視覺細節可以較簡化。

### 5.3 pyproject.toml 建議

不建議把 `ttkbootstrap` 放入正式 `dependencies`，避免 CLI 使用者安裝 `cx` 時被迫安裝 GUI theme dependency。

建議新增 optional dependency：

```toml
[project.optional-dependencies]
gui = [
  "ttkbootstrap>=1.10,<2"
]
```

既有 dev dependency 可保留。

未來可用：

```bash
python -m pip install -e ".[dev,gui]"
```

或：

```bash
pipx install ".[gui]"
```

### 5.4 install.ps1 策略

第一階段不要讓 `install.ps1` 自動安裝 pip 套件，避免公司環境遇到 proxy / 權限 / pip policy 問題。

`install.ps1` 可加提示：

```text
Optional GUI theme package not installed. To enable the modern theme, run:
python -m pip install ttkbootstrap
```

但這是加分項，不是必要項。

若要自動安裝，必須另開 CR 設計 `-InstallGuiTheme` 參數，不在本 CR 預設範圍內。

## 6. 建議架構

新增檔案：

```text
src/cx_account_manager/ui_theme.py
```

用途：

1. 集中管理 theme detection。
2. 集中管理 color tokens。
3. 集中管理 font tokens。
4. 提供 apply styles 的 helper。
5. 隔離 `ttkbootstrap` import，避免 `gui_app.py` 直接散落 try / except。

### 6.1 建議 interface

```python
@dataclass(frozen=True)
class ThemeInfo:
    engine: str              # "ttkbootstrap" or "ttk"
    name: str                # "flatly" / "cosmo" / "standard"
    available: bool

@dataclass(frozen=True)
class ThemeTokens:
    bg: str
    surface: str
    surface_alt: str
    surface_raised: str
    border: str
    border_soft: str
    text: str
    text_secondary: str
    text_muted: str
    text_disabled: str
    primary: str
    primary_hover: str
    primary_soft: str
    primary_border: str
    primary_text: str
    success: str
    success_soft: str
    success_border: str
    warning: str
    warning_soft: str
    warning_border: str
    danger: str
    danger_soft: str
    danger_border: str
    info: str
    info_soft: str
    info_border: str
    table_bg: str
    table_header_bg: str
    table_header_fg: str
    table_row_alt: str
    selected_bg: str
    current_bg: str
    error_bg: str
    error_fg: str
    activity_strip_bg: str
    activity_muted: str
    activity_error: str
    activity_warning: str
    activity_success: str
    log_bg: str
    log_text: str


def enterprise_light_tokens() -> ThemeTokens: ...
def create_root_and_theme(title: str) -> tuple[Tk, ThemeInfo, ThemeTokens]: ...
def configure_enterprise_styles(root: Tk, tokens: ThemeTokens) -> None: ...
def style_status_badge(status: str) -> str: ...
def button_style_kwargs(role: str, theme_info: ThemeInfo) -> dict[str, str]: ...
def format_font_tokens(root: Tk) -> dict[str, object]: ...
```

第一版可以比上面簡化，但至少要把 `ttkbootstrap` import 與 fallback 集中到一處。

注意：`ThemeTokens` 應涵蓋第 7 節列出的所有實際會用到的顏色。若第一版尚未使用某些 token，也應避免在 widget 程式碼中硬編碼散落色值，避免後續 dark mode 或 theme 切換時需要大範圍修改。

### 6.2 Root 建立方式

目前 GUI entrypoint 可調整為：

```python
def main() -> int:
    root, theme_info, theme_tokens = create_root_and_theme(APP_TITLE)
    app = CxGui(root, theme_info=theme_info, theme_tokens=theme_tokens)
    root.mainloop()
    return 0
```

若改動 `CxGui.__init__` 成本較高，可先在 root 上掛屬性：

```python
root.cx_theme_info = theme_info
root.cx_theme_tokens = theme_tokens
```

但正式設計建議用明確參數。

## 7. Enterprise Light 色彩規格

### 7.1 Base colors

建議 token：

```text
app_bg           #F6F8FB
surface          #FFFFFF
surface_alt      #F8FAFC
surface_raised   #FFFFFF
border           #D9E1EA
border_soft      #E6ECF2
text             #111827
text_secondary   #374151
text_muted       #6B7280
text_disabled    #9CA3AF
```

### 7.2 Brand / action colors

```text
primary          #2563EB
primary_hover    #1D4ED8
primary_soft     #EFF6FF
primary_border   #BFDBFE
primary_text     #FFFFFF
```

### 7.3 Semantic colors

```text
success          #16A34A
success_soft     #ECFDF3
success_border   #BBF7D0
warning          #D97706
warning_soft     #FFFBEB
warning_border   #FDE68A
danger           #DC2626
danger_soft      #FEF2F2
danger_border    #FECACA
info             #0284C7
info_soft        #F0F9FF
info_border      #BAE6FD
```

### 7.4 Table colors

```text
table_bg         #FFFFFF
table_header_bg  #F1F5F9
table_header_fg  #334155
table_row_alt    #FAFCFE
table_selected   #DBEAFE
table_current    #EFF6FF
table_error_fg   #B91C1C
table_error_bg   #FEF2F2
```

### 7.5 Activity / Log colors

```text
activity_strip_bg #F8FAFC
activity_body_bg  #0F172A
activity_text     #E5E7EB
activity_muted    #94A3B8
activity_error    #FCA5A5
activity_warning  #FCD34D
activity_success  #86EFAC
```

第一階段如果 `ScrolledText` 深色樣式成本較高，可保留白底，但 monospace 字體與 padding 要調整。

## 8. 字體規格

### 8.1 Windows 預設字體

建議優先順序：

```text
Segoe UI
Microsoft JhengHei UI
Microsoft JhengHei
Arial
```

### 8.2 Linux / WSL fallback

```text
Noto Sans CJK TC
Noto Sans CJK
DejaVu Sans
Arial
```

### 8.3 字級

```text
app_title         12–13 pt, semibold
section_title     10–11 pt, semibold
body              10 pt
body_small        9 pt
table_cell        10 pt
table_alias       10 pt, semibold
table_meta        9 pt
badge             8.5–9 pt, semibold
log               9.5–10 pt, monospace
```

### 8.4 Monospace

```text
Cascadia Mono
Consolas
DejaVu Sans Mono
Courier New
```

Activity / Log、raw doctor output、JSON output 使用 monospace。

## 9. 間距與尺寸規格

### 9.1 Global spacing

```text
spacing_xs  4 px
spacing_sm  6 px
spacing_md  8 px
spacing_lg  12 px
spacing_xl  16 px
```

### 9.2 Window

```text
default size: 1180 x 680
minimum width: 900
minimum height: 560
background: app_bg
```

### 9.3 Top bar

```text
height: 64–72 px
padding: 12 px horizontal, 8 px vertical
background: surface
bottom border: border_soft
```

Top bar layout：

```text
左：產品名 / 版本
中：Auth Environment
右：Refresh Details Best Add More
```

### 9.4 Context action bar

```text
height: 44–52 px
padding: 10 px horizontal
background: primary_soft 或 surface_alt
border: primary_border 或 border_soft
```

Use button 使用 primary style。Remove 使用 danger outline。Work / Personal / Export 使用 secondary style。

### 9.5 Table

```text
row height: 44–48 px
header height: 34–38 px
cell horizontal padding: 8–10 px
line color: border_soft
```

### 9.6 Activity drawer

Collapsed：

```text
height: 36–42 px
```

Expanded：

```text
height: 180–220 px
```

Log text padding：

```text
8–10 px
```

## 10. 元件樣式規格

### 10.1 Buttons

按鈕類型：

```text
Primary: Use, Run Doctor, Copy Report
Secondary: Refresh, Details, Best, Add, Export
Danger: Remove
Ghost / Link: Show details, Hide details
```

`ttkbootstrap` 可使用 bootstyle：

```python
bootstyle="primary"
bootstyle="secondary-outline"
bootstyle="danger-outline"
bootstyle="link"
```

Fallback ttk 則用自訂 style：

```text
Primary.TButton
Secondary.TButton
Danger.TButton
Ghost.TButton
```

實作時不得直接在一般 `ttk.Button` 建立時無條件傳入 `bootstyle`，否則純 `ttk` fallback 會因未知 option 失敗。應集中透過 helper 轉換：

```python
def button_style_kwargs(role: str, theme_info: ThemeInfo) -> dict[str, str]:
    if theme_info.engine == "ttkbootstrap":
        return {"bootstyle": "..."}
    return {"style": "..."}
```

所有 top bar、context action bar、dialog button 需透過同一層 helper 套用角色樣式，避免 `ttkbootstrap` 與 `ttk` 分支散落在 widget 建立處。

### 10.2 Badges / chips

Tkinter 原生沒有真正 badge widget。第一階段可用 `ttk.Label` + style 模擬。

Badge 類型：

```text
Current
work
personal
OK
Warning
Error
Skipped
```

建議 style：

```text
Badge.Current.TLabel
Badge.Work.TLabel
Badge.Personal.TLabel
Badge.OK.TLabel
Badge.Warning.TLabel
Badge.Error.TLabel
Badge.Skipped.TLabel
```

Badge padding：

```text
horizontal 6 px, vertical 2 px
```

### 10.3 Table current row

目前帳號列使用：

```text
table_current background #EFF6FF
alias semibold
current column 顯示 Current 或 ●
```

若 Treeview cell-level badge 不容易做，第一階段用 row background + current column text 即可。

### 10.4 Error row

若 account row 有 error：

```text
row foreground: danger
error column: 短訊息
```

不要讓整列紅底，避免視覺過重。可用淡紅底只標 error column，但 Treeview column-level style 不易做，第一階段可用 row foreground。

### 10.5 Activity / Log

Activity / Log 為唯讀。

行為：

- 成功 refresh 不展開。
- 錯誤時展開。
- doctor warning/error 展開或開 dialog。
- 使用者手動 Show details 展開。

Log style：

```text
font: monospace 9.5–10 pt
background: log_bg
foreground: log_text
```

## 11. Layout 詳細規格

### 11.1 Top bar

建議版面：

```text
+--------------------------------------------------------------------------------+
| cx Account Manager  3.0.5          Auth Environment                             |
|                                     [ Windows Native v ]    Refresh Details Best |
|                                                            Add More             |
+--------------------------------------------------------------------------------+
```

若寬度不足：

1. 產品版本可縮短成 `cx 3.0.5`。
2. `Auth Environment` label 可縮短成 `Environment`。
3. `Details` 可縮短成 `Status` 或保留現名。
4. 不要使用水平 scrollbar。

### 11.2 Context action bar

```text
+--------------------------------------------------------------------------------+
| Selected 1 account · Rank 1 · michaelpo                  Use Remove Work ...    |
+--------------------------------------------------------------------------------+
```

未選取：

```text
No account selected                                      Use/Remove disabled
```

多選：

```text
Selected 3 accounts                                      Remove Work Personal Export
```

注意：若多選時 `Use` 不可用，應 disabled 或 hidden。第一階段保留 disabled。

### 11.3 Account table

欄位：

```text
Current | Rank | Alias | Scope | Email | Plan | 5h | 7d | Error
```

建議寬度：

```text
Current  72
Rank     64
Alias    150
Scope    96
Email    260 stretch
Plan     100
5h       130
7d       130
Error    260 stretch
```

5h / 7d 顯示：

```text
3% used
reset 23:58
```

若 reset time 不存在：

```text
3% used
reset n/a
```

### 11.4 Activity drawer

Collapsed：

```text
Activity                                      Show details
Last action: Ready
```

Expanded：

```text
Activity / Log                                Hide details
[monospace output]
```

## 12. Doctor dialog 視覺規格

CR-004 定義 doctor GUI 功能，本 CR 只定義視覺層。

Doctor dialog 應套用 Enterprise Light：

```text
surface background
section card
status badge
primary Copy Report button
secondary Copy JSON button
```

建議版面：

```text
CX Doctor
Target: Windows Native        Result: Warning

[System]   OK
[Paths]    OK
[Codex]    Warning
[Accounts] OK
[WSL]      Skipped

Warnings
- codex --version failed

Buttons: Copy Report | Copy JSON | Show Raw Output | Close
```

注意：上面的 `Copy JSON` 與 `Show Raw Output` 只代表若 CR-004 或既有實作已提供這些操作，本 CR 需套用一致視覺樣式。本 CR 不要求新增 doctor dialog 功能按鈕；若要新增按鈕或改變 doctor 行為，應另開功能 CR 或明確擴充本 CR 範圍。

Status badge：

```text
OK       green soft
Warning  amber soft
Error    red soft
Skipped  gray soft
```

## 13. Implementation details

### 13.1 建議新增檔案

```text
src/cx_account_manager/ui_theme.py
```

### 13.2 建議修改檔案

```text
src/cx_account_manager/gui_app.py
src/cx_account_manager/gui.py
pyproject.toml
README.md
install.ps1
```

`install.ps1` 修改只限於提示，不自動安裝 dependency。

### 13.3 Theme detection pseudocode

```python
def create_root_and_theme(title: str):
    try:
        import ttkbootstrap as tb
        root = tb.Window(themename="flatly")
        root.title(title)
        return root, ThemeInfo(engine="ttkbootstrap", name="flatly", available=True), enterprise_light_tokens()
    except Exception:
        root = Tk()
        root.title(title)
        return root, ThemeInfo(engine="ttk", name="standard", available=False), enterprise_light_tokens()
```

### 13.4 推薦 ttkbootstrap theme

第一候選：

```text
flatly
```

備選：

```text
cosmo
litera
```

不要使用過度鮮豔或 dark theme 作為預設。

### 13.5 CxGui constructor

建議改為：

```python
class CxGui:
    def __init__(self, root: Tk, theme_info: ThemeInfo | None = None, theme_tokens: ThemeTokens | None = None) -> None:
        ...
```

若不傳入 theme，使用 fallback tokens。

## 14. 測試需求

### 14.1 單元測試

新增：

```text
tests/test_ui_theme.py
```

測試：

1. `enterprise_light_tokens()` 回傳必要 token。
2. theme engine detection 在 mock `ttkbootstrap` import 失敗時回到 ttk。
3. button style helper 在 `ttkbootstrap` engine 回傳 `bootstyle`，在 `ttk` fallback 回傳 `style`，且不混用。
4. `redact` 或 style helper 不依賴 GUI mainloop。
5. style name helper 可回傳穩定字串。

單元測試應盡量測純函式，不應要求真的開啟 GUI display。若需要涵蓋 `create_root_and_theme()`，應 mock `tkinter.Tk` 與 `ttkbootstrap.Window`，或在無 display 時明確 skip，避免 headless CI 不穩。

### 14.2 GUI smoke test

可手測，不一定 CI 自動跑：

```powershell
cx-gui
```

檢查：

1. GUI 可啟動。
2. 沒有 ttkbootstrap 時可啟動。
3. 有 ttkbootstrap 時使用 modern theme。
4. Top bar、context bar、table、activity drawer 可正常顯示。
5. More menu 可正常開啟。
6. Activity / Log 可展開收合。
7. Doctor dialog 若已實作，視覺一致。

### 14.3 回歸測試

既有 CLI tests 必須通過：

```bash
python -m pytest
ruff check .
```

GUI 視覺改版不得影響：

```text
Refresh
Details
Best
Add
Use
Remove
Work / Personal
Export / Import / Inspect
Doctor UI
Activity / Log
```

## 15. README 更新需求

完成後更新 `README.md`：

1. Windows GUI 章節補充：GUI 會優先使用 modern Enterprise Light theme。
2. 說明若未安裝 `ttkbootstrap`，GUI 仍可 fallback 到標準 ttk。
3. 開發安裝補充 optional GUI theme：

```bash
python -m pip install -e ".[dev,gui]"
```

4. 不要把一般使用者安裝流程複雜化。`install.ps1` 仍是主要 Windows 安裝方式。

## 16. 驗收標準

### 16.1 視覺驗收

1. GUI 不再呈現標準 Tk 灰色原型感。
2. Top bar 有清楚層級與一致 spacing。
3. Context action bar 類似正式工具的 action area。
4. Table header、row、current row、error row 樣式清楚。
5. Activity / Log 有明確 collapsed / expanded 視覺差異。
6. Doctor dialog 視覺與主畫面一致。
7. 字體在 Windows 上清楚可讀。
8. 900px 寬度下不出現 top bar 水平捲動。

### 16.2 功能驗收

1. 有 `ttkbootstrap` 時 GUI 正常啟動。
2. 無 `ttkbootstrap` 時 GUI 仍正常啟動。
3. More menu 功能不受影響。
4. Context action enable / disable 不受影響。
5. Activity / Log 不受影響。
6. Doctor UI 不受影響。
7. `cx-gui` entrypoint 不受影響。

### 16.3 安裝驗收

Windows 傳統安裝：

```powershell
.\install.ps1
cx-gui
```

Editable install：

```bash
python -m pip install -e ".[dev,gui]"
cx-gui
```

Fallback test：

```bash
python -m pip uninstall ttkbootstrap
cx-gui
```

或在測試環境 mock import failure。

## 17. 分階段建議

### Phase 1：Theme infrastructure

- 新增 `ui_theme.py`。
- 加 `ttkbootstrap` detection。
- 建立 Enterprise Light tokens。
- GUI 可在 ttkbootstrap / ttk fallback 兩種模式啟動。

### Phase 2：主畫面視覺升級

- Top bar。
- Context action bar。
- Table style。
- Activity drawer。
- Button style。
- Badge style。

### Phase 3：Dialog 與 Doctor UI 視覺升級

- Doctor dialog。
- Login dialog。
- Backup inspect dialog。
- Error / warning message display。

### Phase 4：文件與驗收

- README。
- install.ps1 提示。
- manual smoke test。
- screenshots if applicable。

## 18. 完成定義

完成後，`cx-gui` 應維持原本所有功能，但外觀明顯從標準 Tkinter 工具升級為正式內部管理工具。

成功標準不是「變花俏」，而是：

1. 看起來穩定可信。
2. 層次清楚。
3. 資訊密度合理。
4. 使用者一眼知道目前環境、目前帳號、最佳帳號與下一步操作。
5. 沒有 `ttkbootstrap` 時仍不影響使用。
