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
        email=None,
        plan=None,
        primary_used=primary_used,
        primary_reset="2026-06-18 12:00",
        primary_reset_at=1_800_000_000,
        secondary_used=secondary_used,
        secondary_reset="2026-06-25 12:00",
        secondary_reset_at=1_800_604_800,
    )


class BestCommandTests(unittest.TestCase):
    def test_best_ignores_blocked_accounts_by_default(self) -> None:
        statuses = {
            "blocked": account("blocked", primary_used=100, secondary_used=0),
            "usable": account("usable", primary_used=80, secondary_used=80),
        }

        output = io.StringIO()
        with mock.patch.object(cx, "require_codex"), mock.patch.object(cx, "ensure_layout"), mock.patch.object(
            cx, "list_aliases", return_value=["blocked", "usable"]
        ), mock.patch.object(cx, "read_status_for_alias", side_effect=lambda alias: statuses[alias]), mock.patch.object(
            cx, "use_account"
        ) as use_account, contextlib.redirect_stdout(output):
            result = cx.cmd_best(argparse.Namespace(allow_blocked=False))

        self.assertEqual(result, 0)
        use_account.assert_called_once_with("usable")

    def test_best_does_not_switch_when_all_accounts_are_blocked(self) -> None:
        statuses = {
            "blocked-later": account("blocked-later", primary_used=100, secondary_used=0),
            "blocked-soon": account("blocked-soon", primary_used=0, secondary_used=100),
        }

        output = io.StringIO()
        with mock.patch.object(cx, "require_codex"), mock.patch.object(cx, "ensure_layout"), mock.patch.object(
            cx, "list_aliases", return_value=["blocked-later", "blocked-soon"]
        ), mock.patch.object(cx, "read_status_for_alias", side_effect=lambda alias: statuses[alias]), mock.patch.object(
            cx, "use_account"
        ) as use_account, contextlib.redirect_stdout(output):
            result = cx.cmd_best(argparse.Namespace(allow_blocked=False))

        self.assertEqual(result, 1)
        use_account.assert_not_called()
        self.assertIn("未切換帳號", output.getvalue())
        self.assertIn("cx best --allow-blocked", output.getvalue())

    def test_best_can_switch_to_blocked_account_when_allowed(self) -> None:
        statuses = {
            "blocked": account("blocked", primary_used=100, secondary_used=0),
        }

        output = io.StringIO()
        with mock.patch.object(cx, "require_codex"), mock.patch.object(cx, "ensure_layout"), mock.patch.object(
            cx, "list_aliases", return_value=["blocked"]
        ), mock.patch.object(cx, "read_status_for_alias", side_effect=lambda alias: statuses[alias]), mock.patch.object(
            cx, "use_account"
        ) as use_account, contextlib.redirect_stdout(output):
            result = cx.cmd_best(argparse.Namespace(allow_blocked=True))

        self.assertEqual(result, 0)
        use_account.assert_called_once_with("blocked")


if __name__ == "__main__":
    unittest.main()
