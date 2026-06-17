#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_ROOT="${HOME}/.local/share/cx/app"
BIN_DIR="${HOME}/.local/bin"
TARGET_BIN="${BIN_DIR}/cx"
TARGET_SRC="${INSTALL_ROOT}/cx.py"

mkdir -p "${INSTALL_ROOT}"
mkdir -p "${BIN_DIR}"

install -m 755 "${SCRIPT_DIR}/src/cx.py" "${TARGET_SRC}"

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
    echo "Add this to your shell config if needed:"
    echo "export PATH=\"${BIN_DIR}:\$PATH\""
    ;;
esac
