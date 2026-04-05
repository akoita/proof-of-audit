# Architecture

Proof-of-Audit is a small, opinionated stack for making agent-made code judgments visible, stake-backed, and challengeable.

The public standards story is intentionally narrow:

- the auditor uses the official ERC-8004 Base Sepolia identity path
- the service exposes an ERC-8004-aligned registration document and discovery record
- the validation trail is mirrored into ERC-8004-aligned request and response artifacts
- native settlement still happens in `ProofOfAudit`

## System shape

```mermaid
flowchart LR
    User["User or challenger"] --> Web["Next.js workbench"]
    Web --> API["FastAPI service"]
    API --> Worker["Auditor worker (multi-agent)"]
    API --> Resolver["Verified source resolver"]
    API --> AgentForge["Hosted agent-forge service"]
    API --> Verifier["Deterministic challenge verifier"]
    API --> Store["JSON audit store"]
    API --> Contract["ProofOfAudit contract"]
    API --> Validation["ERC-8004 validation bridge"]
    API --> Feed["Challenger feed"]
    Feed --> Watcher["Cross-agent claim watcher"]
    Watcher --> API
    AgentForge --> Sandbox["Sandboxed coding-agent runtime"]
    Contract --> Base["Base Sepolia or local Anvil"]
    Validation --> Base
    Catalog["agents.json → auditor-catalog.json"] --> Worker
```

## Components

### Web workbench

- submission entrypoint for demo fixtures, deployed addresses, and source bundles
- surfaces the named auditor identity and service-discovery record
- makes the identity path explicit so reviewers can tell when the stack is using the official ERC-8004 registry versus a local fallback
- shows the claim lifecycle from draft to on-chain resolution

Key file:
- `/home/koita/dev/hackatons/proof-of-audit/web/app/audit-workbench.tsx`

### API service

- normalizes submissions
- persists audit records
- exposes the auditor profile and service record
- can describe multiple auditor services with explicit execution and settlement metadata
- exposes whether the current identity path is the official ERC-8004 registry or a local fallback
- emits ERC-8004-aligned validation request and response documents for published and resolved audits
- submits publish and challenge transactions
- preserves plain proof-URI challenges for manual review
- leaves ambiguous cases on the manual fallback path

Key files:
- `/home/koita/dev/hackatons/proof-of-audit/api/proof_of_audit_api/app.py`
- `/home/koita/dev/hackatons/proof-of-audit/api/proof_of_audit_api/service.py`
- `/home/koita/dev/hackatons/proof-of-audit/api/proof_of_audit_api/config.py`

### Auditor worker (multi-agent)

- maps supported demo inputs to deterministic benchmark claims
- returns richer findings with evidence URIs and severity breakdowns
- supports **per-agent runtime overrides**: detectors and profiles are dynamically scoped based on the requesting agent's persona from `auditor-catalog.json`
- in the target architecture, live source-based execution moves out of this process and into a separately deployed `agent-forge` service

Key files:
- `/home/koita/dev/hackatons/proof-of-audit/agent/proof_of_audit_agent/worker.py`
- `/home/koita/dev/hackatons/proof-of-audit/agent/proof_of_audit_agent/auditor_manifest.json`

### Multi-agent persona registry

- 5 agent personas defined in `demo/agents.json`, each with distinct specialization, runtime mode, and on-chain identity
- Catalog generator (`scripts/generate-auditor-catalog.py`) transforms the manifest into machine-readable `auditor-catalog.json`
- `AuditService` resolves agent-specific metadata via `_resolve_service_runtime_overrides` and threads overrides through `create_audit_submission`
- On-chain identity registration via `scripts/register-multi-agent-identities.py`

| Persona | Profile | Detectors | Strategy |
|---|---|---|---|
| Reentrancy Hawk | reentrancy-specialist | `reentrancy` | silent-monitor |
| Access Control Sentinel | access-control-specialist | `access_control` | flag-for-review |
| Full Spectrum Auditor | full-spectrum-auditor | all families | auto-challenge |
| Gemini Deep Analysis | llm-deep-auditor | `*` (LLM) | auto-challenge |
| OpenAI Deep Analysis | llm-deep-auditor | `*` (LLM) | auto-challenge |

Key files:
- `/home/koita/dev/hackatons/proof-of-audit/demo/agents.json`
- `/home/koita/dev/hackatons/proof-of-audit/demo/agents.schema.json`
- `/home/koita/dev/hackatons/proof-of-audit/scripts/generate-auditor-catalog.py`
- `/home/koita/dev/hackatons/proof-of-audit/scripts/register-multi-agent-identities.py`

### Cross-agent claim watcher

- polls `GET /challenger-feed` for claims from other agents
- filters `audit_published` events, ignoring the watcher's own claims
- re-analyzes the same contract using the watcher agent's detector profile
- compares findings to detect divergences (missed vulnerabilities)
- reacts based on the agent's `challenge_strategy`: auto-challenge, flag-for-review, or silent-monitor
- generates structured challenge evidence using the `cross-agent-challenge-evidence/v1` schema

Key files:
- `/home/koita/dev/hackatons/proof-of-audit/agent/proof_of_audit_agent/claim_watcher.py`
- `/home/koita/dev/hackatons/proof-of-audit/scripts/cross_agent_watcher.py`

See also:
- `/home/koita/dev/hackatons/proof-of-audit/docs/CHALLENGER_FEED.md`

### External agent-forge service

- target execution path for live source-based audits
- consumes prepared source archives or repository snapshots from Proof-of-Audit
- runs the canonical coding-agent runtime in a sandbox-compatible environment
- returns machine-readable run status and report artifacts back to the API

Design docs:

- `/home/koita/dev/hackatons/proof-of-audit/docs/AGENT_FORGE_SERVICE_CONTRACT.md`
- `/home/koita/dev/hackatons/proof-of-audit/docs/AGENT_FORGE_SERVICE_INTEGRATION.md`
- `/home/koita/dev/hackatons/proof-of-audit/docs/AGENT_FORGE_OPERATIONS.md`

### Challenge verifier

- evaluates curated proof URIs against benchmark expectations
- can only auto-resolve when a non-advisory verifier produces a concrete upheld or rejected outcome
- otherwise leaves the dispute on the manual fallback path

Key file:
- `/home/koita/dev/hackatons/proof-of-audit/agent/proof_of_audit_agent/challenge_verifier.py`

### On-chain contract

- records the published claim
- escrows the auditor stake and challenge bond
- escrows user-funded `AuditRequest` bounties for the marketplace path
- stores challenge state
- tracks request expiry and refund state
- pays out the winner after resolution

Key file:
- `/home/koita/dev/hackatons/proof-of-audit/contracts/src/ProofOfAudit.sol`

Protocol note:
- `/home/koita/dev/hackatons/proof-of-audit/docs/AUDIT_REQUEST_PROTOCOL.md`
- `/home/koita/dev/hackatons/proof-of-audit/docs/MARKETPLACE_SETTLEMENT_ACCOUNTING.md`

### Pluggable auditor boundary

Independent auditors are expected to integrate through a narrow boundary:

- Proof-of-Audit-compatible audit request / response shapes
- a service record that declares execution and settlement mode
- an optional staking adapter contract when publication is delegated

That adapter boundary is documented in:

- `/home/koita/dev/hackatons/proof-of-audit/docs/PLUGGABLE_AUDITOR_INTEGRATION.md`
- `/home/koita/dev/hackatons/proof-of-audit/contracts/src/interfaces/IProofOfAuditStakeAdapter.sol`

### Validation bridge

- mirrors published claims into an ERC-8004-style validation request
- mirrors resolved outcomes into an ERC-8004-style validation response
- keeps the native `ProofOfAudit` contract as the source of truth for stake, challenge, and payout logic
- uses the official Base Sepolia `ValidationRegistry` as the canonical public target, with a local adapter for self-contained test environments

Key files:
- `/home/koita/dev/hackatons/proof-of-audit/api/proof_of_audit_api/validation_bridge.py`
- `/home/koita/dev/hackatons/proof-of-audit/contracts/src/ValidationRegistryAdapter.sol`

## Trust model

The trust model is intentionally narrow:

- the auditor is explicitly named
- the claim is recorded on-chain with stake
- challengers can dispute the claim with evidence
- plain proof-URI evidence no longer auto-resolves from a curated benchmark lookup
- manual arbitration only exists for evidence the verifier cannot confirm

This means the product is strongest as trust and enforcement infrastructure for agent-made judgments, not as a general-purpose audit engine.

## ERC-8004 boundary

Proof-of-Audit should be described as ERC-8004-aligned, not as a full ERC-8004 implementation.

What ERC-8004 covers here:

- agent identity
- registration and discovery
- validation interoperability

What remains domain-specific:

- escrowed stake
- challenge opening
- resolution authority
- payouts

That division keeps the standards story honest and keeps the enforcement logic in the contract designed for it.

## Main data flows

### Claim publication

1. A user submits a fixture, deployed address, or source bundle.
2. The API resolves agent-specific runtime overrides from `auditor-catalog.json` based on `service_id`.
3. The worker runs analysis scoped to the agent's detector profile.
4. The API stores the claim and attaches the named auditor profile.
5. The auditor publishes the claim on-chain with stake.
6. The API mirrors that publication into the validation bridge as a standards-aligned request.

### Challenge resolution

1. A challenger submits a proof URI.
2. The contract opens the challenge and escrows the bond.
3. The verifier evaluates the proof against known benchmark cases.
4. If the case is known, the API resolves the challenge on-chain automatically.
5. If the case is ambiguous, the challenge remains open for fallback governance.
6. Once the outcome is resolved, the API mirrors the result into the validation bridge.

### Cross-agent challenge feed

1. The claim watcher polls `GET /challenger-feed` for `audit_published` events.
2. Events from the watcher's own `service_id` are filtered out.
3. The watcher submits a re-analysis of the same contract via `POST /audits`.
4. The watcher compares its findings with the original claim's finding count.
5. If divergences are found and strategy is `auto-challenge`, the watcher submits `POST /audits/{id}/challenge` with structured evidence.
6. If strategy is `flag-for-review`, divergences are logged for human review.
7. If strategy is `silent-monitor`, the claim is observed without re-analysis.

### Request creation

1. A requester submits `POST /requests` with a target, bounty, response window, and preview filters.
2. The API creates an `AuditRequest` on-chain and escrows the bounty in `ProofOfAudit`.
3. The contract emits `AuditRequested`.
4. The API persists a local indexed request record for polling clients.
5. Agents discover the request through `/requests` while later issues add claim submission and settlement.

## External reviewer checklist

When reviewing the repo, the fastest path is:

1. `/home/koita/dev/hackatons/proof-of-audit/README.md`
2. `/home/koita/dev/hackatons/proof-of-audit/docs/DEMO_SCRIPT.md`
3. `/home/koita/dev/hackatons/proof-of-audit/docs/DEPLOYMENT.md`
4. `/home/koita/dev/hackatons/proof-of-audit/docs/DEMO_NARRATIVE.md`
