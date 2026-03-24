# Submission UX

This document defines the recommended input UX for Proof-of-Audit across two environments:

- local development and demos
- hosted SaaS usage

The goal is to keep the happy path simple without boxing the product into "single address only" workflows, while keeping the auditor visible as a named agent service instead of an anonymous backend.

## Recommendation

Use a two-tier submission model:

1. Local demo UX
   - lead with `Demo fixtures`
   - support `Deployed address`
   - keep `Source bundle` as an advanced path
2. SaaS UX
   - lead with `On-chain address`
   - support `Source bundle upload`
   - add `Repository URL` later as an async workflow, not the default path

This gives the product a clean default for both demos and real usage:

- demos feel instant and reproducible
- public-chain users can submit one address quickly
- teams with private or multi-contract codebases can submit source code directly

## Current implementation status

The current repo now ships the first step of this model:

- local web and API flows support `demo_fixture`
- local web and API flows support `deployed_address`
- local web and API flows support `source_bundle`
- `repository_url` is reserved in the normalized schema but intentionally not exposed in the UI or publish path yet

Current behavior notes:

- `demo_fixture` resolves to a live local contract address from the generated fixture manifest
- `source_bundle` produces a deterministic off-chain report and cannot be published on-chain until the bundle is deployed and resubmitted as a deployed address
- `repository_url` remains a later async workflow

## Why not choose only one input mode

Each input mode is useful, but none should be the only path:

- `Address only`
  - best when a contract is already deployed and verified
  - weak when the audit target is a multi-contract repo or not yet deployed
- `Zip/source bundle`
  - best when the user has the full codebase and wants source-aware analysis
  - adds friction for casual users and public contract lookups
- `Repository URL`
  - useful for repeated audits and asynchronous imports
  - weak as a first-run UX because it introduces cloning, auth, and build-tool ambiguity

## Local UX

For local development, the top-level input should be:

1. `Demo fixtures`
2. `Deployed address`
3. `Source bundle (advanced)`

### Demo fixtures

This should be the default local path.

The repo should include a small fixture suite under `demo/` with:

- one vulnerable bank fixture
- one access-control fixture
- one clean fixture
- one small multi-contract fixture with imports or inheritance

Recommended local helper:

- `./scripts/deploy-demo-fixtures.sh`

That script should:

- deploy the fixture contracts to Anvil
- write a machine-readable manifest such as `deployments/demo-fixtures.localhost.json`
- update ignored local config so the web app can show the live fixture addresses

Recommended UI copy:

- `Use demo fixture`
- `Audit deployed address`
- `Upload source bundle`

This keeps the local demo strong because the user can click a real fixture instead of pasting an address from memory.

For public testnet or Base Sepolia environments, do not expose these fixtures in the workbench UI.
Treat them as reusable operator assets instead: deploy them once, commit a manifest such as
`deployments/demo-fixtures.base-sepolia.json`, and submit them through the normal
`deployed_address` path when you need repeatable live-chain targets.

### Deployed address

This should remain the second local path.

Use it when:

- the developer already deployed a contract set locally
- the goal is to test on-chain metadata and publication flows

For multi-contract systems, the input should still begin with a single address, but the UI should ask for:

- target chain
- target contract address
- optional `entry contract name`
- optional `source bundle`

The address identifies the primary target. The optional source bundle gives the agent richer context when there are dependencies or internal libraries outside verified metadata.

### Source bundle

This should be available locally but not as the first thing a new user sees.

Recommended accepted forms:

- `.zip` archive
- local directory path in the CLI or API

Expected contents:

- Solidity sources
- dependency lockfiles or vendored dependencies when required
- optional manifest describing the intended entry contract and compiler settings

Recommended normalized fields:

- `input_kind`
- `entry_contract`
- `compiler_version`
- `framework`
- `source_archive_uri`

## SaaS UX

For hosted usage, the top-level input should be:

1. `On-chain address`
2. `Source bundle upload`
3. `Repository URL (beta, async)`

### On-chain address

This should be the default SaaS path because it is the lowest-friction workflow.

The form should ask for:

- chain
- contract address

Then the backend should try to enrich automatically from:

- Sourcify
- block explorer verified sources
- ABI and metadata when available

If verified source retrieval succeeds, the user gets a fast audit without needing to upload anything else.

If verified source retrieval fails, the UI should immediately offer:

- `Upload source bundle for deeper analysis`

This is the best default UX for users who "just want to use the product."

### Source bundle upload

This should be the fallback for:

- unverified contracts
- private codebases
- pre-deployment reviews
- multi-contract systems where repository context matters

For SaaS, a zip upload is the most robust v1 format because it avoids early Git provider integration complexity.

Recommended upload constraints:

- one zip per submission
- optional `entry contract`
- optional `contracts root`
- optional `README` or build metadata

### Repository URL

This is useful, but it should be a later asynchronous flow rather than the primary UX.

It works best when:

- the repo is public
- the user wants recurring audits
- the system can queue a job and report results later

Tradeoffs:

- provider auth
- monorepo path discovery
- dependency installation
- branch and commit selection
- larger security surface

Because of those tradeoffs, repository import should be framed as:

- `Import from repository (beta)`

Not as the first-run submission path.

## Recommended product shape

The most balanced v1/v2 path is:

### Local

- default: demo fixtures
- secondary: deployed address
- advanced: source bundle

### SaaS

- default: on-chain address with automatic verified-source fetch
- fallback: source bundle upload
- later: repository URL import

## Suggested API evolution

The API should evolve from address-only submission to a normalized request model:

```json
{
  "input_kind": "deployed_address",
  "chain_id": 84532,
  "contract_address": "0x...",
  "entry_contract": "Vault",
  "submitted_by": "web-demo",
  "source_bundle_uri": null,
  "repository_url": null
}
```

Valid `input_kind` values should eventually include:

- `demo_fixture`
- `deployed_address`
- `source_bundle`
- `repository_url`

That keeps the audit pipeline explicit while allowing the UI to add richer modes without breaking the backend contract.

## Next implementation steps

1. Add verified-source retrieval for public address submissions.
2. Replace URI-only source-bundle entry with real zip upload handling.
3. Add compiler and framework metadata capture for source-bundle submissions.
4. Introduce `repository_url` as an asynchronous import flow.
5. Let a deployed-address submission attach optional fetched or uploaded source context.
