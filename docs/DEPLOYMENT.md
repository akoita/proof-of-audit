# Deployment

## Base Sepolia

Proof-of-Audit is configured to deploy to Base Sepolia with the following defaults:

- network: `base-sepolia`
- chain id: `84532`
- required stake: `0.01 ETH`
- required challenge bond: `0.005 ETH`
- challenge window: `86400` seconds

The deployment manifest lives in `deployments/base-sepolia.json`.

## Required environment variables

Copy `.env.example` into your preferred local secret-loading workflow and set:

- `BASE_SEPOLIA_RPC_URL`
- `BASESCAN_API_KEY`
- `DEPLOYER_PRIVATE_KEY`
- `PROOF_OF_AUDIT_ARBITER`

The API can target the deployed contract with:

- `PROOF_OF_AUDIT_CONTRACT_ADDRESS`
- `PROOF_OF_AUDIT_RPC_URL`
- `PROOF_OF_AUDIT_PRIVATE_KEY`

## Dry run

```bash
cd /home/koita/dev/hackatons/proof-of-audit/contracts
forge script script/DeployProofOfAudit.s.sol:DeployProofOfAudit --rpc-url base_sepolia
```

## Live deploy

```bash
cd /home/koita/dev/hackatons/proof-of-audit
./scripts/deploy-base-sepolia.sh
```

## Current status

The repository is deployment-ready, but no live Base Sepolia contract address is committed yet in this branch because a funded deployer key and RPC credentials were not available in the current environment.
