#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
CONTRACTS_DIR="${ROOT_DIR}/contracts"
RPC_URL="${ANVIL_RPC_URL:-http://127.0.0.1:8545}"
CHAIN_ID="${ANVIL_CHAIN_ID:-31337}"
NETWORK="${PROOF_OF_AUDIT_NETWORK:-anvil-local}"
EXPLORER_BASE_URL="${PROOF_OF_AUDIT_EXPLORER_BASE_URL:-http://127.0.0.1:8545}"
API_URL="${PROOF_OF_AUDIT_API_URL:-${NEXT_PUBLIC_PROOF_OF_AUDIT_API_URL:-http://127.0.0.1:8080}}"
ARBITER="${PROOF_OF_AUDIT_ARBITER:-0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266}"
TREASURY_ADDRESS="${PROOF_OF_AUDIT_TREASURY_ADDRESS:-${ARBITER}}"
DEPLOYER_PRIVATE_KEY="${LOCAL_DEPLOYER_PRIVATE_KEY:-${DEPLOYER_PRIVATE_KEY:-0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80}}"
CHALLENGER_PRIVATE_KEY="${LOCAL_CHALLENGER_PRIVATE_KEY:-0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d}"
REQUIRED_STAKE_WEI="${PROOF_OF_AUDIT_REQUIRED_STAKE_WEI:-10000000000000000}"
REQUIRED_CHALLENGE_BOND_WEI="${PROOF_OF_AUDIT_REQUIRED_CHALLENGE_BOND_WEI:-5000000000000000}"
CHALLENGE_WINDOW_SECONDS="${PROOF_OF_AUDIT_CHALLENGE_WINDOW_SECONDS:-86400}"
CHALLENGE_RESOLUTION_WINDOW_SECONDS="${PROOF_OF_AUDIT_CHALLENGE_RESOLUTION_WINDOW_SECONDS:-172800}"
PROTOCOL_FEE_BPS="${PROOF_OF_AUDIT_PROTOCOL_FEE_BPS:-0}"
RESOLUTION_FEE_BPS="${PROOF_OF_AUDIT_RESOLUTION_FEE_BPS:-0}"
MANIFEST_FILE="${LOCAL_DEPLOYMENT_MANIFEST_FILE:-${ROOT_DIR}/deployments/localhost.json}"
API_ENV_FILE="${LOCAL_DEPLOYMENT_API_ENV_FILE:-${ROOT_DIR}/api/.env.local}"
WEB_ENV_FILE="${LOCAL_DEPLOYMENT_WEB_ENV_FILE:-${ROOT_DIR}/web/.env.local}"
FORCE_REDEPLOY="${LOCAL_DEPLOYMENT_FORCE_REDEPLOY:-0}"
BROADCAST_FILE="${CONTRACTS_DIR}/broadcast/DeployProofOfAudit.s.sol/${CHAIN_ID}/run-latest.json"
PYTHON_BIN="${PYTHON_BIN:-python3}"

read_existing_manifest_address() {
  "${PYTHON_BIN}" - "${MANIFEST_FILE}" "${CHAIN_ID}" "${RPC_URL}" "${NETWORK}" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
if not path.exists():
    raise SystemExit(1)

data = json.loads(path.read_text(encoding="utf-8"))
if data.get("chain_id") != int(sys.argv[2]):
    raise SystemExit(1)
if data.get("rpc_url") != sys.argv[3]:
    raise SystemExit(1)
if data.get("network") != sys.argv[4]:
    raise SystemExit(1)
address = data.get("address")
if not address:
    raise SystemExit(1)
print(address)
PY
}

existing_deployment_matches() {
  local address="$1"
  local code
  local existing_arbiter
  local existing_stake
  local existing_bond
  local existing_window
  local existing_resolution_window
  local existing_treasury
  local existing_protocol_fee
  local existing_resolution_fee

  code="$(cast code "${address}" --rpc-url "${RPC_URL}" 2>/dev/null || true)"
  [[ -n "${code}" && "${code}" != "0x" ]] || return 1

  existing_arbiter="$(cast call "${address}" "arbiter()(address)" --rpc-url "${RPC_URL}" 2>/dev/null | awk '{print $1}' || true)"
  existing_stake="$(cast call "${address}" "requiredStake()(uint256)" --rpc-url "${RPC_URL}" 2>/dev/null | awk '{print $1}' || true)"
  existing_bond="$(cast call "${address}" "requiredChallengeBond()(uint256)" --rpc-url "${RPC_URL}" 2>/dev/null | awk '{print $1}' || true)"
  existing_window="$(cast call "${address}" "challengeWindow()(uint256)" --rpc-url "${RPC_URL}" 2>/dev/null | awk '{print $1}' || true)"
  existing_resolution_window="$(cast call "${address}" "challengeResolutionWindow()(uint256)" --rpc-url "${RPC_URL}" 2>/dev/null | awk '{print $1}' || true)"
  existing_treasury="$(cast call "${address}" "treasury()(address)" --rpc-url "${RPC_URL}" 2>/dev/null | awk '{print $1}' || true)"
  existing_protocol_fee="$(cast call "${address}" "protocolFeeBps()(uint256)" --rpc-url "${RPC_URL}" 2>/dev/null | awk '{print $1}' || true)"
  existing_resolution_fee="$(cast call "${address}" "resolutionFeeBps()(uint256)" --rpc-url "${RPC_URL}" 2>/dev/null | awk '{print $1}' || true)"

  [[ -n "${existing_arbiter}" && "${existing_arbiter,,}" == "${ARBITER,,}" ]] || return 1
  [[ -n "${existing_treasury}" && "${existing_treasury,,}" == "${TREASURY_ADDRESS,,}" ]] || return 1
  [[ "${existing_stake}" == "${REQUIRED_STAKE_WEI}" ]] || return 1
  [[ "${existing_bond}" == "${REQUIRED_CHALLENGE_BOND_WEI}" ]] || return 1
  [[ "${existing_window}" == "${CHALLENGE_WINDOW_SECONDS}" ]] || return 1
  [[ "${existing_resolution_window}" == "${CHALLENGE_RESOLUTION_WINDOW_SECONDS}" ]] || return 1
  [[ "${existing_protocol_fee}" == "${PROTOCOL_FEE_BPS}" ]] || return 1
  [[ "${existing_resolution_fee}" == "${RESOLUTION_FEE_BPS}" ]] || return 1
}

write_local_outputs() {
  local contract_address="$1"

  "${PYTHON_BIN}" scripts/write-local-config.py \
    --contract-address "${contract_address}" \
    --arbiter "${ARBITER}" \
    --treasury-address "${TREASURY_ADDRESS}" \
    --rpc-url "${RPC_URL}" \
    --chain-id "${CHAIN_ID}" \
    --network "${NETWORK}" \
    --explorer-base-url "${EXPLORER_BASE_URL}" \
    --api-url "${API_URL}" \
    --publisher-private-key "${DEPLOYER_PRIVATE_KEY}" \
    --challenger-private-key "${CHALLENGER_PRIVATE_KEY}" \
    --arbiter-private-key "${DEPLOYER_PRIVATE_KEY}" \
    --required-stake-wei "${REQUIRED_STAKE_WEI}" \
    --required-challenge-bond-wei "${REQUIRED_CHALLENGE_BOND_WEI}" \
    --challenge-window-seconds "${CHALLENGE_WINDOW_SECONDS}" \
    --challenge-resolution-window-seconds "${CHALLENGE_RESOLUTION_WINDOW_SECONDS}" \
    --protocol-fee-bps "${PROTOCOL_FEE_BPS}" \
    --resolution-fee-bps "${RESOLUTION_FEE_BPS}" \
    --deployment-manifest-file "${MANIFEST_FILE}" \
    --api-env-file "${API_ENV_FILE}" \
    --web-env-file "${WEB_ENV_FILE}"
}

cast client --rpc-url "${RPC_URL}" >/dev/null 2>&1 || {
  echo "Anvil or another RPC node is not reachable at ${RPC_URL}" >&2
  echo "Start it with ./scripts/start-anvil.sh or set ANVIL_RPC_URL." >&2
  exit 1
}

if [[ "${FORCE_REDEPLOY}" != "1" ]]; then
  EXISTING_CONTRACT_ADDRESS="$(read_existing_manifest_address || true)"
  if [[ -n "${EXISTING_CONTRACT_ADDRESS:-}" ]] && existing_deployment_matches "${EXISTING_CONTRACT_ADDRESS}"; then
    echo "Reusing existing ProofOfAudit deployment at ${EXISTING_CONTRACT_ADDRESS}."
    write_local_outputs "${EXISTING_CONTRACT_ADDRESS}"
    echo
    echo "Local deployment complete."
    echo "Deployed component: ProofOfAudit smart contract on the local chain."
    echo "Contract address: ${EXISTING_CONTRACT_ADDRESS}"
    echo "Deployment mode: reused existing deployment."
    echo "API config written to: ${API_ENV_FILE}"
    echo "Web config written to: ${WEB_ENV_FILE}"
    echo "Deployment manifest written to: ${MANIFEST_FILE}"
    echo "No API or frontend process was started by this script."
    exit 0
  fi
fi

if [[ "${FORCE_REDEPLOY}" == "1" ]]; then
  echo "Force redeploy requested. Deploying a fresh ProofOfAudit contract to ${RPC_URL}..."
else
  echo "Deploying ProofOfAudit to local RPC at ${RPC_URL}..."
fi

cd "${CONTRACTS_DIR}"

PROOF_OF_AUDIT_ARBITER="${ARBITER}" \
PROOF_OF_AUDIT_TREASURY_ADDRESS="${TREASURY_ADDRESS}" \
PROOF_OF_AUDIT_REQUIRED_STAKE_WEI="${REQUIRED_STAKE_WEI}" \
PROOF_OF_AUDIT_REQUIRED_CHALLENGE_BOND_WEI="${REQUIRED_CHALLENGE_BOND_WEI}" \
PROOF_OF_AUDIT_CHALLENGE_WINDOW_SECONDS="${CHALLENGE_WINDOW_SECONDS}" \
PROOF_OF_AUDIT_CHALLENGE_RESOLUTION_WINDOW_SECONDS="${CHALLENGE_RESOLUTION_WINDOW_SECONDS}" \
PROOF_OF_AUDIT_PROTOCOL_FEE_BPS="${PROTOCOL_FEE_BPS}" \
PROOF_OF_AUDIT_RESOLUTION_FEE_BPS="${RESOLUTION_FEE_BPS}" \
forge script script/DeployProofOfAudit.s.sol:DeployProofOfAudit \
  --rpc-url "${RPC_URL}" \
  --private-key "${DEPLOYER_PRIVATE_KEY}" \
  --broadcast

CONTRACT_ADDRESS="$(
  "${PYTHON_BIN}" - "${BROADCAST_FILE}" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
data = json.loads(path.read_text(encoding="utf-8"))
for tx in data.get("transactions", []):
    if tx.get("transactionType") == "CREATE" and tx.get("contractName") == "ProofOfAudit":
        address = tx.get("contractAddress")
        if address:
            print(address)
            raise SystemExit(0)
raise SystemExit("Could not find deployed ProofOfAudit address in broadcast output")
PY
)"

cast code "${CONTRACT_ADDRESS}" --rpc-url "${RPC_URL}" >/dev/null

cd "${ROOT_DIR}"

write_local_outputs "${CONTRACT_ADDRESS}"

echo
echo "Local deployment complete."
echo "Deployed component: ProofOfAudit smart contract on the local chain."
echo "Contract address: ${CONTRACT_ADDRESS}"
echo "Deployment mode: fresh deployment."
echo "API config written to: ${API_ENV_FILE}"
echo "Web config written to: ${WEB_ENV_FILE}"
echo "Deployment manifest written to: ${MANIFEST_FILE}"
echo "No API or frontend process was started by this script."
