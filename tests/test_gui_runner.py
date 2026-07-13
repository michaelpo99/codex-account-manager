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
        request_backup_sync_check = cx_gui.CxGui.request_backup_sync_check
        cx_gui.CxGui.refresh_accounts = lambda self, **_kwargs: None
        cx_gui.CxGui.detect_environment_values = staticmethod(lambda: [cx_gui.WINDOWS_TARGET])
        cx_gui.CxGui.request_backup_sync_check = lambda self, _trigger: None
        try:
            app = cx_gui.CxGui(root)
        finally:
            cx_gui.CxGui.refresh_accounts = refresh_accounts
            cx_gui.CxGui.detect_environment_values = staticmethod(detect_environment_values)
            cx_gui.CxGui.request_backup_sync_check = request_backup_sync_check
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

        self.assertEqual(cx_gui.CxGui.format_limit(3), "97%")
        self.assertEqual(cx_gui.CxGui.format_limit_reset("2026-06-19 23:58"), "06-19 23:58")
        self.assertEqual(cx_gui.CxGui.format_limit_reset(None), "n/a")
        self.assertEqual(cx_gui.CxGui.format_reset_credits(3, ["2026-07-18 00:00", "2026-07-27 00:00"]), "3 (07-18 00:00, 07-27 00:00)")
        self.assertEqual(cx_gui.CxGui.format_reset_credits(None, None), "")

    def test_reset_credit_tooltip_lists_all_expirations(self) -> None:
        assert cx_gui is not None
        row = cx_gui.AccountRow(
            alias="company",
            reset_credits_available=3,
            reset_credit_expires=["2026-07-18 00:00", "2026-07-27 00:00", "2026-08-01 00:00"],
        )
        app = object.__new__(cx_gui.CxGui)
        app.accounts = {row.alias: row}

        self.assertEqual(
            app.reset_credits_tooltip_text("company"),
            "Usage limit resets: 3 available\n\nExpires:\n- 2026-07-18 00:00\n- 2026-07-27 00:00\n- 2026-08-01 00:00",
        )

    def test_auto_refresh_interval_normalization(self) -> None:
        assert cx_gui is not None

        self.assertEqual(cx_gui.normalize_auto_refresh_interval("0"), (0, None))
        self.assertEqual(cx_gui.normalize_auto_refresh_interval("300"), (300, None))
        self.assertEqual(cx_gui.normalize_auto_refresh_interval("30")[0], 60)
        self.assertEqual(cx_gui.normalize_auto_refresh_interval("7200")[0], 3600)
        with self.assertRaises(ValueError):
            cx_gui.normalize_auto_refresh_interval("five")

    def test_backup_sync_interval_normalization(self) -> None:
        assert cx_gui is not None

        self.assertEqual(cx_gui.normalize_backup_sync_interval("0"), (0, None))
        self.assertEqual(cx_gui.normalize_backup_sync_interval("300"), (300, None))
        self.assertEqual(cx_gui.normalize_backup_sync_interval("30")[0], 60)
        self.assertEqual(cx_gui.normalize_backup_sync_interval("7200")[0], 3600)
        with self.assertRaises(ValueError):
            cx_gui.normalize_backup_sync_interval("oops")

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

    def test_gui_settings_preserve_target_when_saving_backup_sync(self) -> None:
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
                app.request_backup_sync_check = lambda _trigger: None
                app.apply_backup_sync_settings(True, r"D:\sync\cx", 120, True, True, False, True)
                payload = json.loads(settings_file.read_text(encoding="utf-8"))

                self.assertEqual(payload["target"], cx_gui.WINDOWS_TARGET)
                self.assertEqual(
                    payload["backup_sync"],
                    {
                        "enabled": True,
                        "directory": r"D:\sync\cx",
                        "interval_seconds": 120,
                        "import_new_accounts": True,
                        "overwrite_existing_accounts": True,
                        "allow_legacy_overwrite": False,
                        "rollback_before_overwrite": True,
                    },
                )
            finally:
                app.cancel_backup_sync()
                root.destroy()

    def test_backup_sync_args_use_target_path_and_flags(self) -> None:
        assert cx_gui is not None

        root, app = self.create_app()
        try:
            app.backup_sync_settings = cx_gui.BackupSyncSettings(
                enabled=True,
                directory=r"D:\sync\cx",
                interval_seconds=300,
                import_new_accounts=False,
                overwrite_existing_accounts=False,
                allow_legacy_overwrite=True,
                rollback_before_overwrite=False,
            )

            args = app.backup_sync_args("WSL: Ubuntu-22.04")

            self.assertEqual(args[:5], ["sync-import", "--dir", "/mnt/d/sync/cx", "--apply", "--json"])
            self.assertIn("--no-import-new", args)
            self.assertIn("--no-overwrite-existing", args)
            self.assertIn("--allow-legacy-overwrite", args)
            self.assertIn("--no-rollback", args)
        finally:
            root.destroy()

    def test_run_backup_sync_skips_when_directory_is_not_visible_in_wsl(self) -> None:
        assert cx_gui is not None

        root, app = self.create_app()
        try:
            app.target_var.set("WSL: Ubuntu-22.04")
            app.backup_sync_settings = cx_gui.BackupSyncSettings(
                enabled=True,
                directory=r"I:\missing-drive\folder",
                interval_seconds=300,
            )
            calls: list[tuple[str, list[str], int]] = []
            app.runner.target_directory_exists = lambda target, path: (False, None)
            app.runner.run = lambda target, args, timeout=0: calls.append((target, args, timeout))  # type: ignore[assignment]

            app.run_backup_sync("target")

            self.assertEqual(calls, [])
            self.assertIn("directory not accessible in target", app.status_var.get())
        finally:
            app.cancel_backup_sync()
            root.destroy()

    def test_manual_backup_sync_requires_configured_folder(self) -> None:
        assert cx_gui is not None

        root, app = self.create_app()
        original_showinfo = cx_gui.messagebox.showinfo
        try:
            app.backup_sync_settings = cx_gui.BackupSyncSettings(enabled=False, directory="", interval_seconds=300)
            prompts: list[str] = []
            cx_gui.messagebox.showinfo = lambda title, message, parent=None: prompts.append(message)  # type: ignore[assignment]

            app.run_manual_backup_sync()

            self.assertEqual(prompts, ["Backup sync folder is not set. Open Settings to choose a folder first."])
        finally:
            cx_gui.messagebox.showinfo = original_showinfo  # type: ignore[assignment]
            app.cancel_backup_sync()
            root.destroy()

    def test_manual_backup_sync_shows_error_when_directory_is_not_accessible(self) -> None:
        assert cx_gui is not None

        root, app = self.create_app()
        original_showerror = cx_gui.messagebox.showerror
        try:
            app.target_var.set("WSL: Ubuntu-22.04")
            app.backup_sync_settings = cx_gui.BackupSyncSettings(enabled=False, directory=r"I:\missing-drive\folder", interval_seconds=300)
            app.runner.target_directory_exists = lambda target, path: (False, "mount missing")
            prompts: list[str] = []
            cx_gui.messagebox.showerror = lambda title, message, parent=None: prompts.append(message)  # type: ignore[assignment]

            app.run_manual_backup_sync()

            self.assertEqual(len(prompts), 1)
            self.assertIn("Backup sync folder is not accessible", prompts[0])
            self.assertIn("mount missing", prompts[0])
        finally:
            cx_gui.messagebox.showerror = original_showerror  # type: ignore[assignment]
            app.cancel_backup_sync()
            root.destroy()

    def test_manual_backup_sync_runs_even_when_scheduled_sync_is_disabled(self) -> None:
        assert cx_gui is not None

        root, app = self.create_app()
        original_thread = cx_gui.threading.Thread
        original_after = app.root.after
        try:
            app.backup_sync_settings = cx_gui.BackupSyncSettings(
                enabled=False,
                directory=r"D:\sync\cx",
                interval_seconds=300,
            )
            app.runner.target_directory_exists = lambda target, path: (True, None)
            run_calls: list[tuple[str, list[str], int]] = []
            app.runner.run = lambda target, args, timeout=0: run_calls.append((target, args, timeout)) or cx_gui.CommandResult(  # type: ignore[assignment]
                args,
                "cx sync-import",
                0,
                json.dumps({"directory": args[2], "actions": []}),
                "",
            )
            app.root.after = lambda _delay, callback: callback()  # type: ignore[assignment]

            class ImmediateThread:
                def __init__(self, target=None, daemon=None):
                    self._target = target

                def start(self) -> None:
                    if self._target is not None:
                        self._target()

            cx_gui.threading.Thread = ImmediateThread

            app.run_manual_backup_sync()

            self.assertEqual(len(run_calls), 1)
            expected_directory = app.runner.target_path(app.target_var.get(), r"D:\sync\cx")
            self.assertEqual(run_calls[0][1][:5], ["sync-import", "--dir", expected_directory, "--apply", "--json"])
            self.assertIn("Backup sync (manual)", app.output.get("1.0", "end"))
        finally:
            cx_gui.threading.Thread = original_thread
            app.root.after = original_after  # type: ignore[assignment]
            app.cancel_backup_sync()
            root.destroy()

    def test_run_backup_sync_stages_windows_directory_for_wsl_when_direct_path_is_unavailable(self) -> None:
        assert cx_gui is not None

        with tempfile.TemporaryDirectory() as tmpdir:
            archive = Path(tmpdir) / "cx-work-backup.tar.gz"
            archive.write_bytes(b"test-backup")

            root, app = self.create_app()
            original_thread = cx_gui.threading.Thread
            original_after = app.root.after
            try:
                app.target_var.set("WSL: Ubuntu-22.04")
                app.backup_sync_settings = cx_gui.BackupSyncSettings(
                    enabled=True,
                    directory=tmpdir,
                    interval_seconds=300,
                )
                app.runner.target_directory_exists = lambda target, path: (False, None)
                app.runner.stage_directory_for_wsl = lambda target, path: ("/tmp/cx-backup-sync/stage.123456", 1)  # type: ignore[assignment]
                cleanup_calls: list[tuple[str, str]] = []
                app.runner.cleanup_staged_directory = lambda target, directory: cleanup_calls.append((target, directory)) or None  # type: ignore[assignment]
                run_calls: list[tuple[str, list[str], int]] = []
                app.runner.run = lambda target, args, timeout=0: run_calls.append((target, args, timeout)) or cx_gui.CommandResult(  # type: ignore[assignment]
                    args,
                    "cx sync-import",
                    0,
                    json.dumps({"directory": args[2], "actions": []}),
                    "",
                )
                app.root.after = lambda _delay, callback: callback()  # type: ignore[assignment]

                class ImmediateThread:
                    def __init__(self, target=None, daemon=None):
                        self._target = target

                    def start(self) -> None:
                        if self._target is not None:
                            self._target()

                cx_gui.threading.Thread = ImmediateThread

                app.run_backup_sync("target")

                self.assertEqual(len(run_calls), 1)
                self.assertEqual(run_calls[0][1][:5], ["sync-import", "--dir", "/tmp/cx-backup-sync/stage.123456", "--apply", "--json"])
                self.assertEqual(cleanup_calls, [("WSL: Ubuntu-22.04", "/tmp/cx-backup-sync/stage.123456")])
                self.assertIn("mode=staged", app.output.get("1.0", "end"))
            finally:
                cx_gui.threading.Thread = original_thread
                app.root.after = original_after  # type: ignore[assignment]
                app.cancel_backup_sync()
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

    def test_open_rollback_folder_shows_wsl_path_in_activity(self) -> None:
        root, app = self.create_app()
        try:
            app.target_var.set("WSL: Ubuntu-22.04")

            app.open_rollback_folder()

            self.assertIn("/mnt/", app.output.get("1.0", "end"))
            self.assertIn("rollback", app.output.get("1.0", "end"))
            self.assertEqual(app.status_var.get(), "WSL rollback folder shown in Activity")
        finally:
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
            self.assertIn(ACTION_MENUBUTTON_STYLE, [control.cget("style") for control in app.busy_controls])
            self.assertEqual(app.selection_controls["work"].cget("style"), ACTION_BUTTON_STYLE)
            self.assertIn("Preview", app.root.title())
            self.assertEqual(app.selected_alias(), "michaelpo")
        finally:
            root.destroy()

    def test_preview_rows_expose_renew_button_and_menu_states(self) -> None:
        assert cx_gui is not None

        from cx_account_manager.gui_preview import sample_accounts
        from cx_account_manager.ui_theme import ACTION_BUTTON_STYLE

        root, app = self.create_app()
        try:
            app.load_preview_accounts(sample_accounts())
            root.update_idletasks()

            self.assertEqual(app.selection_controls["renew"].cget("style"), ACTION_BUTTON_STYLE)

            app.update_context_menu_state(1)
            self.assertEqual(app.context_menu.entrycget(0, "state"), "normal")
            self.assertEqual(app.context_menu.entrycget(1, "state"), "normal")
            self.assertEqual(app.context_menu.entrycget(2, "state"), "normal")
            self.assertEqual(app.context_menu.entrycget(3, "state"), "normal")
            self.assertEqual(app.context_menu.entrycget(4, "state"), "normal")

            app.update_context_menu_state(2)
            self.assertEqual(app.context_menu.entrycget(0, "state"), "disabled")
            self.assertEqual(app.context_menu.entrycget(1, "state"), "disabled")
            self.assertEqual(app.context_menu.entrycget(2, "state"), "disabled")
            self.assertEqual(app.context_menu.entrycget(3, "state"), "normal")
            self.assertEqual(app.context_menu.entrycget(4, "state"), "normal")
        finally:
            root.destroy()

    def test_renew_selected_prompts_with_expected_email_and_refreshes(self) -> None:
        assert cx_gui is not None

        from cx_account_manager.gui_preview import sample_accounts

        root, app = self.create_app()
        gui_module = sys.modules[cx_gui.CxGui.__module__]
        original_askyesno = cx_gui.messagebox.askyesno
        original_login_dialog = gui_module.LoginDialog
        original_ensure_windows_codex_bin = app.ensure_windows_codex_bin
        try:
            app.load_preview_accounts(sample_accounts())
            app.tree.selection_set("michaelpo")
            app.on_selection_changed()
            prompts: list[str] = []
            refresh_calls: list[dict[str, object]] = []
            login_calls: list[tuple[str, str, bool]] = []

            def fake_askyesno(*args, **kwargs):
                prompts.append(str(args[1]))
                return True

            class FakeLoginDialog:
                def __init__(
                    self,
                    parent,
                    runner,
                    target,
                    *,
                    command: str,
                    alias: str,
                    force: bool,
                    on_done,
                    theme_info=None,
                    theme_tokens=None,
                ) -> None:
                    login_calls.append((command, alias, force))
                    on_done(0)

            cx_gui.messagebox.askyesno = fake_askyesno
            gui_module.LoginDialog = FakeLoginDialog
            app.ensure_windows_codex_bin = lambda: True
            app.refresh_accounts = lambda **kwargs: refresh_calls.append(kwargs)

            app.renew_selected()

            self.assertTrue(prompts)
            self.assertIn("Renew `michaelpo`", prompts[0])
            self.assertIn("Expected email: michaelpo@fovatech.com", prompts[0])
            self.assertEqual(login_calls, [("renew", "michaelpo", False)])
            self.assertEqual(refresh_calls, [{}])
            self.assertEqual(app.post_refresh_status, "Renewed michaelpo")
            self.assertFalse(app.login_dialog_active)
            self.assertEqual(app.busy_count, 0)
        finally:
            cx_gui.messagebox.askyesno = original_askyesno
            gui_module.LoginDialog = original_login_dialog
            app.ensure_windows_codex_bin = original_ensure_windows_codex_bin
            root.destroy()

    def test_renew_selected_rejects_multiple_selection(self) -> None:
        assert cx_gui is not None

        from cx_account_manager.gui_preview import sample_accounts

        root, app = self.create_app()
        original_showinfo = cx_gui.messagebox.showinfo
        try:
            app.load_preview_accounts(sample_accounts())
            app.tree.selection_set(("fova3000", "michaelpo"))
            prompts: list[str] = []

            def fake_showinfo(*args, **kwargs):
                prompts.append(str(args[1]))

            cx_gui.messagebox.showinfo = fake_showinfo

            app.renew_selected()

            self.assertEqual(prompts, ["Renew supports one account at a time."])
        finally:
            cx_gui.messagebox.showinfo = original_showinfo
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
            dialog = cx_gui.LoginDialog(
                root,
                self.FakeRunner(),
                cx_gui.WINDOWS_TARGET,
                command="add",
                alias="abc",
                force=False,
                on_done=lambda _exit_code: None,
            )
        finally:
            cx_gui.LoginDialog.start = original_start
        return root, dialog

    def test_command_args_use_force_only_for_add(self) -> None:
        root, dialog = self.create_dialog()
        try:
            self.assertEqual(dialog.command_args(), ["add", "abc"])
        finally:
            root.destroy()

    def test_renew_command_args_skip_force_flag(self) -> None:
        assert cx_gui is not None
        try:
            root = cx_gui.Tk()
        except cx_gui.TclError as exc:
            self.skipTest(f"Tk cannot start in this environment: {exc}")
        root.withdraw()
        original_start = cx_gui.LoginDialog.start
        cx_gui.LoginDialog.start = lambda self: None
        try:
            dialog = cx_gui.LoginDialog(
                root,
                self.FakeRunner(),
                cx_gui.WINDOWS_TARGET,
                command="renew",
                alias="abc",
                force=False,
                on_done=lambda _exit_code: None,
            )
            self.assertEqual(dialog.command_args(), ["renew", "abc"])
        finally:
            cx_gui.LoginDialog.start = original_start
            root.destroy()

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
