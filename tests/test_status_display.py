from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import sys
import unittest
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


def account(
    alias: str,
    *,
    primary_used: int | None,
    secondary_used: int | None,
) -> cx.AccountStatus:
    return cx.AccountStatus(
        alias=alias,
        scope="work",
        email="demo@example.com",
        plan="business",
        primary_used=primary_used,
        primary_reset="2026-06-25 13:51",
        primary_reset_at=1_800_000_000,
        secondary_used=secondary_used,
        secondary_reset="2026-07-02 10:19",
        secondary_reset_at=1_800_604_800,
    )


class StatusDisplayTests(unittest.TestCase):
    def test_status_human_output_uses_left_percent(self) -> None:
        statuses = [account("company", primary_used=15, secondary_used=2)]
        output = io.StringIO()

        with mock.patch.object(cx, "require_codex"), mock.patch.object(cx, "ensure_layout"), mock.patch.object(
            cx, "list_aliases", return_value=["company"]
        ), mock.patch.object(cx, "read_current_alias", return_value="company"), mock.patch.object(
            cx, "read_status_for_alias", side_effect=statuses
        ), contextlib.redirect_stdout(output):
            result = cx.cmd_status(argparse.Namespace(alias=None, json=False))

        text = output.getvalue()
        self.assertEqual(result, 0)
        self.assertIn("5h: 85% left | reset 2026-06-25 13:51", text)
        self.assertIn("7d: 98% left | reset 2026-07-02 10:19", text)
        self.assertNotIn("% used", text)

    def test_best_human_output_uses_left_percent(self) -> None:
        statuses = {"company": account("company", primary_used=15, secondary_used=2)}
        output = io.StringIO()

        with mock.patch.object(cx, "require_codex"), mock.patch.object(cx, "ensure_layout"), mock.patch.object(
            cx, "list_aliases", return_value=["company"]
        ), mock.patch.object(cx, "read_status_for_alias", side_effect=lambda alias: statuses[alias]), mock.patch.object(
            cx, "use_account"
        ), contextlib.redirect_stdout(output):
            result = cx.cmd_best(argparse.Namespace(allow_blocked=True))

        text = output.getvalue()
        self.assertEqual(result, 0)
        self.assertIn("5h: 85% left | reset 2026-06-25 13:51", text)
        self.assertIn("7d: 98% left | reset 2026-07-02 10:19", text)
        self.assertNotIn("% used", text)

    def test_status_human_output_uses_reported_window_label(self) -> None:
        status = account("company", primary_used=3, secondary_used=None)
        status.primary_window_minutes = 10080
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            cx.print_status(status, "company")

        text = output.getvalue()
        self.assertIn("7d: 97% left", text)
        self.assertNotIn("5h:", text)

    def test_status_human_output_shows_reset_credit_expirations(self) -> None:
        status = account("company", primary_used=3, secondary_used=None)
        status.reset_credits_available = 3
        status.reset_credit_expires = ["2026-07-18 00:00", "2026-07-27 00:00", "2026-08-01 00:00"]
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            cx.print_status(status, "company")

        self.assertIn("Usage limit resets: 3 available | expires 2026-07-18 00:00, 2026-07-27 00:00, 2026-08-01 00:00", output.getvalue())


if __name__ == "__main__":
    unittest.main()
