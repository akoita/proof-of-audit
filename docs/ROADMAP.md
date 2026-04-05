# Roadmap

This roadmap organizes Proof-of-Audit into practical delivery phases. Each phase is intended to produce a usable increment while reducing the largest product and technical risks first.

## Phase 1: On-Chain Foundations

Goal: replace local placeholders with a real deployment and transaction path.

1. Deploy `ProofOfAudit` to Base Sepolia and add environment-based contract configuration.
2. Replace mocked publish and challenge transaction hashes with real contract calls from the API.
3. Add deployment and verification scripts for repeatable contract releases.

## Phase 2: Audit Execution and Verification

Goal: move from benchmark-only reports to a stronger agent-backed audit and challenge flow.

1. Integrate `agent-forge` as the audit execution backend behind the worker interface.
2. Expand the benchmark suite and report schema for multiple finding categories and severities.
3. Implement a deterministic challenge verifier that can evaluate reproducible PoCs.
4. Add deployable demo fixtures and source-aware inputs for multi-contract audit targets.

## Phase 3: Product and Platform Hardening

Goal: make the API, frontend, and storage path durable enough for repeated demos and external use.

1. Migrate the API from `http.server` to FastAPI with typed schemas and cleaner middleware.
2. Persist audits, reports, and challenge state in a durable application store.
3. Connect the web application to deployed contract data and explorer links.
4. Add a multi-source submission UX for addresses, source bundles, and repository imports.

## Phase 4: Release Readiness

Goal: improve trust, test coverage, and operator confidence.

1. Add end-to-end tests covering submit, publish, challenge, and resolution flows.
2. Harden contract and API edge cases, including stake accounting and invalid state transitions.
3. Prepare public release assets: architecture notes, judge/demo script, screenshots, and setup docs.

## Phase 5: Multi-Agent Demo and Cross-Agent Disputes

Goal: demonstrate autonomous multi-agent dispute resolution with specialized auditors.

1. ✅ Define 5 agent personas with distinct profiles and LLM providers (#278).
2. ✅ Implement capability profiles scoping detectors per agent (#275).
3. ✅ Support multi-agent registry with runtime overrides (#274).
4. ✅ Deploy N on-chain agent identities (#280).
5. ✅ Cross-agent claim watcher with configurable challenge strategies (#276).
6. End-to-end multi-agent demo orchestration with live LLM providers.
7. Hosted deployment of multi-agent environment on GCP.

See also: [docs/MULTI_AGENT_DEMO.md](MULTI_AGENT_DEMO.md)

## Working model

- Work should be tracked in GitHub issues tied to one roadmap phase.
- Each issue should be developed on its own branch.
- Branch naming should follow `issue-<NUMBER>-<short-kebab-description>`.
- Changes land through pull requests after CI passes.
- Branches should be deleted after merge.
- Use the `/process-issue` workflow to begin and the `/finish-issue` workflow to complete work.

