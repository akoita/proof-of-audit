# Deployment

## Localhost with Anvil

The fastest local development loop is:

1. start Anvil
2. deploy `ProofOfAudit` to localhost
3. deploy the demo fixtures to localhost
4. let the deployment scripts write fresh local config for the API and web app
5. run the API and frontend against those generated values

### Condensed local flow

```bash
# 0. Start the local chain
cd /home/koita/dev/hackatons/proof-of-audit
./scripts/start-anvil.sh

# 1. Deploy the ProofOfAudit contract to Anvil and sync local app config
./scripts/deploy-local.sh

# 2. Deploy the demo fixtures and write the local fixture manifest
./scripts/deploy-demo-fixtures.sh

# 3. Start the API (loads api/.env.local automatically)
PYENV_VERSION=proof-of-audit-3.12 PYTHONPATH=agent:api python -m proof_of_audit_api.app

# 4. Start the frontend in a separate terminal (loads web/.env.local automatically)
cd /home/koita/dev/hackatons/proof-of-audit/web
pnpm dev
```

### Start Anvil

```bash
cd /home/koita/dev/hackatons/proof-of-audit
./scripts/start-anvil.sh
```

Defaults:

- RPC URL: `http://127.0.0.1:8545`
- chain id: `31337`
- deployer key: first default Anvil key, unless overridden
- arbiter: first default Anvil account, unless overridden

### Deploy locally and sync config

```bash
cd /home/koita/dev/hackatons/proof-of-audit
./scripts/deploy-local.sh
```

This script:

- deploys the `ProofOfAudit` smart contract to the running local Anvil chain
- verifies that bytecode exists at the deployed address
- writes `deployments/localhost.json`
- writes `api/.env.local`
- writes `web/.env.local`
- includes the localhost publisher and arbiter private keys in `api/.env.local` so the API can submit real local publish, challenge, and resolve transactions

Generated files are ignored by Git and are meant for local development only.

This script does not:

- start Anvil
- start the API server
- start the frontend dev server
- deploy backend or frontend services

It only handles the on-chain localhost deployment plus local config synchronization for the dependent app components.

### Deploy local demo fixtures

```bash
cd /home/koita/dev/hackatons/proof-of-audit
./scripts/deploy-demo-fixtures.sh
```

This script:

- deploys the demo fixture contracts to the running local Anvil chain
- verifies that bytecode exists at the deployed addresses
- writes `deployments/demo-fixtures.localhost.json`
- updates `api/.env.local` with `PROOF_OF_AUDIT_DEMO_FIXTURES_FILE`

This script does not:

- start Anvil
- start the API server
- start the frontend dev server
- deploy backend or frontend services

It only handles local demo fixture deployment and fixture manifest synchronization.

### Run the API against the generated local config

```bash
cd /home/koita/dev/hackatons/proof-of-audit
PYENV_VERSION=proof-of-audit-3.12 PYTHONPATH=agent:api python -m proof_of_audit_api.app
```

The API automatically loads `api/.env.local` if it exists.

### Run the frontend against the generated local config

```bash
cd /home/koita/dev/hackatons/proof-of-audit/web
pnpm dev
```

Next.js automatically loads `web/.env.local`.

### Local overrides

You can override defaults without committing secrets:

```bash
export ANVIL_RPC_URL=http://127.0.0.1:8545
export PROOF_OF_AUDIT_ARBITER=0xYourLocalArbiter
export LOCAL_DEPLOYER_PRIVATE_KEY=0xYourLocalPrivateKey
./scripts/deploy-local.sh
```

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
- `PROOF_OF_AUDIT_ARBITER_PRIVATE_KEY`

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
