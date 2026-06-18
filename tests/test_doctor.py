from __future__ import annotations

import argparse
import contextlib
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


class DoctorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="cx-test-doctor-"))
        self.originals = {
            "DATA_DIR": cx.DATA_DIR,
            "ACCOUNTS_DIR": cx.ACCOUNTS_DIR,
            "CURRENT_FILE": cx.CURRENT_FILE,
            "LOCK_FILE": cx.LOCK_FILE,
            "TEMP_DIR": cx.TEMP_DIR,
            "CODEX_HOME": cx.CODEX_HOME,
            "CODEX_AUTH_FILE": cx.CODEX_AUTH_FILE,
        }
        self.configure_paths(self.root / "workspace")
        cx.ensure_layout()
        cx.ensure_dir(cx.CODEX_HOME)
        cx.write_text_atomic(cx.CODEX_AUTH_FILE, json.dumps({"token": "SECRET_TEST_TOKEN", "account": {"email": "private@example.com"}}))

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

    def test_cmd_doctor_json_outputs_valid_safe_json(self) -> None:
        args = argparse.Namespace(json=True, skip_app_server=True)
        stdout = io.StringIO()

        with (
            mock.patch.object(cx, "find_codex_executable", return_value="codex"),
            mock.patch.object(cx, "codex_version_for_doctor", return_value=("codex 1.2.3", None)),
            mock.patch.object(cx, "wsl_info_for_doctor", return_value={"checked": True, "available": False, "distro_count": 0, "is_wsl": False, "error": None}),
            contextlib.redirect_stdout(stdout),
        ):
            exit_code = cx.cmd_doctor(args)

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertTrue(payload["ok"])
        self.assertIn("system", payload)
        self.assertIn("paths", payload)
        self.assertIn("codex", payload)
        self.assertIn("accounts", payload)
        self.assertIn("wsl", payload)
        self.assertNotIn("SECRET_TEST_TOKEN", stdout.getvalue())
        self.assertNotIn("private@example.com", stdout.getvalue())

    def test_cmd_doctor_missing_codex_returns_error_without_traceback(self) -> None:
        args = argparse.Namespace(json=True, skip_app_server=True)
        stdout = io.StringIO()

        with (
            mock.patch.object(cx, "find_codex_executable", return_value=None),
            mock.patch.object(cx, "wsl_info_for_doctor", return_value={"checked": True, "available": False, "distro_count": 0, "is_wsl": False, "error": None}),
            contextlib.redirect_stdout(stdout),
        ):
            exit_code = cx.cmd_doctor(args)

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertFalse(payload["ok"])
        self.assertIn("codex executable was not found", payload["errors"])

    def test_skip_app_server_does_not_call_app_server(self) -> None:
        with (
            mock.patch.object(cx, "find_codex_executable", return_value="codex"),
            mock.patch.object(cx, "codex_version_for_doctor", return_value=("codex 1.2.3", None)),
            mock.patch.object(cx, "request_app_server") as request_app_server,
            mock.patch.object(cx, "wsl_info_for_doctor", return_value={"checked": True, "available": False, "distro_count": 0, "is_wsl": False, "error": None}),
        ):
            report = cx.build_doctor_report(skip_app_server=True)

        request_app_server.assert_not_called()
        self.assertFalse(report["codex"]["app_server"]["checked"])

    def test_no_saved_accounts_is_warning_not_error(self) -> None:
        with (
            mock.patch.object(cx, "find_codex_executable", return_value="codex"),
            mock.patch.object(cx, "codex_version_for_doctor", return_value=("codex 1.2.3", None)),
            mock.patch.object(cx, "wsl_info_for_doctor", return_value={"checked": True, "available": False, "distro_count": 0, "is_wsl": False, "error": None}),
        ):
            report = cx.build_doctor_report(skip_app_server=True)

        self.assertTrue(report["ok"])
        self.assertIn("no saved accounts", report["warnings"])

    def test_parser_registers_doctor_command(self) -> None:
        parser = cx.build_parser()

        args = parser.parse_args(["doctor", "--json", "--skip-app-server"])

        self.assertTrue(args.json)
        self.assertTrue(args.skip_app_server)
        self.assertIs(args.func, cx.cmd_doctor)

    def test_manual_mentions_doctor_command(self) -> None:
        output = cx.build_manual("en", "markdown")

        self.assertIn("### `cx doctor`", output)
        self.assertIn("cx doctor [--json] [--skip-app-server]", output)


if __name__ == "__main__":
    unittest.main()
