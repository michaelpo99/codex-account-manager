from __future__ import annotations

import argparse
import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import cx


class CliRenewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="cx-test-renew-"))
        self.originals = {
            "DATA_DIR": cx.DATA_DIR,
            "ACCOUNTS_DIR": cx.ACCOUNTS_DIR,
            "CURRENT_FILE": cx.CURRENT_FILE,
            "LOCK_FILE": cx.LOCK_FILE,
            "TEMP_DIR": cx.TEMP_DIR,
            "CODEX_HOME": cx.CODEX_HOME,
            "CODEX_AUTH_FILE": cx.CODEX_AUTH_FILE,
            "codex_command": cx.codex_command,
            "run_command": cx.run_command,
            "request_app_server": cx.request_app_server,
        }
        self.configure_paths(self.root / "workspace")
        self.login_email = "user@example.com"
        self.login_token = "new-token"
        self.login_returncode = 0
        self.run_command_calls: list[tuple[list[str], dict[str, str] | None]] = []

        def fake_codex_command(args: list[str]) -> list[str]:
            self.assertEqual(args, ["login", "--device-auth"])
            return ["codex", "login", "--device-auth"]

        def fake_run_command(
            cmd: list[str],
            *,
            env: dict[str, str] | None = None,
            capture_output: bool = False,
        ) -> argparse.Namespace:
            self.assertFalse(capture_output)
            self.run_command_calls.append((cmd, env))
            if env is not None and self.login_returncode == 0:
                temp_auth = Path(env["CODEX_HOME"]) / "auth.json"
                cx.write_text_atomic(
                    temp_auth,
                    json.dumps({"account": {"email": self.login_email}, "token": self.login_token}, ensure_ascii=True) + "\n",
                )
            return argparse.Namespace(returncode=self.login_returncode)

        cx.codex_command = fake_codex_command
        cx.run_command = fake_run_command

        def unexpected_request_app_server(auth_file: Path, timeout_sec: float = 15.0) -> tuple[dict[str, object] | None, dict[str, object] | None]:
            raise AssertionError(f"request_app_server should not be called in this test by default: {auth_file}")

        cx.request_app_server = unexpected_request_app_server

    def tearDown(self) -> None:
        for name, value in self.originals.items():
            setattr(cx, name, value)
        shutil.rmtree(self.root, ignore_errors=True)

    def configure_paths(self, base: Path) -> None:
        cx.DATA_DIR = base / "data"
        cx.ACCOUNTS_DIR = cx.DATA_DIR / "accounts"
        cx.CURRENT_FILE = cx.DATA_DIR / "current"
        cx.LOCK_FILE = cx.DATA_DIR / "lock"
        cx.TEMP_DIR = cx.DATA_DIR / "tmp"
        cx.CODEX_HOME = base / "codex-home"
        cx.CODEX_AUTH_FILE = cx.CODEX_HOME / "auth.json"

    def write_account(self, alias: str, *, email: str = "user@example.com", token: str = "old-token", scope: str = "personal") -> None:
        cx.ensure_dir(cx.account_dir(alias))
        cx.write_text_atomic(
            cx.account_auth_file(alias),
            json.dumps({"account": {"email": email}, "token": token}, ensure_ascii=True) + "\n",
        )
        cx.write_text_atomic(cx.account_meta_file(alias), json.dumps({"scope": scope}, ensure_ascii=True) + "\n")

    def read_json(self, path: Path) -> dict[str, object]:
        return json.loads(path.read_text(encoding="utf-8"))

    def test_parser_registers_renew_command(self) -> None:
        parser = cx.build_parser()

        args = parser.parse_args(["renew", "company"])

        self.assertEqual(args.alias, "company")
        self.assertIs(args.func, cx.cmd_renew)

    def test_manual_mentions_renew(self) -> None:
        output = cx.build_manual("zh-TW", "markdown")

        self.assertIn("### `cx renew`", output)
        self.assertIn("cx renew <alias>", output)

    def test_renew_updates_saved_auth_preserves_scope_and_syncs_current(self) -> None:
        self.write_account("company", scope="personal")
        cx.set_current_alias("company")
        cx.write_text_atomic(cx.CODEX_AUTH_FILE, json.dumps({"account": {"email": "user@example.com"}, "token": "active-old"}) + "\n")

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = cx.cmd_renew(argparse.Namespace(alias="company"))

        self.assertEqual(exit_code, 0)
        self.assertIn("已更新帳號 token：company", stdout.getvalue())
        self.assertIn("已同步更新目前 Codex 帳號。", stdout.getvalue())
        self.assertTrue(cx.account_dir("company").exists())
        self.assertEqual(self.read_json(cx.account_auth_file("company"))["token"], "new-token")
        self.assertEqual(self.read_json(cx.CODEX_AUTH_FILE)["token"], "new-token")
        self.assertEqual(self.read_json(cx.account_meta_file("company"))["scope"], "personal")
        self.assertEqual(self.read_json(cx.account_meta_file("company"))["email"], "user@example.com")
        self.assertEqual(len(self.run_command_calls), 1)

    def test_renew_uses_meta_email_cache_when_auth_and_status_cannot_identify_email(self) -> None:
        cx.ensure_dir(cx.account_dir("company"))
        cx.write_text_atomic(cx.account_auth_file("company"), json.dumps({"token": "old-token"}) + "\n")
        cx.write_text_atomic(
            cx.account_meta_file("company"),
            json.dumps({"scope": "personal", "email": "user@example.com", "plan": "plus"}, ensure_ascii=True) + "\n",
        )

        def fake_request_app_server(
            auth_file: Path,
            timeout_sec: float = 15.0,
        ) -> tuple[dict[str, object] | None, dict[str, object] | None]:
            self.assertEqual(auth_file, cx.account_auth_file("company"))
            raise cx.CxError("app-server unavailable")

        cx.request_app_server = fake_request_app_server

        exit_code = cx.cmd_renew(argparse.Namespace(alias="company"))

        self.assertEqual(exit_code, 0)
        meta = self.read_json(cx.account_meta_file("company"))
        self.assertEqual(meta["scope"], "personal")
        self.assertEqual(meta["email"], "user@example.com")

    def test_renew_does_not_sync_active_auth_when_alias_is_not_current(self) -> None:
        self.write_account("company")
        cx.set_current_alias("other")
        cx.write_text_atomic(cx.CODEX_AUTH_FILE, json.dumps({"account": {"email": "other@example.com"}, "token": "active-old"}) + "\n")

        cx.cmd_renew(argparse.Namespace(alias="company"))

        self.assertEqual(self.read_json(cx.account_auth_file("company"))["token"], "new-token")
        self.assertEqual(self.read_json(cx.CODEX_AUTH_FILE)["token"], "active-old")

    def test_renew_rejects_missing_alias(self) -> None:
        with self.assertRaises(cx.CxError) as raised:
            cx.cmd_renew(argparse.Namespace(alias="missing"))

        self.assertIn("renew 只支援已存在的 alias", str(raised.exception))
        self.assertFalse(cx.account_dir("missing").exists())
        self.assertEqual(self.run_command_calls, [])

    def test_renew_rejects_mismatched_email_without_overwriting(self) -> None:
        self.write_account("company", email="old@example.com", token="old-token")
        self.login_email = "new@example.com"

        with self.assertRaises(cx.CxError) as raised:
            cx.cmd_renew(argparse.Namespace(alias="company"))

        self.assertIn("登入帳號不一致，已取消 renew", str(raised.exception))
        self.assertEqual(self.read_json(cx.account_auth_file("company"))["token"], "old-token")

    def test_renew_rejects_existing_auth_without_email(self) -> None:
        cx.ensure_dir(cx.account_dir("company"))
        cx.write_text_atomic(cx.account_auth_file("company"), json.dumps({"token": "old-token"}) + "\n")

        def fake_request_app_server(
            auth_file: Path,
            timeout_sec: float = 15.0,
        ) -> tuple[dict[str, object] | None, dict[str, object] | None]:
            self.assertEqual(auth_file, cx.account_auth_file("company"))
            raise cx.CxError("app-server unavailable")

        cx.request_app_server = fake_request_app_server

        with self.assertRaises(cx.CxError) as raised:
            cx.cmd_renew(argparse.Namespace(alias="company"))

        self.assertIn("既有 auth.json 無法識別 email", str(raised.exception))
        self.assertEqual(self.run_command_calls, [])

    def test_renew_falls_back_to_status_email_when_static_parse_fails(self) -> None:
        cx.ensure_dir(cx.account_dir("company"))
        cx.write_text_atomic(cx.account_auth_file("company"), json.dumps({"token": "old-token"}) + "\n")
        cx.write_text_atomic(cx.account_meta_file("company"), json.dumps({"scope": "work"}) + "\n")

        def fake_request_app_server(
            auth_file: Path,
            timeout_sec: float = 15.0,
        ) -> tuple[dict[str, object] | None, dict[str, object] | None]:
            self.assertEqual(auth_file, cx.account_auth_file("company"))
            return (
                {"account": {"email": "user@example.com"}},
                {"rateLimits": {}},
            )

        cx.request_app_server = fake_request_app_server

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = cx.cmd_renew(argparse.Namespace(alias="company"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(self.read_json(cx.account_auth_file("company"))["token"], "new-token")
        self.assertIn("已更新帳號 token：company", stdout.getvalue())
        self.assertEqual(len(self.run_command_calls), 1)

    def test_renew_rejects_when_static_parse_and_status_fallback_fail(self) -> None:
        cx.ensure_dir(cx.account_dir("company"))
        cx.write_text_atomic(cx.account_auth_file("company"), json.dumps({"token": "old-token"}) + "\n")

        def fake_request_app_server(
            auth_file: Path,
            timeout_sec: float = 15.0,
        ) -> tuple[dict[str, object] | None, dict[str, object] | None]:
            self.assertEqual(auth_file, cx.account_auth_file("company"))
            raise cx.CxError("app-server unavailable")

        cx.request_app_server = fake_request_app_server

        with self.assertRaises(cx.CxError) as raised:
            cx.cmd_renew(argparse.Namespace(alias="company"))

        self.assertIn("既有 auth.json 無法識別 email", str(raised.exception))
        self.assertEqual(self.run_command_calls, [])

    def test_renew_rejects_new_auth_without_email(self) -> None:
        self.write_account("company", token="old-token")

        def fake_run_command(
            cmd: list[str],
            *,
            env: dict[str, str] | None = None,
            capture_output: bool = False,
        ) -> argparse.Namespace:
            self.run_command_calls.append((cmd, env))
            if env is not None:
                cx.write_text_atomic(Path(env["CODEX_HOME"]) / "auth.json", json.dumps({"token": "new-token"}) + "\n")
            return argparse.Namespace(returncode=0)

        cx.run_command = fake_run_command

        with self.assertRaises(cx.CxError) as raised:
            cx.cmd_renew(argparse.Namespace(alias="company"))

        self.assertIn("新的登入結果無法識別 email", str(raised.exception))
        self.assertEqual(self.read_json(cx.account_auth_file("company"))["token"], "old-token")

    def test_renew_rejects_login_failure_without_overwriting(self) -> None:
        self.write_account("company", token="old-token")
        self.login_returncode = 42

        with self.assertRaises(cx.CxError) as raised:
            cx.cmd_renew(argparse.Namespace(alias="company"))

        self.assertIn("退出碼 42", str(raised.exception))
        self.assertEqual(self.read_json(cx.account_auth_file("company"))["token"], "old-token")

    def test_write_account_scope_preserves_cached_identity_fields(self) -> None:
        self.write_account("company", scope="work")
        cx.write_text_atomic(
            cx.account_meta_file("company"),
            json.dumps({"scope": "work", "email": "user@example.com", "plan": "business"}, ensure_ascii=True) + "\n",
        )

        cx.write_account_scope("company", "personal")

        self.assertEqual(
            self.read_json(cx.account_meta_file("company")),
            {"scope": "personal", "email": "user@example.com", "plan": "business"},
        )


if __name__ == "__main__":
    unittest.main()
