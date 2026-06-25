#!/usr/bin/env bash
set -euo pipefail

INSTALL_ROOT="${HOME}/.local/share/cx/app"
BIN_DIR="${HOME}/.local/bin"
TARGET_BIN="${BIN_DIR}/cx"
DATA_DIR="${HOME}/.local/share/cx"
PURGE_DATA=0

if [[ "${1:-}" == "--purge-data" ]]; then
  PURGE_DATA=1
fi

rm -f "${TARGET_BIN}"

if [[ -d "${INSTALL_ROOT}" ]]; then
  rm -rf "${INSTALL_ROOT}"
fi

if [[ "${PURGE_DATA}" -eq 1 ]]; then
  rm -rf "${DATA_DIR}"
fi

echo "Removed ${TARGET_BIN}"
echo "Removed ${INSTALL_ROOT}"

if [[ "${PURGE_DATA}" -eq 1 ]]; then
  echo "Removed ${DATA_DIR}"
  echo "Purged local cx data including saved accounts, rollback backups, gui-settings.json, current alias, tmp, and other generated files."
else
  echo "Kept account data in ${DATA_DIR}"
  echo "Kept local cx data in ${DATA_DIR}, including saved accounts, rollback backups, gui-settings.json, current alias, tmp, and other generated files."
  echo "Use ./uninstall.sh --purge-data if you also want to delete all local cx data."
fi
