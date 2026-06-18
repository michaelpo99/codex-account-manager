from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from pathlib import Path, PurePosixPath, PureWindowsPath
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
CX_PATH = ROOT / "src" / "cx.py"
SPEC = importlib.util.spec_from_file_location("cx", CX_PATH)
assert SPEC is not None
cx = importlib.util.module_from_spec(SPEC)
sys.modules["cx"] = cx
assert SPEC.loader is not None
SPEC.loader.exec_module(cx)


class PlatformPathTests(unittest.TestCase):
    def test_default_data_dir_uses_localappdata_on_windows(self) -> None:
        with mock.patch.object(cx, "Path", PureWindowsPath):
            with mock.patch.object(cx.os, "name", "nt"):
                with mock.patch.dict(cx.os.environ, {"LOCALAPPDATA": r"C:\Users\demo\AppData\Local"}, clear=False):
                    self.assertEqual(cx.default_data_dir(), PureWindowsPath(r"C:\Users\demo\AppData\Local") / "cx")

    def test_default_data_dir_falls_back_to_appdata_local_without_env(self) -> None:
        class FakeWindowsPath(PureWindowsPath):
            @classmethod
            def home(cls) -> "FakeWindowsPath":
                return cls(r"C:\Users\demo")

        with mock.patch.object(cx, "Path", FakeWindowsPath):
            with mock.patch.object(cx.os, "name", "nt"):
                with mock.patch.dict(cx.os.environ, {}, clear=True):
                    self.assertEqual(cx.default_data_dir(), FakeWindowsPath(r"C:\Users\demo\AppData\Local\cx"))

    def test_default_data_dir_uses_xdg_style_location_on_posix(self) -> None:
        class FakePosixPath(PurePosixPath):
            @classmethod
            def home(cls) -> "FakePosixPath":
                return cls("/home/demo")

        with mock.patch.object(cx, "Path", FakePosixPath):
            with mock.patch.object(cx.os, "name", "posix"):
                self.assertEqual(cx.default_data_dir(), FakePosixPath("/home/demo/.local/share/cx"))

    def test_default_codex_home_prefers_environment_variable(self) -> None:
        custom = str(Path(os.sep) / "tmp" / "custom-codex-home")
        with mock.patch.dict(cx.os.environ, {"CODEX_HOME": custom}, clear=False):
            self.assertEqual(cx.default_codex_home(), Path(custom))

    def test_codex_executable_prefers_configured_binary(self) -> None:
        with mock.patch.dict(cx.os.environ, {"CX_CODEX_BIN": "custom-codex"}, clear=False):
            with mock.patch.object(cx.shutil, "which", return_value="/tools/custom-codex"):
                self.assertEqual(cx.codex_executable(), "/tools/custom-codex")

    def test_windows_codex_search_uses_extra_path_dirs(self) -> None:
        def fake_which(name: str, path: str | None = None) -> str | None:
            if name == "codex.cmd" and path and r"C:\Users\demo\AppData\Roaming\npm" in path:
                return r"C:\Users\demo\AppData\Roaming\npm\codex.cmd"
            return None

        with mock.patch.object(cx.os, "name", "nt"):
            with mock.patch.object(cx, "windows_extra_path_dirs", return_value=[r"C:\Users\demo\AppData\Roaming\npm"]):
                with mock.patch.object(cx, "windows_codex_candidates", return_value=[]):
                    with mock.patch.object(cx, "windows_npm_codex_candidates", return_value=[]):
                        with mock.patch.object(cx.shutil, "which", side_effect=fake_which):
                            self.assertEqual(cx.codex_executable(), r"C:\Users\demo\AppData\Roaming\npm\codex.cmd")

    def test_windows_cmd_codex_is_wrapped_with_comspec(self) -> None:
        with mock.patch.object(cx.os, "name", "nt"):
            with mock.patch.dict(cx.os.environ, {"COMSPEC": r"C:\Windows\System32\cmd.exe"}, clear=False):
                with mock.patch.object(cx, "codex_executable", return_value=r"C:\Users\demo\AppData\Roaming\npm\codex.cmd"):
                    self.assertEqual(
                        cx.codex_command(["app-server"]),
                        [r"C:\Windows\System32\cmd.exe", "/c", r"C:\Users\demo\AppData\Roaming\npm\codex.cmd", "app-server"],
                    )


if __name__ == "__main__":
    unittest.main()
