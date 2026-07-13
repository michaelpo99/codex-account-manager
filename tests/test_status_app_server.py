from __future__ import annotations

import importlib.util
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
CX_PATH = ROOT / "src" / "cx.py"
SPEC = importlib.util.spec_from_file_location("cx", CX_PATH)
assert SPEC is not None
cx = importlib.util.module_from_spec(SPEC)
sys.modules["cx"] = cx
assert SPEC.loader is not None
SPEC.loader.exec_module(cx)


class FakeProc:
    def __init__(self, stdout_lines: list[dict[str, object]], stderr: str = "") -> None:
        self.stdin = io.StringIO()
        self.stdout = io.StringIO("".join(json.dumps(line) + "\n" for line in stdout_lines))
        self.stderr = io.StringIO(stderr)
        self.returncode = None
        self.terminated = False
        self.killed = False

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = 0

    def wait(self, timeout: float | None = None) -> int:
        return 0

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9


class AppServerStatusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="cx-test-status-"))
        self.originals = {
            "DATA_DIR": cx.DATA_DIR,
            "ACCOUNTS_DIR": cx.ACCOUNTS_DIR,
            "CURRENT_FILE": cx.CURRENT_FILE,
            "LOCK_FILE": cx.LOCK_FILE,
            "TEMP_DIR": cx.TEMP_DIR,
            "CODEX_HOME": cx.CODEX_HOME,
            "CODEX_AUTH_FILE": cx.CODEX_AUTH_FILE,
        }

    def tearDown(self) -> None:
        for name, value in self.originals.items():
            setattr(cx, name, value)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def configure_paths(self, base: Path) -> None:
        cx.DATA_DIR = base / "data"
        cx.ACCOUNTS_DIR = cx.DATA_DIR / "accounts"
        cx.CURRENT_FILE = cx.DATA_DIR / "current"
        cx.LOCK_FILE = cx.DATA_DIR / "lock"
        cx.TEMP_DIR = cx.DATA_DIR / "tmp"
        cx.CODEX_HOME = base / "codex-home"
        cx.CODEX_AUTH_FILE = cx.CODEX_HOME / "auth.json"

    def test_json_rpc_error_is_reported_without_timeout_message(self) -> None:
        proc = FakeProc(
            [
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "error": {"code": -32001, "message": "not logged in"},
                }
            ]
        )

        with mock.patch.object(cx, "make_temp_codex_home", return_value=self.temp_dir):
            with mock.patch.object(cx, "atomic_copy"):
                with mock.patch.object(cx, "codex_command", return_value=["codex", "app-server"]):
                    with mock.patch.object(cx.subprocess, "Popen", return_value=proc):
                        with self.assertRaises(cx.CxError) as raised:
                            cx.request_app_server(Path("auth.json"), timeout_sec=1)

        self.assertEqual(str(raised.exception), "account/read: not logged in (code -32001)")

    def test_revoked_token_error_is_summarized(self) -> None:
        backend_body = {
            "error": {
                "message": "Encountered invalidated oauth token for user, failing request",
                "type": None,
                "code": "token_revoked",
                "param": None,
            },
            "status": 401,
        }
        proc = FakeProc(
            [
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "error": {
                        "code": -32603,
                        "message": "failed to fetch codex rate limits: GET https://chatgpt.com/backend-api/wham/usage failed: "
                        f"401 Unauthorized; content-type=text/plain; body={json.dumps(backend_body)}",
                    },
                }
            ]
        )

        with mock.patch.object(cx, "make_temp_codex_home", return_value=self.temp_dir):
            with mock.patch.object(cx, "atomic_copy"):
                with mock.patch.object(cx, "codex_command", return_value=["codex", "app-server"]):
                    with mock.patch.object(cx.subprocess, "Popen", return_value=proc):
                        with self.assertRaises(cx.CxError) as raised:
                            cx.request_app_server(Path("auth.json"), timeout_sec=1)

        self.assertEqual(
            str(raised.exception),
            "account/rateLimits/read: OAuth token revoked or expired (HTTP 401, token_revoked); re-login this account (JSON-RPC code -32603)",
        )

    def test_timeout_message_names_missing_methods(self) -> None:
        proc = FakeProc(
            [
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "result": {"account": {"email": "demo@example.com"}},
                }
            ]
        )

        with mock.patch.object(cx, "make_temp_codex_home", return_value=self.temp_dir):
            with mock.patch.object(cx, "atomic_copy"):
                with mock.patch.object(cx, "codex_command", return_value=["codex", "app-server"]):
                    with mock.patch.object(cx.subprocess, "Popen", return_value=proc):
                        with self.assertRaises(cx.CxError) as raised:
                            cx.request_app_server(Path("auth.json"), timeout_sec=0.1)

        self.assertEqual(str(raised.exception), "app-server did not return account/rateLimits/read in time")

    def test_read_status_for_alias_caches_email_and_plan_in_meta(self) -> None:
        self.configure_paths(self.temp_dir / "workspace")
        cx.ensure_dir(cx.account_dir("alpha"))
        cx.write_text_atomic(cx.account_auth_file("alpha"), json.dumps({"token": "demo"}, ensure_ascii=True) + "\n")
        cx.write_text_atomic(cx.account_meta_file("alpha"), json.dumps({"scope": "personal"}, ensure_ascii=True) + "\n")

        with mock.patch.object(
            cx,
            "request_app_server",
            return_value=(
                {"account": {"email": "cached@example.com", "planType": "plus"}},
                {"rateLimits": {"primary": {}, "secondary": {}}},
            ),
        ):
            status = cx.read_status_for_alias("alpha")

        self.assertEqual(status.email, "cached@example.com")
        self.assertEqual(status.plan, "plus")
        self.assertEqual(
            json.loads(cx.account_meta_file("alpha").read_text(encoding="utf-8")),
            {"scope": "personal", "email": "cached@example.com", "plan": "plus"},
        )

    def test_read_status_for_alias_uses_reported_limit_window(self) -> None:
        self.configure_paths(self.temp_dir / "workspace")
        cx.ensure_dir(cx.account_dir("alpha"))
        cx.write_text_atomic(cx.account_auth_file("alpha"), json.dumps({"token": "demo"}, ensure_ascii=True) + "\n")

        with mock.patch.object(
            cx,
            "request_app_server",
            return_value=(
                {"account": {"email": "demo@example.com", "planType": "team"}},
                {
                    "rateLimits": {"primary": {"usedPercent": 3, "windowDurationMins": 10080, "resetsAt": 1_800_000_000}, "secondary": None},
                    "rateLimitResetCredits": {
                        "availableCount": 3,
                        "credits": [
                            {"expiresAt": 1_800_000_000},
                            {"expiresAt": 1_801_000_000},
                        ],
                    },
                },
            ),
        ):
            status = cx.read_status_for_alias("alpha")

        self.assertEqual(status.primary_window_minutes, 10080)
        self.assertIsNone(status.secondary_used)
        self.assertEqual(cx.primary_limit_label(status), "7d")
        self.assertEqual(status.reset_credits_available, 3)
        self.assertEqual(status.reset_credit_expires, ["2027-01-15 16:00", "2027-01-27 05:46"])

    def test_read_status_for_alias_uses_cached_identity_when_app_server_fails(self) -> None:
        self.configure_paths(self.temp_dir / "workspace")
        cx.ensure_dir(cx.account_dir("alpha"))
        cx.write_text_atomic(cx.account_auth_file("alpha"), json.dumps({"token": "demo"}, ensure_ascii=True) + "\n")
        cx.write_text_atomic(
            cx.account_meta_file("alpha"),
            json.dumps({"scope": "personal", "email": "cached@example.com", "plan": "plus"}, ensure_ascii=True) + "\n",
        )

        with mock.patch.object(cx, "request_app_server", side_effect=cx.CxError("status failed")):
            status = cx.read_status_for_alias("alpha")

        self.assertEqual(status.email, "cached@example.com")
        self.assertEqual(status.plan, "plus")
        self.assertEqual(status.error, "status failed")

    def test_read_status_for_alias_uses_cached_identity_when_auth_file_is_missing(self) -> None:
        self.configure_paths(self.temp_dir / "workspace")
        cx.ensure_dir(cx.account_dir("alpha"))
        cx.write_text_atomic(
            cx.account_meta_file("alpha"),
            json.dumps({"scope": "personal", "email": "cached@example.com", "plan": "plus"}, ensure_ascii=True) + "\n",
        )

        status = cx.read_status_for_alias("alpha")

        self.assertEqual(status.email, "cached@example.com")
        self.assertEqual(status.plan, "plus")
        self.assertEqual(status.error, "auth.json 不存在")


if __name__ == "__main__":
    unittest.main()
