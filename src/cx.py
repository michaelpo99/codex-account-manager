#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from queue import Empty, Queue
from typing import Any

SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from cx_ranking import (
    AccountStatus,
    account_status_blocked,
    is_blocked,
    status_sort_key,
)

if os.name == "nt":
    import msvcrt
else:
    import fcntl


APP_NAME = "cx"
ALIAS_RE = re.compile(r"^[A-Za-z0-9_-]+$")
ACCOUNT_SCOPE_RE = re.compile(r"^(work|personal)$")


def default_data_dir() -> Path:
    if os.name == "nt":
        local_appdata = os.environ.get("LOCALAPPDATA")
        if local_appdata:
            return Path(local_appdata) / "cx"
        return Path.home() / "AppData" / "Local" / "cx"
    return Path.home() / ".local" / "share" / "cx"


def default_codex_home() -> Path:
    configured = os.environ.get("CODEX_HOME")
    if configured:
        return Path(configured)
    return Path.home() / ".codex"


DATA_DIR = default_data_dir()
ACCOUNTS_DIR = DATA_DIR / "accounts"
CURRENT_FILE = DATA_DIR / "current"
LOCK_FILE = DATA_DIR / "lock"
TEMP_DIR = DATA_DIR / "tmp"
CODEX_HOME = default_codex_home()
CODEX_AUTH_FILE = CODEX_HOME / "auth.json"
BACKUP_VERSION = 2
APP_SERVER_METHODS = {
    2: "account/read",
    3: "account/rateLimits/read",
}
MANUAL_FORMATS = ("markdown",)
MANUAL_LANGUAGES = ("zh-TW", "en")
MANUAL_COMMANDS = [
    ("add", "cx add <alias> [--force]"),
    ("save", "cx save <alias> [--force]"),
    ("list", "cx list | cx ls"),
    ("use", "cx use <alias>"),
    ("current", "cx current | cx who"),
    ("scope", "cx scope <alias> <work|personal>"),
    ("status", "cx status [alias]"),
    ("best", "cx best [--allow-blocked]"),
    ("export", "cx export [alias...] [--alias ...] [--email ...] [-o PATH]"),
    ("import", "cx import <archive> [--alias ...] [--email ...] [--force|--skip-existing] [--set-current]"),
    ("backup-list", "cx backup-list <archive>"),
    ("remove", "cx remove <alias> [--yes]"),
]


class CxError(Exception):
    pass


@dataclass
class BackupAccountSummary:
    alias: str
    email: str | None
    scope: str
    plan: str | None


class FileLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.handle = None

    def __enter__(self) -> "FileLock":
        ensure_dir(DATA_DIR, mode=0o700)
        if os.name == "nt":
            self.handle = self.path.open("a+b")
            self.handle.seek(0, os.SEEK_END)
            if self.handle.tell() == 0:
                self.handle.write(b"\0")
                self.handle.flush()
            self.handle.seek(0)
            msvcrt.locking(self.handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            self.handle = self.path.open("a+", encoding="utf-8")
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.handle is not None:
            if os.name == "nt":
                self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            self.handle.close()


def safe_chmod(path: Path, mode: int) -> None:
    try:
        os.chmod(path, mode)
    except OSError:
        pass


def ensure_dir(path: Path, mode: int = 0o700) -> None:
    path.mkdir(parents=True, exist_ok=True)
    safe_chmod(path, mode)


def ensure_layout() -> None:
    ensure_dir(DATA_DIR, mode=0o700)
    ensure_dir(ACCOUNTS_DIR, mode=0o700)
    ensure_dir(TEMP_DIR, mode=0o700)
    if not LOCK_FILE.exists():
        LOCK_FILE.touch(mode=0o600, exist_ok=True)
    safe_chmod(LOCK_FILE, 0o600)


def validate_alias(alias: str) -> str:
    if not alias or not ALIAS_RE.fullmatch(alias):
        raise CxError("alias 只能包含英文字母、數字、底線與連字號")
    return alias


def validate_scope(scope: str) -> str:
    value = scope.strip().lower()
    if not ACCOUNT_SCOPE_RE.fullmatch(value):
        raise CxError("scope 只能是 `work` 或 `personal`")
    return value


def account_dir(alias: str) -> Path:
    return ACCOUNTS_DIR / alias


def account_auth_file(alias: str) -> Path:
    return account_dir(alias) / "auth.json"


def account_meta_file(alias: str) -> Path:
    return account_dir(alias) / "meta.json"


def make_temp_codex_home(prefix: str) -> Path:
    ensure_layout()
    temp_home = Path(tempfile.mkdtemp(prefix=prefix, dir=TEMP_DIR))
    safe_chmod(temp_home, 0o700)
    return temp_home


def add_bytes_to_tar(tar: tarfile.TarFile, name: str, data: bytes, mode: int) -> None:
    info = tarfile.TarInfo(name=name)
    info.size = len(data)
    info.mode = mode
    info.mtime = int(time.time())
    tar.addfile(info, io.BytesIO(data))


def read_tar_member(tar: tarfile.TarFile, name: str, required: bool = True) -> bytes | None:
    try:
        member = tar.getmember(name)
    except KeyError:
        if required:
            raise
        return None
    if not member.isfile():
        raise CxError(f"備份檔內容不合法：`{name}` 不是一般檔案。")
    extracted = tar.extractfile(member)
    if extracted is None:
        raise CxError(f"備份檔內容不合法：無法讀取 `{name}`。")
    return extracted.read()


def atomic_copy(src: Path, dest: Path, mode: int = 0o600) -> None:
    ensure_dir(dest.parent, mode=0o700)
    with tempfile.NamedTemporaryFile(dir=dest.parent, delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        shutil.copyfile(src, tmp_path)
        safe_chmod(tmp_path, mode)
        os.replace(tmp_path, dest)
    finally:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)


def write_bytes_atomic(dest: Path, data: bytes, mode: int = 0o600) -> None:
    ensure_dir(dest.parent, mode=0o700)
    with tempfile.NamedTemporaryFile("wb", dir=dest.parent, delete=False) as tmp:
        tmp.write(data)
        tmp_path = Path(tmp.name)
    try:
        safe_chmod(tmp_path, mode)
        os.replace(tmp_path, dest)
    finally:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)


def write_text_atomic(dest: Path, text: str, mode: int = 0o600) -> None:
    ensure_dir(dest.parent, mode=0o700)
    with tempfile.NamedTemporaryFile("w", dir=dest.parent, encoding="utf-8", delete=False) as tmp:
        tmp.write(text)
        tmp_path = Path(tmp.name)
    try:
        safe_chmod(tmp_path, mode)
        os.replace(tmp_path, dest)
    finally:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)


def read_current_alias() -> str | None:
    if not CURRENT_FILE.exists():
        return None
    value = CURRENT_FILE.read_text(encoding="utf-8").strip()
    return value or None


def set_current_alias(alias: str | None) -> None:
    if alias is None:
        CURRENT_FILE.unlink(missing_ok=True)
        return
    write_text_atomic(CURRENT_FILE, alias + "\n")


def read_account_scope(alias: str) -> str:
    meta_file = account_meta_file(alias)
    if not meta_file.exists():
        return "work"
    try:
        payload = json.loads(meta_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "work"
    scope = payload.get("scope")
    if isinstance(scope, str) and ACCOUNT_SCOPE_RE.fullmatch(scope):
        return scope
    return "work"


def write_account_scope(alias: str, scope: str) -> None:
    payload = {"scope": validate_scope(scope)}
    write_text_atomic(account_meta_file(alias), json.dumps(payload, ensure_ascii=True, indent=2) + "\n")


def find_first_string(payload: Any, candidate_keys: set[str]) -> str | None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in candidate_keys and isinstance(value, str) and value:
                return value
        for value in payload.values():
            found = find_first_string(value, candidate_keys)
            if found is not None:
                return found
    elif isinstance(payload, list):
        for value in payload:
            found = find_first_string(value, candidate_keys)
            if found is not None:
                return found
    return None


def extract_auth_summary(auth_payload: Any) -> tuple[str | None, str | None]:
    if not isinstance(auth_payload, (dict, list)):
        return None, None
    email = find_first_string(auth_payload, {"email"})
    plan = find_first_string(auth_payload, {"planType", "plan"})
    return email, plan


def read_account_summary_from_auth_bytes(auth_data: bytes) -> tuple[str | None, str | None]:
    try:
        payload = json.loads(auth_data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, None
    return extract_auth_summary(payload)


def read_local_account_summary(alias: str) -> BackupAccountSummary:
    email = None
    plan = None
    auth_file = account_auth_file(alias)
    if auth_file.exists():
        email, plan = read_account_summary_from_auth_bytes(auth_file.read_bytes())
    return BackupAccountSummary(
        alias=alias,
        email=email,
        scope=read_account_scope(alias),
        plan=plan,
    )


def windows_extra_path_dirs() -> list[str]:
    if os.name != "nt":
        return []
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

    try:
        import winreg

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
    except ImportError:
        pass

    return [path for path in dirs if path and Path(path).exists()]


def windows_codex_candidates() -> list[Path]:
    if os.name != "nt":
        return []
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


def windows_npm_codex_candidates(search_path: str) -> list[Path]:
    if os.name != "nt":
        return []
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


def is_wsl() -> bool:
    if os.name == "nt":
        return False
    try:
        version = Path("/proc/version").read_text(encoding="utf-8", errors="ignore").lower()
    except OSError:
        return False
    return "microsoft" in version or "wsl" in version


def find_codex_executable() -> str | None:
    configured = os.environ.get("CX_CODEX_BIN")
    if configured:
        configured_path = Path(configured)
        if configured_path.exists():
            return str(configured_path)
        resolved = shutil.which(configured)
        if resolved:
            return resolved

    if os.name == "nt":
        extra_dirs = windows_extra_path_dirs()
        search_path = os.pathsep.join(extra_dirs + [os.environ.get("PATH", "")])
        for name in ("codex.cmd", "codex.exe", "codex.bat", "codex"):
            resolved = shutil.which(name, path=search_path)
            if resolved:
                return resolved

        for candidate in windows_codex_candidates() + windows_npm_codex_candidates(search_path):
            if candidate.exists():
                return str(candidate)

    executable = shutil.which("codex")
    if executable is None:
        return None
    if os.name == "nt" and os.path.splitext(executable)[1] == "":
        cmd_executable = executable + ".cmd"
        if Path(cmd_executable).exists():
            return cmd_executable
    return executable


def codex_executable() -> str:
    executable = find_codex_executable()
    if executable is not None:
        return executable
    if is_wsl():
        raise CxError("WSL 裡找不到 `codex` 指令，請先在 WSL 安裝 Codex CLI。")
    raise CxError("找不到 `codex` 指令，請先安裝 Codex CLI，或設定 CX_CODEX_BIN 指向 codex.cmd。")


def codex_command(args: list[str]) -> list[str]:
    executable = codex_executable()
    if os.name == "nt" and os.path.splitext(executable)[1].lower() in {".bat", ".cmd"}:
        return [os.environ.get("COMSPEC", "cmd.exe"), "/c", executable, *args]
    return [executable, *args]


def require_codex() -> None:
    codex_executable()


def run_command(cmd: list[str], *, env: dict[str, str] | None = None, capture_output: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        env=env,
        text=True,
        check=False,
        capture_output=capture_output,
    )


def cmd_add(args: argparse.Namespace) -> int:
    alias = validate_alias(args.alias)
    codex = codex_command(["login", "--device-auth"])
    ensure_layout()
    target_dir = account_dir(alias)
    target_auth = account_auth_file(alias)

    if target_dir.exists() and not args.force:
        raise CxError(f"帳號 `{alias}` 已存在；若要覆蓋請使用 `--force`。")

    temp_home = make_temp_codex_home("cx-login-")
    try:
        print(f"請在瀏覽器中確認登入的是 `{alias}` 對應的帳號。", file=sys.stderr)
        env = os.environ.copy()
        env["CODEX_HOME"] = str(temp_home)
        result = run_command(codex, env=env)
        if result.returncode != 0:
            raise CxError(f"`codex login --device-auth` 失敗，退出碼 {result.returncode}")
        temp_auth = temp_home / "auth.json"
        if not temp_auth.exists():
            raise CxError("登入完成後沒有找到 auth.json，無法保存帳號。")

        with FileLock(LOCK_FILE):
            if target_dir.exists() and not args.force:
                raise CxError(f"帳號 `{alias}` 已存在；若要覆蓋請使用 `--force`。")
            if target_dir.exists():
                shutil.rmtree(target_dir)
            ensure_dir(target_dir, mode=0o700)
            atomic_copy(temp_auth, target_auth)
    finally:
        shutil.rmtree(temp_home, ignore_errors=True)

    print(f"已保存帳號：{alias}")
    return 0


def cmd_save(args: argparse.Namespace) -> int:
    alias = validate_alias(args.alias)
    ensure_layout()
    if not CODEX_AUTH_FILE.exists():
        raise CxError(f"目前找不到登入憑證：{CODEX_AUTH_FILE}")
    target_dir = account_dir(alias)
    target_auth = account_auth_file(alias)

    with FileLock(LOCK_FILE):
        if target_dir.exists() and not args.force:
            raise CxError(f"帳號 `{alias}` 已存在；若要覆蓋請使用 `--force`。")
        ensure_dir(target_dir, mode=0o700)
        atomic_copy(CODEX_AUTH_FILE, target_auth)

    print(f"已從目前登入狀態保存帳號：{alias}")
    return 0


def list_aliases() -> list[str]:
    ensure_layout()
    if not ACCOUNTS_DIR.exists():
        return []
    return sorted(path.name for path in ACCOUNTS_DIR.iterdir() if path.is_dir())


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def cmd_list(args: argparse.Namespace) -> int:
    aliases = list_aliases()
    current = read_current_alias()
    if args.json:
        print_json(
            {
                "current": current,
                "accounts": [
                    {
                        "alias": alias,
                        "current": alias == current,
                        "scope": read_account_scope(alias),
                    }
                    for alias in aliases
                ],
            }
        )
        return 0
    for alias in aliases:
        marker = "*" if alias == current else " "
        print(f"{marker} {alias} [{read_account_scope(alias)}]")
    return 0


def default_backup_path() -> Path:
    timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    return Path.cwd() / f"cx-backup-{timestamp}.tar.gz"


def validate_email_selector(value: str) -> str:
    email = value.strip()
    if not email:
        raise CxError("email selector 不可為空。")
    return email


def parse_selector_values(values: list[str] | None, *, kind: str) -> list[str]:
    if not values:
        return []
    parsed: list[str] = []
    seen: set[str] = set()
    for raw in values:
        for part in raw.split(","):
            item = part.strip()
            if not item:
                raise CxError(f"`--{kind}` 不能包含空項目。")
            value = validate_alias(item) if kind == "alias" else validate_email_selector(item)
            if value in seen:
                continue
            seen.add(value)
            parsed.append(value)
    return parsed


def validate_backup_summary(raw: Any) -> BackupAccountSummary:
    if not isinstance(raw, dict):
        raise CxError("備份檔中的 account 摘要格式不合法。")
    alias = raw.get("alias")
    if not isinstance(alias, str):
        raise CxError("備份檔中的 account 摘要缺少合法 alias。")
    scope = raw.get("scope", "work")
    if not isinstance(scope, str):
        raise CxError("備份檔中的 account 摘要缺少合法 scope。")
    email = raw.get("email")
    plan = raw.get("plan")
    if email is not None and not isinstance(email, str):
        raise CxError(f"備份檔中的 `{alias}` email 欄位格式不合法。")
    if plan is not None and not isinstance(plan, str):
        raise CxError(f"備份檔中的 `{alias}` plan 欄位格式不合法。")
    return BackupAccountSummary(
        alias=validate_alias(alias),
        email=email,
        scope=validate_scope(scope),
        plan=plan,
    )


def read_archive_account_summary(tar: tarfile.TarFile, names: set[str], alias: str) -> BackupAccountSummary:
    auth_name = f"accounts/{alias}/auth.json"
    try:
        auth_data = read_tar_member(tar, auth_name)
    except KeyError as exc:
        raise CxError(f"備份檔缺少 `{auth_name}`。") from exc
    email, plan = read_account_summary_from_auth_bytes(auth_data)
    scope = "work"
    meta_name = f"accounts/{alias}/meta.json"
    if meta_name in names:
        try:
            meta_payload = json.loads(read_tar_member(tar, meta_name).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CxError(f"備份檔中的 `{meta_name}` 無法解析。") from exc
        scope_value = meta_payload.get("scope")
        if isinstance(scope_value, str):
            scope = validate_scope(scope_value)
    return BackupAccountSummary(alias=alias, email=email, scope=scope, plan=plan)


def read_backup_manifest(
    tar: tarfile.TarFile,
) -> tuple[list[BackupAccountSummary], str | None]:
    names = set(tar.getnames())
    if "manifest.json" not in names:
        raise CxError("備份檔缺少 manifest.json。")
    try:
        manifest = json.loads(read_tar_member(tar, "manifest.json").decode("utf-8"))
    except (KeyError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise CxError("備份檔中的 manifest.json 無法解析。") from exc

    version = manifest.get("version")
    if version not in {1, BACKUP_VERSION}:
        raise CxError(f"不支援的備份版本：{version}")

    aliases = manifest.get("aliases")
    if not isinstance(aliases, list) or not aliases:
        raise CxError("備份檔缺少有效的 aliases 清單。")
    validated_aliases: list[str] = []
    for raw_alias in aliases:
        if not isinstance(raw_alias, str):
            raise CxError("備份檔中的 aliases 清單格式不合法。")
        validated_aliases.append(validate_alias(raw_alias))

    current_alias = manifest.get("current")
    if current_alias is not None:
        if not isinstance(current_alias, str):
            raise CxError("備份檔中的 current 欄位格式不合法。")
        current_alias = validate_alias(current_alias)
        if current_alias not in validated_aliases:
            raise CxError("備份檔中的 current 帳號不在 aliases 清單內。")

    summaries: list[BackupAccountSummary] = []
    if version == BACKUP_VERSION and isinstance(manifest.get("accounts"), list):
        raw_accounts = manifest["accounts"]
        summaries_by_alias = {summary.alias: summary for summary in (validate_backup_summary(raw) for raw in raw_accounts)}
        missing_aliases = [alias for alias in validated_aliases if alias not in summaries_by_alias]
        if missing_aliases:
            missing = ", ".join(missing_aliases)
            raise CxError(f"備份檔中的 accounts 摘要缺少 alias：{missing}")
        summaries = [summaries_by_alias[alias] for alias in validated_aliases]
    else:
        for alias in validated_aliases:
            summaries.append(read_archive_account_summary(tar, names, alias))

    return summaries, current_alias


def select_summaries(
    summaries: list[BackupAccountSummary],
    *,
    alias_selectors: list[str],
    email_selectors: list[str],
) -> tuple[list[BackupAccountSummary], list[tuple[str, list[BackupAccountSummary]]]]:
    if not alias_selectors and not email_selectors:
        return summaries, []

    summary_by_alias = {summary.alias: summary for summary in summaries}
    email_matches: list[tuple[str, list[BackupAccountSummary]]] = []
    matched_aliases: set[str] = set()
    missing_aliases = [alias for alias in alias_selectors if alias not in summary_by_alias]
    if missing_aliases:
        raise CxError(f"找不到以下 alias：{', '.join(missing_aliases)}")
    matched_aliases.update(alias_selectors)

    missing_emails: list[str] = []
    for email in email_selectors:
        matches = [summary for summary in summaries if summary.email == email]
        if not matches:
            missing_emails.append(email)
            continue
        if len(matches) > 1:
            email_matches.append((email, matches))
        matched_aliases.update(summary.alias for summary in matches)
    if missing_emails:
        raise CxError(f"找不到以下 email：{', '.join(missing_emails)}")

    selected = [summary for summary in summaries if summary.alias in matched_aliases]
    return selected, email_matches


def print_email_matches(email_matches: list[tuple[str, list[BackupAccountSummary]]], *, context: str) -> None:
    for email, matches in email_matches:
        print(f"{context} email `{email}` 命中 {len(matches)} 個帳號：")
        for summary in matches:
            plan = summary.plan or "-"
            print(f"- {summary.alias} | {summary.scope} | {plan}")


def cmd_export(args: argparse.Namespace) -> int:
    ensure_layout()
    positional_aliases = [validate_alias(alias) for alias in args.aliases] if args.aliases else []
    alias_selectors = positional_aliases + parse_selector_values(getattr(args, "alias_selectors", None), kind="alias")
    email_selectors = parse_selector_values(getattr(args, "email_selectors", None), kind="email")

    all_aliases = list_aliases()
    if not all_aliases:
        raise CxError("目前沒有可匯出的已保存帳號。")
    all_summaries = [read_local_account_summary(alias) for alias in all_aliases]
    selected_summaries, email_matches = select_summaries(
        all_summaries,
        alias_selectors=alias_selectors,
        email_selectors=email_selectors,
    )
    if not selected_summaries:
        raise CxError("目前沒有可匯出的已保存帳號。")
    print_email_matches(email_matches, context="匯出時")

    output = Path(args.output).expanduser() if args.output else default_backup_path()
    output.parent.mkdir(parents=True, exist_ok=True)

    current = read_current_alias()
    manifest = {
        "version": BACKUP_VERSION,
        "createdAt": dt.datetime.now().isoformat(timespec="seconds"),
        "aliases": [summary.alias for summary in selected_summaries],
        "accounts": [
            {
                "alias": summary.alias,
                "email": summary.email,
                "scope": summary.scope,
                "plan": summary.plan,
            }
            for summary in selected_summaries
        ],
        "current": current if any(summary.alias == current for summary in selected_summaries) else None,
    }

    with tarfile.open(output, "w:gz") as tar:
        add_bytes_to_tar(tar, "manifest.json", json.dumps(manifest, ensure_ascii=True, indent=2).encode("utf-8") + b"\n", 0o600)
        if manifest["current"] is not None:
            add_bytes_to_tar(tar, "current", (str(manifest["current"]) + "\n").encode("utf-8"), 0o600)
        for summary in selected_summaries:
            alias = summary.alias
            auth_data = account_auth_file(alias).read_bytes()
            add_bytes_to_tar(tar, f"accounts/{alias}/auth.json", auth_data, 0o600)
            meta_file = account_meta_file(alias)
            if meta_file.exists():
                add_bytes_to_tar(tar, f"accounts/{alias}/meta.json", meta_file.read_bytes(), 0o600)

    safe_chmod(output, 0o600)
    print(f"已匯出 {len(selected_summaries)} 個帳號到：{output}")
    return 0


def cmd_current(args: argparse.Namespace) -> int:
    current = read_current_alias()
    if args.json:
        print_json({"current": current})
        return 0
    if current:
        print(current)
    else:
        print("目前尚未選擇帳號。")
    return 0


def cmd_use(args: argparse.Namespace) -> int:
    alias = validate_alias(args.alias)
    use_account(alias)
    print(f"目前 Codex 帳號：{alias}")
    return 0


def confirm_remove(alias: str) -> bool:
    reply = input(f"確定刪除 {alias} 的本機登入資料？[y/N] ").strip().lower()
    return reply in {"y", "yes"}


def cmd_remove(args: argparse.Namespace) -> int:
    alias = validate_alias(args.alias)
    ensure_layout()
    target_dir = account_dir(alias)
    if not target_dir.exists():
        raise CxError(f"找不到帳號 `{alias}`。")

    if not args.yes and not confirm_remove(alias):
        print("已取消。")
        return 0

    current = read_current_alias()
    with FileLock(LOCK_FILE):
        shutil.rmtree(target_dir)
        if current == alias:
            set_current_alias(None)

    print(f"已刪除帳號：{alias}")
    if current == alias:
        print(f"已清除目前帳號標記；現有 {CODEX_AUTH_FILE} 保留不動。")
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    ensure_layout()
    archive = Path(args.archive).expanduser()
    if not archive.exists():
        raise CxError(f"找不到備份檔：{archive}")
    if args.force and args.skip_existing:
        raise CxError("`--force` 和 `--skip-existing` 不能同時使用。")

    try:
        with tarfile.open(archive, "r:gz") as tar:
            names = set(tar.getnames())
            all_summaries, current_alias = read_backup_manifest(tar)
            alias_selectors = parse_selector_values(getattr(args, "alias_selectors", None), kind="alias")
            email_selectors = parse_selector_values(getattr(args, "email_selectors", None), kind="email")
            selected_summaries, email_matches = select_summaries(
                all_summaries,
                alias_selectors=alias_selectors,
                email_selectors=email_selectors,
            )
            print_email_matches(email_matches, context="匯入時")

            selected_aliases = [summary.alias for summary in selected_summaries]
            conflicts = [alias for alias in selected_aliases if account_dir(alias).exists()]
            if conflicts and not args.force and not args.skip_existing:
                joined = ", ".join(conflicts)
                raise CxError(f"以下帳號已存在：{joined}。請改用 `--force` 或 `--skip-existing`。")

            imported: list[str] = []
            skipped: list[str] = []
            with FileLock(LOCK_FILE):
                for alias in selected_aliases:
                    if account_dir(alias).exists():
                        if args.skip_existing:
                            skipped.append(alias)
                            continue
                        if args.force:
                            shutil.rmtree(account_dir(alias))

                    auth_name = f"accounts/{alias}/auth.json"
                    try:
                        auth_data = read_tar_member(tar, auth_name)
                    except KeyError as exc:
                        raise CxError(f"備份檔缺少 `{auth_name}`。") from exc

                    ensure_dir(account_dir(alias), mode=0o700)
                    write_bytes_atomic(account_auth_file(alias), auth_data)

                    meta_name = f"accounts/{alias}/meta.json"
                    if meta_name in names:
                        meta_data = read_tar_member(tar, meta_name)
                        write_bytes_atomic(account_meta_file(alias), meta_data)
                    else:
                        account_meta_file(alias).unlink(missing_ok=True)
                    imported.append(alias)

                if args.set_current and current_alias and current_alias in imported:
                    set_current_alias(current_alias)
    except tarfile.ReadError as exc:
        raise CxError(f"無法讀取備份檔：{archive}") from exc

    print(f"已從備份匯入 {len(imported)} 個帳號：{', '.join(imported)}")
    if skipped:
        print(f"已略過已存在帳號：{', '.join(skipped)}")
    if args.set_current:
        if current_alias and current_alias in imported:
            print(f"已恢復目前帳號標記：{current_alias}")
        elif current_alias:
            print("備份中的目前帳號未匯入，因此沒有更新 current。")
    return 0


def cmd_backup_list(args: argparse.Namespace) -> int:
    archive = Path(args.archive).expanduser()
    if not archive.exists():
        raise CxError(f"找不到備份檔：{archive}")

    try:
        with tarfile.open(archive, "r:gz") as tar:
            summaries, current_alias = read_backup_manifest(tar)
    except tarfile.ReadError as exc:
        raise CxError(f"無法讀取備份檔：{archive}") from exc

    if args.json:
        print_json(
            {
                "current": current_alias,
                "accounts": [
                    {
                        "alias": summary.alias,
                        "current": summary.alias == current_alias,
                        "email": summary.email,
                        "scope": summary.scope,
                        "plan": summary.plan,
                    }
                    for summary in summaries
                ],
            }
        )
        return 0

    for summary in summaries:
        marker = "*" if summary.alias == current_alias else " "
        email = summary.email or "-"
        plan = summary.plan or "-"
        print(f"{marker} {summary.alias} | {email} | {summary.scope} | {plan}")
    return 0


def use_account(alias: str) -> None:
    ensure_layout()
    src = account_auth_file(alias)
    if not src.exists():
        raise CxError(f"找不到帳號 `{alias}` 的憑證。")
    if CODEX_AUTH_FILE.exists():
        mode = CODEX_AUTH_FILE.stat().st_mode & 0o777
        if mode != 0o600:
            safe_chmod(CODEX_AUTH_FILE, 0o600)
    with FileLock(LOCK_FILE):
        atomic_copy(src, CODEX_AUTH_FILE)
        set_current_alias(alias)


def format_reset(ts: int | None) -> str | None:
    if ts is None:
        return None
    return dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


def app_server_http_error_summary(message: str) -> str | None:
    body_match = re.search(r"body=(\{.*\})\s*$", message, re.DOTALL)
    if body_match is None:
        return None
    try:
        body = json.loads(body_match.group(1))
    except json.JSONDecodeError:
        return None
    if not isinstance(body, dict):
        return None

    error = body.get("error")
    status = body.get("status")
    if not isinstance(error, dict):
        return None

    error_message = error.get("message")
    error_code = error.get("code")
    if (
        status == 401
        and error_code == "token_revoked"
        and isinstance(error_message, str)
        and "invalidated oauth token" in error_message.lower()
    ):
        return "OAuth token revoked or expired (HTTP 401, token_revoked); re-login this account"

    parts: list[str] = []
    if status is not None:
        parts.append(f"HTTP {status}")
    if isinstance(error_code, str) and error_code:
        parts.append(error_code)
    if isinstance(error_message, str) and error_message:
        parts.append(error_message)
    return ": ".join(parts) if parts else None


def json_rpc_error_message(error: Any) -> str:
    if isinstance(error, dict):
        message = error.get("message")
        code = error.get("code")
        if isinstance(message, str) and message:
            summary = app_server_http_error_summary(message)
            if summary is not None:
                if code is not None:
                    return f"{summary} (JSON-RPC code {code})"
                return summary
            if code is not None:
                return f"{message} (code {code})"
            return message
        if code is not None:
            return f"JSON-RPC error code {code}"
    if isinstance(error, str) and error:
        return error
    return "unknown JSON-RPC error"


def request_app_server(auth_file: Path, timeout_sec: float = 15.0) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    temp_home = make_temp_codex_home("cx-status-")
    try:
        atomic_copy(auth_file, temp_home / "auth.json")
        env = os.environ.copy()
        env["CODEX_HOME"] = str(temp_home)
        codex = codex_command(["app-server"])
        proc = subprocess.Popen(
            codex,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=env,
        )

        stdout_queue: Queue[str] = Queue()
        stderr_queue: Queue[str] = Queue()

        def read_stream(stream, queue: Queue[str]) -> None:
            for line in stream:
                queue.put(line)

        threads = [
            threading.Thread(target=read_stream, args=(proc.stdout, stdout_queue), daemon=True),
            threading.Thread(target=read_stream, args=(proc.stderr, stderr_queue), daemon=True),
        ]
        for thread in threads:
            thread.start()

        messages = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": 2, "clientInfo": {"name": APP_NAME, "version": "0.1"}}},
            {"jsonrpc": "2.0", "method": "initialized", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "account/read", "params": {}},
            {"jsonrpc": "2.0", "id": 3, "method": "account/rateLimits/read", "params": {}},
        ]
        assert proc.stdin is not None
        for message in messages:
            proc.stdin.write(json.dumps(message) + "\n")
            proc.stdin.flush()

        account_result = None
        rate_result = None
        deadline = time.time() + timeout_sec
        while time.time() < deadline and (account_result is None or rate_result is None):
            try:
                line = stdout_queue.get(timeout=0.2)
            except Empty:
                if proc.poll() is not None:
                    break
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            response_id = payload.get("id")
            if response_id in APP_SERVER_METHODS and "error" in payload:
                method = APP_SERVER_METHODS[response_id]
                raise CxError(f"{method}: {json_rpc_error_message(payload.get('error'))}")
            if response_id == 2:
                account_result = payload.get("result")
            elif response_id == 3:
                rate_result = payload.get("result")

        if account_result is None or rate_result is None:
            stderr_texts: list[str] = []
            while True:
                try:
                    stderr_texts.append(stderr_queue.get_nowait().strip())
                except Empty:
                    break
            missing = []
            if account_result is None:
                missing.append("account/read")
            if rate_result is None:
                missing.append("account/rateLimits/read")
            detail = stderr_texts[0] if stderr_texts else f"app-server did not return {', '.join(missing)} in time"
            raise CxError(detail)

        return account_result, rate_result
    finally:
        if "proc" in locals():
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
        shutil.rmtree(temp_home, ignore_errors=True)


def read_status_for_alias(alias: str) -> AccountStatus:
    auth_file = account_auth_file(alias)
    scope = read_account_scope(alias)
    if not auth_file.exists():
        return AccountStatus(alias, scope, None, None, None, None, None, None, None, None, "auth.json 不存在")
    try:
        account_result, rate_result = request_app_server(auth_file)
    except CxError as exc:
        return AccountStatus(alias, scope, None, None, None, None, None, None, None, None, str(exc))

    account = (account_result or {}).get("account") or {}
    rate_limits = (rate_result or {}).get("rateLimits") or {}
    primary = rate_limits.get("primary") or {}
    secondary = rate_limits.get("secondary") or {}
    return AccountStatus(
        alias=alias,
        scope=scope,
        email=account.get("email"),
        plan=account.get("planType") or rate_limits.get("planType"),
        primary_used=primary.get("usedPercent"),
        primary_reset=format_reset(primary.get("resetsAt")),
        primary_reset_at=primary.get("resetsAt"),
        secondary_used=secondary.get("usedPercent"),
        secondary_reset=format_reset(secondary.get("resetsAt")),
        secondary_reset_at=secondary.get("resetsAt"),
    )


def print_status(status: AccountStatus, current_alias: str | None, rank: int | None = None) -> None:
    marker = "*" if status.alias == current_alias else " "
    print(f"{marker} {status.alias}")
    if rank is not None:
        suffix = " (best choice now)" if rank == 1 else ""
        print(f"  Rank: #{rank}{suffix}")
    print(f"  Scope: {status.scope}")
    if status.error:
        print(f"  Status: error ({status.error})")
        return
    if status.email:
        print(f"  Email: {status.email}")
    if status.plan:
        print(f"  Plan: {status.plan}")
    if status.primary_used is not None:
        line = f"  5h: {status.primary_used}% used"
        if status.primary_reset:
            line += f" | reset {status.primary_reset}"
        print(line)
    if status.secondary_used is not None:
        line = f"  7d: {status.secondary_used}% used"
        if status.secondary_reset:
            line += f" | reset {status.secondary_reset}"
        print(line)


def status_to_dict(status: AccountStatus, current_alias: str | None, rank: int | None = None) -> dict[str, Any]:
    return {
        "alias": status.alias,
        "current": status.alias == current_alias,
        "scope": status.scope,
        "email": status.email,
        "plan": status.plan,
        "primary_used": status.primary_used,
        "primary_reset": status.primary_reset,
        "primary_reset_at": status.primary_reset_at,
        "secondary_used": status.secondary_used,
        "secondary_reset": status.secondary_reset,
        "secondary_reset_at": status.secondary_reset_at,
        "rank": rank,
        "error": status.error,
    }


def cmd_status(args: argparse.Namespace) -> int:
    require_codex()
    ensure_layout()
    aliases = [validate_alias(args.alias)] if args.alias else list_aliases()
    if not aliases:
        if args.json:
            print_json({"current": read_current_alias(), "accounts": []})
            return 0
        print("目前沒有已保存的帳號。")
        return 0
    current = read_current_alias()
    statuses = [read_status_for_alias(alias) for alias in aliases]
    if not args.alias:
        now = int(time.time())
        statuses.sort(key=lambda status: status_sort_key(status, now))
    exit_code = 0
    for index, status in enumerate(statuses):
        if status.error:
            exit_code = 1
        rank = index + 1 if not args.alias else None
        if args.json:
            continue
        print_status(status, current, rank=rank)
        if index != len(statuses) - 1:
            print()
    if args.json:
        print_json(
            {
                "current": current,
                "accounts": [
                    status_to_dict(status, current, index + 1 if not args.alias else None)
                    for index, status in enumerate(statuses)
                ],
            }
        )
    return exit_code


def cmd_best(args: argparse.Namespace) -> int:
    require_codex()
    ensure_layout()
    aliases = list_aliases()
    if not aliases:
        print("目前沒有已保存的帳號。")
        return 0

    statuses = [read_status_for_alias(alias) for alias in aliases]
    candidates = [status for status in statuses if not status.error]
    if not candidates:
        raise CxError("所有已保存帳號目前都無法讀取狀態，無法自動切換。")

    now = int(time.time())
    usable_candidates = [status for status in candidates if not account_status_blocked(status)]
    if usable_candidates:
        best = min(usable_candidates, key=lambda status: status_sort_key(status, now))
    elif args.allow_blocked:
        best = min(candidates, key=lambda status: status_sort_key(status, now))
    else:
        soonest = min(candidates, key=lambda status: status_sort_key(status, now))
        print("所有可讀取帳號目前都已 blocked，未切換帳號。")
        print(f"最快恢復帳號：{soonest.alias}")
        if soonest.primary_used is not None:
            line = f"5h: {soonest.primary_used}% used"
            if soonest.primary_reset:
                line += f" | reset {soonest.primary_reset}"
            print(line)
        if soonest.secondary_used is not None:
            line = f"7d: {soonest.secondary_used}% used"
            if soonest.secondary_reset:
                line += f" | reset {soonest.secondary_reset}"
            print(line)
        print("若仍要切換到 blocked 帳號，請使用 `cx best --allow-blocked`。")
        return 1

    use_account(best.alias)
    print(f"已切換到最佳帳號：{best.alias}")
    print(f"Scope: {best.scope}")
    if best.email:
        print(f"Email: {best.email}")
    if best.plan:
        print(f"Plan: {best.plan}")
    if best.primary_used is not None:
        line = f"5h: {best.primary_used}% used"
        if best.primary_reset:
            line += f" | reset {best.primary_reset}"
        print(line)
    if best.secondary_used is not None:
        line = f"7d: {best.secondary_used}% used"
        if best.secondary_reset:
            line += f" | reset {best.secondary_reset}"
        print(line)
    return 0


def cmd_scope(args: argparse.Namespace) -> int:
    alias = validate_alias(args.alias)
    scope = validate_scope(args.scope)
    ensure_layout()
    if not account_dir(alias).exists():
        raise CxError(f"找不到帳號 `{alias}`。")
    with FileLock(LOCK_FILE):
        write_account_scope(alias, scope)
    print(f"已設定帳號 `{alias}` 類型為：{scope}")
    return 0


def build_manual(lang: str, fmt: str) -> str:
    if lang not in MANUAL_LANGUAGES:
        raise CxError(f"Unsupported manual language: {lang}")
    if fmt not in MANUAL_FORMATS:
        raise CxError(f"Unsupported manual format: {fmt}")

    if lang == "en":
        lines = [
            "# cx Manual",
            "",
            "`cx` manages multiple Codex CLI accounts by saving each account as an alias and switching the selected alias into `CODEX_HOME/auth.json`.",
            "",
            "## Common Flows",
            "",
            "1. Save accounts with `cx add` or `cx save`.",
            "2. Mark work and personal accounts with `cx scope`.",
            "3. Use `cx status` to inspect usage and ranking, or `cx best` to switch automatically.",
            "4. Back up and restore accounts with `cx export`, `cx backup-list`, and `cx import`.",
            "",
            "## Command Reference",
            "",
        ]
        for name, usage in MANUAL_COMMANDS:
            lines.extend([f"### `cx {name}`", "", f"- Usage: `{usage}`", ""])
        lines.extend(
            [
                "## AI Usage Guide",
                "",
                "When an AI needs to generate `cx` commands, identify the user's intent, choose the matching subcommand, and only include flags that the request implies.",
                "",
                "### Natural Language to Command Examples",
                "",
                "- Check usage for `company` only.",
                "```bash",
                "cx status company",
                "```",
                "- Back up `company` plus any account with email `me@example.com`.",
                "```bash",
                "cx export --alias company --email me@example.com",
                "```",
                "",
            ]
        )
        return "\n".join(lines).rstrip() + "\n"

    lines = [
        "# cx 操作手冊",
        "",
        "`cx` 可以保存多個 Codex CLI 帳號，並用 alias 快速切換目前要使用的 `auth.json`。",
        "",
        "## 常見流程",
        "",
        "1. 用 `cx add` 或 `cx save` 把帳號收進來。",
        "2. 用 `cx scope` 標記 `work` 或 `personal`，讓排序更符合你的使用情境。",
        "3. 用 `cx status` 看排序與額度，或直接用 `cx best` 自動切換。",
        "4. 用 `cx export`、`cx backup-list`、`cx import` 備份或搬移帳號。",
        "",
        "## 指令參考",
        "",
    ]
    for name, usage in MANUAL_COMMANDS:
        lines.extend([f"### `cx {name}`", "", f"- 用法：`{usage}`", ""])
    lines.extend(
        [
            "## AI 使用指引",
            "",
            "AI 產生 `cx` 指令時，應先判斷使用者想新增、保存、列出、切換、查詢、備份、匯入或刪除帳號，再選擇對應子指令。",
            "",
            "### 自然語言到指令範例",
            "",
            "- 查詢 `company` 的額度狀態。",
            "```bash",
            "cx status company",
            "```",
            "- 備份 `company` 與 email 為 `me@example.com` 的帳號。",
            "```bash",
            "cx export --alias company --email me@example.com",
            "```",
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def cmd_manual(args: argparse.Namespace) -> int:
    print(build_manual(args.lang, args.format), end="")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=APP_NAME,
        description="Manage multiple Codex accounts, backups, and status.",
        epilog=(
            "Examples:\n"
            "  cx list\n"
            "  cx export\n"
            "  cx import ./cx-backup.tar.gz --set-current\n"
            "  cx status\n"
            "  cx best\n"
            "  cx manual\n"
            "  cx scope pomichael personal\n"
            "  cx scope foya_co01 work"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_parser = subparsers.add_parser("add", help="Login and save a new account")
    add_parser.add_argument("alias")
    add_parser.add_argument("--force", action="store_true")
    add_parser.set_defaults(func=cmd_add)

    save_parser = subparsers.add_parser("save", help="Save the current auth as an account")
    save_parser.add_argument("alias")
    save_parser.add_argument("--force", action="store_true")
    save_parser.set_defaults(func=cmd_save)

    list_parser = subparsers.add_parser("list", aliases=["ls"], help="List saved accounts with their current scope")
    list_parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    list_parser.set_defaults(func=cmd_list)

    export_parser = subparsers.add_parser(
        "export",
        help="Export saved accounts to a tar.gz backup",
        description="Export all saved accounts or selected aliases to a tar.gz backup archive.",
        epilog=(
            "Examples:\n"
            "  cx export\n"
            "  cx export michaelpo foya_co01\n"
            "  cx export --output ~/Downloads/cx-backup.tar.gz"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    export_parser.add_argument("aliases", nargs="*", help="Optional saved account aliases to export")
    export_parser.add_argument(
        "--alias",
        dest="alias_selectors",
        action="append",
        help="Select saved aliases by repeated flag or comma-separated values",
    )
    export_parser.add_argument(
        "--email",
        dest="email_selectors",
        action="append",
        help="Select saved accounts by exact email using repeated flag or comma-separated values",
    )
    export_parser.add_argument("-o", "--output", help="Output tar.gz path")
    export_parser.set_defaults(func=cmd_export)

    import_parser = subparsers.add_parser(
        "import",
        help="Import saved accounts from a tar.gz backup",
        description=f"Import saved accounts from a tar.gz backup archive into {DATA_DIR}.",
        epilog=(
            "Examples:\n"
            "  cx import ./cx-backup.tar.gz\n"
            "  cx import ./cx-backup.tar.gz --skip-existing\n"
            "  cx import ./cx-backup.tar.gz --force --set-current"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    import_parser.add_argument("archive", help="Backup archive path")
    import_parser.add_argument(
        "--alias",
        dest="alias_selectors",
        action="append",
        help="Import matching aliases using repeated flag or comma-separated values",
    )
    import_parser.add_argument(
        "--email",
        dest="email_selectors",
        action="append",
        help="Import matching exact emails using repeated flag or comma-separated values",
    )
    import_parser.add_argument("--force", action="store_true", help="Overwrite existing aliases from the backup")
    import_parser.add_argument("--skip-existing", action="store_true", help="Skip aliases that already exist locally")
    import_parser.add_argument("--set-current", action="store_true", help="Restore the backup's current alias marker")
    import_parser.set_defaults(func=cmd_import)

    backup_list_parser = subparsers.add_parser(
        "backup-list",
        help="List accounts stored in a backup archive",
        description="Show aliases and account summaries stored in a tar.gz backup archive.",
        epilog="Example:\n  cx backup-list ./cx-backup.tar.gz",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    backup_list_parser.add_argument("archive", help="Backup archive path")
    backup_list_parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    backup_list_parser.set_defaults(func=cmd_backup_list)

    remove_parser = subparsers.add_parser("remove", aliases=["rm", "delete"], help="Remove a saved account")
    remove_parser.add_argument("alias")
    remove_parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt")
    remove_parser.set_defaults(func=cmd_remove)

    scope_parser = subparsers.add_parser(
        "scope",
        help="Mark an account as work or personal to influence ranking",
        description="Mark a saved account as work or personal. Usable work accounts rank before usable personal accounts.",
        epilog=(
            "Examples:\n"
            "  cx scope pomichael personal\n"
            "  cx scope foya_co01 work"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    scope_parser.add_argument("alias", help="Saved account alias, for example `pomichael`")
    scope_parser.add_argument(
        "scope",
        metavar="work|personal",
        choices=["work", "personal"],
        help="`work` for company accounts, `personal` for your own accounts",
    )
    scope_parser.set_defaults(func=cmd_scope)

    current_parser = subparsers.add_parser("current", aliases=["who"], help="Show current account alias")
    current_parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    current_parser.set_defaults(func=cmd_current)

    use_parser = subparsers.add_parser("use", help="Switch current account")
    use_parser.add_argument("alias")
    use_parser.set_defaults(func=cmd_use)

    status_parser = subparsers.add_parser(
        "status",
        help="Show account usage and ranking for one account or all accounts",
        description="Show account usage and ranking for one saved account or all saved accounts.",
        epilog=(
            "Examples:\n"
            "  cx status\n"
            "  cx status pomichael"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    status_parser.add_argument("alias", nargs="?", help="Optional saved account alias")
    status_parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    status_parser.set_defaults(func=cmd_status)

    best_parser = subparsers.add_parser(
        "best",
        help="Switch to the best-ranked account right now",
        description="Switch to the best-ranked account right now based on availability, scope, current usage, and reset times.",
        epilog="Example:\n  cx best",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    best_parser.add_argument(
        "--allow-blocked",
        action="store_true",
        help="Allow switching to a blocked account when every readable account is blocked",
    )
    best_parser.set_defaults(func=cmd_best)

    manual_parser = subparsers.add_parser(
        "manual",
        help="Print an operations manual for humans and AI agents",
        description="Print a Markdown operations manual for `cx`.",
    )
    manual_parser.add_argument("--lang", choices=list(MANUAL_LANGUAGES), default="zh-TW", help="Manual language")
    manual_parser.add_argument("--format", choices=list(MANUAL_FORMATS), default="markdown", help="Manual output format")
    manual_parser.set_defaults(func=cmd_manual)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except CxError as exc:
        print(f"{APP_NAME}: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print(f"{APP_NAME}: interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
