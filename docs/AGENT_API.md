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
  - includes an explainable `reputation` block for each auditor
- `GET /auditor`
  - operational discovery record
  - backward-compatible alias for the default auditor service
  - includes API path templates, on-chain agent id, identity source, validation and reputation registry metadata, supported submission modes, and resolution modes
- `GET /auditor/registration`
  - stable ERC-8004-aligned registration document
  - includes service endpoints and the `x-proof-of-audit` extension block
- `GET /config`
  - live runtime configuration
  - includes current network, settlement contract, challenge bond, stake amount, marketplace fee parameters, and the current auditor service record

For marketplace-style participation loops, the service also exposes:

- `POST /requests`
  - creates an on-chain `AuditRequest` bounty escrow through the settlement contract
  - persists a local indexed record with tx metadata and request filters for polling clients
- `GET /requests?status=open`
  - lists indexed request records that an agent can poll
  - includes bounty, response window, eligibility filter metadata, and request-level settlement fields when on-chain settlement has progressed
- `GET /requests/{id}`
  - returns one indexed request record
  - re-syncs chain-backed request state and settlement metadata when on-chain access is configured
- `POST /requests/{id}/claims`
  - submits an existing draft audit as a request-bound on-chain claim
  - uses the auditor service's canonical `(agentRegistry, agentId)` identity
- `GET /requests/{id}/claims`
  - lists request-bound claims indexed by this API instance
  - includes claim-level settlement eligibility and payout previews after request finalization
- `GET /requests/{id}/eligibility?auditor=<service-id>`
  - evaluates one auditor against the request filters before the agent spends capacity on a claim

## Submission modes

The current service record advertises these `submission_modes`:

- `demo_fixture`
- `deployed_address`
- `source_bundle`
- `repository_url`

For pluggable auditors, the service record also declares how the auditor executes
and settles claims:

- `execution_mode`
  - `local_worker` for the built-in worker path
  - `remote_http` for a remote auditor service
- `execution_endpoint`
  - optional endpoint for a remote execution service
- `settlement_mode`
  - `native_proof_of_audit` when the native contract is the settlement target
  - `adapter_delegated` when publication happens through an auditor-owned adapter
- `publication_mode`
  - `api_mediated` when this application is allowed to publish the selected claim
  - `self_published` when the external auditor must publish itself
- `staking_adapter_kind`
- `staking_adapter_address`
- `staking_adapter_method`
- `publication_scope`

These fields are meant to tell integrators whether a listed auditor is local,
remote, directly settled, or adapter-settled before they attempt submission.

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
- for `deployed_address` submissions, a captured chain snapshot:
  - `submission.snapshot_block_number`
  - `submission.snapshot_block_hash`
  - `submission.target_code_hash_at_snapshot`
  - proxy identity fields when applicable:
    - `submission.proxy_kind`
    - `submission.proxy_resolution_status`
    - `submission.proxy_resolution_detail`
    - `submission.implementation_address_at_snapshot`
    - `submission.implementation_code_hash_at_snapshot`
- the attached auditor profile
- a deterministic report with findings, summary, and hashes
- optional `execution` metadata when a live agent-forge pass runs or a fallback is recorded

Proxy support notes:

- v1 resolves EIP-1967 implementation-slot proxies
- that covers the common Transparent/UUPS-style layout
- EIP-1967 beacon proxies are detected but marked as unsupported, so callers can
  see that the target identity guarantee is weaker

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

### Create a marketplace request

`POST /requests`

Example:

```json
{
  "contract_address": "0x1000000000000000000000000000000000000001",
  "bounty_wei": 2000000000000000000,
  "response_window_seconds": 3600,
  "filters": {
    "whitelist_mode": "allowlist",
    "allowed_service_ids": ["proof-of-audit-auditor"]
  }
}
```

Returns:

- the on-chain `request_id`
- requester address
- escrowed bounty
- response-window metadata
- settlement counters plus requester-refund preview fields once the request has
  entered the finalization path
- tx hash and explorer URL
- the indexed request filters used by polling clients
- the resolved allowlisted auditor addresses and on-chain eligibility snapshot in
  `metadata`

Filter behavior:

- `allowed_service_ids` is an API convenience input; the API resolves each listed
  service's canonical identity to its current owner address and snapshots those
  addresses into the on-chain request allowlist
- `required_identity_service_id` is resolved to the service's canonical
  `(agentRegistry, agentId)` pair before the request is created
- explicit `required_identity_registry` and `required_identity_agent_id` must match
  the resolved service identity if both are supplied

### Submit a request-bound claim

`POST /requests/{id}/claims`

Example:

```json
{
  "audit_id": "draft-audit-id",
  "stake_wei": 10000000000000000,
  "challenge_policy": {
    "allowed_evidence_types": ["deterministic_fixture"],
    "min_severity_threshold": "medium",
    "allow_informational_only": false,
    "requires_material_incorrectness": true,
    "admissibility_mode": "strict"
  }
}
```

This path:

- reuses an existing draft audit record
- publishes its hashes into the request-bound claim path
- enforces one claim per canonical auditor identity per request
- enforces minimum stake, request allowlist membership, and required registered
  identity on-chain at claim submission time
- persists a machine-readable `challenge_policy` onto the published claim record
- preserves the legacy `POST /audits/{id}/publish` path for non-marketplace publication

The stored claim metadata now includes `challenge_policy`, and the same policy is
copied into claim-facing metadata documents so verifiers and downstream clients
can inspect the admissibility scope without reinterpreting prose.

Request-bound claim state can now move through:

- `submitted`
- `challenged`
- `slashed`
- `resolved`

For V1 cross-auditor settlement:

- an upheld competing-auditor challenge marks the claim `slashed`
- a rejected competing-auditor challenge marks the claim `resolved`
- `slashed` means the claim is no longer eligible for later bounty distribution

After request settlement is finalized, `GET /requests/{id}/claims` also exposes:

- `eligible_for_bounty`
- `settlement_withdrawn`
- `bounty_share_wei`
- `settlement_payout_wei`

Request detail now also exposes finalized fee/accounting fields when available:

- `protocol_fee_wei`
- `eligible_claim_count`
- `eligible_stake_wei`
- `distributable_bounty_wei`
- `requester_refund_available`
- `requester_refund_wei`

## Reputation

Discovery records now include a `reputation` block with:

- a backward-compatible aggregate `score`
- separate `challenge_openness_score` and `challenge_accuracy_score`
- explicit admissible-vs-inadmissible challenge counters
- formula metadata for the aggregate, openness, and accuracy calculations
- when configured, on-chain reputation registry metadata and cumulative staked value

You can also read the current summary directly:

- `GET /auditor/reputation`
- `GET /auditors/{id}/reputation`

See [Reputation model](./REPUTATION_MODEL.md) for the full explanation and caveats.

### Publish a claim on-chain

`POST /audits/{id}/publish`

Example:

```json
{
  "stake_wei": 10000000000000000,
  "challenge_policy": {
    "allowed_evidence_types": ["deterministic_fixture", "executable_test"],
    "min_severity_threshold": "info",
    "allow_informational_only": true,
    "requires_material_incorrectness": false,
    "admissibility_mode": "broad"
  }
}
```

Preconditions:

- the audit must be in `draft`
- the submission must be publishable
- API-side chain configuration must be loaded
- for `deployed_address` submissions, the live target code must still match the
  code hash captured at audit start; otherwise publish is rejected and a fresh
  audit is required
- if the draft resolved a supported proxy implementation at audit start, the
  live implementation address and implementation code hash must still match at
  publish time

On success, the record moves to:

- `status: "published"`

And gains:

- `onchain.publish_tx_hash`
- `onchain.audit_id`
- `onchain.snapshot_block_number`
- `onchain.snapshot_block_hash`
- `onchain.target_code_hash_at_snapshot`
- `onchain.proxy_kind`
- `onchain.proxy_resolution_status`
- `onchain.proxy_resolution_detail`
- `onchain.implementation_address_at_snapshot`
- `onchain.implementation_code_hash_at_snapshot`
- `onchain.challenge_policy`
- `validation.request_hash`
- `validation.request_uri`
- `reputation_trail.claim_hash`
- `reputation_trail.claim_uri`

The validation-request and reputation-claim documents also expose the effective
`challengePolicy` for the published claim, along with the snapshot metadata that
binds the claim to a specific chain state.

### Open a challenge

`POST /audits/{id}/challenge`

Example:

```json
{
  "proof_uri": "ipfs://reentrancy-bank/withdraw-drain",
  "challenger": "agent-challenger"
}
```

This same endpoint is also how callers challenge a published request-bound claim.
Use `GET /requests/{id}/claims` to find the claim's backing `audit_id`, then call
`POST /audits/{audit_id}/challenge`.

Executable evidence example:

```json
{
  "proof_uri": "file:///tmp/ChallengeEvidence.t.sol",
  "evidence_type": "executable_test",
  "execution_env": "foundry",
  "evidence_manifest": {
    "bundle_format": "proof-of-audit-executable-evidence/v1",
    "execution_env": "foundry",
    "entrypoint": "ChallengeEvidence.t.sol",
    "target_chain_id": 31337,
    "test_contract": "ChallengeEvidenceTest"
  },
  "challenger": "agent-challenger"
}
```

Preconditions:

- the audit must already be `published`
- only one challenge is allowed per audit in the current model

On success:

- the audit normally moves to `challenged`
- the challenge stays `opened`
- plain `proof_uri` evidence is recorded for manual review
- validation and reputation resolution stay pending until an arbiter resolves the case

For request-bound claims, this still uses the same verifier and policy-admissibility
pipeline, but the on-chain dispute target is the claim's `request_claim_id`
instead of the legacy single-auditor `audit_id`.

Challenge verification now performs a second pass against the published
`challenge_policy` before any final resolution logic runs:

- inadmissible challenges expose `challenge.policy_admissibility_status`
- the verifier dossier mirrors that as `policy.admissibility_status`
- the verifier dossier also includes `policy.effective_policy`
- inadmissible challenges are distinct from admissible-but-unsuccessful challenges
- inadmissible challenges cannot be manually resolved as `upheld`

Only non-advisory verifier paths can auto-resolve on-chain, and the built-in
deterministic benchmark verifier has been retired.

Executable evidence notes:

- executable evidence is still advisory-only in the current model
- callers should treat `evidence_manifest` as the canonical execution description
- executable challenges now commit `evidence_hash` on-chain from canonical evidence content, while `proof_uri` remains only the locator
- for published `deployed_address` claims, executable challenges default to the
  claim snapshot block even when the caller omits `pinned_block_number`
- if the caller supplies `pinned_block_number`, it must equal the published
  claim snapshot block or the challenge is rejected
- the runner fetches remote evidence before execution and executes only validated local materialized files
- the runner re-hashes fetched executable evidence and rejects execution if it no longer matches the committed on-chain hash
- `ipfs://` is the primary remote URI path for executable evidence
- archive extraction is guarded by size, file-count, extension, symlink, and path-traversal checks
- the API host may execute advisory Foundry evidence either through the local subprocess backend or an explicitly configured Docker backend
- the Docker backend runs with a read-only evidence mount, `--cap-drop=ALL`, `--security-opt=no-new-privileges:true`, explicit `--network`, and bounded CPU / memory / PID limits
- production-oriented deployments may also offload advisory Foundry execution to a dedicated Cloud Run runner service through the `gcp_cloud_run` backend
- the Cloud Run backend sends the validated evidence root as an archive to a separate runner endpoint and records the resulting stdout / stderr back into the advisory verification log
- when configured, the Cloud Run backend stages the archive through GCS first and sends the runner a `gs://` object reference instead of embedding the entire zip in the request body

See [Executable evidence bundle format](./EXECUTABLE_EVIDENCE_BUNDLE.md) for the manifest shape and backward-compatibility rules.
See [Challenge policy grammar](./CHALLENGE_POLICY.md) for the supported
machine-checkable fields and explicit out-of-scope cases.

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

For request-bound claims:

- `upheld` resolves the dispute by slashing the challenged claim
- `rejected` resolves the dispute without slashing the challenged claim

### Read validation documents

These endpoints expose the ERC-8004-aligned bridge artifacts:

- `GET /audits/{id}/validation/request`
- `GET /audits/{id}/validation/response`

These endpoints expose the reputation accumulator artifacts:

- `GET /audits/{id}/reputation/claim`
- `GET /audits/{id}/reputation/resolution`

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
- plain proof-URI evidence opens a challenge for manual review by default
- automatic resolution exists only for non-advisory verifier paths

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
