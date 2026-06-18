#!/usr/bin/env python3

from __future__ import annotations

import json
import math
import os
import re
import shutil
import shlex
import subprocess
import sys
import threading
import webbrowser
import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from tkinter import BooleanVar, Canvas, PanedWindow, PhotoImage, StringVar, Tk, Toplevel, filedialog, messagebox, simpledialog, ttk
from tkinter.scrolledtext import ScrolledText


APP_TITLE = "cx Account Manager"
TIMEOUT_SEC = 45
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


class IconFactory:
    def __init__(self, assets_dir: Path, size: int = 24, color: str = "#1f2937") -> None:
        self.assets_dir = assets_dir
        self.size = size
        self.color = color

    def create(self, name: str) -> PhotoImage:
        path = self.assets_dir / f"{name}.png"
        if path.exists():
            try:
                return PhotoImage(file=str(path))
            except Exception:
                pass

        image = PhotoImage(width=self.size, height=self.size)
        draw = {
            "refresh": self._refresh,
            "status": self._status,
            "add": self._add,
            "save": self._save,
            "use": self._use,
            "best": self._best,
            "scope_work": self._briefcase,
            "scope_personal": self._person,
            "remove": self._remove,
            "export_all": self._archive,
            "export_selected": self._export_selected,
            "export_filtered": self._filter,
            "import": self._import,
            "inspect": self._inspect,
        }.get(name, self._status)
        draw(image)
        return image

    def _dot(self, image: PhotoImage, x: int, y: int, color: str | None = None) -> None:
        if 0 <= x < self.size and 0 <= y < self.size:
            image.put(color or self.color, (x, y))

    def _line(self, image: PhotoImage, x1: int, y1: int, x2: int, y2: int, width: int = 2) -> None:
        steps = max(abs(x2 - x1), abs(y2 - y1), 1)
        radius = max(0, width // 2)
        for step in range(steps + 1):
            x = round(x1 + (x2 - x1) * step / steps)
            y = round(y1 + (y2 - y1) * step / steps)
            for dx in range(-radius, radius + 1):
                for dy in range(-radius, radius + 1):
                    self._dot(image, x + dx, y + dy)

    def _rect(self, image: PhotoImage, x1: int, y1: int, x2: int, y2: int, width: int = 2) -> None:
        self._line(image, x1, y1, x2, y1, width)
        self._line(image, x2, y1, x2, y2, width)
        self._line(image, x2, y2, x1, y2, width)
        self._line(image, x1, y2, x1, y1, width)

    def _circle(self, image: PhotoImage, cx: int, cy: int, radius: int, start: int = 0, end: int = 360) -> None:
        for degree in range(start, end + 1, 3):
            rad = degree * math.pi / 180
            x = round(cx + radius * math.cos(rad))
            y = round(cy + radius * math.sin(rad))
            self._dot(image, x, y)
            self._dot(image, x + 1, y)
            self._dot(image, x, y + 1)

    def _refresh(self, image: PhotoImage) -> None:
        self._circle(image, 12, 12, 8, 35, 315)
        self._line(image, 18, 5, 21, 5)
        self._line(image, 20, 4, 20, 8)

    def _status(self, image: PhotoImage) -> None:
        self._rect(image, 5, 5, 19, 19)
        self._line(image, 8, 15, 11, 11)
        self._line(image, 11, 11, 14, 13)
        self._line(image, 14, 13, 17, 8)

    def _add(self, image: PhotoImage) -> None:
        self._circle(image, 12, 12, 8)
        self._line(image, 12, 7, 12, 17)
        self._line(image, 7, 12, 17, 12)

    def _save(self, image: PhotoImage) -> None:
        self._rect(image, 5, 4, 19, 20)
        self._rect(image, 8, 5, 16, 10, 1)
        self._line(image, 8, 17, 16, 17)
        self._line(image, 8, 14, 16, 14)

    def _use(self, image: PhotoImage) -> None:
        self._line(image, 5, 12, 15, 12)
        self._line(image, 12, 8, 16, 12)
        self._line(image, 12, 16, 16, 12)
        self._rect(image, 5, 5, 19, 19)

    def _best(self, image: PhotoImage) -> None:
        self._line(image, 12, 4, 14, 10)
        self._line(image, 14, 10, 20, 10)
        self._line(image, 20, 10, 15, 14)
        self._line(image, 15, 14, 17, 20)
        self._line(image, 17, 20, 12, 16)
        self._line(image, 12, 16, 7, 20)
        self._line(image, 7, 20, 9, 14)
        self._line(image, 9, 14, 4, 10)
        self._line(image, 4, 10, 10, 10)
        self._line(image, 10, 10, 12, 4)

    def _briefcase(self, image: PhotoImage) -> None:
        self._rect(image, 4, 9, 20, 19)
        self._line(image, 9, 9, 9, 6)
        self._line(image, 9, 6, 15, 6)
        self._line(image, 15, 6, 15, 9)
        self._line(image, 4, 13, 20, 13)

    def _person(self, image: PhotoImage) -> None:
        self._circle(image, 12, 8, 4)
        self._circle(image, 12, 22, 8, 205, 335)

    def _remove(self, image: PhotoImage) -> None:
        self._line(image, 8, 8, 16, 16)
        self._line(image, 16, 8, 8, 16)
        self._circle(image, 12, 12, 8)

    def _archive(self, image: PhotoImage) -> None:
        self._rect(image, 5, 7, 19, 19)
        self._line(image, 5, 10, 19, 10)
        self._line(image, 10, 14, 14, 14)

    def _export_selected(self, image: PhotoImage) -> None:
        self._archive(image)
        self._line(image, 12, 3, 12, 12)
        self._line(image, 8, 7, 12, 3)
        self._line(image, 16, 7, 12, 3)

    def _filter(self, image: PhotoImage) -> None:
        self._line(image, 4, 6, 20, 6)
        self._line(image, 7, 11, 17, 11)
        self._line(image, 10, 16, 14, 16)

    def _import(self, image: PhotoImage) -> None:
        self._rect(image, 5, 7, 19, 19)
        self._line(image, 12, 3, 12, 14)
        self._line(image, 8, 10, 12, 14)
        self._line(image, 16, 10, 12, 14)

    def _inspect(self, image: PhotoImage) -> None:
        self._circle(image, 10, 10, 6)
        self._line(image, 15, 15, 20, 20)


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
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1180x680")
        self.repo_root = Path(__file__).resolve().parents[1]
        self.runner = CxRunner(self.repo_root)
        self.settings_file = self.default_settings_file()
        self.environment_values = self.detect_environment_values()
        self.target_var = StringVar(value=self.load_target_setting())
        self.status_var = StringVar(value="Ready")
        self.accounts: dict[str, AccountRow] = {}
        self.busy_count = 0
        self.busy_controls: list[ttk.Widget] = []
        self.icon_factory = IconFactory(self.repo_root / "gui" / "assets" / "icons")
        self.icons: dict[str, PhotoImage] = {}

        self._build_ui()
        self.refresh_accounts()

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)
        self.configure_styles()

        ribbon_shell = ttk.Frame(self.root, padding=(8, 4, 8, 1), style="Ribbon.TFrame")
        ribbon_shell.grid(row=0, column=0, sticky="ew")
        ribbon_shell.columnconfigure(0, weight=1)
        ribbon_shell.columnconfigure(1, weight=0)

        ribbon_canvas = Canvas(
            ribbon_shell,
            height=68,
            bg="#f3f4f6",
            highlightthickness=0,
            xscrollincrement=24,
        )
        ribbon_scroll = ttk.Scrollbar(ribbon_shell, orient="horizontal", command=ribbon_canvas.xview)
        ribbon_canvas.configure(xscrollcommand=ribbon_scroll.set)
        ribbon_canvas.grid(row=0, column=0, sticky="ew")
        ribbon_scroll.grid(row=1, column=0, sticky="ew")

        ribbon = ttk.Frame(ribbon_canvas, style="Ribbon.TFrame")
        ribbon_window = ribbon_canvas.create_window((0, 0), window=ribbon, anchor="nw")
        ribbon.bind("<Configure>", lambda _event: self.on_ribbon_configure(ribbon_canvas, ribbon_window))
        ribbon_canvas.bind("<Configure>", lambda _event: self.on_ribbon_canvas_configure(ribbon_canvas, ribbon_window))
        ribbon_canvas.bind("<Shift-MouseWheel>", lambda event: self.on_ribbon_mousewheel(ribbon_canvas, event))
        ribbon_canvas.bind("<MouseWheel>", lambda event: self.on_ribbon_mousewheel(ribbon_canvas, event))

        target_group, target_buttons = self.create_ribbon_group(ribbon, "Environment")
        target_group.pack(side="left", fill="y")
        ttk.Label(target_buttons, text="ENVIRONMENT", style="Environment.TLabel").pack(anchor="w", padx=4)
        target = ttk.Combobox(target_buttons, textvariable=self.target_var, values=self.environment_values, state="readonly", width=22, style="Environment.TCombobox")
        target.pack(anchor="w", padx=4, pady=(1, 1))
        target.bind("<<ComboboxSelected>>", self.on_target_changed)
        self.add_ribbon_separator(ribbon)

        account_group, account_buttons = self.create_ribbon_group(ribbon, "Account")
        account_group.pack(side="left", fill="y")
        self.add_busy_button(account_buttons, text="Refresh", icon="refresh", command=self.refresh_accounts, tooltip="Reload saved accounts for the selected target environment.").pack(side="left", padx=1)
        self.add_busy_button(account_buttons, text="Status", icon="status", command=self.refresh_status_all, tooltip="Query usage and ranking for all saved accounts without switching accounts.").pack(side="left", padx=1)
        self.add_busy_button(account_buttons, text="Add\nAccount", icon="add", command=self.add_account, tooltip="Log in with Codex device auth and save the account under a new alias.").pack(side="left", padx=1)
        self.add_busy_button(account_buttons, text="Save\nCurrent", icon="save", command=self.save_current, tooltip="Save the currently active Codex auth.json as a named account alias.").pack(side="left", padx=1)
        self.add_ribbon_separator(ribbon)

        selection_group, selection_buttons = self.create_ribbon_group(ribbon, "Selection")
        selection_group.pack(side="left", fill="y")
        self.add_busy_button(selection_buttons, text="Use\nSelected", icon="use", command=self.use_selected, tooltip="Switch the selected alias into this target environment's CODEX_HOME/auth.json.").pack(side="left", padx=1)
        self.add_busy_button(selection_buttons, text="Best", icon="best", command=self.switch_to_best, tooltip="Automatically switch to the best-ranked usable account right now.").pack(side="left", padx=1)
        self.add_busy_button(selection_buttons, text="Status\nSelected", icon="status", command=self.refresh_status_selected, tooltip="Query usage for the selected account only.").pack(side="left", padx=1)
        self.add_busy_button(selection_buttons, text="Remove", icon="remove", command=self.remove_selected, tooltip="Delete the selected saved account from cx storage.").pack(side="left", padx=1)
        self.add_ribbon_separator(ribbon)

        scope_group, scope_buttons = self.create_ribbon_group(ribbon, "Scope")
        scope_group.pack(side="left", fill="y")
        self.add_busy_button(scope_buttons, text="Work", icon="scope_work", command=lambda: self.set_selected_scope("work"), tooltip="Mark the selected account as a work account for ranking priority.").pack(side="left", padx=1)
        self.add_busy_button(scope_buttons, text="Personal", icon="scope_personal", command=lambda: self.set_selected_scope("personal"), tooltip="Mark the selected account as a personal account.").pack(side="left", padx=1)
        self.add_ribbon_separator(ribbon)

        backup_group, backup_buttons = self.create_ribbon_group(ribbon, "Backup")
        backup_group.pack(side="left", fill="y")
        self.add_busy_button(backup_buttons, text="Export\nAll", icon="export_all", command=self.export_all, tooltip="Export every saved account into a backup archive.").pack(side="left", padx=1)
        self.add_busy_button(backup_buttons, text="Export\nSelected", icon="export_selected", command=self.export_selected, tooltip="Export only the accounts selected in the table.").pack(side="left", padx=1)
        self.add_busy_button(backup_buttons, text="Export\nFiltered", icon="export_filtered", command=self.export_filtered, tooltip="Export accounts matched by alias and/or email filters.").pack(side="left", padx=1)
        self.add_busy_button(backup_buttons, text="Import", icon="import", command=self.import_backup, tooltip="Import selected accounts from a cx backup archive.").pack(side="left", padx=1)
        self.add_busy_button(backup_buttons, text="Inspect", icon="inspect", command=self.inspect_backup, tooltip="Open a backup archive and preview its accounts without importing.").pack(side="left", padx=1)

        status_bar = ttk.Frame(ribbon_shell, style="Ribbon.TFrame")
        status_bar.grid(row=0, column=1, rowspan=2, sticky="ne", padx=(8, 0))
        ttk.Label(status_bar, textvariable=self.status_var, style="RibbonStatus.TLabel").pack(anchor="e", pady=(8, 0))
        self.bind_ribbon_mousewheel(ribbon_shell, ribbon_canvas)

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

        columns = ("current", "rank", "alias", "scope", "email", "plan", "primary", "secondary", "error")
        self.tree = ttk.Treeview(upper, columns=columns, show="headings", selectmode="extended")
        headings = {
            "current": "*",
            "rank": "Rank",
            "alias": "Alias",
            "scope": "Scope",
            "email": "Email",
            "plan": "Plan",
            "primary": "5h",
            "secondary": "7d",
            "error": "Error",
        }
        widths = {"current": 36, "rank": 58, "alias": 130, "scope": 90, "email": 250, "plan": 90, "primary": 180, "secondary": 180, "error": 260}
        for column, heading in headings.items():
            self.tree.heading(column, text=heading)
            self.tree.column(column, width=widths[column], anchor="w", stretch=column in {"email", "primary", "secondary", "error"})
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree.bind("<Double-1>", lambda _event: self.use_selected())

        self.output = ScrolledText(lower, height=10, wrap="word")
        self.output.grid(row=0, column=0, sticky="nsew")
        self.root.after_idle(lambda: main_pane.sash_place(0, 0, 420))

    def configure_styles(self) -> None:
        style = ttk.Style(self.root)
        style.configure("Ribbon.TFrame", background="#f3f4f6")
        style.configure("RibbonGroup.TFrame", background="#f3f4f6")
        style.configure("RibbonGroup.TLabel", background="#f3f4f6", foreground="#4b5563", font=("", 8))
        style.configure("RibbonStatus.TLabel", background="#f3f4f6", foreground="#374151")
        style.configure("Ribbon.TButton", padding=(3, 2))
        style.configure("Environment.TLabel", background="#f3f4f6", foreground="#b91c1c", font=("", 11, "bold"))
        style.configure("Environment.TCombobox", foreground="#b91c1c", font=("", 11, "bold"))

    def create_ribbon_group(self, parent: ttk.Frame, title: str) -> tuple[ttk.Frame, ttk.Frame]:
        group = ttk.Frame(parent, padding=(3, 0), style="RibbonGroup.TFrame")
        commands = ttk.Frame(group, style="RibbonGroup.TFrame")
        commands.grid(row=0, column=0, sticky="n")
        ttk.Label(group, text=title, style="RibbonGroup.TLabel", anchor="center").grid(row=1, column=0, sticky="ew", pady=(1, 0))
        return group, commands

    def on_ribbon_configure(self, canvas: Canvas, window_id: int) -> None:
        canvas.update_idletasks()
        bbox = canvas.bbox(window_id)
        if bbox:
            canvas.configure(scrollregion=bbox)

    def on_ribbon_canvas_configure(self, canvas: Canvas, window_id: int) -> None:
        canvas.update_idletasks()
        bbox = canvas.bbox(window_id)
        content_width = bbox[2] - bbox[0] if bbox else 0
        canvas.itemconfigure(window_id, width=max(canvas.winfo_width(), content_width))
        self.on_ribbon_configure(canvas, window_id)

    @staticmethod
    def on_ribbon_mousewheel(canvas: Canvas, event) -> str:
        delta = getattr(event, "delta", 0)
        if delta:
            canvas.xview_scroll(-1 * int(delta / 120), "units")
        elif getattr(event, "num", None) == 4:
            canvas.xview_scroll(-3, "units")
        elif getattr(event, "num", None) == 5:
            canvas.xview_scroll(3, "units")
        return "break"

    def bind_ribbon_mousewheel(self, widget: ttk.Widget, canvas: Canvas) -> None:
        widget.bind("<MouseWheel>", lambda event: self.on_ribbon_mousewheel(canvas, event))
        widget.bind("<Shift-MouseWheel>", lambda event: self.on_ribbon_mousewheel(canvas, event))
        widget.bind("<Button-4>", lambda event: self.on_ribbon_mousewheel(canvas, event))
        widget.bind("<Button-5>", lambda event: self.on_ribbon_mousewheel(canvas, event))
        for child in widget.winfo_children():
            self.bind_ribbon_mousewheel(child, canvas)

    def add_ribbon_separator(self, parent: ttk.Frame) -> None:
        ttk.Separator(parent, orient="vertical").pack(side="left", fill="y", padx=(2, 4), pady=2)

    def add_busy_button(self, parent, **kwargs) -> ttk.Button:
        icon = kwargs.pop("icon", None)
        tooltip = kwargs.pop("tooltip", None)
        if icon:
            if icon not in self.icons:
                self.icons[icon] = self.icon_factory.create(icon)
            kwargs["text"] = self.ribbon_button_text(str(kwargs.get("text", "")))
            kwargs.setdefault("image", self.icons[icon])
            kwargs.setdefault("compound", "top")
            kwargs.setdefault("style", "Ribbon.TButton")
            kwargs.setdefault("width", 8)
        button = ttk.Button(parent, **kwargs)
        if tooltip:
            ToolTip(button, tooltip)
        self.busy_controls.append(button)
        return button

    @staticmethod
    def ribbon_button_text(text: str) -> str:
        return text if "\n" in text else f"{text}\n "

    def selected_alias(self) -> str | None:
        selection = self.tree.selection()
        if not selection:
            return None
        return str(selection[0])

    def selected_aliases(self) -> list[str]:
        return [str(alias) for alias in self.tree.selection()]

    def on_target_changed(self, _event=None) -> None:
        self.save_target_setting(self.target_var.get())
        self.refresh_accounts()

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
        self.output.insert("end", text)
        if not text.endswith("\n"):
            self.output.insert("end", "\n")
        self.output.see("end")

    def set_busy(self, text: str) -> None:
        self.status_var.set(text)

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

    def run_background(self, label: str, args: list[str], callback, timeout: int = TIMEOUT_SEC) -> None:
        target = self.target_var.get()
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

    def on_accounts_status_loaded(self, result: CommandResult) -> None:
        if not result.stdout.strip():
            self.set_busy("Status unavailable; loading account list")
            self.run_background("Refreshing accounts", ["list", "--json"], self.on_accounts_list_loaded)
            return
        try:
            payload = json.loads(result.stdout or "{}")
        except json.JSONDecodeError:
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
            self.set_busy("Ready")
        else:
            self.set_busy("Ready with status errors")

    def on_accounts_list_loaded(self, result: CommandResult) -> None:
        if result.returncode != 0:
            self.set_busy("Refresh failed")
            return
        try:
            payload = json.loads(result.stdout or "{}")
        except json.JSONDecodeError:
            self.set_busy("Refresh failed")
            return

        self.accounts = {}
        for item in payload.get("accounts", []):
            row = AccountRow(alias=item["alias"], current=bool(item.get("current")), scope=item.get("scope"))
            self.accounts[row.alias] = row
        self.render_accounts()
        self.set_busy("Ready")

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
        self.log_command_result(result)
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

    def switch_to_best(self) -> None:
        self.run_background("Switching to best account", ["best"], self.on_best_done, timeout=90)

    def on_best_done(self, result: CommandResult) -> None:
        self.log_command_result(result)
        if result.returncode == 0:
            self.refresh_accounts()
        else:
            self.set_busy("Best switch failed")

    def set_selected_scope(self, scope: str) -> None:
        alias = self.selected_alias()
        if not alias:
            messagebox.showinfo(APP_TITLE, "Select an account first.", parent=self.root)
            return
        self.run_background(f"Setting {alias} scope", ["scope", alias, scope], self.on_scope_done)

    def on_scope_done(self, result: CommandResult) -> None:
        self.log_command_result(result)
        if result.returncode == 0:
            self.refresh_accounts()
        else:
            self.set_busy("Scope update failed")

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
        LoginDialog(self.root, self.runner, self.target_var.get(), alias, force, self.on_add_done)

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
        rows = sorted(self.accounts.values(), key=lambda row: (row.rank is None, row.rank or 0, row.alias.lower()))
        for row in rows:
            alias = row.alias
            self.tree.insert(
                "",
                "end",
                iid=alias,
                values=(
                    "*" if row.current else "",
                    row.rank or "",
                    row.alias,
                    row.scope or "",
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
            value += f" | {CxGui.format_reset(reset)}"
        return value

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


def main() -> int:
    root = Tk()
    CxGui(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
