# Documentation

This map helps users, integrators, contributors, and operators find the current system description, task guides, reference material, and project direction. Paths are relative to this repository. The checked-in source describes available behavior; it does not prove that a public deployment runs the same code or configuration.

## Entry

| Need | Start with |
| --- | --- |
| Understand the product and run the local stack | [Project README](../README.md) |
| Contribute code and documentation | [Contribution guide](../CONTRIBUTING.md) |
## Current system

| Document | Role |
| --- | --- |
| [Architecture overview](architecture/overview.md) | Canonical current view of components, transaction boundaries, data, and trust limits. |
| [Technical documentation](TECHNICAL_DOCUMENTATION.md) | Cross-domain technical reference for protocol, contracts, worker, web client, and operations. It complements the architecture overview. |
| [Architecture compatibility entry](ARCHITECTURE.md) | Stable legacy path that points to the current architecture and summarizes the settlement trust boundary. |

The architecture overview describes the system as it exists in the repository. The technical reference and focused documents provide deeper detail for specific interfaces and behaviors. Deployment availability and configuration are tracked separately in the [project state](strategy/STATE_OF_THE_PROJECT.md) and [deployment guide](DEPLOYMENT.md).

## Guides

| Task | Document |
| --- | --- |
| Call the service as an agent | [Agent API](AGENT_API.md) |
| Follow the caller lifecycle | [Agent interaction flow](AGENT_INTERACTION_FLOW.md) |
| Participate in marketplace requests | [Agent request participation](AGENT_REQUEST_PARTICIPATION.md) |
| Run a short product walkthrough | [Demo script](DEMO_SCRIPT.md) |
| Integrate the optional, configuration-dependent Agent-Forge lane | [Agent-Forge integration guide](AGENT_FORGE_SERVICE_INTEGRATION.md) |
| Run symbolic contract checks | [Formal testing](FORMAL_TESTING.md) |
| Use the local security audit hook | [Security audit workflow](SECURITY_AUDIT_WORKFLOW.md) |

## Operations

| Task | Document |
| --- | --- |
| Deploy the local stack and use source-controlled deployment procedures | [Deployment](DEPLOYMENT.md) |
| Operate a separately deployed Agent-Forge service | [Agent-Forge operations](AGENT_FORGE_OPERATIONS.md) |
| Connect to a local Agent-Forge runtime | [Local Agent-Forge guide](LOCAL_AGENT_FORGE.md) |
| Maintain reusable testnet fixtures | [Testnet fixtures](TESTNET_FIXTURES.md) |
| Build and operate the isolated evidence runner | [Evidence runner README](../infra/evidence-runner/README.md) |

## Reference

### System interfaces and policies

| Subject | Reference |
| --- | --- |
| Audit request and settlement protocol in source | [AuditRequest protocol](AUDIT_REQUEST_PROTOCOL.md) |
| Snapshot meaning for deployed-address audits | [Audit snapshot semantics](AUDIT_SNAPSHOT_SEMANTICS.md) |
| Challenger event feed | [Challenger feed](CHALLENGER_FEED.md) |
| Challenge admissibility policy | [Challenge policy grammar](CHALLENGE_POLICY.md) |
| Executable challenge evidence format | [Executable evidence bundle](EXECUTABLE_EVIDENCE_BUNDLE.md) |
| Marketplace payout model and its implementation limits | [Marketplace settlement accounting](MARKETPLACE_SETTLEMENT_ACCOUNTING.md) |
| Independent auditor integration boundary | [Pluggable auditor integration](PLUGGABLE_AUDITOR_INTEGRATION.md) |
| Auditor reputation signals | [Reputation model](REPUTATION_MODEL.md) |
| ERC-8004 alignment claims | [ERC-8004 alignment](ERC8004_ALIGNMENT.md) |
| ERC-8004 registration and discovery | [ERC-8004 registration](ERC8004_REGISTRATION.md) |
| ERC-8004 implementation status | [ERC-8004 roadmap status](ERC8004_ROADMAP.md) |
| End-to-end interaction sequence | [Sequence diagram](SEQUENCE_DIAGRAM.md) |
| Agent-Forge HTTP contract | [Service contract](AGENT_FORGE_SERVICE_CONTRACT.md) and [OpenAPI document](AGENT_FORGE_SERVICE_OPENAPI.yaml) |

### Generated and machine-readable references

| Reference | Authoritative source or purpose |
| --- | --- |
| FastAPI's runtime OpenAPI document at `/openapi.json` | Generated from [API routes](../api/proof_of_audit_api/app.py) and [request/response models](../api/proof_of_audit_api/schemas.py); it is not checked in as a separate snapshot. |
| [Agent-Forge OpenAPI contract](AGENT_FORGE_SERVICE_OPENAPI.yaml) | Checked-in machine-readable service contract; see the [service contract guide](AGENT_FORGE_SERVICE_CONTRACT.md). |
| [Demo agent manifest schema](../demo/agents.schema.json) | Schema for the retained demo/persona manifest at [`demo/agents.json`](../demo/agents.json). This fixture showcase is parked; it is not a product roadmap commitment. |
| [Auditor registration artifact](registrations/proof-of-audit-auditor.json) | Checked-in registration artifact; runtime configuration and API responses remain deployment-specific. |

## Strategy

These documents govern product scope, phase ordering, and technology adoption. Read the [vision](strategy/VISION.md) and [roadmap](strategy/ROADMAP.md) before treating a proposed capability as planned work.

| Subject | Document |
| --- | --- |
| Product purpose and trust-model limits | [Vision](strategy/VISION.md) |
| Positioning and business strategy | [Product strategy](strategy/PRODUCT_STRATEGY.md) |
| Current phase and exit criteria | [Strategy roadmap](strategy/ROADMAP.md) |
| Technology adoption boundaries | [Agentic stack and technology radar](strategy/AGENTIC_STACK.md) |
| Current repository and deployment inventory | [State of the project](strategy/STATE_OF_THE_PROJECT.md) |
| Preserved strategic rulings and dated triage | [Backlog triage](strategy/BACKLOG_TRIAGE.md) |

The roadmap under `docs/strategy/` governs planned work. The older [`docs/ROADMAP.md`](ROADMAP.md) is retained as historical delivery context.

## Proposals and research

Proposal status does not imply approval or adoption. The architecture overview and the source remain the references for current behavior.

| Status | Document | How to read it |
| --- | --- | --- |
| Draft, unapproved | [Release and pilot focus](design/release-and-pilot-focus.md) | Review proposal only; it does not change the adopted roadmap. |
| Partially implemented design | [Challenge Verifier V2](CHALLENGE_VERIFIER_V2.md) | Evidence integrity and bounded execution exist in part; verifier output remains advisory and does not settle a challenge. |
| Parked research | [TEE evidence RFC](TEE_EVIDENCE_RFC.md) | Research record; no TEE implementation is recommended or active. |

## Historical material

Historical documents preserve useful context and dated evidence. They do not describe the current product or prove that a deployment still matches the recorded state.

| Material | Status and contents |
| --- | --- |
| [Hackathon archive index](archive/hackathon-2026/README.md) | Synthesis 2026 demo, judging, strategy, release, and submission material; the archive index links the individual records. |
| [Legacy multi-agent demo](MULTI_AGENT_DEMO.md) | Parked fixture/persona showcase; it is not an active headline product surface. |
| [Hackathon-era roadmap](ROADMAP.md) | Superseded planning snapshot; use the strategy roadmap for current phases. |
| [Base Sepolia smoke evidence, 2026-03-22](proofs/base-sepolia-smoke-2026-03-22.md) | Dated evidence for one historical deployment check, not a current deployment health claim. |
| [Demo assets guide](assets/README.md) | Notes for screenshots and recordings associated with earlier demo material. |

## Maintenance

Update current system descriptions when implementation behavior changes. Keep proposals clearly labeled, preserve historical records as history, and check repository-relative links, source paths, and generated references when editing this map. See the contribution guide's [documentation maintenance rules](../CONTRIBUTING.md#documentation-maintenance).
