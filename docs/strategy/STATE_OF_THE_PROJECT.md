# State of the Project — Honest Assessment (July 2026)

This document is a candid audit of what Proof-of-Audit actually is today, produced as the
foundation for the post-hackathon vision reset. It separates what is genuinely built from
what is demo-ware, because a real-world product strategy is only as good as the inventory
it starts from. Companion documents: [VISION.md](./VISION.md),
[PRODUCT_STRATEGY.md](./PRODUCT_STRATEGY.md), [ROADMAP.md](./ROADMAP.md),
[BACKLOG_TRIAGE.md](./BACKLOG_TRIAGE.md).

## Context

Built solo in ~3.5 weeks (2026-03-12 → 2026-04-05) for the Synthesis hackathon
(deadline 2026-03-22), then extended in two post-hackathon waves: a bounty
marketplace + fee model (Mar 24–28) and a multi-agent demo showcase (Apr 2–5).
223 commits, ~150 issues (all closed), strong CI discipline throughout.

## What is genuinely built (the real assets)

| Asset | Where | Assessment |
| --- | --- | --- |
| On-chain escrow & settlement rails | `contracts/src/ProofOfAudit.sol` | Clean, well-tested (28 tests) stake/challenge/resolve state machine plus a full bounty-request/pro-rata/fee subsystem. Checks-effects-interactions respected. |
| ERC-8004 identity anchoring | official Base Sepolia IdentityRegistry, `ownerOf` enforced at claim submission | Real, early, and standards-disciplined ("aligned, not compliant" language). |
| Executable evidence pipeline | `agent/proof_of_audit_agent/executable_evidence_runner.py`, `backends/`, `infra/evidence-runner/` | The most defensible technical asset: hash-committed evidence bundles, pinned fork-block Foundry replays, sandboxed Docker/Cloud Run execution. |
| Validation & reputation bridges | `reputation_bridge.py`, `ValidationRegistryAdapter.sol` | Real web3 signing against ERC-8004-style registries. |
| Ops scaffolding | CI (5 jobs incl. full-stack e2e), release images, Cloud Run + Cloud SQL path, Postgres/SQLite/JSON stores | Well beyond hackathon norms. |
| Abstention-first verifier philosophy | `semantic_comparison.py`, Challenge Verifier V2 design | The *design instinct* (never let a weak verifier auto-slash) is correct and worth keeping. |

## What is demo-ware (be blunt)

| Claimed | Reality | Where |
| --- | --- | --- |
| "AI auditor agent" | Default mode returns 5 hand-written fixture reports; arbitrary contracts get an empty "unknown" report. Live mode is a ~300-line regex scanner (3 detector families). | `deterministic_auditor_backend.py`, `live_auditor.py` |
| "LLM deep-analysis agents (Gemini/OpenAI)" | Config personas pointing at a hosted agent-forge HTTP contract **with no server behind it**; `--provider/--model` flags are ignored by the bundled CLI. | `agent_forge_service_client.py`, `agent_forge_cli.py`, `demo/agents.json` |
| "Multi-agent auditors with divergent findings" | One shared worker process; per-persona "divergence" is fabricated by stripping findings by detector category. Cross-agent challenge detection compares finding *counts*. | `worker.py` (`_apply_detector_scope`), `claim_watcher.py` |
| "Settled on-chain through transparent rules" | Every dispute is decided by a single **immutable arbiter EOA** supplying `upheld: bool`. The executable verifier is always `advisory_only` and never auto-resolves. The plain proof-URI verifier is an intentional no-op ("verifier retired"). | `ProofOfAudit.sol:544,573`, `service.py:2323`, `challenge_verifier.py:176` |
| "Live on Base Sepolia" | The contract is deployed and verified, but the dated smoke-evidence record says all 4 live tests **skipped** ("a green no-op"). No captured live publish→challenge→resolve cycle exists. | `docs/proofs/base-sepolia-smoke-2026-03-22.md` |
| Marketplace + fee model | The bounty/fee subsystem in source was **never deployed** — the live contract is an older 4-arg constructor version without it. | `deployments/base-sepolia.json` vs `ProofOfAudit.sol:283-302` |

## Trust-model reality

What is trustless today: escrow custody, payout arithmetic, challenge-window timing,
identity ownership. What is centralized: **everything that determines who wins** —
the arbiter key, the operator-run API (no auth, open CORS, no rate limits), the
operator-controlled evidence execution and RPC, and an env-var key cascade where the
publisher, arbiter, auditor-owner, validator, and reputation-operator can all fall
back to the **same private key** (`config.py:711-912`), collapsing the very
separation the challenge game depends on.

Additional mechanism gaps found in review:

- Flow A (deployed) allows **self-challenge** (no `auditor == msg.sender` guard).
- A single unresolved challenge can **freeze an entire bounty request's settlement**
  indefinitely (no timeout fallback in `classifyAuditRequestClaims`).
- The arbiter address is never validated non-zero at construction; a dead arbiter
  permanently locks challenged escrow.
- Stakes are economic theater: 0.01 ETH stake / 0.005 ETH bond (~$25/$12).
- No pause, no recovery path, no fuzz/invariant tests.

## Documentation debt

- `ARCHITECTURE.md` and `AGENT_INTERACTION_FLOW.md` still describe the retired
  benchmark-lookup auto-resolution that `TECHNICAL_DOCUMENTATION.md` says was removed.
- Judge/submission-era docs (JUDGE_BRIEF, JUDGE_EVALUATION, EVALUATION_READINESS,
  SUBMISSION_PACK, PITCH, STRATEGIC_ALIGNMENT, demo runbooks) dominate `docs/` and
  frame the project for a contest that ended in March.
- Marketing language ("not a platform's discretion") overstates the trust model;
  single-arbiter adjudication is under-disclosed.
- `AGENTS.md` institutionalizes `git commit --no-verify`, i.e. the security
  pre-commit gate is bypassed by design.

## Net verdict

The project contains a real, differentiated primitive — **staked, identified,
challengeable audit claims with working escrow and a reproducible-evidence
pipeline** — wrapped in a hackathon presentation layer that fabricates the parts
that don't exist yet (audit intelligence, independent agents, autonomous
settlement). The productization path is to keep the primitive, delete the theater,
and buy/borrow the intelligence rather than build it. See [VISION.md](./VISION.md).
