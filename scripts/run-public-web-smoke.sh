#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
WEB_DIR="${ROOT_DIR}/web"

PUBLIC_WEB_URL="${PROOF_OF_AUDIT_PUBLIC_WEB_SMOKE_URL:-${E2E_WEB_URL:-}}"
PNPM_BIN="${PNPM_BIN:-}"

: "${PUBLIC_WEB_URL:?PROOF_OF_AUDIT_PUBLIC_WEB_SMOKE_URL or E2E_WEB_URL must be set}"

if [[ -z "${PNPM_BIN}" ]]; then
  if command -v pnpm >/dev/null 2>&1; then
    PNPM_BIN="$(command -v pnpm)"
  elif [[ -x "${HOME}/.local/share/pnpm/pnpm" ]]; then
    PNPM_BIN="${HOME}/.local/share/pnpm/pnpm"
  else
    echo "pnpm is required to run the public web smoke." >&2
    exit 1
  fi
fi

if ! command -v node >/dev/null 2>&1 && [[ -x "${HOME}/.nvm/versions/node/v24.5.0/bin/node" ]]; then
  export PATH="${HOME}/.nvm/versions/node/v24.5.0/bin:${PATH}"
fi

cd "${WEB_DIR}"
E2E_WEB_URL="${PUBLIC_WEB_URL}" \
E2E_SKIP_WEB_SERVER=1 \
  "${PNPM_BIN}" exec playwright test e2e/public-deploy-smoke.spec.ts
