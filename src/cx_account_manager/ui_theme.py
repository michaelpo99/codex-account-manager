from __future__ import annotations

import sys
from dataclasses import dataclass
from importlib import import_module
from tkinter import TclError, Tk, font as tkfont, ttk
from typing import Any, Callable


@dataclass(frozen=True)
class ThemeInfo:
    engine: str
    name: str
    available: bool


@dataclass(frozen=True)
class ThemeTokens:
    bg: str
    surface: str
    surface_alt: str
    surface_raised: str
    border: str
    border_soft: str
    text: str
    text_secondary: str
    text_muted: str
    text_disabled: str
    primary: str
    primary_hover: str
    primary_soft: str
    primary_border: str
    primary_text: str
    success: str
    success_soft: str
    success_border: str
    warning: str
    warning_soft: str
    warning_border: str
    danger: str
    danger_soft: str
    danger_border: str
    info: str
    info_soft: str
    info_border: str
    table_bg: str
    table_header_bg: str
    table_header_fg: str
    table_row_alt: str
    selected_bg: str
    current_bg: str
    error_bg: str
    error_fg: str
    activity_strip_bg: str
    activity_muted: str
    activity_error: str
    activity_warning: str
    activity_success: str
    log_bg: str
    log_text: str


def fallback_theme_info() -> ThemeInfo:
    return ThemeInfo(engine="ttk", name="standard", available=False)


def enterprise_light_tokens() -> ThemeTokens:
    return ThemeTokens(
        bg="#F6F8FB",
        surface="#FFFFFF",
        surface_alt="#F8FAFC",
        surface_raised="#FFFFFF",
        border="#D9E1EA",
        border_soft="#E6ECF2",
        text="#111827",
        text_secondary="#374151",
        text_muted="#6B7280",
        text_disabled="#9CA3AF",
        primary="#2563EB",
        primary_hover="#1D4ED8",
        primary_soft="#EFF6FF",
        primary_border="#BFDBFE",
        primary_text="#FFFFFF",
        success="#16A34A",
        success_soft="#ECFDF3",
        success_border="#BBF7D0",
        warning="#D97706",
        warning_soft="#FFFBEB",
        warning_border="#FDE68A",
        danger="#DC2626",
        danger_soft="#FEF2F2",
        danger_border="#FECACA",
        info="#0284C7",
        info_soft="#F0F9FF",
        info_border="#BAE6FD",
        table_bg="#FFFFFF",
        table_header_bg="#F1F5F9",
        table_header_fg="#334155",
        table_row_alt="#FAFCFE",
        selected_bg="#DBEAFE",
        current_bg="#EFF6FF",
        error_bg="#FEF2F2",
        error_fg="#B91C1C",
        activity_strip_bg="#F8FAFC",
        activity_muted="#94A3B8",
        activity_error="#FCA5A5",
        activity_warning="#FCD34D",
        activity_success="#86EFAC",
        log_bg="#0F172A",
        log_text="#E5E7EB",
    )


def detect_theme_info(importer: Callable[[str], Any] = import_module) -> ThemeInfo:
    try:
        importer("ttkbootstrap")
    except Exception:
        return fallback_theme_info()
    return ThemeInfo(engine="ttkbootstrap", name="flatly", available=True)


def create_root_and_theme(title: str) -> tuple[Tk, ThemeInfo, ThemeTokens]:
    tokens = enterprise_light_tokens()
    try:
        tb = import_module("ttkbootstrap")
        root = tb.Window(themename="flatly")
        root.title(title)
        return root, ThemeInfo(engine="ttkbootstrap", name="flatly", available=True), tokens
    except Exception:
        root = Tk()
        root.title(title)
        return root, fallback_theme_info(), tokens


def theme_install_hint(prefix: str | None = None) -> str:
    if is_pipx_environment(prefix):
        return "Modern GUI theme unavailable. Install it with: pipx inject cx-account-manager ttkbootstrap"
    return "Modern GUI theme unavailable. Install it with: python -m pip install ttkbootstrap"


def is_pipx_environment(prefix: str | None = None) -> bool:
    value = (prefix or sys.prefix).replace("/", "\\").lower()
    return "\\pipx\\venvs\\" in value or value.endswith("\\pipx")


def themed_widget_class(widget_name: str, fallback_class: type[Any], theme_info: ThemeInfo) -> type[Any]:
    if theme_info.engine != "ttkbootstrap":
        return fallback_class
    try:
        tb = import_module("ttkbootstrap")
    except Exception:
        return fallback_class
    widget_class = getattr(tb, widget_name, None)
    if isinstance(widget_class, type):
        return widget_class
    return fallback_class


def button_style_kwargs(role: str, theme_info: ThemeInfo) -> dict[str, str]:
    role_key = role.lower().replace("_", "-")
    bootstrap_styles = {
        "primary": "primary",
        "secondary": "secondary-outline",
        "danger": "danger-outline",
        "ghost": "link",
    }
    ttk_styles = {
        "primary": "Primary.TButton",
        "secondary": "Secondary.TButton",
        "danger": "Danger.TButton",
        "ghost": "Ghost.TButton",
    }
    if theme_info.engine == "ttkbootstrap":
        return {"bootstyle": bootstrap_styles.get(role_key, "secondary-outline")}
    return {"style": ttk_styles.get(role_key, "Secondary.TButton")}


def menubutton_style_kwargs(role: str, theme_info: ThemeInfo) -> dict[str, str]:
    kwargs = button_style_kwargs(role, theme_info)
    style = kwargs.get("style")
    if style:
        return {"style": style.replace(".TButton", ".TMenubutton")}
    return kwargs


def style_status_badge(status: str) -> str:
    normalized = status.strip().lower()
    mapping = {
        "current": "Badge.Current.TLabel",
        "work": "Badge.Work.TLabel",
        "personal": "Badge.Personal.TLabel",
        "ok": "Badge.OK.TLabel",
        "warning": "Badge.Warning.TLabel",
        "error": "Badge.Error.TLabel",
        "skipped": "Badge.Skipped.TLabel",
    }
    return mapping.get(normalized, "Badge.Skipped.TLabel")


def format_font_tokens(root: Tk) -> dict[str, object]:
    family = _first_available_family(root, _body_font_candidates(), "Arial")
    mono = _first_available_family(root, ("Cascadia Mono", "Consolas", "DejaVu Sans Mono", "Courier New"), "Courier New")
    return {
        "app_title": (family, 12, "bold"),
        "section_title": (family, 10, "bold"),
        "body": (family, 10),
        "body_small": (family, 9),
        "table_cell": (family, 10),
        "table_alias": (family, 10, "bold"),
        "badge": (family, 9, "bold"),
        "log": (mono, 10),
    }


def configure_enterprise_styles(root: Tk, tokens: ThemeTokens) -> None:
    fonts = format_font_tokens(root)
    style = ttk.Style(root)
    _try_configure(root, background=tokens.bg)

    _safe_style_configure(style, ".", font=fonts["body"], background=tokens.bg, foreground=tokens.text)
    _safe_style_configure(style, "App.TFrame", background=tokens.bg)
    _safe_style_configure(style, "Surface.TFrame", background=tokens.surface)
    _safe_style_configure(style, "TopBar.TFrame", background=tokens.surface)
    _safe_style_configure(style, "Context.TFrame", background=tokens.primary_soft)
    _safe_style_configure(style, "Activity.TFrame", background=tokens.activity_strip_bg)
    _safe_style_configure(style, "Dialog.TFrame", background=tokens.surface)

    _safe_style_configure(style, "App.TLabel", background=tokens.bg, foreground=tokens.text, font=fonts["body"])
    _safe_style_configure(style, "Title.TLabel", background=tokens.surface, foreground=tokens.text, font=fonts["app_title"])
    _safe_style_configure(style, "Muted.TLabel", background=tokens.activity_strip_bg, foreground=tokens.text_muted, font=fonts["body_small"])
    _safe_style_configure(style, "Status.TLabel", background=tokens.surface, foreground=tokens.text_muted, font=fonts["body_small"])
    _safe_style_configure(style, "Context.TLabel", background=tokens.primary_soft, foreground=tokens.text_secondary, font=fonts["body"])
    _safe_style_configure(style, "AuthEnvironment.TLabel", background=tokens.surface, foreground=tokens.text, font=fonts["section_title"])
    _safe_style_configure(style, "DoctorTitle.TLabel", background=tokens.surface, foreground=tokens.text, font=fonts["app_title"])
    _safe_style_configure(style, "DoctorMeta.TLabel", background=tokens.surface, foreground=tokens.text_secondary, font=fonts["body"])

    button_padding = (10, 5)
    _safe_style_configure(style, "Primary.TButton", padding=button_padding, font=fonts["body"], foreground=tokens.primary_text, background=tokens.primary)
    _safe_style_map(style, "Primary.TButton", background=[("active", tokens.primary_hover), ("disabled", tokens.border_soft)], foreground=[("disabled", tokens.text_disabled)])
    _safe_style_configure(style, "Secondary.TButton", padding=button_padding, font=fonts["body"], foreground=tokens.text_secondary, background=tokens.surface_alt)
    _safe_style_map(style, "Secondary.TButton", background=[("active", tokens.primary_soft), ("disabled", tokens.surface_alt)], foreground=[("disabled", tokens.text_disabled)])
    _safe_style_configure(style, "Danger.TButton", padding=button_padding, font=fonts["body"], foreground=tokens.danger, background=tokens.surface)
    _safe_style_map(style, "Danger.TButton", background=[("active", tokens.danger_soft), ("disabled", tokens.surface_alt)], foreground=[("disabled", tokens.text_disabled)])
    _safe_style_configure(style, "Ghost.TButton", padding=(6, 4), font=fonts["body_small"], foreground=tokens.primary, background=tokens.activity_strip_bg)
    _safe_style_map(style, "Ghost.TButton", background=[("active", tokens.primary_soft)], foreground=[("disabled", tokens.text_disabled)])
    _safe_style_configure(style, "Primary.TMenubutton", padding=button_padding, font=fonts["body"], foreground=tokens.primary_text, background=tokens.primary)
    _safe_style_configure(style, "Secondary.TMenubutton", padding=button_padding, font=fonts["body"], foreground=tokens.text_secondary, background=tokens.surface_alt)
    _safe_style_configure(style, "Danger.TMenubutton", padding=button_padding, font=fonts["body"], foreground=tokens.danger, background=tokens.surface)
    _safe_style_configure(style, "Ghost.TMenubutton", padding=(6, 4), font=fonts["body_small"], foreground=tokens.primary, background=tokens.activity_strip_bg)

    _safe_style_configure(style, "AuthEnvironment.TCombobox", font=fonts["body"])
    _safe_style_configure(style, "Treeview", rowheight=46, font=fonts["table_cell"], background=tokens.table_bg, fieldbackground=tokens.table_bg, foreground=tokens.text)
    _safe_style_configure(style, "Treeview.Heading", font=fonts["section_title"], background=tokens.table_header_bg, foreground=tokens.table_header_fg, relief="flat")
    _safe_style_map(style, "Treeview", background=[("selected", tokens.selected_bg)], foreground=[("selected", tokens.text)])

    _safe_style_configure(style, "Badge.Current.TLabel", padding=(6, 2), font=fonts["badge"], background=tokens.primary_soft, foreground=tokens.primary)
    _safe_style_configure(style, "Badge.Work.TLabel", padding=(6, 2), font=fonts["badge"], background=tokens.info_soft, foreground=tokens.info)
    _safe_style_configure(style, "Badge.Personal.TLabel", padding=(6, 2), font=fonts["badge"], background=tokens.success_soft, foreground=tokens.success)
    _safe_style_configure(style, "Badge.OK.TLabel", padding=(6, 2), font=fonts["badge"], background=tokens.success_soft, foreground=tokens.success)
    _safe_style_configure(style, "Badge.Warning.TLabel", padding=(6, 2), font=fonts["badge"], background=tokens.warning_soft, foreground=tokens.warning)
    _safe_style_configure(style, "Badge.Error.TLabel", padding=(6, 2), font=fonts["badge"], background=tokens.danger_soft, foreground=tokens.danger)
    _safe_style_configure(style, "Badge.Skipped.TLabel", padding=(6, 2), font=fonts["badge"], background=tokens.surface_alt, foreground=tokens.text_muted)


def _body_font_candidates() -> tuple[str, ...]:
    if sys.platform.startswith("win"):
        return ("Segoe UI", "Microsoft JhengHei UI", "Microsoft JhengHei", "Arial")
    return ("Noto Sans CJK TC", "Noto Sans CJK", "DejaVu Sans", "Arial")


def _first_available_family(root: Tk, candidates: tuple[str, ...], fallback: str) -> str:
    try:
        available = {family.lower(): family for family in tkfont.families(root)}
    except TclError:
        available = {}
    for candidate in candidates:
        found = available.get(candidate.lower())
        if found:
            return found
    return fallback


def _safe_style_configure(style: ttk.Style, name: str, **options: object) -> None:
    try:
        style.configure(name, **options)
    except TclError:
        pass


def _safe_style_map(style: ttk.Style, name: str, **options: object) -> None:
    try:
        style.map(name, **options)
    except TclError:
        pass


def _try_configure(widget: Any, **options: object) -> None:
    try:
        widget.configure(**options)
    except TclError:
        pass
