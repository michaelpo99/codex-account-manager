from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
GUI_PATH = ROOT / "gui" / "cx_gui.py"
HAS_TKINTER = importlib.util.find_spec("tkinter") is not None
cx_gui = None
if HAS_TKINTER:
    SPEC = importlib.util.spec_from_file_location("cx_gui_doctor", GUI_PATH)
    assert SPEC is not None
    cx_gui = importlib.util.module_from_spec(SPEC)
    sys.modules["cx_gui_doctor"] = cx_gui
    assert SPEC.loader is not None
    SPEC.loader.exec_module(cx_gui)


@unittest.skipUnless(HAS_TKINTER, "tkinter is not available in this Python environment")
class GuiDoctorTests(unittest.TestCase):
    def sample_report(self) -> dict[str, object]:
        return {
            "ok": True,
            "warnings": [],
            "errors": [],
            "system": {
                "os": "Windows",
                "python_version": "3.12.10",
                "cx_script": r"C:\Users\demo\AppData\Local\cx\app\cx.py",
                "is_wsl": False,
            },
            "paths": {
                "data_dir": r"C:\Users\demo\AppData\Local\cx",
                "accounts_dir_exists": True,
                "codex_home": r"C:\Users\demo\.codex",
                "auth_json_exists": True,
                "auth_json_parse_ok": True,
            },
            "accounts": {
                "count": 4,
                "current_alias_set": True,
            },
            "codex": {
                "cx_codex_bin": None,
                "executable": r"C:\Users\demo\AppData\Roaming\npm\codex.cmd",
                "version": "codex-cli 0.141.0",
                "app_server": {"checked": True, "ok": True, "error": None},
            },
            "wsl": {
                "checked": True,
                "available": True,
                "distro_count": 2,
            },
        }

    def test_doctor_severity_prefers_errors_then_warnings(self) -> None:
        assert cx_gui is not None

        self.assertEqual(cx_gui.doctor_severity({"errors": ["bad"], "warnings": []}), "Error")
        self.assertEqual(cx_gui.doctor_severity({"errors": [], "warnings": ["hmm"]}), "Warning")
        self.assertEqual(cx_gui.doctor_severity({"errors": [], "warnings": []}), "OK")

    def test_format_doctor_report_for_clipboard_is_human_readable(self) -> None:
        assert cx_gui is not None

        with mock.patch.dict(
            os.environ,
            {
                "USERPROFILE": r"C:\Users\demo",
                "LOCALAPPDATA": r"C:\Users\demo\AppData\Local",
                "APPDATA": r"C:\Users\demo\AppData\Roaming",
            },
            clear=False,
        ):
            text = cx_gui.format_doctor_report_for_clipboard(self.sample_report(), "Windows Native")

        self.assertIn("cx doctor report", text)
        self.assertIn("Target: Windows Native", text)
        self.assertIn("Result: OK", text)
        self.assertIn("app-server: ok", text)
        self.assertIn("%LOCALAPPDATA%\\cx", text)
        self.assertIn("%APPDATA%\\npm\\codex.cmd", text)
        self.assertNotIn(r"C:\Users\demo", text)

    def test_format_doctor_report_does_not_include_sensitive_fields(self) -> None:
        assert cx_gui is not None
        report = self.sample_report()
        report["token"] = "SECRET_TOKEN"
        report["email"] = "private@example.com"

        text = cx_gui.format_doctor_report_for_clipboard(report, "Windows Native")

        self.assertNotIn("SECRET_TOKEN", text)
        self.assertNotIn("private@example.com", text)


if __name__ == "__main__":
    unittest.main()
