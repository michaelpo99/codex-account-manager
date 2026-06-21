from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CX_PATH = ROOT / "src" / "cx.py"
SPEC = importlib.util.spec_from_file_location("cx", CX_PATH)
assert SPEC is not None
cx = importlib.util.module_from_spec(SPEC)
sys.modules["cx"] = cx
assert SPEC.loader is not None
SPEC.loader.exec_module(cx)


class ManualTests(unittest.TestCase):
    def test_build_manual_defaults_to_traditional_chinese_markdown(self) -> None:
        output = cx.build_manual("zh-TW", "markdown")

        self.assertIn("# cx 操作手冊", output)
        self.assertIn("## AI 使用指引", output)
        self.assertIn("1. 用 `cx add` 或 `cx save` 把帳號收進來。", output)
        self.assertIn("3. 用 `cx status` 看排序與額度，或直接用 `cx best` 自動切換。", output)
        self.assertIn("cx export --alias company --email me@example.com", output)

    def test_build_manual_supports_english(self) -> None:
        output = cx.build_manual("en", "markdown")

        self.assertIn("# cx Manual", output)
        self.assertIn("## AI Usage Guide", output)
        self.assertIn("Natural Language to Command Examples", output)
        self.assertIn("cx status company", output)

    def test_cmd_manual_prints_markdown(self) -> None:
        args = argparse.Namespace(lang="zh-TW", format="markdown")
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = cx.cmd_manual(args)

        self.assertEqual(exit_code, 0)
        self.assertTrue(stdout.getvalue().startswith("# cx 操作手冊"))

    def test_parser_registers_manual_command(self) -> None:
        parser = cx.build_parser()

        args = parser.parse_args(["manual", "--lang", "en", "--format", "markdown"])

        self.assertEqual(args.lang, "en")
        self.assertEqual(args.format, "markdown")
        self.assertIs(args.func, cx.cmd_manual)

    def test_manual_mentions_all_core_commands(self) -> None:
        output = cx.build_manual("zh-TW", "markdown")

        for command in [
            "add",
            "save",
            "renew",
            "list",
            "use",
            "current",
            "scope",
            "status",
            "best",
            "export",
            "import",
            "backup-list",
            "remove",
        ]:
            self.assertIn(f"### `cx {command}`", output)


if __name__ == "__main__":
    unittest.main()
