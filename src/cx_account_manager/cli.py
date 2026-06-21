from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path
from typing import Callable

import cx as _cx

_RENEW_COMMAND = ("renew", "cx renew <alias>")
_BUILD_PARSER_WRAPPED_ATTR = "_cx_renew_wrapped"


def _auth_email(auth_file: Path) -> str | None:
    if not auth_file.exists():
        return None
    email, _plan = _cx.read_account_summary_from_auth_bytes(auth_file.read_bytes())
    return email


def _require_auth_email(auth_file: Path, *, message: str) -> str:
    email = _auth_email(auth_file)
    if not email:
        raise _cx.CxError(message)
    return email


def cmd_renew(args: argparse.Namespace) -> int:
    alias = _cx.validate_alias(args.alias)
    _cx.ensure_layout()

    target_dir = _cx.account_dir(alias)
    target_auth = _cx.account_auth_file(alias)
    if not target_dir.exists():
        raise _cx.CxError(f"找不到帳號 `{alias}`；renew 只支援已存在的 alias。")
    if not target_auth.exists():
        raise _cx.CxError(f"找不到帳號 `{alias}` 的既有 auth.json，無法 renew。")

    old_email = _require_auth_email(
        target_auth,
        message=f"帳號 `{alias}` 的既有 auth.json 無法識別 email，為避免覆寫錯帳號，已取消 renew。",
    )

    codex = _cx.codex_command(["login", "--device-auth"])
    temp_home = _cx.make_temp_codex_home("cx-renew-")
    renewed_current = False
    try:
        print(f"請在瀏覽器中重新登入 `{alias}` 對應的帳號。", file=sys.stderr)
        env = os.environ.copy()
        env["CODEX_HOME"] = str(temp_home)
        result = _cx.run_command(codex, env=env)
        if result.returncode != 0:
            raise _cx.CxError(f"`codex login --device-auth` 失敗，退出碼 {result.returncode}")

        temp_auth = temp_home / "auth.json"
        if not temp_auth.exists():
            raise _cx.CxError("登入完成後沒有找到 auth.json，無法 renew 帳號。")

        new_email = _require_auth_email(
            temp_auth,
            message="新的登入結果無法識別 email，為避免覆寫錯帳號，已取消 renew。",
        )
        if old_email != new_email:
            raise _cx.CxError(
                "登入帳號不一致，已取消 renew。\n"
                f"Alias: {alias}\n"
                f"Expected: {old_email}\n"
                f"Actual: {new_email}"
            )

        with _cx.FileLock(_cx.LOCK_FILE):
            if not target_auth.exists():
                raise _cx.CxError(f"找不到帳號 `{alias}` 的既有 auth.json，無法 renew。")
            latest_email = _require_auth_email(
                target_auth,
                message=f"帳號 `{alias}` 的既有 auth.json 無法識別 email，為避免覆寫錯帳號，已取消 renew。",
            )
            if latest_email != old_email:
                raise _cx.CxError(
                    "renew 期間既有帳號資料已變更，已取消覆寫。\n"
                    f"Alias: {alias}\n"
                    f"Original: {old_email}\n"
                    f"Current: {latest_email}"
                )
            current = _cx.read_current_alias()
            _cx.atomic_copy(temp_auth, target_auth)
            if current == alias:
                _cx.atomic_copy(temp_auth, _cx.CODEX_AUTH_FILE)
                renewed_current = True
    finally:
        shutil.rmtree(temp_home, ignore_errors=True)

    print(f"已更新帳號 token：{alias}")
    print(f"Email: {old_email}")
    if renewed_current:
        print("已同步更新目前 Codex 帳號。")
    return 0


def _ensure_manual_command() -> None:
    if any(name == _RENEW_COMMAND[0] for name, _usage in _cx.MANUAL_COMMANDS):
        return
    commands = list(_cx.MANUAL_COMMANDS)
    insert_at = next((index + 1 for index, (name, _usage) in enumerate(commands) if name == "save"), len(commands))
    commands.insert(insert_at, _RENEW_COMMAND)
    _cx.MANUAL_COMMANDS = commands


def _renew_parser(subparsers: argparse._SubParsersAction) -> None:
    renew_parser = subparsers.add_parser(
        "renew",
        help="Re-login and safely update an existing account token",
        description="Re-login an existing alias and update its saved token only when the logged-in account matches the existing alias.",
        epilog="Example:\n  cx renew company",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    renew_parser.add_argument("alias", help="Existing saved account alias")
    renew_parser.set_defaults(func=cmd_renew)


def _wrap_build_parser(original: Callable[[], argparse.ArgumentParser]) -> Callable[[], argparse.ArgumentParser]:
    def build_parser() -> argparse.ArgumentParser:
        parser = original()
        subparsers = next(
            (action for action in parser._actions if isinstance(action, argparse._SubParsersAction)),
            None,
        )
        if subparsers is None:
            raise RuntimeError("cx parser does not expose subcommands")
        if "renew" not in subparsers.choices:
            _renew_parser(subparsers)
        return parser

    setattr(build_parser, _BUILD_PARSER_WRAPPED_ATTR, True)
    return build_parser


def _install_renew_command() -> None:
    _ensure_manual_command()
    _cx.cmd_renew = cmd_renew
    if not getattr(_cx.build_parser, _BUILD_PARSER_WRAPPED_ATTR, False):
        _cx.build_parser = _wrap_build_parser(_cx.build_parser)


def main(argv: list[str] | None = None) -> int:
    _install_renew_command()
    return _cx.main(argv)


__all__ = ["main", "cmd_renew"]
