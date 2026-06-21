from __future__ import annotations


def main() -> int:
    try:
        from cx_account_manager import gui_app
        from cx_account_manager.gui_selection_state import install_renew_selection_state_patch
    except ImportError as exc:
        print(
            "cx-gui: Tkinter or the GUI module is not available in this Python environment.\n"
            "Please install Python with Tkinter support, or use the CLI command `cx`.",
        )
        print(f"Details: {exc}")
        return 1
    install_renew_selection_state_patch(gui_app)
    return gui_app.main()


__all__ = ["main"]
