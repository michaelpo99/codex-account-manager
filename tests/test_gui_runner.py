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


if __name__ == "__main__":
    unittest.main()
