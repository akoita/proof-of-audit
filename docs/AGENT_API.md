# Agent API

This note describes Proof-of-Audit as an agent-callable service rather than a web app.

## What the service does

The service accepts a contract-oriented submission, produces a deterministic review claim, and optionally anchors that claim on-chain with stake.

The service can then:

- expose the claim as a draft audit record
- publish the claim on-chain through `ProofOfAudit`
- open a challenge against the claim
- resolve known cases deterministically
- leave ambiguous cases on a manual fallback path
- mirror the claim and final outcome into an ERC-8004-aligned validation trail

## Discovery flow

An agent caller should start with these endpoints:

1. `GET /auditors`
2. `GET /auditor`
3. `GET /auditor/registration`
4. `GET /config`

Use them for different purposes:

- `GET /auditors`
  - plural discovery record
  - lists all registered auditor services exposed by this API instance
- `GET /auditor`
  - operational discovery record
  - backward-compatible alias for the default auditor service
  - includes API path templates, on-chain agent id, identity source, validation registry metadata, supported submission modes, and resolution modes
- `GET /auditor/registration`
  - stable ERC-8004-aligned registration document
  - includes service endpoints and the `x-proof-of-audit` extension block
- `GET /config`
  - live runtime configuration
  - includes current network, settlement contract, challenge bond, stake amount, and the current auditor service record

## Submission modes

The current service record advertises these `submission_modes`:

- `demo_fixture`
- `deployed_address`
- `source_bundle`
- `repository_url`

Current constraints:

- `demo_fixture`
  - best mode for deterministic local or demo flows
- `deployed_address`
  - best mode for live on-chain publication
- `source_bundle`
  - supported for off-chain claim generation
  - not publishable until deployed
- `repository_url`
  - supports local checkout paths or `file://` URLs
  - can use the optional agent-forge execution lane when worker mode is `hybrid` or `agent_forge`
  - returns execution artifact metadata so callers can inspect the live run context

## Main endpoints

### Create a draft claim

`POST /audits`

Example:

```json
{
  "input_kind": "deployed_address",
  "chain_id": 84532,
  "contract_address": "0x1000000000000000000000000000000000000001",
  "submitted_by": "agent-client"
}
```

Returns:

- a draft audit record
- normalized submission data
- the attached auditor profile
- a deterministic report with findings, summary, and hashes
- optional `execution` metadata when a live agent-forge pass runs or a fallback is recorded

Repository submission example:

```json
{
  "input_kind": "repository_url",
  "repository_url": "file:///home/koita/dev/example-vault",
  "entry_contract": "Vault",
  "submitted_by": "agent-client"
}
```

### Read claim state

`GET /audits/{id}`

Use this after every mutation. The returned record is the source of truth for:

- `status`
- `execution`
- `onchain`
- `challenge`
- `validation`

### Compare claims on one target

Use either:

- `GET /targets/{address}/audits`
- `GET /targets/{address}/comparison`

The comparison endpoint adds a compact summary layer so callers can inspect how many claims exist for a target, how many are published, challenged, or resolved, and what the highest reported severity is before drilling into individual records.

### Publish a claim on-chain

`POST /audits/{id}/publish`

Example:

```json
{
  "stake_wei": 10000000000000000
}
```

Preconditions:

- the audit must be in `draft`
- the submission must be publishable
- API-side chain configuration must be loaded

On success, the record moves to:

- `status: "published"`

And gains:

- `onchain.publish_tx_hash`
- `onchain.audit_id`
- `validation.request_hash`
- `validation.request_uri`

### Open a challenge

`POST /audits/{id}/challenge`

Example:

```json
{
  "proof_uri": "ipfs://reentrancy-bank/withdraw-drain",
  "challenger": "agent-challenger"
}
```

Preconditions:

- the audit must already be `published`
- only one challenge is allowed per audit in the current model

On success, one of two things happens:

- deterministic case:
  - audit moves directly to `resolved`
  - challenge includes `resolution_path: "deterministic"`
  - validation response is submitted
- ambiguous case:
  - audit moves to `challenged`
  - challenge stays `opened`
  - validation request remains open until fallback resolution

### Resolve a fallback case

`POST /audits/{id}/resolve`

Example:

```json
{
  "upheld": true,
  "resolved_by": "arbiter-operator"
}
```

Use this only for cases that remain on the manual fallback path.

### Read validation documents

These endpoints expose the ERC-8004-aligned bridge artifacts:

- `GET /audits/{id}/validation/request`
- `GET /audits/{id}/validation/response`

Interpretation:

- request document
  - present after publish when validation mirroring is configured
- response document
  - present only after a final resolved outcome has been mirrored

## Status model

Top-level audit lifecycle:

- `draft`
- `published`
- `challenged`
- `resolved`

Challenge lifecycle:

- `opened`
- `upheld`
- `rejected`

Resolution path:

- `deterministic`
- `manual_fallback`

Validation lifecycle:

- `requested`
- `responded`
- `request_failed`
- `response_failed`
- `request_unavailable`
- `response_unavailable`

## Trust model for agent callers

Another agent should interpret the service as follows:

- the report itself is deterministic and benchmark-oriented
- repository-style local inputs can optionally run through an agent-forge-backed live execution path
- the economically meaningful claim starts at `publish`
- the canonical settlement truth is the native `ProofOfAudit` contract
- the validation bridge is an interoperability mirror, not the payout engine
- deterministic resolution is preferred when the evidence is known and reproducible
- manual fallback exists for ambiguous evidence only

## Error model

Common structured error types:

- `validation_error`
- `invalid_payload`
- `audit_not_found`
- `onchain_not_configured`
- `publish_failed`
- `challenge_failed`
- `resolve_failed`

Agent callers should treat non-2xx responses as terminal for that mutation and refetch the audit record only when the mutation may have partially succeeded on-chain.
