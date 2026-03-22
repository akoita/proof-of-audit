# Evaluation Readiness

This document is the final evaluation index for Proof-of-Audit.

## Start here

1. Read the [Judge brief](./JUDGE_BRIEF.md) for the 2-minute product summary.
2. Use the [Judge evaluation path](./JUDGE_EVALUATION.md) for the one-command local walkthrough.
3. Use the [Submission pack](./SUBMISSION_PACK.md) for demo copy and canonical assets.
4. Inspect the latest [Base Sepolia smoke evidence](./proofs/base-sepolia-smoke-2026-03-22.md) for the dated live-path record.

## Readiness checklist

- [x] `#182` judge-facing brief exists and is linked from the repo entry points
- [x] `#183` public copy and demo semantics were refreshed to match the current verifier behavior
- [x] `#184` judges have a one-command local evaluation path via `./scripts/run-judge-stack.sh`
- [x] `#185` the repo contains dated Base Sepolia smoke evidence and the workflow now fails loudly when the live env is missing
- [x] `#186` the final submission pack and demo asset inventory are committed

## Judge-risk order

- Highest signal: local end-to-end demo via [Judge evaluation path](./JUDGE_EVALUATION.md)
- Fastest narrative: [Judge brief](./JUDGE_BRIEF.md)
- Canonical submission copy: [Submission pack](./SUBMISSION_PACK.md)
- Live chain evidence: [Base Sepolia smoke evidence](./proofs/base-sepolia-smoke-2026-03-22.md)

## Known limits

- The easiest complete product evaluation path is still local-first rather than a stable public web/API deployment.
- The latest dated Base Sepolia smoke evidence is honest about the current blocker: the live smoke env was not configured for the March 22, 2026 run, so no fresh publish/challenge/resolution tx hashes were captured in that attempt.
- Plain proof URIs remain manual-review challenges. Executable evidence is advisory and does not replace the final arbiter path.
