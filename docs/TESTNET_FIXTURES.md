# Testnet Fixtures

This document describes how to maintain reusable vulnerable contracts on Base Sepolia without
turning them into public workbench fixtures.

## Goal

Use a committed manifest of known deployed targets for:

- smoke tests
- screenshots and demos
- repeated operator validation
- deterministic comparisons across releases

Keep these contracts out of the public testnet UI. Public users should still submit real targets via
`deployed_address` or source bundle analysis flows.

## Deployment flow

```bash
cd /home/koita/dev/hackatons/proof-of-audit
PROOF_OF_AUDIT_FIXTURE_RPC_URL="$BASE_SEPOLIA_RPC_URL" \
PROOF_OF_AUDIT_FIXTURE_PRIVATE_KEY="$DEPLOYER_PRIVATE_KEY" \
./scripts/deploy-base-sepolia-fixtures.sh
```

By default this writes:

- `deployments/demo-fixtures.base-sepolia.json`

It deploys the contracts from `demo/fixtures.catalog.json` and records reusable metadata for each
target.

## Manifest shape

The committed manifest keeps the existing fixture fields the deterministic backend already knows how
to consume, and it can safely include extra deployment metadata for operator use.

Example fixture record:

```json
{
  "id": "vulnerable-bank",
  "label": "Vulnerable Bank",
  "contract_name": "VulnerableBank",
  "entry_contract": "VulnerableBank",
  "benchmark_id": "reentrancy-bank",
  "address": "0x1234...",
  "challenge_proof_uri": "ipfs://reentrancy-bank/withdraw-drain",
  "note": "High-confidence reentrancy finding",
  "source_path": "demo/contracts/VulnerableBank.sol",
  "deployment_tx_hash": "0xabc...",
  "deployment_block_number": 123456,
  "deployer_address": "0xdef...",
  "basescan_url": "https://sepolia.basescan.org/address/0x1234..."
}
```

Extra metadata is intentionally allowed here so the manifest is useful both to the deterministic
fixture loader and to human operators reviewing testnet deployments.

## Commit policy

After deploying or refreshing the targets:

1. verify the addresses and tx hashes on BaseScan
2. commit `deployments/demo-fixtures.base-sepolia.json`
3. reference those addresses in smoke tests, docs, or manual test instructions

Do not point `PROOF_OF_AUDIT_DEMO_FIXTURES_FILE` at this manifest for the public testnet API unless
you explicitly want those contracts to appear as selectable fixtures in the workbench.

## Recommended usage

- Use the committed Base Sepolia manifest for automated smoke tests and manual QA.
- Use the local fixture manifest for localhost demos only.
- Keep public testnet UX centered on real contract addresses instead of curated demo targets.
