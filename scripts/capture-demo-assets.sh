#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
STACK_LOG="${ROOT_DIR}/.tmp/capture-demo-assets.log"

mkdir -p "${ROOT_DIR}/.tmp"

cleanup() {
  local exit_code=$?
  if [[ -n "${STACK_PID:-}" ]] && kill -0 "${STACK_PID}" >/dev/null 2>&1; then
    kill "${STACK_PID}" >/dev/null 2>&1 || true
    wait "${STACK_PID}" >/dev/null 2>&1 || true
  fi
  exit "${exit_code}"
}

trap cleanup EXIT INT TERM

cd "${ROOT_DIR}"

export PYENV_VERSION="${PYENV_VERSION:-proof-of-audit-3.12}"
export PYTHON_BIN="${PYTHON_BIN:-python}"

./scripts/run-e2e-stack.sh >"${STACK_LOG}" 2>&1 &
STACK_PID=$!

for _ in $(seq 1 120); do
  if curl -fsS "http://127.0.0.1:3300" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if ! curl -fsS "http://127.0.0.1:3300" >/dev/null 2>&1; then
  echo "Timed out waiting for the demo web app. See ${STACK_LOG}." >&2
  exit 1
fi

(
  cd "${ROOT_DIR}/web"
  CAPTURE_WEB_URL="http://127.0.0.1:3300" pnpm exec node ./scripts/capture-demo-assets.mjs
)
