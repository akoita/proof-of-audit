# Local Agent Forge Integration Guide

> How to run Proof-of-Audit with a **real** Agent Forge instance instead of the
> deterministic demo backend.

---

## Background: deterministic vs live modes

By default, Proof-of-Audit runs in **deterministic** mode. The audit worker
returns precanned benchmark reports for the demo fixture contracts — no LLM is
involved and nothing is sent to an external service. This is useful for demos,
judging, and UI development, but it never exercises the real agent code path.

The `PROOF_OF_AUDIT_WORKER_RUNTIME_MODE` environment variable controls which
backend the worker uses:

| Mode             | Behavior                                                                                            |
| ---------------- | --------------------------------------------------------------------------------------------------- |
| `deterministic`  | Benchmark-only. No live execution. Default for all existing scripts.                                |
| `hybrid`         | Tries live agent-forge first; falls back to deterministic if the live path fails.                   |
| `agent_forge`    | Strict live-only. If agent-forge execution fails, the request fails (no fallback).                  |

Live execution can happen in two ways:

1. **Local CLI** — the PoA worker spawns `python -m proof_of_audit_agent.agent_forge_cli run …` as a subprocess, which runs the built-in static analyser (`live_auditor.py`).
2. **Hosted service** — the PoA worker sends the source to a running `agent-forge serve` instance over HTTP, which runs a full ReAct loop inside a Docker sandbox with an LLM.

This guide covers **Option 2**, using the real Agent Forge hosted service locally.

---

## Prerequisites

| Dependency      | Version | Notes                                            |
| --------------- | ------- | ------------------------------------------------ |
| Python           | 3.12+  | PoA requires 3.12; Agent Forge works on 3.11+    |
| Docker           | 24+    | For Agent Forge sandbox containers                |
| Foundry (`forge`, `anvil`, `cast`) | latest | For local chain + contract deployment |
| Node.js + pnpm   | 20+    | If running the web UI                            |
| A Gemini API key |        | Or another supported LLM provider key            |

---

## Step 1 — Clone & install Agent Forge

```bash
# Clone agent-forge alongside proof-of-audit
cd ~/dev/hackatons          # or wherever your workspace lives
git clone https://github.com/akoita/agent-forge.git
cd agent-forge

# Create a virtual environment (recommended: separate from PoA's venv)
python3 -m venv .venv
source .venv/bin/activate

# Install with Redis support (used by docker-compose)
pip install -e ".[dev,redis]"

# Build the Docker sandbox image (required for tool execution)
make build-sandbox
```

Verify the install:

```bash
agent-forge config      # prints resolved config
agent-forge --help      # confirms CLI is on $PATH
```

---

## Step 2 — Configure the hosted service

### 2a. Create the service data directory

```bash
mkdir -p ~/.agent-forge/service
```

### 2b. Create a client policy file

Agent Forge uses a `clients.toml` file to authorize callers. Create
`~/.agent-forge/service/clients.toml`:

```toml
[clients.proof-of-audit-auditor]
api_key_env = "POA_SERVICE_API_KEY"
allowed_profiles = ["proof-of-audit-solidity-v1"]
allowed_report_schemas = ["proof-of-audit-report-v1"]
allowed_source_kinds = ["archive_uri", "local_path"]
max_active_runs = 1
max_runs_per_day = 20
allow_local_path = true
```

### 2c. Export secrets

```bash
# The LLM provider key — at least one is required
export GEMINI_API_KEY="your-gemini-key"

# A shared secret for PoA ↔ Agent Forge auth
# Pick any strong random string
export POA_SERVICE_API_KEY="$(openssl rand -hex 24)"

# Print it so you can copy it for PoA's config
echo "Service API key: $POA_SERVICE_API_KEY"
```

---

## Step 3 — Start Agent Forge

You have two options: **bare process** or **docker-compose**.

### Option A — Bare process (simplest)

```bash
cd ~/dev/hackatons/agent-forge
source .venv/bin/activate

agent-forge serve --host 127.0.0.1 --port 8000
```

Verify: `curl http://127.0.0.1:8000/healthz` should return `200`.

### Option B — Docker Compose

```bash
cd ~/dev/hackatons/agent-forge

# Pass the API keys via the environment
GEMINI_API_KEY="$GEMINI_API_KEY" \
POA_SERVICE_API_KEY="$POA_SERVICE_API_KEY" \
docker compose up -d
```

This starts `agent-forge-service` on port `8000` and a Redis instance on
`6379`. The service mounts `/var/run/docker.sock` so it can launch sandbox
containers.

Verify: `curl http://127.0.0.1:8000/healthz`

---

## Step 4 — Prepare the Proof-of-Audit local chain

In a **separate terminal** (with the PoA venv active):

```bash
cd ~/dev/hackatons/proof-of-audit

# Terminal 1: Start the local Anvil chain
./scripts/start-anvil.sh

# Terminal 2: Deploy contracts + demo fixtures + identity stack
./scripts/prepare-agent-demo-stack.sh
```

This deploys the ProofOfAudit settlement contract, all demo fixtures, the
ERC-8004 identity registry, and the validation registry adapter to Anvil.
It also writes `api/.env.local` with the local identity/validation settings.

---

## Step 5 — Configure PoA to use the hosted service

Add the following variables to `api/.env.local` (the file was already created
by `prepare-agent-demo-stack.sh`):

```bash
# Switch from deterministic to hybrid (or agent_forge for strict mode)
PROOF_OF_AUDIT_WORKER_RUNTIME_MODE=hybrid

# Point to the local Agent Forge hosted service
PROOF_OF_AUDIT_AGENT_FORGE_SERVICE_URL=http://127.0.0.1:8000

# Use the same token you exported for Agent Forge
PROOF_OF_AUDIT_AGENT_FORGE_SERVICE_TOKEN=<your-POA_SERVICE_API_KEY-value>

# Optional: increase timeouts for first-run LLM calls
PROOF_OF_AUDIT_AGENT_FORGE_SERVICE_POLL_TIMEOUT_SECONDS=300
PROOF_OF_AUDIT_AGENT_FORGE_SERVICE_REQUEST_TIMEOUT_SECONDS=60
```

> **Tip:** If you want to skip the hosted service and just use the local CLI
> analyser (no LLM, but real static analysis), omit
> `PROOF_OF_AUDIT_AGENT_FORGE_SERVICE_URL` and set `PROOF_OF_AUDIT_WORKER_RUNTIME_MODE=hybrid`.
> The worker will invoke `python -m proof_of_audit_agent.agent_forge_cli` as
> a subprocess for the live path.

---

## Step 6 — Start the PoA API

```bash
cd ~/dev/hackatons/proof-of-audit

# Activate the project's pyenv virtualenv (has all dependencies)
pyenv activate proof-of-audit-3.12

PYTHONPATH=agent:api python -m proof_of_audit_api.app
```

The API starts on `http://127.0.0.1:8080`.

---

## Step 7 — Start the Web UI (optional)

```bash
cd ~/dev/hackatons/proof-of-audit/web
pnpm dev
```

Open `http://localhost:3000`.

---

## Step 8 — Validate the integration

### From the Web UI

1. Go to `http://localhost:3000`
2. Choose **Source bundle** or **Repository URL** as the submission type
3. Upload a Solidity project (e.g., a zip of one of the `demo/contracts/` dirs)
4. Click **Create Audit** → the worker will send it to Agent Forge
5. Watch the PoA API logs: you should see `"source": "agent_forge_service"` in
   the audit execution metadata instead of `"deterministic"`

### From the terminal

```bash
# Create a draft audit with a source bundle
curl -s -X POST http://127.0.0.1:8080/audits \
  -H "Content-Type: application/json" \
  -d '{
    "input_kind": "source_bundle",
    "source_bundle_uri": "file:///home/<you>/dev/hackatons/proof-of-audit/demo/contracts",
    "entry_contract": "VulnerableBank.sol"
  }' | python3 -m json.tool

# Check the audit — the response should contain execution metadata
# with "source": "agent_forge_service" or "agent_forge_run"
```

### What to look for

In the API response's `execution` field:

```json
{
  "backend": "agent_forge",
  "mode": "hybrid",
  "status": "completed",
  "source": "agent_forge_service",   // ← this confirms the hosted path
  "live_attempted": true,
  "fallback_used": false
}
```

If you see `"source": "deterministic-benchmark"` or `"fallback_used": true`,
the live path failed and the worker fell back. Check the `execution.error` field
and the Agent Forge service logs.

---

## Architecture diagram (live mode)

```
┌──────────┐     ┌──────────┐     ┌───────────────┐     ┌────────────────────┐
│  Web UI  │────▸│ PoA API  │────▸│ Audit Worker  │     │ ProofOfAudit.sol   │
│ (Next.js)│     │ (FastAPI) │     │  (Python)     │     │ (Anvil local)      │
└──────────┘     └──────────┘     └───────┬───────┘     └────────────────────┘
                                          │
                                          │ POST /v1/runs
                                          │ (source archive + profile)
                                          ▼
                                  ┌───────────────────┐
                                  │  Agent Forge       │
                                  │  Hosted Service    │
                                  │  (FastAPI :8000)   │
                                  └───────┬───────────┘
                                          │
                                          │ run inside Docker sandbox
                                          │ with LLM (Gemini)
                                          ▼
                                  ┌───────────────────┐
                                  │  Docker Sandbox    │
                                  │  (ephemeral)       │
                                  │  • read_file       │
                                  │  • search_codebase │
                                  │  • write report    │
                                  └───────────────────┘
```

---

## Troubleshooting

### "hosted agent-forge source upload requires non-local source bundle storage"

The hosted service path needs PoA to upload the source archive somewhere
Agent Forge can fetch it. For **local development**, use `local_path` sources
(Agent Forge's `allow_local_path = true` in `clients.toml`).

If you still see this error, set `PROOF_OF_AUDIT_SOURCE_BUNDLE_STORAGE_KIND=local`
and provide sources as `file://` URIs. The local CLI path (`agent_forge_cli.py`)
doesn't require remote storage at all.

### "timed out waiting for hosted agent-forge run"

Increase the poll timeout:

```bash
PROOF_OF_AUDIT_AGENT_FORGE_SERVICE_POLL_TIMEOUT_SECONDS=600
```

LLM-backed runs on large repos can take several minutes.

### Agent Forge healthcheck fails

- Ensure Docker is running and the current user has access to the Docker socket
- `make build-sandbox` must have completed in the agent-forge repo
- Check `agent-forge config` for resolved paths and provider keys
- If using docker-compose, check `docker compose logs agent-forge-service`

### Fallback to deterministic despite hybrid mode

The hybrid path tries agent-forge first, and returns a deterministic report if
the live path fails for any reason. Common causes:

- Agent Forge service is not running or unreachable
- API key mismatch between `POA_SERVICE_API_KEY` and `PROOF_OF_AUDIT_AGENT_FORGE_SERVICE_TOKEN`
- Source archive is too large or the URI scheme is unsupported
- The Agent Forge profile/report-schema doesn't match `clients.toml`

Check the `execution.error` field in the audit response and the Agent Forge logs.

---

## Environment variable reference

| Variable                                                    | Where         | Description                                          |
| ----------------------------------------------------------- | ------------- | ---------------------------------------------------- |
| `PROOF_OF_AUDIT_WORKER_RUNTIME_MODE`                        | PoA API       | `deterministic` / `hybrid` / `agent_forge`           |
| `PROOF_OF_AUDIT_AGENT_FORGE_SERVICE_URL`                    | PoA API       | Agent Forge hosted service base URL                  |
| `PROOF_OF_AUDIT_AGENT_FORGE_SERVICE_TOKEN`                  | PoA API       | Bearer token for Agent Forge auth                    |
| `PROOF_OF_AUDIT_AGENT_FORGE_SERVICE_PROFILE_ID`             | PoA API       | Profile name (default: `proof-of-audit-solidity-v1`) |
| `PROOF_OF_AUDIT_AGENT_FORGE_SERVICE_REPORT_SCHEMA`          | PoA API       | Report schema (default: `proof-of-audit-report-v1`)  |
| `PROOF_OF_AUDIT_AGENT_FORGE_SERVICE_POLL_TIMEOUT_SECONDS`   | PoA API       | Max seconds to wait for a run to complete             |
| `PROOF_OF_AUDIT_AGENT_FORGE_COMMAND`                        | PoA API       | CLI command for local (non-hosted) live path          |
| `GEMINI_API_KEY`                                            | Agent Forge   | LLM provider key                                     |
| `POA_SERVICE_API_KEY`                                       | Agent Forge   | API key for PoA client auth                          |
| `AGENT_FORGE_SERVICE_AUTH_ENABLED`                           | Agent Forge   | Enable/disable API key enforcement                   |
| `AGENT_FORGE_SERVICE_CLIENTS_PATH`                           | Agent Forge   | Path to `clients.toml`                               |

---

## Quick reference: full local stack

```bash
# Terminal 1 — Anvil
cd ~/dev/hackatons/proof-of-audit
./scripts/start-anvil.sh

# Terminal 2 — Deploy contracts + identity
cd ~/dev/hackatons/proof-of-audit
./scripts/prepare-agent-demo-stack.sh

# Terminal 3 — Agent Forge hosted service
cd ~/dev/hackatons/agent-forge
source .venv/bin/activate
export GEMINI_API_KEY="your-key"
export POA_SERVICE_API_KEY="your-shared-secret"
agent-forge serve --host 127.0.0.1 --port 8000

# Terminal 4 — PoA API (add to api/.env.local first)
cd ~/dev/hackatons/proof-of-audit
pyenv activate proof-of-audit-3.12
PYTHONPATH=agent:api python -m proof_of_audit_api.app

# Terminal 5 — Web UI (optional)
cd ~/dev/hackatons/proof-of-audit/web && pnpm dev
```

Then open `http://localhost:3000` and submit an audit with a source bundle.
