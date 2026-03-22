# Submission Pack

This is the canonical source for the final Synthesis submission copy and demo assets.

## Asset pack

### Recording

- Terminal walkthrough: [proof-of-audit-agent-demo.cast](./assets/proof-of-audit-agent-demo.cast)
- Terminal poster/preview: [proof-of-audit-agent-demo.svg](./assets/proof-of-audit-agent-demo.svg)
- Recording runbook: [ASCIINEMA_DEMO.md](./ASCIINEMA_DEMO.md)

### Screenshots

- Workbench overview: [workbench-overview.png](./assets/workbench-overview.png)
- Draft claim: [workbench-draft-claim.png](./assets/workbench-draft-claim.png)
- Challenge and resolution flow: [workbench-challenge-resolution.png](./assets/workbench-challenge-resolution.png)

## Short project summary

Proof-of-Audit is trust infrastructure for agent-made smart contract judgments. An auditor agent publishes a claim on Base, stakes behind it, and can be challenged with evidence through a transparent on-chain process instead of a centralized platform-owned review flow.

## Why Ethereum and Base

Ethereum matters here because the important object is not the model output, it is the public commitment. Base Sepolia is where the prototype records the auditor's identity, stake-backed claim, challenge bond, and dispute outcome so the judgment is portable, inspectable, and economically accountable.

## What judges should try

Run the one-command local evaluation path with `./scripts/run-judge-stack.sh`, open `http://127.0.0.1:3000`, select the `Clean Vault` fixture, generate a claim, publish it, and then challenge it. That shows the full user-facing trust loop: agent identity, draft claim, on-chain publication, challenge intake, and resolution handling.

## Limitation statement

This prototype is not claiming fully autonomous verification. Plain proof-URI challenges are recorded for manual review, and executable evidence produces an advisory verdict rather than replacing the final resolution path. The complete judge-friendly product path is currently local-first instead of a stable public web/API deployment.

## Submission-ready notes

- Best 30-60 second narrative: [DEMO_SCRIPT.md](./DEMO_SCRIPT.md)
- Judge-facing 2-minute brief: [JUDGE_BRIEF.md](./JUDGE_BRIEF.md)
- Default evaluation path: [JUDGE_EVALUATION.md](./JUDGE_EVALUATION.md)
- Latest Base Sepolia smoke evidence: [proofs/base-sepolia-smoke-2026-03-22.md](./proofs/base-sepolia-smoke-2026-03-22.md)
