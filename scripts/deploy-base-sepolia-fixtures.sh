#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
NETWORK="${PROOF_OF_AUDIT_FIXTURE_NETWORK:-base-sepolia}"
CHAIN_ID="${PROOF_OF_AUDIT_FIXTURE_CHAIN_ID:-84532}"
RPC_URL="${PROOF_OF_AUDIT_FIXTURE_RPC_URL:-${BASE_SEPOLIA_RPC_URL:-}}"
DEPLOYER_PRIVATE_KEY="${PROOF_OF_AUDIT_FIXTURE_PRIVATE_KEY:-${PROOF_OF_AUDIT_PRIVATE_KEY:-${DEPLOYER_PRIVATE_KEY:-}}}"
VERIFY_API_KEY="${PROOF_OF_AUDIT_FIXTURE_VERIFY_API_KEY:-${PROOF_OF_AUDIT_VERIFY_API_KEY:-${BASESCAN_API_KEY:-}}}"
VERIFY_SOURCIFY="${PROOF_OF_AUDIT_FIXTURE_VERIFY_SOURCIFY:-1}"
VERIFY_BASESCAN="${PROOF_OF_AUDIT_FIXTURE_VERIFY_BASESCAN:-1}"
ALLOW_UNVERIFIED="${PROOF_OF_AUDIT_FIXTURE_ALLOW_UNVERIFIED:-0}"
VERIFY_DRY_RUN="${PROOF_OF_AUDIT_FIXTURE_VERIFY_DRY_RUN:-0}"
CATALOG_FILE="${ROOT_DIR}/demo/fixtures.catalog.json"
MANIFEST_FILE="${PROOF_OF_AUDIT_FIXTURE_MANIFEST_FILE:-${ROOT_DIR}/deployments/demo-fixtures.base-sepolia.json}"
EXPLORER_BASE_URL="${PROOF_OF_AUDIT_FIXTURE_EXPLORER_BASE_URL:-https://sepolia.basescan.org}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
DUAL_RISK_VAULT_OWNER="${PROOF_OF_AUDIT_FIXTURE_DUAL_RISK_VAULT_OWNER:-0x000000000000000000000000000000000000dEaD}"
DUAL_RISK_VAULT_CONSTRUCTOR_ARGS_HEX="$("${PYTHON_BIN}" - "${DUAL_RISK_VAULT_OWNER}" <<'PY'
from __future__ import annotations

import sys

address = sys.argv[1].strip().lower()
if address.startswith("0x"):
    address = address[2:]
if len(address) != 40:
    raise SystemExit("DualRiskVault owner must be a 20-byte address.")
print("0x" + ("0" * 24) + address)
PY
)"

if [[ -z "${RPC_URL}" ]]; then
  echo "Missing PROOF_OF_AUDIT_FIXTURE_RPC_URL or BASE_SEPOLIA_RPC_URL." >&2
  exit 1
fi

if [[ -z "${DEPLOYER_PRIVATE_KEY}" ]]; then
  echo "Missing PROOF_OF_AUDIT_FIXTURE_PRIVATE_KEY, PROOF_OF_AUDIT_PRIVATE_KEY, or DEPLOYER_PRIVATE_KEY." >&2
  exit 1
fi

cast client --rpc-url "${RPC_URL}" >/dev/null 2>&1 || {
  echo "RPC node is not reachable at ${RPC_URL}" >&2
  exit 1
}

TMP_RECORDS_FILE="$(mktemp)"
VERIFY_PROJECT_DIR="$(mktemp -d)"
declare -a UNRESOLVED_CONTRACTS=()
cleanup() {
  rm -f "${TMP_RECORDS_FILE}"
  rm -rf "${VERIFY_PROJECT_DIR}"
}
trap cleanup EXIT
printf '{}\n' >"${TMP_RECORDS_FILE}"

prepare_verification_project() {
  mkdir -p "${VERIFY_PROJECT_DIR}/src"
  cp -R "${ROOT_DIR}/demo/contracts/." "${VERIFY_PROJECT_DIR}/src/"
  cat >"${VERIFY_PROJECT_DIR}/foundry.toml" <<EOF
[profile.default]
src = "src"
test = "test"
script = "script"
out = "out"
libs = []
solc_version = "0.8.28"
optimizer = false
optimizer_runs = 200
via_ir = false
EOF
}

prepare_verification_project

record_deployment() {
  local contract_name="$1"
  local address="$2"
  local tx_hash="$3"
  local block_number="$4"
  local deployer_address="$5"

  "${PYTHON_BIN}" - "${TMP_RECORDS_FILE}" "${contract_name}" "${address}" "${tx_hash}" "${block_number}" "${deployer_address}" "${EXPLORER_BASE_URL}" <<'PY'
from __future__ import annotations

import json
from pathlib import Path
import sys

records_file = Path(sys.argv[1])
contract_name = sys.argv[2]
address = sys.argv[3]
tx_hash = sys.argv[4]
block_number = int(sys.argv[5])
deployer_address = sys.argv[6]
explorer_base_url = sys.argv[7].rstrip("/")

payload = json.loads(records_file.read_text(encoding="utf-8"))
payload[contract_name] = {
    "address": address,
    "deployment_tx_hash": tx_hash,
    "deployment_block_number": block_number,
    "deployer_address": deployer_address,
    "basescan_url": f"{explorer_base_url}/address/{address}",
}
records_file.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
}

record_verification() {
  local contract_name="$1"
  local provider="$2"
  local status="$3"
  local command="$4"
  local reason="${5:-}"
  local verified_at="${6:-}"

  "${PYTHON_BIN}" - "${TMP_RECORDS_FILE}" "${contract_name}" "${provider}" "${status}" "${command}" "${reason}" "${verified_at}" <<'PY'
from __future__ import annotations

import json
from pathlib import Path
import sys

records_file = Path(sys.argv[1])
contract_name = sys.argv[2]
provider = sys.argv[3]
status = sys.argv[4]
command = sys.argv[5]
reason = sys.argv[6].strip()
verified_at = sys.argv[7].strip()

payload = json.loads(records_file.read_text(encoding="utf-8"))
contract_record = payload.setdefault(contract_name, {})
verification = contract_record.setdefault("verification", {})
provider_record = {
    "status": status,
    "command": command,
}
if reason:
    provider_record["reason"] = reason
if verified_at:
    provider_record["verified_at"] = verified_at
verification[provider] = provider_record
records_file.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
}

now_utc() {
  "${PYTHON_BIN}" - <<'PY'
from datetime import UTC, datetime
print(datetime.now(UTC).isoformat())
PY
}

verify_contract_with_provider() {
  local contract_name="$1"
  local provider="$2"
  local address="$3"
  local contract_reference="$4"
  local tx_hash="$5"
  local constructor_args_hex="$6"
  local verification_root="$7"

  local -a verify_cmd
  local -a display_cmd
  local output
  local reason
  local verified_at=""
  local display_command

  case "${provider}" in
    sourcify)
      if [[ "${VERIFY_SOURCIFY}" != "1" ]]; then
        record_verification "${contract_name}" "${provider}" "skipped" "disabled" "Sourcify verification disabled."
        return 1
      fi
      verify_cmd=(
        forge verify-contract
        --root "${verification_root}"
        --chain "${CHAIN_ID}"
        --watch
        --verifier sourcify
        --creation-transaction-hash "${tx_hash}"
        --use 0.8.28
        "${address}"
        "${contract_reference}"
      )
      display_cmd=(
        forge verify-contract
        --root '<generated-demo-foundry-root>'
        --chain "${CHAIN_ID}"
        --watch
        --verifier sourcify
        --creation-transaction-hash "${tx_hash}"
        --use 0.8.28
        "${address}"
        "${contract_reference}"
      )
      ;;
    basescan)
      if [[ "${VERIFY_BASESCAN}" != "1" ]]; then
        record_verification "${contract_name}" "${provider}" "skipped" "disabled" "BaseScan verification disabled."
        return 1
      fi
      if [[ -z "${VERIFY_API_KEY}" ]]; then
        record_verification "${contract_name}" "${provider}" "skipped" "missing-api-key" "BaseScan verification requires PROOF_OF_AUDIT_FIXTURE_VERIFY_API_KEY, PROOF_OF_AUDIT_VERIFY_API_KEY, or BASESCAN_API_KEY."
        return 1
      fi
      verify_cmd=(
        forge verify-contract
        --root "${verification_root}"
        --chain "${CHAIN_ID}"
        --watch
        --verifier etherscan
        --etherscan-api-key "${VERIFY_API_KEY}"
        --use 0.8.28
        "${address}"
        "${contract_reference}"
      )
      display_cmd=(
        forge verify-contract
        --root '<generated-demo-foundry-root>'
        --chain "${CHAIN_ID}"
        --watch
        --verifier etherscan
        --etherscan-api-key '<redacted>'
        --use 0.8.28
        "${address}"
        "${contract_reference}"
      )
      if [[ -n "${constructor_args_hex}" ]]; then
        verify_cmd=(
          forge verify-contract
          --root "${verification_root}"
          --chain "${CHAIN_ID}"
          --watch
          --verifier etherscan
          --etherscan-api-key "${VERIFY_API_KEY}"
          --constructor-args "${constructor_args_hex}"
          --use 0.8.28
          "${address}"
          "${contract_reference}"
        )
        display_cmd=(
          forge verify-contract
          --root '<generated-demo-foundry-root>'
          --chain "${CHAIN_ID}"
          --watch
          --verifier etherscan
          --etherscan-api-key '<redacted>'
          --constructor-args "${constructor_args_hex}"
          --use 0.8.28
          "${address}"
          "${contract_reference}"
        )
      fi
      ;;
    *)
      echo "Unsupported verification provider ${provider}" >&2
      exit 1
      ;;
  esac

  display_command="$(printf '%q ' "${display_cmd[@]}")"
  if [[ "${VERIFY_DRY_RUN}" == "1" ]]; then
    record_verification "${contract_name}" "${provider}" "skipped" "${display_command}" "Verification dry run enabled."
    return 1
  fi

  if output="$(cd "${verification_root}" && "${verify_cmd[@]}" 2>&1)"; then
    echo "${output}" >&2
    verified_at="$(now_utc)"
    record_verification "${contract_name}" "${provider}" "verified" "${display_command}" "" "${verified_at}"
    return 0
  fi

  echo "${output}" >&2
  reason="$(printf '%s\n' "${output}" | tail -n 10 | tr '\n' ' ' | sed 's/[[:space:]]\+/ /g' | sed 's/^ //; s/ $//')"
  if [[ -z "${reason}" ]]; then
    reason="Verification command failed."
  fi
  record_verification "${contract_name}" "${provider}" "failed" "${display_command}" "${reason}"
  return 1
}

verify_contract() {
  local contract_path="$1"
  local contract_name="$2"
  local address="$3"
  local tx_hash="$4"
  local constructor_args_hex="$5"
  local contract_reference="src/$(basename "${contract_path}"):${contract_name}"
  local resolved=0

  if verify_contract_with_provider "${contract_name}" "sourcify" "${address}" "${contract_reference}" "${tx_hash}" "${constructor_args_hex}" "${VERIFY_PROJECT_DIR}"; then
    resolved=1
  fi
  if verify_contract_with_provider "${contract_name}" "basescan" "${address}" "${contract_reference}" "${tx_hash}" "${constructor_args_hex}" "${VERIFY_PROJECT_DIR}"; then
    resolved=1
  fi

  if [[ "${resolved}" != "1" ]]; then
    UNRESOLVED_CONTRACTS+=("${contract_name}@${address}")
  fi
}

deploy_contract() {
  local contract_path="$1"
  local contract_name="$2"
  local constructor_args_hex="$3"
  shift 3
  local output
  local address
  local tx_hash
  local block_number
  local deployer_address

  output="$(
    forge create \
      --root "${ROOT_DIR}" \
      --contracts demo/contracts \
      --use 0.8.28 \
      --rpc-url "${RPC_URL}" \
      --private-key "${DEPLOYER_PRIVATE_KEY}" \
      --broadcast \
      "${contract_path}:${contract_name}" \
      "$@"
  )"
  echo "${output}" >&2

  address="$(printf '%s\n' "${output}" | awk '/Deployed to:/ {print $3}')"
  tx_hash="$(printf '%s\n' "${output}" | awk '/Transaction hash:/ {print $3}')"
  if [[ -z "${address}" || -z "${tx_hash}" ]]; then
    echo "Failed to determine deployed address or tx hash for ${contract_name}" >&2
    exit 1
  fi

  cast code "${address}" --rpc-url "${RPC_URL}" >/dev/null
  block_number="$("${PYTHON_BIN}" - "$(cast receipt "${tx_hash}" --rpc-url "${RPC_URL}" --json)" <<'PY'
from __future__ import annotations

import json
import sys

payload = json.loads(sys.argv[1])
block_number = payload.get("blockNumber")
if isinstance(block_number, str):
    print(int(block_number, 16) if block_number.startswith("0x") else int(block_number))
else:
    print(int(block_number))
PY
)"
  deployer_address="$(cast wallet address --private-key "${DEPLOYER_PRIVATE_KEY}")"

  record_deployment "${contract_name}" "${address}" "${tx_hash}" "${block_number}" "${deployer_address}"
  verify_contract "${contract_path}" "${contract_name}" "${address}" "${tx_hash}" "${constructor_args_hex}"
  printf '%s=%s\n' "${contract_name}" "${address}"
}

echo "Deploying reusable vulnerable targets to ${NETWORK} (${CHAIN_ID}) via ${RPC_URL}..."

deploy_contract "demo/contracts/VulnerableBank.sol" "VulnerableBank" "" >/dev/null
deploy_contract "demo/contracts/AdminSetter.sol" "AdminSetter" "" >/dev/null
deploy_contract "demo/contracts/CleanVault.sol" "CleanVault" "" >/dev/null
deploy_contract \
  "demo/contracts/DualRiskVault.sol" \
  "DualRiskVault" \
  "${DUAL_RISK_VAULT_CONSTRUCTOR_ARGS_HEX}" \
  --constructor-args "${DUAL_RISK_VAULT_OWNER}" >/dev/null
deploy_contract "demo/contracts/UncheckedTreasury.sol" "UncheckedTreasury" "" >/dev/null

cd "${ROOT_DIR}"

"${PYTHON_BIN}" scripts/write-demo-fixtures-manifest.py \
  --catalog-file "${CATALOG_FILE}" \
  --manifest-file "${MANIFEST_FILE}" \
  --api-env-file "${ROOT_DIR}/api/.env.local" \
  --network "${NETWORK}" \
  --chain-id "${CHAIN_ID}" \
  --rpc-url "${RPC_URL}" \
  --deployment-records-file "${TMP_RECORDS_FILE}" \
  --skip-api-env-update

echo
echo "Base Sepolia fixture deployment complete."
echo "Committed manifest target: ${MANIFEST_FILE}"
echo "This script does not enable these contracts as public UI fixtures."
if [[ "${#UNRESOLVED_CONTRACTS[@]}" -gt 0 ]]; then
  printf 'Contracts without verified source: %s\n' "${UNRESOLVED_CONTRACTS[*]}" >&2
  if [[ "${ALLOW_UNVERIFIED}" != "1" ]]; then
    echo "Fixture verification did not produce a usable verified-source provider for every contract." >&2
    echo "Set PROOF_OF_AUDIT_FIXTURE_ALLOW_UNVERIFIED=1 to keep the manifest without failing the script." >&2
    exit 1
  fi
fi
echo "Review and commit ${MANIFEST_FILE} after verifying the deployed contracts on the explorer."
