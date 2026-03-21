# Proof-of-Audit — Sequence Diagram

Full lifecycle of a stake-backed agent audit claim, from discovery through dispute resolution.

## Trust Loop

```mermaid
sequenceDiagram
    autonumber

    actor User as User / Agent Caller
    participant Web as Web Workbench<br/>(Next.js)
    participant API as REST API<br/>(FastAPI)
    participant Worker as Audit Worker<br/>(Dispatcher)
    participant AF as Agent Forge<br/>Backend
    participant BM as Deterministic<br/>Benchmark Backend
    participant DV as Deterministic<br/>Verifier
    participant EV as Executable Evidence<br/>Verifier
    participant Runner as Execution<br/>Backend
    participant Contract as ProofOfAudit.sol<br/>(Base / Anvil)
    participant Registry as ERC-8004<br/>Identity Registry
    participant Bridge as Validation<br/>Registry

    rect rgb(30, 40, 70)
        note over User,Registry: Phase 1 — Discover & Trust-Check
        User->>API: GET /auditor
        API-->>User: auditor profile (service_id, capabilities)
        User->>API: GET /auditor/registration
        API->>Registry: resolve agent identity
        Registry-->>API: ERC-8004 registration document
        API-->>User: registration (trust model, agent registry, resolution policy)
        User->>API: GET /config
        API-->>User: chain config (stake, bond, contract address)
    end

    rect rgb(40, 50, 30)
        note over User,BM: Phase 2 — Submit & Audit
        User->>Web: select contract (fixture, repo, or source bundle)
        Web->>API: POST /audits {input_kind, fixture_id | repository_url | source_bundle_uri}
        API->>Worker: dispatch submission

        alt input_kind = demo_fixture
            Worker->>BM: audit(submission)
            Note over BM: Curated benchmark<br/>with known findings
            BM-->>Worker: deterministic report
        else input_kind = repository_url | source_bundle
            Worker->>AF: audit(submission)
            Note over AF: Load prompt (local/remote)<br/>Invoke Agent Forge CLI<br/>Parse agent-report.json
            AF-->>Worker: AI-generated report
        end

        Worker-->>API: AuditExecutionResult (report + execution metadata)
        API-->>Web: draft audit record
        Web-->>User: display draft (summary, confidence, findings, report_hash)
    end

    rect rgb(50, 30, 50)
        note over User,Bridge: Phase 3 — Stake & Publish
        User->>Web: click "Publish"
        Web->>API: POST /audits/{id}/publish {stake_wei}
        API->>Contract: publishAudit(reportHash, stake)
        Note right of Contract: Stake escrowed on-chain
        Contract-->>API: tx receipt + on-chain audit ID
        API->>Bridge: mirror → validation request
        Bridge-->>API: request_hash
        API-->>Web: published audit (tx_hash, audit_id, validation status)
        Web-->>User: ✓ Claim published on-chain
    end

    rect rgb(60, 30, 30)
        note over User,Bridge: Phase 4 — Challenge & Verify
        User->>Web: submit challenge evidence
        Web->>API: POST /audits/{id}/challenge {proof_uri, evidence_type, challenger}
        API->>Contract: openChallenge(auditId, challengeHash)
        Note right of Contract: Challenge bond escrowed
        Contract-->>API: challenge tx receipt
        API->>API: build EvidenceContext from audit record

        alt evidence_type = deterministic_fixture
            API->>DV: verify(EvidenceContext)
            DV-->>API: verdict: upheld | rejected
            Note over DV: Curated lookup table<br/>for benchmark fixtures
        else evidence_type = executable_test
            API->>EV: verify(EvidenceContext)
            EV->>Runner: resolve & execute evidence
            Note over Runner: Pluggable backend:<br/>Subprocess · Docker · GCP Cloud Run
            Runner-->>EV: execution result (pass/fail + logs)
            EV->>EV: claim-aware finding match
            Note over EV: Compare exploit signals<br/>against published findings
            EV-->>API: advisory verdict (never auto-resolves)
        end
    end

    rect rgb(50, 40, 20)
        note over User,Bridge: Phase 5 — Resolve
        alt Deterministic verdict available
            API->>Contract: resolveChallenge(auditId, outcome)
            Note right of Contract: Stake + bond redistributed
            Contract-->>API: resolve tx + payout
            API->>Bridge: mirror → validation response
            API-->>Web: resolved audit (payout, resolution path)
            Web-->>User: ✓ Challenge resolved deterministically
        else Advisory verdict or inconclusive
            API-->>Web: challenged audit + advisory verdict
            Web-->>User: ⏳ Awaiting arbiter (advisory: upheld | rejected | inconclusive)
            Note over User,Contract: Manual fallback path
            User->>API: POST /audits/{id}/resolve {outcome}
            API->>Contract: resolveChallenge(auditId, outcome)
            Contract-->>API: resolve tx + payout
            API->>Bridge: mirror → validation response
            API-->>Web: resolved audit
            Web-->>User: ✓ Challenge resolved by arbiter
        end
    end

    rect rgb(30, 50, 50)
        note over User,Bridge: Phase 6 — Consume Validation Trail
        User->>API: GET /audits/{id}/validation/request
        API-->>User: ERC-8004 validation request document
        User->>API: GET /audits/{id}/validation/response
        API-->>User: ERC-8004 validation response (tag, outcome, evidence)
    end
```

## Auditor Backend Strategy

```mermaid
flowchart TB
    subgraph Dispatch["AuditWorker Dispatch"]
        A["Submission arrives"] --> B{input_kind?}
    end

    subgraph Deterministic["DeterministicBenchmarkBackend"]
        B -->|"demo_fixture"| C["Load curated fixture<br/>(clean-vault, reentrancy-bank, etc.)"]
        C --> D["Return benchmark report<br/>with known findings"]
    end

    subgraph AgentForge["AgentForgeBackend"]
        B -->|"repository_url /<br/>source_bundle"| E["Resolve prompt<br/>(local file · remote URL · inline)"]
        E --> F["Prepare workspace<br/>(clone / extract)"]
        F --> G["Invoke Agent Forge CLI<br/>(forge run --task prompt --repo path)"]
        G --> H{Exit code?}
        H -->|"0"| I["Parse .proof-of-audit/<br/>agent-report.json"]
        I --> D2["Return AI-generated report"]
        H -->|"≠ 0"| J{mode?}
        J -->|"strict"| K["Raise AgentForgeExecutionError"]
        J -->|"hybrid"| L["Fall back to<br/>DeterministicBenchmarkBackend"]
    end

    subgraph Remote["RemoteAuditorBackend (future)"]
        B -.->|"any"| M["POST to remote<br/>audit service API"]
        M -.-> N["Poll for result"]
        N -.-> D3["Return remote report"]
    end

    style Dispatch fill:#1e2846,stroke:#4a9eff,color:#fff
    style Deterministic fill:#1e3c2e,stroke:#6bff6b,color:#fff
    style AgentForge fill:#3c2e1e,stroke:#ffb86b,color:#fff
    style Remote fill:#2e2e3c,stroke:#b8b8ff,color:#fff
```

## Challenge Verification Strategy

```mermaid
flowchart TB
    subgraph Dispatch["Strategy Dispatch"]
        A["Challenge submitted<br/>with EvidenceContext"] --> B{evidence_type?}
    end

    subgraph Deterministic["Deterministic Verifier"]
        B -->|"deterministic_fixture"| C["Lookup benchmark_id<br/>in CHALLENGE_CASES"]
        C --> D{proof_uri matches<br/>expected artifact?}
        D -->|Yes| E["Return pre-determined verdict<br/>(upheld or rejected)"]
        D -->|No| F["Return invalid_evidence"]
        C -->|Unknown benchmark| G["Return verifier_unavailable"]
    end

    subgraph Executable["Executable Evidence Verifier"]
        B -->|"executable_test"| H["Resolve evidence bundle<br/>(fetch, validate hash)"]
        H --> I["Select execution backend"]
        I --> I2{Backend?}
        I2 -->|Subprocess| I3["Local sandboxed subprocess<br/>(--no-ffi, temp-dir, rlimits)"]
        I2 -->|Docker| I4["Docker container<br/>(--network=none, cgroups, ro rootfs)"]
        I2 -->|GCP Cloud Run| I5["One-shot Cloud Run job<br/>(gVisor sandbox)"]
        I2 -.->|TEE| I6["Confidential VM<br/>(attestation report)"]
        I3 --> J
        I4 --> J
        I5 --> J
        I6 -.-> J
        J{Test pass/fail?}
        J -->|Fail| K["Advisory: rejected<br/>(exploit not reproduced)"]
        J -->|Pass| L["Extract issue signals<br/>from test + output"]
        L --> M{Signals match<br/>published findings?}
        M -->|"Matched"| N["Advisory: rejected<br/>(audit already covered this)"]
        M -->|"Unmatched"| O["Advisory: upheld<br/>(auditor may have missed it)"]
        M -->|"Ambiguous"| P["Advisory: inconclusive<br/>(manual review required)"]
    end

    subgraph Resolution["Resolution Path"]
        E -->|Auto-resolve| Q["resolveChallenge on-chain"]
        F --> R["Manual fallback"]
        G --> R
        K --> R
        N --> R
        O --> R
        P --> R
    end

    style Dispatch fill:#1e2846,stroke:#4a9eff,color:#fff
    style Deterministic fill:#1e3c2e,stroke:#6bff6b,color:#fff
    style Executable fill:#3c2e1e,stroke:#ffb86b,color:#fff
    style Resolution fill:#2e1e3c,stroke:#b86bff,color:#fff
```

## Economic Flow

```mermaid
flowchart TB
    subgraph Publish["Publish Phase"]
        A["Auditor stakes 0.01 ETH"] --> B["ProofOfAudit escrows stake"]
    end

    subgraph Challenge["Challenge Phase"]
        C["Challenger posts 0.005 ETH bond"] --> D["ProofOfAudit escrows bond"]
    end

    subgraph Resolution["Resolution"]
        D --> E{Outcome?}
        E -->|"Challenge upheld<br/>(auditor was wrong)"| F["Challenger receives<br/>stake + bond = 0.015 ETH"]
        E -->|"Challenge rejected<br/>(auditor was right)"| G["Auditor receives<br/>stake + bond = 0.015 ETH"]
    end

    B --> D

    style Publish fill:#1e2846,stroke:#4a9eff,color:#fff
    style Challenge fill:#3c1e1e,stroke:#ff6b6b,color:#fff
    style Resolution fill:#1e3c2e,stroke:#6bff6b,color:#fff
```

## Simplified View (README-friendly)

```mermaid
sequenceDiagram
    participant Agent as 🤖 Auditor Agent
    participant Chain as ⛓️ On-Chain Contract
    participant Challenger as ⚔️ Challenger

    Agent->>Chain: Publish claim + stake ETH
    Note over Chain: Claim is now public & stake-backed
    Challenger->>Chain: Submit evidence + post bond
    Chain->>Chain: Evaluate evidence
    alt Auditor wrong
        Chain->>Challenger: Payout (stake + bond)
    else Auditor right
        Chain->>Agent: Payout (stake + bond)
    end
```
