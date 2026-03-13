#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
CONTRACTS_DIR="${ROOT_DIR}/contracts"
PYTHON_BIN="${PYTHON_BIN:-python3}"

NETWORK="${PROOF_OF_AUDIT_DEPLOY_NETWORK:-base-sepolia}"
CHAIN_ID="${PROOF_OF_AUDIT_DEPLOY_CHAIN_ID:-84532}"
RPC_URL="${PROOF_OF_AUDIT_DEPLOY_RPC_URL:-${BASE_SEPOLIA_RPC_URL:-}}"
EXPLORER_BASE_URL="${PROOF_OF_AUDIT_EXPLORER_BASE_URL:-https://sepolia.basescan.org}"
MANIFEST_FILE="${PROOF_OF_AUDIT_DEPLOYMENT_MANIFEST_FILE:-${ROOT_DIR}/deployments/${NETWORK}.json}"
DEPLOY_VERIFY="${PROOF_OF_AUDIT_DEPLOY_VERIFY:-0}"

DEPLOYER_PRIVATE_KEY="${DEPLOYER_PRIVATE_KEY:-}"
ARBITER="${PROOF_OF_AUDIT_ARBITER:-}"
REQUIRED_STAKE_WEI="${PROOF_OF_AUDIT_REQUIRED_STAKE_WEI:-10000000000000000}"
REQUIRED_CHALLENGE_BOND_WEI="${PROOF_OF_AUDIT_REQUIRED_CHALLENGE_BOND_WEI:-5000000000000000}"
CHALLENGE_WINDOW_SECONDS="${PROOF_OF_AUDIT_CHALLENGE_WINDOW_SECONDS:-86400}"

: "${RPC_URL:?PROOF_OF_AUDIT_DEPLOY_RPC_URL or BASE_SEPOLIA_RPC_URL must be set}"
: "${DEPLOYER_PRIVATE_KEY:?DEPLOYER_PRIVATE_KEY must be set}"
: "${ARBITER:?PROOF_OF_AUDIT_ARBITER must be set}"

BROADCAST_FILE="${CONTRACTS_DIR}/broadcast/DeployProofOfAudit.s.sol/${CHAIN_ID}/run-latest.json"
CONSTRUCTOR_ARGS_JSON="$(
  printf '{"arbiter":"%s","required_stake_wei":"%s","required_challenge_bond_wei":"%s","challenge_window_seconds":%s}' \
    "${ARBITER}" \
    "${REQUIRED_STAKE_WEI}" \
    "${REQUIRED_CHALLENGE_BOND_WEI}" \
    "${CHALLENGE_WINDOW_SECONDS}"
)"
CONSTRUCTOR_ARGS_HEX="$(
  cast abi-encode "constructor(address,uint256,uint256,uint256)" \
    "${ARBITER}" \
    "${REQUIRED_STAKE_WEI}" \
    "${REQUIRED_CHALLENGE_BOND_WEI}" \
    "${CHALLENGE_WINDOW_SECONDS}"
)"

cd "${CONTRACTS_DIR}"

PROOF_OF_AUDIT_ARBITER="${ARBITER}" \
PROOF_OF_AUDIT_REQUIRED_STAKE_WEI="${REQUIRED_STAKE_WEI}" \
PROOF_OF_AUDIT_REQUIRED_CHALLENGE_BOND_WEI="${REQUIRED_CHALLENGE_BOND_WEI}" \
PROOF_OF_AUDIT_CHALLENGE_WINDOW_SECONDS="${CHALLENGE_WINDOW_SECONDS}" \
forge script script/DeployProofOfAudit.s.sol:DeployProofOfAudit \
  --rpc-url "${RPC_URL}" \
  --private-key "${DEPLOYER_PRIVATE_KEY}" \
  --broadcast

read -r CONTRACT_ADDRESS DEPLOYMENT_TX_HASH DEPLOYMENT_BLOCK_NUMBER DEPLOYER_ADDRESS < <(
  "${PYTHON_BIN}" - "${BROADCAST_FILE}" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
for tx, receipt in zip(payload.get("transactions", []), payload.get("receipts", [])):
    if tx.get("transactionType") == "CREATE" and tx.get("contractName") == "ProofOfAudit":
        print(
            tx.get("contractAddress") or "",
            tx.get("hash") or "",
            str(int(receipt.get("blockNumber", "0x0"), 16)),
            tx.get("transaction", {}).get("from") or "",
        )
        raise SystemExit(0)
raise SystemExit("Could not find deployed ProofOfAudit address in broadcast output")
PY
)

cast code "${CONTRACT_ADDRESS}" --rpc-url "${RPC_URL}" >/dev/null

cd "${ROOT_DIR}"

"${PYTHON_BIN}" "${ROOT_DIR}/scripts/write-release-manifest.py" \
  --manifest-file "${MANIFEST_FILE}" \
  --contract-name "ProofOfAudit" \
  --network "${NETWORK}" \
  --chain-id "${CHAIN_ID}" \
  --address "${CONTRACT_ADDRESS}" \
  --status "deployed" \
  --arbiter "${ARBITER}" \
  --rpc-url "${RPC_URL}" \
  --explorer-base-url "${EXPLORER_BASE_URL}" \
  --required-stake-wei "${REQUIRED_STAKE_WEI}" \
  --required-challenge-bond-wei "${REQUIRED_CHALLENGE_BOND_WEI}" \
  --challenge-window-seconds "${CHALLENGE_WINDOW_SECONDS}" \
  --deployment-tx-hash "${DEPLOYMENT_TX_HASH}" \
  --deployment-block-number "${DEPLOYMENT_BLOCK_NUMBER}" \
  --deployer-address "${DEPLOYER_ADDRESS}" \
  --constructor-args-json "${CONSTRUCTOR_ARGS_JSON}" \
  --constructor-args-hex "${CONSTRUCTOR_ARGS_HEX}" \
  --verification-status "not_requested" \
  --verification-provider "basescan" \
  --notes "Deployed via scripts/deploy-release.sh"

echo
echo "Release deployment complete."
echo "Network: ${NETWORK} (chain ${CHAIN_ID})"
echo "Contract: ProofOfAudit"
echo "Address: ${CONTRACT_ADDRESS}"
echo "Deployment tx: ${DEPLOYMENT_TX_HASH}"
echo "Manifest: ${MANIFEST_FILE}"

if [[ "${DEPLOY_VERIFY}" == "1" ]]; then
  "${ROOT_DIR}/scripts/verify-release.sh"
fi
