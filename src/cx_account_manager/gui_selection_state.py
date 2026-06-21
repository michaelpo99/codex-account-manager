from __future__ import annotations

from typing import Any, Callable

_PATCH_ATTR = "_cx_renew_selection_state_patched"


def install_renew_selection_state_patch(gui_app: Any) -> None:
    """Ensure Renew follows single-selection enablement rules.

    CR-008 requires Renew to be disabled when zero or multiple accounts are
    selected. The context menu already follows the single-selection rule, but
    the contextual action-bar button can stay enabled if the selection handler
    does not explicitly update the `renew` control. This patch keeps Renew in
    sync with Use: enabled only for exactly one selected account and only when
    the GUI is not busy.
    """

    cx_gui = gui_app.CxGui
    original: Callable[..., Any] = cx_gui.on_selection_changed
    if getattr(original, _PATCH_ATTR, False):
        return

    def patched_on_selection_changed(self: Any, _event: object | None = None) -> Any:
        result = original(self, _event)
        count = len(self.selected_aliases())
        single = count == 1 and self.busy_count == 0
        self.set_control_state("renew", single)
        if hasattr(self, "context_menu"):
            self.update_context_menu_state(count)
        return result

    setattr(patched_on_selection_changed, _PATCH_ATTR, True)
    cx_gui.on_selection_changed = patched_on_selection_changed
