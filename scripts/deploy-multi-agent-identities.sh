#!/usr/bin/env bash
# deploy-multi-agent-identities.sh
#
# Deploys an AgentIdentityRegistry (if not already present) and registers
# N agent identities from demo/agents.json.
#
# Supports both:
#   - Local (Anvil): uses Anvil prefunded accounts
#   - Hosted (Base Sepolia / GCP): uses env-supplied keys
#
# Usage:
#   ./scripts/deploy-multi-agent-identities.sh          # local Anvil
#   PROOF_OF_AUDIT_NETWORK=base-sepolia \
#     BASE_SEPOLIA_RPC_URL=https://... \
#     DEPLOYER_PRIVATE_KEY=0x... \
#     ./scripts/deploy-multi-agent-identities.sh        # hosted

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
CONTRACTS_DIR="${ROOT_DIR}/contracts"
PYTHON_BIN="${PYTHON_BIN:-python3}"

NETWORK="${PROOF_OF_AUDIT_NETWORK:-anvil-local}"
CHAIN_ID="${PROOF_OF_AUDIT_CHAIN_ID:-31337}"
RPC_URL="${PROOF_OF_AUDIT_RPC_URL:-${ANVIL_RPC_URL:-http://127.0.0.1:8545}}"
AGENTS_MANIFEST="${PROOF_OF_AUDIT_AGENTS_MANIFEST:-${ROOT_DIR}/demo/agents.json}"
OUTPUT="${PROOF_OF_AUDIT_MULTI_AGENT_OUTPUT:-${ROOT_DIR}/deployments/multi-agent-identities.${NETWORK/\//-}.json}"
FUND_AMOUNT_WEI="${PROOF_OF_AUDIT_AGENT_FUND_WEI:-100000000000000000}"

# Anvil account 0 (deployer / admin) default
DEPLOYER_PRIVATE_KEY="${DEPLOYER_PRIVATE_KEY:-0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80}"

# If the contract manifest has an existing registry, read it
DEPLOYMENT_MANIFEST="${ROOT_DIR}/deployments/${NETWORK/\//-}.json"
EXISTING_REGISTRY=""
if [[ -f "${DEPLOYMENT_MANIFEST}" ]]; then
  EXISTING_REGISTRY="$(
    "${PYTHON_BIN}" -c "
import json, sys
p = json.loads(open('${DEPLOYMENT_MANIFEST}').read())
ai = p.get('auditor_identity', {})
print(ai.get('registry_address') or '')
" 2>/dev/null || true
  )"
fi

REGISTRY_ADDRESS="${PROOF_OF_AUDIT_AGENT_REGISTRY:-${EXISTING_REGISTRY:-}}"

# -------------------------------------------------------------------
# Deploy a new AgentIdentityRegistry if no address is provided
# -------------------------------------------------------------------
if [[ -z "${REGISTRY_ADDRESS}" ]]; then
  echo "No existing AgentIdentityRegistry found. Deploying a new one..."

  DEPLOYER_ADDRESS="$(cast wallet address --private-key "${DEPLOYER_PRIVATE_KEY}")"
  AGENT_REGISTRY_ADMIN="${PROOF_OF_AUDIT_AGENT_REGISTRY_ADMIN:-${DEPLOYER_ADDRESS}}"

  cast client --rpc-url "${RPC_URL}" >/dev/null 2>&1 || {
    echo "RPC node is not reachable at ${RPC_URL}" >&2
    exit 1
  }

  cd "${CONTRACTS_DIR}"

  PROOF_OF_AUDIT_AGENT_REGISTRY_ADMIN="${AGENT_REGISTRY_ADMIN}" \
  forge script script/DeployAgentIdentityRegistry.s.sol:DeployAgentIdentityRegistry \
    --rpc-url "${RPC_URL}" \
    --private-key "${DEPLOYER_PRIVATE_KEY}" \
    --broadcast

  DEPLOY_BROADCAST="${CONTRACTS_DIR}/broadcast/DeployAgentIdentityRegistry.s.sol/${CHAIN_ID}/run-latest.json"
  REGISTRY_ADDRESS="$(
    "${PYTHON_BIN}" - "${DEPLOY_BROADCAST}" <<'PY'
import json, sys
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
for tx in data.get("transactions", []):
    if tx.get("transactionType") == "CREATE" and tx.get("contractName") == "AgentIdentityRegistry":
        print(tx.get("contractAddress") or "")
        raise SystemExit(0)
raise SystemExit("Could not find deployed AgentIdentityRegistry in broadcast output")
PY
  )"

  echo "AgentIdentityRegistry deployed at: ${REGISTRY_ADDRESS}"
  cd "${ROOT_DIR}"
else
  echo "Using existing AgentIdentityRegistry: ${REGISTRY_ADDRESS}"
fi

# Verify registry is live
cast code "${REGISTRY_ADDRESS}" --rpc-url "${RPC_URL}" >/dev/null || {
  echo "Registry not found at ${REGISTRY_ADDRESS}" >&2
  exit 1
}

# -------------------------------------------------------------------
# Register all agent identities
# -------------------------------------------------------------------
"${PYTHON_BIN}" "${ROOT_DIR}/scripts/register-multi-agent-identities.py" \
  --registry-address "${REGISTRY_ADDRESS}" \
  --rpc-url "${RPC_URL}" \
  --admin-private-key "${DEPLOYER_PRIVATE_KEY}" \
  --agents-manifest "${AGENTS_MANIFEST}" \
  --output "${OUTPUT}" \
  --fund-amount-wei "${FUND_AMOUNT_WEI}" \
  --deployer-private-key "${DEPLOYER_PRIVATE_KEY}" \
  --network "${NETWORK}" \
  --chain-id "${CHAIN_ID}"

echo
echo "Multi-agent identity deployment complete."
echo "  Network:  ${NETWORK} (chain ${CHAIN_ID})"
echo "  Registry: ${REGISTRY_ADDRESS}"
echo "  Manifest: ${OUTPUT}"
