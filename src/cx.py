#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
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
    status_sort_key,
)

try:
    from cx_account_manager import __version__ as APP_VERSION
except ImportError:
    APP_VERSION = "0.1.0"

if os.name == "nt":
    import msvcrt
else:
    import fcntl


APP_NAME = "cx"
ALIAS_RE = re.compile(r"^[A-Za-z0-9_-]+$")
ACCOUNT_SCOPE_RE = re.compile(r"^(work|personal)$")
STATUS_MAX_WORKERS = 4


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
BACKUP_VERSION = 3
SUPPORTED_BACKUP_VERSIONS = {1, 2, 3}
APP_SERVER_METHODS = {
    2: "account/read",
    3: "account/rateLimits/read",
}
ACCOUNT_READ_METHODS = {
    2: "account/read",
}
MANUAL_FORMATS = ("markdown",)
MANUAL_LANGUAGES = ("zh-TW", "en")
MANUAL_COMMANDS = [
    ("add", "cx add <alias> [--force]"),
    ("save", "cx save <alias> [--force]"),
    ("renew", "cx renew <alias>"),
    ("list", "cx list | cx ls"),
    ("use", "cx use <alias>"),
    ("current", "cx current | cx who"),
    ("scope", "cx scope <alias> <work|personal>"),
    ("status", "cx status [alias]"),
    ("best", "cx best [--allow-blocked]"),
    ("doctor", "cx doctor [--json] [--skip-app-server]"),
    ("export", "cx export [alias...] [--alias ...] [--email ...] [-o PATH]"),
    ("import", "cx import <archive> [--alias ...] [--email ...] [--force|--skip-existing] [--set-current]"),
    ("backup-list", "cx backup-list <archive>"),
    ("sync-check", "cx sync-check --dir PATH [--json]"),
    ("sync-import", "cx sync-import --dir PATH [--apply] [--json]"),
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
    auth_hash: str | None = None


@dataclass
class BackupManifest:
    version: int
    created_at: str | None
    summaries: list[BackupAccountSummary]
    current_alias: str | None


@dataclass
class SyncAction:
    action: str
    email: str | None
    local_alias: str | None
    remote_alias: str | None
    archive: str | None
    reason: str
    target_alias: str | None = None
    target_version: int | None = None


SYNC_ACTION_SKIP_LOCAL_VALID = "skip-local-valid"
SYNC_ACTION_SKIP_LOCAL_VALIDITY_UNKNOWN = "skip-local-validity-unknown"
SYNC_ACTION_SKIP_SAME_AUTH = "skip-same-auth"
SYNC_ACTION_SKIP_CONFLICT = "skip-conflict"
SYNC_ACTION_SKIP_LEGACY_EXISTING = "skip-legacy-existing"
SYNC_ACTION_SKIP_LOCAL_AMBIGUOUS = "skip-local-ambiguous"
SYNC_ACTION_SKIP_MISSING_EMAIL = "skip-missing-email"
SYNC_ACTION_SKIP_INVALID_ARCHIVE = "skip-invalid-archive"
SYNC_ACTION_SKIP_OVERWRITE_DISABLED = "skip-overwrite-disabled"
SYNC_ACTION_WOULD_IMPORT_NEW = "would-import-new"
SYNC_ACTION_WOULD_OVERWRITE = "would-overwrite"
SYNC_ACTION_IMPORTED_NEW = "imported-new"
SYNC_ACTION_OVERWROTE = "overwrote"
SYNC_ACTION_ERROR = "error"


META_UNSET = object()


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


def read_account_meta(alias: str) -> dict[str, Any]:
    meta_file = account_meta_file(alias)
    if not meta_file.exists():
        return {}
    try:
        payload = json.loads(meta_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def write_account_meta(
    alias: str,
    *,
    scope: str | None = None,
    email: str | None | object = META_UNSET,
    plan: str | None | object = META_UNSET,
) -> None:
    payload = read_account_meta(alias)
    if scope is not None:
        payload["scope"] = validate_scope(scope)
    if email is not META_UNSET:
        if isinstance(email, str) and email:
            payload["email"] = email
        else:
            payload.pop("email", None)
    if plan is not META_UNSET:
        if isinstance(plan, str) and plan:
            payload["plan"] = plan
        else:
            payload.pop("plan", None)
    write_text_atomic(account_meta_file(alias), json.dumps(payload, ensure_ascii=True, indent=2) + "\n")


def write_account_sync_meta(
    alias: str,
    *,
    auth_hash: str | None | object = META_UNSET,
    last_sync_source: str | None | object = META_UNSET,
    last_sync_at: str | None | object = META_UNSET,
) -> None:
    payload = read_account_meta(alias)
    for key, value in (
        ("authHash", auth_hash),
        ("lastSyncSource", last_sync_source),
        ("lastSyncAt", last_sync_at),
    ):
        if value is META_UNSET:
            continue
        if isinstance(value, str) and value:
            payload[key] = value
        else:
            payload.pop(key, None)
    write_text_atomic(account_meta_file(alias), json.dumps(payload, ensure_ascii=True, indent=2) + "\n")


def write_account_scope(alias: str, scope: str) -> None:
    write_account_meta(alias, scope=scope)


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


def read_auth_email(auth_file: Path) -> str | None:
    if not auth_file.exists():
        return None
    email, _plan = read_account_summary_from_auth_bytes(auth_file.read_bytes())
    return email


def read_auth_email_from_app_server(auth_file: Path) -> str | None:
    try:
        account_result, _rate_result = request_app_server(auth_file)
    except CxError:
        return None
    account = (account_result or {}).get("account") or {}
    email = account.get("email")
    if isinstance(email, str) and email:
        return email
    return None


def read_auth_email_with_fallback(auth_file: Path) -> str | None:
    email = read_auth_email(auth_file)
    if email is not None:
        return email
    return read_auth_email_from_app_server(auth_file)


def read_auth_identity_with_fallback(auth_file: Path) -> tuple[str | None, str | None]:
    email, plan = read_account_summary_from_auth_bytes(auth_file.read_bytes())
    if email is not None:
        return email, plan
    return read_auth_identity_from_app_server(auth_file)


def read_cached_account_identity(alias: str) -> tuple[str | None, str | None]:
    payload = read_account_meta(alias)
    email = payload.get("email")
    plan = payload.get("plan")
    return (
        email if isinstance(email, str) and email else None,
        plan if isinstance(plan, str) and plan else None,
    )


def read_account_email_with_fallback(alias: str, auth_file: Path) -> str | None:
    email = read_auth_email(auth_file)
    if email is not None:
        return email
    email = read_auth_email_from_app_server(auth_file)
    if email is not None:
        return email
    cached_email, _cached_plan = read_cached_account_identity(alias)
    return cached_email


def cache_account_identity(alias: str, *, email: str | None, plan: str | None) -> None:
    write_account_meta(alias, scope=read_account_scope(alias), email=email, plan=plan)


def cache_account_identity_from_auth(alias: str, auth_file: Path) -> tuple[str | None, str | None]:
    email, plan = read_account_summary_from_auth_bytes(auth_file.read_bytes())
    cache_account_identity(alias, email=email, plan=plan)
    return email, plan


def read_account_auth_hash(alias: str) -> str | None:
    auth_file = account_auth_file(alias)
    if not auth_file.exists():
        return None
    return auth_hash_from_bytes(auth_file.read_bytes())


def refresh_account_auth_hash(alias: str) -> str | None:
    auth_hash = read_account_auth_hash(alias)
    write_account_sync_meta(alias, auth_hash=auth_hash)
    return auth_hash


def read_local_account_summary(alias: str) -> BackupAccountSummary:
    email = None
    plan = None
    auth_file = account_auth_file(alias)
    if auth_file.exists():
        email, plan = read_account_summary_from_auth_bytes(auth_file.read_bytes())
    cached_email, cached_plan = read_cached_account_identity(alias)
    meta = read_account_meta(alias)
    auth_hash = read_account_auth_hash(alias)
    if auth_hash is None and isinstance(meta.get("authHash"), str):
        auth_hash = meta["authHash"]
    if email is None:
        email = cached_email
    if plan is None:
        plan = cached_plan
    return BackupAccountSummary(
        alias=alias,
        email=email,
        scope=read_account_scope(alias),
        plan=plan,
        auth_hash=auth_hash,
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
            cache_account_identity_from_auth(alias, target_auth)
            refresh_account_auth_hash(alias)
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
        cache_account_identity_from_auth(alias, target_auth)
        refresh_account_auth_hash(alias)

    print(f"已從目前登入狀態保存帳號：{alias}")
    return 0


def cmd_renew(args: argparse.Namespace) -> int:
    alias = validate_alias(args.alias)
    ensure_layout()

    target_dir = account_dir(alias)
    target_auth = account_auth_file(alias)
    if not target_dir.exists():
        raise CxError(f"找不到帳號 `{alias}`；renew 只支援已存在的 alias。")
    if not target_auth.exists():
        raise CxError(f"找不到帳號 `{alias}` 的既有 auth.json，無法 renew。")

    old_email = read_account_email_with_fallback(alias, target_auth)
    if not old_email:
        raise CxError(f"帳號 `{alias}` 的既有 auth.json 無法識別 email，為避免覆寫錯帳號，已取消 renew。")

    codex = codex_command(["login", "--device-auth"])
    temp_home = make_temp_codex_home("cx-renew-")
    renewed_current = False
    try:
        print(f"請在瀏覽器中重新登入 `{alias}` 對應的帳號。", file=sys.stderr)
        env = os.environ.copy()
        env["CODEX_HOME"] = str(temp_home)
        result = run_command(codex, env=env)
        if result.returncode != 0:
            raise CxError(f"`codex login --device-auth` 失敗，退出碼 {result.returncode}")

        temp_auth = temp_home / "auth.json"
        if not temp_auth.exists():
            raise CxError("登入完成後沒有找到 auth.json，無法 renew 帳號。")

        new_email, new_plan = read_auth_identity_with_fallback(temp_auth)
        if not new_email:
            raise CxError("新的登入結果無法識別 email，為避免覆寫錯帳號，已取消 renew。")
        if old_email != new_email:
            raise CxError(
                "登入帳號不一致，已取消 renew。\n"
                f"Alias: {alias}\n"
                f"Expected: {old_email}\n"
                f"Actual: {new_email}"
            )

        with FileLock(LOCK_FILE):
            if not target_auth.exists():
                raise CxError(f"找不到帳號 `{alias}` 的既有 auth.json，無法 renew。")
            latest_email = read_account_email_with_fallback(alias, target_auth)
            if not latest_email:
                raise CxError(f"帳號 `{alias}` 的既有 auth.json 無法識別 email，為避免覆寫錯帳號，已取消 renew。")
            if latest_email != old_email:
                raise CxError(
                    "renew 期間既有帳號資料已變更，已取消覆寫。\n"
                    f"Alias: {alias}\n"
                    f"Original: {old_email}\n"
                    f"Current: {latest_email}"
                )
            current = read_current_alias()
            _cached_email, cached_plan = read_cached_account_identity(alias)
            atomic_copy(temp_auth, target_auth)
            parsed_email, parsed_plan = read_account_summary_from_auth_bytes(target_auth.read_bytes())
            cache_account_identity(
                alias,
                email=new_email if parsed_email is None else parsed_email,
                plan=parsed_plan or new_plan or cached_plan,
            )
            refresh_account_auth_hash(alias)
            if current == alias:
                atomic_copy(temp_auth, CODEX_AUTH_FILE)
                renewed_current = True
    finally:
        shutil.rmtree(temp_home, ignore_errors=True)

    print(f"已更新帳號 token：{alias}")
    print(f"Email: {old_email}")
    if renewed_current:
        print("已同步更新目前 Codex 帳號。")
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


def now_iso_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def parse_iso_utc(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def auth_hash_from_bytes(auth_data: bytes) -> str:
    return "sha256:" + hashlib.sha256(auth_data).hexdigest()


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
    auth_hash = raw.get("authHash")
    if email is not None and not isinstance(email, str):
        raise CxError(f"備份檔中的 `{alias}` email 欄位格式不合法。")
    if plan is not None and not isinstance(plan, str):
        raise CxError(f"備份檔中的 `{alias}` plan 欄位格式不合法。")
    if auth_hash is not None and not isinstance(auth_hash, str):
        raise CxError(f"備份檔中的 `{alias}` authHash 欄位格式不合法。")
    return BackupAccountSummary(
        alias=validate_alias(alias),
        email=email,
        scope=validate_scope(scope),
        plan=plan,
        auth_hash=auth_hash,
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
    return BackupAccountSummary(alias=alias, email=email, scope=scope, plan=plan, auth_hash=auth_hash_from_bytes(auth_data))


def read_backup_bundle(tar: tarfile.TarFile) -> BackupManifest:
    names = set(tar.getnames())
    if "manifest.json" not in names:
        raise CxError("備份檔缺少 manifest.json。")
    try:
        manifest = json.loads(read_tar_member(tar, "manifest.json").decode("utf-8"))
    except (KeyError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise CxError("備份檔中的 manifest.json 無法解析。") from exc

    version = manifest.get("version")
    if version not in SUPPORTED_BACKUP_VERSIONS:
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
    if version >= 2 and isinstance(manifest.get("accounts"), list):
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

    created_at = manifest.get("createdAt")
    if created_at is not None and not isinstance(created_at, str):
        raise CxError("備份檔中的 createdAt 欄位格式不合法。")
    return BackupManifest(version=version, created_at=created_at, summaries=summaries, current_alias=current_alias)


def read_backup_manifest(
    tar: tarfile.TarFile,
) -> tuple[list[BackupAccountSummary], str | None]:
    bundle = read_backup_bundle(tar)
    return bundle.summaries, bundle.current_alias


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


def parse_sync_directory(path_value: str) -> Path:
    directory = Path(path_value).expanduser()
    if not directory.exists():
        raise CxError(f"找不到同步目錄：{directory}")
    if not directory.is_dir():
        raise CxError(f"同步目錄不是資料夾：{directory}")
    return directory


def sync_option_enabled(args: argparse.Namespace, name: str, default: bool = True) -> bool:
    value = getattr(args, name, None)
    if value is None:
        return default
    return bool(value)


def list_backup_archives(directory: Path) -> list[Path]:
    return sorted(path for path in directory.glob("*.tar.gz") if path.is_file())


def local_accounts_by_email() -> dict[str, list[str]]:
    matches: dict[str, list[str]] = {}
    for alias in list_aliases():
        summary = read_local_account_summary(alias)
        if not summary.email:
            continue
        matches.setdefault(summary.email, []).append(alias)
    return matches


def local_account_validity(alias: str) -> tuple[str, str]:
    auth_file = account_auth_file(alias)
    if not auth_file.exists():
        return "invalid", "local auth.json is missing"
    status = read_status_for_alias(alias)
    if status.error is None:
        return "valid", "local account is still valid"
    error_text = status.error.lower()
    invalid_markers = (
        "token_revoked",
        "invalidated oauth token",
        "oauth token revoked or expired",
        "401",
        "auth.json 不存在",
        "missing auth",
    )
    if any(marker in error_text for marker in invalid_markers):
        return "invalid", status.error
    return "unknown", status.error


def choose_remote_alias(base_alias: str) -> str:
    candidate = base_alias
    suffix = 1
    while account_dir(candidate).exists():
        suffix += 1
        candidate = f"{base_alias}-sync" if suffix == 2 else f"{base_alias}-sync-{suffix - 1}"
    return candidate


def bundle_archive_summary(path: Path, bundle: BackupManifest, summary: BackupAccountSummary) -> dict[str, Any]:
    return {
        "archive_path": path,
        "archive_name": path.name,
        "version": bundle.version,
        "created_at": bundle.created_at,
        "created_at_parsed": parse_iso_utc(bundle.created_at),
        "summary": summary,
    }


def inspect_sync_directory(directory: Path) -> tuple[list[dict[str, Any]], list[str]]:
    candidates: list[dict[str, Any]] = []
    warnings: list[str] = []
    for archive in list_backup_archives(directory):
        try:
            with tarfile.open(archive, "r:gz") as tar:
                bundle = read_backup_bundle(tar)
                for summary in bundle.summaries:
                    candidates.append(bundle_archive_summary(archive, bundle, summary))
        except (CxError, tarfile.TarError) as exc:
            warnings.append(f"{archive.name}: {exc}")
    return candidates, warnings


def select_remote_candidates(candidates: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], list[SyncAction]]:
    selected: dict[str, dict[str, Any]] = {}
    actions: list[SyncAction] = []
    grouped: dict[str, list[dict[str, Any]]] = {}
    for candidate in candidates:
        summary = candidate["summary"]
        if not isinstance(summary, BackupAccountSummary):
            continue
        if not summary.email:
            actions.append(
                SyncAction(
                    action=SYNC_ACTION_SKIP_MISSING_EMAIL,
                    email=None,
                    local_alias=None,
                    remote_alias=summary.alias,
                    archive=candidate["archive_name"],
                    reason="remote account is missing email",
                )
            )
            continue
        grouped.setdefault(summary.email, []).append(candidate)

    for email, items in grouped.items():
        v3_items = [item for item in items if item["version"] == 3 and item["created_at_parsed"] is not None]
        if v3_items:
            v3_items.sort(key=lambda item: item["created_at_parsed"], reverse=True)
            if len(v3_items) > 1 and v3_items[0]["created_at_parsed"] == v3_items[1]["created_at_parsed"]:
                actions.append(
                    SyncAction(
                        action=SYNC_ACTION_SKIP_CONFLICT,
                        email=email,
                        local_alias=None,
                        remote_alias=None,
                        archive=None,
                        reason="multiple remote v3 backups share the same createdAt",
                    )
                )
                continue
            selected[email] = v3_items[0]
            continue
        if len(items) == 1:
            selected[email] = items[0]
        else:
            actions.append(
                SyncAction(
                    action=SYNC_ACTION_SKIP_CONFLICT,
                    email=email,
                    local_alias=None,
                    remote_alias=None,
                    archive=None,
                    reason="multiple remote backups could not be safely ordered",
                )
            )
    return selected, actions


def sync_action_to_dict(action: SyncAction) -> dict[str, Any]:
    return {
        "action": action.action,
        "email": action.email,
        "localAlias": action.local_alias,
        "remoteAlias": action.remote_alias,
        "archive": action.archive,
        "reason": action.reason,
        "targetAlias": action.target_alias,
        "targetVersion": action.target_version,
    }


def build_sync_plan(args: argparse.Namespace) -> tuple[list[SyncAction], list[str]]:
    ensure_layout()
    directory = parse_sync_directory(args.dir)
    candidates, warnings = inspect_sync_directory(directory)
    remote_by_email, pre_actions = select_remote_candidates(candidates)
    local_by_email = local_accounts_by_email()
    actions: list[SyncAction] = list(pre_actions)
    import_new = sync_option_enabled(args, "import_new_accounts", True)
    overwrite_existing = sync_option_enabled(args, "overwrite_existing_accounts", True)
    allow_legacy_overwrite = sync_option_enabled(args, "allow_legacy_overwrite", False)

    for email, remote in sorted(remote_by_email.items()):
        summary = remote["summary"]
        archive_name = remote["archive_name"]
        version = remote["version"]
        locals_for_email = local_by_email.get(email, [])
        if not locals_for_email:
            if import_new:
                actions.append(
                    SyncAction(
                        action=SYNC_ACTION_WOULD_IMPORT_NEW,
                        email=email,
                        local_alias=None,
                        remote_alias=summary.alias,
                        archive=archive_name,
                        reason="local account does not exist",
                        target_alias=choose_remote_alias(summary.alias),
                        target_version=version,
                    )
                )
            else:
                actions.append(
                    SyncAction(
                        action=SYNC_ACTION_SKIP_CONFLICT,
                        email=email,
                        local_alias=None,
                        remote_alias=summary.alias,
                        archive=archive_name,
                        reason="import new accounts is disabled",
                        target_version=version,
                    )
                )
            continue
        if len(locals_for_email) > 1:
            actions.append(
                SyncAction(
                    action=SYNC_ACTION_SKIP_LOCAL_AMBIGUOUS,
                    email=email,
                    local_alias=None,
                    remote_alias=summary.alias,
                    archive=archive_name,
                    reason="multiple local aliases share the same email",
                    target_version=version,
                )
            )
            continue

        local_alias = locals_for_email[0]
        validity, validity_reason = local_account_validity(local_alias)
        if validity == "valid":
            actions.append(
                SyncAction(
                    action=SYNC_ACTION_SKIP_LOCAL_VALID,
                    email=email,
                    local_alias=local_alias,
                    remote_alias=summary.alias,
                    archive=archive_name,
                    reason=validity_reason,
                    target_version=version,
                )
            )
            continue
        if validity == "unknown":
            actions.append(
                SyncAction(
                    action=SYNC_ACTION_SKIP_LOCAL_VALIDITY_UNKNOWN,
                    email=email,
                    local_alias=local_alias,
                    remote_alias=summary.alias,
                    archive=archive_name,
                    reason=validity_reason,
                    target_version=version,
                )
            )
            continue
        if version < 3:
            if allow_legacy_overwrite:
                actions.append(
                    SyncAction(
                        action=SYNC_ACTION_WOULD_OVERWRITE,
                        email=email,
                        local_alias=local_alias,
                        remote_alias=summary.alias,
                        archive=archive_name,
                        reason="local account is invalid and legacy overwrite is enabled",
                        target_alias=local_alias,
                        target_version=version,
                    )
                )
            else:
                actions.append(
                    SyncAction(
                        action=SYNC_ACTION_SKIP_LEGACY_EXISTING,
                        email=email,
                        local_alias=local_alias,
                        remote_alias=summary.alias,
                        archive=archive_name,
                        reason="legacy overwrite is disabled",
                        target_version=version,
                    )
                )
            continue
        if not overwrite_existing:
            actions.append(
                SyncAction(
                    action=SYNC_ACTION_SKIP_OVERWRITE_DISABLED,
                    email=email,
                    local_alias=local_alias,
                    remote_alias=summary.alias,
                    archive=archive_name,
                    reason="overwrite existing accounts is disabled",
                    target_version=version,
                )
            )
            continue
        local_auth_hash = read_account_auth_hash(local_alias)
        if summary.auth_hash and local_auth_hash == summary.auth_hash:
            actions.append(
                SyncAction(
                    action=SYNC_ACTION_SKIP_SAME_AUTH,
                    email=email,
                    local_alias=local_alias,
                    remote_alias=summary.alias,
                    archive=archive_name,
                    reason="remote authHash matches local authHash",
                    target_version=version,
                )
            )
            continue
        if not summary.auth_hash:
            actions.append(
                SyncAction(
                    action=SYNC_ACTION_SKIP_CONFLICT,
                    email=email,
                    local_alias=local_alias,
                    remote_alias=summary.alias,
                    archive=archive_name,
                    reason="remote v3 backup is missing authHash",
                    target_version=version,
                )
            )
            continue
        actions.append(
            SyncAction(
                action=SYNC_ACTION_WOULD_OVERWRITE,
                email=email,
                local_alias=local_alias,
                remote_alias=summary.alias,
                archive=archive_name,
                reason="local account is invalid and remote authHash differs",
                target_alias=local_alias,
                target_version=version,
            )
        )
    return actions, warnings


def print_sync_actions(actions: list[SyncAction]) -> None:
    for action in actions:
        parts = [action.action]
        if action.email:
            parts.append(action.email)
        if action.local_alias:
            parts.append(f"local={action.local_alias}")
        if action.remote_alias:
            parts.append(f"remote={action.remote_alias}")
        if action.archive:
            parts.append(f"archive={action.archive}")
        print(" | ".join(parts))
        print(f"  reason: {action.reason}")


def rollback_directory() -> Path:
    path = DATA_DIR / "rollback"
    ensure_dir(path, mode=0o700)
    return path


def create_rollback_backup(alias: str, email: str | None) -> Path:
    safe_email = re.sub(r"[^A-Za-z0-9._-]+", "_", email or alias)
    timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    output = rollback_directory() / f"cx-rollback-{timestamp}-{safe_email}.tar.gz"
    summary = read_local_account_summary(alias)
    manifest = {
        "version": BACKUP_VERSION,
        "createdAt": now_iso_utc(),
        "aliases": [alias],
        "accounts": [
            {
                "alias": summary.alias,
                "email": summary.email,
                "scope": summary.scope,
                "plan": summary.plan,
                "authHash": auth_hash_from_bytes(account_auth_file(alias).read_bytes()),
            }
        ],
        "current": read_current_alias() if read_current_alias() == alias else None,
    }
    with tarfile.open(output, "w:gz") as tar:
        add_bytes_to_tar(tar, "manifest.json", json.dumps(manifest, ensure_ascii=True, indent=2).encode("utf-8") + b"\n", 0o600)
        add_bytes_to_tar(tar, f"accounts/{alias}/auth.json", account_auth_file(alias).read_bytes(), 0o600)
        if account_meta_file(alias).exists():
            add_bytes_to_tar(tar, f"accounts/{alias}/meta.json", account_meta_file(alias).read_bytes(), 0o600)
    safe_chmod(output, 0o600)
    return output


def apply_sync_action(action: SyncAction, directory: Path, rollback_before_overwrite: bool) -> SyncAction:
    archive_path = directory / action.archive if action.archive else None
    if archive_path is None:
        raise CxError("sync action 缺少 archive。")
    try:
        with tarfile.open(archive_path, "r:gz") as tar:
            bundle = read_backup_bundle(tar)
            summary_by_alias = {summary.alias: summary for summary in bundle.summaries}
            if action.remote_alias not in summary_by_alias:
                raise CxError(f"找不到 remote alias：{action.remote_alias}")
            remote_summary = summary_by_alias[action.remote_alias]
            auth_data = read_tar_member(tar, f"accounts/{action.remote_alias}/auth.json")
            target_alias = action.target_alias or action.local_alias or action.remote_alias
            assert target_alias is not None
            if action.action == SYNC_ACTION_WOULD_IMPORT_NEW:
                if account_dir(target_alias).exists():
                    raise CxError(f"target alias already exists: {target_alias}")
                ensure_dir(account_dir(target_alias), mode=0o700)
                write_bytes_atomic(account_auth_file(target_alias), auth_data)
                write_account_meta(target_alias, scope=remote_summary.scope, email=remote_summary.email if remote_summary.email is not None else META_UNSET, plan=remote_summary.plan if remote_summary.plan is not None else META_UNSET)
                refresh_account_auth_hash(target_alias)
                write_account_sync_meta(target_alias, last_sync_source=str(archive_path), last_sync_at=now_iso_utc())
                return SyncAction(SYNC_ACTION_IMPORTED_NEW, action.email, None, action.remote_alias, action.archive, "imported new account", target_alias=target_alias, target_version=action.target_version)
            if action.action == SYNC_ACTION_WOULD_OVERWRITE:
                if action.local_alias is None:
                    raise CxError("overwrite action 缺少 local alias。")
                if rollback_before_overwrite:
                    create_rollback_backup(action.local_alias, action.email)
                write_bytes_atomic(account_auth_file(action.local_alias), auth_data)
                write_account_meta(action.local_alias, scope=read_account_scope(action.local_alias), email=remote_summary.email if remote_summary.email is not None else META_UNSET, plan=remote_summary.plan if remote_summary.plan is not None else META_UNSET)
                refresh_account_auth_hash(action.local_alias)
                write_account_sync_meta(action.local_alias, last_sync_source=str(archive_path), last_sync_at=now_iso_utc())
                return SyncAction(SYNC_ACTION_OVERWROTE, action.email, action.local_alias, action.remote_alias, action.archive, "overwrote invalid local account", target_alias=action.local_alias, target_version=action.target_version)
    except tarfile.TarError as exc:
        raise CxError(f"無法讀取備份檔：{archive_path}") from exc
    raise CxError(f"不支援的 sync action：{action.action}")


def cmd_sync_check(args: argparse.Namespace) -> int:
    actions, warnings = build_sync_plan(args)
    if args.json:
        print_json(
            {
                "directory": str(Path(args.dir).expanduser()),
                "actions": [sync_action_to_dict(action) for action in actions],
                "warnings": warnings,
            }
        )
    else:
        print_sync_actions(actions)
        for warning in warnings:
            print(f"warning: {warning}")
    return 0


def cmd_sync_import(args: argparse.Namespace) -> int:
    if not args.apply:
        return cmd_sync_check(args)
    directory = parse_sync_directory(args.dir)
    results: list[SyncAction] = []
    rollback_before_overwrite = sync_option_enabled(args, "rollback_before_overwrite", True)
    exit_code = 0
    warnings: list[str] = []
    with FileLock(LOCK_FILE):
        actions, warnings = build_sync_plan(args)
        for action in actions:
            if action.action not in {SYNC_ACTION_WOULD_IMPORT_NEW, SYNC_ACTION_WOULD_OVERWRITE}:
                results.append(action)
                continue
            try:
                results.append(apply_sync_action(action, directory, rollback_before_overwrite))
            except CxError as exc:
                exit_code = 1
                results.append(
                    SyncAction(
                        action=SYNC_ACTION_ERROR,
                        email=action.email,
                        local_alias=action.local_alias,
                        remote_alias=action.remote_alias,
                        archive=action.archive,
                        reason=str(exc),
                        target_alias=action.target_alias,
                        target_version=action.target_version,
                    )
                )
    if args.json:
        print_json(
            {
                "directory": str(directory),
                "actions": [sync_action_to_dict(action) for action in results],
                "warnings": warnings,
            }
        )
    else:
        print_sync_actions(results)
        for warning in warnings:
            print(f"warning: {warning}")
    return exit_code


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
        "createdAt": now_iso_utc(),
        "aliases": [summary.alias for summary in selected_summaries],
        "accounts": [
            {
                "alias": summary.alias,
                "email": summary.email,
                "scope": summary.scope,
                "plan": summary.plan,
                "authHash": auth_hash_from_bytes(account_auth_file(summary.alias).read_bytes()),
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
            selected_summary_by_alias = {summary.alias: summary for summary in selected_summaries}

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
                        else:
                            raise CxError(f"account already exists: {alias}; use --force or --skip-existing")

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
                    summary = selected_summary_by_alias[alias]
                    write_account_meta(
                        alias,
                        scope=summary.scope,
                        email=summary.email if summary.email is not None else META_UNSET,
                        plan=summary.plan if summary.plan is not None else META_UNSET,
                    )
                    write_account_sync_meta(alias, auth_hash=auth_hash_from_bytes(auth_data))
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


def request_account_read(auth_file: Path, timeout_sec: float = 15.0) -> dict[str, Any] | None:
    temp_home = make_temp_codex_home("cx-account-")
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
        ]
        assert proc.stdin is not None
        for message in messages:
            proc.stdin.write(json.dumps(message) + "\n")
            proc.stdin.flush()

        account_result = None
        deadline = time.time() + timeout_sec
        while time.time() < deadline and account_result is None:
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
            if response_id in ACCOUNT_READ_METHODS and "error" in payload:
                method = ACCOUNT_READ_METHODS[response_id]
                raise CxError(f"{method}: {json_rpc_error_message(payload.get('error'))}")
            if response_id == 2:
                account_result = payload.get("result")

        if account_result is None:
            stderr_texts: list[str] = []
            while True:
                try:
                    stderr_texts.append(stderr_queue.get_nowait().strip())
                except Empty:
                    break
            detail = stderr_texts[0] if stderr_texts else "app-server did not return account/read in time"
            raise CxError(detail)

        return account_result
    finally:
        if "proc" in locals():
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
        shutil.rmtree(temp_home, ignore_errors=True)


def read_auth_identity_from_app_server(auth_file: Path) -> tuple[str | None, str | None]:
    try:
        account_result = request_account_read(auth_file)
    except CxError:
        return None, None
    account = (account_result or {}).get("account") or {}
    email = account.get("email")
    plan = account.get("planType")
    return (
        email if isinstance(email, str) and email else None,
        plan if isinstance(plan, str) and plan else None,
    )


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


def path_exists(path: Path) -> bool:
    try:
        return path.exists()
    except OSError:
        return False


def path_readable(path: Path) -> bool | None:
    try:
        if not path.exists():
            return None
        return os.access(path, os.R_OK)
    except OSError:
        return False


def path_writable(path: Path) -> bool | None:
    try:
        if not path.exists():
            return None
        return os.access(path, os.W_OK)
    except OSError:
        return False


def auth_json_status(auth_file: Path) -> dict[str, Any]:
    status: dict[str, Any] = {
        "exists": False,
        "size": None,
        "parse_ok": None,
        "error": None,
    }
    try:
        if not auth_file.exists():
            return status
        status["exists"] = True
        status["size"] = auth_file.stat().st_size
        try:
            json.loads(auth_file.read_text(encoding="utf-8"))
            status["parse_ok"] = True
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            status["parse_ok"] = False
            status["error"] = str(exc)
    except OSError as exc:
        status["error"] = str(exc)
    return status


def run_external_for_doctor(cmd: list[str], timeout_sec: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout_sec,
        check=False,
    )


def codex_version_for_doctor(executable: str) -> tuple[str | None, str | None]:
    cmd = [executable, "--version"]
    if os.name == "nt" and os.path.splitext(executable)[1].lower() in {".bat", ".cmd"}:
        cmd = [os.environ.get("COMSPEC", "cmd.exe"), "/c", executable, "--version"]
    try:
        result = run_external_for_doctor(cmd, timeout_sec=5)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, str(exc)
    output = (result.stdout or result.stderr).strip()
    if result.returncode != 0:
        return None, output or f"codex --version exited with {result.returncode}"
    return output.splitlines()[0].strip() if output else None, None


def wsl_info_for_doctor() -> dict[str, Any]:
    info: dict[str, Any] = {
        "checked": False,
        "available": False,
        "distro_count": 0,
        "is_wsl": is_wsl(),
        "error": None,
    }
    if os.name != "nt":
        info["checked"] = True
        info["available"] = info["is_wsl"]
        return info

    wsl_executable = shutil.which("wsl.exe") or shutil.which("wsl")
    info["checked"] = True
    if wsl_executable is None:
        return info
    info["available"] = True
    try:
        result = run_external_for_doctor([wsl_executable, "--list", "--quiet"], timeout_sec=5)
    except (OSError, subprocess.TimeoutExpired) as exc:
        info["error"] = str(exc)
        return info
    if result.returncode != 0:
        info["error"] = (result.stderr or result.stdout).strip() or f"wsl.exe exited with {result.returncode}"
        return info
    normalized = result.stdout.replace("\x00", "")
    info["distro_count"] = len([line for line in normalized.splitlines() if line.strip()])
    return info


def build_doctor_report(skip_app_server: bool = False) -> dict[str, Any]:
    warnings: list[str] = []
    errors: list[str] = []

    try:
        aliases = list_aliases()
    except OSError as exc:
        aliases = []
        errors.append(f"accounts directory cannot be read: {exc}")

    current_alias = None
    try:
        current_alias = read_current_alias()
    except OSError as exc:
        warnings.append(f"current alias cannot be read: {exc}")

    if not aliases:
        warnings.append("no saved accounts")
    if current_alias and current_alias not in aliases:
        warnings.append("current alias points to a missing saved account")

    auth_status = auth_json_status(CODEX_AUTH_FILE)
    if not auth_status["exists"]:
        warnings.append("CODEX_HOME/auth.json is missing")
    elif auth_status["size"] == 0:
        warnings.append("CODEX_HOME/auth.json is empty")
    elif auth_status["parse_ok"] is False:
        warnings.append("CODEX_HOME/auth.json is not valid JSON")

    data_dir_exists = path_exists(DATA_DIR)
    accounts_dir_exists = path_exists(ACCOUNTS_DIR)
    temp_dir_exists = path_exists(TEMP_DIR)
    data_dir_readable = path_readable(DATA_DIR)
    accounts_dir_readable = path_readable(ACCOUNTS_DIR)
    data_dir_writable = path_writable(DATA_DIR)
    if data_dir_exists and data_dir_readable is False:
        errors.append("cx data dir is not readable")
    if accounts_dir_exists and accounts_dir_readable is False:
        errors.append("cx accounts dir is not readable")
    if data_dir_exists and data_dir_writable is False:
        errors.append("cx data dir is not writable")

    codex_bin = os.environ.get("CX_CODEX_BIN")
    codex_path = find_codex_executable()
    codex_version = None
    codex_version_error = None
    if codex_path is None:
        errors.append("codex executable was not found")
    else:
        codex_version, codex_version_error = codex_version_for_doctor(codex_path)
        if codex_version_error is not None:
            warnings.append("codex --version failed")

    app_server: dict[str, Any] = {"checked": False, "ok": None, "error": None}
    if skip_app_server:
        app_server["error"] = "skipped"
    elif not auth_status["exists"]:
        app_server["error"] = "skipped because auth.json is missing"
    elif codex_path is None:
        app_server["error"] = "skipped because codex executable was not found"
    else:
        app_server["checked"] = True
        try:
            request_app_server(CODEX_AUTH_FILE, timeout_sec=10)
            app_server["ok"] = True
        except CxError as exc:
            app_server["ok"] = False
            app_server["error"] = str(exc)
            errors.append("codex app-server check failed")

    wsl = wsl_info_for_doctor()
    if wsl.get("error"):
        warnings.append("WSL detection failed")

    report = {
        "ok": not errors,
        "warnings": warnings,
        "errors": errors,
        "system": {
            "os": platform.system() or os.name,
            "platform": platform.platform(),
            "python_version": platform.python_version(),
            "python_executable": sys.executable,
            "cwd": str(Path.cwd()),
            "cx_script": str(Path(__file__).resolve()),
            "is_wsl": is_wsl(),
        },
        "paths": {
            "data_dir": str(DATA_DIR),
            "data_dir_exists": data_dir_exists,
            "data_dir_readable": data_dir_readable,
            "data_dir_writable": data_dir_writable,
            "accounts_dir": str(ACCOUNTS_DIR),
            "accounts_dir_exists": accounts_dir_exists,
            "accounts_dir_readable": accounts_dir_readable,
            "temp_dir": str(TEMP_DIR),
            "temp_dir_exists": temp_dir_exists,
            "codex_home": str(CODEX_HOME),
            "auth_json": str(CODEX_AUTH_FILE),
            "auth_json_exists": auth_status["exists"],
            "auth_json_size": auth_status["size"],
            "auth_json_parse_ok": auth_status["parse_ok"],
        },
        "accounts": {
            "count": len(aliases),
            "current_alias_set": current_alias is not None,
            "current_alias_saved": current_alias in aliases if current_alias is not None else None,
        },
        "codex": {
            "cx_codex_bin": codex_bin,
            "executable": codex_path,
            "version": codex_version,
            "version_error": codex_version_error,
            "app_server": app_server,
        },
        "wsl": wsl,
    }
    return report


def bool_status(value: bool | None) -> str:
    if value is None:
        return "n/a"
    return "yes" if value else "no"


def app_server_status_text(app_server: dict[str, Any]) -> str:
    if not app_server.get("checked"):
        error = app_server.get("error")
        if error == "skipped":
            return "skipped"
        return f"skipped ({error})" if error else "skipped"
    if app_server.get("ok"):
        return "ok"
    return f"error ({app_server.get('error') or 'unknown error'})"


def print_doctor_human(report: dict[str, Any]) -> None:
    system = report["system"]
    paths = report["paths"]
    accounts = report["accounts"]
    codex = report["codex"]
    wsl = report["wsl"]

    print("cx doctor")
    print()
    print("[System]")
    print(f"  OS: {system['os']}")
    print(f"  Platform: {system['platform']}")
    print(f"  Python: {system['python_version']} ({system['python_executable']})")
    print(f"  cx script: {system['cx_script']}")
    print(f"  WSL: {bool_status(system['is_wsl'])}")
    print()
    print("[Paths]")
    print(f"  data dir: {paths['data_dir']} ({'exists' if paths['data_dir_exists'] else 'missing'})")
    print(f"  accounts dir: {'exists' if paths['accounts_dir_exists'] else 'missing'}")
    print(f"  temp dir: {'exists' if paths['temp_dir_exists'] else 'missing'}")
    print(f"  CODEX_HOME: {paths['codex_home']}")
    if paths["auth_json_exists"]:
        parse_text = "parse ok" if paths["auth_json_parse_ok"] else "parse failed"
        print(f"  auth.json: exists, {parse_text}")
    else:
        print("  auth.json: missing")
    print()
    print("[Accounts]")
    print(f"  saved accounts: {accounts['count']}")
    print(f"  current alias: {bool_status(accounts['current_alias_set'])}")
    print()
    print("[Codex]")
    print(f"  CX_CODEX_BIN: {codex['cx_codex_bin'] or 'not set'}")
    print(f"  executable: {codex['executable'] or 'not found'}")
    print(f"  version: {codex['version'] or 'unknown'}")
    print(f"  app-server: {app_server_status_text(codex['app_server'])}")
    print()
    print("[WSL]")
    print(f"  checked: {bool_status(wsl['checked'])}")
    print(f"  available: {bool_status(wsl['available'])}")
    print(f"  distro count: {wsl['distro_count']}")
    if report["warnings"]:
        print()
        print("[Warnings]")
        for warning in report["warnings"]:
            print(f"  - {warning}")
    if report["errors"]:
        print()
        print("[Errors]")
        for error in report["errors"]:
            print(f"  - {error}")
    print()
    print(f"Result: {'OK' if report['ok'] else 'ERROR'}")


def cmd_doctor(args: argparse.Namespace) -> int:
    try:
        report = build_doctor_report(skip_app_server=args.skip_app_server)
    except Exception as exc:
        if args.json:
            print_json({"ok": False, "warnings": [], "errors": [str(exc)]})
        else:
            print(f"cx doctor failed: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print_json(report)
    else:
        print_doctor_human(report)
    return 0 if report["ok"] else 1


def read_status_for_alias(alias: str) -> AccountStatus:
    auth_file = account_auth_file(alias)
    scope = read_account_scope(alias)
    cached_email, cached_plan = read_cached_account_identity(alias)
    if not auth_file.exists():
        return AccountStatus(alias, scope, cached_email, cached_plan, None, None, None, None, None, None, "auth.json 不存在")
    try:
        account_result, rate_result = request_app_server(auth_file)
    except CxError as exc:
        return AccountStatus(alias, scope, cached_email, cached_plan, None, None, None, None, None, None, str(exc))

    account = (account_result or {}).get("account") or {}
    rate_limits = (rate_result or {}).get("rateLimits") or {}
    primary = rate_limits.get("primary") or {}
    secondary = rate_limits.get("secondary") or {}
    email = account.get("email")
    if not isinstance(email, str) or not email:
        email = cached_email
    plan = account.get("planType") or rate_limits.get("planType")
    if not isinstance(plan, str) or not plan:
        plan = cached_plan
    if isinstance(email, str) and email:
        with FileLock(LOCK_FILE):
            cache_account_identity(
                alias,
                email=email,
                plan=plan if isinstance(plan, str) and plan else None,
            )
    return AccountStatus(
        alias=alias,
        scope=scope,
        email=email,
        plan=plan,
        primary_used=primary.get("usedPercent"),
        primary_reset=format_reset(primary.get("resetsAt")),
        primary_reset_at=primary.get("resetsAt"),
        secondary_used=secondary.get("usedPercent"),
        secondary_reset=format_reset(secondary.get("resetsAt")),
        secondary_reset_at=secondary.get("resetsAt"),
    )


def read_statuses_for_aliases(aliases: list[str]) -> list[AccountStatus]:
    if len(aliases) <= 1:
        return [read_status_for_alias(alias) for alias in aliases]
    worker_count = min(STATUS_MAX_WORKERS, len(aliases))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        return list(executor.map(read_status_for_alias, aliases))


def used_percent_to_left(used_percent: int) -> int:
    return max(0, min(100, 100 - used_percent))


def format_limit_left_line(label: str, used_percent: int, reset: str | None, *, indent: str = "") -> str:
    line = f"{indent}{label}: {used_percent_to_left(used_percent)}% left"
    if reset:
        line += f" | reset {reset}"
    return line


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
        print(format_limit_left_line("5h", status.primary_used, status.primary_reset, indent="  "))
    if status.secondary_used is not None:
        print(format_limit_left_line("7d", status.secondary_used, status.secondary_reset, indent="  "))


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
    statuses = read_statuses_for_aliases(aliases)
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

    statuses = read_statuses_for_aliases(aliases)
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
            print(format_limit_left_line("5h", soonest.primary_used, soonest.primary_reset))
        if soonest.secondary_used is not None:
            print(format_limit_left_line("7d", soonest.secondary_used, soonest.secondary_reset))
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
        print(format_limit_left_line("5h", best.primary_used, best.primary_reset))
    if best.secondary_used is not None:
        print(format_limit_left_line("7d", best.secondary_used, best.secondary_reset))
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
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {APP_VERSION}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_parser = subparsers.add_parser("add", help="Login and save a new account")
    add_parser.add_argument("alias")
    add_parser.add_argument("--force", action="store_true")
    add_parser.set_defaults(func=cmd_add)

    save_parser = subparsers.add_parser("save", help="Save the current auth as an account")
    save_parser.add_argument("alias")
    save_parser.add_argument("--force", action="store_true")
    save_parser.set_defaults(func=cmd_save)

    renew_parser = subparsers.add_parser(
        "renew",
        help="Re-login and safely update an existing account token",
        description="Re-login an existing alias and update its saved token only when the logged-in account matches the existing alias.",
        epilog="Example:\n  cx renew company",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    renew_parser.add_argument("alias", help="Existing saved account alias")
    renew_parser.set_defaults(func=cmd_renew)

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

    sync_check_parser = subparsers.add_parser(
        "sync-check",
        help="Inspect a backup sync directory and print the planned actions",
        description="Scan a backup sync directory and print the actions cx would take without modifying local accounts.",
    )
    sync_check_parser.add_argument("--dir", required=True, help="Backup sync directory path")
    sync_check_parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    sync_check_parser.add_argument("--no-import-new", dest="import_new_accounts", action="store_false", default=True, help="Do not import new accounts")
    sync_check_parser.add_argument("--no-overwrite-existing", dest="overwrite_existing_accounts", action="store_false", default=True, help="Do not overwrite invalid existing accounts")
    sync_check_parser.add_argument("--allow-legacy-overwrite", dest="allow_legacy_overwrite", action="store_true", default=False, help="Allow overwriting invalid accounts from legacy v1/v2 archives")
    sync_check_parser.add_argument("--no-rollback", dest="rollback_before_overwrite", action="store_false", default=True, help="Disable rollback before overwrite")
    sync_check_parser.set_defaults(func=cmd_sync_check)

    sync_import_parser = subparsers.add_parser(
        "sync-import",
        help="Apply backup sync actions from a directory",
        description="Scan a backup sync directory and apply the chosen sync actions.",
    )
    sync_import_parser.add_argument("--dir", required=True, help="Backup sync directory path")
    sync_import_parser.add_argument("--apply", action="store_true", help="Actually modify local accounts")
    sync_import_parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    sync_import_parser.add_argument("--no-import-new", dest="import_new_accounts", action="store_false", default=True, help="Do not import new accounts")
    sync_import_parser.add_argument("--no-overwrite-existing", dest="overwrite_existing_accounts", action="store_false", default=True, help="Do not overwrite invalid existing accounts")
    sync_import_parser.add_argument("--allow-legacy-overwrite", dest="allow_legacy_overwrite", action="store_true", default=False, help="Allow overwriting invalid accounts from legacy v1/v2 archives")
    sync_import_parser.add_argument("--no-rollback", dest="rollback_before_overwrite", action="store_false", default=True, help="Disable rollback before overwrite")
    sync_import_parser.set_defaults(func=cmd_sync_import)

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

    doctor_parser = subparsers.add_parser(
        "doctor",
        help="Diagnose cx, Codex CLI, and environment setup",
        description="Print a safe environment diagnostic report for cx and the local Codex CLI setup.",
    )
    doctor_parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    doctor_parser.add_argument("--skip-app-server", action="store_true", help="Skip the codex app-server health check")
    doctor_parser.set_defaults(func=cmd_doctor)

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
