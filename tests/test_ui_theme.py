from __future__ import annotations

import unittest
import sys
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cx_account_manager import ui_theme


class UiThemeTests(unittest.TestCase):
    def test_enterprise_light_tokens_include_required_values(self) -> None:
        tokens = ui_theme.enterprise_light_tokens()

        required = (
            "bg",
            "surface",
            "border_soft",
            "primary",
            "primary_soft",
            "success_soft",
            "warning_soft",
            "danger_soft",
            "table_header_bg",
            "selected_bg",
            "current_bg",
            "error_fg",
            "activity_strip_bg",
            "log_bg",
            "log_text",
        )
        for name in required:
            self.assertTrue(getattr(tokens, name), name)

    def test_detect_theme_info_falls_back_when_ttkbootstrap_is_missing(self) -> None:
        def importer(_name: str) -> object:
            raise ImportError("missing")

        theme_info = ui_theme.detect_theme_info(importer)

        self.assertEqual(theme_info.engine, "ttk")
        self.assertEqual(theme_info.name, "standard")
        self.assertFalse(theme_info.available)

    def test_detect_theme_info_uses_ttkbootstrap_when_available(self) -> None:
        theme_info = ui_theme.detect_theme_info(lambda _name: object())

        self.assertEqual(theme_info.engine, "ttkbootstrap")
        self.assertEqual(theme_info.name, "flatly")
        self.assertTrue(theme_info.available)

    def test_button_style_kwargs_use_owned_ttk_styles(self) -> None:
        bootstrap = ui_theme.ThemeInfo(engine="ttkbootstrap", name="flatly", available=True)
        fallback = ui_theme.fallback_theme_info()

        self.assertEqual(ui_theme.button_style_kwargs("primary", bootstrap), {"style": ui_theme.MAIN_BUTTON_STYLE})
        self.assertEqual(ui_theme.button_style_kwargs("secondary", bootstrap), {"style": ui_theme.ACTION_BUTTON_STYLE})
        self.assertEqual(ui_theme.button_style_kwargs("danger", fallback), {"style": ui_theme.WARN_BUTTON_STYLE})

    def test_menubutton_style_kwargs_use_tmenubutton_for_ttk_fallback(self) -> None:
        bootstrap = ui_theme.ThemeInfo(engine="ttkbootstrap", name="flatly", available=True)
        fallback = ui_theme.fallback_theme_info()

        self.assertEqual(ui_theme.menubutton_style_kwargs("secondary", bootstrap), {"style": ui_theme.ACTION_MENUBUTTON_STYLE})
        self.assertEqual(ui_theme.menubutton_style_kwargs("secondary", fallback), {"style": ui_theme.ACTION_MENUBUTTON_STYLE})

    def test_theme_install_hint_uses_python_command_outside_pipx(self) -> None:
        self.assertEqual(
            ui_theme.theme_install_hint(),
            "Modern GUI theme unavailable. Install it with: python -m pip install ttkbootstrap",
        )

    def test_theme_install_hint_uses_pipx_injection_inside_pipx(self) -> None:
        self.assertTrue(ui_theme.is_pipx_environment(r"C:\Users\demo\.local\pipx\venvs\cx-account-manager"))
        self.assertEqual(
            ui_theme.theme_install_hint(r"C:\Users\demo\.local\pipx\venvs\cx-account-manager"),
            "Modern GUI theme unavailable. Install it with: pipx inject cx-account-manager ttkbootstrap",
        )

    def test_style_status_badge_returns_stable_style_names(self) -> None:
        self.assertEqual(ui_theme.style_status_badge("OK"), "Badge.OK.TLabel")
        self.assertEqual(ui_theme.style_status_badge("warning"), "Badge.Warning.TLabel")
        self.assertEqual(ui_theme.style_status_badge("unknown"), "Badge.Skipped.TLabel")

    def test_create_root_and_theme_fallback_can_be_mocked_without_display(self) -> None:
        fake_root = mock.Mock()
        with mock.patch.object(ui_theme, "import_module", side_effect=ImportError("missing")):
            with mock.patch.object(ui_theme, "Tk", return_value=fake_root):
                root, theme_info, tokens = ui_theme.create_root_and_theme("cx")

        self.assertIs(root, fake_root)
        self.assertEqual(theme_info.engine, "ttk")
        self.assertFalse(theme_info.available)
        self.assertEqual(tokens.bg, "#F6F8FB")
        fake_root.title.assert_called_once_with("cx")

    def test_create_root_and_theme_uses_ttkbootstrap_window_when_available(self) -> None:
        fake_root = mock.Mock()
        fake_module = mock.Mock()
        fake_module.Window.return_value = fake_root

        with mock.patch.object(ui_theme, "import_module", return_value=fake_module):
            root, theme_info, tokens = ui_theme.create_root_and_theme("cx")

        self.assertIs(root, fake_root)
        self.assertEqual(theme_info.engine, "ttkbootstrap")
        self.assertTrue(theme_info.available)
        self.assertEqual(tokens.surface, "#FFFFFF")
        fake_module.Window.assert_called_once_with(themename="flatly")
        fake_root.title.assert_called_once_with("cx")

    def test_themed_widget_class_keeps_buttons_on_ttk_for_owned_styles(self) -> None:
        class FallbackButton:
            pass

        class BootstrapButton:
            pass

        fake_module = mock.Mock()
        fake_module.Button = BootstrapButton
        theme_info = ui_theme.ThemeInfo(engine="ttkbootstrap", name="flatly", available=True)

        with mock.patch.object(ui_theme, "import_module", return_value=fake_module):
            widget_class = ui_theme.themed_widget_class("Button", FallbackButton, theme_info)

        self.assertIs(widget_class, FallbackButton)

    def test_themed_widget_class_uses_bootstrap_class_for_other_widgets_when_available(self) -> None:
        class FallbackWidget:
            pass

        class BootstrapWidget:
            pass

        fake_module = mock.Mock()
        fake_module.Frame = BootstrapWidget
        theme_info = ui_theme.ThemeInfo(engine="ttkbootstrap", name="flatly", available=True)

        with mock.patch.object(ui_theme, "import_module", return_value=fake_module):
            widget_class = ui_theme.themed_widget_class("Frame", FallbackWidget, theme_info)

        self.assertIs(widget_class, BootstrapWidget)


if __name__ == "__main__":
    unittest.main()
