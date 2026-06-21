from __future__ import annotations

import threading
from typing import Any, Callable

_RENEW_PATCH_ATTR = "_cx_renew_selection_state_patched"
_UPDATE_PATCH_ATTR = "_cx_update_check_status_patched"
_MANUAL_UPDATE_TIMEOUT_SECONDS = 20
_AUTO_UPDATE_TIMEOUT_SECONDS = 10


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
    """Make update checks easier to diagnose and less likely to false-timeout.

    The built-in update-check flow used a fixed 5-second urllib timeout and left
    the status bar on "Checking for updates" after failures. Manual checks now
    get a longer timeout and clearer error details, while automatic checks stay
    quiet and return the status bar to Ready on failure.
    """

    cx_gui = gui_app.CxGui
    original_finish: Callable[..., Any] = cx_gui.finish_update_check
    if getattr(original_finish, _UPDATE_PATCH_ATTR, False):
        return

    def fetch_update_check_result_with_timeout(timeout_seconds: int) -> Any:
        request = gui_app.urlrequest.Request(
            gui_app.UPDATE_CHECK_LATEST_RELEASE_URL,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": f"{gui_app.APP_TITLE}/{gui_app.__version__}",
            },
        )
        try:
            with gui_app.urlrequest.urlopen(request, timeout=timeout_seconds) as response:
                payload = gui_app.json.loads(response.read().decode("utf-8"))
        except gui_app.urlerror.HTTPError as exc:
            return gui_app.UpdateCheckResult(ok=False, error=f"HTTP {exc.code} {exc.reason}")
        except gui_app.urlerror.URLError as exc:
            reason = getattr(exc, "reason", None)
            return gui_app.UpdateCheckResult(ok=False, error=f"URLError: {reason or exc}")
        except TimeoutError:
            return gui_app.UpdateCheckResult(ok=False, error=f"TimeoutError: timed out after {timeout_seconds} seconds")
        except (gui_app.json.JSONDecodeError, UnicodeDecodeError) as exc:
            return gui_app.UpdateCheckResult(ok=False, error=f"{type(exc).__name__}: {exc}")
        except OSError as exc:
            return gui_app.UpdateCheckResult(ok=False, error=f"{type(exc).__name__}: {exc}")

        if not isinstance(payload, dict):
            return gui_app.UpdateCheckResult(ok=False, error="Release response was not a JSON object")

        latest_version = gui_app.normalize_release_version(payload.get("tag_name"))
        if latest_version is None:
            return gui_app.UpdateCheckResult(ok=False, error="Release tag is missing or invalid")

        release_url = payload.get("html_url")
        if not isinstance(release_url, str) or not release_url.strip():
            release_url = gui_app.UPDATE_CHECK_LATEST_RELEASE_URL

        local_version = gui_app.normalize_release_version(gui_app.__version__)
        if local_version is None:
            return gui_app.UpdateCheckResult(ok=False, error=f"Local version is invalid: {gui_app.__version__}")

        is_newer = gui_app.is_remote_version_newer(local_version, latest_version)
        return gui_app.UpdateCheckResult(ok=True, latest_version=latest_version, release_url=release_url, is_newer=is_newer)

    def patched_run_update_check(self: Any, *, manual: bool, force: bool) -> None:
        self.update_check_running = True
        timeout_seconds = _MANUAL_UPDATE_TIMEOUT_SECONDS if manual else _AUTO_UPDATE_TIMEOUT_SECONDS
        if manual:
            self.set_busy("Checking for updates")

        def worker() -> None:
            result = fetch_update_check_result_with_timeout(timeout_seconds)
            self.root.after(0, lambda: self.finish_update_check(result, manual=manual, force=force))

        threading.Thread(target=worker, daemon=True).start()

    def patched_finish_update_check(self: Any, result: Any, *, manual: bool, force: bool) -> Any:
        original_result = original_finish(self, result, manual=manual, force=force)
        if not getattr(result, "ok", False):
            error = getattr(result, "error", None) or "unknown error"
            if manual:
                self.set_busy("Update check failed")
                gui_app.messagebox.showerror(gui_app.APP_TITLE, f"Update check failed:\n{error}", parent=self.root)
            else:
                self.set_busy("Ready")
        return original_result

    setattr(patched_finish_update_check, _UPDATE_PATCH_ATTR, True)
    cx_gui.run_update_check = patched_run_update_check
    cx_gui.finish_update_check = patched_finish_update_check
