#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import re
import shutil
import shlex
import argparse
import subprocess
import sys
import threading
import webbrowser
import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from tkinter import BooleanVar, Entry, Menu, PanedWindow, StringVar, TclError, Tk, Toplevel, filedialog, messagebox, simpledialog, ttk
from tkinter.scrolledtext import ScrolledText

from cx_account_manager import __version__
from cx_account_manager.ui_theme import (
    ACCOUNT_TREE_STYLE,
    ThemeInfo,
    ThemeTokens,
    button_style_kwargs,
    configure_enterprise_styles,
    create_root_and_theme,
    enterprise_light_tokens,
    fallback_theme_info,
    format_font_tokens,
    menubutton_style_kwargs,
    style_status_badge,
    theme_install_hint,
    themed_widget_class,
)


APP_TITLE = "cx Account Manager"
TIMEOUT_SEC = 45
ACTIVITY_COLLAPSED_HEIGHT = 42
ACTIVITY_EXPANDED_HEIGHT = 220
ACTIVITY_MIN_EXPANDED_HEIGHT = 150
THEME_HINT_BLINK_INTERVAL_MS = 500
THEME_HINT_ALERT_DURATION_MS = 15000
WINDOWS_TARGET = "Windows Native"
DEFAULT_WSL_TARGET = "WSL"
WSL_TARGET_PREFIX = "WSL: "
ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
URL_RE = re.compile(r"https?://[^\s\x1b]+")
DEVICE_CODE_RE = re.compile(
    r"(?i)\b(?:one-time\s+code|device\s+code|user\s+code|verification\s+code|code)\b"
    r"(?:\s+(?:is|=))?[\s:]+"
    r"([A-Z0-9]{4,8}(?:-[A-Z0-9]{4,8}){1,3}|[A-Z0-9]{6,12})\b"
)
DEVICE_CODE_TOKEN_RE = re.compile(r"\b[A-Z0-9]{4,8}(?:-[A-Z0-9]{4,8}){1,3}\b")


def icon_label(icon: str, text: str) -> str:
    return f"{icon} {text}"


def enforce_widget_style(widget: ttk.Widget, style_kwargs: dict[str, str]) -> ttk.Widget:
    style = style_kwargs.get("style")
    if style:
        try:
            widget.configure(style=style)
        except TclError:
            pass
    return widget


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
    scope: str | None = None
    email: str | None = None
    plan: str | None = None
    primary_used: int | None = None
    primary_reset: str | None = None
    secondary_used: int | None = None
    secondary_reset: str | None = None
    rank: int | None = None
    error: str | None = None


def doctor_severity(report: dict[str, object]) -> str:
    errors = report.get("errors")
    warnings = report.get("warnings")
    if isinstance(errors, list) and errors:
        return "Error"
    if isinstance(warnings, list) and warnings:
        return "Warning"
    return "OK"


def redact_doctor_report_text(text: str) -> str:
    replacements: list[tuple[str, str]] = []
    for env_name, label in (
        ("LOCALAPPDATA", "%LOCALAPPDATA%"),
        ("APPDATA", "%APPDATA%"),
        ("USERPROFILE", "%USERPROFILE%"),
    ):
        value = os.environ.get(env_name)
        if value:
            replacements.append((value, label))
    try:
        home = str(Path.home())
    except RuntimeError:
        home = ""
    if home:
        replacements.append((home, "~"))

    redacted = text
    for path, label in sorted(replacements, key=lambda item: len(item[0]), reverse=True):
        if not path:
            continue
        variants = {path, path.replace("\\", "/")}
        for variant in variants:
            redacted = re.sub(re.escape(variant), label, redacted, flags=re.IGNORECASE)
    return redacted


def doctor_bool(value: object) -> str:
    if value is True:
        return "yes"
    if value is False:
        return "no"
    return "n/a"


def doctor_list_lines(values: object) -> list[str]:
    if not isinstance(values, list) or not values:
        return ["- none"]
    return [f"- {value}" for value in values]


def app_server_doctor_text(report: dict[str, object]) -> str:
    codex = report.get("codex") if isinstance(report.get("codex"), dict) else {}
    app_server = codex.get("app_server") if isinstance(codex, dict) and isinstance(codex.get("app_server"), dict) else {}
    if not isinstance(app_server, dict):
        return "unknown"
    if app_server.get("checked") is False:
        error = app_server.get("error")
        return f"skipped ({error})" if error and error != "skipped" else "skipped"
    if app_server.get("ok") is True:
        return "ok"
    if app_server.get("ok") is False:
        return f"error ({app_server.get('error') or 'unknown error'})"
    return "unknown"


def format_doctor_report_for_clipboard(report: dict[str, object], target: str) -> str:
    system = report.get("system") if isinstance(report.get("system"), dict) else {}
    paths = report.get("paths") if isinstance(report.get("paths"), dict) else {}
    accounts = report.get("accounts") if isinstance(report.get("accounts"), dict) else {}
    codex = report.get("codex") if isinstance(report.get("codex"), dict) else {}
    wsl = report.get("wsl") if isinstance(report.get("wsl"), dict) else {}

    auth_line = "missing"
    if isinstance(paths, dict) and paths.get("auth_json_exists"):
        auth_line = "exists, parse ok" if paths.get("auth_json_parse_ok") else "exists, parse failed"

    lines = [
        "cx doctor report",
        f"Target: {target}",
        f"Result: {doctor_severity(report)}",
        "",
        "[System]",
        f"OS: {system.get('os') if isinstance(system, dict) else ''}",
        f"Python: {system.get('python_version') if isinstance(system, dict) else ''}",
        f"cx script: {system.get('cx_script') if isinstance(system, dict) else ''}",
        f"WSL: {doctor_bool(system.get('is_wsl') if isinstance(system, dict) else None)}",
        "",
        "[Paths]",
        f"data dir: {paths.get('data_dir') if isinstance(paths, dict) else ''}",
        f"accounts dir: {'exists' if isinstance(paths, dict) and paths.get('accounts_dir_exists') else 'missing'}",
        f"CODEX_HOME: {paths.get('codex_home') if isinstance(paths, dict) else ''}",
        f"auth.json: {auth_line}",
        "",
        "[Codex]",
        f"CX_CODEX_BIN: {codex.get('cx_codex_bin') or 'not set' if isinstance(codex, dict) else 'not set'}",
        f"executable: {codex.get('executable') or 'not found' if isinstance(codex, dict) else 'not found'}",
        f"version: {codex.get('version') or 'unknown' if isinstance(codex, dict) else 'unknown'}",
        f"app-server: {app_server_doctor_text(report)}",
        "",
        "[Accounts]",
        f"saved accounts: {accounts.get('count') if isinstance(accounts, dict) else 0}",
        f"current alias: {doctor_bool(accounts.get('current_alias_set') if isinstance(accounts, dict) else None)}",
        "",
        "[WSL]",
        f"checked: {doctor_bool(wsl.get('checked') if isinstance(wsl, dict) else None)}",
        f"available: {doctor_bool(wsl.get('available') if isinstance(wsl, dict) else None)}",
        f"distro count: {wsl.get('distro_count') if isinstance(wsl, dict) else 0}",
        "",
        "Warnings:",
        *doctor_list_lines(report.get("warnings")),
        "",
        "Errors:",
        *doctor_list_lines(report.get("errors")),
    ]
    return redact_doctor_report_text("\n".join(str(line) for line in lines).strip() + "\n")


class CxRunner:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root
        self.src_cx = repo_root / "src" / "cx.py"
        if not self.src_cx.exists():
            self.src_cx = repo_root / "cx.py"

    @staticmethod
    def is_wsl_target(target: str) -> bool:
        return target == DEFAULT_WSL_TARGET or target.startswith(WSL_TARGET_PREFIX)

    @staticmethod
    def wsl_distro_name(target: str) -> str | None:
        if target.startswith(WSL_TARGET_PREFIX):
            distro = target[len(WSL_TARGET_PREFIX) :].strip()
            return distro or None
        return None

    def base_command(self, target: str) -> list[str]:
        if self.is_wsl_target(target):
            distro = self.wsl_distro_name(target)
            if distro:
                return ["wsl.exe", "-d", distro, "bash", "-lic"]
            return ["wsl.exe", "bash", "-lic"]
        return [sys.executable, str(self.src_cx)]

    def command(self, target: str, args: list[str]) -> list[str]:
        if self.is_wsl_target(target):
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

    def target_path(self, target: str, path: str) -> str:
        if not self.is_wsl_target(target):
            return path
        normalized = path.replace("\\", "/")
        drive_match = re.match(r"^([A-Za-z]):/(.*)$", normalized)
        if not drive_match:
            return normalized
        drive = drive_match.group(1).lower()
        rest = drive_match.group(2)
        return f"/mnt/{drive}/{rest}"

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
        if self.is_wsl_target(target):
            distro = self.wsl_distro_name(target)
            prefix = f"wsl.exe -d {shlex.quote(distro)} cx" if distro else "wsl.exe cx"
            return prefix + " " + " ".join(shlex.quote(arg) for arg in args)
        return subprocess.list2cmdline(self.command(target, args))

    def subprocess_env(self, target: str) -> dict[str, str]:
        env = os.environ.copy()
        if target == WINDOWS_TARGET:
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


class ExportFilterDialog(simpledialog.Dialog):
    def __init__(self, parent: Tk, aliases: list[str] | None = None) -> None:
        self.aliases_var = StringVar(value=",".join(aliases or []))
        self.emails_var = StringVar()
        self.result: tuple[list[str], list[str]] | None = None
        super().__init__(parent, "Export Filtered")

    def body(self, master: ttk.Frame) -> ttk.Entry:
        ttk.Label(master, text="Aliases").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=(0, 8))
        alias_entry = ttk.Entry(master, textvariable=self.aliases_var, width=48)
        alias_entry.grid(row=0, column=1, sticky="ew", pady=(0, 8))
        ttk.Label(master, text="Emails").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(0, 8))
        ttk.Entry(master, textvariable=self.emails_var, width=48).grid(row=1, column=1, sticky="ew", pady=(0, 8))
        master.columnconfigure(1, weight=1)
        return alias_entry

    def buttonbox(self) -> None:
        box = ttk.Frame(self)
        ttk.Button(box, text="Export", command=self.ok).pack(side="left", padx=4, pady=8)
        ttk.Button(box, text="Cancel", command=self.cancel).pack(side="left", padx=4, pady=8)
        box.pack()

    def validate(self) -> bool:
        aliases = parse_csv_values(self.aliases_var.get())
        emails = parse_csv_values(self.emails_var.get())
        if not aliases and not emails:
            messagebox.showerror(APP_TITLE, "Enter at least one alias or email.", parent=self)
            return False
        self.result = (aliases, emails)
        return True


class BackupSelectionDialog(simpledialog.Dialog):
    def __init__(self, parent: Tk, title: str, accounts: list[dict[str, object]], import_mode: bool = False) -> None:
        self.accounts = accounts
        self.import_mode = import_mode
        self.force_var = BooleanVar(value=False)
        self.skip_existing_var = BooleanVar(value=True)
        self.set_current_var = BooleanVar(value=False)
        self.emails_var = StringVar()
        self.result: tuple[list[str], list[str], bool, bool, bool] | None = None
        super().__init__(parent, title)

    def body(self, master: ttk.Frame) -> ttk.Frame:
        master.columnconfigure(0, weight=1)
        master.rowconfigure(0, weight=1)
        columns = ("current", "alias", "email", "scope", "plan")
        self.tree = ttk.Treeview(master, columns=columns, show="headings", selectmode="extended", height=12)
        headings = {"current": "*", "alias": "Alias", "email": "Email", "scope": "Scope", "plan": "Plan"}
        widths = {"current": 36, "alias": 150, "email": 260, "scope": 90, "plan": 120}
        for column, heading in headings.items():
            self.tree.heading(column, text=heading)
            self.tree.column(column, width=widths[column], anchor="w", stretch=column == "email")
        self.tree.grid(row=0, column=0, sticky="nsew")
        for item in self.accounts:
            alias = str(item.get("alias") or "")
            if not alias:
                continue
            self.tree.insert(
                "",
                "end",
                iid=alias,
                values=(
                    "*" if item.get("current") else "",
                    alias,
                    item.get("email") or "",
                    item.get("scope") or "",
                    item.get("plan") or "",
                ),
            )
        for child in self.tree.get_children():
            self.tree.selection_add(child)

        if self.import_mode:
            options = ttk.Frame(master, padding=(0, 8, 0, 0))
            options.grid(row=1, column=0, sticky="ew")
            options.columnconfigure(1, weight=1)
            ttk.Label(options, text="Emails").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=(0, 8))
            ttk.Entry(options, textvariable=self.emails_var).grid(row=0, column=1, sticky="ew", pady=(0, 8))
            ttk.Checkbutton(options, text="Skip existing aliases", variable=self.skip_existing_var, command=self.on_skip_changed).grid(row=1, column=0, columnspan=2, sticky="w")
            ttk.Checkbutton(options, text="Overwrite existing aliases", variable=self.force_var, command=self.on_force_changed).grid(row=2, column=0, columnspan=2, sticky="w")
            ttk.Checkbutton(options, text="Restore current alias marker", variable=self.set_current_var).grid(row=3, column=0, columnspan=2, sticky="w")

        return master

    def buttonbox(self) -> None:
        box = ttk.Frame(self)
        action = "Import" if self.import_mode else "Close"
        ttk.Button(box, text=action, command=self.ok).pack(side="left", padx=4, pady=8)
        ttk.Button(box, text="Cancel", command=self.cancel).pack(side="left", padx=4, pady=8)
        box.pack()

    def on_skip_changed(self) -> None:
        if self.skip_existing_var.get():
            self.force_var.set(False)

    def on_force_changed(self) -> None:
        if self.force_var.get():
            self.skip_existing_var.set(False)

    def validate(self) -> bool:
        aliases = [str(alias) for alias in self.tree.selection()]
        emails = parse_csv_values(self.emails_var.get()) if self.import_mode else []
        if self.import_mode and not aliases and not emails:
            messagebox.showerror(APP_TITLE, "Select at least one alias or enter an email.", parent=self)
            return False
        self.result = (aliases, emails, self.force_var.get(), self.skip_existing_var.get(), self.set_current_var.get())
        return True


def parse_csv_values(value: str) -> list[str]:
    parsed: list[str] = []
    seen: set[str] = set()
    for part in value.split(","):
        item = part.strip()
        if not item or item in seen:
            continue
        seen.add(item)
        parsed.append(item)
    return parsed


class DoctorDialog:
    def __init__(
        self,
        parent: Tk,
        target: str,
        report: dict[str, object],
        copy_callback,
        theme_info: ThemeInfo | None = None,
        theme_tokens: ThemeTokens | None = None,
    ) -> None:
        self.theme_info = theme_info or getattr(parent, "cx_theme_info", fallback_theme_info())
        self.theme_tokens = theme_tokens or getattr(parent, "cx_theme_tokens", enterprise_light_tokens())
        self.button_class = themed_widget_class("Button", ttk.Button, self.theme_info)
        self.window = Toplevel(parent)
        self.window.cx_theme_info = self.theme_info
        self.window.cx_theme_tokens = self.theme_tokens
        self.window.title("CX Doctor")
        self.window.geometry("720x560")
        self.window.transient(parent)
        self.window.configure(background=self.theme_tokens.surface)
        self.window.columnconfigure(0, weight=1)
        self.window.rowconfigure(1, weight=1)

        severity = doctor_severity(report)
        header = ttk.Frame(self.window, padding=(14, 12, 14, 8), style="Dialog.TFrame")
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="CX Doctor", style="DoctorTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(header, text=f"Target: {target}", style="DoctorMeta.TLabel").grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Label(header, text=severity, style=style_status_badge(severity)).grid(row=0, column=1, rowspan=2, sticky="ne")

        output = ScrolledText(self.window, height=22, wrap="word")
        output.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 10))
        output.configure(
            background=self.theme_tokens.surface_alt,
            foreground=self.theme_tokens.text,
            insertbackground=self.theme_tokens.text,
            relief="flat",
            borderwidth=1,
            padx=10,
            pady=8,
            font=format_font_tokens(parent)["log"],
        )
        output.insert("1.0", self.dialog_text(report))
        output.configure(state="disabled")

        buttons = ttk.Frame(self.window, padding=(14, 0, 14, 14), style="Dialog.TFrame")
        buttons.grid(row=2, column=0, sticky="e")
        copy_style = button_style_kwargs("primary", self.theme_info)
        copy_button = self.button_class(buttons, text="Copy Report", command=copy_callback, **copy_style)
        enforce_widget_style(copy_button, copy_style).pack(side="left", padx=(0, 6))
        close_style = button_style_kwargs("secondary", self.theme_info)
        close_button = self.button_class(buttons, text="Close", command=self.window.destroy, **close_style)
        enforce_widget_style(close_button, close_style).pack(side="left")

    @staticmethod
    def dialog_text(report: dict[str, object]) -> str:
        text = format_doctor_report_for_clipboard(report, target="")
        lines = [line for line in text.splitlines() if line and not line.startswith("Target:")]
        return "\n".join(lines).strip() + "\n"


class LoginDialog:
    def __init__(
        self,
        parent: Tk,
        runner: CxRunner,
        target: str,
        alias: str,
        force: bool,
        on_done,
        theme_info: ThemeInfo | None = None,
        theme_tokens: ThemeTokens | None = None,
    ) -> None:
        self.parent = parent
        self.runner = runner
        self.target = target
        self.alias = alias
        self.force = force
        self.on_done = on_done
        self.theme_info = theme_info or getattr(parent, "cx_theme_info", fallback_theme_info())
        self.theme_tokens = theme_tokens or getattr(parent, "cx_theme_tokens", enterprise_light_tokens())
        self.button_class = themed_widget_class("Button", ttk.Button, self.theme_info)
        self.proc: subprocess.Popen[str] | None = None
        self.finished = False
        self.stream_output_seen = False

        self.window = Toplevel(parent)
        self.window.cx_theme_info = self.theme_info
        self.window.cx_theme_tokens = self.theme_tokens
        self.window.title(f"Add Account: {alias}")
        self.window.geometry("760x460")
        self.window.configure(background=self.theme_tokens.surface)
        self.window.columnconfigure(0, weight=1)
        self.window.rowconfigure(1, weight=1)
        self.window.protocol("WM_DELETE_WINDOW", self.close_or_cancel)

        self.status_var = StringVar(value="Starting login...")
        ttk.Label(self.window, textvariable=self.status_var, padding=10, style="DoctorMeta.TLabel").grid(row=0, column=0, sticky="ew")

        self.output = ScrolledText(self.window, wrap="word", height=18)
        self.output.grid(row=1, column=0, sticky="nsew", padx=12)
        self.output.configure(
            background=self.theme_tokens.log_bg,
            foreground=self.theme_tokens.log_text,
            insertbackground=self.theme_tokens.log_text,
            relief="flat",
            borderwidth=0,
            padx=10,
            pady=8,
            font=format_font_tokens(parent)["log"],
        )
        self.output.tag_configure("link", foreground=self.theme_tokens.info_border, underline=True)
        self.output.tag_configure("copy", foreground=self.theme_tokens.info_border, underline=True)
        self.output.tag_bind("link", "<Enter>", lambda _event: self.output.configure(cursor="hand2"))
        self.output.tag_bind("link", "<Leave>", lambda _event: self.output.configure(cursor=""))
        self.output.tag_bind("copy", "<Enter>", lambda _event: self.output.configure(cursor="hand2"))
        self.output.tag_bind("copy", "<Leave>", lambda _event: self.output.configure(cursor=""))
        self.output.bind("<Control-c>", self.copy_selected_output)
        self.output.bind("<Control-C>", self.copy_selected_output)
        self.link_count = 0

        buttons = ttk.Frame(self.window, padding=10, style="Dialog.TFrame")
        buttons.grid(row=2, column=0, sticky="ew")
        buttons.columnconfigure(0, weight=1)
        close_style = button_style_kwargs("secondary", self.theme_info)
        self.close_button = self.button_class(buttons, text="Cancel", command=self.close_or_cancel, **close_style)
        enforce_widget_style(self.close_button, close_style)
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
                self.output.insert("end", clean_text[start:end], ("copy", tag))
                self.output.insert("end", " [複製]", ("copy", tag))
                self.output.tag_bind(tag, "<Button-1>", lambda _event, code=value: self.copy_code(code))
                self.status_var.set(f"Code ready: {value}")
            position = end
        self.output.insert("end", clean_text[position:])
        self.output.see("end")

    def copy_text_to_clipboard(self, text: str) -> None:
        self.parent.clipboard_clear()
        self.parent.clipboard_append(text)
        self.parent.update_idletasks()

    def copy_selected_output(self, _event=None) -> str:
        try:
            selected = self.output.get("sel.first", "sel.last")
        except TclError:
            return "break"
        self.copy_text_to_clipboard(selected)
        self.status_var.set("Copied selected text")
        return "break"

    def copy_code(self, code: str) -> None:
        clean_code = code.strip()
        self.copy_text_to_clipboard(clean_code)
        self.status_var.set(f"Copied code: {clean_code}")

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


class ToolTip:
    def __init__(self, widget: ttk.Widget, text: str, delay_ms: int = 500) -> None:
        self.widget = widget
        self.text = text
        self.delay_ms = delay_ms
        self.after_id: str | None = None
        self.window: Toplevel | None = None

        self.widget.bind("<Enter>", self.schedule, add="+")
        self.widget.bind("<Leave>", self.hide, add="+")
        self.widget.bind("<ButtonPress>", self.hide, add="+")

    def schedule(self, _event=None) -> None:
        self.cancel()
        self.after_id = self.widget.after(self.delay_ms, self.show)

    def cancel(self) -> None:
        if self.after_id is not None:
            self.widget.after_cancel(self.after_id)
            self.after_id = None

    def show(self) -> None:
        self.after_id = None
        if self.window is not None or not self.text:
            return
        x = self.widget.winfo_rootx() + 16
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 8
        self.window = Toplevel(self.widget)
        self.window.wm_overrideredirect(True)
        self.window.wm_geometry(f"+{x}+{y}")
        label = ttk.Label(
            self.window,
            text=self.text,
            justify="left",
            padding=(8, 5),
            relief="solid",
            borderwidth=1,
            wraplength=320,
        )
        label.pack()

    def hide(self, _event=None) -> None:
        self.cancel()
        if self.window is not None:
            self.window.destroy()
            self.window = None


class CxGui:
    def __init__(
        self,
        root: Tk,
        theme_info: ThemeInfo | None = None,
        theme_tokens: ThemeTokens | None = None,
        preview_rows: list[AccountRow] | None = None,
    ) -> None:
        self.root = root
        self.theme_info = theme_info or getattr(root, "cx_theme_info", fallback_theme_info())
        self.theme_tokens = theme_tokens or getattr(root, "cx_theme_tokens", enterprise_light_tokens())
        self.root.cx_theme_info = self.theme_info
        self.root.cx_theme_tokens = self.theme_tokens
        self.root.title(APP_TITLE)
        self.root.geometry("1360x760")
        self.root.minsize(1220, 620)
        self.repo_root = Path(__file__).resolve().parents[1]
        self.runner = CxRunner(self.repo_root)
        self.settings_file = self.default_settings_file()
        self.environment_values = self.detect_environment_values()
        self.target_var = StringVar(value=self.load_target_setting())
        self.status_var = StringVar(value="Ready")
        self.selection_var = StringVar(value="No account selected")
        self.activity_var = StringVar(value="Activity")
        self.activity_status_var = StringVar(value="Last action: Ready")
        self.theme_hint_var = StringVar(value="")
        self.log_expanded = BooleanVar(value=False)
        self.accounts: dict[str, AccountRow] = {}
        self.busy_count = 0
        self.busy_controls: list[ttk.Widget] = []
        self.selection_controls: dict[str, ttk.Widget] = {}
        self.post_refresh_status: str | None = None
        self.last_doctor_report: dict[str, object] | None = None
        self.last_doctor_target: str | None = None
        self.copy_doctor_after_load = False
        self.font_tokens = format_font_tokens(self.root)
        self.button_class = themed_widget_class("Button", ttk.Button, self.theme_info)
        self.menubutton_class = themed_widget_class("Menubutton", ttk.Menubutton, self.theme_info)
        self.theme_hint_after_id: str | None = None
        self.theme_hint_decay_id: str | None = None
        self.theme_hint_blink_on = False

        self._build_ui()
        if not self.theme_info.available:
            hint = theme_install_hint()
            self.show_theme_hint(hint)
        if preview_rows is not None:
            self.load_preview_accounts(preview_rows)
        else:
            self.refresh_accounts()

    def _build_ui(self) -> None:
        tokens = self.theme_tokens
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(2, weight=1)
        self.configure_styles()

        toolbar = ttk.Frame(self.root, padding=(12, 8), style="TopBar.TFrame")
        toolbar.grid(row=0, column=0, sticky="ew")
        toolbar.columnconfigure(0, weight=1)
        toolbar.columnconfigure(1, weight=0)
        toolbar.columnconfigure(2, weight=1)

        title_box = ttk.Frame(toolbar, style="TopBar.TFrame")
        title_box.grid(row=0, column=0, sticky="w")
        title_box.columnconfigure(0, weight=1)
        title_box.columnconfigure(1, weight=0)
        ttk.Label(title_box, text=APP_TITLE, style="Title.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(title_box, text=f"cx {__version__}", style="Status.TLabel").grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 0))
        self.theme_hint_entry = Entry(
            title_box,
            textvariable=self.theme_hint_var,
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            state="readonly",
            readonlybackground=tokens.surface,
            background=tokens.surface,
            foreground=tokens.info,
            disabledforeground=tokens.info,
            font=self.font_tokens["body"],
            width=72,
        )
        self.theme_hint_entry.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        self.theme_hint_entry.grid_remove()
        self.theme_hint_entry.bind("<Button-1>", self.on_theme_hint_click)
        self.theme_hint_entry.bind("<Control-c>", self.copy_theme_hint_from_event)
        self.theme_hint_entry.bind("<Control-C>", self.copy_theme_hint_from_event)
        theme_hint_copy_style = button_style_kwargs("ghost", self.theme_info)
        self.theme_hint_copy_button = self.button_class(
            title_box,
            text="Copy",
            command=self.copy_theme_hint,
            **theme_hint_copy_style,
        )
        enforce_widget_style(self.theme_hint_copy_button, theme_hint_copy_style)
        self.theme_hint_copy_button.grid(row=2, column=1, sticky="e", padx=(8, 0), pady=(8, 0))
        self.theme_hint_copy_button.grid_remove()

        env_box = ttk.Frame(toolbar, style="TopBar.TFrame")
        env_box.grid(row=0, column=1, sticky="n")
        ttk.Label(env_box, text="Auth Environment", style="AuthEnvironment.TLabel").pack(anchor="center")
        target = ttk.Combobox(env_box, textvariable=self.target_var, values=self.environment_values, state="readonly", width=28, style="AuthEnvironment.TCombobox")
        target.pack(anchor="center", pady=(2, 0))
        target.bind("<<ComboboxSelected>>", self.on_target_changed)

        action_bar = ttk.Frame(toolbar, style="TopBar.TFrame")
        action_bar.grid(row=0, column=2, sticky="e")
        self.add_busy_button(action_bar, text=icon_label("↻", "Refresh"), command=self.refresh_accounts, role="secondary", tooltip="Reload saved accounts and usage for the selected environment.").pack(side="left", padx=(0, 4))
        self.add_busy_button(action_bar, text=icon_label("▤", "Details"), command=self.refresh_status_all, role="secondary", tooltip="Show the CLI status output in Activity.").pack(side="left", padx=(0, 4))
        self.add_busy_button(action_bar, text=icon_label("☆", "Best"), command=self.switch_to_best, role="secondary", tooltip="Switch to the best-ranked usable account right now.").pack(side="left", padx=(0, 4))
        self.add_busy_button(action_bar, text=icon_label("+", "Add"), command=self.add_account, role="secondary", tooltip="Log in with Codex device auth and save a new account.").pack(side="left", padx=(0, 4))

        more_style = menubutton_style_kwargs("secondary", self.theme_info)
        more_button = self.menubutton_class(action_bar, text=icon_label("⋯", "More"), **more_style)
        enforce_widget_style(more_button, more_style)
        more_menu = Menu(more_button, tearoff=False)
        more_menu.add_command(label=icon_label("▣", "Save Current"), command=self.save_current)
        more_menu.add_command(label=icon_label("▤", "Details Selected"), command=self.refresh_status_selected)
        more_menu.add_separator()
        more_menu.add_command(label=icon_label("⇧", "Export All"), command=self.export_all)
        more_menu.add_command(label=icon_label("⇧", "Export Filtered"), command=self.export_filtered)
        more_menu.add_command(label=icon_label("⇩", "Import"), command=self.import_backup)
        more_menu.add_command(label=icon_label("⌕", "Inspect Backup"), command=self.inspect_backup)
        more_menu.add_separator()
        more_menu.add_command(label=icon_label("◇", "Run Doctor"), command=self.run_doctor)
        more_menu.add_command(label=icon_label("◇", "Run Quick Doctor"), command=lambda: self.run_doctor(skip_app_server=True))
        more_menu.add_command(label=icon_label("⧉", "Copy Doctor Report"), command=self.copy_doctor_report)
        more_menu.add_separator()
        more_menu.add_command(label=icon_label("☰", "Show Activity / Log"), command=self.show_log_panel)
        more_menu.add_command(label=icon_label("▣", "Open Data Folder"), command=self.open_data_folder)
        more_menu.add_separator()
        more_menu.add_command(label=icon_label("?", "Help / Manual"), command=self.show_manual)
        more_button.configure(menu=more_menu)
        more_button.pack(side="left")
        self.busy_controls.append(more_button)

        ttk.Label(toolbar, textvariable=self.status_var, style="Status.TLabel").grid(row=1, column=0, columnspan=3, sticky="ew", pady=(5, 0))

        context = ttk.Frame(self.root, padding=(10, 8), style="Context.TFrame")
        context.grid(row=1, column=0, sticky="ew")
        context.columnconfigure(0, weight=1)
        ttk.Label(context, textvariable=self.selection_var, style="Context.TLabel").grid(row=0, column=0, sticky="w")
        actions = ttk.Frame(context, style="Context.TFrame")
        actions.grid(row=0, column=1, sticky="e")
        self.selection_controls["use"] = self.add_busy_button(actions, text=icon_label("▷", "Use"), command=self.use_selected, role="primary", tooltip="Switch to the selected account.")
        self.selection_controls["use"].pack(side="left", padx=(0, 4))
        self.selection_controls["remove"] = self.add_busy_button(actions, text=icon_label("⊘", "Remove"), command=self.remove_selected, role="danger", tooltip="Remove selected local account data.")
        self.selection_controls["remove"].pack(side="left", padx=(0, 4))
        self.selection_controls["work"] = self.add_busy_button(actions, text=icon_label("▣", "Work"), command=lambda: self.set_selected_scope("work"), role="secondary", tooltip="Mark selected account as work.")
        self.selection_controls["work"].pack(side="left", padx=(0, 4))
        self.selection_controls["personal"] = self.add_busy_button(actions, text=icon_label("◇", "Personal"), command=lambda: self.set_selected_scope("personal"), role="secondary", tooltip="Mark selected account as personal.")
        self.selection_controls["personal"].pack(side="left", padx=(0, 4))
        self.selection_controls["export"] = self.add_busy_button(actions, text=icon_label("⇧", "Export"), command=self.export_selected, role="secondary", tooltip="Export selected accounts.")
        self.selection_controls["export"].pack(side="left")

        self.main_pane = PanedWindow(self.root, orient="vertical", sashrelief="flat", sashwidth=6, opaqueresize=True, bd=0, relief="flat", background=tokens.border_soft)
        self.main_pane.grid(row=2, column=0, sticky="nsew")

        table_frame = ttk.Frame(self.main_pane, padding=(10, 8, 10, 6), style="App.TFrame")
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)
        self.main_pane.add(table_frame, minsize=220)

        columns = ("current", "rank", "alias", "scope", "email", "plan", "primary", "primary_reset", "secondary", "secondary_reset", "error")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="extended", style=ACCOUNT_TREE_STYLE)
        self.tree.configure(style=ACCOUNT_TREE_STYLE)
        headings = {
            "current": "Current",
            "rank": "Rank",
            "alias": "Alias",
            "scope": "Scope",
            "email": "Email",
            "plan": "Plan",
            "primary": "5h %",
            "primary_reset": "5h at",
            "secondary": "7d %",
            "secondary_reset": "7d at",
            "error": "Error",
        }
        widths = {"current": 96, "rank": 64, "alias": 170, "scope": 96, "email": 320, "plan": 86, "primary": 64, "primary_reset": 126, "secondary": 64, "secondary_reset": 126, "error": 88}
        anchors = {
            "current": "center",
            "rank": "center",
            "alias": "w",
            "scope": "center",
            "email": "w",
            "plan": "center",
            "primary": "center",
            "primary_reset": "center",
            "secondary": "center",
            "secondary_reset": "center",
            "error": "w",
        }
        stretch_columns = {"email", "error"}
        for column, heading in headings.items():
            anchor = anchors[column]
            self.tree.heading(column, text=heading, anchor=anchor)
            self.tree.column(column, width=widths[column], anchor=anchor, stretch=column in stretch_columns)
        self.tree.grid(row=0, column=0, sticky="nsew")
        yscroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        xscroll = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        self.tree.bind("<<TreeviewSelect>>", self.on_selection_changed)
        self.tree.bind("<Button-3>", self.show_table_context_menu)
        self.tree.tag_configure("current", background=tokens.current_bg)
        self.tree.tag_configure("error", foreground=tokens.error_fg)

        self.activity_frame = ttk.Frame(self.main_pane, padding=(10, 0, 10, 8), style="App.TFrame")
        self.activity_frame.columnconfigure(0, weight=1)
        activity_strip = ttk.Frame(self.activity_frame, style="Activity.TFrame")
        activity_strip.grid(row=0, column=0, sticky="ew", ipady=4)
        activity_strip.columnconfigure(0, weight=1)
        ttk.Label(activity_strip, textvariable=self.activity_var, style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(activity_strip, textvariable=self.activity_status_var, style="Muted.TLabel").grid(row=1, column=0, sticky="w")
        activity_toggle_style = button_style_kwargs("ghost", self.theme_info)
        self.activity_toggle = self.button_class(activity_strip, text="Show details", command=self.toggle_log_panel, **activity_toggle_style)
        enforce_widget_style(self.activity_toggle, activity_toggle_style)
        self.activity_toggle.grid(row=0, column=1, sticky="e")
        self.activity_body = ttk.Frame(self.activity_frame, style="Activity.TFrame")
        self.activity_body.columnconfigure(0, weight=1)
        self.activity_body.rowconfigure(0, weight=1)
        self.output = ScrolledText(self.activity_body, height=9, wrap="word")
        self.output.grid(row=0, column=0, sticky="nsew")
        self.output.configure(
            state="disabled",
            background=tokens.log_bg,
            foreground=tokens.log_text,
            insertbackground=tokens.log_text,
            relief="flat",
            borderwidth=0,
            padx=10,
            pady=8,
            font=self.font_tokens["log"],
        )
        self.main_pane.add(self.activity_frame, minsize=ACTIVITY_COLLAPSED_HEIGHT)

        self.context_menu = Menu(self.root, tearoff=False)
        self.context_menu.add_command(label=icon_label("▷", "Use"), command=self.use_selected)
        self.context_menu.add_command(label=icon_label("▤", "Details"), command=self.refresh_status_selected)
        self.context_menu.add_command(label=icon_label("▣", "Mark as Work"), command=lambda: self.set_selected_scope("work"))
        self.context_menu.add_command(label=icon_label("◇", "Mark as Personal"), command=lambda: self.set_selected_scope("personal"))
        self.context_menu.add_separator()
        self.context_menu.add_command(label=icon_label("⇧", "Export Selected"), command=self.export_selected)
        self.context_menu.add_command(label=icon_label("⊘", "Remove Selected"), command=self.remove_selected)

        self.root.bind("<F5>", lambda _event: self.refresh_accounts())
        self.root.bind("<Control-d>", lambda _event: self.refresh_status_all())
        self.root.bind("<Control-D>", lambda _event: self.refresh_status_all())
        self.root.bind("<Return>", lambda _event: self.use_selected())
        self.root.bind("<Delete>", lambda _event: self.remove_selected())
        self.root.bind("<Control-e>", lambda _event: self.export_selected())
        self.root.bind("<Control-E>", lambda _event: self.export_selected())
        self.root.bind("<Control-l>", lambda _event: self.toggle_log_panel())
        self.root.bind("<Control-L>", lambda _event: self.toggle_log_panel())
        self.on_selection_changed()

    def configure_styles(self) -> None:
        if self.theme_info.engine == "ttk":
            style = ttk.Style(self.root)
            try:
                style.theme_use("clam")
            except TclError:
                pass
        configure_enterprise_styles(self.root, self.theme_tokens)

    def add_busy_button(self, parent, **kwargs) -> ttk.Button:
        tooltip = kwargs.pop("tooltip", None)
        role = kwargs.pop("role", "secondary")
        kwargs.update(button_style_kwargs(role, self.theme_info))
        style_kwargs = {"style": kwargs["style"]} if "style" in kwargs else {}
        button = self.button_class(parent, **kwargs)
        enforce_widget_style(button, style_kwargs)
        if tooltip:
            ToolTip(button, tooltip)
        self.busy_controls.append(button)
        return button

    def show_theme_hint(self, hint: str) -> None:
        self.theme_hint_var.set(hint)
        self.theme_hint_entry.grid()
        self.theme_hint_copy_button.grid()
        self.apply_theme_hint_style(active=True)
        self.cancel_theme_hint_timers()
        self.theme_hint_blink_on = False
        self.post_refresh_status = hint
        self.activity_status_var.set(f"Last action: {hint}")
        self.log("Theme: standard ttk fallback")
        self.log(hint)
        self.schedule_theme_hint_blink()
        self.theme_hint_decay_id = self.root.after(THEME_HINT_ALERT_DURATION_MS, self.deactivate_theme_hint)

    def schedule_theme_hint_blink(self) -> None:
        self.theme_hint_blink_on = not self.theme_hint_blink_on
        self.apply_theme_hint_style(active=self.theme_hint_blink_on)
        self.theme_hint_after_id = self.root.after(THEME_HINT_BLINK_INTERVAL_MS, self.schedule_theme_hint_blink)

    def deactivate_theme_hint(self) -> None:
        self.cancel_theme_hint_timers(cancel_decay=False)
        self.theme_hint_decay_id = None
        self.apply_theme_hint_style(active=False)

    def cancel_theme_hint_timers(self, *, cancel_decay: bool = True) -> None:
        if self.theme_hint_after_id is not None:
            self.root.after_cancel(self.theme_hint_after_id)
            self.theme_hint_after_id = None
        if cancel_decay and self.theme_hint_decay_id is not None:
            self.root.after_cancel(self.theme_hint_decay_id)
            self.theme_hint_decay_id = None

    def apply_theme_hint_style(self, *, active: bool) -> None:
        tokens = self.theme_tokens
        foreground = tokens.primary if active else tokens.text_muted
        background = tokens.primary_soft if active else tokens.surface
        self.theme_hint_entry.configure(
            readonlybackground=background,
            background=background,
            foreground=foreground,
            disabledforeground=foreground,
        )

    def on_theme_hint_click(self, _event=None) -> str:
        self.theme_hint_entry.focus_set()
        self.theme_hint_entry.selection_range(0, "end")
        return "break"

    def copy_theme_hint(self) -> None:
        hint = self.theme_hint_var.get().strip()
        if not hint:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(hint)
        self.activity_status_var.set("Last action: Theme install hint copied")
        self.set_busy("Theme install hint copied")

    def copy_theme_hint_from_event(self, _event=None) -> str:
        self.copy_theme_hint()
        return "break"

    def selected_alias(self) -> str | None:
        selection = self.tree.selection()
        if not selection:
            return None
        return str(selection[0])

    def selected_aliases(self) -> list[str]:
        return [str(alias) for alias in self.tree.selection()]

    def on_selection_changed(self, _event=None) -> None:
        aliases = self.selected_aliases()
        count = len(aliases)
        if count == 0:
            self.selection_var.set("No account selected")
        elif count == 1:
            row = self.accounts.get(aliases[0])
            rank = f"Rank {row.rank}" if row and row.rank is not None else "Unranked"
            self.selection_var.set(f"Selected 1 account ({rank} · {aliases[0]})")
        else:
            self.selection_var.set(f"Selected {count} accounts")

        any_selected = count > 0 and self.busy_count == 0
        single = count == 1 and self.busy_count == 0
        self.set_control_state("use", single)
        self.set_control_state("work", any_selected)
        self.set_control_state("personal", any_selected)
        self.set_control_state("export", any_selected)
        self.set_control_state("remove", any_selected)
        self.update_context_menu_state(count)

    def set_control_state(self, name: str, enabled: bool) -> None:
        control = self.selection_controls.get(name)
        if control is not None:
            control.configure(state="normal" if enabled else "disabled")

    def update_context_menu_state(self, count: int | None = None) -> None:
        if not hasattr(self, "context_menu"):
            return
        if count is None:
            count = len(self.selected_aliases())
        single = count == 1 and self.busy_count == 0
        any_selected = count > 0 and self.busy_count == 0
        for index in (0, 1):
            self.context_menu.entryconfigure(index, state="normal" if single else "disabled")
        for index in (2, 3):
            self.context_menu.entryconfigure(index, state="normal" if any_selected else "disabled")
        self.context_menu.entryconfigure(5, state="normal" if any_selected else "disabled")
        self.context_menu.entryconfigure(6, state="normal" if any_selected else "disabled")

    def show_table_context_menu(self, event) -> str:
        row_id = self.tree.identify_row(event.y)
        if row_id and row_id not in self.tree.selection():
            self.tree.selection_set(row_id)
        self.on_selection_changed()
        self.context_menu.tk_popup(event.x_root, event.y_root)
        return "break"

    def toggle_log_panel(self) -> None:
        if self.log_expanded.get():
            self.hide_log_panel()
        else:
            self.show_log_panel()

    def show_log_panel(self) -> None:
        if self.log_expanded.get():
            return
        self.log_expanded.set(True)
        self.activity_body.grid(row=1, column=0, sticky="nsew", pady=(6, 0))
        self.activity_frame.rowconfigure(1, weight=1)
        self.activity_toggle.configure(text="Hide details")
        self.activity_var.set("Activity / Log")
        self.root.after_idle(self.expand_log_panel)

    def hide_log_panel(self) -> None:
        if not self.log_expanded.get():
            return
        self.log_expanded.set(False)
        self.activity_body.grid_remove()
        self.activity_frame.rowconfigure(1, weight=0)
        self.activity_toggle.configure(text="Show details")
        self.activity_var.set("Activity")
        self.root.after_idle(self.collapse_log_panel)

    def expand_log_panel(self) -> None:
        self.root.update_idletasks()
        pane_height = self.main_pane.winfo_height()
        if pane_height <= 1:
            return
        detail_height = min(ACTIVITY_EXPANDED_HEIGHT, max(ACTIVITY_MIN_EXPANDED_HEIGHT, pane_height // 3))
        table_height = min(max(220, pane_height - detail_height), max(0, pane_height - ACTIVITY_MIN_EXPANDED_HEIGHT))
        try:
            self.main_pane.sash_place(0, 0, table_height)
        except TclError:
            pass

    def collapse_log_panel(self) -> None:
        self.root.update_idletasks()
        pane_height = self.main_pane.winfo_height()
        if pane_height <= 1:
            return
        try:
            self.main_pane.sash_place(0, 0, max(220, pane_height - ACTIVITY_COLLAPSED_HEIGHT))
        except TclError:
            pass

    def open_data_folder(self) -> None:
        data_dir = self.runner.target_path(self.target_var.get(), str(self.default_settings_file().parent))
        if self.runner.is_wsl_target(self.target_var.get()):
            self.log(f"WSL data folder: {data_dir}")
            self.show_log_panel()
            self.set_busy("WSL data folder shown in Activity")
            return
        folder = self.default_settings_file().parent
        folder.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(folder)  # type: ignore[attr-defined]
        except (AttributeError, OSError) as exc:
            self.log(f"Could not open data folder: {exc}")
            self.show_log_panel()

    def show_manual(self) -> None:
        self.run_background_for_target(WINDOWS_TARGET, "Loading manual", ["manual", "--lang", "zh-TW"], self.on_manual_loaded, timeout=30)

    def on_manual_loaded(self, result: CommandResult) -> None:
        self.log_command_result(result, show=True)
        self.set_busy("Ready" if result.returncode == 0 else "Manual failed")

    def on_target_changed(self, _event=None) -> None:
        target = self.target_var.get()
        self.save_target_setting(target)
        self.post_refresh_status = self.auth_environment_message(target)
        self.refresh_accounts()

    @staticmethod
    def auth_environment_message(target: str) -> str:
        if target == WINDOWS_TARGET:
            return "Auth Environment: Windows Native. Actions affect Windows CODEX_HOME/auth.json."
        if target == DEFAULT_WSL_TARGET:
            return "Auth Environment: WSL default distro. Actions affect that WSL CODEX_HOME/auth.json."
        if target.startswith(WSL_TARGET_PREFIX):
            return f"Auth Environment: {target}. Actions affect that WSL CODEX_HOME/auth.json."
        return f"Auth Environment: {target}. Actions affect this environment's CODEX_HOME/auth.json."

    def current_auth_environment_label(self) -> str:
        return self.target_var.get()

    @staticmethod
    def detect_environment_values() -> list[str]:
        values = [WINDOWS_TARGET]
        for distro in CxGui.detect_wsl_distros():
            values.append(f"{WSL_TARGET_PREFIX}{distro}")
        if len(values) == 1:
            values.append(DEFAULT_WSL_TARGET)
        return values

    @staticmethod
    def detect_wsl_distros() -> list[str]:
        try:
            result = subprocess.run(
                ["wsl.exe", "--list", "--quiet"],
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
        distros: list[str] = []
        for line in result.stdout.splitlines():
            distro = line.replace("\x00", "").strip()
            if distro and distro not in distros:
                distros.append(distro)
        return distros

    @staticmethod
    def default_settings_file() -> Path:
        if os.name == "nt":
            local_appdata = os.environ.get("LOCALAPPDATA")
            if local_appdata:
                return Path(local_appdata) / "cx" / "gui-settings.json"
        return Path.home() / ".local" / "share" / "cx" / "gui-settings.json"

    def load_target_setting(self) -> str:
        try:
            payload = json.loads(self.settings_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return self.default_target_value()
        target = payload.get("target")
        if isinstance(target, str):
            if target in self.environment_values:
                return target
            if target == DEFAULT_WSL_TARGET or target.startswith(WSL_TARGET_PREFIX):
                return target
        return self.default_target_value()

    def save_target_setting(self, target: str) -> None:
        if target != WINDOWS_TARGET and not self.runner.is_wsl_target(target):
            return
        try:
            self.settings_file.parent.mkdir(parents=True, exist_ok=True)
            self.settings_file.write_text(json.dumps({"target": target}, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
        except OSError:
            pass

    def default_target_value(self) -> str:
        for target in self.environment_values:
            if self.runner.is_wsl_target(target):
                return target
        return WINDOWS_TARGET

    def log(self, text: str) -> None:
        self.output.configure(state="normal")
        self.output.insert("end", text)
        if not text.endswith("\n"):
            self.output.insert("end", "\n")
        self.output.see("end")
        self.output.configure(state="disabled")

    def set_busy(self, text: str) -> None:
        self.status_var.set(text)
        self.activity_status_var.set(f"Last action: {text}")

    def consume_post_refresh_status(self) -> str | None:
        message = self.post_refresh_status
        self.post_refresh_status = None
        return message

    def begin_busy(self) -> None:
        self.busy_count += 1
        if self.busy_count == 1:
            for control in self.busy_controls:
                control.configure(state="disabled")

    def end_busy(self) -> None:
        self.busy_count = max(0, self.busy_count - 1)
        if self.busy_count == 0:
            for control in self.busy_controls:
                control.configure(state="normal")
            self.on_selection_changed()

    def run_background(self, label: str, args: list[str], callback, timeout: int = TIMEOUT_SEC) -> None:
        self.run_background_for_target(self.target_var.get(), label, args, callback, timeout=timeout)

    def run_background_for_target(self, target: str, label: str, args: list[str], callback, timeout: int = TIMEOUT_SEC) -> None:
        self.begin_busy()
        self.set_busy(f"{label}...")

        def worker() -> None:
            result = self.runner.run(target, args, timeout=timeout)
            self.root.after(0, lambda: self.finish_background(callback, result))

        threading.Thread(target=worker, daemon=True).start()

    def finish_background(self, callback, result: CommandResult) -> None:
        try:
            callback(result)
        finally:
            self.end_busy()

    def refresh_accounts(self) -> None:
        self.run_background("Loading account status", ["status", "--json"], self.on_accounts_status_loaded, timeout=90)

    def load_preview_accounts(self, rows: list[AccountRow]) -> None:
        self.root.title(f"{APP_TITLE} - Preview")
        self.accounts = {row.alias: row for row in rows}
        self.render_accounts()
        current = next((row for row in rows if row.current), None)
        if current is not None and current.alias in self.accounts:
            self.tree.selection_set(current.alias)
            self.tree.see(current.alias)
        self.on_selection_changed()
        self.status_var.set("Preview mode")
        self.activity_status_var.set("Last action: Preview mode")
        self.log("Loaded GUI preview dataset")

    def on_accounts_status_loaded(self, result: CommandResult) -> None:
        if not result.stdout.strip():
            if result.returncode != 0:
                self.log_command_result(result)
            self.set_busy("Status unavailable; loading account list")
            self.run_background("Refreshing accounts", ["list", "--json"], self.on_accounts_list_loaded)
            return
        try:
            payload = json.loads(result.stdout or "{}")
        except json.JSONDecodeError:
            self.log_command_result(result)
            self.set_busy("Status JSON parse error; loading account list")
            self.run_background("Refreshing accounts", ["list", "--json"], self.on_accounts_list_loaded)
            return

        self.accounts = {}
        for item in payload.get("accounts", []):
            alias = item.get("alias")
            if not isinstance(alias, str):
                continue
            self.accounts[alias] = self.account_row_from_status_item(item)
        self.render_accounts()
        if result.returncode == 0:
            self.set_busy(self.consume_post_refresh_status() or "Ready")
        else:
            self.log_command_result(result)
            self.set_busy("Ready with status errors")

    def on_accounts_list_loaded(self, result: CommandResult) -> None:
        if result.returncode != 0:
            self.log_command_result(result)
            self.set_busy("Refresh failed")
            return
        try:
            payload = json.loads(result.stdout or "{}")
        except json.JSONDecodeError:
            self.log_command_result(result)
            self.set_busy("Refresh failed")
            return

        self.accounts = {}
        for item in payload.get("accounts", []):
            row = AccountRow(alias=item["alias"], current=bool(item.get("current")), scope=item.get("scope"))
            self.accounts[row.alias] = row
        self.render_accounts()
        self.set_busy(self.consume_post_refresh_status() or "Ready")

    @staticmethod
    def account_row_from_status_item(item: dict[str, object]) -> AccountRow:
        return AccountRow(
            alias=str(item["alias"]),
            current=bool(item.get("current")),
            scope=item.get("scope") if isinstance(item.get("scope"), str) else None,
            email=item.get("email") if isinstance(item.get("email"), str) else None,
            plan=item.get("plan") if isinstance(item.get("plan"), str) else None,
            primary_used=item.get("primary_used") if isinstance(item.get("primary_used"), int) else None,
            primary_reset=item.get("primary_reset") if isinstance(item.get("primary_reset"), str) else None,
            secondary_used=item.get("secondary_used") if isinstance(item.get("secondary_used"), int) else None,
            secondary_reset=item.get("secondary_reset") if isinstance(item.get("secondary_reset"), str) else None,
            rank=item.get("rank") if isinstance(item.get("rank"), int) else None,
            error=item.get("error") if isinstance(item.get("error"), str) else None,
        )

    def refresh_status_all(self) -> None:
        self.run_background("Reading status", ["status"], self.on_status_loaded, timeout=90)

    def refresh_status_selected(self) -> None:
        alias = self.selected_alias()
        if not alias:
            messagebox.showinfo(APP_TITLE, "Select an account first.", parent=self.root)
            return
        self.run_background(f"Reading {alias}", ["status", alias], self.on_status_loaded, timeout=90)

    def on_status_loaded(self, result: CommandResult) -> None:
        self.log_command_result(result, show=True)
        self.set_busy("Ready" if result.returncode == 0 else "Status completed with errors")

    def run_doctor(self, *, skip_app_server: bool = False) -> None:
        target = self.target_var.get()
        args = ["doctor", "--json"]
        label = "Running quick doctor" if skip_app_server else "Running doctor"
        timeout = 15 if skip_app_server else 30
        if skip_app_server:
            args.append("--skip-app-server")
        self.run_background_for_target(target, label, args, lambda result: self.on_doctor_loaded(result, target), timeout=timeout)

    def copy_doctor_report(self) -> None:
        if self.last_doctor_report is None or self.last_doctor_target is None:
            self.copy_doctor_after_load = True
            self.run_doctor(skip_app_server=True)
            return
        self.copy_doctor_report_to_clipboard()

    def copy_doctor_report_to_clipboard(self) -> None:
        if self.last_doctor_report is None or self.last_doctor_target is None:
            return
        text = format_doctor_report_for_clipboard(self.last_doctor_report, self.last_doctor_target)
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.set_busy("Doctor report copied to clipboard")

    def on_doctor_loaded(self, result: CommandResult, target: str) -> None:
        try:
            report = json.loads(result.stdout or "{}")
        except json.JSONDecodeError:
            self.log_command_result(result, show=True)
            messagebox.showerror(APP_TITLE, "Doctor output was not valid JSON. See Activity for details.", parent=self.root)
            self.set_busy("Doctor failed")
            self.copy_doctor_after_load = False
            return
        if not isinstance(report, dict):
            self.log_command_result(result, show=True)
            messagebox.showerror(APP_TITLE, "Doctor output was not a JSON object. See Activity for details.", parent=self.root)
            self.set_busy("Doctor failed")
            self.copy_doctor_after_load = False
            return

        self.last_doctor_report = report
        self.last_doctor_target = target
        DoctorDialog(self.root, target, report, self.copy_doctor_report_to_clipboard, theme_info=self.theme_info, theme_tokens=self.theme_tokens)
        if result.returncode != 0:
            self.log_command_result(result)
        if self.copy_doctor_after_load:
            self.copy_doctor_report_to_clipboard()
            self.copy_doctor_after_load = False
        else:
            self.set_busy(f"Doctor completed: {doctor_severity(report)}")

    def use_selected(self) -> None:
        alias = self.selected_alias()
        if not alias:
            messagebox.showinfo(APP_TITLE, "Select an account first.", parent=self.root)
            return
        environment = self.current_auth_environment_label()
        if not messagebox.askyesno(APP_TITLE, f"Switch `{alias}` in Auth Environment: {environment}?\n\nThis updates that environment's CODEX_HOME/auth.json.", parent=self.root):
            return
        self.run_background(f"Switching to {alias}", ["use", alias], self.on_use_done)

    def on_use_done(self, result: CommandResult) -> None:
        self.log_command_result(result)
        if result.returncode == 0:
            alias = self.selected_alias()
            if alias:
                self.post_refresh_status = f"Switched to {alias}"
            self.refresh_accounts()
        else:
            self.set_busy("Switch failed")

    def switch_to_best(self) -> None:
        self.run_background("Switching to best account", ["best"], self.on_best_done, timeout=90)

    def on_best_done(self, result: CommandResult) -> None:
        self.log_command_result(result)
        if result.returncode == 0:
            self.post_refresh_status = self.best_status_message(result) or "Switched to best account"
            self.refresh_accounts()
        else:
            self.set_busy("Best switch failed")

    def set_selected_scope(self, scope: str) -> None:
        aliases = self.selected_aliases()
        if not aliases:
            messagebox.showinfo(APP_TITLE, "Select an account first.", parent=self.root)
            return
        if len(aliases) == 1:
            self.run_background(f"Setting {aliases[0]} scope", ["scope", aliases[0], scope], self.on_scope_done)
            return
        self.begin_busy()
        self.set_busy(f"Setting {len(aliases)} accounts to {scope}...")

        def worker() -> None:
            target = self.target_var.get()
            results = [self.runner.run(target, ["scope", alias, scope], timeout=TIMEOUT_SEC) for alias in aliases]
            self.root.after(0, lambda: self.finish_background(self.on_scope_many_done, (scope, results)))

        threading.Thread(target=worker, daemon=True).start()

    def on_scope_done(self, result: CommandResult) -> None:
        self.log_command_result(result)
        if result.returncode == 0:
            self.refresh_accounts()
        else:
            self.set_busy("Scope update failed")

    def on_scope_many_done(self, payload: tuple[str, list[CommandResult]]) -> None:
        scope, results = payload
        failed = 0
        for result in results:
            self.log_command_result(result)
            if result.returncode != 0:
                failed += 1
        if failed == 0:
            self.post_refresh_status = f"Set {len(results)} accounts to {scope}"
            self.refresh_accounts()
        else:
            self.set_busy(f"Scope update completed with {failed} errors")

    def add_account(self) -> None:
        dialog = AliasDialog(self.root, "Add Account", "Add")
        if not dialog.result:
            return
        alias, force = dialog.result
        if self.target_var.get() == "Windows Native" and not self.ensure_windows_codex_bin():
            return
        self.log(f"Starting UI login for {alias}.")
        self.begin_busy()
        self.set_busy("Login started")
        LoginDialog(self.root, self.runner, self.target_var.get(), alias, force, self.on_add_done, theme_info=self.theme_info, theme_tokens=self.theme_tokens)

    def on_add_done(self, exit_code: int) -> None:
        try:
            if exit_code == 0:
                self.refresh_accounts()
            else:
                self.set_busy("Add failed")
        finally:
            self.end_busy()

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
        aliases = self.selected_aliases()
        if not aliases:
            messagebox.showinfo(APP_TITLE, "Select an account first.", parent=self.root)
            return
        if len(aliases) == 1:
            prompt = f"Delete `{aliases[0]}` from Auth Environment: {self.current_auth_environment_label()}?"
        else:
            prompt = f"Delete {len(aliases)} accounts from Auth Environment: {self.current_auth_environment_label()}?"
        if not messagebox.askyesno(APP_TITLE, prompt, parent=self.root):
            return
        if len(aliases) == 1:
            self.run_background(f"Removing {aliases[0]}", ["remove", "--yes", aliases[0]], self.on_remove_done)
            return
        self.begin_busy()
        self.set_busy(f"Removing {len(aliases)} accounts...")

        def worker() -> None:
            results = [self.runner.run(self.target_var.get(), ["remove", "--yes", alias], timeout=TIMEOUT_SEC) for alias in aliases]
            self.root.after(0, lambda: self.finish_background(self.on_remove_many_done, results))

        threading.Thread(target=worker, daemon=True).start()

    def on_remove_done(self, result: CommandResult) -> None:
        self.log_command_result(result)
        if result.returncode == 0:
            self.refresh_accounts()
        else:
            self.set_busy("Remove failed")

    def on_remove_many_done(self, results: list[CommandResult]) -> None:
        failed = 0
        for result in results:
            self.log_command_result(result)
            if result.returncode != 0:
                failed += 1
        if failed == 0:
            self.post_refresh_status = f"Removed {len(results)} accounts"
            self.refresh_accounts()
        else:
            self.set_busy(f"Remove completed with {failed} errors")

    def on_save_done(self, result: CommandResult) -> None:
        self.log_command_result(result)
        if result.returncode == 0:
            self.refresh_accounts()
        else:
            self.set_busy("Save failed")

    def export_all(self) -> None:
        path = filedialog.asksaveasfilename(
            parent=self.root,
            title="Export all accounts",
            defaultextension=".tar.gz",
            filetypes=[("cx backup", "*.tar.gz"), ("All files", "*.*")],
        )
        if not path:
            return
        target_path = self.runner.target_path(self.target_var.get(), path)
        self.run_background("Exporting accounts", ["export", "--output", target_path], self.on_export_done, timeout=90)

    def export_selected(self) -> None:
        aliases = self.selected_aliases()
        if not aliases:
            messagebox.showinfo(APP_TITLE, "Select one or more accounts first.", parent=self.root)
            return
        path = filedialog.asksaveasfilename(
            parent=self.root,
            title="Export selected accounts",
            defaultextension=".tar.gz",
            initialfile=self.default_selected_backup_name(aliases),
            filetypes=[("cx backup", "*.tar.gz"), ("All files", "*.*")],
        )
        if not path:
            return
        target_path = self.runner.target_path(self.target_var.get(), path)
        self.run_background("Exporting selected accounts", ["export", *aliases, "--output", target_path], self.on_export_done, timeout=90)

    def export_filtered(self) -> None:
        dialog = ExportFilterDialog(self.root, self.selected_aliases())
        if not dialog.result:
            return
        aliases, emails = dialog.result
        path = filedialog.asksaveasfilename(
            parent=self.root,
            title="Export filtered accounts",
            defaultextension=".tar.gz",
            filetypes=[("cx backup", "*.tar.gz"), ("All files", "*.*")],
        )
        if not path:
            return
        target_path = self.runner.target_path(self.target_var.get(), path)
        args = ["export", "--output", target_path]
        for alias in aliases:
            args.extend(["--alias", alias])
        for email in emails:
            args.extend(["--email", email])
        self.run_background("Exporting filtered accounts", args, self.on_export_done, timeout=90)

    def on_export_done(self, result: CommandResult) -> None:
        self.log_command_result(result)
        self.set_busy("Ready" if result.returncode == 0 else "Export failed")

    def import_backup(self) -> None:
        path = self.select_backup_file("Import backup")
        if not path:
            return
        target_path = self.runner.target_path(self.target_var.get(), path)
        self.run_background("Reading backup", ["backup-list", target_path, "--json"], lambda result: self.on_backup_ready_for_import(result, target_path), timeout=90)

    def on_backup_ready_for_import(self, result: CommandResult, archive_path: str) -> None:
        self.log_command_result(result)
        if result.returncode != 0:
            self.set_busy("Backup read failed")
            return
        accounts = self.parse_backup_accounts(result)
        if accounts is None:
            self.set_busy("Backup read failed")
            return
        dialog = BackupSelectionDialog(self.root, "Import Backup", accounts, import_mode=True)
        if not dialog.result:
            self.set_busy("Ready")
            return
        aliases, emails, force, skip_existing, set_current = dialog.result
        args = ["import", archive_path]
        if aliases and len(aliases) != len(accounts):
            args.extend(["--alias", ",".join(aliases)])
        for email in emails:
            args.extend(["--email", email])
        if force:
            args.append("--force")
        if skip_existing:
            args.append("--skip-existing")
        if set_current:
            args.append("--set-current")
        self.run_background("Importing backup", args, self.on_import_done, timeout=90)

    def on_import_done(self, result: CommandResult) -> None:
        self.log_command_result(result)
        if result.returncode == 0:
            self.refresh_accounts()
        else:
            self.set_busy("Import failed")

    def inspect_backup(self) -> None:
        path = self.select_backup_file("Inspect backup")
        if not path:
            return
        target_path = self.runner.target_path(self.target_var.get(), path)
        self.run_background("Inspecting backup", ["backup-list", target_path, "--json"], self.on_backup_list_done)

    def on_backup_list_done(self, result: CommandResult) -> None:
        self.log_command_result(result)
        if result.returncode == 0:
            accounts = self.parse_backup_accounts(result)
            if accounts is not None:
                BackupSelectionDialog(self.root, "Backup Contents", accounts, import_mode=False)
        self.set_busy("Ready" if result.returncode == 0 else "Inspect failed")

    def parse_backup_accounts(self, result: CommandResult) -> list[dict[str, object]] | None:
        try:
            payload = json.loads(result.stdout or "{}")
        except json.JSONDecodeError as exc:
            self.log(f"JSON parse error: {exc}")
            return None
        accounts = payload.get("accounts")
        if not isinstance(accounts, list):
            self.log("Backup JSON does not contain an accounts list.")
            return None
        return [item for item in accounts if isinstance(item, dict)]

    def select_backup_file(self, title: str) -> str:
        return filedialog.askopenfilename(
            parent=self.root,
            title=title,
            filetypes=[("cx backup", "*.tar.gz"), ("All files", "*.*")],
        )

    @staticmethod
    def default_selected_backup_name(aliases: list[str]) -> str:
        if len(aliases) == 1:
            return f"cx-{aliases[0]}-backup.tar.gz"
        return f"cx-{len(aliases)}-accounts-backup.tar.gz"

    @staticmethod
    def best_status_message(result: CommandResult) -> str | None:
        for line in result.stdout.splitlines():
            if "：" in line and ("最佳帳號" in line or "best" in line.lower()):
                alias = line.split("：", 1)[-1].strip()
                if alias:
                    return f"Switched to {alias}"
            if line.lower().startswith("switched"):
                return line.strip()
        return None

    def log_command_result(self, result: CommandResult, show: bool = False) -> None:
        if show or result.returncode != 0:
            self.show_log_panel()
        self.log("$ " + result.display)
        if result.stdout.strip():
            self.log(result.stdout.rstrip())
        if result.stderr.strip():
            self.log(result.stderr.rstrip())
        if result.returncode != 0:
            self.log(f"Exit code: {result.returncode}")

    def render_accounts(self) -> None:
        selected = set(self.selected_aliases())
        self.tree.delete(*self.tree.get_children())
        rows = sorted(self.accounts.values(), key=lambda row: (row.rank is None, row.rank or 0, row.alias.lower()))
        for row in rows:
            alias = row.alias
            tags = []
            if row.current:
                tags.append("current")
            if row.error:
                tags.append("error")
            self.tree.insert(
                "",
                "end",
                iid=alias,
                tags=tuple(tags),
                values=(
                    "Current" if row.current else "",
                    row.rank or "",
                    row.alias,
                    row.scope or "",
                    row.email or "",
                    row.plan or "",
                    self.format_limit(row.primary_used),
                    self.format_limit_reset(row.primary_reset),
                    self.format_limit(row.secondary_used),
                    self.format_limit_reset(row.secondary_reset),
                    row.error or "",
                ),
            )
        restored = [alias for alias in selected if alias in self.accounts]
        if restored:
            self.tree.selection_set(restored)
        self.on_selection_changed()

    @staticmethod
    def format_limit(used: int | None) -> str:
        if used is None:
            return ""
        return f"{used}%"

    @staticmethod
    def format_limit_reset(reset: str | None) -> str:
        if not reset:
            return "n/a"
        return CxGui.format_reset(reset)

    @staticmethod
    def format_reset(reset: str) -> str:
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                parsed = dt.datetime.strptime(reset, fmt)
            except ValueError:
                continue
            if parsed.year == dt.datetime.now().year:
                return parsed.strftime("%m-%d %H:%M" if "%H" in fmt else "%m-%d")
            return parsed.strftime("%Y-%m-%d %H:%M" if "%H" in fmt else "%Y-%m-%d")
        return reset


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--preview", action="store_true")
    args, _unknown = parser.parse_known_args(argv)

    root, theme_info, theme_tokens = create_root_and_theme(APP_TITLE)
    preview_rows = None
    if args.preview:
        from cx_account_manager.gui_preview import sample_accounts

        preview_rows = sample_accounts()
    CxGui(root, theme_info=theme_info, theme_tokens=theme_tokens, preview_rows=preview_rows)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
