# Challenge Verifier V2

## Purpose

Challenge verification is the trust core of Proof-of-Audit.

The product is not differentiated by whether it can store audit records or
open on-chain challenges. It is differentiated by whether other agents and
operators can rely on it to answer one narrow question well:

> Does this submitted evidence credibly show that the published audit missed,
> misstated, or contradicted a material issue?

Today, the verifier is good at evidence integrity and bounded execution, but
still weak at semantic adjudication. Challenge Verifier V2 is the design for
hardening that layer without giving up reproducibility or safety.

## Core Judgments

Challenge adjudication should be treated as three separate judgments:

1. `evidence_validity`
   Can the submitted evidence be fetched, validated, pinned, and replayed?
2. `exploit_truth`
   Does the evidence actually demonstrate the claimed behavior on the relevant
   target and state?
3. `audit_contradiction`
   Does that demonstrated behavior fall outside what the published audit
   already covered?

V2 should not collapse those questions into a single opaque verdict.

## Design Principles

- Keep evidence integrity and execution deterministic.
- Use LLMs only where semantic interpretation is required.
- Fail closed into abstention or manual review on uncertainty.
- Persist enough structured context to replay a verifier decision later.
- Emit machine-consumable dossiers, not just prose summaries.
- Separate "the exploit runs" from "the audit was wrong."

## Current V1 Limits

The current verifier path already has useful primitives:

- deterministic evidence hash commitment
- executable evidence bundle validation
- bounded Foundry execution against a fork
- storage of execution logs and advisory outcomes

The weak point is the final comparison step. Today, executable evidence is
classified by token overlap between:

- challenge source and runner output
- published finding titles, descriptions, categories, and function names

That approach is too brittle for:

- paraphrased but equivalent findings
- same root cause expressed through a different exploit path
- variants of already-known issues
- overbroad audit claims such as "clean" or "no critical issues"
- challenge artifacts that prove something real but describe it noisily

## V2 Architecture

Challenge Verifier V2 should be a staged pipeline.

### 1. Integrity Layer

This layer remains deterministic.

Responsibilities:

- resolve the challenge evidence bundle
- validate the manifest and bundle structure
- verify the committed evidence hash
- pin target chain and block requirements
- derive a canonical execution plan

Output:

- `evidence_valid: true | false`
- canonical evidence hash
- normalized manifest
- integrity errors, if any

If this layer fails, no LLM should run.

### 2. Execution Layer

This layer also remains deterministic.

Responsibilities:

- execute the challenge artifact in a bounded runner
- capture stdout, stderr, return code, traces, and normalized artifacts
- pin the fork block used during execution
- normalize runner metadata across backends

Output:

- `exploit_reproduced: true | false | unknown`
- execution artifacts
- runner backend and isolation metadata
- normalized observed surfaces when possible

This layer is stronger than "forge exited 0." It should become the source of
truth for what actually happened during reproduction.

### 3. Claim Extraction Layer

This is the first place where LLMs help materially.

Input:

- evidence manifest
- challenge test source
- normalized execution result
- stdout and stderr
- limited audit metadata needed for context

Task:

- produce a structured claim for what the evidence demonstrates

Expected output fields:

- vulnerability class
- affected functions or surfaces
- attacker preconditions
- demonstrated effect
- claimed impact
- evidence limits
- confidence

This stage must use schema-constrained output.

### 4. Finding Normalization Layer

Published audit findings should be normalized into the same comparison space as
challenge claims.

For each finding, derive structured fields such as:

- vulnerability class
- affected surface
- preconditions
- claimed impact
- remediation intent

This normalization can happen at publish time or lazily and then be cached on
the audit record.

### 5. Semantic Comparison Layer

This is the actual "brain" of V2.

Input:

- structured challenge claim
- normalized audit findings
- published report summary and overall claim
- execution artifacts

Required outcome classes:

- `already_covered`
- `likely_new_issue`
- `contradicts_audit_claim`
- `same_root_cause_variant`
- `ambiguous`

This stage can use LLM reasoning, but only over bounded, explicit inputs.

### 6. Policy Layer

The policy layer converts comparison outputs into a verifier recommendation.

Recommended first-rollout behavior:

- reject only when evidence clearly reproduces an already-covered issue
- uphold only as an advisory recommendation
- force manual review on ambiguity, disagreement, or low confidence

Initial policy outputs:

- `recommended_resolution: rejected | upheld | manual_review_required`
- `abstained: true | false`
- confidence
- disagreement flags
- rationale list

### 7. Explanation Layer

The verifier should emit a structured dossier suitable for both humans and
agents.

The dossier should include:

- integrity decision
- execution decision
- extracted challenge claim
- matched findings
- unmatched findings
- semantic comparison result
- policy recommendation
- uncertainty and abstention reasons
- prompt, model, and schema versions

## LLM Usage Policy

LLMs should be used as bounded reasoning components, not as the final source of
truth.

Good uses:

- extract structured challenge claims from evidence and execution artifacts
- normalize published findings
- compare whether a reproduced exploit is already covered or appears novel
- produce explicit justification for a comparison result

Bad uses:

- replacing evidence validation or execution
- allowing unconstrained freeform adjudication
- triggering automatic on-chain resolution from a single model pass
- consuming unbounded external context during verification

## Hardening Requirements For LLM Use

### Schema-Constrained Output

Every LLM stage should return validated structured output, not freeform prose.

### Evidence-Bounded Context

Models should only see:

- the published report or normalized findings
- the challenge evidence
- the normalized execution artifacts
- the metadata required to compare them

### Prompt and Model Versioning

Every verifier run should persist:

- prompt version
- model identifier
- schema version
- verifier version

### Abstention-First Behavior

Any of the following should force manual review:

- invalid schema output
- low confidence
- extractor/comparator disagreement
- ambiguous match result
- inconsistent execution artifacts

### Replayability

A verifier decision should be reconstructible later from stored inputs and
artifacts.

### Evaluation Before Authority

V2 should not gain stronger automatic authority before it has a benchmark and
evaluation harness.

## Suggested Data Model

Illustrative verifier dossier shape:

```json
{
  "verifier_version": "challenge-verifier-v2",
  "integrity": {
    "evidence_valid": true,
    "canonical_hash": "sha256:...",
    "manifest_version": "proof-of-audit-executable-evidence/v1"
  },
  "execution": {
    "exploit_reproduced": true,
    "backend": "local_subprocess",
    "fork_block_number": 123456,
    "artifacts": {}
  },
  "challenge_claim": {
    "claim_type": "missing_access_control",
    "affected_surfaces": ["rotateOwner(address)"],
    "preconditions": ["arbitrary caller"],
    "demonstrated_effect": "ownership changes without authorization",
    "impact": "privilege takeover",
    "confidence": 0.84
  },
  "comparison": {
    "outcome": "likely_new_issue",
    "matched_findings": [],
    "related_findings": [],
    "rationale": [
      "No published finding covers unauthorized ownership rotation."
    ]
  },
  "policy": {
    "recommended_resolution": "manual_review_required",
    "advisory_verdict": "upheld",
    "abstained": true,
    "reasons": ["First-rollout policy does not auto-uphold semantic decisions."]
  },
  "metadata": {
    "extractor_model": "model-name",
    "extractor_prompt_version": "v1",
    "comparison_model": "model-name",
    "comparison_prompt_version": "v1"
  }
}
```

## Rollout Plan

### Phase 1

Introduce the structured substrate.

- issue [#170](https://github.com/akoita/proof-of-audit/issues/170)
- schemas for normalized claims, findings, and verifier dossiers

### Phase 2

Add post-execution claim extraction.

- issue [#171](https://github.com/akoita/proof-of-audit/issues/171)
- LLM-assisted structured claim extraction after deterministic execution

### Phase 3

Replace token matching with semantic comparison and policy.

- issue [#172](https://github.com/akoita/proof-of-audit/issues/172)
- semantic comparison layer and abstention-first policy

### Phase 4

Build the benchmark before expanding trust.

- issue [#173](https://github.com/akoita/proof-of-audit/issues/173)
- evaluation corpus and replayable verifier benchmark

### Phase 5

Expose verifier dossiers to humans and agents.

- issue [#174](https://github.com/akoita/proof-of-audit/issues/174)
- API, UI, and downstream agent-facing dossier support

## Recommendation

Challenge Verifier V2 should be built as:

`deterministic evidence validation + deterministic execution + structured semantic adjudication`

That is the path most likely to make Proof-of-Audit useful for autonomous
agents without turning the verifier into an opaque, overconfident model call.
