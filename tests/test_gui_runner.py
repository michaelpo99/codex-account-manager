from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GUI_PATH = ROOT / "gui" / "cx_gui.py"
HAS_TKINTER = importlib.util.find_spec("tkinter") is not None
cx_gui = None
if HAS_TKINTER:
    SPEC = importlib.util.spec_from_file_location("cx_gui", GUI_PATH)
    assert SPEC is not None
    cx_gui = importlib.util.module_from_spec(SPEC)
    sys.modules["cx_gui"] = cx_gui
    assert SPEC.loader is not None
    SPEC.loader.exec_module(cx_gui)


@unittest.skipUnless(HAS_TKINTER, "tkinter is not available in this Python environment")
class CxRunnerTests(unittest.TestCase):
    def test_wsl_target_path_converts_windows_drive_path(self) -> None:
        assert cx_gui is not None
        runner = cx_gui.CxRunner(ROOT)

        self.assertEqual(
            runner.target_path("WSL", r"D:\backups\cx-backup.tar.gz"),
            "/mnt/d/backups/cx-backup.tar.gz",
        )

    def test_named_wsl_target_path_converts_windows_drive_path(self) -> None:
        assert cx_gui is not None
        runner = cx_gui.CxRunner(ROOT)

        self.assertEqual(
            runner.target_path("WSL: Ubuntu-22.04", r"D:\backups\cx-backup.tar.gz"),
            "/mnt/d/backups/cx-backup.tar.gz",
        )

    def test_native_target_path_keeps_windows_path(self) -> None:
        assert cx_gui is not None
        runner = cx_gui.CxRunner(ROOT)

        self.assertEqual(
            runner.target_path("Windows Native", r"D:\backups\cx-backup.tar.gz"),
            r"D:\backups\cx-backup.tar.gz",
        )

    def test_default_wsl_command_uses_default_distro(self) -> None:
        assert cx_gui is not None
        runner = cx_gui.CxRunner(ROOT)

        command = runner.command("WSL", ["status"])

        self.assertEqual(command[:3], ["wsl.exe", "bash", "-lic"])
        self.assertIn("status", command[-1])

    def test_named_wsl_command_uses_selected_distro(self) -> None:
        assert cx_gui is not None
        runner = cx_gui.CxRunner(ROOT)

        command = runner.command("WSL: Ubuntu-22.04", ["status"])

        self.assertEqual(command[:5], ["wsl.exe", "-d", "Ubuntu-22.04", "bash", "-lic"])
        self.assertIn("status", command[-1])

    def test_named_wsl_display_command_includes_distro(self) -> None:
        assert cx_gui is not None
        runner = cx_gui.CxRunner(ROOT)

        self.assertEqual(
            runner.display_command("WSL: Debian", ["status", "work"]),
            "wsl.exe -d Debian cx status work",
        )

    def test_wsl_target_detection(self) -> None:
        assert cx_gui is not None

        self.assertTrue(cx_gui.CxRunner.is_wsl_target("WSL"))
        self.assertTrue(cx_gui.CxRunner.is_wsl_target("WSL: Debian"))
        self.assertFalse(cx_gui.CxRunner.is_wsl_target("Windows Native"))


@unittest.skipUnless(HAS_TKINTER, "tkinter is not available in this Python environment")
class CxGuiActivityPanelTests(unittest.TestCase):
    def create_app(self):
        assert cx_gui is not None
        try:
            root = cx_gui.Tk()
        except cx_gui.TclError as exc:
            self.skipTest(f"Tk cannot start in this environment: {exc}")
        root.geometry("1180x680")
        refresh_accounts = cx_gui.CxGui.refresh_accounts
        detect_environment_values = cx_gui.CxGui.detect_environment_values
        cx_gui.CxGui.refresh_accounts = lambda self: None
        cx_gui.CxGui.detect_environment_values = staticmethod(lambda: [cx_gui.WINDOWS_TARGET])
        try:
            app = cx_gui.CxGui(root)
        finally:
            cx_gui.CxGui.refresh_accounts = refresh_accounts
            cx_gui.CxGui.detect_environment_values = detect_environment_values
        return root, app

    def test_show_log_panel_expands_detail_area(self) -> None:
        root, app = self.create_app()
        try:
            root.update_idletasks()

            app.show_log_panel()
            root.update()
            root.update_idletasks()

            self.assertTrue(app.log_expanded.get())
            self.assertTrue(app.activity_body.winfo_ismapped())
            self.assertEqual(app.activity_toggle.cget("text"), "Hide details")
            pane_height = app.main_pane.winfo_height()
            sash_y = app.main_pane.sash_coord(0)[1]
            self.assertLessEqual(sash_y, pane_height - cx_gui.ACTIVITY_MIN_EXPANDED_HEIGHT)
        finally:
            root.destroy()

    def test_hide_log_panel_collapses_detail_area(self) -> None:
        root, app = self.create_app()
        try:
            app.show_log_panel()
            root.update()
            app.hide_log_panel()
            root.update()
            root.update_idletasks()

            self.assertFalse(app.log_expanded.get())
            self.assertFalse(app.activity_body.winfo_ismapped())
            self.assertEqual(app.activity_toggle.cget("text"), "Show details")
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
