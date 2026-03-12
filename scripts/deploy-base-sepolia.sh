#!/usr/bin/env bash

set -euo pipefail

: "${BASE_SEPOLIA_RPC_URL:?BASE_SEPOLIA_RPC_URL must be set}"
: "${DEPLOYER_PRIVATE_KEY:?DEPLOYER_PRIVATE_KEY must be set}"
: "${PROOF_OF_AUDIT_ARBITER:?PROOF_OF_AUDIT_ARBITER must be set}"
: "${PROOF_OF_AUDIT_REQUIRED_STAKE_WEI:=10000000000000000}"
: "${PROOF_OF_AUDIT_REQUIRED_CHALLENGE_BOND_WEI:=5000000000000000}"
: "${PROOF_OF_AUDIT_CHALLENGE_WINDOW_SECONDS:=86400}"

cd /home/koita/dev/hackatons/proof-of-audit/contracts

cmd=(
  forge script script/DeployProofOfAudit.s.sol:DeployProofOfAudit
  --rpc-url base_sepolia \
  --private-key "${DEPLOYER_PRIVATE_KEY}" \
  --broadcast
)

if [ -n "${BASESCAN_API_KEY:-}" ]; then
  cmd+=(--verify)
fi

"${cmd[@]}"
