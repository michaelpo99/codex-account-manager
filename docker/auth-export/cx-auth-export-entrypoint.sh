#!/bin/sh
set -eu

ALIAS="${CX_DEFAULT_ALIAS:-}"
EXPECTED_EMAIL="${CX_EXPECTED_EMAIL:-}"

usage() {
  cat <<'EOF'
Usage:
  cx-auth-export <alias> [--email expected@example.com]
  cx-auth-export [--email expected@example.com]

Environment defaults:
  CX_DEFAULT_ALIAS     default account alias
  CX_EXPECTED_EMAIL    optional expected email guard

Output:
  /out/<alias>.tar.gz

Notes:
  - This helper runs Codex device login inside the container.
  - The login result is exported as a cx backup archive.
  - Treat the output archive as a sensitive login credential.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --email)
      shift
      if [ "$#" -eq 0 ]; then
        echo "ERROR: --email requires a value." >&2
        exit 2
      fi
      EXPECTED_EMAIL="$1"
      ;;
    --email=*)
      EXPECTED_EMAIL="${1#--email=}"
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    --*)
      echo "ERROR: unexpected option: $1" >&2
      usage >&2
      exit 2
      ;;
    *)
      if [ -z "$ALIAS" ]; then
        ALIAS="$1"
      else
        echo "ERROR: unexpected argument: $1" >&2
        usage >&2
        exit 2
      fi
      ;;
  esac
  shift
done

if [ -z "$ALIAS" ]; then
  echo "ERROR: alias is required." >&2
  usage >&2
  exit 2
fi

OUT="/out/${ALIAS}.tar.gz"

echo "cx auth export helper"
echo "Alias: ${ALIAS}"
if [ -n "$EXPECTED_EMAIL" ]; then
  echo "Expected email: ${EXPECTED_EMAIL}"
else
  echo "Expected email: <not restricted>"
fi

echo ""
echo "Starting Codex device login..."
cx add "$ALIAS"

if [ -n "$EXPECTED_EMAIL" ]; then
  ACTUAL_EMAIL="$(python3 - "$ALIAS" <<'PY'
import json
import sys
from pathlib import Path

alias = sys.argv[1]
meta_path = Path.home() / ".local" / "share" / "cx" / "accounts" / alias / "meta.json"

try:
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
except Exception:
    print("")
    raise SystemExit(0)

print(str(meta.get("email") or ""))
PY
)"

  if [ "$ACTUAL_EMAIL" != "$EXPECTED_EMAIL" ]; then
    echo "" >&2
    echo "ERROR: logged-in account email does not match expected email." >&2
    echo "Expected: $EXPECTED_EMAIL" >&2
    echo "Actual:   ${ACTUAL_EMAIL:-<unknown>}" >&2
    echo "No backup file was created." >&2
    exit 20
  fi
fi

echo ""
echo "Exporting backup to ${OUT}"
cx export "$ALIAS" -o "$OUT"

echo ""
echo "Backup created: ${OUT}"
echo "Treat this file as a sensitive login credential."
