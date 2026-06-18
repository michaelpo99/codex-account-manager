from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import json
import shutil
import sys
import tarfile
import tempfile
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


class BackupArchiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="cx-test-backup-"))
        self.archive = self.root / "backup.tar.gz"
        self.originals = {
            "DATA_DIR": cx.DATA_DIR,
            "ACCOUNTS_DIR": cx.ACCOUNTS_DIR,
            "CURRENT_FILE": cx.CURRENT_FILE,
            "LOCK_FILE": cx.LOCK_FILE,
            "TEMP_DIR": cx.TEMP_DIR,
            "CODEX_HOME": cx.CODEX_HOME,
            "CODEX_AUTH_FILE": cx.CODEX_AUTH_FILE,
        }
        self.configure_paths(self.root / "workspace-a")

    def tearDown(self) -> None:
        for name, value in self.originals.items():
            setattr(cx, name, value)
        shutil.rmtree(self.root, ignore_errors=True)

    def configure_paths(self, base: Path) -> None:
        cx.DATA_DIR = base / "data"
        cx.ACCOUNTS_DIR = cx.DATA_DIR / "accounts"
        cx.CURRENT_FILE = cx.DATA_DIR / "current"
        cx.LOCK_FILE = cx.DATA_DIR / "lock"
        cx.TEMP_DIR = cx.DATA_DIR / "tmp"
        cx.CODEX_HOME = base / "codex-home"
        cx.CODEX_AUTH_FILE = cx.CODEX_HOME / "auth.json"

    def create_account(self, alias: str, *, email: str, scope: str = "work", plan: str | None = None) -> None:
        account_dir = cx.account_dir(alias)
        cx.ensure_dir(account_dir)
        auth_payload = {
            "account": {
                "email": email,
                "planType": plan,
            }
        }
        cx.write_text_atomic(cx.account_auth_file(alias), json.dumps(auth_payload, ensure_ascii=True) + "\n")
        cx.write_text_atomic(cx.account_meta_file(alias), json.dumps({"scope": scope}, ensure_ascii=True) + "\n")

    def read_manifest(self) -> dict[str, object]:
        with tarfile.open(self.archive, "r:gz") as tar:
            return json.loads(cx.read_tar_member(tar, "manifest.json").decode("utf-8"))

    def test_parse_selector_values_supports_repeat_and_commas(self) -> None:
        aliases = cx.parse_selector_values(["alpha, beta", "beta", "gamma"], kind="alias")
        emails = cx.parse_selector_values(["a@example.com, b@example.com", "b@example.com"], kind="email")

        self.assertEqual(aliases, ["alpha", "beta", "gamma"])
        self.assertEqual(emails, ["a@example.com", "b@example.com"])

    def test_parse_selector_values_rejects_empty_entries(self) -> None:
        with self.assertRaises(cx.CxError) as raised:
            cx.parse_selector_values(["alpha,,beta"], kind="alias")

        self.assertEqual(str(raised.exception), "`--alias` 不能包含空項目。")

    def test_export_supports_alias_and_email_union_and_writes_account_summaries(self) -> None:
        self.create_account("alpha", email="shared@example.com", scope="work", plan="plus")
        self.create_account("beta", email="shared@example.com", scope="personal", plan="business")
        self.create_account("gamma", email="solo@example.com", scope="work", plan="pro")
        cx.set_current_alias("beta")

        args = argparse.Namespace(
            aliases=[],
            alias_selectors=["gamma"],
            email_selectors=["shared@example.com"],
            output=str(self.archive),
        )
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            cx.cmd_export(args)

        output = stdout.getvalue()
        manifest = self.read_manifest()
        self.assertIn("匯出時 email `shared@example.com` 命中 2 個帳號", output)
        self.assertEqual(manifest["version"], 2)
        self.assertEqual(manifest["aliases"], ["alpha", "beta", "gamma"])
        self.assertEqual(manifest["current"], "beta")
        self.assertEqual(
            manifest["accounts"],
            [
                {"alias": "alpha", "email": "shared@example.com", "scope": "work", "plan": "plus"},
                {"alias": "beta", "email": "shared@example.com", "scope": "personal", "plan": "business"},
                {"alias": "gamma", "email": "solo@example.com", "scope": "work", "plan": "pro"},
            ],
        )

    def test_import_supports_email_selection_and_restores_current_when_selected(self) -> None:
        self.create_account("alpha", email="shared@example.com", scope="work", plan="plus")
        self.create_account("beta", email="shared@example.com", scope="personal", plan="business")
        self.create_account("gamma", email="solo@example.com", scope="work", plan="pro")
        cx.set_current_alias("beta")
        cx.cmd_export(
            argparse.Namespace(
                aliases=[],
                alias_selectors=None,
                email_selectors=None,
                output=str(self.archive),
            )
        )

        self.configure_paths(self.root / "workspace-b")
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            cx.cmd_import(
                argparse.Namespace(
                    archive=str(self.archive),
                    alias_selectors=None,
                    email_selectors=["shared@example.com"],
                    force=False,
                    skip_existing=False,
                    set_current=True,
                )
            )

        output = stdout.getvalue()
        self.assertIn("匯入時 email `shared@example.com` 命中 2 個帳號", output)
        self.assertTrue(cx.account_auth_file("alpha").exists())
        self.assertTrue(cx.account_auth_file("beta").exists())
        self.assertFalse(cx.account_auth_file("gamma").exists())
        self.assertEqual(cx.read_current_alias(), "beta")

    def test_backup_list_prints_archive_rows(self) -> None:
        self.create_account("alpha", email="alpha@example.com", scope="work", plan="plus")
        self.create_account("beta", email="beta@example.com", scope="personal", plan="business")
        cx.set_current_alias("beta")
        cx.cmd_export(
            argparse.Namespace(
                aliases=[],
                alias_selectors=None,
                email_selectors=None,
                output=str(self.archive),
            )
        )

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            cx.cmd_backup_list(argparse.Namespace(archive=str(self.archive)))

        lines = stdout.getvalue().splitlines()
        self.assertEqual(lines, ["  alpha | alpha@example.com | work | plus", "* beta | beta@example.com | personal | business"])

    def test_backup_list_can_read_version_1_archive_by_deriving_summaries(self) -> None:
        with tarfile.open(self.archive, "w:gz") as tar:
            manifest = {
                "version": 1,
                "createdAt": "2026-06-18T00:00:00",
                "aliases": ["legacy"],
                "current": "legacy",
            }
            cx.add_bytes_to_tar(tar, "manifest.json", json.dumps(manifest, ensure_ascii=True).encode("utf-8"), 0o600)
            cx.add_bytes_to_tar(
                tar,
                "accounts/legacy/auth.json",
                json.dumps({"account": {"email": "legacy@example.com", "planType": "starter"}}, ensure_ascii=True).encode("utf-8"),
                0o600,
            )
            cx.add_bytes_to_tar(
                tar,
                "accounts/legacy/meta.json",
                json.dumps({"scope": "personal"}, ensure_ascii=True).encode("utf-8"),
                0o600,
            )

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            cx.cmd_backup_list(argparse.Namespace(archive=str(self.archive)))

        self.assertEqual(stdout.getvalue().strip(), "* legacy | legacy@example.com | personal | starter")


if __name__ == "__main__":
    unittest.main()
