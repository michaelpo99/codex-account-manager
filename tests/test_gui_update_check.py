from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
GUI_PATH = ROOT / "gui" / "cx_gui.py"
HAS_TKINTER = importlib.util.find_spec("tkinter") is not None
cx_gui = None
if HAS_TKINTER:
    SPEC = importlib.util.spec_from_file_location("cx_gui_update", GUI_PATH)
    assert SPEC is not None
    cx_gui = importlib.util.module_from_spec(SPEC)
    sys.modules["cx_gui_update"] = cx_gui
    assert SPEC.loader is not None
    SPEC.loader.exec_module(cx_gui)


@unittest.skipUnless(HAS_TKINTER, "tkinter is not available in this Python environment")
class UpdateCheckTests(unittest.TestCase):
    def create_app(self):
        assert cx_gui is not None
        try:
            root = cx_gui.Tk()
        except cx_gui.TclError as exc:
            self.skipTest(f"Tk cannot start in this environment: {exc}")
        root.geometry("1180x680")
        refresh_accounts = cx_gui.CxGui.refresh_accounts
        detect_environment_values = cx_gui.CxGui.detect_environment_values
        cx_gui.CxGui.refresh_accounts = lambda self, **_kwargs: None
        cx_gui.CxGui.detect_environment_values = staticmethod(lambda: [cx_gui.WINDOWS_TARGET])
        try:
            app = cx_gui.CxGui(root)
        finally:
            cx_gui.CxGui.refresh_accounts = refresh_accounts
            cx_gui.CxGui.detect_environment_values = staticmethod(detect_environment_values)
        return root, app

    def test_release_version_helpers_normalize_and_compare(self) -> None:
        assert cx_gui is not None

        self.assertEqual(cx_gui.normalize_release_version(" v4.2.1 "), "4.2.1")
        self.assertEqual(cx_gui.parse_semver("4.2.1"), (4, 2, 1))
        self.assertIsNone(cx_gui.parse_semver("4.2"))
        self.assertTrue(cx_gui.is_remote_version_newer("4.2.0", "4.2.1"))
        self.assertFalse(cx_gui.is_remote_version_newer("4.2.1", "4.2.1"))

    def test_update_check_settings_default_to_enabled_and_save_cleanly(self) -> None:
        assert cx_gui is not None

        with tempfile.TemporaryDirectory() as tmpdir:
            settings_file = Path(tmpdir) / "gui-settings.json"
            settings_file.write_text(json.dumps({"target": cx_gui.WINDOWS_TARGET}) + "\n", encoding="utf-8")
            default_settings_file = cx_gui.CxGui.default_settings_file
            cx_gui.CxGui.default_settings_file = staticmethod(lambda: settings_file)
            try:
                root, app = self.create_app()
            finally:
                cx_gui.CxGui.default_settings_file = staticmethod(default_settings_file)
            try:
                self.assertTrue(app.update_check_state.enabled)
                self.assertIsNone(app.update_check_state.last_checked_at)
                self.assertIsNone(app.update_check_state.last_seen_version)
                self.assertIsNone(app.update_check_state.dismissed_version)
                self.assertIsNone(app.update_check_state.last_error_at)

                app.update_check_state.last_checked_at = cx_gui.now_utc()
                app.update_check_state.last_seen_version = "4.4.1"
                app.update_check_state.dismissed_version = "4.4.0"
                app.update_check_state.last_error_at = cx_gui.now_utc()
                app.save_update_check_settings()

                payload = json.loads(settings_file.read_text(encoding="utf-8"))
                self.assertEqual(
                    payload["update_check"],
                    {
                        "enabled": True,
                        "last_checked_at": payload["update_check"]["last_checked_at"],
                        "last_seen_version": "4.4.1",
                        "dismissed_version": "4.4.0",
                        "last_error_at": payload["update_check"]["last_error_at"],
                    },
                )
            finally:
                root.destroy()

    def test_fetch_update_check_result_parses_latest_release_payload(self) -> None:
        assert cx_gui is not None

        class FakeResponse:
            def __init__(self, body: bytes) -> None:
                self.body = body

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb) -> None:
                return None

            def read(self) -> bytes:
                return self.body

        package = __import__("cx_account_manager", fromlist=["__version__"])
        local_version = cx_gui.normalize_release_version(package.__version__)
        self.assertIsNotNone(local_version)
        assert local_version is not None
        parsed_local = cx_gui.parse_semver(local_version)
        self.assertIsNotNone(parsed_local)
        assert parsed_local is not None
        major, minor, patch = parsed_local
        remote_version = f"{major}.{minor}.{patch + 1}"
        payload = {"tag_name": f"v{remote_version}", "html_url": f"https://example.com/releases/v{remote_version}"}

        with tempfile.TemporaryDirectory() as tmpdir:
            settings_file = Path(tmpdir) / "gui-settings.json"
            settings_file.write_text(json.dumps({"target": cx_gui.WINDOWS_TARGET}) + "\n", encoding="utf-8")
            default_settings_file = cx_gui.CxGui.default_settings_file
            cx_gui.CxGui.default_settings_file = staticmethod(lambda: settings_file)
            try:
                root, app = self.create_app()
            finally:
                cx_gui.CxGui.default_settings_file = staticmethod(default_settings_file)
            try:
                with mock.patch.object(cx_gui.urlrequest, "urlopen", return_value=FakeResponse(json.dumps(payload).encode("utf-8"))):
                    result = app.fetch_update_check_result()

                self.assertTrue(result.ok)
                self.assertEqual(result.latest_version, remote_version)
                self.assertEqual(result.release_url, f"https://example.com/releases/v{remote_version}")
                self.assertTrue(result.is_newer)
            finally:
                root.destroy()

    def test_update_notice_can_be_dismissed_and_persisted(self) -> None:
        assert cx_gui is not None

        with tempfile.TemporaryDirectory() as tmpdir:
            settings_file = Path(tmpdir) / "gui-settings.json"
            settings_file.write_text(json.dumps({"target": cx_gui.WINDOWS_TARGET}) + "\n", encoding="utf-8")
            default_settings_file = cx_gui.CxGui.default_settings_file
            cx_gui.CxGui.default_settings_file = staticmethod(lambda: settings_file)
            try:
                root, app = self.create_app()
            finally:
                cx_gui.CxGui.default_settings_file = staticmethod(default_settings_file)
            try:
                result = cx_gui.UpdateCheckResult(
                    ok=True,
                    latest_version="4.4.1",
                    release_url="https://example.com/releases/v4.4.1",
                    is_newer=True,
                )
                app.finish_update_check(result, manual=False, force=False)
                root.update()
                root.update_idletasks()

                self.assertEqual(app.update_notice_var.get(), "Update available: cx-account-manager 4.4.1")
                self.assertTrue(app.update_notice_frame.winfo_ismapped())
                self.assertEqual(str(app.update_release_button.cget("state")), "normal")

                app.dismiss_update_notice()

                self.assertEqual(app.update_notice_var.get(), "")
                self.assertFalse(app.update_notice_frame.winfo_ismapped())
                payload = json.loads(settings_file.read_text(encoding="utf-8"))
                self.assertEqual(payload["update_check"]["dismissed_version"], "4.4.1")
            finally:
                root.destroy()


if __name__ == "__main__":
    unittest.main()
