#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from queue import Empty, Queue
from typing import Any


APP_NAME = "cx"
ALIAS_RE = re.compile(r"^[A-Za-z0-9_-]+$")
ACCOUNT_SCOPE_RE = re.compile(r"^(work|personal)$")
DATA_DIR = Path.home() / ".local" / "share" / "cx"
ACCOUNTS_DIR = DATA_DIR / "accounts"
CURRENT_FILE = DATA_DIR / "current"
LOCK_FILE = DATA_DIR / "lock"
CODEX_HOME = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
CODEX_AUTH_FILE = CODEX_HOME / "auth.json"


class CxError(Exception):
    pass


@dataclass
class AccountStatus:
    alias: str
    scope: str
    email: str | None
    plan: str | None
    primary_used: int | None
    primary_reset: str | None
    primary_reset_at: int | None
    secondary_used: int | None
    secondary_reset: str | None
    secondary_reset_at: int | None
    error: str | None = None


class FileLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.handle = None

    def __enter__(self) -> "FileLock":
        ensure_dir(DATA_DIR, mode=0o700)
        self.handle = self.path.open("a+", encoding="utf-8")
        fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.handle is not None:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            self.handle.close()


def ensure_dir(path: Path, mode: int = 0o700) -> None:
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, mode)


def ensure_layout() -> None:
    ensure_dir(DATA_DIR, mode=0o700)
    ensure_dir(ACCOUNTS_DIR, mode=0o700)
    if not LOCK_FILE.exists():
        LOCK_FILE.touch(mode=0o600, exist_ok=True)
    os.chmod(LOCK_FILE, 0o600)


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


def atomic_copy(src: Path, dest: Path, mode: int = 0o600) -> None:
    ensure_dir(dest.parent, mode=0o700)
    with tempfile.NamedTemporaryFile(dir=dest.parent, delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        shutil.copyfile(src, tmp_path)
        os.chmod(tmp_path, mode)
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
        os.chmod(tmp_path, mode)
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


def require_codex() -> None:
    if shutil.which("codex") is None:
        raise CxError("找不到 `codex` 指令，請先安裝 Codex CLI。")


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
    require_codex()
    ensure_layout()
    target_dir = account_dir(alias)
    target_auth = account_auth_file(alias)

    with FileLock(LOCK_FILE):
        if target_dir.exists() and not args.force:
            raise CxError(f"帳號 `{alias}` 已存在；若要覆蓋請使用 `--force`。")
        if target_dir.exists():
            shutil.rmtree(target_dir)
        ensure_dir(target_dir, mode=0o700)

        temp_home = Path(tempfile.mkdtemp(prefix="cx-login-"))
        try:
            print(f"請在瀏覽器中確認登入的是 `{alias}` 對應的帳號。", file=sys.stderr)
            env = os.environ.copy()
            env["CODEX_HOME"] = str(temp_home)
            result = run_command(["codex", "login", "--device-auth"], env=env)
            if result.returncode != 0:
                raise CxError(f"`codex login --device-auth` 失敗，退出碼 {result.returncode}")
            temp_auth = temp_home / "auth.json"
            if not temp_auth.exists():
                raise CxError("登入完成後沒有找到 auth.json，無法保存帳號。")
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


def cmd_list(args: argparse.Namespace) -> int:
    aliases = list_aliases()
    current = read_current_alias()
    for alias in aliases:
        marker = "*" if alias == current else " "
        print(f"{marker} {alias} [{read_account_scope(alias)}]")
    return 0


def cmd_current(args: argparse.Namespace) -> int:
    current = read_current_alias()
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


def use_account(alias: str) -> None:
    ensure_layout()
    src = account_auth_file(alias)
    if not src.exists():
        raise CxError(f"找不到帳號 `{alias}` 的憑證。")
    if CODEX_AUTH_FILE.exists():
        mode = CODEX_AUTH_FILE.stat().st_mode & 0o777
        if mode != 0o600:
            os.chmod(CODEX_AUTH_FILE, 0o600)
    with FileLock(LOCK_FILE):
        atomic_copy(src, CODEX_AUTH_FILE)
        set_current_alias(alias)


def format_reset(ts: int | None) -> str | None:
    if ts is None:
        return None
    return dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


def usage_remaining(used_percent: int | None) -> int:
    if used_percent is None:
        return -1
    return max(0, 100 - used_percent)


def status_sort_key(status: AccountStatus) -> tuple[Any, ...]:
    if status.error:
        return (1, 1, 1, 1, status.alias)

    primary_remaining = usage_remaining(status.primary_used)
    secondary_remaining = usage_remaining(status.secondary_used)
    primary_blocked = status.primary_used is not None and status.primary_used >= 100
    secondary_blocked = status.secondary_used is not None and status.secondary_used >= 100
    personal_penalty = 1 if status.scope == "personal" else 0

    return (
        0,
        personal_penalty,
        1 if primary_blocked else 0,
        -primary_remaining,
        status.primary_reset_at if primary_blocked else 0,
        1 if secondary_blocked else 0,
        -secondary_remaining,
        status.secondary_reset_at if secondary_blocked else 0,
        status.alias,
    )


def request_app_server(auth_file: Path, timeout_sec: float = 15.0) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    temp_home = Path(tempfile.mkdtemp(prefix="cx-status-"))
    try:
        atomic_copy(auth_file, temp_home / "auth.json")
        env = os.environ.copy()
        env["CODEX_HOME"] = str(temp_home)
        proc = subprocess.Popen(
            ["codex", "app-server", "--stdio"],
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
            if payload.get("id") == 2:
                account_result = payload.get("result")
            elif payload.get("id") == 3:
                rate_result = payload.get("result")

        if account_result is None or rate_result is None:
            stderr_texts: list[str] = []
            while True:
                try:
                    stderr_texts.append(stderr_queue.get_nowait().strip())
                except Empty:
                    break
            detail = stderr_texts[0] if stderr_texts else "app-server did not return account data in time"
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


def cmd_status(args: argparse.Namespace) -> int:
    require_codex()
    ensure_layout()
    aliases = [validate_alias(args.alias)] if args.alias else list_aliases()
    if not aliases:
        print("目前沒有已保存的帳號。")
        return 0
    current = read_current_alias()
    statuses = [read_status_for_alias(alias) for alias in aliases]
    if not args.alias:
        statuses.sort(key=status_sort_key)
    exit_code = 0
    for index, status in enumerate(statuses):
        if status.error:
            exit_code = 1
        rank = index + 1 if not args.alias else None
        print_status(status, current, rank=rank)
        if index != len(statuses) - 1:
            print()
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

    best = min(candidates, key=status_sort_key)
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=APP_NAME,
        description="Manage multiple Codex accounts and query status.",
        epilog=(
            "Examples:\n"
            "  cx list\n"
            "  cx status\n"
            "  cx best\n"
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
    list_parser.set_defaults(func=cmd_list)

    scope_parser = subparsers.add_parser(
        "scope",
        help="Mark an account as work or personal to influence ranking",
        description="Mark a saved account as work or personal. Work accounts are preferred over personal accounts when ranking.",
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
    status_parser.set_defaults(func=cmd_status)

    best_parser = subparsers.add_parser(
        "best",
        help="Switch to the best-ranked account right now, preferring work accounts",
        description="Switch to the best-ranked account right now, preferring work accounts over personal accounts.",
        epilog="Example:\n  cx best",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    best_parser.set_defaults(func=cmd_best)

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
