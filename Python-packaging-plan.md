# codex-account-manager Python Packaging 規格書

## 1. 目的

目前 `codex-account-manager` 專案主要透過 `install.sh` 與 `install.ps1` 複製 `src/cx.py`、`gui/cx_gui.py` 並建立 launcher。這種方式可保留，但專案需要補上標準 Python packaging 設定，使其可以被 Python 工具鏈辨識、安裝、測試與維護。

本次任務目標是加入 `pyproject.toml`，讓專案支援：

```bash
pipx install git+https://github.com/michaelpo99/codex-account-manager.git
```

或在本機開發時支援：

```bash
pip install -e .
python -m pytest
ruff check .
```

本次不要求發布到 PyPI，但設計上應保留未來可發布的可能性。

## 2. 非目標

本次不要做以下事情：

1. 不移除 `install.sh`。
2. 不移除 `install.ps1`。
3. 不改變現有 CLI 指令行為。
4. 不改變帳號資料儲存位置。
5. 不改變 `auth.json`、`meta.json`、backup archive 格式。
6. 不大幅重構 `src/cx.py`。
7. 不把專案改成需要額外 runtime dependency。
8. 不要求立刻發布到 PyPI。

`pyproject.toml` 是補上標準 packaging 與工具設定，不是取代現有 installer。

## 3. 現有專案結構

目前主要檔案包含：

```text
README.md
AGENTS.md
codex-account-manager-SPEC.md
GUI-redesign-plan.md
install.sh
install.ps1
uninstall.sh
uninstall.ps1
src/cx.py
src/cx_ranking.py
gui/cx_gui.py
tests/
```

目前 CLI 入口是：

```bash
python3 src/cx.py
```

Windows GUI 入口是：

```bash
python gui/cx_gui.py
```

安裝後使用者可以執行：

```bash
cx
cx-gui
```

加入 `pyproject.toml` 後，仍應提供這兩個 console scripts：

```bash
cx
cx-gui
```

## 4. Packaging 設計原則

### 4.1 套件名稱

Python package / distribution 建議名稱：

```text
cx-account-manager
```

或：

```text
codex-account-manager
```

建議使用：

```text
cx-account-manager
```

理由是實際使用者指令是 `cx`，工具名稱短，避免和 OpenAI 官方 Codex CLI 混淆。若 Codex 認為使用 repo 名稱較直覺，也可以使用 `codex-account-manager`，但需在 README 中一致說明。

### 4.2 Python import package 名稱

建議建立 package：

```text
src/cx_account_manager/
```

未來較標準的結構應為：

```text
src/cx_account_manager/__init__.py
src/cx_account_manager/cli.py
src/cx_account_manager/gui.py
```

但本次不要大幅重構。第一階段可保守處理：

1. 保留 `src/cx.py`。
2. 保留 `src/cx_ranking.py`。
3. 新增一個輕量 package wrapper。
4. 讓 console scripts 呼叫現有 `cx.py` 的 `main()`。
5. 讓 `cx-gui` 呼叫現有 GUI 的 main 或 package 內等價入口。

`gui/cx_gui.py` 目前已經有 `main()` 與 `if __name__ == "__main__"` 入口，重點不是新增 main，而是確保 packaging 後 `cx-gui` 能 import 到 GUI 程式碼。

### 4.3 建議新增 wrapper 檔案

建議新增：

```text
src/cx_account_manager/__init__.py
src/cx_account_manager/cli.py
src/cx_account_manager/gui.py
```

其中 `cli.py` 可用最小 wrapper 呼叫現有 `src/cx.py`：

```python
from __future__ import annotations

from cx import main

__all__ = ["main"]
```

如果這種 import 因為 package 結構不穩定，請改為將現有 `src/cx.py` 複製或移動成：

```text
src/cx_account_manager/cx.py
```

然後在 repo root 保留相容 wrapper：

```text
src/cx.py
```

內容為：

```python
from cx_account_manager.cx import main

if __name__ == "__main__":
    raise SystemExit(main())
```

但第一階段以最小變更為原則，不要為了 packaging 進行過大搬移。

GUI 目前位於 repo root 的 `gui/cx_gui.py`，不在 `src/` package tree 內。若要讓 pipx / wheel 安裝後的 `cx-gui` 可用，必須採取其中一種做法：

1. 將 GUI 程式搬入 `src/cx_account_manager/gui_app.py`，並在 `gui/cx_gui.py` 保留相容 wrapper。
2. 或在 build 設定中明確包含 root `gui/`，但這比較不標準，console script import 也較脆弱。

建議採用第 1 種：把真正 GUI implementation 放進 package，保留 `gui/cx_gui.py` 作為 repo / installer 相容入口。

## 5. pyproject.toml 需求

請新增 `pyproject.toml`。

建議使用 `setuptools` 作為 build backend，避免引入 hatchling、poetry 等額外工具概念。

基本內容應包含：

```toml
[build-system]
requires = ["setuptools>=69", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "cx-account-manager"
version = "0.1.0"
description = "A Codex CLI account manager for switching and checking multiple Codex accounts."
readme = "README.md"
requires-python = ">=3.10"
license = { text = "MIT" }
authors = [
  { name = "Michael Po" }
]
keywords = ["codex", "cli", "account", "account-manager"]
classifiers = [
  "Programming Language :: Python :: 3",
  "Programming Language :: Python :: 3.10",
  "Programming Language :: Python :: 3.11",
  "Programming Language :: Python :: 3.12",
  "Operating System :: OS Independent",
  "Environment :: Console",
  "Topic :: Utilities"
]
dependencies = []

[project.optional-dependencies]
dev = [
  "pytest>=8",
  "ruff>=0.6",
  "mypy>=1.10"
]

[project.scripts]
cx = "cx_account_manager.cli:main"
cx-gui = "cx_account_manager.gui:main"

[tool.setuptools]
package-dir = {"" = "src"}
py-modules = ["cx", "cx_ranking"]

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]

[tool.ruff]
line-length = 140
target-version = "py310"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]
ignore = []

[tool.mypy]
python_version = "3.10"
ignore_missing_imports = true
warn_unused_ignores = false
check_untyped_defs = false
```

如果最後採用搬移後的 package 結構，`py-modules = ["cx", "cx_ranking"]` 可視情況移除。

## 6. 版本號需求

請在程式中加入版本號常數。

建議在 `src/cx.py` 中加入：

```python
APP_VERSION = "0.1.0"
```

並讓 `argparse` 支援：

```bash
cx --version
```

輸出：

```text
cx 0.1.0
```

`pyproject.toml` 的 version 與 `APP_VERSION` 第一階段可以手動保持一致，不需要導入 dynamic versioning。

若新增 package：

```text
src/cx_account_manager/__init__.py
```

可包含：

```python
__version__ = "0.1.0"
```

但避免產生多處版本不同步。若有多處版本號，需在註解中說明同步規則。

建議以 `src/cx_account_manager/__init__.py` 的 `__version__` 作為主要版本來源，`src/cx.py` 匯入該值為 `APP_VERSION`。若為了相容安裝器而保留單檔執行能力，需確保傳統 installer 同步複製 package wrapper 或改用 fallback 常數。

## 7. console scripts 需求

安裝後必須可執行：

```bash
cx --help
cx --version
cx manual --lang zh-TW
cx-gui
```

其中 `cx-gui` 若執行環境沒有 Tkinter，應給出合理錯誤訊息，不要造成難以理解的 traceback。

若 Tkinter import 失敗，錯誤訊息建議：

```text
cx-gui: Tkinter is not available in this Python environment.
Please install Python with Tkinter support, or use the CLI command `cx`.
```

此錯誤處理應放在 `cx_account_manager.gui` wrapper，不要讓匯入 CLI package 時就載入 Tkinter。

## 8. install.sh / install.ps1 相容需求

現有 installer 不可被破壞。

### 8.1 install.sh

`install.sh` 目前直接複製：

```text
src/cx.py
```

到：

```text
~/.local/share/cx/app/cx.py
```

這行為應維持可用。

如果程式搬移到 package 結構，必須同步調整 `install.sh`，確保傳統安裝仍可執行：

```bash
./install.sh
cx --help
```

### 8.2 install.ps1

`install.ps1` 目前會複製：

```text
src\cx.py
gui\cx_gui.py
```

到 `%LOCALAPPDATA%` 底下，並產生：

```text
cx.cmd
cx-gui.cmd
```

這行為應維持可用。

如果 GUI import path 因 packaging 改變，必須確保 `install.ps1` 安裝後仍可執行：

```powershell
cx --help
cx-gui
```

目前 installer 已經會複製 `src\cx.py`、`src\cx_ranking.py` 與 `gui\cx_gui.py`。若將 GUI implementation 搬入 package，Windows / Linux installer 也要同步複製 `src\cx_account_manager\`。

### 8.3 不要強迫使用 pipx

README 可以新增 pipx 安裝方式，但原有 shell / PowerShell installer 仍應保留。

## 9. README 更新需求

請更新 README，新增一節：

```markdown
## 標準 Python 安裝方式
```

內容包含：

### 9.1 pipx 從 GitHub 安裝

```bash
pipx install git+https://github.com/michaelpo99/codex-account-manager.git
```

### 9.2 pipx 更新

```bash
pipx upgrade cx-account-manager
```

或依實際 package 名稱調整。

### 9.3 pipx 移除

```bash
pipx uninstall cx-account-manager
```

### 9.4 本機開發安裝

```bash
python -m pip install -e ".[dev]"
python -m pytest
ruff check .
```

### 9.5 保留原 installer 說明

需明確說明：

```text
install.sh / install.ps1 仍保留，適合不熟悉 Python packaging 或需要 Windows PATH/Python 偵測協助的使用者。
```

## 10. 測試需求

新增或調整測試，至少涵蓋：

1. `cx --version` 可執行。
2. `cx manual --lang zh-TW` 可輸出。
3. `cx manual --lang en` 可輸出。
4. `python -m pytest` 全部通過。
5. console script wrapper 呼叫的是同一個 `main()`。
6. 若新增 package wrapper，import 不應破壞既有 tests。
7. 傳統 launcher 與 package console scripts 都應指向同一組實作，不要出現兩套 GUI 或 CLI 邏輯。

可新增測試檔：

```text
tests/test_package_entrypoints.py
```

測試內容可用直接 import 驗證：

```python
from cx_account_manager.cli import main
```

並確認 callable。

若測試 console script 實際安裝太麻煩，可不做 subprocess install 測試，先以 wrapper import 測試為主。

## 11. Ruff / formatting 需求

加入 ruff 設定後，先不要一次大規模格式化整個專案，以免造成 diff 過大。

最低要求：

```bash
ruff check .
```

若現有程式碼有大量 ruff 問題，可以先調整 `ignore`，讓專案能逐步導入。

本次任務重點是建立工具框架，不是一次完成所有 lint 修正。

## 12. mypy 需求

`mypy` 設定可先保守：

```toml
[tool.mypy]
ignore_missing_imports = true
check_untyped_defs = false
```

本次不要求 mypy 完全通過所有嚴格檢查。

若 mypy 問題過多，可以先只保留設定，不把 mypy 納入 CI 強制檢查。

## 13. GitHub Actions 建議

如果時間允許，新增：

```text
.github/workflows/test.yml
```

內容：

* checkout
* setup-python 3.10 / 3.11 / 3.12
* install dev dependencies
* run pytest
* run ruff check

但這是加分項，不是本次必要項。

若新增 CI，請確保不會因 Tkinter 缺失導致 GUI 測試在 Linux runner 失敗。GUI 測試應避免真的開視窗。

## 14. 驗收指令

完成後，以下指令應成功：

```bash
python -m pip install -e ".[dev]"
python -m pytest
ruff check .
python -m cx --help
```

若 `python -m cx` 不適用，可不要求，但若保留 `py-modules = ["cx"]`，建議讓它可用。以下必須成功：

```bash
cx --help
cx --version
cx manual --lang zh-TW
```

在 pipx 情境：

```bash
pipx install .
cx --version
cx manual --lang zh-TW
```

Windows 傳統 installer 情境：

```powershell
.\install.ps1
cx --version
cx manual --lang zh-TW
cx-gui
```

Linux / WSL 傳統 installer 情境：

```bash
./install.sh
cx --version
cx manual --lang zh-TW
```

## 15. 實作順序建議

請依下列順序執行：

1. 新增最小 `pyproject.toml`。
2. 新增 `src/cx_account_manager/` wrapper package。
3. 將 GUI implementation 納入 package，並保留 `gui/cx_gui.py` wrapper。
4. 新增 `APP_VERSION` 與 `cx --version`。
5. 執行既有 tests。
6. 補上 package entrypoint 測試。
7. 更新 README。
8. 確認 `install.sh` / `install.ps1` 仍可用。
9. 如有時間，再加 GitHub Actions。

## 16. 注意事項

1. 不要讓 packaging 改動導致 Windows GUI 找不到 `cx.py`。
2. 不要讓 `cx-gui` 在沒有 Tkinter 的環境中導致 CLI import 失敗。
3. 不要新增不必要 runtime dependencies。
4. 不要把 dev dependencies 放進正式 dependencies。
5. 不要提交任何 `auth.json`、backup archive、token 或本機帳號資料。
6. 若修改檔案路徑，請同步更新 README、install scripts、tests。
7. 完成後請列出實際改動檔案與測試結果。

## 17. 預期成果

完成後，專案仍可用原本方式安裝：

```bash
./install.sh
```

```powershell
.\install.ps1
```

同時也支援標準 Python 工具鏈：

```bash
pipx install git+https://github.com/michaelpo99/codex-account-manager.git
```

並可透過版本號、console scripts、pytest、ruff 等工具進行較正式的維護。

這次改版的核心價值是讓 `cx` 從「可用腳本」升級成「可安裝、可測試、可版本化、可交付給同仁使用的 Python 工具」。
