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
from unittest import mock


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
        self.assertEqual(manifest["version"], 3)
        self.assertEqual(manifest["aliases"], ["alpha", "beta", "gamma"])
        self.assertEqual(manifest["current"], "beta")
        self.assertEqual([account["alias"] for account in manifest["accounts"]], ["alpha", "beta", "gamma"])
        self.assertEqual(manifest["accounts"][0]["email"], "shared@example.com")
        self.assertTrue(str(manifest["accounts"][0]["authHash"]).startswith("sha256:"))

    def test_export_uses_cached_meta_identity_when_auth_lacks_email(self) -> None:
        account_dir = cx.account_dir("alpha")
        cx.ensure_dir(account_dir)
        cx.write_text_atomic(cx.account_auth_file("alpha"), json.dumps({"token": "only-token"}, ensure_ascii=True) + "\n")
        cx.write_text_atomic(
            cx.account_meta_file("alpha"),
            json.dumps({"scope": "work", "email": "cached@example.com", "plan": "plus"}, ensure_ascii=True) + "\n",
        )

        cx.cmd_export(
            argparse.Namespace(
                aliases=[],
                alias_selectors=None,
                email_selectors=None,
                output=str(self.archive),
            )
        )

        manifest = self.read_manifest()
        self.assertEqual(
            manifest["accounts"],
            [
                {
                    "alias": "alpha",
                    "email": "cached@example.com",
                    "scope": "work",
                    "plan": "plus",
                    "authHash": manifest["accounts"][0]["authHash"],
                }
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

    def test_import_writes_cached_identity_from_manifest_summary(self) -> None:
        with tarfile.open(self.archive, "w:gz") as tar:
            manifest = {
                "version": 2,
                "createdAt": "2026-06-22T00:00:00",
                "aliases": ["alpha"],
                "accounts": [
                    {"alias": "alpha", "email": "cached@example.com", "scope": "personal", "plan": "business"}
                ],
                "current": None,
            }
            cx.add_bytes_to_tar(tar, "manifest.json", json.dumps(manifest, ensure_ascii=True).encode("utf-8"), 0o600)
            cx.add_bytes_to_tar(tar, "accounts/alpha/auth.json", json.dumps({"token": "imported"}, ensure_ascii=True).encode("utf-8"), 0o600)
            cx.add_bytes_to_tar(tar, "accounts/alpha/meta.json", json.dumps({"scope": "personal"}, ensure_ascii=True).encode("utf-8"), 0o600)

        cx.cmd_import(
            argparse.Namespace(
                archive=str(self.archive),
                alias_selectors=None,
                email_selectors=None,
                force=False,
                skip_existing=False,
                set_current=False,
            )
        )

        meta = json.loads(cx.account_meta_file("alpha").read_text(encoding="utf-8"))
        self.assertEqual(meta["scope"], "personal")
        self.assertEqual(meta["email"], "cached@example.com")
        self.assertEqual(meta["plan"], "business")
        self.assertEqual(meta["authHash"], cx.auth_hash_from_bytes(cx.account_auth_file("alpha").read_bytes()))

    def test_save_force_refreshes_stale_auth_hash(self) -> None:
        self.create_account("alpha", email="old@example.com", scope="work", plan="plus")
        cx.write_account_sync_meta("alpha", auth_hash="sha256:stale")
        new_auth = {
            "account": {
                "email": "new@example.com",
                "planType": "pro",
            },
            "token": "current-token",
        }
        cx.ensure_dir(cx.CODEX_HOME)
        cx.write_text_atomic(cx.CODEX_AUTH_FILE, json.dumps(new_auth, ensure_ascii=True) + "\n")

        cx.cmd_save(argparse.Namespace(alias="alpha", force=True))

        meta = json.loads(cx.account_meta_file("alpha").read_text(encoding="utf-8"))
        self.assertEqual(meta["email"], "new@example.com")
        self.assertEqual(meta["plan"], "pro")
        self.assertEqual(meta["authHash"], cx.auth_hash_from_bytes(cx.account_auth_file("alpha").read_bytes()))

    def test_import_rechecks_conflicts_inside_lock(self) -> None:
        with tarfile.open(self.archive, "w:gz") as tar:
            manifest = {
                "version": 3,
                "createdAt": "2026-06-22T00:00:00Z",
                "aliases": ["alpha"],
                "accounts": [
                    {
                        "alias": "alpha",
                        "email": "imported@example.com",
                        "scope": "personal",
                        "plan": "business",
                        "authHash": "sha256:unused",
                    }
                ],
                "current": None,
            }
            auth_data = json.dumps({"account": {"email": "imported@example.com"}, "token": "imported-token"}, ensure_ascii=True).encode("utf-8")
            cx.add_bytes_to_tar(tar, "manifest.json", json.dumps(manifest, ensure_ascii=True).encode("utf-8"), 0o600)
            cx.add_bytes_to_tar(tar, "accounts/alpha/auth.json", auth_data, 0o600)

        class RaceFileLock:
            def __init__(self, _path: Path) -> None:
                pass

            def __enter__(self) -> "RaceFileLock":
                cx.ensure_dir(cx.account_dir("alpha"))
                cx.write_text_atomic(
                    cx.account_auth_file("alpha"),
                    json.dumps({"account": {"email": "local@example.com"}, "token": "local-token"}, ensure_ascii=True) + "\n",
                )
                cx.write_text_atomic(cx.account_meta_file("alpha"), json.dumps({"scope": "work"}, ensure_ascii=True) + "\n")
                return self

            def __exit__(self, exc_type, exc, tb) -> bool:
                return False

        with mock.patch.object(cx, "FileLock", RaceFileLock):
            with self.assertRaises(cx.CxError):
                cx.cmd_import(
                    argparse.Namespace(
                        archive=str(self.archive),
                        alias_selectors=None,
                        email_selectors=None,
                        force=False,
                        skip_existing=False,
                        set_current=False,
                    )
                )

        self.assertEqual(json.loads(cx.account_auth_file("alpha").read_text(encoding="utf-8"))["token"], "local-token")

    def test_sync_check_marks_invalid_local_v3_remote_as_would_overwrite(self) -> None:
        self.create_account("alpha", email="shared@example.com", scope="work", plan="plus")
        cx.write_account_sync_meta("alpha", auth_hash="sha256:local")
        self.create_account("remote", email="shared@example.com", scope="work", plan="pro")
        cx.cmd_export(
            argparse.Namespace(
                aliases=["remote"],
                alias_selectors=None,
                email_selectors=None,
                output=str(self.archive),
            )
        )
        shutil.rmtree(cx.account_dir("remote"))

        with mock.patch.object(cx, "local_account_validity", return_value=("invalid", "token revoked")):
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                cx.cmd_sync_check(
                    argparse.Namespace(
                        dir=str(self.root),
                        json=True,
                        import_new_accounts=True,
                        overwrite_existing_accounts=True,
                        allow_legacy_overwrite=False,
                        rollback_before_overwrite=True,
                    )
                )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["actions"][0]["action"], "would-overwrite")
        self.assertEqual(payload["actions"][0]["localAlias"], "alpha")

    def test_sync_check_uses_current_local_auth_hash_when_meta_is_stale(self) -> None:
        self.create_account("alpha", email="shared@example.com", scope="work", plan="plus")
        cx.write_account_sync_meta("alpha", auth_hash="sha256:stale")
        self.create_account("remote", email="shared@example.com", scope="work", plan="plus")
        cx.cmd_export(
            argparse.Namespace(
                aliases=["remote"],
                alias_selectors=None,
                email_selectors=None,
                output=str(self.archive),
            )
        )
        shutil.rmtree(cx.account_dir("remote"))

        with mock.patch.object(cx, "local_account_validity", return_value=("invalid", "token revoked")):
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                cx.cmd_sync_check(
                    argparse.Namespace(
                        dir=str(self.root),
                        json=True,
                        import_new_accounts=True,
                        overwrite_existing_accounts=True,
                        allow_legacy_overwrite=False,
                        rollback_before_overwrite=True,
                    )
                )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["actions"][0]["action"], "skip-same-auth")
        self.assertEqual(payload["actions"][0]["localAlias"], "alpha")

    def test_sync_import_imports_new_account_and_writes_sync_meta(self) -> None:
        self.create_account("remote", email="new@example.com", scope="personal", plan="pro")
        cx.cmd_export(
            argparse.Namespace(
                aliases=["remote"],
                alias_selectors=None,
                email_selectors=None,
                output=str(self.archive),
            )
        )
        shutil.rmtree(cx.account_dir("remote"))

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = cx.cmd_sync_import(
                argparse.Namespace(
                    dir=str(self.root),
                    apply=True,
                    json=True,
                    import_new_accounts=True,
                    overwrite_existing_accounts=True,
                    allow_legacy_overwrite=False,
                    rollback_before_overwrite=True,
                )
            )

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["actions"][0]["action"], "imported-new")
        target_alias = payload["actions"][0]["targetAlias"]
        meta = json.loads(cx.account_meta_file(target_alias).read_text(encoding="utf-8"))
        self.assertEqual(meta["email"], "new@example.com")
        self.assertTrue(meta["authHash"].startswith("sha256:"))
        self.assertEqual(meta["scope"], "personal")

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
            cx.cmd_backup_list(argparse.Namespace(archive=str(self.archive), json=False))

        lines = stdout.getvalue().splitlines()
        self.assertEqual(lines, ["  alpha | alpha@example.com | work | plus", "* beta | beta@example.com | personal | business"])

    def test_backup_list_json_outputs_archive_rows(self) -> None:
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
            cx.cmd_backup_list(argparse.Namespace(archive=str(self.archive), json=True))

        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["current"], "beta")
        self.assertEqual(
            payload["accounts"],
            [
                {"alias": "alpha", "current": False, "email": "alpha@example.com", "scope": "work", "plan": "plus"},
                {"alias": "beta", "current": True, "email": "beta@example.com", "scope": "personal", "plan": "business"},
            ],
        )

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
            cx.cmd_backup_list(argparse.Namespace(archive=str(self.archive), json=False))

        self.assertEqual(stdout.getvalue().strip(), "* legacy | legacy@example.com | personal | starter")


if __name__ == "__main__":
    unittest.main()
