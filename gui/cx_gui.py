#!/usr/bin/env python3

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if SRC_DIR.exists() and str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from cx_account_manager.gui_app import *  # noqa: F403
    from cx_account_manager.gui_app import main
except ImportError as exc:
    print(
        "cx-gui: Tkinter or the packaged GUI module is not available in this Python environment.\n"
        "Please install Python with Tkinter support, or use the CLI command `cx`.",
        file=sys.stderr,
    )
    print(f"Details: {exc}", file=sys.stderr)
    raise SystemExit(1) from exc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
