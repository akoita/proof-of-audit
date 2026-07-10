# Backlog Triage (July 2026)

The tracker currently has **zero open issues and zero open PRs** — all ~150 issues
were closed during the hackathon and the two post-hackathon waves. So this triage
reviews the *closed strategic threads* and rules on each: **maintain** (the thread's
direction is right — revive it as new issues), **update** (right area, wrong scope —
rescope before reviving), or **discard** (do not reinvest). It ends with the
proposed new backlog aligned to [ROADMAP.md](./ROADMAP.md).

## Thread-by-thread rulings

| Thread (issues) | What it was | Ruling | Why |
| --- | --- | --- | --- |
| Core trust loop (#1–#3, #7, #44–#47) | Stake/publish/challenge/resolve on Base Sepolia | **Maintain** | This is the product. Foundation of everything in Roadmap v2. |
| Pluggable auditor integration (#155, #156, #124, #238) | Third-party engine contract, backend interface, service contract | **Maintain — promote to center of strategy** | The single most productizable decision already made. Becomes the Phase-1 headline. |
| Executable evidence (#109–#113, #117, #119, #120, #126–#127, #188–#189) | Evidence bundles, Foundry fork runner, Docker/Cloud Run sandboxes | **Maintain** | The strongest technical asset; feeds Phase-2 binding settlement. |
| Challenge Verifier V2 (#169–#174) | Staged adjudication, semantic comparison, abstention policy, dossiers | **Update** | Keep the abstention-first architecture; rescope the goal from "LLM-assisted semantic comparison" to **binding execution-based settlement for a narrow claim class** (Phase 2). Grow the 6-case corpus into a real benchmark before granting any authority. |
| Challenge policies & reputation split (#210–#212, #98, #97) | Verifier-checkable policies, openness/accuracy scores | **Maintain** | Good primitives; reputation becomes the slash-tested track record product. ERC-8004 Reputation Registry integration (the acknowledged gap) goes to Phase 4. |
| Marketplace & fees (#217–#224) | Bounty escrow, pro-rata settlement, protocol/resolution fees, marketplace UX | **Update** | The contract-side fee/settlement engine is valuable — but it was **never deployed**, and the marketplace UX is premature. Rescope: fix contract flaws (self-challenge, settlement freeze, zero-arbiter), redeploy honestly (Phase 0/3), park the marketplace UI, and repurpose "bounties" as **challenge bounties** (pay to break verdicts) before audit bounties. |
| Multi-agent showcase (#274–#280, and #96's reversal) | 5 personas, fabricated divergence, cross-agent watcher, demo orchestration | **Discard as a demo; salvage two parts** | Personas over one engine with findings stripped by category is theater that now damages credibility. Salvage: the multi-service registry (as third-party onboarding surface) and the challenger feed (as the challenge-bounty scanner's data source). Note: #96 ("not planned: multi-auditor") was the *correct* call for the wrong reason — multi-auditor is right, but only with real third parties. |
| Agent-forge externalization (#237–#243, #235, #271) | Separate hosted audit-engine service with auth/quotas | **Update** | Right architecture (engine out of the trust layer), but don't sink solo-dev time into operating a GCP service fleet. Rescope to: one working hosted engine behind the pluggable contract, or partner engines instead. |
| Live deployed-address audits (#226, #229, #234, #255, #256, #269) | Verified-source retrieval, proxy pinning, snapshot semantics | **Maintain** | Snapshot/proxy pinning is exactly what bonded diff-audits need (Phase 1). |
| API/infra hardening (#8, #9, #192, #203, #205, #207, #240, #265) | FastAPI, persistence, Docker, Cloud Run, Postgres | **Maintain** | Continue, plus the new Phase-0 items: API auth on mutating endpoints, rate limits, key-role separation, audit-request storage off flat JSON. |
| Testing & CI (#11, #37, #123, #131, #132, #166–#167, #188, #242, #266) | Unit/system/testnet/UI e2e layers | **Maintain** | Genuine strength. Add: contract fuzz/invariant tests, a real verifier benchmark, and un-break the pre-commit hook so `--no-verify` stops being policy. |
| ERC-8004 alignment (#63–#69, #73–#74, #97) | Identity, validation bridge, registration docs | **Maintain** | Early, disciplined, differentiating. Reputation Registry is the remaining gap (Phase 4; spec still Draft). |
| Hackathon packaging (#80–#94, #181–#186, #54, #161, #153) | Judge briefs, pitch scripts, asciinema, submission pack | **Discard** | Done its job. Archive to `docs/archive/`; do not maintain. The docs-consolidation instinct (#161) survives as Phase-0 doc-truth work. |
| UI redesign & workbench (#19, #22, #138–#143, #264) | Workbench views, marketplace/multi-agent tabs | **Update** | Keep the workbench + comparison views (they become the public challenge-outcome ledger and track-record UI). Park marketplace/multi-agent tabs. |
| TEE research (#118) | TEE-backed evidence execution RFC | **Discard (keep the RFC)** | Its own conclusion was no-go; EigenCompute is the later, cheaper path (Phase 4). |

## Proposed new backlog

### Phase 0 — Truth & hygiene
1. Reconcile ARCHITECTURE/AGENT_INTERACTION_FLOW with TECHNICAL_DOCUMENTATION (retired benchmark auto-resolution).
2. Disclose single-arbiter adjudication + advisory verifier status in README/pitch surfaces.
3. Record and publish a real Base Sepolia publish→challenge→resolve cycle (replaces the green no-op smoke evidence).
4. Contract: block self-challenge in the direct flow.
5. Contract: validate arbiter non-zero; document arbiter-loss consequences.
6. Contract: settlement-timeout path so one unresolved challenge can't freeze request escrow.
7. Contract: fuzz/invariant test suite.
8. Enforce key-role separation (no single-key fallback across publisher/arbiter/validator/operator).
9. API auth (keys on mutating endpoints), rate limiting, CORS allowlist.
10. Move audit-request persistence off the flat JSON file.
11. Fix the pre-commit security hook (remove `--no-verify` from AGENTS.md policy).
12. Archive hackathon-era docs to `docs/archive/`; make `docs/strategy/` the entry point.

### Phase 1 — Real engine, bonded diff-audits
13. Promote the pluggable-auditor HTTP contract to the primary integration surface.
14. Integrate one real audit engine end-to-end; publish EVMbench results.
15. Bonded diff-audit pipeline: GitHub App/CI action → verdict on the diff → ERC-8004 validation mirror.
16. Remove fabricated persona divergence (`_apply_detector_scope` scoping as a product feature).
17. Design-partner pilot program (1–3 protocols).

### Phase 2 — Objective settlement
18. Specify the binding claim class (reproduction + machine-checkable invariant ⇒ auto-slash).
19. Arbiter EOA → multisig + published adjudication rubric + public abstention dossiers.
20. Challenge bounty program + open-source claim scanner.
21. Verifier benchmark corpus expansion + published precision/abstention metrics.
22. Public challenge-outcome ledger UI.

### Phase 3+ — Coverage & agent economy (open when Phase 2 exits)
23. Coverage pools design (stake-behind-auditor, fee on distribution).
24. Underwriter data pilot (bonded-verdict feed).
25. External security review + honest redeploy of the full-source contract.
26. x402-priced attestation read/commission API.
27. ERC-8004 Reputation Registry integration (when spec stabilizes).
