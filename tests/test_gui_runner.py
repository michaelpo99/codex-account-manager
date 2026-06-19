from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
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
        cx_gui.CxGui.refresh_accounts = lambda self, **_kwargs: None
        cx_gui.CxGui.detect_environment_values = staticmethod(lambda: [cx_gui.WINDOWS_TARGET])
        try:
            app = cx_gui.CxGui(root)
        finally:
            cx_gui.CxGui.refresh_accounts = refresh_accounts
            cx_gui.CxGui.detect_environment_values = staticmethod(detect_environment_values)
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

    def test_theme_hint_is_visible_and_copyable_in_fallback_mode(self) -> None:
        root, app = self.create_app()
        try:
            root.update_idletasks()

            self.assertEqual(app.theme_hint_entry.winfo_manager(), "grid")
            self.assertEqual(app.theme_hint_copy_button.winfo_manager(), "grid")
            self.assertIn("ttkbootstrap", app.theme_hint_var.get())

            app.copy_theme_hint()

            self.assertEqual(root.clipboard_get(), app.theme_hint_var.get())
            self.assertEqual(app.status_var.get(), "Theme install hint copied")
        finally:
            root.destroy()

    def test_theme_hint_deactivates_to_muted_style(self) -> None:
        root, app = self.create_app()
        try:
            app.deactivate_theme_hint()

            self.assertEqual(app.theme_hint_entry.cget("foreground"), app.theme_tokens.text_muted)
            self.assertEqual(app.theme_hint_entry.cget("readonlybackground"), app.theme_tokens.surface)
        finally:
            root.destroy()

    def test_format_limit_and_reset_are_split_for_table_columns(self) -> None:
        assert cx_gui is not None

        self.assertEqual(cx_gui.CxGui.format_limit(3), "3%")
        self.assertEqual(cx_gui.CxGui.format_limit_reset("2026-06-19 23:58"), "06-19 23:58")
        self.assertEqual(cx_gui.CxGui.format_limit_reset(None), "n/a")

    def test_auto_refresh_interval_normalization(self) -> None:
        assert cx_gui is not None

        self.assertEqual(cx_gui.normalize_auto_refresh_interval("0"), (0, None))
        self.assertEqual(cx_gui.normalize_auto_refresh_interval("300"), (300, None))
        self.assertEqual(cx_gui.normalize_auto_refresh_interval("30")[0], 60)
        self.assertEqual(cx_gui.normalize_auto_refresh_interval("7200")[0], 3600)
        with self.assertRaises(ValueError):
            cx_gui.normalize_auto_refresh_interval("five")

    def test_gui_settings_preserve_target_when_saving_auto_refresh(self) -> None:
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
                app.apply_auto_refresh_settings(True, 120)
                payload = json.loads(settings_file.read_text(encoding="utf-8"))

                self.assertEqual(payload["target"], cx_gui.WINDOWS_TARGET)
                self.assertEqual(payload["auto_refresh"], {"enabled": True, "interval_seconds": 120})
            finally:
                app.cancel_auto_refresh()
                root.destroy()

    def test_auto_refresh_tick_skips_while_busy_without_queueing_refresh(self) -> None:
        root, app = self.create_app()
        try:
            called: list[str] = []
            app.auto_refresh_enabled.set(True)
            app.auto_refresh_interval_seconds = 60
            app.busy_count = 1
            app.refresh_accounts = lambda **kwargs: called.append(kwargs.get("reason", "manual"))

            app.on_auto_refresh_tick()

            self.assertEqual(called, [])
            self.assertIsNotNone(app.auto_refresh_after_id)
            self.assertIn("Auto refresh skipped", app.status_var.get())
        finally:
            app.cancel_auto_refresh()
            root.destroy()

    def test_preview_rows_load_into_table(self) -> None:
        assert cx_gui is not None

        from cx_account_manager.gui_preview import sample_accounts
        from cx_account_manager.ui_theme import ACCOUNT_TREE_ROW_HEIGHT, ACCOUNT_TREE_STYLE, ACTION_BUTTON_STYLE, ACTION_MENUBUTTON_STYLE

        root, app = self.create_app()
        try:
            rows = sample_accounts()
            app.load_preview_accounts(rows)
            root.update()
            root.update_idletasks()

            self.assertEqual(len(app.tree.get_children()), len(rows))
            self.assertEqual(app.tree.cget("style"), ACCOUNT_TREE_STYLE)
            first_row_box = app.tree.bbox(app.tree.get_children()[0])
            self.assertGreaterEqual(first_row_box[3], ACCOUNT_TREE_ROW_HEIGHT - 2)
            self.assertTrue(app.tree.column("email", option="stretch"))
            self.assertTrue(app.tree.column("error", option="stretch"))
            self.assertEqual(app.busy_controls[0].cget("style"), ACTION_BUTTON_STYLE)
            self.assertEqual(app.busy_controls[4].cget("style"), ACTION_MENUBUTTON_STYLE)
            self.assertEqual(app.selection_controls["work"].cget("style"), ACTION_BUTTON_STYLE)
            self.assertEqual(app.status_var.get(), "Preview mode")
            self.assertEqual(app.selected_alias(), "michaelpo")
        finally:
            root.destroy()

    def test_z_preview_tree_style_applies_with_real_theme_factory(self) -> None:
        assert cx_gui is not None

        from cx_account_manager.gui_preview import sample_accounts
        from cx_account_manager.ui_theme import ACCOUNT_TREE_ROW_HEIGHT, ACCOUNT_TREE_STYLE

        try:
            root, theme_info, theme_tokens = cx_gui.create_root_and_theme(cx_gui.APP_TITLE)
        except cx_gui.TclError as exc:
            self.skipTest(f"Tk cannot start in this environment: {exc}")
        try:
            app = cx_gui.CxGui(root, theme_info=theme_info, theme_tokens=theme_tokens, preview_rows=sample_accounts())
            root.update()
            root.update_idletasks()

            self.assertEqual(app.tree.cget("style"), ACCOUNT_TREE_STYLE)
            first_row_box = app.tree.bbox(app.tree.get_children()[0])
            self.assertGreaterEqual(first_row_box[3], ACCOUNT_TREE_ROW_HEIGHT - 2)
        finally:
            root.destroy()


@unittest.skipUnless(HAS_TKINTER, "tkinter is not available in this Python environment")
class LoginDialogCopyTests(unittest.TestCase):
    class FakeRunner:
        @staticmethod
        def display_command(_target: str, args: list[str]) -> str:
            return "cx " + " ".join(args)

    def create_dialog(self):
        assert cx_gui is not None
        try:
            root = cx_gui.Tk()
        except cx_gui.TclError as exc:
            self.skipTest(f"Tk cannot start in this environment: {exc}")
        root.withdraw()
        original_start = cx_gui.LoginDialog.start
        cx_gui.LoginDialog.start = lambda self: None
        try:
            dialog = cx_gui.LoginDialog(root, self.FakeRunner(), cx_gui.WINDOWS_TARGET, "abc", False, lambda _exit_code: None)
        finally:
            cx_gui.LoginDialog.start = original_start
        return root, dialog

    def test_device_code_text_and_copy_label_share_copy_tag(self) -> None:
        root, dialog = self.create_dialog()
        try:
            dialog.append("Enter this one-time code\nV9MH-WCQ48\n")
            root.update_idletasks()

            code_start = dialog.output.search("V9MH-WCQ48", "1.0", "end")
            self.assertTrue(code_start)
            code_tags = set(dialog.output.tag_names(code_start))
            self.assertIn("copy", code_tags)

            copy_label_start = dialog.output.search("[", f"{code_start}+10c", "end")
            self.assertTrue(copy_label_start)
            copy_label_tags = set(dialog.output.tag_names(copy_label_start))
            self.assertIn("copy", copy_label_tags)
            self.assertTrue(any(tag.startswith("copy-") for tag in code_tags & copy_label_tags))
        finally:
            root.destroy()

    def test_copy_code_uses_parent_clipboard_and_trims_code(self) -> None:
        root, dialog = self.create_dialog()
        try:
            dialog.copy_code(" V9MH-WCQ48 ")

            self.assertEqual(root.clipboard_get(), "V9MH-WCQ48")
            self.assertEqual(dialog.status_var.get(), "Copied code: V9MH-WCQ48")
        finally:
            root.destroy()

    def test_ctrl_c_copy_selected_output(self) -> None:
        root, dialog = self.create_dialog()
        try:
            dialog.append("Enter this one-time code\nV9MH-WCQ48\n")
            code_start = dialog.output.search("V9MH-WCQ48", "1.0", "end")
            code_end = f"{code_start}+10c"
            dialog.output.tag_add("sel", code_start, code_end)

            result = dialog.copy_selected_output()

            self.assertEqual(result, "break")
            self.assertEqual(root.clipboard_get(), "V9MH-WCQ48")
            self.assertEqual(dialog.status_var.get(), "Copied selected text")
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
