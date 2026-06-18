from __future__ import annotations

import importlib.util
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


def account(alias: str) -> cx.AccountStatus:
    return cx.AccountStatus(
        alias=alias,
        scope="work",
        email=None,
        plan=None,
        primary_used=0,
        primary_reset=None,
        primary_reset_at=None,
        secondary_used=0,
        secondary_reset=None,
        secondary_reset_at=None,
    )


class FakeExecutor:
    created_workers: list[int] = []

    def __init__(self, *, max_workers: int) -> None:
        self.max_workers = max_workers
        self.created_workers.append(max_workers)

    def __enter__(self) -> "FakeExecutor":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def map(self, func, aliases):
        return [func(alias) for alias in aliases]


class StatusParallelTests(unittest.TestCase):
    def tearDown(self) -> None:
        FakeExecutor.created_workers.clear()

    def test_multiple_statuses_use_capped_thread_pool(self) -> None:
        aliases = ["a", "b", "c", "d", "e"]

        with mock.patch.object(cx, "ThreadPoolExecutor", FakeExecutor), mock.patch.object(
            cx, "read_status_for_alias", side_effect=lambda alias: account(alias)
        ) as read_status:
            statuses = cx.read_statuses_for_aliases(aliases)

        self.assertEqual([status.alias for status in statuses], aliases)
        self.assertEqual(FakeExecutor.created_workers, [4])
        self.assertEqual(read_status.call_count, len(aliases))

    def test_single_status_does_not_create_thread_pool(self) -> None:
        with mock.patch.object(cx, "ThreadPoolExecutor", FakeExecutor), mock.patch.object(
            cx, "read_status_for_alias", side_effect=lambda alias: account(alias)
        ) as read_status:
            statuses = cx.read_statuses_for_aliases(["solo"])

        self.assertEqual([status.alias for status in statuses], ["solo"])
        self.assertEqual(FakeExecutor.created_workers, [])
        read_status.assert_called_once_with("solo")


if __name__ == "__main__":
    unittest.main()
