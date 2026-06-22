from __future__ import annotations

import contextlib
import importlib.util
import io
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "docs_status.py"
SPEC = importlib.util.spec_from_file_location("docs_status", SCRIPT_PATH)
assert SPEC is not None
docs_status = importlib.util.module_from_spec(SPEC)
sys.modules["docs_status"] = docs_status
assert SPEC.loader is not None
SPEC.loader.exec_module(docs_status)


class DocsStatusTests(unittest.TestCase):
    def test_collect_documents_reads_statuses(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "docs" / "cr").mkdir(parents=True)
            (root / "docs" / "bugfix").mkdir(parents=True)
            (root / "docs" / "cr" / "CR-001-example.md").write_text(
                textwrap.dedent(
                    """\
                    # CR-001: Example

                    Status: Completed
                    """
                ),
                encoding="utf-8",
            )
            (root / "docs" / "bugfix" / "bugfix-0001-sample.md").write_text(
                textwrap.dedent(
                    """\
                    # Bugfix: Sample

                    Status: Proposed
                    """
                ),
                encoding="utf-8",
            )

            records, issues = docs_status.collect_documents(root)

        self.assertEqual(issues, [])
        self.assertEqual([record.doc_id for record in records], ["CR-001", "bugfix-0001"])
        self.assertEqual([record.status for record in records], ["Completed", "Proposed"])

    def test_collect_documents_reports_invalid_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "docs" / "cr").mkdir(parents=True)
            (root / "docs" / "bugfix").mkdir(parents=True)
            (root / "docs" / "cr" / "CR-001-example.md").write_text(
                textwrap.dedent(
                    """\
                    # CR-001: Example

                    Status: Done
                    """
                ),
                encoding="utf-8",
            )

            records, issues = docs_status.collect_documents(root)

        self.assertEqual(records, [])
        self.assertEqual(len(issues), 1)
        self.assertIn("unsupported status 'Done'", issues[0])

    def test_main_check_returns_nonzero_when_issues_exist(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "docs" / "cr").mkdir(parents=True)
            (root / "docs" / "cr" / "CR-001-example.md").write_text(
                textwrap.dedent(
                    """\
                    # CR-001: Example

                    Status: Completed
                    """
                ),
                encoding="utf-8",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = docs_status.main(["--root", str(root)])

        self.assertEqual(exit_code, 1)
        self.assertIn("Missing directory", stdout.getvalue())

    def test_main_index_prints_markdown_table(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "docs" / "cr").mkdir(parents=True)
            (root / "docs" / "bugfix").mkdir(parents=True)
            (root / "docs" / "cr" / "CR-001-example.md").write_text(
                textwrap.dedent(
                    """\
                    # CR-001: Example

                    Status: Completed
                    """
                ),
                encoding="utf-8",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = docs_status.main(["--mode", "index", "--root", str(root)])

        self.assertEqual(exit_code, 0)
        self.assertIn("| Type | ID | Status | Title | Path |", stdout.getvalue())
        self.assertIn("CR-001", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
