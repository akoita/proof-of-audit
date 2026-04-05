#!/usr/bin/env bash
# run-multi-agent-demo.sh — Deploy & run N agents end-to-end.
#
# Usage:
#   ./scripts/run-multi-agent-demo.sh [--mode local|hosted] [--skip-deploy] [--skip-watchers]
#
# Local mode (default):
#   1. Start Anvil with prefunded accounts
#   2. Deploy contracts (ProofOfAudit, AgentIdentityRegistry)
#   3. Deploy demo fixture contracts
#   4. Register 5 agent identities from demo/agents.json
#   5. Generate auditor catalog
#   6. Start the API with multi-agent config
#   7. Submit audits from each agent
#   8. Publish claims
#   9. Start cross-agent challenge watchers
#  10. Print summary table
#
# Hosted mode:
#   Connects to GCP-hosted agents via env vars.
#   Requires PROOF_OF_AUDIT_API_URL to point to the hosted API.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"

# ---------- defaults ----------
MODE="${DEMO_MODE:-local}"
SKIP_DEPLOY="${DEMO_SKIP_DEPLOY:-0}"
SKIP_WATCHERS="${DEMO_SKIP_WATCHERS:-0}"
AGENTS_MANIFEST="${DEMO_AGENTS_MANIFEST:-${ROOT_DIR}/demo/agents.json}"

# Anvil / local chain
ANVIL_HOST="${DEMO_ANVIL_HOST:-127.0.0.1}"
ANVIL_PORT="${DEMO_ANVIL_PORT:-8545}"
ANVIL_CHAIN_ID="${DEMO_ANVIL_CHAIN_ID:-31337}"
RPC_URL="http://${ANVIL_HOST}:${ANVIL_PORT}"

# API
API_HOST="${DEMO_API_HOST:-127.0.0.1}"
API_PORT="${DEMO_API_PORT:-8080}"
API_URL="http://${API_HOST}:${API_PORT}"

# Data
DATA_ROOT="${DEMO_DATA_ROOT:-${ROOT_DIR}/.tmp/demo-data}"
LOG_DIR="${DEMO_LOG_DIR:-${ROOT_DIR}/.tmp/demo-logs}"
CONFIG_DIR="${LOG_DIR}/config"
DEPLOYMENT_MANIFEST_FILE="${CONFIG_DIR}/localhost.json"
API_ENV_FILE="${CONFIG_DIR}/api.env.local"
WEB_ENV_FILE="${CONFIG_DIR}/web.env.local"
FIXTURE_MANIFEST_FILE="${CONFIG_DIR}/demo-fixtures.localhost.json"
IDENTITY_MANIFEST_FILE="${CONFIG_DIR}/multi-agent-identities.json"
PYTHON_BIN="${PYTHON_BIN:-python3}"

# Hosted mode overrides
HOSTED_API_URL="${PROOF_OF_AUDIT_API_URL:-}"

# ---------- parse CLI args ----------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode)        MODE="$2"; shift 2 ;;
    --skip-deploy) SKIP_DEPLOY=1; shift ;;
    --skip-watchers) SKIP_WATCHERS=1; shift ;;
    --agents-manifest) AGENTS_MANIFEST="$2"; shift 2 ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

# ---------- colors ----------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

banner() { echo -e "\n${CYAN}${BOLD}═══════════════════════════════════════════════════════${NC}"; echo -e "${CYAN}${BOLD}  $1${NC}"; echo -e "${CYAN}${BOLD}═══════════════════════════════════════════════════════${NC}\n"; }
step()   { echo -e "${BLUE}[STEP]${NC} ${BOLD}$1${NC}"; }
ok()     { echo -e "${GREEN}  ✓${NC} $1"; }
warn()   { echo -e "${YELLOW}  ⚠${NC} $1"; }
fail()   { echo -e "${RED}  ✗${NC} $1"; }

# ---------- setup ----------
mkdir -p "${DATA_ROOT}" "${LOG_DIR}" "${CONFIG_DIR}"

PIDS=()

cleanup() {
  local exit_code=$?
  echo
  step "Cleaning up background processes..."
  for pid in "${PIDS[@]}"; do
    if kill -0 "${pid}" >/dev/null 2>&1; then
      kill "${pid}" >/dev/null 2>&1 || true
      wait "${pid}" >/dev/null 2>&1 || true
    fi
  done
  if [[ ${exit_code} -ne 0 ]]; then
    fail "Demo exited with code ${exit_code}. Check logs in ${LOG_DIR}/"
  fi
  exit "${exit_code}"
}

trap cleanup EXIT INT TERM

wait_for_http() {
  local url="$1"
  local attempts="${2:-60}"
  for _ in $(seq 1 "${attempts}"); do
    if curl -fsS "${url}" >/dev/null 2>&1; then return 0; fi
    sleep 1
  done
  fail "Timed out waiting for ${url}"
  return 1
}

wait_for_rpc() {
  local attempts="${1:-60}"
  for _ in $(seq 1 "${attempts}"); do
    if cast client --rpc-url "${RPC_URL}" >/dev/null 2>&1; then return 0; fi
    sleep 1
  done
  fail "Timed out waiting for RPC at ${RPC_URL}"
  return 1
}

cd "${ROOT_DIR}"

# ╔═══════════════════════════════════════════════════════╗
# ║                  HOSTED MODE                          ║
# ╚═══════════════════════════════════════════════════════╝
if [[ "${MODE}" == "hosted" ]]; then
  banner "Multi-Agent Demo — Hosted Mode (GCP)"

  if [[ -z "${HOSTED_API_URL}" ]]; then
    fail "PROOF_OF_AUDIT_API_URL must be set for hosted mode"
    exit 1
  fi
  API_URL="${HOSTED_API_URL}"

  step "Verifying API connectivity at ${API_URL}..."
  wait_for_http "${API_URL}/health" 10
  ok "API reachable"

  step "Running demo orchestration against hosted API..."
  PYTHONPATH=agent:api "${PYTHON_BIN}" scripts/run-multi-agent-demo.py \
    --api-base "${API_URL}" \
    --agents-manifest "${AGENTS_MANIFEST}" \
    --mode hosted \
    ${SKIP_WATCHERS:+--skip-watchers}

  exit $?
fi

# ╔═══════════════════════════════════════════════════════╗
# ║                  LOCAL MODE                           ║
# ╚═══════════════════════════════════════════════════════╝
banner "Multi-Agent Demo — Local Mode (Anvil)"

echo -e "  Mode:      ${BOLD}${MODE}${NC}"
echo -e "  Agents:    ${BOLD}${AGENTS_MANIFEST}${NC}"
echo -e "  RPC:       ${BOLD}${RPC_URL}${NC}"
echo -e "  API:       ${BOLD}${API_URL}${NC}"
echo -e "  Data:      ${BOLD}${DATA_ROOT}${NC}"
echo -e "  Logs:      ${BOLD}${LOG_DIR}${NC}"
echo

# ────── Step 1: Start Anvil ──────
if [[ "${SKIP_DEPLOY}" != "1" ]]; then
  step "1/9  Starting Anvil (chain ${ANVIL_CHAIN_ID})..."
  rm -rf "${DATA_ROOT}"
  mkdir -p "${DATA_ROOT}"

  ANVIL_HOST="${ANVIL_HOST}" \
  ANVIL_PORT="${ANVIL_PORT}" \
  ANVIL_CHAIN_ID="${ANVIL_CHAIN_ID}" \
  ./scripts/start-anvil.sh >"${LOG_DIR}/anvil.log" 2>&1 &
  PIDS+=($!)
  wait_for_rpc
  ok "Anvil running on ${RPC_URL}"

  # ────── Step 2: Deploy contracts ──────
  step "2/9  Deploying ProofOfAudit contract..."
  ANVIL_RPC_URL="${RPC_URL}" \
  ANVIL_CHAIN_ID="${ANVIL_CHAIN_ID}" \
  PROOF_OF_AUDIT_NETWORK="anvil-demo" \
  PROOF_OF_AUDIT_EXPLORER_BASE_URL="${RPC_URL}" \
  PROOF_OF_AUDIT_API_URL="${API_URL}" \
  PROOF_OF_AUDIT_CHALLENGE_WINDOW_SECONDS="${PROOF_OF_AUDIT_CHALLENGE_WINDOW_SECONDS:-60}" \
  LOCAL_DEPLOYMENT_MANIFEST_FILE="${DEPLOYMENT_MANIFEST_FILE}" \
  LOCAL_DEPLOYMENT_API_ENV_FILE="${API_ENV_FILE}" \
  LOCAL_DEPLOYMENT_WEB_ENV_FILE="${WEB_ENV_FILE}" \
  LOCAL_DEPLOYMENT_FORCE_REDEPLOY=1 \
  ./scripts/deploy-local.sh >"${LOG_DIR}/deploy-local.log" 2>&1
  ok "Contract deployed"

  # ────── Step 3: Deploy demo fixtures ──────
  step "3/9  Deploying demo fixture contracts..."
  ANVIL_RPC_URL="${RPC_URL}" \
  ANVIL_CHAIN_ID="${ANVIL_CHAIN_ID}" \
  PROOF_OF_AUDIT_NETWORK="anvil-demo" \
  LOCAL_DEMO_FIXTURES_MANIFEST_FILE="${FIXTURE_MANIFEST_FILE}" \
  LOCAL_DEMO_FIXTURES_API_ENV_FILE="${API_ENV_FILE}" \
  ./scripts/deploy-demo-fixtures.sh >"${LOG_DIR}/deploy-fixtures.log" 2>&1
  ok "Fixtures deployed"

  # ────── Step 4: Register agent identities ──────
  step "4/9  Registering agent identities on-chain..."

  # Extract the identity registry address from the deploy broadcast
  IDENTITY_REGISTRY_ADDRESS="$(
    "${PYTHON_BIN}" - "${DEPLOYMENT_MANIFEST_FILE}" <<'PY'
import json, sys
from pathlib import Path
data = json.loads(Path(sys.argv[1]).read_text())
# The deploy script deploys both ProofOfAudit and AgentIdentityRegistry.
# Try to extract from manifest extras, or use a default search.
identity_addr = data.get("identity_registry_address", "")
if identity_addr:
    print(identity_addr)
    sys.exit(0)
# If not in manifest, search broadcast for CREATE of AgentIdentityRegistry.
import glob
for f in sorted(glob.glob("contracts/broadcast/DeployProofOfAudit.s.sol/*/run-latest.json")):
    txs = json.loads(Path(f).read_text()).get("transactions", [])
    for tx in txs:
        if tx.get("contractName") == "AgentIdentityRegistry" and tx.get("transactionType") == "CREATE":
            print(tx["contractAddress"])
            sys.exit(0)
print("", file=sys.stderr)
sys.exit(1)
PY
  )" || true

  if [[ -n "${IDENTITY_REGISTRY_ADDRESS:-}" ]]; then
    ADMIN_KEY="0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
    PYTHONPATH=agent:api "${PYTHON_BIN}" scripts/register-multi-agent-identities.py \
      --registry-address "${IDENTITY_REGISTRY_ADDRESS}" \
      --rpc-url "${RPC_URL}" \
      --admin-private-key "${ADMIN_KEY}" \
      --agents-manifest "${AGENTS_MANIFEST}" \
      --output "${IDENTITY_MANIFEST_FILE}" \
      --chain-id "${ANVIL_CHAIN_ID}" \
      --network "anvil-demo" \
      >"${LOG_DIR}/register-identities.log" 2>&1
    ok "Agent identities registered"
  else
    warn "AgentIdentityRegistry not found — skipping identity registration"
  fi

  # ────── Step 5: Generate auditor catalog ──────
  step "5/9  Generating auditor catalog..."
  PYTHONPATH=agent:api "${PYTHON_BIN}" scripts/generate-auditor-catalog.py \
    >"${LOG_DIR}/generate-catalog.log" 2>&1 || warn "Catalog generation skipped (non-fatal)"
  ok "Catalog generated"
else
  step "Skipping deployment (--skip-deploy)"
fi

# ────── Step 6: Start the API ──────
step "6/9  Starting API server..."
CATALOG_FILE="${ROOT_DIR}/deployments/auditor-catalog.json"
(
  set -a
  [[ -f "${API_ENV_FILE}" ]] && source "${API_ENV_FILE}"
  set +a
  PROOF_OF_AUDIT_HOST="${API_HOST}" \
  PROOF_OF_AUDIT_PORT="${API_PORT}" \
  PROOF_OF_AUDIT_DATA_ROOT="${DATA_ROOT}" \
  PROOF_OF_AUDIT_AUDITOR_CATALOG_FILE="${CATALOG_FILE}" \
  PYTHONPATH=agent:api \
  "${PYTHON_BIN}" -m proof_of_audit_api.app
) >"${LOG_DIR}/api.log" 2>&1 &
PIDS+=($!)
wait_for_http "${API_URL}/health"
ok "API running on ${API_URL}"

# ────── Step 7: Run demo orchestration ──────
step "7/9  Running multi-agent audit lifecycle..."
PYTHONPATH=agent:api "${PYTHON_BIN}" scripts/run-multi-agent-demo.py \
  --api-base "${API_URL}" \
  --agents-manifest "${AGENTS_MANIFEST}" \
  --mode local \
  2>&1 | tee "${LOG_DIR}/orchestration.log"

# ────── Step 8: Start watchers ──────
if [[ "${SKIP_WATCHERS}" != "1" ]]; then
  step "8/9  Starting cross-agent watchers..."
  PYTHONPATH=agent:api "${PYTHON_BIN}" scripts/cross_agent_watcher.py \
    --api-base "${API_URL}" \
    --agents-manifest "${AGENTS_MANIFEST}" \
    --all-agents \
    --once \
    2>&1 | tee "${LOG_DIR}/watchers.log"
  ok "Watcher cycle complete"
else
  step "8/9  Skipping watchers (--skip-watchers)"
fi

# ────── Step 9: Summary ──────
step "9/9  Generating summary..."
PYTHONPATH=agent:api "${PYTHON_BIN}" scripts/run-multi-agent-demo.py \
  --api-base "${API_URL}" \
  --agents-manifest "${AGENTS_MANIFEST}" \
  --mode local \
  --summary-only \
  2>&1 | tee -a "${LOG_DIR}/orchestration.log"

banner "Demo Complete"
echo -e "  ${GREEN}All agents have audited, published, and watchers ran.${NC}"
echo -e "  API:  ${BOLD}${API_URL}${NC}"
echo -e "  Logs: ${BOLD}${LOG_DIR}${NC}"
echo
echo -e "  ${CYAN}Press Ctrl+C to stop the stack.${NC}"
echo

# Keep the stack running until interrupted.
wait "${PIDS[@]}" 2>/dev/null || true
