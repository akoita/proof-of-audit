#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="/home/koita/dev/hackatons/proof-of-audit"
CONTRACTS_DIR="${ROOT_DIR}/contracts"
RPC_URL="${ANVIL_RPC_URL:-http://127.0.0.1:8545}"
CHAIN_ID="${ANVIL_CHAIN_ID:-31337}"
NETWORK="${PROOF_OF_AUDIT_NETWORK:-anvil-local}"
EXPLORER_BASE_URL="${PROOF_OF_AUDIT_EXPLORER_BASE_URL:-http://127.0.0.1:8545}"
API_URL="${NEXT_PUBLIC_PROOF_OF_AUDIT_API_URL:-http://127.0.0.1:8080}"
ARBITER="${PROOF_OF_AUDIT_ARBITER:-0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266}"
DEPLOYER_PRIVATE_KEY="${LOCAL_DEPLOYER_PRIVATE_KEY:-${DEPLOYER_PRIVATE_KEY:-0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80}}"
REQUIRED_STAKE_WEI="${PROOF_OF_AUDIT_REQUIRED_STAKE_WEI:-10000000000000000}"
REQUIRED_CHALLENGE_BOND_WEI="${PROOF_OF_AUDIT_REQUIRED_CHALLENGE_BOND_WEI:-5000000000000000}"
CHALLENGE_WINDOW_SECONDS="${PROOF_OF_AUDIT_CHALLENGE_WINDOW_SECONDS:-86400}"
BROADCAST_FILE="${CONTRACTS_DIR}/broadcast/DeployProofOfAudit.s.sol/${CHAIN_ID}/run-latest.json"

cast client --rpc-url "${RPC_URL}" >/dev/null 2>&1 || {
  echo "Anvil or another RPC node is not reachable at ${RPC_URL}" >&2
  echo "Start it with ./scripts/start-anvil.sh or set ANVIL_RPC_URL." >&2
  exit 1
}

echo "Deploying ProofOfAudit to local RPC at ${RPC_URL}..."

cd "${CONTRACTS_DIR}"

PROOF_OF_AUDIT_ARBITER="${ARBITER}" \
PROOF_OF_AUDIT_REQUIRED_STAKE_WEI="${REQUIRED_STAKE_WEI}" \
PROOF_OF_AUDIT_REQUIRED_CHALLENGE_BOND_WEI="${REQUIRED_CHALLENGE_BOND_WEI}" \
PROOF_OF_AUDIT_CHALLENGE_WINDOW_SECONDS="${CHALLENGE_WINDOW_SECONDS}" \
forge script script/DeployProofOfAudit.s.sol:DeployProofOfAudit \
  --rpc-url "${RPC_URL}" \
  --private-key "${DEPLOYER_PRIVATE_KEY}" \
  --broadcast

CONTRACT_ADDRESS="$(
  python3 - "${BROADCAST_FILE}" <<'PY'
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

python3 scripts/write-local-config.py \
  --contract-address "${CONTRACT_ADDRESS}" \
  --arbiter "${ARBITER}" \
  --rpc-url "${RPC_URL}" \
  --chain-id "${CHAIN_ID}" \
  --network "${NETWORK}" \
  --explorer-base-url "${EXPLORER_BASE_URL}" \
  --api-url "${API_URL}" \
  --required-stake-wei "${REQUIRED_STAKE_WEI}" \
  --required-challenge-bond-wei "${REQUIRED_CHALLENGE_BOND_WEI}" \
  --challenge-window-seconds "${CHALLENGE_WINDOW_SECONDS}"

echo
echo "Local deployment complete."
echo "Deployed component: ProofOfAudit smart contract on the local chain."
echo "Contract address: ${CONTRACT_ADDRESS}"
echo "API config written to: ${ROOT_DIR}/api/.env.local"
echo "Web config written to: ${ROOT_DIR}/web/.env.local"
echo "Deployment manifest written to: ${ROOT_DIR}/deployments/localhost.json"
echo "No API or frontend process was started by this script."
