# CX Account Manager UI 改版需求文件

## 1. 改版目的

目前 `cx-gui` 功能完整，但畫面配置偏向工程原型。主要問題是上方功能列過長、按鈕過多、視窗寬度不容易縮小，下方 Log 區域預設佔用大量空間但平常幾乎沒有資訊。此次改版目標是讓 GUI 更適合日常使用，讓帳號表格成為主畫面核心，常用操作容易找到，低頻功能收納起來，Log 僅在需要時顯示。

本次改版以現有 Tkinter GUI 為基礎，不重寫成其他 GUI framework，不改 CLI 指令行為，不改 `cx.py` 的核心帳號管理邏輯。必要時可新增 GUI 輔助函式與 UI 狀態管理。

## 2. 改版目標

新版 GUI 應達成以下目標：

1. 移除目前過長的 Ribbon toolbar，改成精簡工具列。
2. 視窗寬度縮小時不應出現主要操作列水平捲動。
3. 帳號表格應佔據主要可視空間。
4. 選取帳號後，才顯示或啟用與該帳號相關的操作。
5. 備份、匯入、檢查、進階功能應收納至 `More` 或下拉選單。
6. Log / Activity 預設收合，不再佔用畫面大區塊。
7. 執行長時間操作、登入流程、匯入匯出、錯誤診斷時，Log 才展開或提示可展開。
8. 介面風格應更簡潔，減少粗重邊框與過多圖示。
9. 保留 Windows Native / WSL / 指定 WSL distro 的 Environment 切換能力。
10. 不影響現有 CLI 功能、資料格式、備份格式與帳號儲存位置。

## 3. 非目標

本次不處理以下事項：

1. 不改寫 CLI 指令格式。
2. 不改 `auth.json` 儲存結構。
3. 不改 `cx status`、`cx best` 的排序邏輯。
4. 不新增 Web UI。
5. 不新增資料庫。
6. 不要求支援深色模式。
7. 不要求跨平台 GUI 完整支援，仍以 Windows GUI 為主要目標。

## 4. 目前 UI 問題

### 4.1 上方 Ribbon 過長

目前所有功能都放在第一層，包括：

* Refresh
* Status
* Add Account
* Save Current
* Use Selected
* Best
* Status Selected
* Remove
* Work
* Personal
* Export All
* Export Selected
* Export Filtered
* Import
* Inspect

這造成按鈕過多、視窗寬度無法縮小，並且所有功能看起來同等重要，缺乏主次層級。

### 4.2 Log 區域預設佔用太多空間

目前下半部 Log 區域大多時間是空白，卻佔用約半個視窗高度。這使帳號表格可視高度不足，也讓主畫面看起來鬆散。

### 4.3 主表格不夠突出

此工具的核心用途是查看帳號狀態、比較 5h / 7d 額度、選擇帳號並切換。主表格應是畫面中心，目前卻被 toolbar 與 log panel 擠壓。

### 4.4 視覺層級不清楚

目前 TARGET 文字過於醒目，按鈕圖示與文字佔比過高，表格、工具列、狀態列的層級不明確。

## 5. 新版整體版面

新版 GUI 採用以下結構：

```text
+-------------------------------------------------------------+
| CX Account Manager                                          |
+-------------------------------------------------------------+
| Environment [ Windows Native v ]       Refresh Details Best |
|                                      Add  More v            |
+-------------------------------------------------------------+
| 選取 1 個帳號（Rank 1 · michaelpo）     Use Remove Work ... |
+-------------------------------------------------------------+
| Account Table                                                |
|                                                             |
| Rank | Alias | Scope | Email | Plan | 5h | 7d | Error        |
|                                                             |
|                                                             |
+-------------------------------------------------------------+
| Activity / Log (optional)                         Show details |
+-------------------------------------------------------------+
```

## 6. Top Toolbar 需求

### 6.1 工具列內容

第一層工具列只保留高頻功能：

* Auth Environment dropdown
* Refresh
* Details
* Best
* Add
* More

### 6.2 Auth Environment 區塊

置中顯示，字體比一般 label 大一號並使用粗體：

```text
Auth Environment
[ Windows Native v ]
```

可選項維持現有動態偵測結果：

* Windows Native
* WSL: `<distro name>`
* WSL fallback（偵測不到 distro 或舊設定值時，代表 Windows 預設 WSL distro）

不再使用紅色大字 `TARGET`。改用一般 label，避免過度搶眼。

切換 Auth Environment 後，status bar 應提示接下來的操作會影響該環境的 `CODEX_HOME/auth.json`。`Use` / `Remove` 這類會切換 auth 或刪除資料的確認訊息，也應帶入目前 Auth Environment。

### 6.3 常用操作按鈕

右側顯示 compact buttons：

```text
Refresh | Details | Best | Add | More v
```

按鈕應盡量維持單行文字，不再使用大型圖示加兩行文字。可以保留小圖示，但圖示不是必要條件。若保留圖示，需統一尺寸與風格。

`Refresh` 負責重新載入帳號表格與 `status --json` 資訊；`Details` 顯示 CLI 文字格式的 `cx status` 輸出，避免和 Refresh 語意混淆。

### 6.4 More 選單

`More` 選單收納低頻或進階功能：

* Save Current
* Status Selected / Details Selected
* Export All
* Export Filtered
* Import
* Inspect Backup
* Open Data Folder（可延後）
* Open Log / Activity
* About / Help（可延後）

若目前沒有 `Open Data Folder` 或 `About / Help`，可以先不做，但 More 選單結構需預留。

## 7. Contextual Action Bar 需求

### 7.1 顯示位置

在 top toolbar 下方新增一條 contextual action bar。

當使用者未選取帳號時，顯示：

```text
尚未選取帳號
```

操作按鈕 disable 或隱藏。

當使用者選取 1 個帳號時，顯示：

```text
選取 1 個帳號（Rank 1 · michaelpo）
```

右側顯示可用操作：

* Use
* Remove
* Work
* Personal
* Export

當使用者選取多個帳號時，顯示：

```text
選取 N 個帳號
```

右側只顯示適合多選的操作：

* Export
* Remove
* Work
* Personal

`Use`、`Details` 只支援單一帳號，多選時應 disable 或隱藏。`Work`、`Personal`、`Remove`、`Export` 支援批次操作。

### 7.2 Contextual Actions 行為

`Use`：對目前選取的單一帳號執行 `cx use <alias>`。

`Remove`：支援單選與多選。多選時需逐一刪除並處理部分成功 / 部分失敗。

`Work`：對選取帳號執行 `cx scope <alias> work`。多選時逐一執行。

`Personal`：對選取帳號執行 `cx scope <alias> personal`。多選時逐一執行。

`Export`：若單選或多選，執行 selected export。可以提供下拉選項：

* Export Selected
* Export All
* Export Filtered

## 8. Account Table 需求

### 8.1 表格為主畫面核心

帳號表格應佔用主要高度。新版不應讓 Log 預設佔據大量空間。

建議配置：

* Top toolbar 高度約 56 px
* Contextual action bar 高度約 48 px
* Account table 佔剩餘大部分高度
* Log collapsed strip 高度約 44 px

### 8.2 欄位

表格保留以下欄位：

* Select checkbox
* Current marker
* Rank
* Alias
* Scope
* Email
* Plan
* 5h
* 7d
* Error

其中 Current marker 可以使用 `*`、星號、勾選標記或淡色 badge。重點是目前使用帳號要比現在更容易辨識。

Tkinter `Treeview` 原生不支援真正的 checkbox。Phase 1 可以沿用目前多選 selection，不必先做 checkbox；若要加入視覺 checkbox，建議放到 Phase 3，避免表格互動複雜化。

### 8.3 5h / 7d 顯示格式

目前格式可以保留：

```text
3% used | 06-18 23:58
```

但建議在 UI 中換成兩行顯示：

```text
3% used
06-18 23:58
```

這樣欄位寬度較容易控制，表格也比較整齊。

若 `Treeview` 在不同 Windows 字體下換行效果不穩，Phase 1 可先保留單行短格式，優先完成版面重排；兩行格式放到 Phase 3 驗證。

### 8.4 Row selection

單擊 row 時選取帳號，contextual action bar 應立即更新。

雙擊 row 是否執行 `Use Selected` 需謹慎。Phase 1 建議先不新增雙擊切換，避免誤觸；若後續保留雙擊切換，應在 tooltip 或狀態提示中說明。

### 8.5 空白區域

帳號只有少數幾列時，表格下方可以空白，但這個空白應屬於表格本身，不應被 Log panel 佔用。

## 9. Activity / Log 需求

### 9.1 預設收合

Log 不應預設展開。底部只顯示一條 collapsed strip：

```text
Activity / Log (optional)                         Show details
平常可不顯示；僅在執行操作或發生錯誤時展開
```

### 9.2 何時需要 Log

Log 不是日常主畫面必要資訊。它主要用於以下情境：

1. 新增帳號登入流程
   需要顯示 device auth 網址、認證碼、登入進度、錯誤訊息。

2. 匯入 / 匯出
   需要顯示輸出檔案路徑、匯入帳號數、跳過或覆蓋哪些 alias。

3. 備份檢查
   `Inspect Backup` 或 `backup-list` 需要顯示備份內容摘要。

4. 錯誤診斷
   例如找不到 codex、token revoked、app-server timeout、WSL path 問題。

5. 長時間操作
   例如 `cx status` 查多帳號時，可顯示正在查詢中或完成訊息。

### 9.3 自動展開規則

建議採用以下規則：

* 使用者按 `Show details` 時手動展開。
* 發生錯誤時自動展開。
* 新增帳號登入流程自動展開或開啟登入 dialog。
* 匯入 / 匯出完成後若成功，不一定自動展開，只在 status bar 顯示結果。
* 匯入 / 匯出失敗時自動展開。
* `Refresh` 成功時只更新表格，不展開。
* `Details` 成功時可展開 Log，因為使用者明確要求看 CLI 輸出。
* `Best` 成功時不展開，只刷新表格並在 status bar 顯示切換結果。

### 9.4 展開後行為

展開後 Log panel 高度建議為 160–220 px。使用者可以收合，也應可拖曳表格與 Activity / Log 之間的分隔線調整高度。若現有 `PanedWindow` 可保留，需將預設 sash 位置改為幾乎收合，而非佔半個畫面。

## 10. Status Bar 需求

應保留輕量狀態提示，但不要佔用太多空間。

可顯示：

* Ready
* Loading accounts...
* Reading status...
* Switched to michaelpo
* Exported 3 accounts
* Error: codex not found

Status bar 可放在 top toolbar 右側或底部 log strip 附近。

`Best` 成功後應顯示明確訊息，例如 `Switched to michaelpo`，並刷新表格讓 current marker 立即更新。

## 11. 視覺風格需求

### 11.1 整體風格

* Light theme
* 白底
* 淺灰分隔線
* 藍色只用於選取狀態與重要提示
* 減少粗框線
* 減少過多圖示
* 按鈕尺寸比現在更小
* 不使用大型 Ribbon group 標題

### 11.2 字體與間距

* 表格字體維持清楚可讀
* Toolbar 按鈕使用單行文字
* 區塊間距一致
* 表格 header 與 row 高度保持穩定

### 11.3 選取狀態

選取 row 使用淡藍底。Current account 可用星號、badge 或粗體提示，但不要只靠最左側 `*`，因為不夠明顯。

## 12. 視窗縮放需求

新版 UI 應支援較小寬度。

最低合理寬度目標：

```text
約 900px
```

當寬度不足時：

1. Top toolbar 不應產生水平捲動。
2. 低頻功能應已收進 More。
3. 表格欄位可以水平捲動，但 toolbar 不應水平捲動。
4. Email / Error 欄位可伸縮。
5. 5h / 7d 欄位維持固定寬度或中等寬度。

## 13. More 選單細節

More 選單建議內容：

```text
Save Current
Details Selected
---
Export All
Export Filtered
Import
Inspect Backup
---
Show Activity / Log
---
Help / Manual
```

若現階段不做 Help / Manual，可先保留但 disable，或不顯示。

## 14. 右鍵選單需求

帳號表格 row 建議新增右鍵選單。

單一帳號右鍵：

```text
Use
Details
Mark as Work
Mark as Personal
Export
Remove
```

多選帳號右鍵：

```text
Export Selected
Remove Selected
```

右鍵選單不是必要第一階段，但建議納入第二階段。

## 15. 鍵盤操作建議

可加入基本快捷鍵：

* F5：Refresh
* Ctrl+D：Details
* Enter：Use selected account
* Delete：Remove selected account
* Ctrl+E：Export selected
* Ctrl+L：Toggle Activity / Log

若要降低改版範圍，可以先不做快捷鍵。

## 16. 實作建議

### 16.1 建議修改檔案

主要修改：

```text
gui/cx_gui.py
```

可能需要小幅新增：

```text
gui/ui_helpers.py
```

但第一階段可以只改 `gui/cx_gui.py`。

### 16.2 建議重構方向

目前 GUI 的 `_build_ui()` 建立了 Ribbon、PanedWindow、Treeview、Log 等。建議拆成：

```python
build_top_toolbar()
build_context_action_bar()
build_account_table()
build_activity_log_panel()
build_more_menu()
```

這樣後續維護較容易。

### 16.3 移除或弱化 Ribbon

目前 Ribbon 相關函式若不再需要，可以逐步移除：

* create_ribbon_group
* add_ribbon_separator
* ribbon_button_text
* on_ribbon_mousewheel
* bind_ribbon_mousewheel
* ribbon canvas horizontal scroll

新版不應依賴 ribbon horizontal scroll。

### 16.4 Log panel

將目前固定顯示的 ScrolledText 改成可收合 panel。

需要狀態：

```python
self.log_expanded = BooleanVar(value=False)
```

需要操作：

```python
toggle_log_panel()
show_log_panel()
hide_log_panel()
```

當 log 收合時，隱藏 ScrolledText，只保留底部 strip。

### 16.5 Context action bar

需要在 Treeview selection change 時更新：

```python
self.tree.bind("<<TreeviewSelect>>", self.on_selection_changed)
```

`on_selection_changed()` 需更新：

* selected count label
* selected alias label
* Use button enabled / disabled
* Work / Personal button enabled / disabled
* Export button enabled / disabled
* Remove button enabled / disabled

## 17. 驗收標準

### 17.1 畫面驗收

1. 啟動 `cx-gui` 後，上方不再出現長 Ribbon。
2. 視窗縮到約 900px 寬時，top toolbar 不需要水平捲動。
3. 帳號表格佔據主要畫面高度。
4. 下方 Log 預設收合。
5. 選取帳號後，contextual action bar 顯示目前選取帳號與可用操作。
6. 未選取帳號時，Use / Remove / Work / Personal 等操作不可直接執行。
7. More 選單可看到低頻功能。

### 17.2 功能驗收

1. Refresh 可正常更新帳號清單。
2. Details 可正常顯示 CLI 文字格式的 `cx status` 輸出。
3. Best 可正常切換最佳帳號並刷新表格。
4. Add 可正常啟動新增帳號流程。
5. Use 可正常切換選取帳號。
6. Work / Personal 可正常更新 scope。
7. Export selected 可正常匯出選取帳號。
8. Import / Inspect Backup 從 More 選單可正常執行。
9. 發生錯誤時 Log / Activity 可自動展開或提示使用者展開。
10. 成功的簡單操作不應強制展開 Log。

### 17.3 回歸驗收

以下既有 CLI 行為不得受影響：

```bash
cx list
cx status
cx best
cx use <alias>
cx add <alias>
cx save <alias>
cx scope <alias> work
cx scope <alias> personal
cx export
cx import
cx backup-list
```

既有 unit tests 應全部通過。

## 18. 建議分階段實作

### Phase 1：版面骨架與主流程

* 移除 Ribbon 長工具列
* 新增 compact top toolbar
* 新增 contextual action bar
* 建立 More 選單，先收納低頻功能
* 表格佔滿主要空間
* Log 預設收合
* Treeview selection state 更新 contextual action bar
* 保留現有 Environment 動態選項，包括 `Windows Native`、`WSL: <distro>`、legacy `WSL`
* 保留現有 CLI runner 行為，不改 command 行為

### Phase 2：操作細節與錯誤處理

* Export 下拉選單
* 多選 Export 流程整理
* 多選 Remove（需確認訊息與部分失敗處理）
* 錯誤時自動展開 Log
* status bar 訊息整理
* Details / Details Selected 與 Activity Log 的呈現整理

### Phase 3：細節優化

* 右鍵選單
* 快捷鍵
* Current account 更明顯
* 表格欄位寬度最佳化
* 5h / 7d 兩行顯示驗證
* Treeview checkbox 或更明確的選取視覺
* 視覺細節微調

## 19. 實作注意事項

1. 不要為了 UI 改版改動 CLI 邏輯。
2. GUI 仍應透過現有 `CxRunner` 呼叫 CLI。
3. Windows Native / WSL / 指定 WSL distro 的 Environment 切換邏輯需保留。
4. 不要讓備份檔、auth.json、token 類資訊顯示在一般畫面。
5. Log 裡若有敏感資訊，應避免顯示完整 token 或 auth.json 內容。
6. 若操作失敗，錯誤訊息應保留足夠診斷資訊，但不要暴露登入憑證。
7. 改版後 README 的 GUI 截圖與說明需同步更新。

## 20. 預期成果

改版後的 `cx-gui` 應從「所有功能攤開的工程工具」變成「帳號狀態一眼可讀、常用操作清楚、進階功能收納得當」的日常使用工具。

核心畫面應讓使用者一打開就能完成三件事：

1. 看現在有哪些帳號與額度狀態。
2. 判斷目前最適合用哪個帳號。
3. 快速切換帳號。

其他功能如備份、匯入、檢查、Log，應保留但不干擾日常主流程。
