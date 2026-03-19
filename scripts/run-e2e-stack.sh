#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${E2E_ROOT_DIR:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
ANVIL_HOST="${E2E_ANVIL_HOST:-127.0.0.1}"
ANVIL_PORT="${E2E_ANVIL_PORT:-9545}"
ANVIL_CHAIN_ID="${E2E_ANVIL_CHAIN_ID:-31338}"
API_HOST="${E2E_API_HOST:-127.0.0.1}"
API_PORT="${E2E_API_PORT:-18080}"
WEB_HOST="${E2E_WEB_HOST:-127.0.0.1}"
WEB_PORT="${E2E_WEB_PORT:-3300}"
RPC_URL="http://${ANVIL_HOST}:${ANVIL_PORT}"
API_URL="http://${API_HOST}:${API_PORT}"
WEB_URL="http://${WEB_HOST}:${WEB_PORT}"
DATA_ROOT="${E2E_DATA_ROOT:-${ROOT_DIR}/.tmp/e2e-data}"
LOG_DIR="${E2E_LOG_DIR:-${ROOT_DIR}/.tmp/e2e-logs}"
CONFIG_DIR="${E2E_CONFIG_DIR:-${LOG_DIR}/config}"
DEPLOYMENT_MANIFEST_FILE="${CONFIG_DIR}/localhost.json"
API_ENV_FILE="${CONFIG_DIR}/api.env.local"
WEB_ENV_FILE="${CONFIG_DIR}/web.env.local"
FIXTURE_MANIFEST_FILE="${CONFIG_DIR}/demo-fixtures.localhost.json"
PYTHON_BIN="${PYTHON_BIN:-python}"

mkdir -p "${DATA_ROOT}" "${LOG_DIR}" "${CONFIG_DIR}"
rm -rf "${DATA_ROOT}"
mkdir -p "${DATA_ROOT}"

wait_for_http() {
  local url="$1"
  local attempts="${2:-60}"

  for _ in $(seq 1 "${attempts}"); do
    if curl -fsS "${url}" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done

  echo "Timed out waiting for ${url}" >&2
  return 1
}

wait_for_rpc() {
  local attempts="${1:-60}"

  for _ in $(seq 1 "${attempts}"); do
    if cast client --rpc-url "${RPC_URL}" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done

  echo "Timed out waiting for RPC at ${RPC_URL}" >&2
  return 1
}

cleanup() {
  local exit_code=$?
  for pid in "${WEB_PID:-}" "${API_PID:-}" "${ANVIL_PID:-}"; do
    if [[ -n "${pid}" ]] && kill -0 "${pid}" >/dev/null 2>&1; then
      kill "${pid}" >/dev/null 2>&1 || true
      wait "${pid}" >/dev/null 2>&1 || true
    fi
  done
  exit "${exit_code}"
}

trap cleanup EXIT INT TERM

cd "${ROOT_DIR}"

ANVIL_HOST="${ANVIL_HOST}" \
ANVIL_PORT="${ANVIL_PORT}" \
ANVIL_CHAIN_ID="${ANVIL_CHAIN_ID}" \
./scripts/start-anvil.sh >"${LOG_DIR}/anvil.log" 2>&1 &
ANVIL_PID=$!
wait_for_rpc

ANVIL_RPC_URL="${RPC_URL}" \
ANVIL_CHAIN_ID="${ANVIL_CHAIN_ID}" \
PROOF_OF_AUDIT_NETWORK="anvil-e2e" \
PROOF_OF_AUDIT_EXPLORER_BASE_URL="${RPC_URL}" \
NEXT_PUBLIC_PROOF_OF_AUDIT_API_URL="${API_URL}" \
LOCAL_DEPLOYMENT_MANIFEST_FILE="${DEPLOYMENT_MANIFEST_FILE}" \
LOCAL_DEPLOYMENT_API_ENV_FILE="${API_ENV_FILE}" \
LOCAL_DEPLOYMENT_WEB_ENV_FILE="${WEB_ENV_FILE}" \
./scripts/deploy-local.sh >"${LOG_DIR}/deploy-local.log" 2>&1

ANVIL_RPC_URL="${RPC_URL}" \
ANVIL_CHAIN_ID="${ANVIL_CHAIN_ID}" \
PROOF_OF_AUDIT_NETWORK="anvil-e2e" \
LOCAL_DEMO_FIXTURES_MANIFEST_FILE="${FIXTURE_MANIFEST_FILE}" \
LOCAL_DEMO_FIXTURES_API_ENV_FILE="${API_ENV_FILE}" \
./scripts/deploy-demo-fixtures.sh >"${LOG_DIR}/deploy-fixtures.log" 2>&1

( set -a
  source "${API_ENV_FILE}"
  set +a
  PROOF_OF_AUDIT_HOST="${API_HOST}" \
  PROOF_OF_AUDIT_PORT="${API_PORT}" \
  PROOF_OF_AUDIT_DATA_ROOT="${DATA_ROOT}" \
  PYTHONPATH=agent:api \
  "${PYTHON_BIN}" -m proof_of_audit_api.app
) >"${LOG_DIR}/api.log" 2>&1 &
API_PID=$!
wait_for_http "${API_URL}/health"

(
  cd "${ROOT_DIR}/web"
  set -a
  source "${WEB_ENV_FILE}"
  set +a
  pnpm exec next dev --hostname "${WEB_HOST}" --port "${WEB_PORT}"
) >"${LOG_DIR}/web.log" 2>&1 &
WEB_PID=$!
wait_for_http "${WEB_URL}"

echo "E2E stack ready"
echo "RPC: ${RPC_URL}"
echo "API: ${API_URL}"
echo "WEB: ${WEB_URL}"

wait -n "${ANVIL_PID}" "${API_PID}" "${WEB_PID}"
