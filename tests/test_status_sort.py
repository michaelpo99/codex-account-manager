from __future__ import annotations

import importlib.util
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

NOW = 1_800_000_000


def account(
    alias: str,
    *,
    scope: str = "work",
    primary_used: int | None,
    primary_reset_in: int | None,
    secondary_used: int | None,
    secondary_reset_in: int | None,
) -> cx.AccountStatus:
    return cx.AccountStatus(
        alias=alias,
        scope=scope,
        email=None,
        plan=None,
        primary_used=primary_used,
        primary_reset=None,
        primary_reset_at=NOW + primary_reset_in if primary_reset_in is not None else None,
        secondary_used=secondary_used,
        secondary_reset=None,
        secondary_reset_at=NOW + secondary_reset_in if secondary_reset_in is not None else None,
    )


def ranked_aliases(statuses: list[cx.AccountStatus]) -> list[str]:
    return [status.alias for status in sorted(statuses, key=lambda status: cx.status_sort_key(status, NOW))]


class StatusSortTests(unittest.TestCase):
    def test_weekly_blocked_work_account_loses_to_usable_work_account(self) -> None:
        statuses = [
            account("michaelpo", primary_used=1, primary_reset_in=4 * 60 * 60, secondary_used=100, secondary_reset_in=36 * 60 * 60),
            account("foya_co01", primary_used=6, primary_reset_in=4 * 60 * 60, secondary_used=11, secondary_reset_in=6 * 24 * 60 * 60),
        ]

        self.assertEqual(ranked_aliases(statuses), ["foya_co01", "michaelpo"])

    def test_fast_primary_reset_can_beat_more_current_remaining(self) -> None:
        statuses = [
            account("low-but-soon", primary_used=80, primary_reset_in=20 * 60, secondary_used=20, secondary_reset_in=3 * 24 * 60 * 60),
            account("high-but-late", primary_used=30, primary_reset_in=4 * 60 * 60, secondary_used=20, secondary_reset_in=3 * 24 * 60 * 60),
        ]

        self.assertEqual(ranked_aliases(statuses), ["low-but-soon", "high-but-late"])

    def test_usable_work_beats_higher_scoring_personal(self) -> None:
        statuses = [
            account(
                "personal-fast-reset",
                scope="personal",
                primary_used=42,
                primary_reset_in=30 * 60,
                secondary_used=52,
                secondary_reset_in=12 * 60 * 60,
            ),
            account(
                "work-available",
                scope="work",
                primary_used=24,
                primary_reset_in=4 * 60 * 60,
                secondary_used=14,
                secondary_reset_in=6 * 24 * 60 * 60,
            ),
        ]

        self.assertEqual(ranked_aliases(statuses), ["work-available", "personal-fast-reset"])

    def test_usable_personal_beats_blocked_work(self) -> None:
        statuses = [
            account("work-blocked", scope="work", primary_used=1, primary_reset_in=4 * 60 * 60, secondary_used=100, secondary_reset_in=36 * 60 * 60),
            account("personal-usable", scope="personal", primary_used=80, primary_reset_in=4 * 60 * 60, secondary_used=80, secondary_reset_in=6 * 24 * 60 * 60),
        ]

        self.assertEqual(ranked_aliases(statuses), ["personal-usable", "work-blocked"])

    def test_weekly_bottleneck_with_far_reset_drags_score_down(self) -> None:
        statuses = [
            account("short-term-only", primary_used=0, primary_reset_in=5 * 60 * 60, secondary_used=95, secondary_reset_in=6 * 24 * 60 * 60),
            account("balanced", primary_used=25, primary_reset_in=4 * 60 * 60, secondary_used=40, secondary_reset_in=4 * 24 * 60 * 60),
        ]

        self.assertEqual(ranked_aliases(statuses), ["balanced", "short-term-only"])

    def test_all_usable_accounts_beat_blocked_accounts(self) -> None:
        statuses = [
            account("blocked-soon", primary_used=100, primary_reset_in=5 * 60, secondary_used=0, secondary_reset_in=7 * 24 * 60 * 60),
            account("usable-low", primary_used=99, primary_reset_in=5 * 60 * 60, secondary_used=99, secondary_reset_in=7 * 24 * 60 * 60),
        ]

        self.assertEqual(ranked_aliases(statuses), ["usable-low", "blocked-soon"])

    def test_blocked_accounts_sort_by_unblock_time(self) -> None:
        statuses = [
            account("weekly-blocked", primary_used=0, primary_reset_in=5 * 60 * 60, secondary_used=100, secondary_reset_in=24 * 60 * 60),
            account("primary-blocked", primary_used=100, primary_reset_in=30 * 60, secondary_used=0, secondary_reset_in=7 * 24 * 60 * 60),
        ]

        self.assertEqual(ranked_aliases(statuses), ["primary-blocked", "weekly-blocked"])


if __name__ == "__main__":
    unittest.main()
