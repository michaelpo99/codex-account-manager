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

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

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


if __name__ == "__main__":
    unittest.main()
