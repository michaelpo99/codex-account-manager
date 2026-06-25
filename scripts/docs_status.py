from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path


VALID_STATUSES = ("Proposed", "In Progress", "Completed", "Blocked")
STATUS_PATTERN = re.compile(r"^Status:\s*(.+?)\s*$")
CR_ID_PATTERN = re.compile(r"^(CR-\d+)-")
BUGFIX_ID_PATTERN = re.compile(r"^(bugfix-\d+)-")


@dataclass(frozen=True)
class DocumentRecord:
    doc_type: str
    doc_id: str
    title: str
    status: str
    path: Path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize CR and bugfix document statuses.")
    parser.add_argument(
        "--mode",
        choices=("check", "index"),
        default="check",
        help="check prints a status summary and validates docs; index prints a Markdown table.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root. Defaults to the parent of scripts/.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    records, issues = collect_documents(args.root)

    if args.mode == "index":
        print(build_index(records))
        return 0

    print(build_check_output(records, issues))
    return 1 if issues else 0


def collect_documents(root: Path) -> tuple[list[DocumentRecord], list[str]]:
    docs_root = root / "docs"
    targets = (
        ("CR", docs_root / "cr", CR_ID_PATTERN),
        ("bugfix", docs_root / "bugfix", BUGFIX_ID_PATTERN),
    )

    records: list[DocumentRecord] = []
    issues: list[str] = []

    for doc_type, directory, id_pattern in targets:
        if not directory.is_dir():
            issues.append(f"Missing directory: {directory.relative_to(root)}")
            continue

        for path in sorted(directory.glob("*.md")):
            record, doc_issues = parse_document(root, path, doc_type, id_pattern)
            issues.extend(doc_issues)
            if record is not None:
                records.append(record)

    issues.extend(find_duplicate_ids(records))
    records.sort(key=lambda item: (item.doc_type, item.doc_id, item.path.name))
    return records, issues


def find_duplicate_ids(records: list[DocumentRecord]) -> list[str]:
    seen: dict[tuple[str, str], Path] = {}
    issues: list[str] = []
    for record in records:
        key = (record.doc_type, record.doc_id)
        previous = seen.get(key)
        if previous is None:
            seen[key] = record.path
            continue
        issues.append(
            f"duplicate {record.doc_type} id {record.doc_id}: {previous.as_posix()} and {record.path.as_posix()}"
        )
    return issues


def parse_document(root: Path, path: Path, doc_type: str, id_pattern: re.Pattern[str]) -> tuple[DocumentRecord | None, list[str]]:
    issues: list[str] = []
    match = id_pattern.match(path.stem)
    if match is None:
        issues.append(f"{path.relative_to(root)}: filename does not match expected {doc_type} pattern")
        return None, issues

    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        issues.append(f"{path.relative_to(root)}: failed to read file ({exc})")
        return None, issues

    lines = content.splitlines()
    title = extract_title(lines, root, path, issues)
    status = extract_status(lines, root, path, issues)
    if title is None or status is None:
        return None, issues

    return DocumentRecord(doc_type=doc_type, doc_id=match.group(1), title=title, status=status, path=path.relative_to(root)), issues


def extract_title(lines: list[str], root: Path, path: Path, issues: list[str]) -> str | None:
    for line in lines:
        if line.startswith("# "):
            return line[2:].strip()
    issues.append(f"{path.relative_to(root)}: missing H1 title")
    return None


def extract_status(lines: list[str], root: Path, path: Path, issues: list[str]) -> str | None:
    for line in lines:
        match = STATUS_PATTERN.match(line)
        if match is None:
            continue
        status = match.group(1)
        if status not in VALID_STATUSES:
            issues.append(f"{path.relative_to(root)}: unsupported status '{status}'")
            return None
        return status
    issues.append(f"{path.relative_to(root)}: missing Status line")
    return None


def build_check_output(records: list[DocumentRecord], issues: list[str]) -> str:
    lines = ["Document status summary", ""]
    for record in records:
        lines.append(f"{record.status:<11} | {record.doc_type:<7} | {record.doc_id:<12} | {record.path.as_posix()}")

    lines.extend(["", "Counts"])
    for status in VALID_STATUSES:
        count = sum(1 for record in records if record.status == status)
        lines.append(f"- {status}: {count}")

    if issues:
        lines.extend(["", "Issues"])
        for issue in issues:
            lines.append(f"- {issue}")
    else:
        lines.extend(["", "Issues", "- none"])

    return "\n".join(lines)


def build_index(records: list[DocumentRecord]) -> str:
    lines = [
        "| Type | ID | Status | Title | Path |",
        "| --- | --- | --- | --- | --- |",
    ]
    for record in records:
        lines.append(
            f"| {record.doc_type} | {record.doc_id} | {record.status} | {escape_table_cell(record.title)} | `{record.path.as_posix()}` |"
        )
    return "\n".join(lines)


def escape_table_cell(value: str) -> str:
    return value.replace("|", "\\|")


if __name__ == "__main__":
    raise SystemExit(main())
