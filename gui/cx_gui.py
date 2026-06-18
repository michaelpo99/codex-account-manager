#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import re
import shutil
import shlex
import subprocess
import sys
import threading
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from tkinter import BooleanVar, PanedWindow, StringVar, Tk, Toplevel, filedialog, messagebox, simpledialog, ttk
from tkinter.scrolledtext import ScrolledText


APP_TITLE = "cx Account Manager"
TIMEOUT_SEC = 45
ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
URL_RE = re.compile(r"https?://[^\s\x1b]+")
DEVICE_CODE_RE = re.compile(
    r"(?i)\b(?:one-time\s+code|device\s+code|user\s+code|verification\s+code|code)\b"
    r"(?:\s+(?:is|=))?[\s:]+"
    r"([A-Z0-9]{4,8}(?:-[A-Z0-9]{4,8}){1,3}|[A-Z0-9]{6,12})\b"
)
DEVICE_CODE_TOKEN_RE = re.compile(r"\b[A-Z0-9]{4,8}(?:-[A-Z0-9]{4,8}){1,3}\b")


@dataclass
class CommandResult:
    args: list[str]
    display: str
    returncode: int
    stdout: str
    stderr: str


@dataclass
class AccountRow:
    alias: str
    current: bool = False
    email: str | None = None
    plan: str | None = None
    primary_used: int | None = None
    primary_reset: str | None = None
    secondary_used: int | None = None
    secondary_reset: str | None = None
    error: str | None = None


class CxRunner:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root
        self.src_cx = repo_root / "src" / "cx.py"
        if not self.src_cx.exists():
            self.src_cx = repo_root / "cx.py"

    def base_command(self, target: str) -> list[str]:
        if target == "WSL":
            return ["wsl.exe", "bash", "-lic"]
        return [sys.executable, str(self.src_cx)]

    def command(self, target: str, args: list[str]) -> list[str]:
        if target == "WSL":
            return self.base_command(target) + [self.wsl_command_script(args)]
        return self.base_command(target) + args

    def wsl_repo_path(self) -> str:
        src = str(self.repo_root).replace("\\", "/")
        drive_match = re.match(r"^([A-Za-z]):/(.*)$", src)
        if drive_match:
            drive = drive_match.group(1).lower()
            rest = drive_match.group(2)
            return f"/mnt/{drive}/{rest}"
        return src

    def wsl_command_script(self, args: list[str]) -> str:
        quoted_repo = shlex.quote(self.wsl_repo_path())
        quoted_args = " ".join(shlex.quote(arg) for arg in args if arg)
        return (
            "export NVM_DIR=\"$HOME/.nvm\"; "
            "[ -s \"$NVM_DIR/nvm.sh\" ] && . \"$NVM_DIR/nvm.sh\" >/dev/null 2>&1 || true; "
            "for f in ~/.profile ~/.bash_profile ~/.bashrc ~/.zshrc; do "
            "[ -f \"$f\" ] && . \"$f\" >/dev/null 2>&1 || true; "
            "done; "
            "[ -s \"$NVM_DIR/nvm.sh\" ] && . \"$NVM_DIR/nvm.sh\" >/dev/null 2>&1 || true; "
            f"cd {quoted_repo} || exit 1; "
            "export PYTHONUNBUFFERED=1; "
            f"if [ -f ./src/cx.py ]; then exec python3 -u ./src/cx.py {quoted_args}; fi; "
            f"exec python3 -u ./cx.py {quoted_args}"
        )

    def display_command(self, target: str, args: list[str]) -> str:
        if target == "WSL":
            return "wsl.exe cx " + " ".join(shlex.quote(arg) for arg in args)
        return subprocess.list2cmdline(self.command(target, args))

    def subprocess_env(self, target: str) -> dict[str, str]:
        env = os.environ.copy()
        if target == "Windows Native":
            env["PYTHONUTF8"] = "1"
            env["PYTHONIOENCODING"] = "utf-8"
            env["PYTHONUNBUFFERED"] = "1"
        return env

    def run(self, target: str, args: list[str], timeout: int = TIMEOUT_SEC) -> CommandResult:
        cmd = self.command(target, args)
        display = self.display_command(target, args)
        try:
            completed = subprocess.run(
                cmd,
                env=self.subprocess_env(target),
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=timeout,
                check=False,
            )
            return CommandResult(cmd, display, completed.returncode, completed.stdout, completed.stderr)
        except FileNotFoundError as exc:
            return CommandResult(cmd, display, 127, "", f"{exc}\n")
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout if isinstance(exc.stdout, str) else ""
            stderr = exc.stderr if isinstance(exc.stderr, str) else ""
            return CommandResult(cmd, display, 124, stdout, stderr + f"Command timed out after {timeout} seconds.\n")

    def popen_stream(self, target: str, args: list[str]) -> subprocess.Popen[str]:
        cmd = self.command(target, args)
        return subprocess.Popen(
            cmd,
            cwd=str(self.repo_root),
            env=self.subprocess_env(target),
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            bufsize=1,
        )


class AliasDialog(simpledialog.Dialog):
    def __init__(self, parent: Tk, title: str, action_label: str) -> None:
        self.action_label = action_label
        self.alias_var = StringVar()
        self.force_var = BooleanVar(value=False)
        self.result: tuple[str, bool] | None = None
        super().__init__(parent, title)

    def body(self, master: ttk.Frame) -> ttk.Entry:
        ttk.Label(master, text="Alias").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=(0, 8))
        entry = ttk.Entry(master, textvariable=self.alias_var, width=32)
        entry.grid(row=0, column=1, sticky="ew", pady=(0, 8))
        ttk.Checkbutton(master, text="Force overwrite", variable=self.force_var).grid(row=1, column=1, sticky="w")
        master.columnconfigure(1, weight=1)
        return entry

    def buttonbox(self) -> None:
        box = ttk.Frame(self)
        ttk.Button(box, text=self.action_label, command=self.ok).pack(side="left", padx=4, pady=8)
        ttk.Button(box, text="Cancel", command=self.cancel).pack(side="left", padx=4, pady=8)
        box.pack()

    def validate(self) -> bool:
        alias = self.alias_var.get().strip()
        if not alias:
            messagebox.showerror(APP_TITLE, "Alias is required.", parent=self)
            return False
        self.result = (alias, self.force_var.get())
        return True


class LoginDialog:
    def __init__(self, parent: Tk, runner: CxRunner, target: str, alias: str, force: bool, on_done) -> None:
        self.parent = parent
        self.runner = runner
        self.target = target
        self.alias = alias
        self.force = force
        self.on_done = on_done
        self.proc: subprocess.Popen[str] | None = None
        self.finished = False
        self.stream_output_seen = False

        self.window = Toplevel(parent)
        self.window.title(f"Add Account: {alias}")
        self.window.geometry("760x460")
        self.window.columnconfigure(0, weight=1)
        self.window.rowconfigure(1, weight=1)
        self.window.protocol("WM_DELETE_WINDOW", self.close_or_cancel)

        self.status_var = StringVar(value="Starting login...")
        ttk.Label(self.window, textvariable=self.status_var, padding=10).grid(row=0, column=0, sticky="ew")

        self.output = ScrolledText(self.window, wrap="word", height=18)
        self.output.grid(row=1, column=0, sticky="nsew", padx=10)
        self.output.tag_configure("link", foreground="#0b63ce", underline=True)
        self.output.tag_configure("copy", foreground="#0b63ce", underline=True)
        self.output.tag_bind("link", "<Enter>", lambda _event: self.output.configure(cursor="hand2"))
        self.output.tag_bind("link", "<Leave>", lambda _event: self.output.configure(cursor=""))
        self.output.tag_bind("copy", "<Enter>", lambda _event: self.output.configure(cursor="hand2"))
        self.output.tag_bind("copy", "<Leave>", lambda _event: self.output.configure(cursor=""))
        self.link_count = 0

        buttons = ttk.Frame(self.window, padding=10)
        buttons.grid(row=2, column=0, sticky="ew")
        buttons.columnconfigure(0, weight=1)
        self.close_button = ttk.Button(buttons, text="Cancel", command=self.close_or_cancel)
        self.close_button.grid(row=0, column=1)

        self.start()

    def start(self) -> None:
        args = ["add"]
        if self.force:
            args.append("--force")
        args.append(self.alias)
        self.append("$ " + self.runner.display_command(self.target, args) + "\n")
        self.append("Waiting for Codex login output...\n")

        def worker() -> None:
            exit_code = 1
            try:
                self.proc = self.runner.popen_stream(self.target, args)
                assert self.proc.stdout is not None
                buffer = ""
                while True:
                    chunk = self.proc.stdout.read(1)
                    if not chunk:
                        break
                    self.stream_output_seen = True
                    buffer += chunk
                    if chunk in {"\n", "\r"} or len(buffer) >= 120:
                        self.parent.after(0, self.append, buffer)
                        buffer = ""
                if buffer:
                    self.parent.after(0, self.append, buffer)
                exit_code = self.proc.wait()
            except OSError as exc:
                self.parent.after(0, self.append, f"{exc}\n")
            self.parent.after(0, self.finish, exit_code)

        threading.Thread(target=worker, daemon=True).start()

    def append(self, text: str) -> None:
        clean_text = ANSI_RE.sub("", text)

        spans: list[tuple[int, int, str, str]] = []
        for match in URL_RE.finditer(clean_text):
            url = match.group(0).rstrip(".,;)")
            spans.append((match.start(), match.start() + len(url), url, "url"))
        for match in DEVICE_CODE_RE.finditer(clean_text):
            code = match.group(1)
            spans.append((match.start(1), match.end(1), code, "code"))
        for match in DEVICE_CODE_TOKEN_RE.finditer(clean_text):
            code = match.group(0)
            spans.append((match.start(), match.end(), code, "code"))
        spans.sort(key=lambda item: item[0])

        position = 0
        for start, end, value, kind in spans:
            if start < position:
                continue
            self.output.insert("end", clean_text[position:start])
            tag_prefix = "link" if kind == "url" else "copy"
            tag = f"{tag_prefix}-{self.link_count}"
            self.link_count += 1
            if kind == "url":
                self.output.insert("end", clean_text[start:end], ("link", tag))
                self.output.tag_bind(tag, "<Button-1>", lambda _event, link=value: webbrowser.open(link))
            else:
                self.output.insert("end", clean_text[start:end])
                self.output.insert("end", " [複製]", ("copy", tag))
                self.output.tag_bind(tag, "<Button-1>", lambda _event, code=value: self.copy_code(code))
                self.status_var.set(f"Code ready: {value}")
            position = end
        self.output.insert("end", clean_text[position:])
        self.output.see("end")

    def copy_code(self, code: str) -> None:
        self.window.clipboard_clear()
        self.window.clipboard_append(code)
        self.window.update()
        self.status_var.set(f"Copied code: {code}")

    def finish(self, exit_code: int) -> None:
        self.finished = True
        if not self.stream_output_seen:
            self.append("\nNo login output was captured from the subprocess.\n")
        self.append(f"\nCommand finished with exit code {exit_code}.\n")
        self.status_var.set("Login completed" if exit_code == 0 else "Login failed")
        self.close_button.configure(text="Close")
        self.on_done(exit_code)

    def close_or_cancel(self) -> None:
        if not self.finished and self.proc and self.proc.poll() is None:
            self.proc.terminate()
            self.status_var.set("Cancelling...")
            return
        self.window.destroy()


class CxGui:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("980x640")
        self.repo_root = Path(__file__).resolve().parents[1]
        self.runner = CxRunner(self.repo_root)
        self.target_var = StringVar(value="WSL")
        self.status_var = StringVar(value="Ready")
        self.accounts: dict[str, AccountRow] = {}

        self._build_ui()
        self.refresh_accounts()

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(self.root, padding=10)
        toolbar.grid(row=0, column=0, sticky="ew")
        toolbar.columnconfigure(4, weight=1)

        ttk.Label(toolbar, text="Target").grid(row=0, column=0, padx=(0, 8))
        target = ttk.Combobox(toolbar, textvariable=self.target_var, values=["WSL", "Windows Native"], state="readonly", width=18)
        target.grid(row=0, column=1, padx=(0, 8))
        target.bind("<<ComboboxSelected>>", lambda _event: self.refresh_accounts())
        ttk.Button(toolbar, text="Refresh", command=self.refresh_accounts).grid(row=0, column=2, padx=(0, 8))
        ttk.Button(toolbar, text="Status", command=self.refresh_status_all).grid(row=0, column=3, padx=(0, 8))
        ttk.Label(toolbar, textvariable=self.status_var).grid(row=0, column=4, sticky="e")

        main_pane = PanedWindow(self.root, orient="vertical", sashrelief="flat", sashwidth=6, opaqueresize=True, bd=0, relief="flat")
        main_pane.grid(row=1, column=0, sticky="nsew")

        upper = ttk.Frame(main_pane, padding=(10, 0, 10, 0))
        lower = ttk.Frame(main_pane, padding=(10, 0, 10, 10))
        main_pane.add(upper, minsize=180)
        main_pane.add(lower, minsize=120)

        upper.columnconfigure(0, weight=1)
        upper.rowconfigure(0, weight=1)
        lower.columnconfigure(0, weight=1)
        lower.rowconfigure(0, weight=1)

        columns = ("current", "alias", "email", "plan", "primary", "secondary", "error")
        self.tree = ttk.Treeview(upper, columns=columns, show="headings", selectmode="browse")
        headings = {
            "current": "*",
            "alias": "Alias",
            "email": "Email",
            "plan": "Plan",
            "primary": "5h",
            "secondary": "7d",
            "error": "Error",
        }
        widths = {"current": 42, "alias": 150, "email": 240, "plan": 110, "primary": 140, "secondary": 140, "error": 220}
        for column, heading in headings.items():
            self.tree.heading(column, text=heading)
            self.tree.column(column, width=widths[column], anchor="w", stretch=column in {"email", "error"})
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree.bind("<Double-1>", lambda _event: self.use_selected())

        buttons = ttk.Frame(upper, padding=(0, 8))
        buttons.grid(row=1, column=0, sticky="ew")
        ttk.Button(buttons, text="Use Selected", command=self.use_selected).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="Status Selected", command=self.refresh_status_selected).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="Add Account", command=self.add_account).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="Save Current", command=self.save_current).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="Remove Selected", command=self.remove_selected).pack(side="left", padx=(0, 8))

        self.output = ScrolledText(lower, height=10, wrap="word")
        self.output.grid(row=0, column=0, sticky="nsew")
        self.root.after_idle(lambda: main_pane.sash_place(0, 0, 420))

    def selected_alias(self) -> str | None:
        selection = self.tree.selection()
        if not selection:
            return None
        return str(selection[0])

    def log(self, text: str) -> None:
        self.output.insert("end", text)
        if not text.endswith("\n"):
            self.output.insert("end", "\n")
        self.output.see("end")

    def set_busy(self, text: str) -> None:
        self.status_var.set(text)

    def run_background(self, label: str, args: list[str], callback, timeout: int = TIMEOUT_SEC) -> None:
        target = self.target_var.get()
        self.set_busy(f"{label}...")

        def worker() -> None:
            result = self.runner.run(target, args, timeout=timeout)
            self.root.after(0, lambda: callback(result))

        threading.Thread(target=worker, daemon=True).start()

    def refresh_accounts(self) -> None:
        self.run_background("Refreshing accounts", ["list", "--json"], self.on_accounts_loaded)

    def on_accounts_loaded(self, result: CommandResult) -> None:
        self.log_command_result(result)
        if result.returncode != 0:
            self.set_busy("Refresh failed")
            return
        try:
            payload = json.loads(result.stdout or "{}")
        except json.JSONDecodeError as exc:
            self.log(f"JSON parse error: {exc}")
            self.set_busy("Refresh failed")
            return

        self.accounts = {}
        for item in payload.get("accounts", []):
            row = AccountRow(alias=item["alias"], current=bool(item.get("current")))
            self.accounts[row.alias] = row
        self.render_accounts()
        self.set_busy("Ready")

    def refresh_status_all(self) -> None:
        self.run_background("Reading status", ["status", "--json"], self.on_status_loaded, timeout=90)

    def refresh_status_selected(self) -> None:
        alias = self.selected_alias()
        if not alias:
            messagebox.showinfo(APP_TITLE, "Select an account first.", parent=self.root)
            return
        self.run_background(f"Reading {alias}", ["status", alias, "--json"], self.on_status_loaded, timeout=90)

    def on_status_loaded(self, result: CommandResult) -> None:
        self.log_command_result(result)
        if not result.stdout.strip():
            self.set_busy("Status failed")
            return
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            self.log(f"JSON parse error: {exc}")
            self.set_busy("Status failed")
            return

        current_alias = payload.get("current")
        for row in self.accounts.values():
            row.current = row.alias == current_alias
        for item in payload.get("accounts", []):
            row = AccountRow(
                alias=item["alias"],
                current=bool(item.get("current")),
                email=item.get("email"),
                plan=item.get("plan"),
                primary_used=item.get("primary_used"),
                primary_reset=item.get("primary_reset"),
                secondary_used=item.get("secondary_used"),
                secondary_reset=item.get("secondary_reset"),
                error=item.get("error"),
            )
            self.accounts[row.alias] = row
        self.render_accounts()
        self.set_busy("Ready" if result.returncode == 0 else "Status completed with errors")

    def use_selected(self) -> None:
        alias = self.selected_alias()
        if not alias:
            messagebox.showinfo(APP_TITLE, "Select an account first.", parent=self.root)
            return
        self.run_background(f"Switching to {alias}", ["use", alias], self.on_use_done)

    def on_use_done(self, result: CommandResult) -> None:
        self.log_command_result(result)
        if result.returncode == 0:
            self.refresh_accounts()
        else:
            self.set_busy("Switch failed")

    def add_account(self) -> None:
        dialog = AliasDialog(self.root, "Add Account", "Add")
        if not dialog.result:
            return
        alias, force = dialog.result
        if self.target_var.get() == "Windows Native" and not self.ensure_windows_codex_bin():
            return
        self.log(f"Starting UI login for {alias}.")
        self.set_busy("Login started")
        LoginDialog(self.root, self.runner, self.target_var.get(), alias, force, self.on_add_done)

    def on_add_done(self, exit_code: int) -> None:
        if exit_code == 0:
            self.refresh_accounts()
        else:
            self.set_busy("Add failed")

    def find_windows_codex_bin(self) -> Path | None:
        configured = os.environ.get("CX_CODEX_BIN")
        if configured:
            configured_path = Path(configured)
            if configured_path.exists():
                return configured_path
            resolved = shutil.which(configured)
            if resolved:
                return Path(resolved)

        extra_dirs = self.windows_extra_path_dirs()
        search_path = os.pathsep.join(extra_dirs + [os.environ.get("PATH", "")])
        for name in ("codex.cmd", "codex.exe", "codex.bat", "codex"):
            resolved = shutil.which(name, path=search_path)
            if resolved:
                return Path(resolved)

        try:
            result = subprocess.run(
                ["where", "codex"],
                env={**os.environ, "PATH": search_path},
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=5,
                check=False,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            result = None
        if result and result.returncode == 0:
            for line in result.stdout.splitlines():
                path = Path(line.strip())
                if path.exists():
                    return path
        candidates = self.windows_codex_candidates() + self.windows_npm_codex_candidates(search_path)
        for path in candidates:
            if path.exists():
                return path
        return None

    def windows_extra_path_dirs(self) -> list[str]:
        dirs = [
            os.path.expandvars(r"%APPDATA%\npm"),
            os.path.expandvars(r"%LOCALAPPDATA%\pnpm"),
            os.path.expandvars(r"%LOCALAPPDATA%\Yarn\bin"),
            os.path.expandvars(r"%ProgramFiles%\nodejs"),
            os.path.expandvars(r"%ProgramFiles(x86)%\nodejs"),
            os.path.expandvars(r"%USERPROFILE%\scoop\shims"),
            os.path.expandvars(r"%USERPROFILE%\.codex\.sandbox-bin"),
            os.path.expandvars(r"%USERPROFILE%\.codex\bin"),
            os.path.expandvars(r"%USERPROFILE%\.codex"),
            os.path.expandvars(r"%USERPROFILE%\.bun\bin"),
            os.path.expandvars(r"%USERPROFILE%\.cargo\bin"),
        ]
        dirs.extend(self.windows_registry_path_dirs())
        return [path for path in dirs if path and Path(path).exists()]

    def windows_registry_path_dirs(self) -> list[str]:
        try:
            import winreg
        except ImportError:
            return []

        dirs: list[str] = []
        registry_paths = [
            (winreg.HKEY_CURRENT_USER, r"Environment"),
            (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
        ]
        for hive, key_name in registry_paths:
            try:
                with winreg.OpenKey(hive, key_name) as key:
                    value, _value_type = winreg.QueryValueEx(key, "Path")
            except OSError:
                continue
            expanded = os.path.expandvars(value)
            dirs.extend(part for part in expanded.split(os.pathsep) if part)
        return dirs

    def windows_codex_candidates(self) -> list[Path]:
        return [
            Path(os.path.expandvars(r"%APPDATA%\npm\codex.cmd")),
            Path(os.path.expandvars(r"%APPDATA%\npm\codex.exe")),
            Path(os.path.expandvars(r"%LOCALAPPDATA%\pnpm\codex.cmd")),
            Path(os.path.expandvars(r"%LOCALAPPDATA%\Yarn\bin\codex.cmd")),
            Path(os.path.expandvars(r"%USERPROFILE%\scoop\shims\codex.cmd")),
            Path(os.path.expandvars(r"%USERPROFILE%\.codex\.sandbox-bin\codex.exe")),
            Path(os.path.expandvars(r"%USERPROFILE%\.codex\.sandbox-bin\codex.cmd")),
            Path(os.path.expandvars(r"%USERPROFILE%\.codex\bin\codex.exe")),
            Path(os.path.expandvars(r"%USERPROFILE%\.codex\bin\codex.cmd")),
            Path(os.path.expandvars(r"%USERPROFILE%\.bun\bin\codex.cmd")),
            Path(os.path.expandvars(r"%USERPROFILE%\.cargo\bin\codex.exe")),
        ]

    def windows_npm_codex_candidates(self, search_path: str) -> list[Path]:
        try:
            result = subprocess.run(
                ["npm", "config", "get", "prefix"],
                env={**os.environ, "PATH": search_path},
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=5,
                check=False,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return []
        if result.returncode != 0:
            return []
        prefix = result.stdout.strip()
        if not prefix:
            return []
        return [Path(prefix) / "codex.cmd", Path(prefix) / "codex.exe"]

    def ensure_windows_codex_bin(self) -> bool:
        detected = self.find_windows_codex_bin()
        if detected:
            os.environ["CX_CODEX_BIN"] = str(detected)
            self.log(f"CX_CODEX_BIN set to {detected}")
            return True

        messagebox.showinfo(
            APP_TITLE,
            "Could not find Windows codex automatically. Select codex.cmd or codex.exe once.",
            parent=self.root,
        )
        selected = filedialog.askopenfilename(
            parent=self.root,
            title="Select codex.cmd or codex.exe",
            filetypes=[("Codex executable", "codex.cmd codex.exe"), ("Command files", "*.cmd *.exe"), ("All files", "*.*")],
        )
        if not selected:
            self.log("Add cancelled: no Codex executable selected.")
            return False
        path = Path(selected)
        if not path.exists():
            messagebox.showerror(APP_TITLE, f"File does not exist: {selected}", parent=self.root)
            return False
        os.environ["CX_CODEX_BIN"] = str(path)
        self.log(f"CX_CODEX_BIN set to {path}")
        return True

    def save_current(self) -> None:
        dialog = AliasDialog(self.root, "Save Current Account", "Save")
        if not dialog.result:
            return
        alias, force = dialog.result
        args = ["save"]
        if force:
            args.append("--force")
        args.append(alias)
        self.run_background(f"Saving {alias}", args, self.on_save_done)

    def remove_selected(self) -> None:
        alias = self.selected_alias()
        if not alias:
            messagebox.showinfo(APP_TITLE, "Select an account first.", parent=self.root)
            return
        if not messagebox.askyesno(APP_TITLE, f"確定刪除 {alias} 的本機登入資料？", parent=self.root):
            return
        self.run_background(f"Removing {alias}", ["remove", "--yes", alias], self.on_remove_done)

    def on_remove_done(self, result: CommandResult) -> None:
        self.log_command_result(result)
        if result.returncode == 0:
            self.refresh_accounts()
        else:
            self.set_busy("Remove failed")

    def on_save_done(self, result: CommandResult) -> None:
        self.log_command_result(result)
        if result.returncode == 0:
            self.refresh_accounts()
        else:
            self.set_busy("Save failed")

    def log_command_result(self, result: CommandResult) -> None:
        self.log("$ " + result.display)
        if result.stdout.strip():
            self.log(result.stdout.rstrip())
        if result.stderr.strip():
            self.log(result.stderr.rstrip())
        if result.returncode != 0:
            self.log(f"Exit code: {result.returncode}")

    def render_accounts(self) -> None:
        selected = self.selected_alias()
        self.tree.delete(*self.tree.get_children())
        for alias in sorted(self.accounts):
            row = self.accounts[alias]
            self.tree.insert(
                "",
                "end",
                iid=alias,
                values=(
                    "*" if row.current else "",
                    row.alias,
                    row.email or "",
                    row.plan or "",
                    self.format_limit(row.primary_used, row.primary_reset),
                    self.format_limit(row.secondary_used, row.secondary_reset),
                    row.error or "",
                ),
            )
        if selected in self.accounts:
            self.tree.selection_set(selected)

    @staticmethod
    def format_limit(used: int | None, reset: str | None) -> str:
        if used is None:
            return ""
        value = f"{used}% used"
        if reset:
            value += f" | {reset}"
        return value


def main() -> int:
    root = Tk()
    CxGui(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
