from __future__ import annotations

from typing import Any, Callable

_RENEW_PATCH_ATTR = "_cx_renew_selection_state_patched"
_UPDATE_PATCH_ATTR = "_cx_update_check_status_patched"


def install_renew_selection_state_patch(gui_app: Any) -> None:
    """Install small GUI runtime patches that avoid large-file rewrites."""

    install_update_check_status_patch(gui_app)

    cx_gui = gui_app.CxGui
    original: Callable[..., Any] = cx_gui.on_selection_changed
    if getattr(original, _RENEW_PATCH_ATTR, False):
        return

    def patched_on_selection_changed(self: Any, _event: object | None = None) -> Any:
        result = original(self, _event)
        count = len(self.selected_aliases())
        single = count == 1 and self.busy_count == 0
        self.set_control_state("renew", single)
        if hasattr(self, "context_menu"):
            self.update_context_menu_state(count)
        return result

    setattr(patched_on_selection_changed, _RENEW_PATCH_ATTR, True)
    cx_gui.on_selection_changed = patched_on_selection_changed


def install_update_check_status_patch(gui_app: Any) -> None:
    """Avoid leaving the GUI stuck at "Checking for updates" after failures.

    The built-in update-check flow logs failures and returns early. That leaves
    the status bar on the previous "Checking for updates" message even though
    the background worker has completed. Automatic checks should fail quietly;
    manual checks should surface a clear failure message.
    """

    cx_gui = gui_app.CxGui
    original: Callable[..., Any] = cx_gui.finish_update_check
    if getattr(original, _UPDATE_PATCH_ATTR, False):
        return

    def patched_finish_update_check(self: Any, result: Any, *, manual: bool, force: bool) -> Any:
        original_result = original(self, result, manual=manual, force=force)
        if not getattr(result, "ok", False):
            error = getattr(result, "error", None) or "unknown error"
            if manual:
                self.set_busy("Update check failed")
                gui_app.messagebox.showerror(gui_app.APP_TITLE, f"Update check failed:\n{error}", parent=self.root)
            else:
                self.set_busy("Ready")
        return original_result

    setattr(patched_finish_update_check, _UPDATE_PATCH_ATTR, True)
    cx_gui.finish_update_check = patched_finish_update_check
