> This file is read by AI coding assistants (GitHub Copilot, Gemini Code Assist, Claude, etc.)
> to enforce project-wide conventions. Keep it up to date.

## Product Vision Governance

All strategic and product decisions are governed by the documents in `docs/strategy/`:
[VISION.md](./docs/strategy/VISION.md) (what the product is and is NOT),
[PRODUCT_STRATEGY.md](./docs/strategy/PRODUCT_STRATEGY.md),
[ROADMAP.md](./docs/strategy/ROADMAP.md) (phased, with exit criteria), and
[BACKLOG_TRIAGE.md](./docs/strategy/BACKLOG_TRIAGE.md).

Binding rules for AI assistants and human contributors:

1. **Check alignment before building.** Before proposing or implementing any new feature,
   scope change, or architectural pivot, verify it against the "What Proof-of-Audit is not"
   section of `docs/strategy/VISION.md` and the current phase of `docs/strategy/ROADMAP.md`.
   If it doesn't map to the current phase, say so instead of building it.
2. **Respect phase ordering.** Do not start a later phase's headline work before the current
   phase's exit criterion is met. Phase 0 (truth & hygiene) blocks everything else.
3. **Parked items stay parked.** Multi-agent persona demos, marketplace UI as a headline
   surface, TEE evidence execution, a proprietary frontier audit engine, and cross-chain
   expansion are explicitly parked. Do not reopen them without new external evidence, and
   never silently.
4. **Deviations require a docs-first decision record.** If a decision genuinely deviates from
   the vision, update the relevant `docs/strategy/` document **in the same PR** with the
   decision and rationale. The strategy docs are the source of truth; code must not diverge
   from them silently.
5. **Never overstate the trust model.** Public claims (README, pitches, docs, UI copy) must
   match the current rung of the decentralization ladder in `docs/strategy/VISION.md`.
   Today that means: disclose single-arbiter adjudication and advisory-only verification.
6. **Technology adoption follows the radar.** New frameworks/protocols (agentic or
   otherwise) enter only per [AGENTIC_STACK.md](./docs/strategy/AGENTIC_STACK.md): update the
   radar ring with a rationale in the same PR. The containment boundary is non-negotiable —
   **no agent frameworks in the trust & settlement layer** (contracts, escrow, evidence
   verification, on-chain publishing). Upskilling/branding is a valid, citable adoption
   reason in the intelligence and interop layers — disguising it as a product reason is not.

---

**NEVER hardcode** URLs, ports, secrets, API keys, private keys, RPC endpoints, contract addresses,
or any environment-dependent values directly in source code.

### Rules
1. **Always use environment variables** with a sensible local-dev fallback:

   ```python
   # ✅ CORRECT
   rpc_url = os.environ.get("PROOF_OF_AUDIT_RPC_URL", "http://127.0.0.1:8545")

   # ❌ WRONG — hardcoded production URL
   rpc_url = "https://base-sepolia.infura.io/v3/XXXX"

   # ❌ WRONG — no env var at all
   rpc_url = "http://127.0.0.1:8545"
   ```

2. **Use centralized config** — don't redeclare configuration in every module:

   ```python
   # ✅ Import from the canonical source
   from proof_of_audit_api.config import ContractConfig

   # ❌ Don't redeclare per-file
   CONTRACT_ADDRESS = os.environ["PROOF_OF_AUDIT_CONTRACT_ADDRESS"]
   ```

3. **Port conventions** — local dev defaults must use the correct port:
   - API (FastAPI/Uvicorn): `8080`
   - Anvil (local chain): `8545`
   - Agent Forge Service: `8000`
   - Frontend (Next.js): `3000`

4. **Never commit secrets** — private keys, API keys, JWT secrets, and service account
   credentials must come from environment variables or secret managers, never from source.

### Environment Variable Naming
| Layer         | Prefix                   | Example                                     |
| ------------- | ------------------------ | ------------------------------------------- |
| API / Agent   | `PROOF_OF_AUDIT_`        | `PROOF_OF_AUDIT_RPC_URL`                    |
| Agent Forge   | `PROOF_OF_AUDIT_AGENT_FORGE_` | `PROOF_OF_AUDIT_AGENT_FORGE_PROVIDER`  |
| Deployment    | `PROOF_OF_AUDIT_DEPLOY_` | `PROOF_OF_AUDIT_DEPLOY_NETWORK`             |
| Identity      | `PROOF_OF_AUDIT_IDENTITY_` | `PROOF_OF_AUDIT_IDENTITY_CHAIN_ID`        |
| Frontend      | `NEXT_PUBLIC_`           | `NEXT_PUBLIC_API_URL`                       |

### Required Environment Variables
Document any new env var in `.env.example` and the relevant IaC config in `agent-forge-iac`.

---

**NEVER push directly to `main`.** All changes must go through a feature branch and Pull Request.

1. **Always work on a branch** — use the naming convention:
   - `issue-<NUMBER>-<short-kebab-description>` for all issue-tracked work
   - `feat/<short-description>` for untracked features
   - `fix/<short-description>` for untracked fixes

2. **Submit a Pull Request** targeting `main` — include a clear description and reference the issue (`Closes #N`).

3. **Merge only on explicit developer request** — never merge a PR autonomously. Wait for the developer to say "merge", "you can merge", or equivalent.

4. **Never force-push to `main`** — only force-push on feature branches if absolutely necessary.

5. **Clean up after merge** — delete the feature branch (local + remote) and align local `main`.

6. **Use the `process-issue` skill** when beginning work on any GitHub issue. Run the steps in `.agents/skills/process-issue/SKILL.md` to create the branch, implement, test, commit, push, create PR, merge, and clean up. (Claude Code discovers it via the `.claude/skills` symlink.)

7. **Use the `finish-issue` skill** when completing work on an issue or any branch. Run the steps in `.agents/skills/finish-issue/SKILL.md` to verify, test, commit, push, create PR, merge, and clean up. This ensures security scans are executed and no steps are skipped.

8. **Always use `--no-verify`** on `git commit` — the pre-commit security-audit hook uses a different Python version and cannot resolve project modules. Tests must be run manually with the correct pyenv environment.

---

### Project Structure

```
proof-of-audit/
├── agent/                          # Agent package (proof_of_audit_agent)
│   ├── proof_of_audit_agent/       # Core agent modules
│   │   ├── worker.py               # AuditWorker — submission execution
│   │   ├── live_auditor.py          # Static analysis engine
│   │   ├── agent_forge_backend.py   # Agent Forge integration
│   │   ├── claim_watcher.py         # Cross-agent claim watcher
│   │   ├── challenge_verifier.py    # Challenge evidence verification
│   │   └── ...
│   └── tests/                       # Agent tests
├── api/                             # API package (proof_of_audit_api)
│   ├── proof_of_audit_api/          # FastAPI application
│   │   ├── app.py                   # Route definitions
│   │   ├── service.py               # AuditService — business logic
│   │   ├── config.py                # ContractConfig — env config loading
│   │   ├── publisher.py             # On-chain publish/challenge/resolve
│   │   ├── schemas.py               # Pydantic request/response models
│   │   └── ...
│   └── tests/                       # API tests
├── contracts/                       # Solidity smart contracts (Foundry)
├── demo/                            # Demo fixtures and agent manifests
│   ├── agents.json                  # Multi-agent persona manifest
│   ├── agents.schema.json           # Schema for agents.json
│   └── contracts/                   # Sample Solidity contracts
├── scripts/                         # Utility scripts
│   ├── generate-auditor-catalog.py  # Build auditor catalog from agents.json
│   ├── cross_agent_watcher.py       # Cross-agent claim watcher CLI
│   ├── register-multi-agent-identities.py
│   └── ...
├── docs/                            # Documentation
├── web/                             # Frontend (Next.js)
├── infra/                           # Infrastructure config
└── deployments/                     # Deployment artifacts (gitignored)
```

### Python Environment
- **Required**: Python 3.12+ via pyenv
- **Virtualenv**: `pyenv activate proof-of-audit-3.12`
- **PYTHONPATH**: Always set `PYTHONPATH=agent:api` when running tests or scripts

### API (FastAPI)
- Entry point: `api/proof_of_audit_api/app.py`
- All configuration loads from `PROOF_OF_AUDIT_*` env vars via `ContractConfig`
- Worker runtime mode: `deterministic` (default) or `hybrid` (with Agent Forge LLM)
- Data storage: `sqlite` (local), `cloudsql` (GCP)

### Agent
- Static analysis engine: `live_auditor.py` with detector families (`reentrancy`, `access_control`, `unchecked_external_call`)
- Multi-agent persona manifest: `demo/agents.json`
- Catalog generator: `scripts/generate-auditor-catalog.py`
- Worker runtime overrides: per-agent detector/profile scoping via `runtime_overrides`

### Contracts (Foundry)
- Audit registry: `ProofOfAudit.sol`
- Identity: `AgentIdentityRegistry.sol`
- Validation: `ValidationRegistry.sol`
- Reputation: `ReputationRegistry.sol`
- Build: `forge build`
- Test: `forge test`

---

### Testing

All tests use **pytest** with `PYENV_VERSION=proof-of-audit-3.12`.

#### Test Command
```bash
PYENV_VERSION=proof-of-audit-3.12 PYTHONPATH=agent:api python -m pytest agent/tests/ -x -q
```

#### Test Conventions
| Pattern                           | Purpose                                         |
| --------------------------------- | ----------------------------------------------- |
| `agent/tests/test_*.py`          | Agent unit tests — deterministic engine, worker  |
| `api/tests/test_*.py`            | API tests — service logic, HTTP endpoints        |
| `api/tests/test_app.py`          | HTTP contract tests — routing, status codes      |
| `api/tests/test_service.py`      | Integration tests — full audit lifecycle         |
| `test_*_e2e.py`                  | System E2E tests — real API + chain stack        |

#### Rules
1. **Never skip tests.** All tests must pass before committing. The current baseline is **145+ tests**.

2. **Use `--no-verify` on commit.** The pre-commit hook runs tests with the wrong Python. Always run tests manually:
   ```bash
   PYENV_VERSION=proof-of-audit-3.12 PYTHONPATH=agent:api python -m pytest agent/tests/ -x -q
   ```

3. **On-chain tests use eth-tester.** The `build_onchain_test_context()` helper provides a full in-memory EVM with deployed contracts — no external RPC needed.

4. **Use `tempfile.TemporaryDirectory`** for service tests that need a data store.

5. **Ignore `test_executable_evidence_resolver.py`** — requires external `forge` binary not available in CI.

---

### Security

- **NEVER commit `.env` files, private keys, or secrets** — scan every file before staging
- **NEVER hardcode credentials** in ANY file (source, config, scripts, Terraform, Docker compose)
- Check `.gitignore` covers suspicious files: `git status --ignored`
- All contract changes should be reviewed for security implications
- Challenge verifier evidence must be validated before execution

### Deployment
- **Local**: Anvil (Foundry) for chain, Uvicorn for API
- **Staging/Prod**: GCP Cloud Run + Cloud SQL + Base Sepolia
- **IaC**: Managed in `agent-forge-iac` repository
- **Multi-agent**: Use `scripts/deploy-multi-agent-identities.sh` for demo environments

---

### Data — Ignored Paths

The following paths contain runtime data and must **never** be committed:

- `api/data/*` — audit store, runtime state
- `deployments/*.json` — deployment manifests (except checked-in templates)
- `.tmp/` — temporary build/scan artifacts
- `cache/` / `out/` — Foundry build outputs

---

### Documentation

- **Always update documentation alongside code changes** — docs should never lag behind the implementation
- When adding new modules, scripts, or top-level directories, **update the Project Structure** section above
- When adding new environment variables, **update `.env.example`** and the env var naming table
- For new features (endpoints, agent capabilities, cross-agent workflows), add or update docs in `docs/`
- For Solidity changes, update NatSpec comments and any relevant deployment docs
- Python modules must include docstrings for public classes and functions
- When architectural patterns change (new agent modules, data flows, contract interactions), update or create architecture docs in `docs/`

---

- Always run tests before committing
- Use `PYTHONPATH=agent:api` for all Python commands
- Agent persona changes require regenerating the auditor catalog: `python scripts/generate-auditor-catalog.py`
- Solidity changes require `forge build` and `forge test`
- Document new env vars in `.env.example`

