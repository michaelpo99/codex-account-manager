from __future__ import annotations

import contextlib
import importlib
import importlib.util
import io
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

CX_PATH = SRC / "cx.py"
SPEC = importlib.util.spec_from_file_location("cx", CX_PATH)
assert SPEC is not None
cx = importlib.util.module_from_spec(SPEC)
sys.modules["cx"] = cx
assert SPEC.loader is not None
SPEC.loader.exec_module(cx)


class PackageEntrypointTests(unittest.TestCase):
    def test_cli_entrypoint_exports_main(self) -> None:
        module = importlib.import_module("cx_account_manager.cli")

        self.assertTrue(callable(module.main))

    def test_gui_entrypoint_exports_main_without_importing_tkinter(self) -> None:
        module = importlib.import_module("cx_account_manager.gui")

        self.assertTrue(callable(module.main))

    def test_version_flag_outputs_package_version(self) -> None:
        stdout = io.StringIO()
        with self.assertRaises(SystemExit) as raised, contextlib.redirect_stdout(stdout):
            cx.build_parser().parse_args(["--version"])

        self.assertEqual(raised.exception.code, 0)
        self.assertEqual(stdout.getvalue().strip(), "cx 0.1.0")


if __name__ == "__main__":
    unittest.main()
