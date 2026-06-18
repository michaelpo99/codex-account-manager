from __future__ import annotations


def main() -> int:
    try:
        from cx_account_manager.gui_app import main as gui_main
    except ImportError as exc:
        print(
            "cx-gui: Tkinter or the GUI module is not available in this Python environment.\n"
            "Please install Python with Tkinter support, or use the CLI command `cx`.",
        )
        print(f"Details: {exc}")
        return 1
    return gui_main()


__all__ = ["main"]
