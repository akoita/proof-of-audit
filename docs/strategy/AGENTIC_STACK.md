# Agentic Architecture & Technology Radar (July 2026)

Companion to [VISION.md](./VISION.md) and [ROADMAP.md](./ROADMAP.md). This document
answers two questions at once: *where do agentic frameworks (ADK, LangGraph, CrewAI,
MCP, A2A, …) genuinely fit this project?* and *how do we honor the maintainer's dual
mandate* — the project is both a product and a public upskilling/branding vehicle —
*without letting résumé-driven choices erode the product?*

## The dual mandate, made explicit

This project deliberately serves two goals:

1. **Product value** — trust infrastructure for machine-made code judgments.
2. **Maintainer growth & branding** — staying sharp on trending agentic concepts and
   demonstrating them publicly.

Both are legitimate. The failure mode is letting goal 2 masquerade as goal 1 (the
hackathon's persona-theater was exactly that). The rule that reconciles them:

> **A technology may enter the repo for upskilling/branding reasons — but only in a
> layer where it cannot damage product credibility, and never when it adds zero value
> there. If a technology adds no value anywhere, it stays out, however trendy.**

## The three-layer containment model

The pluggable-auditor boundary (Phase 1 centerpiece) is what makes the dual mandate
safe. It splits the system into layers with different technology rules:

| Layer | Contents | Technology rule |
| --- | --- | --- |
| **Trust & settlement** | `ProofOfAudit.sol`, escrow, challenge windows, evidence hash verification, sandboxed Foundry replays, the API's on-chain publishing | **Boring by design. No agent frameworks, ever.** This layer's entire value is determinism and auditability. An accountability protocol built on framework churn refutes itself. |
| **Intelligence** | The audit engine (agent-forge v2), challenge-claim extraction, semantic triage | **Agentic frameworks welcome — behind the pluggable HTTP contract.** Multi-step tool-using LLM workflows are exactly what these frameworks exist for. Framework churn here never touches the trust layer. |
| **Interop & distribution** | ERC-8004, MCP, A2A, x402 | **Protocols, not frameworks. Adopt aggressively.** The buyers of Phase 4 are agents; speaking their protocols *is* distribution. |

## Radar

### Adopt (real product value + strong branding)

- **Google ADK — for the audit engine (agent-forge v2).** A real audit engine is a
  stateful, tool-using, multi-step agent: ingest repo → static analysis tools
  (Slither, forge build) → hypothesis loop (write PoC test, run on fork, observe) →
  structured `proof-of-audit-report-v1` output. That is ADK's exact shape. Concrete
  added value over the hand-rolled ReAct loop: the **eval framework**
  (final-response + trajectory evals — this directly powers the "publish EVMbench
  numbers" credibility artifact), session/state management, tool abstraction,
  Cloud Run/Agent Engine deployment (already our GCP stack), and Cloud Trace
  observability. Branding: consistent with the maintainer's ADK track record
  (resonate-agentic); "early ADK expertise" is a differentiated position.
  **Containment: ADK lives in the agent-forge repo, behind the HTTP contract —
  proof-of-audit itself never imports it.**
- **MCP server — expose Proof-of-Audit as tools.** `get_bonded_audit_status`,
  `list_auditor_track_record`, `request_audit`, `submit_challenge_evidence`. Cheap
  to build on the existing FastAPI service, immediately demoable in any MCP client,
  and it *is* the Phase 4 distribution thesis (agents as consumers) arriving early.
  High branding value, genuine product value, near-zero risk. Do it in Phase 1–2.
- **Evals & observability as a public artifact.** Whatever the engine framework:
  benchmark harness (EVMbench + the verifier corpus), trajectory evals, and
  published traces/dossiers. In a trust product, evals are not internal tooling —
  they are marketing. (ADK evals if ADK; Langfuse/Phoenix acceptable alternates.)

### Trial (probable value — validate with a bounded experiment)

- **A2A protocol AgentCard for the auditor.** ERC-8004 registration documents are
  AgentCard-shaped already; publishing a compliant A2A card + endpoint makes the
  auditor discoverable/callable by the broader agent ecosystem and strengthens the
  standards story. Bounded: one card + one endpoint, no rearchitecture.
- **x402-paid attestation reads.** Already Phase 4 in the roadmap; a thin early
  spike (one paid endpoint) is a fair upskilling exercise with real strategic
  information value (is anyone paying?).
- **LangGraph — as the *alternative* engine framework.** Job-market visibility is
  higher than ADK's. Acceptable substitute if the maintainer wants that signal —
  but pick **one** engine framework, not two. A second engine built on LangGraph
  only becomes interesting later, as a genuinely independent second auditor
  identity staking on our own rails (which is product-honest: real independent
  engines, not personas).

### Hold (no adoption without new evidence)

- **TEE / EigenCompute for evidence-runner integrity** — the RFC's no-go stands;
  revisit at ladder stage 4.
- **LangChain (classic chains)** — subsumed by the engine-framework choice; no
  standalone value here.
- **Agent frameworks in the API/web layer** — the API is a CRUD-plus-web3 service;
  frameworks add latency, nondeterminism, and dependency weight for nothing.

### Avoid (negative value — would repeat the hackathon mistake)

- **CrewAI / AutoGen-style multi-agent roleplay for "multiple auditors."** The
  multi-auditor story must be *real independent third parties with separate stakes
  and identities*, or nothing. Orchestrated crews inside one process is the persona
  theater we just deleted, with a framework badge on it.
- **LLM-driven dispute resolution on-chain.** The verifier stays abstention-first;
  authority comes from reproducible execution, not from a model's opinion
  (see VISION.md thesis 2 and the UMA precedent).

## How this maps to the roadmap

- **Phase 1**: ADK-based agent-forge v2 as the "one real engine"; MCP server spike.
- **Phase 2**: eval harness becomes public (verifier benchmark + engine EVMbench);
  optional LLM claim-extractor runs *inside* the intelligence layer only.
- **Phase 4**: A2A card, x402 payments, second independent engine (LangGraph)
  staking as a genuinely separate auditor identity.

## Governance

Technology adoption follows the AGENTS.md Product Vision Governance rules: a new
framework/protocol enters only with a decision record in this file (move it between
radar rings with rationale in the same PR). The containment boundary is
non-negotiable: **nothing agentic in the trust & settlement layer.** Upskilling
rationale is a valid and citable reason in the record — pretending it's a product
reason is not.
