#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_ROOT="${HOME}/.local/share/cx/app"
BIN_DIR="${HOME}/.local/bin"
TARGET_BIN="${BIN_DIR}/cx"
TARGET_SRC="${INSTALL_ROOT}/cx.py"
PROFILE_FILE="${HOME}/.profile"
PATH_EXPORT='export PATH="$HOME/.local/bin:$PATH"'

mkdir -p "${INSTALL_ROOT}"
mkdir -p "${BIN_DIR}"

install -m 755 "${SCRIPT_DIR}/src/cx.py" "${TARGET_SRC}"
install -m 644 "${SCRIPT_DIR}/src/cx_ranking.py" "${INSTALL_ROOT}/cx_ranking.py"

cat > "${TARGET_BIN}" <<EOF
#!/usr/bin/env bash
set -euo pipefail

exec python3 "${TARGET_SRC}" "\$@"
EOF

chmod 755 "${TARGET_BIN}"

echo "Installed cx to ${TARGET_BIN}"

case ":${PATH}:" in
  *":${BIN_DIR}:"*)
    ;;
  *)
    echo
    echo "${BIN_DIR} is not in PATH."
    if grep -Fqx "${PATH_EXPORT}" "${PROFILE_FILE}" 2>/dev/null; then
      echo "${PROFILE_FILE} already contains the PATH entry."
      echo "Open a new shell or run: ${PATH_EXPORT}"
    else
      read -r -p "Add ${PATH_EXPORT} to ${PROFILE_FILE}? [Y/n] " reply
      case "${reply}" in
        ""|[Yy]|[Yy][Ee][Ss])
          printf '\n%s\n' "${PATH_EXPORT}" >> "${PROFILE_FILE}"
          echo "Added PATH entry to ${PROFILE_FILE}"
          echo "Open a new shell or run: ${PATH_EXPORT}"
          ;;
        *)
          echo "Skipped updating ${PROFILE_FILE}."
          echo "Add this manually if needed:"
          echo "${PATH_EXPORT}"
          ;;
      esac
    fi
    ;;
esac
