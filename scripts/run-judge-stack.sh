#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

for candidate in \
  "${HOME}/.local/share/pnpm" \
  "${HOME}"/.nvm/versions/node/*/bin
do
  if [[ -d "${candidate}" ]]; then
    PATH="${candidate}:${PATH}"
  fi
done

require_cmd() {
  local name="$1"
  if ! command -v "${name}" >/dev/null 2>&1; then
    echo "Missing required command: ${name}" >&2
    exit 1
  fi
}

resolve_python_bin() {
  if [[ -n "${PYTHON_BIN:-}" ]]; then
    printf '%s\n' "${PYTHON_BIN}"
    return 0
  fi

  if [[ -x "${HOME}/.pyenv/versions/proof-of-audit-3.12/bin/python" ]]; then
    printf '%s\n' "${HOME}/.pyenv/versions/proof-of-audit-3.12/bin/python"
    return 0
  fi

  if command -v python >/dev/null 2>&1; then
    command -v python
    return 0
  fi

  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return 0
  fi

  echo "Missing required command: python or python3" >&2
  exit 1
}

PYTHON_BIN="$(resolve_python_bin)"

require_cmd anvil
require_cmd cast
require_cmd curl

if ! command -v pnpm >/dev/null 2>&1; then
  require_cmd corepack
  corepack enable >/dev/null 2>&1
  corepack prepare pnpm@10.18.3 --activate >/dev/null 2>&1
fi

require_cmd pnpm

cd "${ROOT_DIR}"

echo "Starting the judge evaluation stack..."
echo "Python: ${PYTHON_BIN}"
echo "Web: http://127.0.0.1:3000"
echo "API: http://127.0.0.1:8080"
echo "Fallback docs: http://127.0.0.1:8080/docs"
echo

PYTHON_BIN="${PYTHON_BIN}" \
E2E_ANVIL_PORT="${E2E_ANVIL_PORT:-8545}" \
E2E_ANVIL_CHAIN_ID="${E2E_ANVIL_CHAIN_ID:-31337}" \
E2E_API_PORT="${E2E_API_PORT:-8080}" \
E2E_WEB_PORT="${E2E_WEB_PORT:-3000}" \
./scripts/run-e2e-stack.sh
