#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="/home/koita/dev/hackatons/proof-of-audit"
RPC_URL="${ANVIL_RPC_URL:-http://127.0.0.1:8545}"
CHAIN_ID="${ANVIL_CHAIN_ID:-31337}"
NETWORK="${PROOF_OF_AUDIT_NETWORK:-anvil-local}"
DEPLOYER_PRIVATE_KEY="${LOCAL_DEPLOYER_PRIVATE_KEY:-${DEPLOYER_PRIVATE_KEY:-0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80}}"
CATALOG_FILE="${ROOT_DIR}/demo/fixtures.catalog.json"
MANIFEST_FILE="${ROOT_DIR}/deployments/demo-fixtures.localhost.json"
API_ENV_FILE="${ROOT_DIR}/api/.env.local"

cast client --rpc-url "${RPC_URL}" >/dev/null 2>&1 || {
  echo "Anvil or another RPC node is not reachable at ${RPC_URL}" >&2
  echo "Start it with ./scripts/start-anvil.sh or set ANVIL_RPC_URL." >&2
  exit 1
}

echo "Deploying demo fixtures to local RPC at ${RPC_URL}..."

deploy_contract() {
  local contract_path="$1"
  local contract_name="$2"
  local output
  local address

  output="$(
    forge create \
      --root "${ROOT_DIR}" \
      --contracts demo/contracts \
      --use 0.8.28 \
      --rpc-url "${RPC_URL}" \
      --private-key "${DEPLOYER_PRIVATE_KEY}" \
      --broadcast \
      "${contract_path}:${contract_name}"
  )"
  echo "${output}" >&2
  address="$(printf '%s\n' "${output}" | awk '/Deployed to:/ {print $3}')"
  if [[ -z "${address}" ]]; then
    echo "Failed to determine deployed address for ${contract_name}" >&2
    exit 1
  fi

  cast code "${address}" --rpc-url "${RPC_URL}" >/dev/null
  printf '%s=%s\n' "${contract_name}" "${address}"
}

VULNERABLE_BANK_DEPLOYMENT="$(deploy_contract "demo/contracts/VulnerableBank.sol" "VulnerableBank")"
ADMIN_SETTER_DEPLOYMENT="$(deploy_contract "demo/contracts/AdminSetter.sol" "AdminSetter")"
CLEAN_VAULT_DEPLOYMENT="$(deploy_contract "demo/contracts/CleanVault.sol" "CleanVault")"
UNCHECKED_TREASURY_DEPLOYMENT="$(deploy_contract "demo/contracts/UncheckedTreasury.sol" "UncheckedTreasury")"

cd "${ROOT_DIR}"

python3 scripts/write-demo-fixtures-manifest.py \
  --catalog-file "${CATALOG_FILE}" \
  --manifest-file "${MANIFEST_FILE}" \
  --api-env-file "${API_ENV_FILE}" \
  --network "${NETWORK}" \
  --chain-id "${CHAIN_ID}" \
  --rpc-url "${RPC_URL}" \
  --deployed-contract "${VULNERABLE_BANK_DEPLOYMENT}" \
  --deployed-contract "${ADMIN_SETTER_DEPLOYMENT}" \
  --deployed-contract "${CLEAN_VAULT_DEPLOYMENT}" \
  --deployed-contract "${UNCHECKED_TREASURY_DEPLOYMENT}"

echo
echo "Local demo fixture deployment complete."
echo "Deployed components: demo fixture contracts on the local chain."
echo "Fixture manifest written to: ${MANIFEST_FILE}"
echo "API config updated with fixture manifest path: ${API_ENV_FILE}"
echo "No API or frontend process was started by this script."
