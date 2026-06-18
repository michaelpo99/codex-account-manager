from __future__ import annotations

import argparse
import importlib.util
import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
CX_PATH = ROOT / "src" / "cx.py"
SPEC = importlib.util.spec_from_file_location("cx", CX_PATH)
assert SPEC is not None
cx = importlib.util.module_from_spec(SPEC)
sys.modules["cx"] = cx
assert SPEC.loader is not None
SPEC.loader.exec_module(cx)


def capture_json(func, args: argparse.Namespace) -> dict[str, object]:
    output = io.StringIO()
    with redirect_stdout(output):
        exit_code = func(args)
    payload = json.loads(output.getvalue())
    payload["_exit_code"] = exit_code
    return payload


class JsonOutputTests(unittest.TestCase):
    def test_list_json_includes_current_and_scope(self) -> None:
        with mock.patch.object(cx, "list_aliases", return_value=["company", "personal"]):
            with mock.patch.object(cx, "read_current_alias", return_value="company"):
                with mock.patch.object(cx, "read_account_scope", side_effect=lambda alias: "work" if alias == "company" else "personal"):
                    payload = capture_json(cx.cmd_list, argparse.Namespace(json=True))

        self.assertEqual(payload["_exit_code"], 0)
        self.assertEqual(payload["current"], "company")
        self.assertEqual(
            payload["accounts"],
            [
                {"alias": "company", "current": True, "scope": "work"},
                {"alias": "personal", "current": False, "scope": "personal"},
            ],
        )

    def test_current_json_allows_empty_current(self) -> None:
        with mock.patch.object(cx, "read_current_alias", return_value=None):
            payload = capture_json(cx.cmd_current, argparse.Namespace(json=True))

        self.assertEqual(payload["_exit_code"], 0)
        self.assertIsNone(payload["current"])

    def test_status_json_includes_gui_fields_and_rank(self) -> None:
        statuses = [
            cx.AccountStatus(
                alias="company",
                scope="work",
                email="demo@example.com",
                plan="plus",
                primary_used=20,
                primary_reset="2026-06-18 18:00",
                primary_reset_at=1_800_000_000,
                secondary_used=30,
                secondary_reset="2026-06-20 18:00",
                secondary_reset_at=1_800_172_800,
            )
        ]

        with mock.patch.object(cx, "require_codex"):
            with mock.patch.object(cx, "ensure_layout"):
                with mock.patch.object(cx, "list_aliases", return_value=["company"]):
                    with mock.patch.object(cx, "read_current_alias", return_value="company"):
                        with mock.patch.object(cx, "read_status_for_alias", side_effect=statuses):
                            payload = capture_json(cx.cmd_status, argparse.Namespace(alias=None, json=True))

        self.assertEqual(payload["_exit_code"], 0)
        self.assertEqual(payload["current"], "company")
        self.assertEqual(payload["accounts"][0]["alias"], "company")
        self.assertEqual(payload["accounts"][0]["current"], True)
        self.assertEqual(payload["accounts"][0]["scope"], "work")
        self.assertEqual(payload["accounts"][0]["email"], "demo@example.com")
        self.assertEqual(payload["accounts"][0]["primary_used"], 20)
        self.assertEqual(payload["accounts"][0]["rank"], 1)


if __name__ == "__main__":
    unittest.main()
